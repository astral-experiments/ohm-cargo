//! Compares storage paths across filesystem aliases before acquiring locks or removing files.

use std::fs;
use std::io;
use std::path::Path;

use crate::CargoResult;

/// Tests whether a resolved path names an ancestor's already allocated root or lock.
pub(crate) fn same_file(path: &Path, other: &Path) -> io::Result<bool> {
    if path == other {
        return Ok(true);
    }
    match fs::metadata(other).and_then(|metadata| same_existing(path, other, &metadata)) {
        Err(error)
            if matches!(
                error.kind(),
                io::ErrorKind::NotFound | io::ErrorKind::NotADirectory
            ) =>
        {
            Ok(false)
        }
        result => result,
    }
}

/// Compares an existing object without opening a lock file or blocking on a FIFO.
fn same_existing(path: &Path, other: &Path, _other_metadata: &fs::Metadata) -> io::Result<bool> {
    if path == other {
        return Ok(true);
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt as _;
        let metadata = fs::metadata(path)?;
        Ok((metadata.dev(), metadata.ino()) == (_other_metadata.dev(), _other_metadata.ino()))
    }
    #[cfg(not(unix))]
    same_file::is_same_file(path, other)
}

/// Checks whether either storage root contains the other, including missing descendants.
pub(crate) fn overlaps(left: &Path, right: &Path) -> CargoResult<bool> {
    Ok(starts_with(left, right)? || starts_with(right, left)?)
}

/// Finds the on-disk prefix of an absolute storage path without creating its missing tail.
fn existing_storage_ancestor(path: &Path) -> io::Result<(&Path, fs::Metadata)> {
    for ancestor in path.ancestors() {
        match fs::metadata(ancestor) {
            Ok(metadata) => return Ok((ancestor, metadata)),
            Err(error)
                if matches!(
                    error.kind(),
                    io::ErrorKind::NotFound | io::ErrorKind::NotADirectory
                ) => {}
            Err(error) => return Err(error),
        }
    }
    Err(io::ErrorKind::NotFound.into())
}

/// Compares resolved storage paths using the filesystem's lookup rules for missing names.
pub(crate) fn starts_with(path: &Path, base: &Path) -> CargoResult<bool> {
    if path.starts_with(base) {
        return Ok(true);
    }
    let (left, left_metadata) = existing_storage_ancestor(path)?;
    let (right, right_metadata) = existing_storage_ancestor(base)?;
    if !left_metadata.is_dir() || !right_metadata.is_dir() {
        return Ok(false);
    }
    if right == base {
        for ancestor in left.ancestors() {
            if same_existing(ancestor, right, &right_metadata)? {
                return Ok(true);
            }
        }
        #[cfg(target_os = "linux")]
        return crate::util::mountinfo::is_bind_descendant(left, right);
        #[cfg(not(target_os = "linux"))]
        return Ok(false);
    }
    if !same_existing(left, right, &right_metadata)? {
        return Ok(false);
    }
    let mut remaining = path.strip_prefix(left)?.iter();
    let mut missing = Vec::new();
    for b in base.strip_prefix(right)? {
        let Some(a) = remaining.next() else {
            return Ok(false);
        };
        if a != b {
            missing.push((a, b));
        }
    }
    if missing.is_empty() {
        return Ok(true);
    }
    // Both tails are absent under the same directory. Probe differing names on that
    // filesystem without creating either requested path. This also handles Unicode aliases.
    let probe = tempfile::tempdir_in(left)?;
    for (a, b) in missing {
        let entry = probe.path().join(a);
        fs::create_dir(&entry)?;
        if !probe.path().join(b).try_exists()? {
            return Ok(false);
        }
        fs::remove_dir(entry)?;
    }
    Ok(true)
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;

    #[test]
    fn storage_aliases_can_have_different_numbers_of_ancestors() -> CargoResult<()> {
        let root = tempfile::tempdir()?;
        let source = root.path().join("storage");
        let directory = root.path().join("several/levels");
        fs::create_dir(&source)?;
        fs::create_dir_all(&directory)?;
        let alias = directory.join("view");
        // A symlink lets the test give a directory two names without mounting a filesystem.
        std::os::unix::fs::symlink(&source, &alias)?;
        assert!(overlaps(&source.join("new"), &alias.join("new"))?);
        assert!(overlaps(&alias.join("new"), &source.join("new/child"))?);
        assert!(overlaps(&source, &alias.join("new/child"))?);
        assert!(!overlaps(&source.join("one"), &alias.join("two"))?);
        Ok(())
    }
}
