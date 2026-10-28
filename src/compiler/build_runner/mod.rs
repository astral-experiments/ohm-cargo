//! [`BuildRunner`] is the mutable state used during the build process.

use crate::util::data_structures::{HashMap, HashSet};
use std::ffi::OsString;
use std::fs::File;
use std::hash::{Hash, Hasher};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};

#[cfg(unix)]
use std::os::unix::fs::MetadataExt;

use crate::compiler::compilation::{self, UnitOutput};
use crate::compiler::locking::LockManager;
use crate::compiler::{self, CrateType, Unit, UserIntent, artifact};
use crate::util::cache_lock::CacheLockMode;
use crate::util::errors::CargoResult;
use crate::util::{GlobalContext, StableHasher};
use crate::workspace::PackageId;
use crate::workspace::SharedCacheAncestor;
use anyhow::{Context as _, bail};
use cargo_util::{ProcessBuilder, Sha256, paths};
use cargo_util_terminal::report::{Level, Message};
use filetime::FileTime;
use itertools::Itertools;
use jobserver::Client;
use serde::{Deserialize, Serialize};

use super::RustdocFingerprint;
use super::custom_build::{self, BuildDeps, BuildScriptOutputs, BuildScripts};
use super::fingerprint::{self, Checksum, Fingerprint};
use super::job_queue::JobQueue;
use super::layout::Layout;
use super::lto::Lto;
use super::unit_graph::UnitDep;
use super::unused_deps::UnusedDepState;
use super::{
    BuildContext, Compilation, CompileKind, CompileMode, CompileTarget, Executor, FileFlavor,
    OHM_COMPILER_LOADER_ENVIRONMENT, OHM_COMPILER_LOADER_INJECTION_ENVIRONMENT, UnitIndex,
};

mod compilation_files;
use self::compilation_files::CompilationFiles;
pub use self::compilation_files::{Metadata, OutputFile, UnitHash};

/// Registry packages whose built artifacts cannot safely satisfy a check.
///
/// Regenerating the graph without these packages preserves independently fresh
/// registry builds instead of disabling reuse for the entire dependency graph.
#[derive(Debug, thiserror::Error)]
#[error("an existing registry build artifact is missing or stale")]
pub(crate) struct StaleBuiltRegistryDependency {
    pub(crate) packages: HashSet<PackageId>,
    pub(crate) ordinary_check_might_exist: bool,
}

/// Retry preparation from scratch before changing any shared artifact.
#[derive(Debug, thiserror::Error)]
#[error("shared registry artifacts require additional exclusive unit locks")]
struct SharedCacheNeedsExclusiveLocks {
    units: HashSet<UnitIndex>,
}

#[derive(Deserialize)]
struct ExistingFingerprintProfile {
    profile: u64,
}

/// Additional facts needed to safely reuse an ordinary build as a check.
///
/// This is deliberately separate from Cargo's persisted fingerprint: users who
/// never opt in must keep their existing dependency artifacts completely fresh.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RegistryMessageProvenance {
    version: u8,
    compiler_context: u64,
    compiler_driver: CompilerDriverIdentity,
    compiler_search_directories: Vec<PathBuf>,
    effective_policy_context: u64,
    loader_injected: bool,
    messages: Option<CachedCompilerMessages>,
}

/// The executable launcher is only a small shim around this shared library.
#[derive(Clone, Debug, Deserialize, Eq, Hash, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct CompilerDriverIdentity {
    path: PathBuf,
    length: u64,
    modified: (i64, u32),
    created: Option<(i64, u32)>,
    #[cfg(unix)]
    changed: (i64, i64),
    #[cfg(unix)]
    device: u64,
    #[cfg(unix)]
    inode: u64,
}

/// Every option read by rustc's logger before it starts compiling a crate.
pub(crate) const OHM_RUSTC_LOG_ENVIRONMENT: &[&str] = &[
    "RUSTC_LOG",
    "RUSTC_LOG_COLOR",
    "RUSTC_LOG_ENTRY_EXIT",
    "RUSTC_LOG_THREAD_IDS",
    "RUSTC_LOG_BACKTRACE",
    "RUSTC_LOG_WRAPTREE",
    "RUSTC_LOG_LINES",
    "RUSTC_LOG_FORMAT_JSON",
    "RUSTC_LOG_OUTPUT_TARGET",
];

/// Reject runtime-driver substitutions without reading the large compiler dylib.
fn compiler_driver_search_directory_is_unshadowed(expected: &Path, directory: &Path) -> bool {
    let Some(driver_name) = expected.file_name() else {
        return false;
    };

    // Relative entries resolve against each rustc's own current directory,
    // which varies across registry units and cannot be validated globally.
    if !directory.is_absolute() {
        return false;
    }

    match directory.join(driver_name).canonicalize() {
        Ok(candidate) => candidate == expected,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => true,
        Err(_) => false,
    }
}

/// Resolve the compiler using the same executable search path as its child process.
///
/// Registry compiler processes run from their package roots, so relative programs
/// and relative search directories cannot be authenticated independently of a unit.
pub(crate) fn resolve_effective_compiler_executable(
    gctx: &GlobalContext,
    compiler: &Path,
) -> Option<PathBuf> {
    if compiler.is_absolute() {
        return compiler.canonicalize().ok();
    }
    // On Windows, Cargo also synthesizes a per-unit dynamic-library search
    // path in `PATH`, so a bare executable cannot be resolved globally.
    if cfg!(windows) {
        return None;
    }
    if compiler.components().count() != 1 {
        return None;
    }

    let configured_environment = gctx.env_config().ok()?;
    let search_path = configured_environment
        .get("PATH")
        .map(OsString::as_os_str)
        .or_else(|| gctx.get_env_os("PATH"))?;
    if std::env::split_paths(search_path).any(|directory| !directory.is_absolute()) {
        return None;
    }

    for directory in std::env::split_paths(search_path) {
        let candidate = directory.join(compiler);
        if candidate.is_file() {
            return candidate.canonicalize().ok();
        }
        if !std::env::consts::EXE_EXTENSION.is_empty() {
            let candidate = candidate.with_extension(std::env::consts::EXE_EXTENSION);
            if candidate.is_file() {
                return candidate.canonicalize().ok();
            }
        }
    }

    None
}

/// A toolchain can select an external default backend at compiler build time,
/// without exposing that choice in the unit's profile or command-line options.
fn sysroot_has_external_codegen_backends(sysroot: &Path, host: &str) -> bool {
    let backend_directory = sysroot
        .join("lib")
        .join("rustlib")
        .join(host)
        .join("codegen-backends");

    !matches!(backend_directory.try_exists(), Ok(false))
}

/// Windows treats environment variable names as case-insensitive even though
/// Cargo's process builder preserves their original spelling.
pub(crate) fn is_sensitive_compiler_environment(name: &str, windows: bool) -> bool {
    let matches_name = |expected: &str| {
        if windows {
            name.eq_ignore_ascii_case(expected)
        } else {
            name == expected
        }
    };

    OHM_COMPILER_LOADER_ENVIRONMENT
        .iter()
        .any(|expected| matches_name(expected))
        || OHM_RUSTC_LOG_ENVIRONMENT
            .iter()
            .any(|expected| matches_name(expected))
        || matches_name(paths::dylib_path_envvar())
        || (windows && matches_name("PATH"))
        || matches_name("RUSTC_BOOTSTRAP")
        || matches_name("RUSTC_OVERRIDE_VERSION_STRING")
}

/// Mixed-case Windows configuration keys can silently replace any variable
/// Cargo synthesized for its child processes, not just known loader names.
fn configured_compiler_environment_has_case_alias(
    configured_environment: &HashMap<String, OsString>,
    windows: bool,
) -> bool {
    windows
        && configured_environment
            .keys()
            .any(|name| name.bytes().any(|character| character.is_ascii_lowercase()))
}

/// Follow the same last-wins environment ordering as `ProcessBuilder` when a
/// Windows build script spells an existing variable with different casing.
fn effective_compiler_environment(
    compiler: &ProcessBuilder,
    name: &str,
    windows: bool,
) -> Option<OsString> {
    if windows
        && let Some((_, value)) = compiler
            .get_envs()
            .iter()
            .rev()
            .find(|(actual, _)| actual.eq_ignore_ascii_case(name))
    {
        return value.clone();
    }

    compiler.get_env(name)
}

/// Bind cacheable diagnostics to the successful compiler invocation.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct CachedCompilerMessages {
    length: u64,
    sha256: String,
}

impl RegistryMessageProvenance {
    /// Capture the actual child environment after build scripts override it.
    pub(crate) fn capture_compiler_environment(
        &mut self,
        compiler: &ProcessBuilder,
        build_script_overrides_loader: bool,
    ) {
        let mut policy = StableHasher::new();
        for name in ["RUSTC_BOOTSTRAP", "RUSTC_OVERRIDE_VERSION_STRING"] {
            name.hash(&mut policy);
            effective_compiler_environment(compiler, name, cfg!(windows)).hash(&mut policy);
        }
        self.effective_policy_context = Hasher::finish(&policy);
        self.compiler_search_directories =
            effective_compiler_environment(compiler, paths::dylib_path_envvar(), cfg!(windows))
                .map(|search_path| std::env::split_paths(&search_path).collect())
                .unwrap_or_default();
        self.loader_injected = build_script_overrides_loader
            || !self.compiler_search_directories.iter().all(|directory| {
                compiler_driver_search_directory_is_unshadowed(
                    &self.compiler_driver.path,
                    directory,
                )
            })
            || OHM_COMPILER_LOADER_INJECTION_ENVIRONMENT
                .iter()
                .any(|name| {
                    effective_compiler_environment(compiler, name, cfg!(windows))
                        .is_some_and(|value| !value.is_empty())
                });
    }

