use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::Write as _;
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

use cargo_util::paths;
use cargo_util_schemas::manifest::{InheritableDependency, TomlDependency, TomlManifest};
use serde::{Deserialize, Serialize};
use serde_json::value::RawValue;

use crate::core::SourceId;
use crate::util::GlobalContext;
use crate::util::errors::CargoResult;

thread_local! {
    static ACTIVE_CACHE: RefCell<Option<ActiveCache>> = const { RefCell::new(None) };
}

/// The parsed forms of an immutable registry manifest, ready for package construction.
pub(super) struct CachedManifest {
    pub(super) original_toml: TomlManifest,
    pub(super) normalized_toml: TomlManifest,
    pub(super) warnings: Vec<String>,
    pub(super) errors: Vec<String>,
}

struct ActiveCache {
    path: PathBuf,
    contents: CacheContents,
    dirty_entries: BTreeSet<String>,
}

#[derive(Deserialize, Serialize)]
struct CacheContents {
    schema_version: u32,
    cargo_version: String,
    cargo_commit_hash: String,
    nightly_features_allowed: bool,
    unstable_flags: String,
    entries: BTreeMap<String, CacheEntry>,
}

#[derive(Deserialize, Serialize)]
struct CacheEntry {
    fingerprint: ManifestFingerprint,
    original_toml: Box<RawValue>,
    normalized_toml: Box<RawValue>,
    // TomlManifest intentionally skips this diagnostic bookkeeping when serialized.
    original_unused_keys: BTreeSet<String>,
    normalized_unused_keys: BTreeSet<String>,
    warnings: Vec<String>,
    errors: Vec<String>,
}

#[derive(Deserialize, Eq, PartialEq, Serialize)]
struct ManifestFingerprint {
    len: u64,
    modified_seconds: u64,
    modified_nanos: u32,
}

impl CacheContents {
    fn empty(gctx: &GlobalContext) -> Self {
        Self {
            schema_version: 3,
            cargo_version: crate::version().to_string(),
            cargo_commit_hash: option_env!("CARGO_COMMIT_HASH")
                .unwrap_or_default()
                .to_owned(),
            nightly_features_allowed: gctx.nightly_features_allowed,
            unstable_flags: format!("{:?}", gctx.cli_unstable()),
            entries: BTreeMap::new(),
        }
    }

    fn is_compatible(&self, gctx: &GlobalContext) -> bool {
        self.schema_version == 3
            && self.cargo_version == crate::version().to_string()
            && self.cargo_commit_hash == option_env!("CARGO_COMMIT_HASH").unwrap_or_default()
            && self.nightly_features_allowed == gctx.nightly_features_allowed
            && self.unstable_flags == format!("{:?}", gctx.cli_unstable())
    }

    fn has_same_configuration(&self, other: &Self) -> bool {
        self.schema_version == other.schema_version
            && self.cargo_version == other.cargo_version
            && self.cargo_commit_hash == other.cargo_commit_hash
            && self.nightly_features_allowed == other.nightly_features_allowed
            && self.unstable_flags == other.unstable_flags
    }
}

/// Loads the invocation-wide cache once, treating unreadable or outdated entries as misses.
pub(super) fn start(cache_path: PathBuf, gctx: &GlobalContext) -> CargoResult<()> {
    let contents = match read_regular_file(&cache_path) {
        Ok(bytes) => match serde_json::from_slice::<CacheContents>(&bytes) {
            Ok(contents) if contents.is_compatible(gctx) => contents,
            Ok(_) => {
                tracing::debug!(path = %cache_path.display(), "registry manifest cache is outdated");
                CacheContents::empty(gctx)
            }
            Err(error) => {
                tracing::debug!(path = %cache_path.display(), %error, "ignoring invalid registry manifest cache");
                CacheContents::empty(gctx)
            }
        },
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => CacheContents::empty(gctx),
        Err(error) => {
            tracing::debug!(path = %cache_path.display(), %error, "registry manifest cache could not be read");
            CacheContents::empty(gctx)
        }
    };

    ACTIVE_CACHE.with(|active| {
        *active.borrow_mut() = Some(ActiveCache {
            path: cache_path,
            contents,
            dirty_entries: BTreeSet::new(),
        });
    });

    Ok(())
}

