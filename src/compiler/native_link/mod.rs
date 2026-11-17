//! A successful native link can be reused only after the platform resolver has
//! accounted for the inputs of the real linker. An incomplete plan is a miss.
mod apple;
mod generation;
mod namespace;
mod relay;
pub(super) use relay::run_if_driver;

use std::collections::{BTreeMap, BTreeSet};
use std::ffi::OsString;
use std::fs::{self, File, Metadata, OpenOptions};
use std::io::{self, Read, Write};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};

use blake3::{Hash, Hasher};

#[derive(Default)]
struct Inputs {
    /// Platform, effective environment, and normalized driver and linker arguments.
    action: Vec<OsString>,
    /// Include lexical names even when two paths currently resolve to the same inode.
    files: BTreeSet<PathBuf>,
    directories: BTreeSet<PathBuf>,
    missing: BTreeSet<PathBuf>,
    /// Only compiler-owned files whose pathname and mtime cannot appear in the output.
    transient: BTreeMap<OsString, PathBuf>,
}

fn field(hasher: &mut Hasher, bytes: &[u8]) {
    hasher.update(&(bytes.len() as u64).to_le_bytes());
    hasher.update(bytes);
}

fn invalid(reason: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, reason)
}

fn stamp(meta: &Metadata) -> (u64, u64, u64, u32, i64, i64, i64, i64) {
    (
        meta.dev(),
        meta.ino(),
        meta.len(),
        meta.mode(),
        meta.mtime(),
        meta.mtime_nsec(),
        meta.ctime(),
        meta.ctime_nsec(),
    )
}

fn missing(err: &io::Error) -> bool {
    matches!(
        err.kind(),
        io::ErrorKind::NotFound | io::ErrorKind::NotADirectory
    )
}