    /// Snapshot diagnostics with a bounded streaming read; no-warning builds
    /// have no message file and therefore never read compiler output.
    pub(crate) fn capture_messages(&mut self, path: &Path) -> CargoResult<()> {
        self.messages = Self::read_messages(path)?;
        Ok(())
    }

    /// Hash compiler messages while rejecting non-files and concurrent writes.
    /// An absent cache is valid only when no diagnostics were emitted.
    fn read_messages(path: &Path) -> CargoResult<Option<CachedCompilerMessages>> {
        let file = match File::open(path) {
            Ok(file) => file,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(error.into()),
        };
        let before = file.metadata()?;
        if !before.is_file() {
            bail!("cached compiler diagnostics must be a regular file");
        }
        let mut digest = Sha256::new();
        digest.update_file(&file)?;
        let after = file.metadata()?;
        if before.len() != after.len()
            || FileTime::from_last_modification_time(&before)
                != FileTime::from_last_modification_time(&after)
        {
            bail!("cached compiler diagnostics changed while being recorded");
        }
        Ok(Some(CachedCompilerMessages {
            length: after.len(),
            sha256: digest.finish_hex(),
        }))
    }

    /// Recheck both message presence and contents before replaying a cached build.
    fn messages_match(&self, path: &Path) -> bool {
        match (&self.messages, std::fs::metadata(path)) {
            (None, Err(error)) if error.kind() == std::io::ErrorKind::NotFound => true,
            (Some(expected), Ok(metadata))
                if metadata.is_file() && metadata.len() == expected.length =>
            {
                Self::read_messages(path)
                    .ok()
                    .flatten()
                    .is_some_and(|actual| actual == *expected)
            }
            _ => false,
        }
    }
}

/// Collection of all the stuff that is needed to perform a build.
///
/// Different from the [`BuildContext`], `Context` is a _mutable_ state used
/// throughout the entire build process. Everything is coordinated through this.
///
/// [`BuildContext`]: crate::compiler::BuildContext
pub struct BuildRunner<'a, 'gctx> {
    /// Mostly static information about the build task.
    pub bcx: &'a BuildContext<'a, 'gctx>,
    /// A large collection of information about the result of the entire compilation.
    pub compilation: Compilation<'gctx>,
    /// Output from build scripts, updated after each build script runs.
    pub build_script_outputs: Arc<Mutex<BuildScriptOutputs>>,
    /// Dependencies (like rerun-if-changed) declared by a build script.
    /// This is *only* populated from the output from previous runs.
    /// If the build script hasn't ever been run, then it must be run.
    pub build_explicit_deps: HashMap<Unit, BuildDeps>,
    /// Fingerprints used to detect if a unit is out-of-date.
    pub fingerprints: HashMap<Unit, Arc<Fingerprint>>,
    /// Cache of file mtimes to reduce filesystem hits.
    pub mtime_cache: HashMap<PathBuf, FileTime>,
    /// Cache of file checksums to reduce filesystem reads.
    pub checksum_cache: HashMap<PathBuf, Checksum>,
    /// A set used to track which units have been compiled.
    /// A unit may appear in the job graph multiple times as a dependency of
    /// multiple packages, but it only needs to run once.
    pub compiled: HashSet<Unit>,
    /// Linking information for each `Unit`.
    /// See `build_map` for details.
    pub build_scripts: HashMap<Unit, Arc<BuildScripts>>,
    /// Job server client to manage concurrency with other processes.
    pub jobserver: Client,
    /// "Primary" packages are the ones the user selected on the command-line
    /// with `-p` flags. If no flags are specified, then it is the defaults
    /// based on the current directory and the default workspace members.
    primary_packages: HashSet<PackageId>,
    /// Requested check units whose metadata is not consumed by another unit.
    terminal_check_units: HashSet<Unit>,
    /// Registry units that actually occupy a metadata-only check dependency
    /// edge after being promoted to an already-built library.
    reused_registry_units: HashSet<Unit>,
    /// Reused registry units which also have a consumer that genuinely needs
    /// their object code and therefore must retain their full JSON artifact.
    object_required_registry_units: HashSet<Unit>,
    /// Cached identity of the dynamic compiler implementation, not its tiny
    /// executable launcher. `None` disables cross-mode reuse fail-closed.
    compiler_driver_identity: OnceLock<Option<CompilerDriverIdentity>>,
    /// An abstraction of the files and directories that will be generated by
    /// the compilation. This is `None` until after `unit_dependencies` has
    /// been computed.
    files: Option<CompilationFiles<'a, 'gctx>>,

    /// A set of units which are compiling rlibs and are expected to produce
    /// metadata files in addition to the rlib itself.
    rmeta_required: HashSet<Unit>,

    /// Map of the LTO-status of each unit. This indicates what sort of
    /// compilation is happening (only object, only bitcode, both, etc), and is
    /// precalculated early on.
    pub lto: HashMap<Unit, Lto>,

    /// Map of Doc/Docscrape units to metadata for their -Cmetadata flag.
    /// See `Context::find_metadata_units` for more details.
    pub metadata_for_doc_units: HashMap<Unit, Metadata>,

    /// Set of metadata of Docscrape units that fail before completion, e.g.
    /// because the target has a type error. This is in an Arc<Mutex<..>>
    /// because it is continuously updated as the job progresses.
    pub failed_scrape_units: Arc<Mutex<HashSet<UnitHash>>>,

    pub unused_dep_state: UnusedDepState,

    /// Manages locks for build units when fine grain locking is enabled.
    pub lock_manager: Arc<LockManager>,

    /// Readers never upgrade in place: a dirty shared cache needs a fresh runner.
    exclusive_shared_cache_units: HashSet<UnitIndex>,
}

impl<'a, 'gctx> BuildRunner<'a, 'gctx> {
    pub fn new(bcx: &'a BuildContext<'a, 'gctx>) -> CargoResult<Self> {
        // Load up the jobserver that we'll use to manage our parallelism. This
        // is the same as the GNU make implementation of a jobserver, and
        // intentionally so! It's hoped that we can interact with GNU make and
        // all share the same jobserver.
        //
        // Note that if we don't have a jobserver in our environment then we
        // create our own, and we create it with `n` tokens, but immediately
        // acquire one, because one token is ourself, a running process.
        let jobserver = match bcx.gctx.jobserver_from_env() {
            Some(c) => c.clone(),
            None => {
                let client =
                    Client::new(bcx.jobs() as usize).context("failed to create jobserver")?;
                client.acquire_raw()?;
                client
            }
        };

        let mut terminal_check_units = bcx
            .roots
            .iter()
            .filter(|unit| matches!(unit.mode, CompileMode::Check { .. }))
            .cloned()
            .collect::<HashSet<_>>();
        let mut reused_registry_units = HashSet::default();
        let mut object_required_registry_units = HashSet::default();
        let reuse_built_registry_dependencies = bcx.gctx.cli_unstable().ohm_reuse_built_deps()
            && !bcx.gctx.cli_unstable().bindeps
            && matches!(bcx.build_config.intent, UserIntent::Check { .. });
        for (parent, dependencies) in &bcx.unit_graph {
            for dependency in dependencies {
                terminal_check_units.remove(&dependency.unit);
                if reuse_built_registry_dependencies
                    && Self::is_promotable_registry_dependency(bcx, &dependency.unit)
                {
                    if parent.mode.is_check() {
                        reused_registry_units.insert(dependency.unit.clone());
                    }
                    if !parent.mode.is_check() && parent.requires_upstream_objects() {
                        object_required_registry_units.insert(dependency.unit.clone());
                    }
                }
            }
        }

        if reuse_built_registry_dependencies {
            for registry_units in [
                &mut reused_registry_units,
                &mut object_required_registry_units,
            ] {
                let mut pending = registry_units.iter().cloned().collect::<Vec<_>>();
                while let Some(unit) = pending.pop() {
                    if let Some(dependencies) = bcx.unit_graph.get(&unit) {
                        for dependency in dependencies {
                            if Self::is_promotable_registry_dependency(bcx, &dependency.unit)
                                && registry_units.insert(dependency.unit.clone())
                            {
                                pending.push(dependency.unit.clone());
                            }
                        }
                    }
                }
            }
        }

        Ok(Self {
            bcx,
            compilation: Compilation::new(bcx)?,
            build_script_outputs: Arc::new(Mutex::new(BuildScriptOutputs::default())),
            fingerprints: HashMap::default(),
            mtime_cache: HashMap::default(),
            checksum_cache: HashMap::default(),
            compiled: HashSet::default(),
            build_scripts: HashMap::default(),
            build_explicit_deps: HashMap::default(),
            jobserver,
            primary_packages: HashSet::default(),
            terminal_check_units,
            reused_registry_units,
            object_required_registry_units,
            compiler_driver_identity: OnceLock::new(),
            files: None,
            rmeta_required: HashSet::default(),
            lto: HashMap::default(),
            metadata_for_doc_units: HashMap::default(),
            failed_scrape_units: Arc::new(Mutex::new(HashSet::default())),
            unused_dep_state: UnusedDepState::new(bcx),
            lock_manager: Arc::new(LockManager::new()),
            exclusive_shared_cache_units: HashSet::default(),
        })
    }

