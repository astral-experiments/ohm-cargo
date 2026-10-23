//! A private cache of successfully parsed registry TOML, before Cargo validation.
//!
//! Cache generic values, not TomlManifest: its ordinary serializer drops unused
//! keys that diagnostics need. Typed deserialization and normalization still run.

use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::sync::LazyLock;

use serde::{Deserialize, Serialize};

// Bump when the codec or parsing mode changes. The lockfile binds the TOML
// parser version/checksum; Cargo's typed schema is deliberately not cached.
const MAGIC: &[u8] = b"cargo-registry-toml-v1\0";
const DIRECTORY: &str = ".registry-manifest-cache-v1";
const MAX_BYTES: u64 = 4 * 1024 * 1024;
// A tagged table adds three JSON nesting levels. Leave ample room beneath
// serde_json's default recursion limit so stored entries can be read back.
const MAX_DEPTH: usize = 32;
const DATETIME_FIELD: &str = "$__toml_private_datetime";
static PARSER: LazyLock<blake3::Hash> = LazyLock::new(|| {
    let mut hasher = blake3::Hasher::new();
    for bytes in [
        env!("CARGO_PKG_VERSION").as_bytes(),
        option_env!("CARGO_COMMIT_HASH").unwrap_or("").as_bytes(),
        include_bytes!("../../../Cargo.lock").as_slice(),
        include_bytes!("../../../Cargo.toml").as_slice(),
        include_bytes!("mod.rs").as_slice(),
        include_bytes!("registry_cache.rs").as_slice(),
    ] {
        hasher.update(&(bytes.len() as u64).to_le_bytes());
        hasher.update(bytes);
    }
    hasher.finalize()
});

pub(super) struct Cache<'a> {
    directory: PathBuf,
    path: PathBuf,
    key: blake3::Hash,
    contents: &'a str,
}

impl<'a> Cache<'a> {
    pub(super) fn new(home: &Path, contents: &'a str) -> Option<Self> {
        if contents.len() as u64 > MAX_BYTES {
            return None;
        }
        let home = home.canonicalize().ok()?;
        if !trusted_ancestors(&home) {
            return None;
        }
        let directory = home.join(DIRECTORY);
        let _ = fs::DirBuilder::new().mode(0o700).create(&directory);
        if !private_metadata(&fs::symlink_metadata(&directory).ok()?, true) {
            return None;
        }
        let mut hasher = blake3::Hasher::new();
        hasher.update(MAGIC);
        hasher.update(PARSER.as_bytes());
        hasher.update(contents.as_bytes());
        let key = hasher.finalize();
        let path = directory.join(key.to_hex().to_string());
        Some(Self {
            directory,
            path,
            key,
            contents,
        })
    }

    pub(super) fn load(&self) -> Option<toml::Value> {
        if !private_metadata(&fs::symlink_metadata(&self.directory).ok()?, true)
            || !private_metadata(&fs::symlink_metadata(&self.path).ok()?, false)
        {
            return None;
        }
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(&self.path)
            .ok()?;
        let metadata = file.metadata().ok()?;
        if !private_metadata(&metadata, false) || metadata.len() > MAX_BYTES {
            return None;
        }
        let mut bytes = Vec::new();
        file.take(MAX_BYTES + 1).read_to_end(&mut bytes).ok()?;
        if bytes.len() as u64 > MAX_BYTES {
            return None;
        }
        let bytes = bytes.strip_prefix(MAGIC)?;
        let bytes = bytes.strip_prefix(self.key.as_bytes().as_slice())?;
        let (checksum, payload) = bytes.split_at_checked(32)?;
        if checksum != blake3::hash(payload).as_bytes() {
            return None;
        }
        serde_json::from_slice::<Value>(payload).ok()?.into_toml()
    }

    // Best effort, and called only after the ordinary typed parser succeeded.
    pub(super) fn store(&self) {
        let _ = self.try_store();
    }

