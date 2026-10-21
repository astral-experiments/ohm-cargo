use std::fs;
use std::path::Path;

use crate::CargoResult;
use crate::util::file_clone::try_clone;

/// Copies a regular file into an absent destination with independent writable state.
/// Returns its logical size and whether an explicit copy-on-write clone succeeded.
pub(super) fn copy_file(source: &Path, destination: &Path) -> CargoResult<(u64, bool)> {
    if try_clone(source, destination)? {
        let metadata = fs::metadata(source)?;
        fs::set_permissions(destination, metadata.permissions())?;
        return Ok((metadata.len(), true));
    }
    // Reserve our own file before the fallback, which otherwise overwrites paths.
    drop(
        fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(destination)?,
    );
    Ok((fs::copy(source, destination)?, false))
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
        assert_eq!(copy_file(&source, &destination)?.0, 8);
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
        assert!(copy_file(&source, &destination).is_err());
        assert_eq!(fs::read(&destination)?, b"private");
        Ok(())
    }
}
