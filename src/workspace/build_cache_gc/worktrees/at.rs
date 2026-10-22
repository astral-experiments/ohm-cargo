//! Operates on single names relative to a pinned private-cache directory.

use std::ffi::{CString, OsStr};
use std::fs::File;
use std::io;
use std::mem::MaybeUninit;
use std::os::fd::{AsRawFd as _, FromRawFd as _};
use std::os::unix::ffi::OsStrExt as _;
use std::os::unix::fs::MetadataExt as _;

use crate::CargoResult;
use crate::workspace::build_cache_gc::{CollectorLock, try_lock_opened};

fn basename(name: &OsStr) -> io::Result<CString> {
    let bytes = name.as_bytes();
    if bytes.is_empty() || bytes == b"." || bytes == b".." || bytes.contains(&b'/') {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "expected a single filename",
        ));
    }
    Ok(CString::new(bytes)?)
}

pub(super) fn open(
    dir: &File,
    name: &OsStr,
    flags: libc::c_int,
    mode: libc::c_uint,
) -> io::Result<File> {
    let name = basename(name)?;
    // SAFETY: both borrowed arguments are live; openat returns a fresh descriptor on success.
    let fd = unsafe {
        libc::openat(
            dir.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC,
            mode,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}

pub(super) fn open_dir(parent: &File, name: &OsStr) -> io::Result<File> {
    open(parent, name, libc::O_RDONLY | libc::O_DIRECTORY, 0)
}

pub(super) fn stat(dir: &File, name: &OsStr) -> io::Result<libc::stat> {
    let name = basename(name)?;
    let mut stat = MaybeUninit::uninit();
    // SAFETY: the directory and name remain live; a successful call initializes stat.
    if unsafe {
        libc::fstatat(
            dir.as_raw_fd(),
            name.as_ptr(),
            stat.as_mut_ptr(),
            libc::AT_SYMLINK_NOFOLLOW,
        )
    } < 0
    {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { stat.assume_init() })
}

pub(super) fn exists(dir: &File, name: &str) -> io::Result<bool> {
    match stat(dir, name.as_ref()) {
        Ok(_) => Ok(true),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(e) => Err(e),
    }
}

/// Returns the logical length only when the planned entry is still named in this directory.
#[allow(
    clippy::unnecessary_cast,
    reason = "libc device and inode types are platform-dependent"
)]
pub(super) fn entry_len(
    dir: &File,
    name: &OsStr,
    device: u64,
    inode: u64,
    directory: bool,
) -> io::Result<Option<u64>> {
    let stat = match stat(dir, name) {
        Ok(stat) => stat,
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(e),
    };
    let kind = stat.st_mode & libc::S_IFMT;
    let same_kind = if directory {
        kind == libc::S_IFDIR
    } else {
        matches!(kind, libc::S_IFREG | libc::S_IFLNK)
    };
    Ok((same_kind
        && stat.st_dev as u64 == device
        && stat.st_ino as u64 == inode
        && stat.st_size >= 0)
        .then_some(stat.st_size as u64))
}

pub(super) fn unlink(dir: &File, name: &OsStr, directory: bool) -> io::Result<()> {
    let name = basename(name)?;
    let flags = if directory { libc::AT_REMOVEDIR } else { 0 };
    // SAFETY: the borrowed directory and basename remain live throughout the call.
    if unsafe { libc::unlinkat(dir.as_raw_fd(), name.as_ptr(), flags) } < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

/// Create optional stock Cargo locks only during real cleanup. Check their binding after flock.
pub(super) fn lock_profile(
    dir: &File,
    name: &str,
    create: bool,
) -> CargoResult<Option<CollectorLock>> {
    let name = OsStr::new(name);
    let flags = if create { libc::O_CREAT } else { 0 };
    let file = open(dir, name, libc::O_RDONLY | flags, 0o666)?;
    let Some(lock) = try_lock_opened(file, true)? else {
        return Ok(None);
    };
    let held = lock.0.metadata()?;
    anyhow::ensure!(
        entry_len(dir, name, held.dev(), held.ino(), false)?.is_some(),
        "profile lock changed during acquisition"
    );
    Ok(Some(lock))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::os::unix::fs::symlink;

    #[test]
    fn replacing_a_parent_cannot_redirect_unlink_or_lock_creation() -> CargoResult<()> {
        let root = tempfile::tempdir()?;
        let original = root.path().join("profile");
        let outside = root.path().join("outside");
        for dir in [&original, &outside] {
            fs::create_dir(dir)?;
            fs::write(dir.join("payload"), b"data")?;
        }
        let root_fd = File::open(root.path())?;
        let pinned = open_dir(&root_fd, "profile".as_ref())?;
        let metadata = fs::symlink_metadata(original.join("payload"))?;
        fs::rename(&original, root.path().join("moved"))?;
        symlink(&outside, &original)?;
        assert!(open_dir(&root_fd, "profile".as_ref()).is_err());
        assert_eq!(
            entry_len(
                &pinned,
                "payload".as_ref(),
                metadata.dev(),
                metadata.ino(),
                false
            )?,
            Some(4)
        );
        unlink(&pinned, "payload".as_ref(), false)?;
        assert!(outside.join("payload").is_file());
        assert!(!root.path().join("moved/payload").exists());
        let missing = lock_profile(&pinned, ".cargo-lock", false).err().unwrap();
        assert_eq!(
            missing.downcast_ref::<io::Error>().unwrap().kind(),
            io::ErrorKind::NotFound
        );
        let _lock = lock_profile(&pinned, ".cargo-lock", true)?.unwrap();
        assert!(lock_profile(&pinned, ".cargo-lock", false)?.is_none());
        assert!(exists(&pinned, ".cargo-lock")?);
        assert!(!outside.join(".cargo-lock").exists());
        Ok(())
    }
}
