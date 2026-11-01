//! [`BuildContext`] is a (mostly) static information about a build task.

use std::hash::Hash;
use std::path::{Path, PathBuf};

use crate::compiler::BuildConfig;
use crate::compiler::CompileKind;
use crate::compiler::Unit;
use crate::compiler::UnitIndex;
use crate::compiler::unit_graph::UnitGraph;
use crate::context::GlobalContext;
use crate::util::data_structures::{HashMap, HashSet};
use crate::util::errors::CargoResult;
use crate::util::interning::InternedString;
use crate::util::logger::BuildLogger;
use crate::util::{Rustc, StableHasher};
use crate::workspace::PackageId;
use crate::workspace::PackageSet;
use crate::workspace::Workspace;
use crate::workspace::dependency::DepKind;
use crate::workspace::profiles::Profiles;

mod target_info;
pub use self::target_info::FileFlavor;
pub use self::target_info::FileType;
pub use self::target_info::RustcTargetData;
pub use self::target_info::TargetInfo;

/// The build context, containing complete information needed for a build task
/// before it gets started.
///
/// It is intended that this is mostly static information. Stuff that mutates
/// during the build can be found in the parent [`BuildRunner`]. (I say mostly,
/// because this has internal caching, but nothing that should be observable
/// or require &mut.)
///
/// As a result, almost every field on `BuildContext` is public, including
///
/// * a resolved [`UnitGraph`] of your dependencies,
/// * a [`Profiles`] containing compiler flags presets,
/// * a [`RustcTargetData`] containing host and target platform information,
/// * and a [`PackageSet`] for further package downloads,
///
/// just to name a few. Learn more on each own documentation.
///
/// # How to use
///
/// To prepare a build task, you may not want to use [`BuildContext::new`] directly,
/// since it is often too lower-level.
/// Instead, [`ops::create_bcx`] is usually what you are looking for.
///
/// After a `BuildContext` is built, the next stage of building is handled in [`BuildRunner`].
///
/// [`BuildRunner`]: crate::compiler::BuildRunner
/// [`ops::create_bcx`]: crate::ops::create_bcx
pub struct BuildContext<'a, 'gctx> {
    /// The workspace the build is for.
    pub ws: &'a Workspace<'gctx>,

    /// The physical build directory used to make local source paths relocatable.
    build_dir: PathBuf,

    /// The cargo context.
    pub gctx: &'gctx GlobalContext,

    /// Build logger for `-Zbuild-analysis`.
    pub logger: Option<&'a BuildLogger>,

    /// This contains a collection of compiler flags presets.
    pub profiles: Profiles,

    /// Configuration information for a rustc build.
    pub build_config: &'a BuildConfig,

    /// Associated [`DepKind`]s for root targets
    pub selected_dep_kinds: DepKindSet,

    /// Extra compiler args for either `rustc` or `rustdoc`.
    pub extra_compiler_args: HashMap<Unit, Vec<String>>,

    /// Effective flags for units whose compiler arguments reference files.
    pub(super) argfile_hashes: HashMap<Unit, ArgfileFingerprint>,
    /// Documentation units whose forwarded arguments select JSON output.
    forwarded_json_docs: HashSet<Unit>,

    /// Package downloader.
    ///
    /// This holds ownership of the `Package` objects.
    pub packages: PackageSet<'gctx>,

    /// Information about rustc and the target platform.
    pub target_data: RustcTargetData<'gctx>,

    /// The root units of `unit_graph` (units requested on the command-line).
    pub roots: Vec<Unit>,

    /// Native integration-test units inspected as possible check results.
    /// These and their private dependencies are never scheduled as build jobs.
    pub test_check_candidates: HashMap<Unit, Unit>,

    /// The dependency graph of units to compile.
    pub unit_graph: UnitGraph,

    /// Exact registry packages authenticated for execution inside an audited procedural macro.
    pub audited_proc_macro_packages: HashSet<PackageId>,

    /// Canonical registry packages authenticated for permissive native-tool execution.
    pub authenticated_native_tool_packages: HashSet<PackageId>,

    /// A map from unit to index.
    pub unit_to_index: HashMap<Unit, UnitIndex>,

    /// Reverse-dependencies of documented units, used by the `rustdoc --scrape-examples` flag.
    pub scrape_units: Vec<Unit>,

    /// The list of all kinds that are involved in this build
    pub all_kinds: HashSet<CompileKind>,
}

impl<'a, 'gctx> BuildContext<'a, 'gctx> {
    pub fn new(
        ws: &'a Workspace<'gctx>,
        logger: Option<&'a BuildLogger>,
        packages: PackageSet<'gctx>,
        build_config: &'a BuildConfig,
        selected_dep_kinds: DepKindSet,
        profiles: Profiles,
        extra_compiler_args: HashMap<Unit, Vec<String>>,
        target_data: RustcTargetData<'gctx>,
        roots: Vec<Unit>,
        test_check_candidates: HashMap<Unit, Unit>,
        unit_graph: UnitGraph,
        audited_proc_macro_packages: HashSet<PackageId>,
        authenticated_native_tool_packages: HashSet<PackageId>,
        unit_to_index: HashMap<Unit, UnitIndex>,
        scrape_units: Vec<Unit>,
    ) -> CargoResult<BuildContext<'a, 'gctx>> {
        let all_kinds = unit_graph
            .keys()
            .map(|u| u.kind)
            .chain(build_config.requested_kinds.iter().copied())
            .chain(std::iter::once(CompileKind::Host))
            .collect();

        let (argfile_hashes, forwarded_json_docs) =
            compiler_inputs(ws, &unit_graph, &extra_compiler_args);

        Ok(BuildContext {
            ws,
            build_dir: ws.canonical_build_path(ws.build_dir().as_path_unlocked()),
            gctx: ws.gctx(),
            logger,
            packages,
            build_config,
            selected_dep_kinds,
            profiles,
            extra_compiler_args,
            argfile_hashes,
            forwarded_json_docs,
            target_data,
            roots,
            test_check_candidates,
            unit_graph,
            audited_proc_macro_packages,
            authenticated_native_tool_packages,
            unit_to_index,
            scrape_units,
            all_kinds,
        })
    }

