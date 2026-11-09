//! Replays a previous feature selection when the manifests, lockfile, and source summaries match.

use crate::resolver::Resolve;
use crate::util::StableHasher;
use crate::workspace::Workspace;
use cargo_util::paths;
use rustc_hash::FxHashMap as HashMap;
use std::hash::{Hash, Hasher};
use std::path::{Path, PathBuf};

use crate::resolver::{CliFeatures, HasDevUnits, ResolveOpts, ResolveVersion};
use crate::sources::{IndexSummary, source::QueryKind};
use crate::util::data_structures::HashSet;
use crate::util::interning::InternedString;
use crate::util::{Graph, OptVersionReq};
use crate::workspace::registry::{PackageRegistry, Registry};
use crate::workspace::{Dependency, PackageId, PackageIdSpec, Summary};

#[derive(serde::Serialize, serde::Deserialize)]
struct Selection {
    key: u64,
    packages: Vec<SelectedPackage>,
    index: crate::sources::registry::index::SelectedIndex,
}

#[derive(serde::Serialize, serde::Deserialize)]
struct SelectedPackage {
    id: usize,
    signature: SelectedSignature,
    features: Option<Vec<InternedString>>,
    // Target lockfile package and ordinal in the parent's current dependency declarations.
    dependencies: Vec<(usize, usize)>,
}

#[derive(serde::Serialize, serde::Deserialize, PartialEq)]
enum SelectedSignature {
    Index(u64, [u8; 32]),
    Summary(u64),
}

impl SelectedSignature {
    fn for_summary(summary: &Summary, gctx: &crate::GlobalContext) -> Self {
        let id = summary.package_id();
        if id.source_id().is_registry()
            && let Some((source, digest)) = gctx
                .selected_index
                .current()
                .and_then(|i| i.lock().unwrap().observed(id))
        {
            SelectedSignature::Index(source, digest)
        } else {
            SelectedSignature::Summary(selection_summary_hash(summary))
        }
    }
}

pub(in crate::ops) struct SelectedPlan {
    path: PathBuf,
    key: u64,
    auth: [u8; 32],
}

impl SelectedPlan {
    /// The workspace fingerprint includes its complete lockfile, manifests, and resolver configuration.
    /// Distinct member, feature, and dev-dependency selections can coexist in the target directory.
    pub(in crate::ops) fn new(
        ws: &Workspace<'_>,
        fingerprint: u64,
        features: &CliFeatures,
        dev: HasDevUnits,
        specs: &[PackageIdSpec],
    ) -> Option<Self> {
        if !cfg!(unix)
            || !ws.root_patch().ok()?.is_empty()
            || !ws.root_replace().is_empty()
            || ws.resolve_publish_time().is_some()
            || ws.gctx().paths_overrides().ok()?.is_some()
            || ws.gctx().cli_unstable().min_publish_age
        {
            return None;
        }
        let mut hasher = StableHasher::new();
        (
            2u32,
            fingerprint,
            features,
            dev == HasDevUnits::Yes,
            specs,
            ws.root(),
            ws.gctx().home().as_path_unlocked(),
            ws.gctx().network_allowed(),
        )
            .hash(&mut hasher);
        let key = Hasher::finish(&hasher);
        let target = ws.target_dir();
        let auth = selection_auth_key(
            ws.gctx().home().as_path_unlocked(),
            target.as_path_unlocked(),
        )?;
        let path = target
            .as_path_unlocked()
            .join(format!(".cargo-locked-selection-v2-{:02x}", key & 63));
        Some(Self { path, key, auth })
    }

