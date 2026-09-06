use std::fs;
#[cfg(any(target_os = "macos", target_os = "linux"))]
use std::io;
use std::path::Path;

use crate::CargoResult;

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

/// Unsupported cloning is an optional-cache miss; ordinary I/O errors still surface.
#[cfg(any(target_os = "macos", target_os = "linux"))]
fn clone_error(error: io::Error) -> CargoResult<bool> {
    match error.raw_os_error() {
        Some(code)
            if [
                libc::ENOTSUP,
                libc::EOPNOTSUPP,
                libc::ENOTTY,
                libc::ENOSYS,
                libc::EXDEV,
                libc::EINVAL,
            ]
            .contains(&code) =>
        {
            Ok(false)
        }
        _ => Err(error.into()),
    }
}

#[cfg(target_os = "macos")]
fn try_clone(source: &Path, destination: &Path) -> CargoResult<bool> {
    use std::ffi::CString;
    use std::os::unix::ffi::OsStrExt;

    let source = CString::new(source.as_os_str().as_bytes())?;
    let destination = CString::new(destination.as_os_str().as_bytes())?;
    // SAFETY: Both pointers refer to live, NUL-terminated path strings.
    if unsafe { libc::clonefile(source.as_ptr(), destination.as_ptr(), 0) } == 0 {
        return Ok(true);
    }
    let error = io::Error::last_os_error();
    // clonefile is atomic: a failed call does not create a destination to remove.
    clone_error(error)
}

#[cfg(target_os = "linux")]
fn try_clone(source: &Path, destination: &Path) -> CargoResult<bool> {
    use std::os::fd::AsRawFd;

    let input = fs::File::open(source)?;
    let output = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(destination)?;
    // SAFETY: Both descriptors remain open; FICLONE takes the source descriptor by value.
    let cloned = unsafe { libc::ioctl(output.as_raw_fd(), libc::FICLONE, input.as_raw_fd()) } == 0;
    let error = (!cloned).then(io::Error::last_os_error);
    drop(output);
    if !cloned {
        // create_new above proves this is the file created by our clone attempt.
        fs::remove_file(destination)?;
    }
    match error {
        Some(error) => clone_error(error),
        None => Ok(true),
    }
}

#[cfg(not(any(target_os = "macos", target_os = "linux")))]
fn try_clone(_source: &Path, _destination: &Path) -> CargoResult<bool> {
    Ok(false)
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

    #[test]
    #[cfg(any(target_os = "macos", target_os = "linux"))]
    fn real_clone_errors_are_not_cache_misses() {
        assert!(!clone_error(io::Error::from_raw_os_error(libc::ENOTSUP)).unwrap());
        assert!(!clone_error(io::Error::from_raw_os_error(libc::EOPNOTSUPP)).unwrap());
        assert!(!clone_error(io::Error::from_raw_os_error(libc::EXDEV)).unwrap());
        for code in [libc::ENOSPC, libc::EIO, libc::EACCES, libc::EEXIST] {
            assert!(clone_error(io::Error::from_raw_os_error(code)).is_err());
        }
    }
}