    /// Information of the `rustc` this build task will use.
    pub fn rustc(&self) -> &Rustc {
        &self.target_data.rustc
    }

    /// Gets the host architecture triple.
    ///
    /// For example, `x86_64-unknown-linux-gnu`, would be
    /// - machine: `x86_64`,
    /// - hardware-platform: `unknown`,
    /// - operating system: `linux-gnu`.
    pub fn host_triple(&self) -> InternedString {
        self.target_data.rustc.host
    }

    /// Distinguishes the source on disk and the manifest path visible to build scripts and rustc.
    pub(crate) fn hash_shared_build_source(&self, unit: &Unit, hasher: &mut StableHasher) {
        if unit.is_std || !unit.pkg.package_id().source_id().is_path() {
            return;
        }
        let root = unit.pkg.root();
        let resolved = self.ws.canonical_build_path(root);
        if root == resolved && self.ws.shared_registry_cache_enabled() {
            return;
        }
        let mut hash_relative = |path: &Path| {
            pathdiff::diff_paths(path, &self.build_dir)
                .as_deref()
                .unwrap_or(path)
                .hash(hasher);
        };
        hash_relative(&resolved);
        if root != resolved {
            hash_relative(root);
        }
    }

    /// Gets the number of jobs specified for this build.
    pub fn jobs(&self) -> u32 {
        self.build_config.jobs
    }

    /// Whether Cargo or the flags forwarded to this rustdoc unit requested JSON.
    pub(crate) fn wants_doc_json(&self, unit: &Unit) -> bool {
        self.build_config.intent.wants_doc_json_output() || self.forwarded_json_docs.contains(unit)
    }

    /// Extra compiler args for either `rustc` or `rustdoc`.
    ///
    /// As of now, these flags come from the trailing args of either
    /// `cargo rustc` or `cargo rustdoc`.
    pub fn extra_args_for(&self, unit: &Unit) -> Option<&Vec<String>> {
        self.extra_compiler_args.get(unit)
    }
}

#[derive(Copy, Clone, Default, Debug)]
pub struct DepKindSet {
    pub build: bool,
    pub normal: bool,
    pub dev: bool,
}

impl DepKindSet {
    pub fn contains(&self, kind: DepKind) -> bool {
        match kind {
            DepKind::Build => self.build,
            DepKind::Normal => self.normal,
            DepKind::Development => self.dev,
        }
    }
}

/// Effective argument fingerprint and whether it includes a per-build fallback.
pub(super) struct ArgfileFingerprint {
    pub(super) hash: u64,
    pub(super) untracked: bool,
}

/// Resolves file-backed arguments and identifies the documentation each unit produces.
fn compiler_inputs(
    ws: &Workspace<'_>,
    units: &UnitGraph,
    extra: &HashMap<Unit, Vec<String>>,
) -> (HashMap<Unit, ArgfileFingerprint>, HashSet<Unit>) {
    let mut hashes = HashMap::default();
    let mut json_docs = HashSet::default();
    let mut sources = HashMap::default();
    for unit in units.keys() {
        let doc = unit.mode.is_doc() || unit.mode.is_doc_scrape();
        let configured = if doc {
            &unit.rustdocflags
        } else {
            &unit.rustflags
        };
        let profile = (!doc).then_some(&unit.profile.rustflags);
        let flags = profile
            .into_iter()
            .flatten()
            .map(|flag| flag.as_str())
            .chain(extra.get(unit).into_iter().flatten().map(String::as_str))
            .chain(configured.iter().map(String::as_str));
        let expanded = if flags.clone().any(|arg| arg.starts_with('@')) {
            let expanded = crate::util::argfiles::expand(
                &crate::util::path_args(ws, unit).1,
                flags.clone(),
                &mut sources,
            );
            // Missing or streaming files must be handled by the compiler itself.
            let hash = expanded
                .as_ref()
                .map(crate::util::hash_u64)
                .unwrap_or_else(rand::random);
            hashes.insert(
                unit.clone(),
                ArgfileFingerprint {
                    hash,
                    untracked: expanded.is_none(),
                },
            );
            expanded
        } else {
            None
        };
        if doc {
            let json = match expanded {
                Some(args) => {
                    crate::compiler::rustdoc::forwarded_json(args.iter().map(String::as_str))
                }
                None => crate::compiler::rustdoc::forwarded_json(flags),
            };
            if json {
                json_docs.insert(unit.clone());
            }
        }
    }
    (hashes, json_docs)
}
