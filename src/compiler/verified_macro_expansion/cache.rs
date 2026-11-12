use std::fs::File;
use std::io::Read;
use std::os::unix::fs::{FileExt as _, MetadataExt as _};
use std::path::Path;
use std::sync::LazyLock;

use rustix::fs::{Mode, OFlags, mkdirat, open, openat};

const DIRECTORY: &str = ".ohm-verified-expansions-v1";

pub(super) struct Entry {
    directory: File,
    slot: String,
    key: blake3::Hash,
}

impl Entry {
    pub(super) fn new(
        home: &Path,
        native_metadata: &Path,
        package_checksum: &str,
        fingerprint: &[u8],
        compiler: &[u8],
    ) -> Option<Self> {
        let home = open(
            home,
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NONBLOCK | OFlags::CLOEXEC,
            Mode::empty(),
        )
        .ok()?;
        let private = Mode::from_raw_mode(0o700);
        let _ = mkdirat(&home, DIRECTORY, private);
        // Keep the directory descriptor for the lifetime of both lookups. A writable
        // Cargo-home parent may otherwise be swapped between a permission check and use.
        let directory = File::from(
            openat(
                &home,
                DIRECTORY,
                read_flags() | OFlags::DIRECTORY,
                Mode::empty(),
            )
            .ok()?,
        );
        let dir = directory.metadata().ok()?;
        if !dir.is_dir() || !owned_private(&dir) {
            return None;
        }

        let file = File::from(open(native_metadata, read_flags(), Mode::empty()).ok()?);
        let metadata = file.metadata().ok()?;
        if !metadata.is_file() || metadata.len() > 128 * 1024 * 1024 {
            return None;
        }
        static FORMAT: LazyLock<blake3::Hash> = LazyLock::new(|| {
            let mut hash = blake3::Hasher::new();
            hash.update(include_bytes!("mod.rs"));
            hash.update(include_bytes!("cache.rs"));
            hash.update(include_bytes!("../../../Cargo.lock"));
            hash.finalize()
        });
        let mut hash = blake3::Hasher::new_keyed(FORMAT.as_bytes());
        for input in [
            native_metadata.as_os_str().as_encoded_bytes(),
            package_checksum.as_bytes(),
            fingerprint,
            compiler,
        ] {
            hash.update(&(input.len() as u64).to_le_bytes())
                .update(input);
        }
        hash.update(&metadata.dev().to_le_bytes())
            .update(&metadata.ino().to_le_bytes())
            .update(&metadata.ctime().to_le_bytes())
            .update(&metadata.ctime_nsec().to_le_bytes())
            .update(&metadata.len().to_le_bytes());
        hash.update_reader((&file).take(metadata.len() + 1)).ok()?;
        let end = file.metadata().ok()?;
        if end.ctime() != metadata.ctime()
            || end.ctime_nsec() != metadata.ctime_nsec()
            || end.len() != metadata.len()
        {
            return None;
        }
        let key = hash.finalize();
        // Replacement is bounded to 4096 slots; readers compare the complete digest.
        let slot = key.to_hex()[..3].to_owned();
        Some(Self {
            directory,
            slot,
            key,
        })
    }

    pub(super) fn contains(&self) -> bool {
        let Some(file) = self.open_record(false) else {
            return false;
        };
        let mut saved = [0; 32];
        file.read_exact_at(&mut saved, 0).is_ok() && saved == *self.key.as_bytes()
    }

    pub(super) fn record(&self) -> bool {
        self.open_record(true)
            .is_some_and(|file| file.write_all_at(self.key.as_bytes(), 0).is_ok())
            // A concurrent writer may have already published this exact proof.
            || self.contains()
    }

    fn open_record(&self, write: bool) -> Option<File> {
        let mut flags = OFlags::CLOEXEC | OFlags::NOFOLLOW | OFlags::NONBLOCK;
        flags |= if write {
            OFlags::RDWR | OFlags::CREATE
        } else {
            OFlags::RDONLY
        };
        let file = File::from(
            openat(
                &self.directory,
                self.slot.as_str(),
                flags,
                Mode::from_raw_mode(0o600),
            )
            .ok()?,
        );
        let meta = file.metadata().ok()?;
        // A short or racing slot cannot authenticate another compiler input. Never
        // overwrite linked or special files in a replaced or restored directory.
        (meta.is_file()
            && owned_private(&meta)
            && meta.nlink() == 1
            && (meta.len() == 32 || write && meta.len() == 0))
            .then_some(file)
    }
}

fn owned_private(meta: &std::fs::Metadata) -> bool {
    // SAFETY: geteuid takes no arguments and has no safety requirements.
    meta.uid() == unsafe { libc::geteuid() } && meta.mode() & 0o077 == 0
}

fn read_flags() -> OFlags {
    OFlags::RDONLY | OFlags::CLOEXEC | OFlags::NOFOLLOW | OFlags::NONBLOCK
}

#[cfg(test)]
mod tests {
    use super::Entry;
    use std::fs;
    use std::os::unix::fs::{PermissionsExt as _, symlink};
    use std::sync::{Arc, Barrier};
    use std::thread;

    #[test]
    fn authenticates_the_complete_artifact_and_compiler_context() {
        let root = tempfile::tempdir().unwrap();
        let metadata = root.path().join("libsample.rmeta");
        fs::write(&metadata, b"product").unwrap();
        let receipt = |profile, compiler| {
            Entry::new(root.path(), &metadata, "package", profile, compiler).unwrap()
        };
        let original = receipt(b"unit", b"compiler");
        assert!(!original.contains());
        assert!(original.record());
        assert!(receipt(b"unit", b"compiler").contains());
        assert!(!receipt(b"other unit", b"compiler").contains());
        assert!(!receipt(b"unit", b"other compiler").contains());
        fs::write(&metadata, b"another product").unwrap();
        assert!(!receipt(b"unit", b"compiler").contains());
    }

