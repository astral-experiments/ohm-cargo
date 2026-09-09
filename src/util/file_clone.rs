//! Copy-on-write file cloning shared by snapshot import and capability admission.

use std::fs;
use std::io;
use std::path::Path;

use crate::CargoResult;

/// Tests the same clone operation used to import a snapshot, without copying fallback.
///
/// The source namespace may not exist yet. Probe in its nearest existing directory,
/// where it will inherit the filesystem, and likewise for the destination parent.
/// No persistent capability marker survives this Cargo invocation.
pub(crate) fn supported_between(source: &Path, destination: &Path) -> bool {
    fn existing_directory(mut path: &Path) -> io::Result<&Path> {
        loop {
            match fs::symlink_metadata(path) {
                Ok(metadata) if metadata.is_dir() => return Ok(path),
                Ok(_) => return Err(io::Error::other("clone probe requires a plain directory")),
                Err(error) if error.kind() == io::ErrorKind::NotFound => {
                    path = path.parent().ok_or(error)?;
                }
                Err(error) => return Err(error),
            }
        }
    }
    let probe = || -> CargoResult<bool> {
        let source = tempfile::Builder::new()
            .prefix(".ohm-clone-probe-")
            .tempdir_in(existing_directory(source)?)?;
        let destination = tempfile::Builder::new()
            .prefix(".ohm-clone-probe-")
            .tempdir_in(existing_directory(destination)?)?;
        // A nonempty file exercises extent cloning rather than only inode creation.
        let input = source.path().join("source");
        fs::write(&input, [0x42; 4096])?;
        let cloned = try_clone(&input, &destination.path().join("clone"))?;
        destination.close()?;
        source.close()?;
        Ok(cloned)
    };
    probe().unwrap_or(false)
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
pub(crate) fn try_clone(source: &Path, destination: &Path) -> CargoResult<bool> {
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
    // clonefile is atomic: a failed call does not create a destination to remove.
    clone_error(error)
}

#[cfg(target_os = "linux")]
pub(crate) fn try_clone(source: &Path, destination: &Path) -> CargoResult<bool> {
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
pub(crate) fn try_clone(_source: &Path, _destination: &Path) -> CargoResult<bool> {
    Ok(false)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[cfg(any(target_os = "macos", target_os = "linux"))]
    fn cloned_files_are_independent_and_existing_destinations_are_preserved() -> CargoResult<()> {
        let root = tempfile::tempdir()?;
        let source = root.path().join("source");
        let destination = root.path().join("destination");
        fs::write(&source, b"snapshot")?;
        let supported = cargo_test_support::paths::clone_file(&source, &root.path().join("probe"));
        let cloned = try_clone(&source, &destination)?;
        assert_eq!(
            cloned, supported,
            "Cargo and the independent clone probe disagree"
        );
        if !cloned {
            assert!(!destination.exists());
            return Ok(());
        }
        assert_eq!(fs::read(&destination)?, b"snapshot");
        assert!(!same_file::is_same_file(&source, &destination)?);
        fs::write(&destination, b"private")?;
        assert_eq!(fs::read(&source)?, b"snapshot");
        assert!(try_clone(&source, &destination).is_err());
        assert_eq!(fs::read(&destination)?, b"private");
        Ok(())
    }

    #[test]
    fn capability_probe_cleans_up_and_does_not_create_namespace_directories() {
        let root = tempfile::tempdir().unwrap();
        let source = root.path().join("source");
        fs::create_dir(&source).unwrap();
        fs::write(source.join("keep"), b"unchanged").unwrap();
        let _ = supported_between(&source.join("future-namespace"), root.path());
        assert_eq!(fs::read(source.join("keep")).unwrap(), b"unchanged");
        assert_eq!(fs::read_dir(&source).unwrap().count(), 1);
        assert_eq!(fs::read_dir(root.path()).unwrap().count(), 1);
        assert!(!supported_between(&source.join("keep"), root.path()));
        assert_eq!(fs::read_dir(root.path()).unwrap().count(), 1);
    }

    #[test]
    #[cfg(unix)]
    fn capability_probe_rejects_symlinked_namespaces() {
        let root = tempfile::tempdir().unwrap();
        let source = root.path().join("source");
        fs::create_dir(&source).unwrap();
        let link = root.path().join("link");
        std::os::unix::fs::symlink(&source, &link).unwrap();
        assert!(!supported_between(&link, root.path()));
        assert_eq!(fs::read_dir(&source).unwrap().count(), 0);
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
