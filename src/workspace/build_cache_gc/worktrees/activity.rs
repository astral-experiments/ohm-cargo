//! Tracks the last use of a private target across workspaces and Cargo homes.

use std::ffi::{CString, OsStr};
use std::fs::{self, File, Metadata, OpenOptions};
use std::io;
use std::os::unix::ffi::OsStrExt as _;
use std::os::unix::fs::{MetadataExt as _, OpenOptionsExt as _};
use std::path::Path;
use std::time::SystemTime;

use crate::compiler::Layout;
use crate::util::{CargoResult, flock};
use crate::workspace::build_cache_gc::CONTEXT_MAX_IDLE;
use crate::workspace::build_cache_gc::tracker::used_through;

use super::at;

pub(crate) const MARKER: &str = ".ohm-target-last-use-v1";

pub(crate) struct TargetUse {
    directory: Option<File>,
    used_through: Option<SystemTime>,
}

impl TargetUse {
    /// The shared target lease already excludes cleanup during a build or import.
    pub(crate) fn start(root: &Path, lock: &File) -> CargoResult<Self> {
        let now = SystemTime::now();
        let directory = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY)
            .open(root)?;
        let named = at::open(
            &directory,
            OsStr::new(Layout::PRIVATE_BUILD_LOCK),
            libc::O_RDONLY,
            0,
        )?
        .metadata()?;
        let held = lock.metadata()?;
        // Pin the directory for the whole lease, including a long build finishing
        // after the target moved. A replacement's warm marker cannot stand in for it.
        if !named.is_file()
            || named.nlink() != 1
            || (held.dev(), held.ino()) != (named.dev(), named.ino())
        {
            lock.set_modified(now)?;
            return Ok(Self {
                directory: None,
                used_through: None,
            });
        }
        let used_through = record(&directory, now)?;
        Ok(Self {
            directory: Some(directory),
            used_through,
        })
    }

    /// Short builds stay read-only. Long builds renew use before releasing the lease.
    pub(crate) fn finish(&self, lock: &File) {
        self.finish_at(lock, SystemTime::now());
    }

    fn finish_at(&self, lock: &File, now: SystemTime) {
        if let Some(directory) = &self.directory
            && self.used_through.is_none_or(|end| now > end)
            && let Err(error) = record(directory, now)
        {
            // If both updating and unlinking a trusted stamp failed, invalidate
            // existing enrollment receipts before releasing the target lock.
            if let Err(invalidate) = lock.set_modified(now) {
                tracing::warn!(
                    ?error,
                    ?invalidate,
                    "could not invalidate private target activity"
                );
            }
        }
    }
}

fn stamp(metadata: &Metadata) -> Option<SystemTime> {
    (metadata.is_file() && metadata.nlink() == 1 && metadata.len() == 0)
        .then(|| metadata.modified().ok())
        .flatten()
}

/// A missing or untrusted marker, or a clock that moved backwards, cannot establish age.
pub(crate) fn idle(root: &Path, now: SystemTime) -> bool {
    let path = root.join(MARKER);
    // Use the collector's effective credentials without opening for write, even in dry-run.
    let Ok(name) = CString::new(path.as_os_str().as_bytes()) else {
        return false;
    };
    // SAFETY: the absolute, NUL-terminated pathname is live across the call.
    let access = unsafe {
        libc::faccessat(
            libc::AT_FDCWD,
            name.as_ptr(),
            libc::W_OK,
            libc::AT_EACCESS | libc::AT_SYMLINK_NOFOLLOW,
        )
    };
    access == 0
        && fs::symlink_metadata(&path)
            .ok()
            .and_then(|metadata| stamp(&metadata))
            .and_then(|used| now.duration_since(used).ok())
            .is_some_and(|age| age >= CONTEXT_MAX_IDLE)
}

