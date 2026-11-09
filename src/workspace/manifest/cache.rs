//! Reuse verified package manifests across compilation commands.
use super::*;
use crate::workspace::dependency::ManifestDependency;
use crate::workspace::summary::PackedIndexSummary;
use serde::{Deserialize, Serialize};
use std::cell::OnceCell;
use std::io::{Read, Write};
use std::sync::{Mutex, OnceLock};

const MAX_RECORD: usize = 256 * 1024;
const AUTH_FILE: &str = ".ohm-prepared-manifest-key-v1";
const AUTH_FORMAT: &[u8] = b"ohm-manifest-auth-v1\0";
const MAX_TOML_FORMS: usize = 1024 * 1024;

#[derive(Debug, Default)]
pub(crate) struct Cache {
    pub(crate) enabled: bool,
    pub(crate) settings: OnceLock<Option<(PathBuf, blake3::Hash, AuthKey)>>,
    pub(crate) roots: Mutex<HashMap<PathBuf, blake3::Hash>>,
    pub(crate) target: OnceLock<PathBuf>,
}

/// The target may be restored independently of this Cargo home. Only its local writer can
/// authenticate a validated record. Never expose the key through GlobalContext's Debug output.
#[derive(Clone, Copy)]
pub(crate) struct AuthKey([u8; 32]);

impl std::fmt::Debug for AuthKey {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("AuthKey")
    }
}

impl AuthKey {
    fn load(home: &Path, target: &Path) -> Option<Self> {
        let home = match home.canonicalize() {
            Ok(home) => home,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                // A first build of a dependency-free project can reach manifest loading
                // before Cargo's package cache has created its home.
                std::fs::create_dir_all(home).ok()?;
                home.canonicalize().ok()?
            }
            Err(_) => return None,
        };
        if home.starts_with(target.canonicalize().ok()?) {
            return None;
        }
        let path = home.join(AUTH_FILE);
        if let Err(error) = path.symlink_metadata() {
            if error.kind() != std::io::ErrorKind::NotFound {
                return None;
            }
            let mut key = [0; 32];
            std::fs::File::open("/dev/urandom")
                .ok()?
                .read_exact(&mut key)
                .ok()?;
            let mut temporary = tempfile::NamedTempFile::new_in(&home).ok()?;
            temporary.write_all(AUTH_FORMAT).ok()?;
            temporary.write_all(&key).ok()?;
            match temporary.persist_noclobber(&path) {
                Ok(_) => {}
                Err(error) if error.error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(_) => return None,
            }
        }
        let mut file = cargo_util::paths::open_regular(&path).ok()?;
        let metadata = file.metadata().ok()?;
        if !crate::workspace::parser::registry_cache::private(&metadata)
            || metadata.len() != (AUTH_FORMAT.len() + 32) as u64
        {
            return None;
        }
        let mut prefix = [0; AUTH_FORMAT.len()];
        file.read_exact(&mut prefix).ok()?;
        if prefix != AUTH_FORMAT {
            return None;
        }
        let mut key = [0; 32];
        file.read_exact(&mut key).ok()?;
        (key != [0; 32]).then_some(Self(key))
    }

    fn tag(&self, input: &blake3::Hash, payload: &[u8]) -> blake3::Hash {
        let mut hasher = blake3::Hasher::new_keyed(&self.0);
        hasher.update(input.as_bytes());
        hasher.update(payload);
        hasher.finalize()
    }
}

#[derive(Debug)]
pub(super) struct StoredToml {
    compressed_forms: Vec<u8>,
    pub(super) member: bool,
    pub(super) document: OnceCell<Arc<toml::Spanned<toml::de::DeTable<'static>>>>,
    forms: OnceCell<(TomlManifest, TomlManifest)>,
}

#[derive(Serialize, Deserialize)]
struct Record<'a> {
    summary: PackedIndexSummary,
    dependencies: Vec<(usize, ManifestDependency)>,
    targets: Vec<TargetInner>,
    metadata: ManifestMetadata,
    exclude: Vec<String>,
    include: Vec<String>,
    custom: Vec<u8>,
    publish: Option<Vec<String>>,
    edition: Edition,
    rust_version: Option<RustVersion>,
    default_run: Option<String>,
    lint_flags: Vec<String>,
    #[serde(borrow)]
    normalized: &'a [u8],
    discovery: Option<u64>,
}