    /// Query each locked package through its actual source. A failed query or changed
    /// index record, path summary, or checksum sends the caller through the resolver.
    pub(in crate::ops) fn load(
        &self,
        previous: &Resolve,
        registry: &PackageRegistry<'_>,
        roots: &[(Summary, ResolveOpts)],
        version: ResolveVersion,
        version_prefs: &crate::resolver::VersionPreferences,
        gctx: &crate::GlobalContext,
    ) -> Option<Resolve> {
        use std::io::Read as _;
        let file = paths::open_regular(&self.path).ok()?;
        let metadata = file.metadata().ok()?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt as _;
            // SAFETY: geteuid accepts no arguments and has no memory safety requirements.
            if metadata.uid() != unsafe { libc::geteuid() } || metadata.mode() & 0o022 != 0 {
                return None;
            }
        }
        if metadata.len() > 4 << 20 {
            return None;
        }
        let mut data = Vec::with_capacity(metadata.len() as usize);
        file.take(metadata.len() + 1).read_to_end(&mut data).ok()?;
        if data.len() as u64 != metadata.len() {
            return None;
        }
        let (digest, payload) = data.split_at_checked(32)?;
        if digest != blake3::keyed_hash(&self.auth, payload).as_bytes() {
            return None;
        }
        let selected: Selection = postcard::from_bytes(payload)
            .inspect_err(|error| {
                tracing::debug!("unable to decode a prior locked selection: {error}");
            })
            .ok()?;
        if selected.key != self.key {
            return None;
        }
        let ids = previous.iter().collect::<Vec<_>>();
        let present: HashSet<_> = selected
            .packages
            .iter()
            .map(|pkg| ids.get(pkg.id).copied())
            .collect::<Option<_>>()?;
        if present.is_empty()
            || present.len() != selected.packages.len()
            || !roots
                .iter()
                .all(|(root, _)| present.contains(&root.package_id()))
            || selected
                .packages
                .iter()
                .flat_map(|pkg| &pkg.dependencies)
                .any(|(target, _)| ids.get(*target).is_none_or(|id| !present.contains(id)))
        {
            return None;
        }
        *gctx.selected_index.current()?.lock().unwrap() = selected.index;
        let roots = roots
            .iter()
            .map(|(s, _)| (s.package_id(), s))
            .collect::<HashMap<_, _>>();
        let mut graph: Graph<PackageId, HashSet<Dependency>> = Graph::new();
        let mut features = HashMap::default();
        let mut checksums = HashMap::default();
        let mut summaries = HashMap::default();
        crate::util::block_on(async {
            for pkg in selected.packages {
                let id = *ids.get(pkg.id)?;
                let summary = if let Some(summary) = roots.get(&id) {
                    (*summary).clone()
                } else {
                    let mut dep = Dependency::parse(id.name(), None, id.source_id()).ok()?;
                    dep.set_version_req(OptVersionReq::lock_to_exact(id.version()));
                    let mut matches = registry
                        .query_vec(&dep, QueryKind::Exact)
                        .await
                        .ok()?
                        .into_iter();
                    match (matches.next(), matches.next()) {
                        (Some(IndexSummary::Candidate(s)), None) if s.package_id() == id => s,
                        // The resolver permits a yanked version only when already preferred
                        // from the lockfile. This path only considers fully locked selections.
                        (Some(IndexSummary::Yanked(s)), None)
                            if s.package_id() == id && version_prefs.should_prefer(&id) =>
                        {
                            s
                        }
                        _ => {
                            tracing::debug!(
                                "the source did not return one locked candidate for {id}"
                            );
                            return None;
                        }
                    }
                };
                if SelectedSignature::for_summary(&summary, gctx) != pkg.signature {
                    tracing::debug!("the locked source summary changed for {id}");
                    return None;
                }
                graph.add(id);
                for (target, ordinal) in pkg.dependencies {
                    let target = *ids.get(target)?;
                    let declaration = summary.dependencies().get(ordinal)?;
                    if !declaration.matches_id(target) {
                        return None;
                    }
                    graph.link(id, target).insert(declaration.clone());
                }
                if let Some(f) = pkg.features {
                    features.insert(id, f);
                }
                checksums.insert(id, summary.checksum().map(str::to_owned));
                summaries.insert(id, summary);
            }
            Some(())
        })?;
        Some(Resolve::new(
            graph,
            Default::default(),
            features,
            checksums,
            Default::default(),
            Vec::new(),
            version,
            summaries,
        ))
    }

    /// Keep only successful selections whose edges all have exact versions in the lockfile.
    pub(in crate::ops) fn store(
        &self,
        previous: &Resolve,
        resolved: &Resolve,
        gctx: &crate::GlobalContext,
    ) -> Option<()> {
        if !resolved.replacements().is_empty() {
            return None;
        }
        let ids = previous
            .iter()
            .enumerate()
            .map(|(i, id)| (id, i))
            .collect::<HashMap<_, _>>();
        let mut features = resolved.features_clone();
        let mut packages = Vec::new();
        for id in resolved.iter() {
            if !(id.source_id().is_path() || id.source_id().is_crates_io()) {
                return None;
            }
            let summary = resolved.summary(id);
            let mut dependencies = Vec::new();
            for (target, declarations) in resolved.deps_not_replaced(id) {
                for decl in declarations {
                    if decl.version_req().locked_version() != Some(target.version()) {
                        return None;
                    }
                    let ordinal = summary.dependencies().iter().position(|d| d == decl)?;
                    dependencies.push((*ids.get(&target)?, ordinal));
                }
            }
            packages.push(SelectedPackage {
                id: *ids.get(&id)?,
                signature: SelectedSignature::for_summary(summary, gctx),
                features: features.remove(&id),
                dependencies,
            });
        }
        let mut index = std::mem::take(&mut *gctx.selected_index.current()?.lock().unwrap());
        index.finish_recording();
        let data = postcard::to_allocvec(&Selection {
            key: self.key,
            packages,
            index,
        })
        .ok()?;
        if data.len() + 32 > 4 << 20 {
            return None;
        }
        use std::io::Write as _;
        let mut entry = tempfile::NamedTempFile::new_in(self.path.parent()?).ok()?;
        entry
            .write_all(blake3::keyed_hash(&self.auth, &data).as_bytes())
            .ok()?;
        entry.write_all(&data).ok()?;
        entry.persist(&self.path).ok()?;
        Some(())
    }
}