fn record(directory: &File, now: SystemTime) -> CargoResult<Option<SystemTime>> {
    let end = used_through(now)?;
    let name = OsStr::new(MARKER);
    // futimens accepts an owner's read-only fd. Warm reads produce no write-open event.
    let file = match at::open(directory, name, libc::O_RDONLY | libc::O_CREAT, 0o600) {
        Ok(file) => file,
        Err(error) => {
            // Even a mode-000 marker can become readable again after a build.
            // Forget its old timestamp when the target directory permits it.
            match at::stat(directory, name) {
                Ok(stat)
                    if stat.st_mode & libc::S_IFMT == libc::S_IFREG
                        && stat.st_nlink == 1
                        && stat.st_size == 0 =>
                {
                    unlink_marker(directory, name)?;
                }
                Ok(_) => {}
                Err(e) if e.kind() == io::ErrorKind::NotFound => {}
                Err(_) => return Err(error.into()),
            }
            return Ok(None);
        }
    };
    let Some(previous) = stamp(&file.metadata()?) else {
        return Ok(None);
    };
    if previous >= end {
        return Ok(Some(previous));
    }
    // Builders share the target lock. Serialize only the one timestamp write per
    // bucket so a delayed writer cannot overwrite a newer timestamp.
    let update = || -> CargoResult<Option<SystemTime>> {
        flock::try_lock_exclusive(&file).map_err(io::Error::from)?;
        let Some(previous) = stamp(&file.metadata()?) else {
            return Ok(None);
        };
        if previous >= end {
            return Ok(Some(previous));
        }
        file.set_modified(end)?;
        anyhow::ensure!(
            file.metadata()?.modified()? >= now,
            "filesystem truncated activity time"
        );
        Ok(Some(end))
    };
    match update() {
        Ok(used) => Ok(used),
        Err(error) => invalidate(directory, name, &file, now, error),
    }
}

/// A later GC must not trust an old timestamp when recording use fails.
fn invalidate(
    directory: &File,
    name: &OsStr,
    recorded: &File,
    used: SystemTime,
    error: anyhow::Error,
) -> CargoResult<Option<SystemTime>> {
    let current = match at::open(directory, name, libc::O_RDONLY, 0) {
        Ok(file) => file.metadata()?,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error.into()),
    };
    let recorded = recorded.metadata()?;
    if (current.dev(), current.ino()) == (recorded.dev(), recorded.ino()) {
        if let Some(saved) = stamp(&recorded).filter(|saved| *saved >= used) {
            return Ok(Some(saved));
        }
        if unlink_marker(directory, name).is_err() {
            return Err(error);
        }
    }
    Ok(None)
}