fn hash_file(path: &Path, no_follow: bool) -> io::Result<(Hash, Metadata)> {
    let flags = libc::O_NONBLOCK | if no_follow { libc::O_NOFOLLOW } else { 0 };
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(flags)
        .open(path)?;
    let before = file.metadata()?;
    if !before.is_file() {
        return Err(invalid("expected a regular file"));
    }
    if !no_follow
        && let Some(version) = generation::data_version(&file, &before)
        && stamp(&fs::metadata(path)?) == stamp(&before)
    {
        return Ok((version, before));
    }
    let mut hash = Hasher::new();
    if hash.update_reader(&mut file)?.count() != before.len()
        || stamp(&file.metadata()?) != stamp(&before)
        || stamp(&fs::metadata(path)?) != stamp(&before)
    {
        return Err(invalid("file changed during read"));
    }
    Ok((hash.finalize(), before))
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct InputSnapshot {
    action: Hash,
    archive_generations: Hash,
}

impl Inputs {
    #[cfg(test)]
    fn digest(&self) -> io::Result<Hash> {
        Ok(self.snapshot()?.action)
    }

    /// Platform-specific code first supplies a closed set of potential inputs,
    /// including failed lookups. Validate it before and after a successful link.
    fn snapshot(&self) -> io::Result<InputSnapshot> {
        let mut h = Hasher::new_derive_key("Ohm native link inputs v5");
        // A fresh link creates the executable with the invoking process's umask.
        h.update(&crate::util::get_umask().to_le_bytes());
        let mut archives = Hasher::new_derive_key("Ohm open archive generations v1");
        for arg in &self.action {
            h.update(b"A");
            field(&mut h, arg.as_encoded_bytes());
        }
        for p in &self.files {
            let target = p.canonicalize()?;
            // Apple ld reads debug-map dates from the archive member headers.
            // Cargo can replace or touch the outer rlib without changing a member.
            let archive_contents = p.extension().is_some_and(|s| s == "rlib");
            let (contents, meta) = hash_file(p, archive_contents)?;
            if p.canonicalize()? != target {
                return Err(invalid("file was redirected"));
            }
            h.update(b"F");
            field(&mut h, p.as_os_str().as_encoded_bytes());
            field(&mut h, target.as_os_str().as_encoded_bytes());
            h.update(&meta.mode().to_le_bytes());
            // A real link must see the same generations before and after it runs,
            // even for archives whose identical contents allow a later build to skip it.
            let stamps = if archive_contents {
                &mut archives
            } else {
                &mut h
            };
            stamps.update(&meta.dev().to_le_bytes());
            stamps.update(&meta.ino().to_le_bytes());
            stamps.update(&meta.ctime().to_le_bytes());
            stamps.update(&meta.ctime_nsec().to_le_bytes());
            stamps.update(&meta.mtime().to_le_bytes());
            stamps.update(&meta.mtime_nsec().to_le_bytes());
            h.update(contents.as_bytes());
        }
        for p in &self.directories {
            if !p.is_dir() {
                return Err(invalid("missing search directory"));
            }
            h.update(b"D");
            field(&mut h, p.as_os_str().as_encoded_bytes());
            field(&mut h, p.canonicalize()?.as_os_str().as_encoded_bytes());
        }
        for p in &self.missing {
            match fs::metadata(p) {
                Err(err) if missing(&err) => {}
                Err(err) => return Err(err),
                Ok(_) => return Err(invalid("previously missing input exists")),
            }
            h.update(b"M");
            field(&mut h, p.as_os_str().as_encoded_bytes());
        }
        for (role, p) in &self.transient {
            h.update(b"T");
            field(&mut h, role.as_encoded_bytes());
            h.update(hash_file(p, true)?.0.as_bytes());
        }
        Ok(InputSnapshot {
            action: h.finalize(),
            archive_generations: archives.finalize(),
        })
    }
}

/// One bounded entry per executable in its private retained-link directory.
/// Cargo can unlink the executable before invoking rustc; keep the last good
/// inode available without copying the executable's bytes.
struct Entry {
    directory: PathBuf,
    _lock: File,
}

const MAX_STDERR: usize = 64 * 1024;

impl Entry {
    fn open(directory: &Path) -> io::Result<Self> {
        match fs::create_dir(directory) {
            Ok(()) => {}
            Err(e) if e.kind() == io::ErrorKind::AlreadyExists => {}
            Err(e) => return Err(e),
        }
        if !fs::symlink_metadata(directory)?.is_dir() {
            return Err(invalid("indirect cache directory"));
        }
        let lock = OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(directory.join("lock"))?;
        if !lock.metadata()?.is_file() {
            return Err(invalid("invalid cache lock"));
        }
        lock.lock()?;
        Ok(Self {
            directory: directory.to_owned(),
            _lock: lock,
        })
    }

    /// Remove the authorization record before a real link or fallback.
    fn invalidate(&self) -> io::Result<()> {
        match fs::remove_file(self.directory.join("seal")) {
            Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
            other => other,
        }
    }

    fn seal(action: Hash, out: &Path, product: Hash, meta: &Metadata, stderr: &[u8]) -> Hash {
        let mut h = Hasher::new_derive_key("Ohm native link result v2");
        field(&mut h, out.as_os_str().as_encoded_bytes());
        h.update(action.as_bytes());
        h.update(product.as_bytes());
        h.update(&meta.mode().to_le_bytes());
        field(&mut h, stderr);
        h.finalize()
    }

    /// Commit only after the platform reconciles its real successful linker
    /// report and the pre-link and post-link input digests agree.
    fn publish(&self, action: Hash, out: &Path, stderr: &[u8]) -> io::Result<()> {
        self.invalidate()?;
        if stderr.len() > MAX_STDERR {
            return Err(invalid("too much linker output"));
        }
        let published = self.directory.join("product");
        let staging = tempfile::tempdir_in(&self.directory)?;
        let product = staging.path().join("product");
        fs::hard_link(out, &product)?;
        let (digest, meta) = hash_file(&product, true)?;
        if stamp(&fs::symlink_metadata(out)?) != stamp(&meta) {
            return Err(invalid("native output changed while recording it"));
        }
        fs::rename(&product, &published)?;
        let mut seal = tempfile::NamedTempFile::new_in(&self.directory)?;
        seal.write_all(Self::seal(action, out, digest, &meta, stderr).as_bytes())?;
        seal.write_all(stderr)?;
        seal.persist(self.directory.join("seal"))?;
        Ok(())
    }

    fn reuse(&self, action: Hash, out: &Path) -> io::Result<Option<Vec<u8>>> {
        let seal = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(self.directory.join("seal"))?;
        let meta = seal.metadata()?;
        if !meta.is_file() || !(32..=32 + MAX_STDERR as u64).contains(&meta.len()) {
            return Ok(None);
        }
        let mut record = Vec::with_capacity(meta.len() as usize);
        seal.take(meta.len() + 1).read_to_end(&mut record)?;
        if record.len() as u64 != meta.len() {
            return Ok(None);
        }
        let (stored, stderr) = record.split_at(32);
        let product = self.directory.join("product");
        let (digest, meta) = hash_file(&product, true)?;
        if Self::seal(action, out, digest, &meta, stderr).as_bytes() != stored {
            return Ok(None);
        }
        match fs::symlink_metadata(out) {
            Ok(existing)
                if existing.is_file()
                    && existing.dev() == meta.dev()
                    && existing.ino() == meta.ino() => {}
            Ok(_) => return Ok(None),
            Err(e) if e.kind() == io::ErrorKind::NotFound => fs::hard_link(&product, out)?,
            Err(e) => return Err(e),
        }
        Ok(Some(stderr.to_vec()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs::FileTimes;
    use std::os::unix::fs::symlink;

    #[test]
    fn archive_key_survives_an_identical_replacement() -> io::Result<()> {
        let dir = tempfile::tempdir()?;
        let archive = dir.path().join("dep.rlib");
        let replacement = dir.path().join("replacement");
        let mut inputs = Inputs::default();
        inputs.files.insert(archive.clone());
        fs::write(&archive, b"first member")?;
        let before = inputs.snapshot()?;
        fs::write(&replacement, b"first member")?;
        fs::rename(&replacement, &archive)?;
        let after = inputs.snapshot()?;
        assert_eq!(before.action, after.action);
        assert_ne!(before.archive_generations, after.archive_generations);
        fs::write(&archive, b"other member")?;
        assert_ne!(before.action, inputs.digest()?);
        Ok(())
    }

    #[test]
    fn inputs_track_changes_outside_cargo() -> io::Result<()> {
        let dir = tempfile::tempdir()?;
        let root = dir.path();
        let first = root.join("first");
        let second = root.join("second");
        let selected = root.join("selected");
        let shadow = root.join("shadow");
        fs::write(&first, b"17")?;
        fs::write(&second, b"17")?;
        symlink(&first, &selected)?;
        let mut inputs = Inputs::default();
        inputs.files.insert(selected.clone());
        inputs.missing.insert(shadow.clone());
        let cold = inputs.digest()?;
        let time = first.metadata()?.modified()?;
        fs::write(&first, b"29")?;
        File::options()
            .write(true)
            .open(&first)?
            .set_times(FileTimes::new().set_modified(time))?;
        assert_ne!(cold, inputs.digest()?);
        fs::remove_file(&selected)?;
        symlink(&second, &selected)?;
        assert_ne!(cold, inputs.digest()?);
        fs::write(shadow, b"17")?;
        assert!(inputs.digest().is_err());
        Ok(())
    }

    #[test]
    fn only_restore_the_completed_output() -> io::Result<()> {
        let dir = tempfile::tempdir()?;
        let entry = Entry::open(&dir.path().join("cache"))?;
        let output = dir.path().join("app");
        fs::write(&output, b"first executable")?;
        let key = blake3::hash(b"first action");
        let diagnostic = b"validated linker warning\n";
        entry.publish(key, &output, diagnostic)?;
        assert_eq!(
            entry.reuse(key, &output)?.as_deref(),
            Some(diagnostic.as_slice())
        );
        let seal = entry.directory.join("seal");
        let mut damaged = fs::read(&seal)?;
        *damaged.last_mut().unwrap() ^= 1;
        fs::write(&seal, damaged)?;
        assert!(entry.reuse(key, &output)?.is_none());
        entry.publish(key, &output, diagnostic)?;
        fs::remove_file(&output)?;
        assert!(
            entry
                .reuse(blake3::hash(b"other action"), &output)?
                .is_none()
        );
        assert_eq!(
            entry.reuse(key, &output)?.as_deref(),
            Some(diagnostic.as_slice())
        );
        assert_eq!(fs::read(&output)?, b"first executable");
        fs::write(&output, b"bad executable!!")?;
        assert!(entry.reuse(key, &output)?.is_none());
        entry.invalidate()?;
        fs::remove_file(&output)?;
        assert!(entry.reuse(key, &output).is_err());
        assert!(!output.exists());
        Ok(())
    }
}