pub(crate) struct Entry {
    path: PathBuf,
    manifest: PathBuf,
    key: blake3::Hash,
    auth: AuthKey,
    dependency_source: SourceId,
    before: OnceCell<u64>,
}
impl Entry {
    pub(crate) fn new(
        path: &Path,
        source: SourceId,
        contents: &str,
        gctx: &GlobalContext,
    ) -> Option<Self> {
        if !gctx.manifests.enabled || contents.len() > MAX_RECORD {
            return None;
        }
        // A workspace member can inherit fields from its root. Use the exact root source seen
        // by this Workspace, and let Cargo resolve any intervening or explicitly chosen roots.
        let known_root = if source.is_path() {
            if path.file_name()? != "Cargo.toml" {
                return None;
            }
            let roots = gctx.manifests.roots.lock().unwrap();
            let (parent, salt) = path
                .parent()?
                .ancestors()
                .find_map(|p| roots.get(p).map(|s| (p, *s)))?;
            if parent == path.parent()?
                || path
                    .parent()?
                    .parent()?
                    .ancestors()
                    .take_while(|&p| p != parent)
                    .any(|p| p.join("Cargo.toml").exists())
            {
                return None;
            }
            Some((parent.to_owned(), salt))
        } else {
            if !source.is_remote_registry() || !contents.starts_with(MANIFEST_PREAMBLE.trim_end()) {
                return None;
            }
            None
        };
        let target = if let Some((root, _)) = &known_root {
            Some(root.join("target"))
        } else {
            gctx.manifests.target.get().cloned()
        };
        let (directory, salt, auth) = gctx
            .manifests
            .settings
            .get_or_init(|| {
                let target = if let Some(target) = gctx.target_dir().ok()? {
                    target.as_path_unlocked().to_owned()
                } else {
                    target?
                };
                let directory = target.join(".cargo-prepared-manifests-v1");
                std::fs::create_dir_all(&directory).ok()?;
                let auth = AuthKey::load(gctx.home().as_path_unlocked(), &target)?;
                let mut hasher = blake3::Hasher::new();
                hasher.update(env!("CARGO_PKG_VERSION").as_bytes());
                hasher.update(option_env!("CARGO_COMMIT_HASH")?.as_bytes());
                hasher.update(include_bytes!(concat!(
                    env!("CARGO_MANIFEST_DIR"),
                    "/Cargo.lock"
                )));
                hasher.update(format!("{:?}", gctx.cli_unstable()).as_bytes());
                hasher.update(&[gctx.nightly_features_allowed as u8]);
                let mut configuration = crate::util::StableHasher::new();
                crate::context::hash_config_table(gctx.values().ok()?, &mut configuration);
                hasher.update(&Hasher::finish(&configuration).to_le_bytes());
                let mut env = gctx
                    .env()
                    .filter(|(k, _)| k.starts_with("CARGO_") || k.starts_with("RUST"))
                    .collect::<Vec<_>>();
                env.sort_by_key(|(k, _)| *k);
                for (key, value) in env {
                    hasher.update(key.as_bytes());
                    hasher.update(&[0]);
                    hasher.update(value.as_bytes());
                    hasher.update(&[0]);
                }
                Some((directory, hasher.finalize(), auth))
            })
            .as_ref()?;
        // Keep one file per source path, replacing its older contents and settings.
        let slot = blake3::hash(path.as_os_str().as_encoded_bytes());
        let mut hasher = blake3::Hasher::new_keyed(salt.as_bytes());
        if let Some((root, root_salt)) = &known_root {
            hasher.update(root.as_os_str().as_encoded_bytes());
            hasher.update(root_salt.as_bytes());
            if let Some(readme) = crate::workspace::parser::default_readme_from_package_root(root) {
                hasher.update(readme.as_bytes());
            }
        }
        hasher.update(path.as_os_str().as_encoded_bytes());
        hasher.update(&[0]);
        hasher.update(source.as_url().to_string().as_bytes());
        hasher.update(&[0]);
        hasher.update(contents.as_bytes());
        let dependency_source = SourceId::crates_io(gctx).ok()?;
        hasher.update(dependency_source.as_url().to_string().as_bytes());
        let key = hasher.finalize();
        Some(Self {
            path: directory.join(&slot.to_hex().as_str()[..32]),
            manifest: path.to_owned(),
            key,
            auth: *auth,
            dependency_source,
            before: OnceCell::new(),
        })
    }
    /// Compare automatic discovery before and after parsing, so a concurrent target change
    /// cannot publish the old result under the new directory state.
    pub(crate) fn before_parse(&self) {
        self.before.get_or_init(|| {
            crate::workspace::parser::inferred_manifest_inputs(self.manifest.parent().unwrap())
        });
    }
    pub(crate) fn read(
        &self,
        contents: &str,
        source: SourceId,
        gctx: &GlobalContext,
    ) -> Option<Manifest> {
        // The record can contain compiler inputs, including lint flags and source paths.
        // Read only an owner-private regular file and verify the full key and payload.
        let file = cargo_util::paths::open_regular(&self.path).ok()?;
        let meta = file.metadata().ok()?;
        if meta.len() > MAX_RECORD as u64
            || !crate::workspace::parser::registry_cache::private(&meta)
        {
            return None;
        }
        let mut data = Vec::with_capacity(meta.len() as usize);
        file.take(meta.len() + 1).read_to_end(&mut data).ok()?;
        if data.len() as u64 != meta.len() {
            return None;
        }
        let payload = data.strip_prefix(self.key.as_bytes().as_slice())?;
        let (checksum, payload) = payload.split_at_checked(32)?;
        if checksum != self.auth.tag(&self.key, payload).as_bytes() {
            return None;
        }
        let record: Record<'_> = postcard::from_bytes(payload).ok()?;
        if let Some(discovery) = record.discovery
            && discovery
                != crate::workspace::parser::inferred_manifest_inputs(self.manifest.parent()?)
        {
            return None;
        }
        let mut summary = record
            .summary
            .unpack_with_dependency_source(source, self.dependency_source)?;
        if !record.dependencies.is_empty() {
            let mut changes = record.dependencies.into_iter().collect::<BTreeMap<_, _>>();
            let mut index = 0;
            summary = summary
                .try_map_dependencies(|dep| {
                    let local = changes.remove(&index);
                    index += 1;
                    match local {
                        Some(c) => c.restore(dep).context("invalid local dependency"),
                        None => Ok(dep),
                    }
                })
                .ok()?;
            if !changes.is_empty() {
                return None;
            }
        }
        tracing::debug!("reusing prepared manifest {}", self.manifest.display());
        let mut manifest = Manifest::new(
            Some(Rc::new(contents.to_owned())),
            None,
            None,
            Rc::new(TomlManifest::default()),
            summary,
            None,
            None,
            record
                .targets
                .into_iter()
                .map(|inner| Target {
                    inner: Arc::new(inner),
                })
                .collect(),
            record.exclude,
            record.include,
            record.metadata.links.clone(),
            record.metadata,
            serde_json::from_slice(&record.custom).ok()?,
            record.publish,
            Vec::new(),
            HashMap::default(),
            WorkspaceConfig::Member { root: None },
            Features::new(&[], gctx, &mut Vec::new(), source.is_path()).ok()?,
            record.edition,
            record.rust_version,
            None,
            record.default_run,
            None,
            None,
            record.lint_flags,
            None,
            false,
        );
        manifest.deferred_toml = Some(Rc::new(StoredToml {
            compressed_forms: record.normalized.to_vec(),
            member: source.is_path(),
            document: OnceCell::new(),
            forms: OnceCell::new(),
        }));
        Some(manifest)
    }
    pub(crate) fn store(&self, manifest: &Manifest) {
        let _ = self.try_store(manifest);
    }
    fn try_store(&self, manifest: &Manifest) -> Option<()> {
        if !matches!(manifest.cargo_lints(), (None, None)) {
            return None;
        }
        // Flags, replacements, and package diagnostics outside this representation take the
        // ordinary path. Adding all new fields to Manifest::new also requires updating replay.
        let original = manifest.original_toml()?;
        let package = original.package()?;
        let inferred = [
            package.autolib,
            package.autobins,
            package.autoexamples,
            package.autotests,
            package.autobenches,
        ]
        .into_iter()
        .any(|v| v != Some(false))
            || package.build.is_none()
            || package.readme.is_none();
        if original.cargo_features.is_some()
            || original.workspace.is_some()
            || original.profile.is_some()
            || original.patch.is_some()
            || original.replace.is_some()
            || manifest.default_kind.is_some()
            || manifest.forced_kind.is_some()
            || manifest.metabuild.is_some()
            || manifest.im_a_teapot.is_some()
            || manifest.hints.is_some()
            || manifest.resolve_behavior.is_some()
            || !manifest.replace.is_empty()
            || !manifest.patch.is_empty()
            || !manifest.warnings.warnings().is_empty()
            || !matches!(manifest.workspace, WorkspaceConfig::Member { root: None })
            || !original._unused_keys.is_empty()
        {
            return None;
        }
        let inferred = inferred
            || original.lib.as_ref().is_some_and(|t| t.path.is_none())
            || original.bin.iter().flatten().any(|t| t.path.is_none())
            || original.test.iter().flatten().any(|t| t.path.is_none())
            || original.example.iter().flatten().any(|t| t.path.is_none())
            || original.bench.iter().flatten().any(|t| t.path.is_none());
        let discovery = if inferred {
            if manifest.edition == Edition::Edition2015 {
                return None;
            }
            let layout =
                crate::workspace::parser::inferred_manifest_inputs(self.manifest.parent()?);
            if self.before.get() != Some(&layout) {
                return None;
            }
            Some(layout)
        } else {
            None
        };
        let mut dependencies = Vec::new();
        let summary = if manifest.package_id().source_id().is_path() {
            let mut ordinal = 0;
            let canonical = manifest
                .summary()
                .clone()
                .try_map_dependencies(|dep| {
                    let (dep, diff) = ManifestDependency::encode(dep, self.dependency_source)
                        .context("unsupported dependency source")?;
                    if let Some(diff) = diff {
                        dependencies.push((ordinal, diff));
                    }
                    ordinal += 1;
                    Ok(dep)
                })
                .ok()?;
            PackedIndexSummary::pack_with_dependency_source(&canonical, self.dependency_source)?
        } else {
            PackedIndexSummary::pack_with_dependency_source(
                manifest.summary(),
                self.dependency_source,
            )?
        };
        // Some manifest fields deliberately omit parser details during serialization. Only
        // preserve a pair when reading it back reproduces both typed forms, including those
        // details. Diagnostics and consumers that inspect TOML can then materialize it lazily.
        let forms = (original, manifest.normalized_toml());
        let encoded = serde_json::to_vec(&forms).ok()?;
        if encoded.len() > MAX_TOML_FORMS {
            return None;
        }
        let mut encoder =
            flate2::write::DeflateEncoder::new(Vec::new(), flate2::Compression::fast());
        encoder.write_all(&encoded).ok()?;
        let normalized = encoder.finish().ok()?;
        // Validate the compressed bytes that will be authenticated, using the reader's exact
        // decoder and limit. A copied target cannot sign replacement bytes using its header.
        let verified = StoredToml::decode(&normalized)?;
        if format!("{verified:?}") != format!("{forms:?}") {
            return None;
        }

        let custom = serde_json::to_vec(&manifest.custom_metadata).ok()?;
        if serde_json::from_slice::<Option<toml::Value>>(&custom).ok()? != manifest.custom_metadata
        {
            return None;
        }
        if manifest
            .targets
            .iter()
            .flat_map(Target::rustc_crate_types)
            .any(|kind| matches!(kind, CrateType::Other(_)))
            || manifest.links != manifest.metadata.links
        {
            return None;
        }
        let record = Record {
            summary,
            dependencies,
            targets: manifest
                .targets
                .iter()
                .map(|t| (*t.inner).clone())
                .collect(),
            metadata: manifest.metadata.clone(),
            exclude: manifest.exclude.clone(),
            include: manifest.include.clone(),
            custom,
            publish: manifest.publish.clone(),
            edition: manifest.edition,
            rust_version: manifest.rust_version.clone(),
            default_run: manifest.default_run.clone(),
            lint_flags: manifest.lint_rustflags.clone(),
            normalized: &normalized,
            discovery,
        };
        let data = postcard::to_allocvec(&record).ok()?;
        if data.len() + 64 > MAX_RECORD {
            return None;
        };
        match self.path.symlink_metadata() {
            Ok(meta)
                if !meta.is_file() || !crate::workspace::parser::registry_cache::private(&meta) =>
            {
                return None;
            }
            Err(error) if error.kind() != std::io::ErrorKind::NotFound => return None,
            _ => {}
        }
        let mut temporary = tempfile::NamedTempFile::new_in(self.path.parent()?).ok()?;
        temporary.write_all(self.key.as_bytes()).ok()?;
        temporary
            .write_all(self.auth.tag(&self.key, &data).as_bytes())
            .ok()?;
        temporary.write_all(&data).ok()?;
        temporary.persist(&self.path).ok()?;
        Some(())
    }
}