/// A restored target carries the resolver's choices. Authenticate them with a key
/// kept separately in this Cargo home's private cache.
#[cfg(unix)]
fn selection_auth_key(home: &Path, target: &Path) -> Option<[u8; 32]> {
    use std::io::{Read as _, Write as _};
    use std::os::unix::fs::MetadataExt as _;
    let directory =
        crate::workspace::parser::registry_cache::private_directory(home, ".ohm-locked-selection")?;
    if directory.starts_with(target.canonicalize().ok()?) {
        return None;
    }
    let path = directory.join("key-v2");
    if let Err(error) = path.symlink_metadata() {
        if error.kind() != std::io::ErrorKind::NotFound {
            return None;
        }
        let mut key = [0; 32];
        std::fs::File::open("/dev/urandom")
            .ok()?
            .read_exact(&mut key)
            .ok()?;
        let mut temp = tempfile::NamedTempFile::new_in(&directory).ok()?;
        temp.write_all(&key).ok()?;
        match temp.persist_noclobber(&path) {
            Ok(_) => {}
            Err(e) if e.error.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(_) => return None,
        }
    }
    let mut file = paths::open_regular(&path).ok()?;
    let metadata = file.metadata().ok()?;
    // SAFETY: geteuid takes no arguments.
    if metadata.uid() != unsafe { libc::geteuid() }
        || metadata.mode() & 0o077 != 0
        || metadata.nlink() != 1
        || metadata.len() != 32
    {
        return None;
    }
    let mut key = [0; 32];
    file.read_exact(&mut key).ok()?;
    (key != [0; 32]).then_some(key)
}

#[cfg(not(unix))]
fn selection_auth_key(_: &Path, _: &Path) -> Option<[u8; 32]> {
    None
}

fn selection_summary_hash(s: &Summary) -> u64 {
    let mut hasher = StableHasher::new();
    (
        s.package_id(),
        s.dependencies(),
        s.features(),
        s.checksum(),
        s.rust_version(),
        s.links(),
        s.pubtime(),
    )
        .hash(&mut hasher);
    Hasher::finish(&hasher)
}