fn unlink_marker(directory: &File, name: &OsStr) -> io::Result<()> {
    match at::unlink(directory, name, false) {
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        result => result,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::workspace::global_cache_tracker::UPDATE_RESOLUTION;
    use std::os::unix::fs::symlink;
    use std::time::{Duration, UNIX_EPOCH};

    #[test]
    fn fresh_builds_share_a_bucket_and_long_builds_extend_it() -> CargoResult<()> {
        let root = tempfile::tempdir()?;
        let lock = File::create_new(root.path().join(Layout::PRIVATE_BUILD_LOCK))?;
        let directory = File::open(root.path())?;
        let path = root.path().join(MARKER);
        assert!(!idle(root.path(), SystemTime::now()));
        let marker = File::create_new(&path)?;
        marker.set_modified(UNIX_EPOCH)?;
        let start = UNIX_EPOCH + Duration::from_secs(UPDATE_RESOLUTION * 100 + 2);
        let end = UNIX_EPOCH + Duration::from_secs(UPDATE_RESOLUTION * 101);
        assert_eq!(record(&directory, start)?, Some(end));
        let before = marker.metadata()?;
        let usage = TargetUse {
            directory: Some(directory.try_clone()?),
            used_through: Some(end),
        };
        assert_eq!(
            record(&directory, start + Duration::from_secs(1))?,
            Some(end)
        );
        usage.finish_at(&lock, end);
        let after = marker.metadata()?;
        assert_eq!(
            (before.ctime(), before.ctime_nsec()),
            (after.ctime(), after.ctime_nsec())
        );
        assert!(!idle(
            root.path(),
            end + CONTEXT_MAX_IDLE - Duration::from_nanos(1)
        ));
        assert!(idle(root.path(), end + CONTEXT_MAX_IDLE));
        usage.finish_at(&lock, end + CONTEXT_MAX_IDLE + Duration::from_secs(1));
        assert!(!idle(root.path(), end + CONTEXT_MAX_IDLE * 2));
        assert_eq!(
            marker.metadata()?.modified()?,
            end + CONTEXT_MAX_IDLE + Duration::from_secs(UPDATE_RESOLUTION)
        );
        Ok(())
    }

    #[test]
    fn untrusted_markers_and_replaced_targets_do_not_authorize_age() -> CargoResult<()> {
        let root = tempfile::tempdir()?;
        let target = root.path().join("target");
        fs::create_dir(&target)?;
        let lock = File::create_new(target.join(Layout::PRIVATE_BUILD_LOCK))?;
        let directory = File::open(&target)?;
        let outside = root.path().join("outside");
        let original = File::create_new(&outside)?;
        original.set_modified(UNIX_EPOCH)?;
        let path = target.join(MARKER);
        let now = SystemTime::now();
        for link in [false, true] {
            if link {
                symlink(&outside, &path)?;
            } else {
                fs::hard_link(&outside, &path)?;
            }
            assert!(!idle(&target, now));
            assert!(record(&directory, now)?.is_none());
            assert_eq!(original.metadata()?.modified()?, UNIX_EPOCH);
            fs::remove_file(&path)?;
        }
        fs::rename(&target, root.path().join("previous"))?;
        fs::create_dir(&target)?;
        File::create_new(target.join(Layout::PRIVATE_BUILD_LOCK))?;
        let warm = File::create_new(&path)?;
        let future = now + CONTEXT_MAX_IDLE;
        warm.set_modified(future)?;
        let usage = TargetUse::start(&target, &lock)?;
        assert!(usage.directory.is_none());
        assert_eq!(warm.metadata()?.modified()?, future);
        Ok(())
    }

    #[test]
    fn long_build_refreshes_the_moved_physical_directory() -> CargoResult<()> {
        let root = tempfile::tempdir()?;
        let target = root.path().join("target");
        fs::create_dir(&target)?;
        let lock = File::create_new(target.join(Layout::PRIVATE_BUILD_LOCK))?;
        let usage = TargetUse::start(&target, &lock)?;
        let moved = root.path().join("moved");
        fs::rename(&target, &moved)?;
        fs::create_dir(&target)?;
        File::create_new(target.join(Layout::PRIVATE_BUILD_LOCK))?;
        let finish = usage.used_through.unwrap() + CONTEXT_MAX_IDLE;
        usage.finish_at(&lock, finish);
        assert!(fs::metadata(moved.join(MARKER))?.modified()? >= finish);
        assert!(!target.join(MARKER).exists());
        Ok(())
    }

    #[test]
    fn failed_refresh_invalidates_only_the_same_marker() -> CargoResult<()> {
        let root = tempfile::tempdir()?;
        let directory = File::open(root.path())?;
        let name = OsStr::new(MARKER);
        let path = root.path().join(MARKER);
        let old = File::create_new(&path)?;
        fs::rename(&path, root.path().join("old"))?;
        let new = File::create_new(&path)?;
        let now = SystemTime::now() + CONTEXT_MAX_IDLE;
        invalidate(
            &directory,
            name,
            &old,
            now,
            anyhow::anyhow!("failed refresh"),
        )?;
        assert!(path.exists());
        invalidate(
            &directory,
            name,
            &new,
            now,
            anyhow::anyhow!("failed refresh"),
        )?;
        assert!(!path.exists());
        assert!(!idle(root.path(), SystemTime::now() + CONTEXT_MAX_IDLE * 2));
        Ok(())
    }

    #[test]
    fn overlapping_writers_never_block_a_build_on_the_timestamp() -> CargoResult<()> {
        let root = tempfile::tempdir()?;
        let lock = File::create_new(root.path().join(Layout::PRIVATE_BUILD_LOCK))?;
        let path = root.path().join(MARKER);
        let paused = File::create_new(&path)?;
        paused.set_modified(UNIX_EPOCH)?;
        flock::lock_exclusive(&paused)?;
        let usage = TargetUse::start(root.path(), &lock)?;
        assert!(usage.used_through.is_none());
        assert!(!path.exists());
        usage.finish(&lock);
        assert!(path.exists());
        assert!(!idle(root.path(), SystemTime::now()));
        Ok(())
    }
}