    /// Dry-run the compilation without actually running it.
    ///
    /// This is expected to collect information like the location of output artifacts.
    /// Please keep in sync with non-compilation part in [`BuildRunner::compile`].
    pub fn dry_run(mut self) -> CargoResult<Compilation<'gctx>> {
        let _lock = self
            .bcx
            .gctx
            .acquire_package_cache_lock(CacheLockMode::Shared)?;
        self.lto = super::lto::generate(self.bcx)?;
        self.prepare_units()?;
        self.prepare()?;
        self.check_collisions()?;

        for unit in &self.bcx.roots {
            self.collect_tests_and_executables(unit)?;
        }

        Ok(self.compilation)
    }

    /// Conservatively checks whether every root has an existing same-profile check.
    ///
    /// A speculative graph changes dependency metadata and therefore the root's
    /// fingerprint directory. Scan only siblings in the locked workspace/profile
    /// namespace; ambiguous entries retain the complete ordinary graph probe.
    fn ordinary_check_might_exist(&self) -> bool {
        self.bcx.roots.iter().all(|unit| {
            if !unit.mode.is_check() {
                return true;
            }

            let fingerprint = self.files().fingerprint_file_path(unit, "");
            let Some(filename) = fingerprint.file_name() else {
                return true;
            };
            let Some(directory) = fingerprint.parent() else {
                return true;
            };
            let new_layout = self.bcx.gctx.cli_unstable().build_dir_new_layout;
            let search_directory = if new_layout {
                directory.parent().and_then(Path::parent)
            } else {
                directory.parent()
            };
            let Some(search_directory) = search_directory else {
                return true;
            };
            let entries = match std::fs::read_dir(search_directory) {
                Ok(entries) => entries,
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => return false,
                Err(_) => return true,
            };
            let prefix = format!("{}-", unit.pkg.package_id().name());
            let expected_profile = fingerprint::unit_profile_hash(self, unit);

            for entry in entries {
                let Ok(entry) = entry else {
                    return true;
                };
                if !new_layout && !entry.file_name().to_string_lossy().starts_with(&prefix) {
                    continue;
                }
                match entry.file_type() {
                    Ok(kind) if kind.is_dir() => {}
                    Ok(kind) if kind.is_symlink() => return true,
                    Ok(_) => continue,
                    Err(_) => return true,
                }

                let candidate = if new_layout {
                    entry.path().join("fingerprint").join(filename)
                } else {
                    entry.path().join(filename)
                };
                match std::fs::symlink_metadata(&candidate) {
                    Ok(metadata) if metadata.is_file() => {}
                    Ok(_) => return true,
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
                    Err(_) => return true,
                }

                let json = candidate.with_extension("json");
                match std::fs::symlink_metadata(&json) {
                    Ok(metadata) if metadata.is_file() => {}
                    Ok(_) => return true,
                    Err(_) => return true,
                }
                let Ok(contents) = std::fs::read(json) else {
                    return true;
                };
                let Ok(existing) = serde_json::from_slice::<ExistingFingerprintProfile>(&contents)
                else {
                    return true;
                };
                if existing.profile == expected_profile {
                    return true;
                }
            }

            false
        })
    }

    /// Compiles an established ordinary check graph when it can still be reused.
    ///
    /// Keep the package-cache and workspace locks held while validating fingerprints and
    /// executing the selected graph. Consuming the runner also releases its workspace locks
    /// before an alternative graph is prepared when this graph cannot be reused.
    #[tracing::instrument(name = "compile", skip_all)]
    pub(crate) fn compile_if_check_graph_is_reusable(
        self,
        exec: &Arc<dyn Executor>,
    ) -> CargoResult<Option<Compilation<'gctx>>> {
        self.retry_with_shared_cache_write_locks(|runner| {
            runner.compile_if_check_graph_is_reusable_inner(exec)
        })
    }

    fn compile_if_check_graph_is_reusable_inner(
        mut self,
        exec: &Arc<dyn Executor>,
    ) -> CargoResult<Option<Compilation<'gctx>>> {
        if !matches!(self.bcx.build_config.intent, UserIntent::Check { .. })
            || self.bcx.build_config.force_rebuild
            || self.bcx.roots.is_empty()
        {
            return Ok(None);
        }

        let global_context = self.bcx.gctx;
        let _lock = global_context.acquire_package_cache_lock(CacheLockMode::Shared)?;
        let queue = JobQueue::new(self.bcx);
        self.lto = super::lto::generate(self.bcx)?;
        self.prepare_units()?;

        if self.bcx.roots.iter().any(|unit| {
            !unit.mode.is_check() || !self.files().fingerprint_file_path(unit, "").is_file()
        }) {
            return Ok(None);
        }

        self.prepare()?;
        custom_build::build_map(&mut self)?;

        let fine_grain_locking = self.bcx.gctx.cli_unstable().fine_grain_locking;
        let workspace_is_locked = self
            .files()
            .layout(CompileKind::Host)
            .build_dir()
            .has_workspace_lock();
        if fine_grain_locking && !workspace_is_locked {
            let mut roots = self.bcx.roots.clone();
            roots.sort_by_cached_key(|unit| self.files().build_unit_lock(unit));
            for unit in roots {
                self.lock_manager.lock_shared(&self, &unit)?;
            }
        }

        let mut workspace_changed = false;
        for unit in self.bcx.roots.clone() {
            match fingerprint::existing_check_root(&mut self, &unit)? {
                Some(fingerprint::ExistingCheckRoot::Fresh) => {}
                Some(fingerprint::ExistingCheckRoot::WorkspaceChanged) => workspace_changed = true,
                None => return Ok(None),
            }
        }

        if workspace_changed {
            let mut registry_check_units = self
                .bcx
                .unit_graph
                .keys()
                .filter(|unit| {
                    unit.mode.is_check() && unit.pkg.package_id().source_id().is_remote_registry()
                })
                .cloned()
                .collect::<Vec<_>>();
            if fine_grain_locking
                && (!workspace_is_locked
                    || registry_check_units
                        .iter()
                        .any(|unit| self.files().is_shared_registry_unit(unit)))
            {
                registry_check_units.sort_by_cached_key(|unit| self.files().build_unit_lock(unit));
            }

            for unit in registry_check_units {
                if fine_grain_locking
                    && (!workspace_is_locked || self.files().is_shared_registry_unit(&unit))
                {
                    self.lock_manager.lock_shared(&self, &unit)?;
                }
                if !fingerprint::existing_unit_is_fresh(&mut self, &unit)? {
                    return Ok(None);
                }
            }
        }

        self.compile_prepared(exec, queue).map(Some)
    }

    /// Starts compilation, waits for it to finish, and returns information
    /// about the result of compilation.
    ///
    /// See [`ops::cargo_compile`] for a higher-level view of the compile process.
    ///
    /// [`ops::cargo_compile`]: crate::ops::cargo_compile
    #[tracing::instrument(skip_all)]
    pub fn compile(self, exec: &Arc<dyn Executor>) -> CargoResult<Compilation<'gctx>> {
        self.retry_with_shared_cache_write_locks(|runner| runner.compile_inner(exec))
    }

    /// Discards locks and observations before reserving any newly discovered shared writers.
    fn retry_with_shared_cache_write_locks<T>(
        self,
        compile: impl Fn(Self) -> CargoResult<T>,
    ) -> CargoResult<T> {
        let bcx = self.bcx;
        let mut exclusive = self.exclusive_shared_cache_units.clone();
        let mut runner = self;
        loop {
            match compile(runner) {
                Err(error) if error.is::<SharedCacheNeedsExclusiveLocks>() => {
                    let request = error.downcast::<SharedCacheNeedsExclusiveLocks>().unwrap();
                    let previous = exclusive.len();
                    exclusive.extend(request.units);
                    if exclusive.len() == previous {
                        bail!("shared registry writer reservation did not make progress");
                    }
                    runner = Self::new(bcx)?;
                    runner.exclusive_shared_cache_units = exclusive.clone();
                }
                result => return result,
            }
        }
    }

    fn compile_inner(mut self, exec: &Arc<dyn Executor>) -> CargoResult<Compilation<'gctx>> {
        // A shared lock is held during the duration of the build since rustc
        // needs to read from the `src` cache, and we don't want other
        // commands modifying the `src` cache while it is running.
        let global_context = self.bcx.gctx;
        let _lock = global_context.acquire_package_cache_lock(CacheLockMode::Shared)?;
        let queue = JobQueue::new(self.bcx);
        self.lto = super::lto::generate(self.bcx)?;
        self.prepare_units()?;
        self.prepare()?;
        custom_build::build_map(&mut self)?;
        self.compile_prepared(exec, queue)
    }

    /// Executes a graph after its layouts, fingerprints, and build scripts are prepared.
    ///
    /// Both callers retain the package-cache lock for this method's entire execution.
    fn compile_prepared(
        mut self,
        exec: &Arc<dyn Executor>,
        mut queue: JobQueue<'gctx>,
    ) -> CargoResult<Compilation<'gctx>> {
        let stale_registry_packages = self.stale_reused_registry_dependencies()?;
        if !stale_registry_packages.is_empty() {
            return Err(StaleBuiltRegistryDependency {
                packages: stale_registry_packages,
                ordinary_check_might_exist: self.ordinary_check_might_exist(),
            }
            .into());
        }
        self.check_collisions()?;
        self.compute_metadata_for_doc_units();

        // We need to make sure that if there were any previous docs already compiled,
        // they were compiled with the same Rustc version that we're currently using.
        // See the function doc comment for more.
        if self.bcx.build_config.intent.is_doc() {
            RustdocFingerprint::check_rustdoc_fingerprint(&self)?
        }

        // Rustdoc may have removed outputs after a compiler change. Only cache
        // unit freshness once that invalidation is complete.
        self.check_shared_cache_write_locks(exec)?;

        for unit in &self.bcx.roots {
            let force_rebuild = self.bcx.build_config.force_rebuild;
            super::compile(&mut self, &mut queue, unit, exec, force_rebuild)?;
        }

        // Now that we've got the full job queue and we've done all our
        // fingerprint analysis to determine what to run, bust all the memoized
        // fingerprint hashes to ensure that during the build they all get the
        // most up-to-date values. In theory we only need to bust hashes that
        // transitively depend on a dirty build script, but it shouldn't matter
        // that much for performance anyway.
        for fingerprint in self.fingerprints.values() {
            fingerprint.clear_memoized();
        }

        // Now that we've figured out everything that we're going to do, do it!
        queue.execute(&mut self)?;

        // Add `OUT_DIR` to env vars if unit has a build script.
        let units_with_build_script = &self
            .bcx
            .roots
            .iter()
            .filter(|unit| self.build_scripts.contains_key(unit))
            .dedup_by(|x, y| x.pkg.package_id() == y.pkg.package_id())
            .collect::<Vec<_>>();
        for unit in units_with_build_script {
            for dep in &self.bcx.unit_graph[unit] {
                if dep.unit.mode.is_run_custom_build() {
                    let out_dir = if self.bcx.gctx.cli_unstable().build_dir_new_layout {
                        self.files().out_dir_new_layout(&dep.unit)
                    } else {
                        self.files().build_script_out_dir(&dep.unit)
                    };
                    let script_meta = self.get_run_build_script_metadata(&dep.unit);
                    self.compilation
                        .extra_env
                        .entry(script_meta)
                        .or_insert_with(Vec::new)
                        .push(("OUT_DIR".to_string(), out_dir.display().to_string()));
                }
            }
        }

        self.collect_doc_merge_info()?;

        // Collect the result of the build into `self.compilation`.
        for unit in &self.bcx.roots {
            self.collect_tests_and_executables(unit)?;

            // Collect information for `rustdoc --test`.
            if unit.mode.is_doc_test() {
                let mut unstable_opts = false;
                let mut args = compiler::extern_args(&self, unit, &mut unstable_opts)?;
                args.extend(compiler::lib_search_paths(&self, unit)?);
                args.extend(compiler::lto_args(&self, unit));
                args.extend(compiler::features_args(unit));
                args.extend(compiler::check_cfg_args(unit));

                let script_metas = self.find_build_script_metadatas(unit);
                if let Some(meta_vec) = script_metas.clone() {
                    for meta in meta_vec {
                        if let Some(output) = self.build_script_outputs.lock().unwrap().get(meta) {
                            for cfg in &output.cfgs {
                                args.push("--cfg".into());
                                args.push(cfg.into());
                            }

                            for check_cfg in &output.check_cfgs {
                                args.push("--check-cfg".into());
                                args.push(check_cfg.into());
                            }

                            for (lt, arg) in &output.linker_args {
                                if lt.applies_to(&unit.target, unit.mode) {
                                    args.push("-C".into());
                                    args.push(format!("link-arg={}", arg).into());
                                }
                            }
                        }
                    }
                }
                args.extend(unit.rustdocflags.iter().map(Into::into));

                use super::MessageFormat;
                let format = match self.bcx.build_config.message_format {
                    MessageFormat::Short => "short",
                    MessageFormat::Human => "human",
                    MessageFormat::Json { .. } => "json",
                };
                args.push("--error-format".into());
                args.push(format.into());

                self.compilation.to_doc_test.push(compilation::Doctest {
                    unit: unit.clone(),
                    args,
                    unstable_opts,
                    linker: self
                        .compilation
                        .target_linker(unit.kind)
                        .map(|p| p.to_path_buf()),
                    script_metas,
                    env: artifact::get_env(&self, unit, self.unit_deps(unit))?,
                });
            }

            super::output_depinfo(&mut self, unit)?;
        }

        for (script_meta, output) in self.build_script_outputs.lock().unwrap().iter() {
            self.compilation
                .extra_env
                .entry(*script_meta)
                .or_insert_with(Vec::new)
                .extend(output.env.iter().cloned());

            for dir in output.library_paths.iter() {
                self.compilation
                    .native_dirs
                    .insert(dir.clone().into_path_buf());
            }
        }
        Ok(self.compilation)
    }

    /// Discovers all missing writer reservations before any fingerprint is invalidated.
    fn check_shared_cache_write_locks(&mut self, exec: &Arc<dyn Executor>) -> CargoResult<()> {
        if !self.bcx.ws.shared_registry_cache_enabled() {
            return Ok(());
        }
        let units = self
            .bcx
            .unit_graph
            .keys()
            // Doctests run after compilation and deliberately have no fingerprint.
            .filter(|unit| !unit.mode.is_doc_test() && self.files().is_shared_registry_unit(unit))
            .cloned()
            .collect::<Vec<_>>();
        let mut needed = HashSet::default();
        for unit in units {
            let key = self.lock_manager.key_for_unit(self, &unit);
            if self.lock_manager.has_shared_cache_write_access(&key) {
                continue;
            }
            let forced = exec.force_rebuild(&unit)
                || (self.bcx.build_config.force_rebuild && self.bcx.roots.contains(&unit));
            if forced || !fingerprint::existing_unit_is_fresh(self, &unit)? {
                needed.insert(self.bcx.unit_to_index[&unit]);
            }
        }
        if !needed.is_empty() {
            return Err(SharedCacheNeedsExclusiveLocks { units: needed }.into());
        }
        Ok(())
    }

    /// Guards the mutation boundary as well as the read-only preflight.
    pub(super) fn require_shared_cache_write_access(&self, unit: &Unit) -> CargoResult<()> {
        if self.files().is_shared_registry_unit(unit) {
            let key = self.lock_manager.key_for_unit(self, unit);
            if !self.lock_manager.has_shared_cache_write_access(&key) {
                return Err(SharedCacheNeedsExclusiveLocks {
                    units: HashSet::from_iter([self.bcx.unit_to_index[unit]]),
                }
                .into());
            }
        }
        Ok(())
    }

    /// Gives actual build commands ownership of the leases protecting their inputs/outputs.
    pub(super) fn inherit_shared_cache_locks(
        &self,
        command: &mut ProcessBuilder,
    ) -> CargoResult<()> {
        if !self.bcx.ws.shared_registry_cache_enabled() {
            return Ok(());
        }
        #[cfg(unix)]
        {
            self.files().host.inherit_locks(command);
            for layout in self.files().target.values() {
                layout.inherit_locks(command);
            }
            self.lock_manager.inherit_shared_cache_locks(command);
        }
        let ws = self.bcx.ws;
        let mut ancestors = ws.shared_cache_ancestors()?;
        for kind in std::iter::once(CompileKind::Host)
            .chain(self.bcx.all_kinds.iter().copied())
            .sorted()
            .dedup()
        {
            let mut target = ws.target_dir();
            if let CompileKind::Target(target_kind) = kind {
                target.push(target_kind.short_name());
            }
            let build = self.files().layout(kind).build_dir();
            let build_profile = build
                .build()
                .parent()
                .expect("build directory has a profile");
            let artifact_profile = target.join(self.bcx.profiles.get_dir_name().as_str());
            ancestors.push(SharedCacheAncestor {
                build_root: ws.canonical_build_path(build.root()),
                target_root: ws.canonical_build_path(target.as_path_unlocked()),
                build_lock: ws.canonical_build_path(&build_profile.join(".cargo-build-lock")),
                artifact_lock: ws
                    .canonical_build_path(&artifact_profile.as_path_unlocked().join(".cargo-lock")),
            });
        }
        command.env(
            crate::CARGO_SHARED_CACHE_ANCESTORS_ENV,
            serde_json::to_string(&ancestors)?,
        );
        Ok(())
    }

    fn collect_tests_and_executables(&mut self, unit: &Unit) -> CargoResult<()> {
        for output in self.outputs(unit)?.iter() {
            if matches!(
                output.flavor,
                FileFlavor::DebugInfo
                    | FileFlavor::Auxiliary
                    | FileFlavor::Sbom
                    | FileFlavor::Unremap
            ) {
                continue;
            }

            let bindst = output.bin_dst();

            if unit.mode == CompileMode::Test {
                self.compilation
                    .tests
                    .push(self.unit_output(unit, &output.path)?);
            } else if unit.target.is_executable() {
                self.compilation
                    .binaries
                    .push(self.unit_output(unit, bindst)?);
            } else if unit.target.is_cdylib()
                && !self.compilation.cdylibs.iter().any(|uo| uo.unit == *unit)
            {
                self.compilation
                    .cdylibs
                    .push(self.unit_output(unit, bindst)?);
            }
        }
        Ok(())
    }

    fn collect_doc_merge_info(&mut self) -> CargoResult<()> {
        if !self.bcx.gctx.cli_unstable().rustdoc_mergeable_info {
            return Ok(());
        }

        if !self.bcx.build_config.intent.is_doc() {
            return Ok(());
        }

        if self.bcx.build_config.intent.wants_doc_json_output() {
            // rustdoc JSON output doesn't support merge (yet?)
            return Ok(());
        }

        let mut doc_parts_map: HashMap<_, Vec<_>> = HashMap::default();

        let unit_iter = if self.bcx.build_config.intent.wants_deps_docs() {
            itertools::Either::Left(self.bcx.unit_graph.keys())
        } else {
            itertools::Either::Right(self.bcx.roots.iter())
        };

        for unit in unit_iter {
            if !unit.mode.is_doc() {
                continue;
            }
            // Assumption: one `rustdoc` call generates only one cross-crate info JSON.
            let outputs = self.outputs(unit)?;

            let Some(doc_parts) = outputs
                .iter()
                .find(|o| matches!(o.flavor, FileFlavor::DocParts))
            else {
                continue;
            };

            doc_parts_map
                .entry(unit.kind)
                .or_default()
                .push(doc_parts.path.to_owned());
        }

        self.compilation.rustdoc_fingerprints = Some(
            doc_parts_map
                .into_iter()
                .map(|(kind, doc_parts)| (kind, RustdocFingerprint::new(self, kind, doc_parts)))
                .collect(),
        );

        Ok(())
    }

    /// Returns the executable for the specified unit (if any).
    pub fn get_executable(&mut self, unit: &Unit) -> CargoResult<Option<PathBuf>> {
        let is_binary = unit.target.is_executable();
        let is_test = unit.mode.is_any_test();
        if !unit.mode.generates_executable() || !(is_binary || is_test) {
            return Ok(None);
        }
        Ok(self
            .outputs(unit)?
            .iter()
            .find(|o| o.flavor == FileFlavor::Normal)
            .map(|output| output.bin_dst().clone()))
    }

    #[tracing::instrument(skip_all)]
    pub fn prepare_units(&mut self) -> CargoResult<()> {
        let dest = self.bcx.profiles.get_dir_name();
        if self.bcx.ws.shared_registry_cache_enabled() {
            let mut profile_locks = HashSet::default();
            for kind in std::iter::once(CompileKind::Host)
                .chain(self.bcx.all_kinds.iter().copied())
                .sorted()
                .dedup()
            {
                let mut root = self.bcx.ws.build_dir();
                if let CompileKind::Target(target) = kind {
                    root.push(target.short_name());
                }
                let lock = root.join(dest.as_str()).join(".cargo-build-lock");
                let lock = self.bcx.ws.canonical_build_path(lock.as_path_unlocked());
                if !profile_locks.insert(lock.clone()) {
                    bail!(
                        "shared registry build profiles alias the same lock: {}; \
                         use distinct host and target build directories",
                        lock.display()
                    );
                }
            }
        }
        // We try to only lock the artifact-dir if we need to.
        // For example, `cargo check` does not write any files to the artifact-dir so we don't need
        // to lock it.
        let must_take_artifact_dir_lock = match self.bcx.build_config.intent {
            UserIntent::Check { .. } => {
                // Generally cargo check does not need to take the artifact-dir lock but there is
                // one exception: If check has `--timings` we still need to lock artifact-dir since
                // we will output the report files.
                self.bcx.build_config.timing_report
            }
            UserIntent::Build
            | UserIntent::Test
            | UserIntent::Doc { .. }
            | UserIntent::Doctest
            | UserIntent::Bench => true,
        };
        let host_layout =
            Layout::new(self.bcx.ws, None, &dest, must_take_artifact_dir_lock, false)?;
        let mut targets = HashMap::default();
        for kind in self.bcx.all_kinds.iter() {
            if let CompileKind::Target(target) = *kind {
                let layout = Layout::new(
                    self.bcx.ws,
                    Some(target),
                    &dest,
                    must_take_artifact_dir_lock,
                    false,
                )?;
                targets.insert(target, layout);
            }
        }
        self.primary_packages
            .extend(self.bcx.roots.iter().map(|u| u.pkg.package_id()));
        self.compilation
            .root_crate_names
            .extend(self.bcx.roots.iter().map(|u| u.target.crate_name()));

        self.record_units_requiring_metadata();

        let files = CompilationFiles::new(self, host_layout, targets);
        self.files = Some(files);
        self.lock_manager
            .reserve_shared_cache(self, &self.exclusive_shared_cache_units)?;
        if !self
            .files()
            .shared_cache_compiler_directories_are_safe(self)
        {
            bail!(
                "generated compiler search paths changed while acquiring shared registry locks; \
                 retry with shared registry caching disabled"
            );
        }
        Ok(())
    }

    /// Prepare this context, ensuring that all filesystem directories are in
    /// place.
    #[tracing::instrument(skip_all)]
    pub fn prepare(&mut self) -> CargoResult<()> {
        self.files
            .as_mut()
            .unwrap()
            .host
            .prepare()
            .context("couldn't prepare build directories")?;
        for target in self.files.as_mut().unwrap().target.values_mut() {
            target
                .prepare()
                .context("couldn't prepare build directories")?;
        }

        let files = self.files.as_ref().unwrap();
        for &kind in self.bcx.all_kinds.iter() {
            let layout = files.layout(kind);
            if let Some(artifact_dir) = layout.artifact_dir() {
                self.compilation
                    .root_output
                    .insert(kind, artifact_dir.dest().to_path_buf());
            }
            if self.bcx.gctx.cli_unstable().build_dir_new_layout {
                for (unit, _) in self.bcx.unit_graph.iter() {
                    if kind != unit.kind {
                        continue;
                    }
                    let dep_dir = self.files().deps_dir(unit);
                    paths::create_dir_all(&dep_dir)?;
                    if unit.target.is_dylib() {
                        self.compilation
                            .deps_output
                            .entry(kind)
                            .or_default()
                            .insert(dep_dir);
                    }
                }
            } else {
                self.compilation
                    .deps_output
                    .entry(kind)
                    .or_default()
                    .insert(layout.build_dir().legacy_deps().to_path_buf());
            }
        }
        Ok(())
    }

    pub fn files(&self) -> &CompilationFiles<'a, 'gctx> {
        self.files.as_ref().unwrap()
    }

    /// Returns true only after the complete shared-registry trust context is finalized.
    ///
    /// Unit metadata is computed before `CompilationFiles` exists, so callers must treat
    /// registry immutability as unproven until its authenticated transitive closure is ready.
    pub(crate) fn is_immutable_shared_registry_unit(&self, unit: &Unit) -> bool {
        self.files
            .as_ref()
            .is_some_and(|files| files.is_shared_registry_unit(unit))
    }

    /// Records the compiler context and whether a successful registry build
    /// produced cached diagnostics without changing Cargo's own fingerprints.
    ///
    /// Compiler message caches are intentionally created lazily, so an absent
    /// cache is safe to reuse only when its originating build recorded that it
    /// emitted no cacheable messages.
    pub(crate) fn registry_message_provenance_path(&self, unit: &Unit) -> PathBuf {
        self.files()
            .fingerprint_file_path(unit, "ohm-message-provenance-")
    }

    /// Capture compiler inputs that an ordinary same-mode Cargo fingerprint
    /// does not track but that cross-mode reuse must validate.
    pub(crate) fn registry_message_provenance(
        &self,
    ) -> CargoResult<Option<RegistryMessageProvenance>> {
        let Some(compiler_driver) = self
            .compiler_driver_identity
            .get_or_init(|| self.find_compiler_driver())
            .as_ref()
        else {
            return Ok(None);
        };
        let mut context = StableHasher::new();
        let Some(compiler) =
            resolve_effective_compiler_executable(self.bcx.gctx, &self.bcx.rustc().path)
        else {
            return Ok(None);
        };
        compiler.hash(&mut context);
        let compiler_metadata = paths::metadata(&compiler)?;
        compiler_metadata.len().hash(&mut context);
        FileTime::from_creation_time(&compiler_metadata).hash(&mut context);
        FileTime::from_last_modification_time(&compiler_metadata).hash(&mut context);
        compiler_driver.hash(&mut context);

        let configured_environment = self.bcx.gctx.env_config()?;
        if configured_compiler_environment_has_case_alias(configured_environment, cfg!(windows)) {
            return Ok(None);
        }
        let mut policy = StableHasher::new();
        for name in ["RUSTC_BOOTSTRAP", "RUSTC_OVERRIDE_VERSION_STRING"]
            .into_iter()
            .chain(OHM_COMPILER_LOADER_ENVIRONMENT.iter().copied())
            .chain(
                (!OHM_COMPILER_LOADER_ENVIRONMENT.contains(&paths::dylib_path_envvar()))
                    .then_some(paths::dylib_path_envvar()),
            )
        {
            let value = if name == paths::dylib_path_envvar() {
                // Cargo constructs this variable from the inherited process
                // environment before applying configuration. `apply_env_config`
                // never overrides a variable that Cargo already populated.
                self.bcx.gctx.get_env_os(name)
            } else {
                configured_environment
                    .get(name)
                    .map(std::ffi::OsString::as_os_str)
                    .or_else(|| self.bcx.gctx.get_env_os(name))
            };
            name.hash(&mut context);
            value.hash(&mut context);
            if matches!(name, "RUSTC_BOOTSTRAP" | "RUSTC_OVERRIDE_VERSION_STRING") {
                name.hash(&mut policy);
                value.map(std::ffi::OsStr::to_os_string).hash(&mut policy);
            }
        }

        Ok(Some(RegistryMessageProvenance {
            version: 3,
            compiler_context: Hasher::finish(&context),
            compiler_driver: compiler_driver.clone(),
            compiler_search_directories: Vec::new(),
            effective_policy_context: Hasher::finish(&policy),
            loader_injected: false,
            messages: None,
        }))
    }

    /// Locate the one platform-native compiler implementation in its real
    /// sysroot. Multiple matches are ambiguous and must never be reused.
    fn find_compiler_driver(&self) -> Option<CompilerDriverIdentity> {
        let sysroot = &self.bcx.target_data.info(CompileKind::Host).sysroot;
        let runtime_directory = sysroot.join(if cfg!(windows) { "bin" } else { "lib" });
        let prefix = format!("{}rustc_driver-", std::env::consts::DLL_PREFIX);
        let suffix = std::env::consts::DLL_SUFFIX;
        let mut matching_driver = None;

        for entry in std::fs::read_dir(runtime_directory).ok()? {
            let entry = entry.ok()?;
            let file_name = entry.file_name();
            let name = file_name.to_str()?;
            let Some(hash) = name
                .strip_prefix(&prefix)
                .and_then(|name| name.strip_suffix(suffix))
            else {
                continue;
            };
            if hash.is_empty() || !hash.chars().all(|character| character.is_ascii_hexdigit()) {
                continue;
            }
            if matching_driver.replace(entry.path()).is_some() {
                return None;
            }
        }

        let path = matching_driver?.canonicalize().ok()?;
        let file = File::open(&path).ok()?;
        let metadata = file.metadata().ok()?;
        if !metadata.is_file() {
            return None;
        }
        if !self.compiler_driver_search_is_unshadowed(&path) {
            return None;
        }
        let modified = FileTime::from_last_modification_time(&metadata);
        let created = FileTime::from_creation_time(&metadata)
            .map(|time| (time.unix_seconds(), time.nanoseconds()));

        Some(CompilerDriverIdentity {
            path,
            length: metadata.len(),
            modified: (modified.unix_seconds(), modified.nanoseconds()),
            created,
            #[cfg(unix)]
            changed: (metadata.ctime(), metadata.ctime_nsec()),
            #[cfg(unix)]
            device: metadata.dev(),
            #[cfg(unix)]
            inode: metadata.ino(),
        })
    }

    /// A stable search-path string can still start resolving a different driver when its
    /// directory contents change, independently of the compiler or sysroot metadata.
    fn compiler_driver_search_is_unshadowed(&self, expected: &Path) -> bool {
        let Ok(configured_environment) = self.bcx.gctx.env_config() else {
            return false;
        };

        let inherited_search_paths_are_safe = OHM_COMPILER_LOADER_ENVIRONMENT
            .iter()
            .copied()
            .filter(|name| !OHM_COMPILER_LOADER_INJECTION_ENVIRONMENT.contains(name))
            .chain(
                (!OHM_COMPILER_LOADER_ENVIRONMENT.contains(&paths::dylib_path_envvar()))
                    .then_some(paths::dylib_path_envvar()),
            )
            .all(|name| {
                let search_path = if name == paths::dylib_path_envvar() {
                    self.bcx.gctx.get_env_os(name)
                } else {
                    configured_environment
                        .get(name)
                        .map(std::ffi::OsString::as_os_str)
                        .or_else(|| self.bcx.gctx.get_env_os(name))
                };
                let Some(search_path) = search_path else {
                    return true;
                };

                std::env::split_paths(search_path).all(|directory| {
                    compiler_driver_search_directory_is_unshadowed(expected, &directory)
                })
            });

        inherited_search_paths_are_safe
            && self
                .compilation
                .deps_output
                .values()
                .flatten()
                .chain(self.compilation.native_dirs.iter())
                .all(|directory| {
                    compiler_driver_search_directory_is_unshadowed(expected, directory)
                })
    }

    /// Validates the exact build-mode registry units selected by a check graph.
    /// This runs after Cargo has computed canonical unit hashes, LTO settings,
    /// output paths, and build-script dependencies, but before any rustc work.
    fn stale_reused_registry_dependencies(&mut self) -> CargoResult<HashSet<PackageId>> {
        if !self.bcx.gctx.cli_unstable().ohm_reuse_built_deps()
            || !matches!(self.bcx.build_config.intent, UserIntent::Check { .. })
        {
            return Ok(HashSet::default());
        }

        let mut promoted_units = self
            .reused_registry_units
            .iter()
            .cloned()
            .collect::<Vec<_>>();
        promoted_units.sort_by_key(|unit| self.files().unit_hash(unit));

        if promoted_units.is_empty() {
            return Ok(HashSet::default());
        }

        let mut registry_closure_units = HashSet::default();
        let mut pending = promoted_units.clone();
        while let Some(unit) = pending.pop() {
            if !registry_closure_units.insert(unit.clone()) {
                continue;
            }
            pending.extend(
                self.unit_deps(&unit)
                    .iter()
                    .filter(|dependency| {
                        dependency
                            .unit
                            .pkg
                            .package_id()
                            .source_id()
                            .is_remote_registry()
                            || self.bcx.ws.is_member(&dependency.unit.pkg)
                    })
                    .map(|dependency| dependency.unit.clone()),
            );
        }
        let mut registry_closure_units = registry_closure_units.into_iter().collect::<Vec<_>>();
        registry_closure_units.sort_by_key(|unit| self.files().unit_hash(unit));

        // Host procedural macros, build scripts, and their dependencies have
        // independent package and build-override profiles. Check their actual
        // units too, not just the target libraries promoted by the check graph.
        let mut stale_units = registry_closure_units
            .iter()
            .filter(|unit| self.unit_uses_custom_codegen_backend(unit))
            .cloned()
            .collect::<HashSet<_>>();

        if self.bcx.gctx.cli_unstable().fine_grain_locking {
            // Keep the complete registry closure stable from the fingerprint
            // probe until the normal job queue acquires these same locks.
            for unit in &registry_closure_units {
                self.lock_manager.lock_shared(self, unit)?;
            }
        }

        // Future-incompatibility diagnostics can originate in any transitive
        // dependency, even when only its parent has an incoming check edge.
        let Some(expected_provenance) = self.registry_message_provenance()? else {
            return Ok(promoted_units
                .into_iter()
                .map(|unit| unit.pkg.package_id())
                .collect());
        };
        // Equal provenance records share their authenticated driver and loader paths.
        let mut compiler_search_directories = HashSet::default();
        for unit in registry_closure_units
            .iter()
            .filter(|unit| Self::is_promotable_registry_dependency(self.bcx, unit))
        {
            let messages_available = std::fs::read(self.registry_message_provenance_path(unit))
                .ok()
                .and_then(|contents| {
                    serde_json::from_slice::<RegistryMessageProvenance>(&contents).ok()
                })
                .is_some_and(|provenance| {
                    if provenance.version != expected_provenance.version
                        || provenance.compiler_context != expected_provenance.compiler_context
                        || provenance.compiler_driver != expected_provenance.compiler_driver
                        || provenance.effective_policy_context
                            != expected_provenance.effective_policy_context
                        || provenance.loader_injected
                    {
                        return false;
                    }

                    compiler_search_directories
                        .extend(provenance.compiler_search_directories.iter().cloned());

                    let cached_messages = self.files().message_cache_path(unit);
                    provenance.messages_match(&cached_messages)
                });
            if !messages_available {
                stale_units.insert(unit.clone());
            }
        }

        for unit in &promoted_units {
            let outputs = self.outputs(unit)?;
            let has_output = |extension| {
                outputs.iter().any(|output| {
                    output.path.extension().and_then(|actual| actual.to_str()) == Some(extension)
                        && output.path.is_file()
                })
            };
            if !has_output("rlib")
                || !has_output("rmeta")
                || !fingerprint::existing_unit_is_fresh(self, unit)?
            {
                stale_units.insert(unit.clone());
            }
        }

        // Every accepted record has the same authenticated compiler driver. Check each
        // distinct loader directory once, after all fingerprints and diagnostics have
        // been validated, so substitutions are rejected immediately before promotion.
        if !compiler_search_directories.iter().all(|directory| {
            compiler_driver_search_directory_is_unshadowed(
                &expected_provenance.compiler_driver.path,
                directory,
            )
        }) {
            return Ok(promoted_units
                .into_iter()
                .map(|unit| unit.pkg.package_id())
                .collect());
        }

        if stale_units.is_empty() {
            return Ok(HashSet::default());
        }

        // A built parent cannot remain promoted when any dependency in its
        // build closure must fall back to metadata-only checking. Propagate
        // rejected artifacts towards their registry dependents, but leave
        // independent branches and shared, otherwise-fresh leaves reusable.
        let mut reverse_dependencies = HashMap::<Unit, Vec<Unit>>::default();
        for unit in &registry_closure_units {
            if !self.reused_registry_units.contains(unit) {
                continue;
            }
            for dependency in self.unit_deps(unit) {
                if dependency
                    .unit
                    .pkg
                    .package_id()
                    .source_id()
                    .is_remote_registry()
                    || self.bcx.ws.is_member(&dependency.unit.pkg)
                {
                    reverse_dependencies
                        .entry(dependency.unit.clone())
                        .or_default()
                        .push(unit.clone());
                }
            }
        }

        let mut pending = stale_units.iter().cloned().collect::<Vec<_>>();
        while let Some(unit) = pending.pop() {
            if let Some(dependents) = reverse_dependencies.get(&unit) {
                for dependent in dependents {
                    if stale_units.insert(dependent.clone()) {
                        pending.push(dependent.clone());
                    }
                }
            }
        }

        Ok(stale_units
            .into_iter()
            .map(|unit| unit.pkg.package_id())
            .collect())
    }

    /// External backends are compiler plugins, and execute even for metadata
    /// checks. Their arbitrary ambient inputs cannot safely be fingerprinted.
    fn unit_uses_custom_codegen_backend(&self, unit: &Unit) -> bool {
        let host_sysroot = &self.bcx.target_data.info(CompileKind::Host).sysroot;
        let unit_sysroot = &self.bcx.target_data.info(unit.kind).sysroot;
        let host_triple = self.bcx.host_triple();
        if unit.profile.codegen_backend.is_some()
            || sysroot_has_external_codegen_backends(host_sysroot, host_triple.as_str())
            || (unit_sysroot != host_sysroot
                && sysroot_has_external_codegen_backends(unit_sysroot, host_triple.as_str()))
        {
            return true;
        }

        if let CompileKind::Target(target) = unit.kind {
            let CompileTarget::Tuple(target_name) = target else {
                // Custom target specifications can select an external backend
                // without adding any command-line compiler options.
                return true;
            };

            let Ok(configured_environment) = self.bcx.gctx.env_config() else {
                return true;
            };
            if configured_environment
                .get("RUST_TARGET_PATH")
                .map(std::ffi::OsString::as_os_str)
                .or_else(|| self.bcx.gctx.get_env_os("RUST_TARGET_PATH"))
                .is_some_and(|search_path| !search_path.is_empty())
            {
                // A bare target tuple can resolve to a custom specification
                // through this search path, despite looking like a built-in.
                return true;
            }

            let local_specification_name = format!("{}.json", target_name.as_str());
            if [self.bcx.gctx.cwd(), unit.pkg.root()]
                .into_iter()
                .any(|directory| {
                    !matches!(
                        directory.join(&local_specification_name).try_exists(),
                        Ok(false)
                    )
                })
            {
                // An absent or empty `RUST_TARGET_PATH` still contains one
                // current-directory search entry in rustc's target resolver.
                return true;
            }

            let target_specification = unit_sysroot
                .join("lib")
                .join("rustlib")
                .join(target_name.as_str())
                .join("target.json");
            if !matches!(target_specification.try_exists(), Ok(false)) {
                // rustc also resolves otherwise unknown tuples from the
                // selected toolchain's installed target specifications.
                return true;
            }
        }

        let extra_args = self
            .bcx
            .extra_args_for(unit)
            .map(Vec::as_slice)
            .unwrap_or_default();
        let arguments = unit
            .pkg
            .manifest()
            .lint_rustflags()
            .iter()
            .map(String::as_str)
            .chain(unit.profile.rustflags.iter().map(|flag| flag.as_str()))
            .chain(extra_args.iter().map(String::as_str))
            .chain(unit.rustflags.iter().map(String::as_str));

        compilation_files::unit_compiler_arguments_use_opaque_execution(
            unit,
            host_triple.as_str(),
            unit_sysroot,
            arguments,
        )
    }

    /// Returns whether a unit has the shape of a promotable owned or registry library.
    fn is_promotable_registry_dependency(bcx: &BuildContext<'_, '_>, unit: &Unit) -> bool {
        unit.mode == CompileMode::Build
            && (unit.pkg.package_id().source_id().is_remote_registry()
                || bcx.ws.is_member(&unit.pkg))
            && !unit.target.for_host()
            && unit.target.is_lib()
            && !unit.artifact.is_true()
            && unit
                .target
                .rustc_crate_types()
                .iter()
                .all(|crate_type| matches!(crate_type, CrateType::Lib | CrateType::Rlib))
    }

    /// Returns whether this unit actually has an incoming promoted check edge.
    pub(crate) fn is_reused_registry_dependency(&self, unit: &Unit) -> bool {
        self.reused_registry_units.contains(unit)
    }

    /// Returns whether a promoted unit has no consumer requiring object code.
    pub(crate) fn is_metadata_only_reused_registry_dependency(&self, unit: &Unit) -> bool {
        self.reused_registry_units.contains(unit)
            && !self.object_required_registry_units.contains(unit)
    }

    /// Returns the filenames that the given unit will generate.
    pub fn outputs(&self, unit: &Unit) -> CargoResult<Arc<Vec<OutputFile>>> {
        self.files.as_ref().unwrap().outputs(unit, self.bcx)
    }

    /// Direct dependencies for the given unit.
    pub fn unit_deps(&self, unit: &Unit) -> &[UnitDep] {
        &self.bcx.unit_graph[unit]
    }

    /// Returns the `RunCustomBuild` Units associated with the given Unit.
    ///
    /// If the package does not have a build script, this returns None.
    pub fn find_build_script_units(&self, unit: &Unit) -> Option<Vec<Unit>> {
        if unit.mode.is_run_custom_build() {
            return Some(vec![unit.clone()]);
        }

        let build_script_units: Vec<Unit> = self.bcx.unit_graph[unit]
            .iter()
            .filter(|unit_dep| {
                unit_dep.unit.mode.is_run_custom_build()
                    && unit_dep.unit.pkg.package_id() == unit.pkg.package_id()
            })
            .map(|unit_dep| unit_dep.unit.clone())
            .collect();
        if build_script_units.is_empty() {
            None
        } else {
            Some(build_script_units)
        }
    }

    /// Returns the metadata hash for the `RunCustomBuild` Unit associated with
    /// the given unit.
    ///
    /// If the package does not have a build script, this returns None.
    pub fn find_build_script_metadatas(&self, unit: &Unit) -> Option<Vec<UnitHash>> {
        self.find_build_script_units(unit).map(|units| {
            units
                .iter()
                .map(|u| self.get_run_build_script_metadata(u))
                .collect()
        })
    }

    /// Returns the metadata hash for a `RunCustomBuild` unit.
    pub fn get_run_build_script_metadata(&self, unit: &Unit) -> UnitHash {
        assert!(unit.mode.is_run_custom_build());
        self.files().metadata(unit).unit_id()
    }

    /// Returns the list of SBOM output file paths for a given [`Unit`].
    pub fn sbom_output_files(&self, unit: &Unit) -> CargoResult<Vec<PathBuf>> {
        Ok(self
            .outputs(unit)?
            .iter()
            .filter(|o| o.flavor == FileFlavor::Sbom)
            .map(|o| o.path.clone())
            .collect())
    }

    /// Returns the list of unremap file paths for a given [`Unit`].
    pub fn unremap_output_files(&self, unit: &Unit) -> CargoResult<Vec<PathBuf>> {
        Ok(self
            .outputs(unit)?
            .iter()
            .filter(|o| o.flavor == FileFlavor::Unremap)
            .map(|o| o.path.clone())
            .collect())
    }

    pub fn is_primary_package(&self, unit: &Unit) -> bool {
        self.primary_packages.contains(&unit.pkg.package_id())
    }

    pub fn is_terminal_check_unit(&self, unit: &Unit) -> bool {
        self.terminal_check_units.contains(unit)
    }

    /// Returns a [`UnitOutput`] which represents some information about the
    /// output of a unit.
    pub fn unit_output(&self, unit: &Unit, path: &Path) -> CargoResult<UnitOutput> {
        let script_metas = self.find_build_script_metadatas(unit);
        let env = artifact::get_env(&self, unit, self.unit_deps(unit))?;
        Ok(UnitOutput {
            unit: unit.clone(),
            path: path.to_path_buf(),
            script_metas,
            env,
        })
    }

    /// Check if any output file name collision happens.
    /// See <https://github.com/rust-lang/cargo/issues/6313> for more.
    #[tracing::instrument(skip_all)]
    fn check_collisions(&self) -> CargoResult<()> {
        let mut output_collisions = HashMap::default();
        let describe_collision = |unit: &Unit, other_unit: &Unit| -> String {
            format!(
                "the {} target `{}` in package `{}` has the same output filename as the {} target `{}` in package `{}`",
                unit.target.kind().description(),
                unit.target.name(),
                unit.pkg.package_id(),
                other_unit.target.kind().description(),
                other_unit.target.name(),
                other_unit.pkg.package_id(),
            )
        };
        let suggestion = [
            Level::NOTE.message("this may become a hard error in the future; see <https://github.com/rust-lang/cargo/issues/6313>"),
            Level::HELP.message("consider changing their names to be unique or compiling them separately")
        ];
        let rustdoc_suggestion = [
            Level::NOTE.message("this is a known bug where multiple crates with the same name use the same path; see <https://github.com/rust-lang/cargo/issues/6313>")
        ];
        let report_collision = |unit: &Unit,
                                other_unit: &Unit,
                                path: &PathBuf,
                                messages: &[Message<'_>]|
         -> CargoResult<()> {
            if unit.target.name() == other_unit.target.name() {
                self.bcx.gctx.shell().print_report(
                    &[Level::WARNING
                        .secondary_title(format!("output filename collision at {}", path.display()))
                        .elements(
                            [Level::NOTE.message(describe_collision(unit, other_unit))]
                                .into_iter()
                                .chain(messages.iter().cloned()),
                        )],
                    false,
                )
            } else {
                self.bcx.gctx.shell().print_report(
                    &[Level::WARNING
                        .secondary_title(format!("output filename collision at {}", path.display()))
                        .elements([
                            Level::NOTE.message(describe_collision(unit, other_unit)),
                            Level::NOTE.message("if this looks unexpected, it may be a bug in Cargo. Please file a bug \
                                report at https://github.com/rust-lang/cargo/issues/ with as much information as you \
                                can provide."),
                            Level::NOTE.message(format!("cargo {} running on `{}` target `{}`",
                                crate::version(), self.bcx.host_triple(), self.bcx.target_data.short_name(&unit.kind))),
                            Level::NOTE.message(format!("first unit: {unit:?}")),
                            Level::NOTE.message(format!("second unit: {other_unit:?}")),
                        ])],
                    false,
                )
            }
        };

        fn doc_collision_error(unit: &Unit, other_unit: &Unit) -> CargoResult<()> {
            bail!(
                "document output filename collision\n\
                 The {} `{}` in package `{}` has the same name as the {} `{}` in package `{}`.\n\
                 Only one may be documented at once since they output to the same path.\n\
                 Consider documenting only one, renaming one, \
                 or marking one with `doc = false` in Cargo.toml.",
                unit.target.kind().description(),
                unit.target.name(),
                unit.pkg,
                other_unit.target.kind().description(),
                other_unit.target.name(),
                other_unit.pkg,
            );
        }

        let mut keys = self
            .bcx
            .unit_graph
            .keys()
            .filter(|unit| !unit.mode.is_run_custom_build())
            .collect::<Vec<_>>();
        // Sort for consistent error messages.
        keys.sort_unstable();
        // These are kept separate to retain compatibility with older
        // versions, which generated an error when there was a duplicate lib
        // or bin (but the old code did not check bin<->lib collisions). To
        // retain backwards compatibility, this only generates an error for
        // duplicate libs or duplicate bins (but not both). Ideally this
        // shouldn't be here, but since there isn't a complete workaround,
        // yet, this retains the old behavior.
        let mut doc_libs = HashMap::default();
        let mut doc_bins = HashMap::default();
        for unit in keys {
            if unit.mode.is_doc() && self.is_primary_package(unit) {
                // These situations have been an error since before 1.0, so it
                // is not a warning like the other situations.
                if unit.target.is_lib() {
                    if let Some(prev) = doc_libs.insert((unit.target.crate_name(), unit.kind), unit)
                    {
                        doc_collision_error(unit, prev)?;
                    }
                } else if let Some(prev) =
                    doc_bins.insert((unit.target.crate_name(), unit.kind), unit)
                {
                    doc_collision_error(unit, prev)?;
                }
            }
            for output in self.outputs(unit)?.iter() {
                if let Some(other_unit) = output_collisions.insert(output.path.clone(), unit) {
                    if unit.mode.is_doc() {
                        // See https://github.com/rust-lang/rust/issues/56169
                        // and https://github.com/rust-lang/rust/issues/61378
                        report_collision(unit, other_unit, &output.path, &rustdoc_suggestion)?;
                    } else {
                        report_collision(unit, other_unit, &output.path, &suggestion)?;
                    }
                }
                if let Some(hardlink) = output.hardlink.as_ref() {
                    if let Some(other_unit) = output_collisions.insert(hardlink.clone(), unit) {
                        report_collision(unit, other_unit, hardlink, &suggestion)?;
                    }
                }
                if let Some(ref export_path) = output.export_path {
                    if let Some(other_unit) = output_collisions.insert(export_path.clone(), unit) {
                        self.bcx.gctx.shell().print_report(
                            &[Level::WARNING
                                .secondary_title(format!(
                                    "`--artifact-dir` filename collision at {}",
                                    export_path.display()
                                ))
                                .elements(
                                    [Level::NOTE.message(describe_collision(unit, other_unit))]
                                        .into_iter()
                                        .chain(suggestion.iter().cloned()),
                                )],
                            false,
                        )?;
                    }
                }
            }
        }
        Ok(())
    }

    /// Records the list of units which are required to emit metadata.
    ///
    /// Units which depend only on the metadata of others requires the others to
    /// actually produce metadata, so we'll record that here.
    fn record_units_requiring_metadata(&mut self) {
        for (key, deps) in self.bcx.unit_graph.iter() {
            for dep in deps {
                if self.only_requires_rmeta(key, &dep.unit) {
                    self.rmeta_required.insert(dep.unit.clone());
                }
            }
        }
    }

    /// Returns whether when `parent` depends on `dep` if it only requires the
    /// metadata file from `dep`.
    pub fn only_requires_rmeta(&self, parent: &Unit, dep: &Unit) -> bool {
        if parent.mode.is_check()
            && self.is_reused_registry_dependency(dep)
            && !dep.requires_upstream_objects()
        {
            return true;
        }

        if parent.mode.is_check()
            && dep.mode.is_check()
            && fingerprint::unit_can_use_early_cutoff(self, parent)
            && fingerprint::unit_can_use_early_cutoff(self, dep)
        {
            return true;
        }

        // We're only a candidate for requiring an `rmeta` file if we
        // ourselves are building an rlib,
        !parent.requires_upstream_objects()
            && parent.mode == CompileMode::Build
            // Our dependency must also be built as an rlib, otherwise the
            // object code must be useful in some fashion
            && !dep.requires_upstream_objects()
            && dep.mode == CompileMode::Build
    }

    /// Returns whether when `unit` is built whether it should emit metadata as
    /// well because some compilations rely on that.
    pub fn rmeta_required(&self, unit: &Unit) -> bool {
        self.rmeta_required.contains(unit)
    }

    /// Finds metadata for Doc/Docscrape units.
    ///
    /// rustdoc needs a -Cmetadata flag in order to recognize StableCrateIds that refer to
    /// items in the crate being documented. The -Cmetadata flag used by reverse-dependencies
    /// will be the metadata of the Cargo unit that generated the current library's rmeta file,
    /// which should be a Check unit.
    ///
    /// If the current crate has reverse-dependencies, such a Check unit should exist, and so
    /// we use that crate's metadata. If not, we use the crate's Doc unit so at least examples
    /// scraped from the current crate can be used when documenting the current crate.
    #[tracing::instrument(skip_all)]
    pub fn compute_metadata_for_doc_units(&mut self) {
        for unit in self.bcx.unit_graph.keys() {
            if !unit.mode.is_doc() && !unit.mode.is_doc_scrape() {
                continue;
            }

            let matching_units = self
                .bcx
                .unit_graph
                .keys()
                .filter(|other| {
                    unit.pkg == other.pkg
                        && unit.target == other.target
                        && !other.mode.is_doc_scrape()
                })
                .collect::<Vec<_>>();
            let metadata_unit = matching_units
                .iter()
                .find(|other| other.mode.is_check())
                .or_else(|| matching_units.iter().find(|other| other.mode.is_doc()))
                .unwrap_or(&unit);
            self.metadata_for_doc_units
                .insert(unit.clone(), self.files().metadata(metadata_unit));
        }
    }
}