/// Saves newly discovered manifests together, avoiding one filesystem write per package.
pub(super) fn finish() -> CargoResult<()> {
    let active = ACTIVE_CACHE.with(|active| active.borrow_mut().take());
    let Some(active) = active else {
        return Ok(());
    };
    if active.dirty_entries.is_empty() {
        return Ok(());
    }

    let cache_path = active.path;
    let dirty_entries = active.dirty_entries;
    let mut contents = active.contents;
    let mut write = || -> CargoResult<()> {
        if let Some(parent) = cache_path.parent() {
            paths::create_dir_all(parent)?;
        }

        match fs::symlink_metadata(&cache_path) {
            Ok(metadata) if !metadata.file_type().is_file() => {
                anyhow::bail!(
                    "refusing to replace non-regular registry manifest cache `{}`",
                    cache_path.display()
                );
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error.into()),
        }

        // Another Cargo may have populated this workspace's cache between the
        // read and write locks. Keep its entries instead of dropping them.
        if let Ok(bytes) = read_regular_file(&cache_path)
            && let Ok(mut previous) = serde_json::from_slice::<CacheContents>(&bytes)
            && previous.has_same_configuration(&contents)
        {
            for key in &dirty_entries {
                if let Some(entry) = contents.entries.remove(key) {
                    previous.entries.insert(key.clone(), entry);
                }
            }
            contents = previous;
        }

        let parent = cache_path
            .parent()
            .expect("registry manifest cache has a parent directory");
        let mut temporary = tempfile::Builder::new()
            .prefix(".registry-manifest-cache-")
            .tempfile_in(parent)?;
        serde_json::to_writer(temporary.as_file_mut(), &contents)?;
        temporary.as_file_mut().flush()?;
        // `persist` renames over the directory entry itself, unlike
        // `paths::write_atomic`, which intentionally follows leaf symlinks.
        temporary
            .persist(&cache_path)
            .map_err(|error| error.error)?;
        Ok(())
    };

    if let Err(error) = write() {
        tracing::debug!(path = %cache_path.display(), %error, "registry manifest cache could not be saved");
    }

    Ok(())
}

fn read_regular_file(path: &Path) -> std::io::Result<Vec<u8>> {
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.file_type().is_file() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            format!(
                "registry manifest cache `{}` is not a regular file",
                path.display()
            ),
        ));
    }
    fs::read(path)
}

/// Returns whether registry manifest caching is enabled for this invocation.
pub(super) fn is_active() -> bool {
    ACTIVE_CACHE.with(|active| active.borrow().is_some())
}

/// Forgets unpublished entries when the package-cache lock cannot be reacquired.
pub(super) fn discard() {
    ACTIVE_CACHE.with(|active| active.borrow_mut().take());
}

/// Returns a parsed manifest only when its source and on-disk fingerprint still agree.
pub(super) fn get(
    path: &Path,
    source_id: SourceId,
    _gctx: &GlobalContext,
) -> Option<CachedManifest> {
    if !source_id.is_remote_registry() {
        return None;
    }

    ACTIVE_CACHE.with(|active| {
        let active = active.borrow();
        let active = active.as_ref()?;
        let fingerprint = manifest_fingerprint(path)?;
        let key = cache_key(path, source_id);
        let entry = active.contents.entries.get(&key)?;
        if entry.fingerprint != fingerprint {
            return None;
        }

        let mut original_toml: TomlManifest =
            serde_json::from_str(entry.original_toml.get()).ok()?;
        original_toml._unused_keys = entry.original_unused_keys.clone();
        let mut normalized_toml: TomlManifest =
            serde_json::from_str(entry.normalized_toml.get()).ok()?;
        normalized_toml._unused_keys = entry.normalized_unused_keys.clone();

        Some(CachedManifest {
            original_toml,
            normalized_toml,
            warnings: entry.warnings.clone(),
            errors: entry.errors.clone(),
        })
    })
}

