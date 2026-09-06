use std::fs;
use std::path::Path;

use crate::CargoResult;
use crate::util::file_clone::try_clone;

/// Copies a regular file into an absent destination with independent writable state.
/// Returns `None` when cloning is unavailable and byte copying was not requested.
/// Otherwise returns the logical size and whether a copy-on-write clone succeeded.
pub(super) fn copy_file(
    source: &Path,
    destination: &Path,
    allow_copy: bool,
) -> CargoResult<Option<(u64, bool)>> {
    copy_file_with(source, destination, allow_copy, try_clone)
}

fn copy_file_with(
    source: &Path,
    destination: &Path,
    allow_copy: bool,
    clone: impl FnOnce(&Path, &Path) -> CargoResult<bool>,
) -> CargoResult<Option<(u64, bool)>> {
    if clone(source, destination)? {
        let metadata = fs::metadata(source)?;
        fs::set_permissions(destination, metadata.permissions())?;
        return Ok(Some((metadata.len(), true)));
    }
    if !allow_copy {
        return Ok(None);
    }
    // Reserve our own file before the fallback, which otherwise overwrites paths.
    drop(
        fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(destination)?,
    );
    Ok(Some((fs::copy(source, destination)?, false)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn copied_files_are_independent_and_existing_destinations_are_preserved() -> CargoResult<()> {
        let root = tempfile::tempdir()?;
        let source = root.path().join("source");
        let destination = root.path().join("destination");
        fs::write(&source, b"snapshot")?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&source, fs::Permissions::from_mode(0o750))?;
        }
        assert_eq!(copy_file(&source, &destination, true)?.unwrap().0, 8);
        assert_eq!(fs::read(&destination)?, b"snapshot");
        assert!(!same_file::is_same_file(&source, &destination)?);
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                fs::metadata(&destination)?.permissions().mode() & 0o777,
                0o750
            );
        }
        fs::write(&destination, b"private")?;
        assert_eq!(fs::read(&source)?, b"snapshot");
        assert!(copy_file(&source, &destination, true).is_err());
        assert_eq!(fs::read(&destination)?, b"private");
        Ok(())
    }

    #[test]
    fn unsupported_cloning_requires_explicit_copying() -> CargoResult<()> {
        let root = tempfile::tempdir()?;
        let source = root.path().join("source");
        let destination = root.path().join("destination");
        fs::write(&source, b"snapshot")?;
        assert_eq!(
            copy_file_with(&source, &destination, false, |_, _| Ok(false))?,
            None
        );
        assert!(!destination.exists());
        assert_eq!(
            copy_file_with(&source, &destination, true, |_, _| Ok(false))?,
            Some((8, false))
        );
        assert!(!same_file::is_same_file(&source, &destination)?);
        fs::write(destination, b"private")?;
        assert_eq!(fs::read(source)?, b"snapshot");
        Ok(())
    }

    #[test]
    fn default_cloning_never_copies_bytes() -> CargoResult<()> {
        let root = tempfile::tempdir()?;
        let source = root.path().join("source");
        let destination = root.path().join("destination");
        fs::write(&source, b"snapshot")?;
        match copy_file(&source, &destination, false)? {
            Some((8, true)) => {
                assert!(!same_file::is_same_file(&source, &destination)?);
                fs::write(destination, b"private")?;
                assert_eq!(fs::read(source)?, b"snapshot");
            }
            None => assert!(!destination.exists()),
            other => panic!("unexpected clone result: {other:?}"),
        }
        Ok(())
    }
}