#[cfg(test)]
mod tests {
    use cargo_util::ProcessBuilder;

    use super::{
        configured_compiler_environment_has_case_alias, effective_compiler_environment,
        is_sensitive_compiler_environment, sysroot_has_external_codegen_backends,
    };

    #[test]
    fn detects_opaque_default_codegen_backend_directories() {
        let sysroot = tempfile::tempdir().expect("create isolated compiler sysroot");
        let host = "test-host";

        assert!(!sysroot_has_external_codegen_backends(sysroot.path(), host));

        std::fs::create_dir_all(
            sysroot
                .path()
                .join("lib")
                .join("rustlib")
                .join(host)
                .join("codegen-backends"),
        )
        .expect("create external backend directory");

        assert!(sysroot_has_external_codegen_backends(sysroot.path(), host));
    }

    #[test]
    fn recognizes_windows_sensitive_environment_aliases_without_changing_unix() {
        for name in [
            "pAtH",
            "rUsTc_BoOtStRaP",
            "rustc_override_version_string",
            "dYlD_iNsErT_lIbRaRiEs",
            "lD_lIbRaRy_PaTh",
            "rUsTc_LoG_oUtPuT_tArGeT",
        ] {
            assert!(is_sensitive_compiler_environment(name, true));
            assert!(!is_sensitive_compiler_environment(name, false));
        }

        assert!(is_sensitive_compiler_environment("RUSTC_BOOTSTRAP", false));
        assert!(is_sensitive_compiler_environment("RUSTC_LOG", false));
        assert!(is_sensitive_compiler_environment(
            "RUSTC_LOG_OUTPUT_TARGET",
            false
        ));
        assert!(!is_sensitive_compiler_environment("UNRELATED_POLICY", true));
    }