/// Records only registry manifests whose nested diagnostic state survives serialization.
pub(super) fn insert(
    path: &Path,
    source_id: SourceId,
    _gctx: &GlobalContext,
    original_toml: &TomlManifest,
    normalized_toml: &TomlManifest,
    warnings: &[String],
    errors: &[String],
) {
    if !source_id.is_remote_registry() {
        return;
    }
    ACTIVE_CACHE.with(|active| {
        let mut active = active.borrow_mut();
        let Some(active) = active.as_mut() else {
            return;
        };
        if has_unserializable_diagnostic_state(original_toml)
            || has_unserializable_diagnostic_state(normalized_toml)
        {
            return;
        }
        let Some(fingerprint) = manifest_fingerprint(path) else {
            return;
        };
        let key = cache_key(path, source_id);
        let Some(cached_original_toml) = compact_toml(original_toml) else {
            return;
        };
        let Some(cached_normalized_toml) = compact_toml(normalized_toml) else {
            return;
        };

        active.contents.entries.insert(
            key.clone(),
            CacheEntry {
                fingerprint,
                original_toml: cached_original_toml,
                normalized_toml: cached_normalized_toml,
                original_unused_keys: original_toml._unused_keys.clone(),
                normalized_unused_keys: normalized_toml._unused_keys.clone(),
                warnings: warnings.to_vec(),
                errors: errors.to_vec(),
            },
        );
        active.dirty_entries.insert(key);
    });
}

fn compact_toml(manifest: &TomlManifest) -> Option<Box<RawValue>> {
    let json = serde_json::to_vec(manifest).ok()?;
    compact_json(&json)
}

/// Removes null-valued object fields without reordering serialized TOML metadata.
fn compact_json(json: &[u8]) -> Option<Box<RawValue>> {
    let mut compactor = JsonCompactor {
        input: json,
        offset: 0,
        output: Vec::with_capacity(json.len()),
    };
    compactor.write_value()?;
    compactor.skip_whitespace();
    if compactor.offset != compactor.input.len() {
        return None;
    }
    RawValue::from_string(String::from_utf8(compactor.output).ok()?).ok()
}

struct JsonCompactor<'a> {
    input: &'a [u8],
    offset: usize,
    output: Vec<u8>,
}

impl JsonCompactor<'_> {
    fn write_value(&mut self) -> Option<()> {
        self.skip_whitespace();
        match *self.input.get(self.offset)? {
            b'{' => self.write_object(),
            b'[' => self.write_array(),
            b'"' => {
                let start = self.offset;
                self.skip_string()?;
                self.output
                    .extend_from_slice(&self.input[start..self.offset]);
                Some(())
            }
            b't' => self.write_literal(b"true"),
            b'f' => self.write_literal(b"false"),
            b'n' => self.write_literal(b"null"),
            b'-' | b'0'..=b'9' => {
                let start = self.offset;
                while matches!(
                    self.input.get(self.offset),
                    Some(b'-' | b'+' | b'.' | b'e' | b'E' | b'0'..=b'9')
                ) {
                    self.offset += 1;
                }
                self.output
                    .extend_from_slice(&self.input[start..self.offset]);
                Some(())
            }
            _ => None,
        }
    }

    fn write_object(&mut self) -> Option<()> {
        self.offset += 1;
        self.output.push(b'{');
        self.skip_whitespace();
        if self.consume(b'}') {
            self.output.push(b'}');
            return Some(());
        }

        let mut wrote_field = false;
        loop {
            self.skip_whitespace();
            let key_start = self.offset;
            self.skip_string()?;
            let key_end = self.offset;
            self.skip_whitespace();
            if !self.consume(b':') {
                return None;
            }
            self.skip_whitespace();

            if self.input.get(self.offset..)?.starts_with(b"null") {
                self.offset += 4;
            } else {
                if wrote_field {
                    self.output.push(b',');
                }
                self.output
                    .extend_from_slice(&self.input[key_start..key_end]);
                self.output.push(b':');
                self.write_value()?;
                wrote_field = true;
            }

            self.skip_whitespace();
            if self.consume(b'}') {
                self.output.push(b'}');
                return Some(());
            }
            if !self.consume(b',') {
                return None;
            }
        }
    }

    fn write_array(&mut self) -> Option<()> {
        self.offset += 1;
        self.output.push(b'[');
        self.skip_whitespace();
        if self.consume(b']') {
            self.output.push(b']');
            return Some(());
        }

        loop {
            self.write_value()?;
            self.skip_whitespace();
            if self.consume(b']') {
                self.output.push(b']');
                return Some(());
            }
            if !self.consume(b',') {
                return None;
            }
            self.output.push(b',');
        }
    }

    fn skip_string(&mut self) -> Option<()> {
        if !self.consume(b'"') {
            return None;
        }
        loop {
            match *self.input.get(self.offset)? {
                b'"' => {
                    self.offset += 1;
                    return Some(());
                }
                b'\\' => {
                    self.offset += 1;
                    self.input.get(self.offset)?;
                    self.offset += 1;
                }
                0..=0x1f => return None,
                _ => self.offset += 1,
            }
        }
    }

    fn write_literal(&mut self, literal: &[u8]) -> Option<()> {
        let end = self.offset.checked_add(literal.len())?;
        if self.input.get(self.offset..end)? != literal {
            return None;
        }
        self.output.extend_from_slice(literal);
        self.offset = end;
        Some(())
    }

    fn consume(&mut self, expected: u8) -> bool {
        if self.input.get(self.offset) == Some(&expected) {
            self.offset += 1;
            true
        } else {
            false
        }
    }

    fn skip_whitespace(&mut self) {
        while matches!(
            self.input.get(self.offset),
            Some(b' ' | b'\n' | b'\r' | b'\t')
        ) {
            self.offset += 1;
        }
    }
}