impl StoredToml {
    fn decode(compressed: &[u8]) -> Option<(TomlManifest, TomlManifest)> {
        let mut bytes = Vec::new();
        let decoded = flate2::read::DeflateDecoder::new(compressed)
            .take(MAX_TOML_FORMS as u64 + 1)
            .read_to_end(&mut bytes)
            .ok()?;
        if decoded > MAX_TOML_FORMS {
            return None;
        }
        serde_json::from_slice(&bytes).ok()
    }

    pub(super) fn forms(&self) -> &(TomlManifest, TomlManifest) {
        self.forms.get_or_init(|| {
            Self::decode(&self.compressed_forms)
                .expect("the local writer validated the authenticated compressed manifest")
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt as _;

    #[test]
    fn key_creation_is_atomic_and_key_replacement_invalidates_the_tag() {
        let home = tempfile::tempdir().unwrap();
        let target = tempfile::tempdir().unwrap();
        let input = blake3::hash(b"manifest");
        let barrier = std::sync::Barrier::new(8);
        let tags = std::thread::scope(|scope| {
            let handles = (0..8)
                .map(|_| {
                    scope.spawn(|| {
                        barrier.wait();
                        AuthKey::load(home.path(), target.path())
                            .unwrap()
                            .tag(&input, b"payload")
                    })
                })
                .collect::<Vec<_>>();
            handles
                .into_iter()
                .map(|h| h.join().unwrap())
                .collect::<Vec<_>>()
        });
        assert!(tags.iter().all(|tag| tag == &tags[0]));
        assert_ne!(tags[0], blake3::keyed_hash(input.as_bytes(), b"payload"));
        let path = home.path().join(AUTH_FILE);
        std::fs::remove_file(&path).unwrap();
        assert_ne!(
            AuthKey::load(home.path(), target.path())
                .unwrap()
                .tag(&input, b"payload"),
            tags[0]
        );
        assert!(AuthKey::load(home.path(), home.path()).is_none());
        let malformed = vec![0; AUTH_FORMAT.len() + 32];
        std::fs::write(&path, &malformed).unwrap();
        assert!(AuthKey::load(home.path(), target.path()).is_none());
        assert_eq!(std::fs::read(&path).unwrap(), malformed);
        let moved = home.path().join("moved");
        std::fs::rename(&path, &moved).unwrap();
        std::os::unix::fs::symlink(&moved, &path).unwrap();
        assert!(AuthKey::load(home.path(), target.path()).is_none());
        assert!(path.is_symlink());
    }

    #[test]
    fn first_writer_creates_a_missing_cargo_home() {
        let parent = tempfile::tempdir().unwrap();
        let target = tempfile::tempdir().unwrap();
        let home = parent.path().join("home/.cargo");
        let key = AuthKey::load(&home, target.path()).unwrap();
        assert_eq!(AuthKey::load(&home, target.path()).unwrap().0, key.0);
        assert_eq!(
            home.join(AUTH_FILE)
                .metadata()
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
    }

    #[test]
    fn read_only_home_reuses_an_existing_key_and_misses_without_one() {
        let home = tempfile::tempdir().unwrap();
        let target = tempfile::tempdir().unwrap();
        let key = AuthKey::load(home.path(), target.path()).unwrap();
        let permissions = home.path().metadata().unwrap().permissions();
        std::fs::set_permissions(home.path(), std::fs::Permissions::from_mode(0o500)).unwrap();
        assert_eq!(AuthKey::load(home.path(), target.path()).unwrap().0, key.0);
        std::fs::set_permissions(home.path(), permissions.clone()).unwrap();
        std::fs::remove_file(home.path().join(AUTH_FILE)).unwrap();
        std::fs::set_permissions(home.path(), std::fs::Permissions::from_mode(0o500)).unwrap();
        if tempfile::NamedTempFile::new_in(home.path()).is_err() {
            assert!(AuthKey::load(home.path(), target.path()).is_none());
        }
        std::fs::set_permissions(home.path(), permissions).unwrap();
    }

    #[test]
    fn compressed_forms_are_bounded_and_must_contain_the_typed_pair() {
        for invalid in [
            vec![0xff; 32],
            b"[]".to_vec(),
            vec![b' '; MAX_TOML_FORMS + 1],
        ] {
            let mut writer =
                flate2::write::DeflateEncoder::new(Vec::new(), flate2::Compression::fast());
            writer.write_all(&invalid).unwrap();
            assert!(StoredToml::decode(&writer.finish().unwrap()).is_none());
        }
        assert!(StoredToml::decode(&[0xff; 32]).is_none());
    }
}