    fn try_store(&self) -> Option<()> {
        let value = toml::from_str::<toml::Value>(self.contents).ok()?;
        let payload = serde_json::to_vec(&Value::from_toml(value, 0)?).ok()?;
        if (MAGIC.len() + 64 + payload.len()) as u64 > MAX_BYTES {
            return None;
        }
        if !trusted_ancestors(&self.directory)
            || !private_metadata(&fs::symlink_metadata(&self.directory).ok()?, true)
        {
            return None;
        }
        match fs::symlink_metadata(&self.path) {
            Ok(metadata) if !private_metadata(&metadata, false) => return None,
            Err(error) if error.kind() != std::io::ErrorKind::NotFound => return None,
            _ => {}
        }
        // Unlike paths::write_atomic, persist replaces a destination symlink
        // rather than following it. Never change existing directory permissions.
        let mut temporary = tempfile::NamedTempFile::new_in(&self.directory).ok()?;
        temporary.write_all(MAGIC).ok()?;
        temporary.write_all(self.key.as_bytes()).ok()?;
        temporary
            .write_all(blake3::hash(&payload).as_bytes())
            .ok()?;
        temporary.write_all(&payload).ok()?;
        temporary.persist(&self.path).ok()?;
        Some(())
    }
}

fn private_metadata(metadata: &fs::Metadata, directory: bool) -> bool {
    // SAFETY: geteuid has no arguments or memory-safety requirements.
    metadata.uid() == unsafe { libc::geteuid() }
        && metadata.mode() & 0o077 == 0
        && if directory {
            metadata.is_dir()
        } else {
            metadata.is_file()
        }
}

fn trusted_ancestors(path: &Path) -> bool {
    // SAFETY: geteuid has no arguments or memory-safety requirements.
    let uid = unsafe { libc::geteuid() };
    path.ancestors().all(|path| {
        let Ok(metadata) = fs::symlink_metadata(path) else {
            return false;
        };
        metadata.is_dir()
            && (metadata.uid() == uid || metadata.uid() == 0)
            && (metadata.mode() & 0o022 == 0
                // A root-owned sticky temporary directory cannot have its
                // user-owned child replaced by another unprivileged user.
                || (metadata.uid() == 0 && metadata.mode() & 0o1000 != 0))
    })
}

/// Lossless representation of supported TOML values. JSON numbers cannot
/// represent NaN or infinities; preserve their bits and table insertion order.
#[derive(Debug, PartialEq, Serialize, Deserialize)]
enum Value {
    String(String),
    Integer(i64),
    Float(u64),
    Boolean(bool),
    Array(Vec<Value>),
    Table(Vec<(String, Value)>),
}

impl Value {
    fn from_toml(value: toml::Value, depth: usize) -> Option<Self> {
        if depth > MAX_DEPTH {
            return None;
        }
        Some(match value {
            toml::Value::String(value) => Self::String(value),
            toml::Value::Integer(value) => Self::Integer(value),
            toml::Value::Float(value) => Self::Float(value.to_bits()),
            toml::Value::Boolean(value) => Self::Boolean(value),
            // Value's datetime deserializer emits a string, whereas the TOML
            // parser uses a map protocol. Reparse these uncommon manifests.
            toml::Value::Datetime(_) => return None,
            toml::Value::Array(values) => Self::Array(
                values
                    .into_iter()
                    .map(|value| Self::from_toml(value, depth + 1))
                    .collect::<Option<_>>()?,
            ),
            toml::Value::Table(values) => Self::Table(
                values
                    .into_iter()
                    .map(|(key, value)| {
                        if key == DATETIME_FIELD {
                            return None;
                        }
                        Some((key, Self::from_toml(value, depth + 1)?))
                    })
                    .collect::<Option<_>>()?,
            ),
        })
    }

    fn into_toml(self) -> Option<toml::Value> {
        self.into_toml_at(0)
    }