fn cache_key(path: &Path, source_id: SourceId) -> String {
    format!("{source_id}\u{1f}{}", path.display())
}

fn manifest_fingerprint(path: &Path) -> Option<ManifestFingerprint> {
    let metadata = path.metadata().ok()?;
    let modified = metadata.modified().ok()?.duration_since(UNIX_EPOCH).ok()?;
    Some(ManifestFingerprint {
        len: metadata.len(),
        modified_seconds: modified.as_secs(),
        modified_nanos: modified.subsec_nanos(),
    })
}

fn has_unserializable_diagnostic_state(manifest: &TomlManifest) -> bool {
    let inherited = |dependency: &InheritableDependency| !dependency.unused_keys().is_empty();
    let direct = |dependency: &TomlDependency| !dependency.unused_keys().is_empty();

    manifest
        .dependencies
        .iter()
        .chain(manifest.dev_dependencies.iter())
        .chain(manifest.dev_dependencies2.iter())
        .chain(manifest.build_dependencies.iter())
        .chain(manifest.build_dependencies2.iter())
        .flat_map(|dependencies| dependencies.values())
        .any(inherited)
        || manifest
            .target
            .iter()
            .flat_map(|targets| targets.values())
            .flat_map(|target| {
                target
                    .dependencies
                    .iter()
                    .chain(target.dev_dependencies.iter())
                    .chain(target.dev_dependencies2.iter())
                    .chain(target.build_dependencies.iter())
                    .chain(target.build_dependencies2.iter())
                    .flat_map(|dependencies| dependencies.values())
            })
            .any(inherited)
        || manifest
            .workspace
            .iter()
            .flat_map(|workspace| workspace.dependencies.iter())
            .flat_map(|dependencies| dependencies.values())
            .any(direct)
        || manifest
            .patch
            .iter()
            .flat_map(|patches| patches.values())
            .flat_map(|dependencies| dependencies.values())
            .any(direct)
        || manifest
            .replace
            .iter()
            .flat_map(|dependencies| dependencies.values())
            .any(direct)
        || manifest
            .package()
            .is_some_and(|package| package._invalid_cargo_features.is_some())
}

#[cfg(test)]
mod tests {
    use super::compact_json;

    #[test]
    fn compact_json_preserves_object_order_and_escaped_strings() {
        let json = br#"{"zebra":{"escaped":"say \"hi\" \\ \u263a","drop":null},"alpha":[null,{"gone":null,"k\"ey":"\u0041"}],"omega":null}"#;
        let compacted = compact_json(json).unwrap();

        assert_eq!(
            compacted.get(),
            r#"{"zebra":{"escaped":"say \"hi\" \\ \u263a"},"alpha":[null,{"k\"ey":"\u0041"}]}"#
        );
    }

    #[test]
    fn compact_json_handles_empty_containers_numbers_and_whitespace() {
        let json = br#" { "zebra": null, "alpha": [], "nested": { "gone": null }, "number": -1.25e+3, "truth": true, "falsehood": false } "#;
        let compacted = compact_json(json).unwrap();

        assert_eq!(
            compacted.get(),
            r#"{"alpha":[],"nested":{},"number":-1.25e+3,"truth":true,"falsehood":false}"#
        );
    }

    #[test]
    fn compact_json_rejects_invalid_json() {
        assert!(compact_json(br#"{"unfinished":null"#).is_none());
        assert!(compact_json(br#"{"invalid":"unterminated}"#).is_none());
        assert!(compact_json(br#"{"valid":null} trailing"#).is_none());
    }
}
