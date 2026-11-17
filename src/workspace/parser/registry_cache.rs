//! Read published registry manifests from a compact representation on subsequent runs.

use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::sync::LazyLock;

use cargo_util_schemas::manifest::TomlManifest;

use super::deserialize_toml;
use crate::util::GlobalContext;

const MAGIC: &[u8] = b"ohm-registry-json-v1\0";
const DIRECTORY: &str = ".ohm-registry-json-v1";
const MAX_SOURCE: usize = 256 * 1024;
const MAX_ENTRY: usize = 64 * 1024;
const MAX_DEPTH: usize = 32;

// The lockfile pins the TOML and JSON codecs that wrote the entry.
static PARSER: LazyLock<blake3::Hash> = LazyLock::new(|| {
    let mut hash = blake3::Hasher::new();
    hash.update(MAGIC);
    hash.update(include_bytes!("../../../Cargo.lock"));
    hash.update(env!("CARGO_PKG_VERSION").as_bytes());
    hash.update(option_env!("CARGO_COMMIT_HASH").unwrap_or("").as_bytes());
    hash.finalize()
});

pub(crate) fn directory(home: &Path) -> Option<PathBuf> {
    let home = home.canonicalize().ok()?;
    if !trusted_ancestors(&home) {
        return None;
    }
    let directory = home.join(DIRECTORY);
    let _ = fs::DirBuilder::new().mode(0o700).create(&directory);
    let meta = directory.symlink_metadata().ok()?;
    (meta.is_dir() && private(&meta)).then_some(directory)
}

fn private(meta: &fs::Metadata) -> bool {
    // SAFETY: geteuid has no arguments or memory-safety requirements.
    meta.uid() == unsafe { libc::geteuid() } && meta.mode() & 0o077 == 0
}

fn trusted_ancestors(dir: &Path) -> bool {
    // SAFETY: geteuid has no arguments or memory-safety requirements.
    let uid = unsafe { libc::geteuid() };
    dir.ancestors().all(|p| {
        let Ok(meta) = p.symlink_metadata() else {
            return false;
        };
        meta.is_dir()
            && (meta.uid() == uid || meta.uid() == 0)
            && (meta.mode() & 0o022 == 0 || (meta.uid() == 0 && meta.mode() & 0o1000 != 0))
    })
}

pub(super) struct Entry<'a> {
    directory: &'a Path,
    path: PathBuf,
    key: blake3::Hash,
}

impl<'a> Entry<'a> {
    pub(super) fn new(gctx: &'a GlobalContext, contents: &str) -> Option<Self> {
        if contents.len() > MAX_SOURCE {
            return None;
        }
        Some(Self::at(gctx.registry_manifest_cache()?, contents))
    }

    fn at(directory: &'a Path, contents: &str) -> Self {
        let key = blake3::keyed_hash(PARSER.as_bytes(), contents.as_bytes());
        // 4,096 slots bound committed records to 256 MiB. A collision is a miss.
        let slot = u16::from_be_bytes([key.as_bytes()[0], key.as_bytes()[1]]) >> 4;
        Self {
            directory,
            path: directory.join(format!("{slot:03x}")),
            key,
        }
    }

    pub(super) fn read(&self) -> Option<TomlManifest> {
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(&self.path)
            .ok()?;
        let meta = file.metadata().ok()?;
        if !meta.is_file() || !private(&meta) || meta.len() > MAX_ENTRY as u64 {
            return None;
        }
        let mut bytes = Vec::with_capacity(meta.len() as usize);
        file.take(meta.len() + 1).read_to_end(&mut bytes).ok()?;
        if bytes.len() as u64 != meta.len() {
            return None;
        }
        let body = bytes
            .strip_prefix(MAGIC)?
            .strip_prefix(self.key.as_bytes().as_slice())?;
        let (digest, payload) = body.split_at_checked(32)?;
        if digest != blake3::keyed_hash(self.key.as_bytes(), payload).as_bytes() {
            return None;
        }
        let mut de = serde_json::Deserializer::from_slice(payload);
        let manifest = deserialize_toml(&mut de).ok()?;
        de.end().ok()?;
        Some(manifest)
    }

    pub(super) fn store(&self, contents: &str) {
        let _ = self.try_store(contents);
    }

    fn try_store(&self, contents: &str) -> Option<()> {
        let value: toml::Value = toml::from_str(contents).ok()?;
        if !supported(&value, 0) {
            return None;
        }
        let payload = serde_json::to_vec(&value).ok()?;
        if MAGIC.len() + 64 + payload.len() > MAX_ENTRY {
            return None;
        }
        if !trusted_ancestors(self.directory) || !private(&self.directory.symlink_metadata().ok()?)
        {
            return None;
        }
        match self.path.symlink_metadata() {
            Ok(meta) if !meta.is_file() || !private(&meta) => return None,
            Err(e) if e.kind() != std::io::ErrorKind::NotFound => return None,
            _ => {}
        }
        let mut temporary = tempfile::NamedTempFile::new_in(self.directory).ok()?;
        temporary.write_all(MAGIC).ok()?;
        temporary.write_all(self.key.as_bytes()).ok()?;
        temporary
            .write_all(blake3::keyed_hash(self.key.as_bytes(), &payload).as_bytes())
            .ok()?;
        temporary.write_all(&payload).ok()?;
        temporary.persist(&self.path).ok()?;
        Some(())
    }
}

