use std::fs;
use std::path::Path;

use crate::CargoResult;

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

#[cfg(target_os = "macos")]
fn try_clone(source: &Path, destination: &Path) -> CargoResult<bool> {
    use std::ffi::CString;
    use std::io;
    use std::os::unix::ffi::OsStrExt;

    let source = CString::new(source.as_os_str().as_bytes())?;
    let destination = CString::new(destination.as_os_str().as_bytes())?;
    // SAFETY: Both pointers refer to live, NUL-terminated path strings.
    if unsafe { libc::clonefile(source.as_ptr(), destination.as_ptr(), 0) } == 0 {
        return Ok(true);
    }
    let error = io::Error::last_os_error();
    if error.kind() == io::ErrorKind::AlreadyExists {
        return Err(error.into());
    }
    // clonefile is atomic: a failed call does not create a destination to remove.
    Ok(false)
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
    drop(output);
    if !cloned {
        // create_new above proves this is the file created by our clone attempt.
        fs::remove_file(destination)?;
    }
    Ok(cloned)
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