    #[test]
    fn linked_and_malformed_records_never_overwrite_other_files() {
        let root = tempfile::tempdir().unwrap();
        let metadata = root.path().join("libsample.rmeta");
        fs::write(&metadata, b"native product").unwrap();
        let receipt = Entry::new(root.path(), &metadata, "package", b"unit", b"compiler").unwrap();
        let directory = root.path().join(super::DIRECTORY);
        let slot = directory.join(&receipt.slot);
        let victim = root.path().join("keep");
        fs::write(&victim, [0x41; 32]).unwrap();
        fs::set_permissions(&victim, fs::Permissions::from_mode(0o600)).unwrap();
        symlink(&victim, &slot).unwrap();
        assert!(!receipt.contains() && !receipt.record());
        fs::remove_file(&slot).unwrap();
        fs::hard_link(&victim, &slot).unwrap();
        assert!(!receipt.contains() && !receipt.record());
        fs::remove_file(&slot).unwrap();
        fs::write(&slot, b"bad").unwrap();
        assert!(!receipt.contains() && !receipt.record());
        assert_eq!(fs::read(victim).unwrap(), [0x41; 32]);
    }

    #[test]
    fn pins_the_private_directory_across_an_ancestor_replacement() {
        let root = tempfile::tempdir().unwrap();
        let metadata = root.path().join("libsample.rmeta");
        fs::write(&metadata, b"native").unwrap();
        let original = Entry::new(root.path(), &metadata, "package", b"unit", b"compiler").unwrap();
        let directory = root.path().join(super::DIRECTORY);
        let moved = root.path().join("moved");
        let unrelated = root.path().join("unrelated");
        fs::rename(&directory, &moved).unwrap();
        fs::create_dir(&unrelated).unwrap();
        symlink(&unrelated, &directory).unwrap();
        assert!(original.record());
        assert!(moved.join(&original.slot).is_file());
        assert!(!unrelated.join(&original.slot).exists());
        assert!(Entry::new(root.path(), &metadata, "package", b"unit", b"compiler").is_none());
    }

    #[test]
    fn a_read_only_home_can_use_an_existing_proof() {
        let root = tempfile::tempdir().unwrap();
        let home = root.path().join("home");
        fs::create_dir(&home).unwrap();
        let metadata = root.path().join("libsample.rmeta");
        fs::write(&metadata, b"product").unwrap();
        // A privileged test process can bypass directory write permissions.
        if unsafe { libc::geteuid() } == 0 {
            return;
        }
        fs::set_permissions(&home, fs::Permissions::from_mode(0o500)).unwrap();
        assert!(Entry::new(&home, &metadata, "package", b"unit", b"compiler").is_none());
        fs::set_permissions(&home, fs::Permissions::from_mode(0o700)).unwrap();
        let original = Entry::new(&home, &metadata, "package", b"unit", b"compiler").unwrap();
        assert!(original.record());
        let private = home.join(super::DIRECTORY);
        fs::set_permissions(&private, fs::Permissions::from_mode(0o500)).unwrap();
        fs::set_permissions(
            private.join(&original.slot),
            fs::Permissions::from_mode(0o400),
        )
        .unwrap();
        let hit = Entry::new(&home, &metadata, "package", b"unit", b"compiler").unwrap();
        assert!(hit.contains());
        assert!(hit.record());
        let miss = Entry::new(&home, &metadata, "package", b"other unit", b"compiler").unwrap();
        assert!(!miss.contains() && !miss.record());
        fs::set_permissions(&private, fs::Permissions::from_mode(0o700)).unwrap();
    }

    #[test]
    fn linked_or_oversized_native_metadata_is_ineligible() {
        let root = tempfile::tempdir().unwrap();
        let metadata = root.path().join("libsample.rmeta");
        fs::write(&metadata, b"native").unwrap();
        let linked = root.path().join("linked.rmeta");
        symlink(&metadata, &linked).unwrap();
        assert!(Entry::new(root.path(), &linked, "package", b"unit", b"compiler").is_none());
        fs::File::options()
            .write(true)
            .open(&metadata)
            .unwrap()
            .set_len(128 * 1024 * 1024 + 1)
            .unwrap();
        assert!(Entry::new(root.path(), &metadata, "package", b"unit", b"compiler").is_none());
    }

    #[test]
    fn concurrent_first_writers_can_share_the_private_slot() {
        let root = tempfile::tempdir().unwrap();
        let metadata = root.path().join("libsample.rmeta");
        fs::write(&metadata, b"native").unwrap();
        let start = Arc::new(Barrier::new(8));
        thread::scope(|scope| {
            for _ in 0..8 {
                let start = start.clone();
                let root = root.path();
                let metadata = &metadata;
                scope.spawn(move || {
                    start.wait();
                    // A racing first create can fall back to the ordinary check.
                    // After all writers finish, their shared proof must be readable.
                    Entry::new(root, metadata, "package", b"unit", b"compiler")
                        .unwrap()
                        .record()
                });
            }
        });
        let submitted =
            Entry::new(root.path(), &metadata, "package", b"unit", b"compiler").unwrap();
        assert!(submitted.contains());
        let mut other = Entry::new(
            root.path(),
            &metadata,
            "package",
            b"other unit",
            b"compiler",
        )
        .unwrap();
        other.slot = submitted.slot;
        assert!(!other.contains());
    }
}