fn supported(value: &toml::Value, depth: usize) -> bool {
    if depth > MAX_DEPTH {
        return false;
    }
    match value {
        toml::Value::Float(_) | toml::Value::Datetime(_) => false,
        toml::Value::Array(items) => items.iter().all(|v| supported(v, depth + 1)),
        toml::Value::Table(items) => items
            .iter()
            .all(|(k, v)| k != "$__toml_private_datetime" && supported(v, depth + 1)),
        _ => true,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{PermissionsExt, symlink};

    const SOURCE: &str = r#"
[package]
name = "example"
version = "1.0.0"
unknown = "keep this warning"
[package.metadata]
signed = [-9223372036854775808, 9223372036854775807]
nested = [{ text = "a\tb", flag = true }]
[dependencies.other]
version = "1"
default-features = false
[lib]
path = "src/lib.rs"
"#;

    fn private_home() -> tempfile::TempDir {
        tempfile::Builder::new()
            .permissions(fs::Permissions::from_mode(0o700))
            .tempdir()
            .unwrap()
    }

    #[test]
    fn typed_fields_metadata_and_ignored_keys_round_trip() {
        let home = private_home();
        let dir = directory(home.path()).unwrap();
        let entry = Entry::at(&dir, SOURCE);
        let expected = deserialize_toml(toml::de::Deserializer::parse(SOURCE).unwrap()).unwrap();
        assert!(expected._unused_keys.contains("package.unknown"));
        assert!(entry.read().is_none());
        entry.store(SOURCE);
        assert_eq!(
            format!("{:?}", entry.read().unwrap()),
            format!("{expected:?}")
        );
    }

    #[test]
    fn collisions_corruption_and_invalid_payloads_are_misses() {
        let home = private_home();
        let dir = directory(home.path()).unwrap();
        let entry = Entry::at(&dir, SOURCE);
        entry.store(SOURCE);
        let bytes = fs::read(&entry.path).unwrap();
        let mut other = Entry::at(&dir, "[package]\nname = 'other'\nversion = '2'\n");
        other.path = entry.path.clone();
        assert!(other.read().is_none());
        for offset in [0, MAGIC.len(), MAGIC.len() + 32, bytes.len() - 1] {
            let mut corrupt = bytes.clone();
            corrupt[offset] ^= 1;
            fs::write(&entry.path, corrupt).unwrap();
            assert!(entry.read().is_none());
        }
        for payload in [b"{".as_slice(), b"{} null", br#"{"package":{"name":17}}"#] {
            let mut bad = bytes[..MAGIC.len() + 32].to_vec();
            bad.extend_from_slice(blake3::keyed_hash(entry.key.as_bytes(), payload).as_bytes());
            bad.extend_from_slice(payload);
            fs::write(&entry.path, bad).unwrap();
            assert!(entry.read().is_none());
        }
        fs::write(&entry.path, vec![0; MAX_ENTRY + 1]).unwrap();
        assert!(entry.read().is_none());
    }

    #[test]
    fn unsupported_toml_is_left_to_the_original_reader() {
        let home = private_home();
        let dir = directory(home.path()).unwrap();
        for field in [
            "x = nan",
            "x = -0.0",
            "x = 2026-10-25T00:00:00Z",
            "x = [{ y = 1.5 }]",
            "'$__toml_private_datetime' = '2000-01-01'",
        ] {
            let source = format!("[package]\nname='p'\nversion='1'\n[package.metadata]\n{field}\n");
            let entry = Entry::at(&dir, &source);
            entry.store(&source);
            assert!(!entry.path.exists(), "{field}");
        }
        assert!(!supported(&toml::Value::String("x".into()), MAX_DEPTH + 1));
    }

    #[test]
    fn cache_paths_must_be_private_regular_files() {
        let home = private_home();
        let dir = directory(home.path()).unwrap();
        let entry = Entry::at(&dir, SOURCE);
        entry.store(SOURCE);
        fs::set_permissions(&entry.path, fs::Permissions::from_mode(0o644)).unwrap();
        assert!(entry.read().is_none());
        let external = home.path().join("sentinel");
        fs::write(&external, b"untouched").unwrap();
        fs::remove_file(&entry.path).unwrap();
        symlink(&external, &entry.path).unwrap();
        entry.store(SOURCE);
        assert!(entry.read().is_none());
        assert_eq!(fs::read(&external).unwrap(), b"untouched");
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o755)).unwrap();
        assert!(directory(home.path()).is_none());
    }
}
