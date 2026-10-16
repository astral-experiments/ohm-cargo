//! Keeps shared build artifacts available while Cargo or its children use them.

use crate::util::CargoResult;
use cargo_util::ProcessBuilder;
use std::path::Path;

/// A root-wide shared lease, acquired before any profile or workspace locks.
///
/// The file is closed rather than explicitly unlocked: children may inherit the
/// same open file description and continue using artifacts after Cargo exits.
#[derive(Clone)]
pub(crate) struct ConsumerLease {
    #[cfg(any(target_os = "linux", target_os = "macos"))]
    file: std::sync::Arc<std::fs::File>,
}

impl ConsumerLease {
    /// Acquires the stable consumer lock without following metadata symlinks.
    pub(crate) fn acquire(root: &Path) -> CargoResult<Self> {
        #[cfg(any(target_os = "linux", target_os = "macos"))]
        {
            use super::build_cache_gc::{CONSUMERS_LOCK, metadata_dir};
            use anyhow::{Context, ensure};
            use std::fs::{self, OpenOptions};
            use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
            use std::sync::Arc;

            fs::create_dir_all(root)?;
            let root = root.canonicalize()?;
            ensure!(
                !crate::compiler::layout::shared_registry_directory_is_nfs(&root)?,
                "shared registry caching requires reliable filesystem locks"
            );
            let directory = metadata_dir(&root, true)?;
            let before = fs::symlink_metadata(&directory)?;

            let path = directory.join(CONSUMERS_LOCK);
            let file = OpenOptions::new()
                .read(true)
                .write(true)
                .create(true)
                .truncate(false)
                .mode(0o600)
                .custom_flags(libc::O_NOFOLLOW)
                .open(&path)
                .with_context(|| format!("opening build cache consumer lock {}", path.display()))?;
            let opened = file.metadata()?;
            ensure!(
                opened.is_file(),
                "build cache consumer lock must be a regular file"
            );
            crate::util::flock::lock_shared(&file)
                .context("locking shared build cache for artifact consumers")?;

            let after = fs::symlink_metadata(&directory)?;
            let named = fs::symlink_metadata(&path)?;
            ensure!(
                after.is_dir()
                    && (before.dev(), before.ino()) == (after.dev(), after.ino())
                    && named.is_file()
                    && (opened.dev(), opened.ino()) == (named.dev(), named.ino()),
                "build cache consumer lock changed while acquiring it"
            );
            Ok(Self {
                file: Arc::new(file),
            })
        }
        #[cfg(not(any(target_os = "linux", target_os = "macos")))]
        {
            // Collection is disabled where inherited file leases are not supported.
            let _ = root;
            Ok(Self {})
        }
    }

    /// Extends the lease through a child process, including process replacement.
    pub(crate) fn inherit(&self, command: &mut ProcessBuilder) {
        #[cfg(any(target_os = "linux", target_os = "macos"))]
        command.inherit_file(std::sync::Arc::clone(&self.file));
        #[cfg(not(any(target_os = "linux", target_os = "macos")))]
        let _ = command;
    }
}

#[cfg(all(test, any(target_os = "linux", target_os = "macos")))]
mod tests {
    use super::ConsumerLease;
    use crate::workspace::build_cache_gc::{CONSUMERS_LOCK, DIRECTORY};
    use std::fs::OpenOptions;

    #[test]
    fn shared_lease_lasts_until_its_last_owner_is_dropped() -> anyhow::Result<()> {
        let root = tempfile::tempdir()?;
        let lease = ConsumerLease::acquire(root.path())?;
        let retained = lease.clone();
        let collector = OpenOptions::new()
            .read(true)
            .write(true)
            .open(root.path().join(DIRECTORY).join(CONSUMERS_LOCK))?;
        drop(lease);
        assert!(matches!(
            crate::util::flock::try_lock_exclusive(&collector),
            Err(std::fs::TryLockError::WouldBlock)
        ));
        drop(retained);
        crate::util::flock::try_lock_exclusive(&collector)?;
        Ok(())
    }

    #[test]
    fn refuses_symlinked_metadata_or_lock() -> anyhow::Result<()> {
        use std::fs;
        use std::os::unix::fs::symlink;

        let root = tempfile::tempdir()?;
        let other = tempfile::tempdir()?;
        let directory = root.path().join(DIRECTORY);
        symlink(other.path(), &directory)?;
        assert!(ConsumerLease::acquire(root.path()).is_err());
        fs::remove_file(&directory)?;
        fs::create_dir(&directory)?;
        let other_file = other.path().join("lock");
        fs::write(&other_file, b"unchanged")?;
        symlink(&other_file, directory.join(CONSUMERS_LOCK))?;
        assert!(ConsumerLease::acquire(root.path()).is_err());
        assert_eq!(fs::read(other_file)?, b"unchanged");
        Ok(())
    }
}