    #[test]
    fn captures_windows_compiler_environment_alias_using_actual_process_order() {
        let mut compiler = ProcessBuilder::new("rustc");
        compiler.env("RUSTC_OVERRIDE_VERSION_STRING", "1.50.0");
        compiler.env("rustc_override_version_string", "1.99.0");

        assert_eq!(
            effective_compiler_environment(&compiler, "RUSTC_OVERRIDE_VERSION_STRING", true),
            Some("1.99.0".into())
        );
        assert_eq!(
            effective_compiler_environment(&compiler, "RUSTC_OVERRIDE_VERSION_STRING", false),
            Some("1.50.0".into())
        );
    }

    #[test]
    fn rejects_windows_sensitive_config_aliases_without_changing_unix() {
        let configured_environment = [
            ("Path".to_owned(), "opaque-linker-directory".into()),
            ("rustc_override_version_string".to_owned(), "1.99.0".into()),
            ("Cargo_Manifest_Dir".to_owned(), "opaque-workspace".into()),
        ]
        .into_iter()
        .collect();

        assert!(configured_compiler_environment_has_case_alias(
            &configured_environment,
            true
        ));
        assert!(!configured_compiler_environment_has_case_alias(
            &configured_environment,
            false
        ));

        let canonical_environment = [
            ("PATH".to_owned(), "trusted-linker-directory".into()),
            ("RUSTC_OVERRIDE_VERSION_STRING".to_owned(), "1.99.0".into()),
        ]
        .into_iter()
        .collect();

        assert!(!configured_compiler_environment_has_case_alias(
            &canonical_environment,
            true
        ));
    }
}