    fn into_toml_at(self, depth: usize) -> Option<toml::Value> {
        if depth > MAX_DEPTH {
            return None;
        }
        Some(match self {
            Self::String(value) => toml::Value::String(value),
            Self::Integer(value) => toml::Value::Integer(value),
            Self::Float(value) => toml::Value::Float(f64::from_bits(value)),
            Self::Boolean(value) => toml::Value::Boolean(value),
            Self::Array(values) => toml::Value::Array(
                values
                    .into_iter()
                    .map(|value| value.into_toml_at(depth + 1))
                    .collect::<Option<_>>()?,
            ),
            Self::Table(values) => {
                let mut table = toml::map::Map::new();
                for (key, value) in values {
                    if key == DATETIME_FIELD {
                        return None;
                    }
                    if table.insert(key, value.into_toml_at(depth + 1)?).is_some() {
                        return None;
                    }
                }
                toml::Value::Table(table)
            }
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    use crate::GlobalContext;
    use crate::workspace::parser::{deserialize_toml, deserialize_without_document, read_manifest};
    use crate::workspace::{EitherManifest, GitReference, Manifest, SourceId};
    use cargo_util_terminal::Shell;

    const MANIFEST: &str = r#"
unknown-root = true
[package]
name = "cache-fixture"
version = "1.0.0"
edition = "2021"
unknown-package = "retained"
[package.metadata]
nan = nan
negative_nan = -nan
positive_infinity = inf
negative_infinity = -inf
negative_zero = -0.0
min_integer = -9223372036854775808
max_integer = 9223372036854775807
values = ["quoted\ntext", true, 2, { nested = ["unicode \u2764", -0.0] }]
[dependencies.detailed]
version = "1"
unknown-detailed = { keep = true }
[dependencies.inherited]
workspace = true
unknown-inherited = ["keep"]
[target.'cfg(unix)'.dependencies.targeted]
version = "1"
unknown-target = 42
[workspace.dependencies.workspace_dep]
version = "1"
unknown-workspace = "keep"
[patch.crates-io.patched]
version = "1"
unknown-patch = true
[replace."replaced:1.0.0"]
version = "1"
unknown-replace = false
"#;

    fn source() -> SourceId {
        SourceId::for_registry(&url::Url::parse("https://example.invalid/index").unwrap()).unwrap()
    }

    fn private_directory() -> tempfile::TempDir {
        tempfile::Builder::new()
            .permissions(fs::Permissions::from_mode(0o700))
            .tempdir()
            .unwrap()
    }

    fn context(home: &Path, enabled: bool) -> GlobalContext {
        let mut gctx = GlobalContext::new(Shell::new(), home.to_owned(), home.to_owned());
        gctx.nightly_features_allowed = true;
        gctx.configure(
            0,
            false,
            Some("never"),
            false,
            false,
            true,
            &None,
            &[format!(
                "ohm-defaults={}",
                if enabled { "yes" } else { "no" }
            )],
            &[],
        )
        .unwrap();
        gctx
    }

    fn fixture(contents: &str) -> (tempfile::TempDir, PathBuf, PathBuf) {
        let root = private_directory();
        let home = root.path().join("home");
        let package = root.path().join("package");
        fs::DirBuilder::new().mode(0o700).create(&home).unwrap();
        fs::create_dir_all(package.join("src")).unwrap();
        fs::write(package.join("src/lib.rs"), "").unwrap();
        let path = package.join("Cargo.toml");
        fs::write(&path, contents).unwrap();
        (root, home, path)
    }

    fn manifest(path: &Path, home: &Path, enabled: bool) -> Manifest {
        let EitherManifest::Real(manifest) =
            read_manifest(path, source(), &context(home, enabled)).unwrap()
        else {
            panic!("expected package");
        };
        manifest
    }

    #[test]
    fn lossless_values_and_all_unused_keys_match_direct_deserialization() {
        let home = private_directory();
        let cache = Cache::new(home.path(), MANIFEST).unwrap();
        assert!(cache.load().is_none());
        cache.store();
        let value = cache.load().expect("readable cached value");
        let original_value = toml::from_str::<toml::Value>(MANIFEST).unwrap();
        // The tagged comparison includes floating-point bits, including NaNs.
        assert_eq!(
            Value::from_toml(original_value, 0),
            Value::from_toml(value.clone(), 0)
        );
        let direct = deserialize_toml(toml::de::Deserializer::parse(MANIFEST).unwrap()).unwrap();
        let cached = deserialize_toml(value).unwrap();
        assert_eq!(format!("{direct:#?}"), format!("{cached:#?}"));
        assert_eq!(
            Value::from_toml(direct.package().unwrap().metadata.clone().unwrap(), 0),
            Value::from_toml(cached.package().unwrap().metadata.clone().unwrap(), 0)
        );
        let debug = format!("{cached:#?}");
        for key in [
            "unknown-root",
            "unknown-package",
            "unknown-detailed",
            "unknown-inherited",
            "unknown-target",
            "unknown-workspace",
            "unknown-patch",
            "unknown-replace",
        ] {
            assert!(debug.contains(key), "lost {key}");
        }
    }

    #[test]
    fn invalid_cached_types_fall_back_to_original_error_and_span() {
        let contents = "[package]\nname = []\nversion = \"1.0.0\"\n";
        let home = private_directory();
        // Simulate an incompatible cached value: store normally requires the
        // original typed deserializer to succeed before it can be called.
        let cache = Cache::new(home.path(), contents).unwrap();
        cache.store();
        assert!(cache.load().is_some());
        let direct =
            deserialize_toml(toml::de::Deserializer::parse(contents).unwrap()).unwrap_err();
        let cached = deserialize_without_document(contents, source(), &context(home.path(), true))
            .unwrap_err();
        assert_eq!(cached.message(), direct.message());
        assert_eq!(cached.span(), direct.span());
        assert_eq!(cached.to_string(), direct.to_string());
    }

    #[test]
    fn datetimes_and_literal_protocol_keys_use_original_parser() {
        for extra in [
            "instant = 1979-05-27T07:32:00.123456789-07:00",
            "date = 1979-05-27",
            "time = 07:32:00.999999999",
            "nested = [{ date = 1979-05-27 }]",
            r#""$\u005f_toml_private_datetime" = "1979-05-27""#,
        ] {
            let contents = format!("{MANIFEST}\n[package.metadata.extra]\n{extra}\n");
            let home = private_directory();
            let direct =
                deserialize_toml(toml::de::Deserializer::parse(&contents).unwrap()).unwrap();
            let cache = Cache::new(home.path(), &contents).unwrap();
            for _ in 0..2 {
                let cached =
                    deserialize_without_document(&contents, source(), &context(home.path(), true))
                        .unwrap();
                assert_eq!(format!("{direct:#?}"), format!("{cached:#?}"));
                assert!(!cache.path.exists());
            }
        }

        // A protocol key outside metadata must also be ineligible, whether it
        // appears first (generic parsing sees datetime) or later (a table key).
        for contents in [
            "[package]\n\"$\\u005f_toml_private_datetime\" = \"1979-05-27\"\nname=\"literal\"\nversion=\"1.0.0\"\n",
            "[package]\nname=\"literal\"\nversion=\"1.0.0\"\n\"$\\u005f_toml_private_datetime\" = \"1979-05-27\"\n",
        ] {
            let home = private_directory();
            let cache = Cache::new(home.path(), contents).unwrap();
            cache.store();
            assert!(!cache.path.exists());
            let direct =
                deserialize_toml(toml::de::Deserializer::parse(contents).unwrap()).unwrap();
            let cached =
                deserialize_without_document(contents, source(), &context(home.path(), true))
                    .unwrap();
            assert_eq!(format!("{direct:#?}"), format!("{cached:#?}"));
        }
    }

    #[test]
    fn malformed_incompatible_or_damaged_entries_are_misses() {
        let home = private_directory();
        let cache = Cache::new(home.path(), MANIFEST).unwrap();
        cache.store();
        let valid = fs::read(&cache.path).unwrap();
        for offset in [0, MAGIC.len(), MAGIC.len() + 32, valid.len() - 1] {
            let mut damaged = valid.clone();
            damaged[offset] ^= 1;
            fs::write(&cache.path, damaged).unwrap();
            assert!(cache.load().is_none());
        }
        fs::write(&cache.path, &valid[..MAGIC.len() + 5]).unwrap();
        assert!(cache.load().is_none());

        // Valid framing/checksum must not make invalid JSON or values usable.
        for payload in [
            b"not-json".as_slice(),
            br#"{"Datetime":"1979-05-27"}"#.as_slice(),
            br#"{"Table":[["$\u005f_toml_private_datetime",{"String":"1979-05-27"}]]}"#.as_slice(),
            br#"{"Table":[["duplicate",{"Integer":1}],["duplicate",{"Integer":2}]]}"#.as_slice(),
        ] {
            let mut bytes = MAGIC.to_vec();
            bytes.extend_from_slice(cache.key.as_bytes());
            bytes.extend_from_slice(blake3::hash(payload).as_bytes());
            bytes.extend_from_slice(payload);
            fs::write(&cache.path, bytes).unwrap();
            assert!(cache.load().is_none());
            let fallback =
                deserialize_without_document(MANIFEST, source(), &context(home.path(), true))
                    .unwrap();
            let direct =
                deserialize_toml(toml::de::Deserializer::parse(MANIFEST).unwrap()).unwrap();
            assert_eq!(format!("{fallback:#?}"), format!("{direct:#?}"));
        }
        cache.store();
        assert!(cache.load().is_some());
        fs::File::options()
            .write(true)
            .open(&cache.path)
            .unwrap()
            .set_len(MAX_BYTES + 1)
            .unwrap();
        assert!(cache.load().is_none());
    }

    #[test]
    fn private_ownership_permissions_and_symlinks_are_required() {
        let home = private_directory();
        let cache = Cache::new(home.path(), MANIFEST).unwrap();
        cache.store();
        fs::set_permissions(&cache.path, fs::Permissions::from_mode(0o644)).unwrap();
        assert!(cache.load().is_none());
        cache.store();
        assert_eq!(fs::metadata(&cache.path).unwrap().mode() & 0o777, 0o644);
        fs::remove_file(&cache.path).unwrap();
        let outside = home.path().join("untouched");
        fs::write(&outside, b"unchanged").unwrap();
        std::os::unix::fs::symlink(&outside, &cache.path).unwrap();
        assert!(cache.load().is_none());
        cache.store();
        assert_eq!(fs::read(&outside).unwrap(), b"unchanged");
        fs::remove_file(&cache.path).unwrap();
        fs::set_permissions(&cache.directory, fs::Permissions::from_mode(0o777)).unwrap();
        assert!(Cache::new(home.path(), MANIFEST).is_none());
        fs::set_permissions(&cache.directory, fs::Permissions::from_mode(0o700)).unwrap();
        fs::set_permissions(home.path(), fs::Permissions::from_mode(0o777)).unwrap();
        assert!(Cache::new(home.path(), MANIFEST).is_none());
    }

    #[test]
    fn supported_depth_round_trips_and_unsupported_depth_is_not_stored() {
        fn nested(depth: usize) -> toml::Value {
            let mut value = toml::Value::Integer(1);
            for _ in 0..depth {
                value = toml::Value::Table([("key".into(), value)].into_iter().collect());
            }
            value
        }
        let value = Value::from_toml(nested(MAX_DEPTH), 0).unwrap();
        let bytes = serde_json::to_vec(&value).unwrap();
        assert_eq!(serde_json::from_slice::<Value>(&bytes).unwrap(), value);
        assert!(Value::from_toml(nested(MAX_DEPTH + 1), 0).is_none());
        let supported = format!("{} = 1\n", vec!["key"; MAX_DEPTH].join("."));
        let contents = format!("{} = 1\n", vec!["key"; MAX_DEPTH + 2].join("."));
        let home = private_directory();
        let readable = Cache::new(home.path(), &supported).unwrap();
        readable.store();
        assert!(readable.load().is_some());
        let cache = Cache::new(home.path(), &contents).unwrap();
        cache.store();
        cache.store();
        assert!(!cache.path.exists());
    }

    #[test]
    fn concurrent_writers_publish_complete_entries() {
        let home = private_directory();
        std::thread::scope(|scope| {
            for _ in 0..8 {
                scope.spawn(|| {
                    let cache = Cache::new(home.path(), MANIFEST).unwrap();
                    for _ in 0..4 {
                        cache.store();
                        assert!(cache.load().is_some());
                    }
                });
            }
        });
        let cache = Cache::new(home.path(), MANIFEST).unwrap();
        assert_eq!(fs::read_dir(&cache.directory).unwrap().count(), 1);
    }

    #[test]
    fn source_contents_override_same_length_and_restored_mtime() {
        let contents = "[package]\nname='fixture'\nversion='1.0.0'\nedition='2021'\n[package.metadata]\nmarker='old'\n";
        let (_root, home, path) = fixture(contents);
        let original_time = fs::metadata(&path).unwrap().modified().unwrap();
        let cold = manifest(&path, &home, true);
        deserialize_toml(Cache::new(&home, contents).unwrap().load().unwrap()).unwrap();
        let hit = manifest(&path, &home, true);
        assert_eq!(
            format!("{:?}", cold.original_toml()),
            format!("{:?}", hit.original_toml())
        );
        let edited = contents.replace("'old'", "'new'");
        assert_eq!(contents.len(), edited.len());
        fs::write(&path, &edited).unwrap();
        fs::File::options()
            .write(true)
            .open(&path)
            .unwrap()
            .set_modified(original_time)
            .unwrap();
        assert_eq!(
            fs::metadata(&path).unwrap().modified().unwrap(),
            original_time
        );
        let changed = manifest(&path, &home, true);
        assert_eq!(
            changed
                .normalized_toml()
                .package()
                .unwrap()
                .metadata
                .as_ref()
                .unwrap()["marker"]
                .as_str(),
            Some("new")
        );
        let before = Cache::new(&home, contents).unwrap();
        let after = Cache::new(&home, &edited).unwrap();
        assert_ne!(before.path, after.path);
        assert!(before.load().is_some());
        assert!(after.load().is_some());
    }

    #[test]
    fn warnings_and_filesystem_normalization_match_cold_and_hit() {
        let contents = r#"
unknown-root = true
[package]
name = "fixture"
version = "1.0.0"
edition = "2021"
unknown-package = true
[dependencies.detailed]
version = "1"
unknown-detailed = true
[dependencies.inherited]
workspace = true
unknown-inherited = true
[workspace.dependencies.inherited]
version = "1"
unknown-workspace = true
"#;
        let (_root, home, path) = fixture(contents);
        let direct = manifest(&path, &home, false);
        assert!(!home.join(DIRECTORY).exists());
        let cold = manifest(&path, &home, true);
        deserialize_toml(Cache::new(&home, contents).unwrap().load().unwrap()).unwrap();
        let hit = manifest(&path, &home, true);
        let warnings = format!("{:?}", direct.warnings());
        assert_eq!(warnings, format!("{:?}", cold.warnings()));
        assert_eq!(warnings, format!("{:?}", hit.warnings()));
        for key in [
            "unknown-root",
            "unknown-package",
            "unknown-detailed",
            "unknown-inherited",
            "unknown-workspace",
        ] {
            assert!(
                warnings.contains(key),
                "missing warning for {key}: {warnings}"
            );
        }
        assert_eq!(hit.targets().len(), 1);
        let source = path.parent().unwrap().join("src");
        fs::create_dir(source.join("bin")).unwrap();
        fs::write(source.join("bin/new-target.rs"), "fn main() {}").unwrap();
        let changed = manifest(&path, &home, true);
        let uncached = manifest(&path, &home, false);
        assert_eq!(changed.targets().len(), 2);
        assert_eq!(
            format!("{:?}", changed.targets()),
            format!("{:?}", uncached.targets())
        );
        assert_eq!(
            format!("{:?}", changed.warnings()),
            format!("{:?}", uncached.warnings())
        );
    }

    #[test]
    fn feature_gates_remain_after_cached_parsing() {
        let contents = "cargo-features=['metabuild']\n[package]\nname='fixture'\nversion='1.0.0'\nedition='2021'\n";
        let (_root, home, path) = fixture(contents);
        manifest(&path, &home, true);
        assert!(Cache::new(&home, contents).unwrap().load().is_some());
        let error = |enabled| {
            let mut gctx = context(&home, enabled);
            gctx.nightly_features_allowed = false;
            format!(
                "{:#}",
                read_manifest(&path, source(), &gctx)
                    .err()
                    .expect("feature gate must reject the manifest")
            )
        };
        assert_eq!(error(true), error(false));
        assert!(error(true).contains("metabuild"));
    }

    #[test]
    fn only_enabled_remote_registry_sources_are_cached() {
        let home = private_directory();
        deserialize_without_document(MANIFEST, source(), &context(home.path(), false)).unwrap();
        assert!(!home.path().join(DIRECTORY).exists());
        for source in [
            SourceId::for_path(home.path()).unwrap(),
            SourceId::for_git(
                &url::Url::parse("https://example.invalid/repo").unwrap(),
                GitReference::DefaultBranch,
            )
            .unwrap(),
        ] {
            deserialize_without_document(MANIFEST, source, &context(home.path(), true)).unwrap();
            assert!(!home.path().join(DIRECTORY).exists());
        }
        for url in [
            "https://example.invalid/index",
            "sparse+https://example.invalid/index/",
        ] {
            let source = SourceId::for_registry(&url::Url::parse(url).unwrap()).unwrap();
            deserialize_without_document(MANIFEST, source, &context(home.path(), true)).unwrap();
            let cache = Cache::new(home.path(), MANIFEST).unwrap();
            assert!(cache.load().is_some());
            fs::remove_file(cache.path).unwrap();
        }
    }
}
