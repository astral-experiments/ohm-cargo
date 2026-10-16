//! See [`CompilationFiles`].

use crate::util::data_structures::{HashMap, HashSet};
use std::cell::OnceCell;
use std::ffi::{OsStr, OsString};
use std::fmt;
use std::hash::{Hash, Hasher};
#[cfg(unix)]
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::SystemTime;

use cargo_platform::CfgExpr;
use cargo_util::paths;
use tracing::debug;

use super::{BuildContext, BuildRunner, CompileKind, FileFlavor, Layout};
use crate::compiler::custom_build::OHM_SHARED_RUSTC_LOG_ENVIRONMENT;
use crate::compiler::trim_paths;
use crate::compiler::{CompileMode, CompileTarget, CrateType, FileType, Unit, UserIntent};
use crate::util::{self, CargoResult, OnceExt, StableHasher};
use crate::workspace::features::{OhmNativeToolTrust, OhmProcMacroTrust};
use crate::workspace::profiles::StripInner;
use crate::workspace::{Target, TargetKind, Workspace};

/// This is a generic version number that can be changed to make
/// backwards-incompatible changes to any file structures in the output
/// directory. For example, the fingerprint files or the build-script
/// output files.
///
/// Normally cargo updates ship with rustc updates which will
/// cause a new hash due to the rustc version changing, but this allows
/// cargo to be extra careful to deal with different versions of cargo that
/// use the same rustc version.
const METADATA_VERSION: u8 = 2;

/// Uniquely identify a [`Unit`] under specific circumstances, see [`Metadata`] for more.
#[derive(Copy, Clone, Hash, Eq, PartialEq, Ord, PartialOrd)]
pub struct UnitHash(u64);

impl fmt::Display for UnitHash {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:016x}", self.0)
    }
}

impl fmt::Debug for UnitHash {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "UnitHash({:016x})", self.0)
    }
}

/// [`Metadata`] tracks several [`UnitHash`]s, including
/// [`Metadata::unit_id`], [`Metadata::c_metadata`], and [`Metadata::c_extra_filename`].
///
/// We use a hash because it is an easy way to guarantee
/// that all the inputs can be converted to a valid path.
///
/// [`Metadata::unit_id`] is used to uniquely identify a unit in the build graph.
/// This serves as a similar role as [`Metadata::c_extra_filename`] in that it uniquely identifies output
/// on the filesystem except that its always present.
///
/// [`Metadata::c_extra_filename`] is needed for cases like:
/// - A project may depend on crate `A` and crate `B`, so the package name must be in the file name.
/// - Similarly a project may depend on two versions of `A`, so the version must be in the file name.
///
/// This also acts as the main layer of caching provided by Cargo
/// so this must include all things that need to be distinguished in different parts of
/// the same build. This is absolutely required or we override things before
/// we get chance to use them.
///
/// For example, we want to cache `cargo build` and `cargo doc` separately, so that running one
/// does not invalidate the artifacts for the other. We do this by including [`CompileMode`] in the
/// hash, thus the artifacts go in different folders and do not override each other.
/// If we don't add something that we should have, for this reason, we get the
/// correct output but rebuild more than is needed.
///
/// Some things that need to be tracked to ensure the correct output should definitely *not*
/// go in the `Metadata`. For example, the modification time of a file, should be tracked to make a
/// rebuild when the file changes. However, it would be wasteful to include in the `Metadata`. The
/// old artifacts are never going to be needed again. We can save space by just overwriting them.
/// If we add something that we should not have, for this reason, we get the correct output but take
/// more space than needed. This makes not including something in `Metadata`
/// a form of cache invalidation.
///
/// Note that the `Fingerprint` is in charge of tracking everything needed to determine if a
/// rebuild is needed.
///
/// [`Metadata::c_metadata`] is used for symbol mangling, because if you have two versions of
/// the same crate linked together, their symbols need to be differentiated.
///
/// You should avoid anything that would interfere with reproducible
/// builds. For example, *any* absolute path should be avoided. This is one
/// reason that `RUSTFLAGS` is not in [`Metadata::c_metadata`], because it often has
/// absolute paths (like `--remap-path-prefix` which is fundamentally used for
/// reproducible builds and has absolute paths in it). Also, in some cases the
/// mangled symbols need to be stable between different builds with different
/// settings. For example, profile-guided optimizations need to swap
/// `RUSTFLAGS` between runs, but needs to keep the same symbol names.
#[derive(Copy, Clone, Debug)]
pub struct Metadata {
    unit_id: UnitHash,
    c_metadata: UnitHash,
    c_extra_filename: bool,
    pkg_dir: bool,
}

impl Metadata {
    /// A hash to identify a given [`Unit`] in the build graph
    pub fn unit_id(&self) -> UnitHash {
        self.unit_id
    }

    /// A hash to add to symbol naming through `-C metadata`
    pub fn c_metadata(&self) -> UnitHash {
        self.c_metadata
    }

    /// A hash to add to file names through `-C extra-filename`
    pub fn c_extra_filename(&self) -> Option<UnitHash> {
        self.c_extra_filename.then_some(self.unit_id)
    }

    /// A hash to add to Cargo directory names
    pub fn pkg_dir(&self) -> Option<UnitHash> {
        self.pkg_dir.then_some(self.unit_id)
    }
}

/// Collection of information about the files emitted by the compiler, and the
/// output directory structure.
pub struct CompilationFiles<'a, 'gctx> {
    /// The target directory layout for the host (and target if it is the same as host).
    pub(super) host: Layout,
    /// The target directory layout for the target (if different from then host).
    pub(super) target: HashMap<CompileTarget, Layout>,
    /// Additional directory to include a copy of the outputs.
    export_dir: Option<PathBuf>,
    /// The root targets requested by the user on the command line (does not
    /// include dependencies).
    roots: Vec<Unit>,
    ws: &'a Workspace<'gctx>,
    /// Namespace immutable registry artifacts separately from workspace-local units.
    shared_registry_cache: Option<SharedRegistryCache>,
    /// Metadata hash to use for each unit.
    metas: HashMap<Unit, Metadata>,
    /// For each Unit, a list all files produced.
    outputs: HashMap<Unit, OnceCell<Arc<Vec<OutputFile>>>>,
}

/// Separates verified immutable registry artifacts from workspace-private compiler outputs.
struct SharedRegistryCache {
    workspace: String,
    /// Keeps known Clippy invocations from changing ordinary artifact seed policy.
    isolated_clippy: bool,
    /// Includes the compiler and every stable Cargo-provided build-script input.
    rustc: String,
    /// Canonical implementation dynamically loaded by the verified compiler launcher.
    compiler_driver: Option<PathBuf>,
    /// Whether compiler execution satisfies the shared cache's ambient-input checks.
    trusted_context: bool,
    #[cfg(windows)]
    implicit_native_tools: Vec<String>,
    immutable_units: HashMap<Unit, bool>,
}

/// The compiler implementation is a dynamic library, not its small executable launcher.
#[derive(Debug, Eq, Hash, PartialEq)]
struct CompilerDriverIdentity {
    path: PathBuf,
    length: u64,
    modified: SystemTime,
    #[cfg(unix)]
    device: u64,
    #[cfg(unix)]
    inode: u64,
    #[cfg(unix)]
    changed: i64,
    #[cfg(unix)]
    changed_nanoseconds: i64,
    #[cfg(not(unix))]
    created: Option<SystemTime>,
}

/// Info about a single file emitted by the compiler.
#[derive(Debug)]
pub struct OutputFile {
    /// Absolute path to the file that will be produced by the build process.
    pub path: PathBuf,
    /// If it should be linked into `target`, and what it should be called
    /// (e.g., without metadata).
    pub hardlink: Option<PathBuf>,
    /// If `--artifact-dir` is specified, the absolute path to the exported file.
    pub export_path: Option<PathBuf>,
    /// Type of the file (library / debug symbol / else).
    pub flavor: FileFlavor,
}

impl OutputFile {
    /// Gets the hard link if present; otherwise, returns the path.
    pub fn bin_dst(&self) -> &PathBuf {
        match self.hardlink {
            Some(ref link_dst) => link_dst,
            None => &self.path,
        }
    }
}

impl<'a, 'gctx: 'a> CompilationFiles<'a, 'gctx> {
    pub(super) fn new(
        build_runner: &BuildRunner<'a, 'gctx>,
        host: Layout,
        target: HashMap<CompileTarget, Layout>,
    ) -> CompilationFiles<'a, 'gctx> {
        let mut metas = HashMap::default();
        for unit in build_runner
            .bcx
            .roots
            .iter()
            .chain(build_runner.bcx.test_check_candidates.values())
        {
            metadata_of(unit, build_runner, &mut metas);
        }
        let outputs = metas
            .keys()
            .cloned()
            .map(|unit| (unit, OnceCell::new()))
            .collect();
        let shared_registry_cache = if build_runner.bcx.ws.shared_registry_cache_enabled() {
            Some({
                let context = build_runner.bcx.gctx;
                let compiler = build_runner.bcx.rustc();
                let rustdoc = context.rustdoc().ok().map(Path::to_path_buf);
                let cargo = context.cargo_exe().ok().map(Path::to_path_buf);
                let configured_environment = context.env_config().ok().map(|variables| {
                    let mut variables = variables
                        .iter()
                        .map(|(name, value)| (name.clone(), value.clone()))
                        .collect::<Vec<_>>();
                    variables.sort_unstable_by(|left, right| left.0.cmp(&right.0));
                    variables
                });
                let effective_environment = |name: &str| {
                    // Cargo synthesizes this variable itself from the inherited environment.
                    // `apply_env_config` deliberately does not override Cargo-provided values,
                    // so a forced `[env]` entry does not affect the actual compiler process.
                    if name == paths::dylib_path_envvar() {
                        return context.get_env_os(name).map(OsStr::to_os_string);
                    }

                    configured_environment
                        .as_ref()
                        .and_then(|variables| {
                            variables
                                .iter()
                                .find(|(configured_name, _)| configured_name == name)
                                .map(|(_, value)| value.clone())
                        })
                        .or_else(|| context.get_env_os(name).map(OsStr::to_os_string))
                };
                let native_environment = [
                    "PATH",
                    "SDKROOT",
                    "DEVELOPER_DIR",
                    "DYLD_LIBRARY_PATH",
                    "DYLD_FALLBACK_LIBRARY_PATH",
                    "DYLD_FRAMEWORK_PATH",
                    "DYLD_FALLBACK_FRAMEWORK_PATH",
                    "DYLD_VERSIONED_LIBRARY_PATH",
                    "DYLD_VERSIONED_FRAMEWORK_PATH",
                    "DYLD_IMAGE_SUFFIX",
                    "DYLD_ROOT_PATH",
                    "DYLD_FORCE_FLAT_NAMESPACE",
                    "LD_LIBRARY_PATH",
                    "LIBPATH",
                    "SHLIB_PATH",
                    "LIBRARY_PATH",
                    "COMPILER_PATH",
                    "GCC_EXEC_PREFIX",
                    "CPATH",
                    "C_INCLUDE_PATH",
                    "CPLUS_INCLUDE_PATH",
                    "OBJC_INCLUDE_PATH",
                ]
                .into_iter()
                .map(|name| (name, effective_environment(name)))
                .collect::<Vec<_>>();
                let effective_executable_path = effective_environment("PATH");
                let rustup_environment = ["RUSTUP_HOME", "RUSTUP_TOOLCHAIN"]
                    .map(|name| (name, context.get_env_os(name).map(OsStr::to_os_string)));
                let mut native_tool_names = Vec::new();
                for tool in [
                    "CC",
                    "CXX",
                    "AR",
                    "RANLIB",
                    "NVCC",
                    "CMAKE",
                    "EMCMAKE",
                    "EMMAKE",
                    "PKG_CONFIG",
                    "PERL",
                    "OPENSSL_SRC_PERL",
                ] {
                    append_native_environment_names(&mut native_tool_names, tool, build_runner);
                }
                native_tool_names.sort_unstable();
                native_tool_names.dedup();
                let native_tools = native_tool_names
                    .into_iter()
                    .map(|name| {
                        let value = effective_environment(&name);
                        (name, value)
                    })
                    .collect::<Vec<_>>();
                let opaque_native_selector = ["CROSS_COMPILE", "CMAKE_TOOLCHAIN_FILE"]
                    .into_iter()
                    .any(|selector| {
                        let mut names = Vec::new();
                        append_native_environment_names(&mut names, selector, build_runner);
                        names.into_iter().any(|name| {
                            effective_environment(&name).is_some_and(|value| !value.is_empty())
                        })
                    });
                let verified_environment_spelling =
                    configured_environment.as_ref().is_some_and(|configured| {
                        !configured_environment_has_sensitive_case_alias(configured, cfg!(windows))
                    });
                let compiler_file_identity = resolve_effective_executable(
                    &compiler.path,
                    effective_executable_path.as_deref(),
                )
                .ok()
                .flatten()
                .and_then(|path| path.canonicalize().ok())
                .and_then(|path| std::fs::metadata(path).ok())
                .and_then(|metadata| {
                    let modified = metadata.modified().ok()?;

                    #[cfg(unix)]
                    {
                        Some((
                            metadata.len(),
                            modified,
                            metadata.dev(),
                            metadata.ino(),
                            metadata.ctime(),
                            metadata.ctime_nsec(),
                        ))
                    }

                    #[cfg(not(unix))]
                    {
                        Some((metadata.len(), modified, metadata.created().ok()))
                    }
                });
                let compiler_driver_identity = compiler_driver_identity_for_sysroot(
                    &build_runner.bcx.target_data.info(CompileKind::Host).sysroot,
                );
                let verified_compiler_driver =
                    compiler_driver_identity.as_ref().is_some_and(|driver| {
                        super::OHM_COMPILER_LOADER_ENVIRONMENT
                            .iter()
                            .copied()
                            .filter(|name| {
                                !super::OHM_COMPILER_LOADER_INJECTION_ENVIRONMENT.contains(name)
                            })
                            .chain(["LIBPATH", "SHLIB_PATH", paths::dylib_path_envvar()])
                            .all(|name| {
                                effective_environment(name).is_none_or(|search_path| {
                                    std::env::split_paths(&search_path).all(|directory| {
                                        directory.is_absolute()
                                            && compiler_driver_search_directory_is_safe(
                                                &directory,
                                                &driver.path,
                                            )
                                    })
                                })
                            })
                    });
                let injected_loader = super::OHM_COMPILER_LOADER_INJECTION_ENVIRONMENT
                    .iter()
                    .any(|name| effective_environment(name).is_some_and(|value| !value.is_empty()));
                let configured_compiler_logger = OHM_SHARED_RUSTC_LOG_ENVIRONMENT
                    .iter()
                    .any(|name| effective_environment(name).is_some());
                let mut linkers = build_runner
                    .bcx
                    .all_kinds
                    .iter()
                    .map(|kind| {
                        (
                            kind.is_host(),
                            build_runner.bcx.target_data.short_name(kind).to_owned(),
                            build_runner
                                .compilation
                                .target_linker(*kind)
                                .map(Path::to_path_buf),
                        )
                    })
                    .collect::<Vec<_>>();
                linkers.sort_unstable();
                let host_linker = build_runner
                    .compilation
                    .host_linker()
                    .map(Path::to_path_buf);
                let verified_linkers = linkers
                    .iter()
                    .filter_map(|(_, _, linker)| linker.as_deref())
                    .chain(host_linker.as_deref())
                    .all(|linker| {
                        linker_has_verified_toolchain_identity(
                            linker,
                            build_runner,
                            effective_executable_path.as_deref(),
                        )
                    });
                let universal_implicit_native_tools = [
                    "cc", "c++", "gcc", "g++", "clang", "clang++", "ar", "ranlib", "perl", "xcrun",
                ];
                let compilation_targets = build_runner
                    .bcx
                    .all_kinds
                    .iter()
                    .map(|kind| build_runner.bcx.target_data.short_name(kind).to_owned())
                    .collect::<Vec<_>>();
                let mut package_native_tools = HashMap::default();
                for unit in metas.keys() {
                    let package = unit.pkg.package_id().name().as_str();
                    if package_native_tools.contains_key(package) {
                        continue;
                    }
                    let tools = package_implicit_native_tools(package, &compilation_targets);
                    if !tools.is_empty() {
                        package_native_tools.insert(package.to_owned(), tools);
                    }
                }
                let mut implicit_native_tools = universal_implicit_native_tools
                    .iter()
                    .map(|tool| (*tool).to_owned())
                    .chain(package_native_tools.values().flatten().cloned())
                    .collect::<Vec<_>>();
                implicit_native_tools.sort_unstable();
                implicit_native_tools.dedup();
                let implicit_native_tool_is_verified =
                    |tool: &str| match resolve_effective_executable(
                        Path::new(tool),
                        effective_executable_path.as_deref(),
                    ) {
                        Ok(Some(executable)) => linker_has_verified_toolchain_identity(
                            &executable,
                            build_runner,
                            effective_executable_path.as_deref(),
                        ),
                        Ok(None) => true,
                        Err(_) => false,
                    };
                let verified_implicit_native_tools = universal_implicit_native_tools
                    .iter()
                    .all(|tool| implicit_native_tool_is_verified(tool));
                let untrusted_native_tool_packages = package_native_tools
                    .iter()
                    .filter(|(_, tools)| {
                        !tools
                            .iter()
                            .all(|tool| implicit_native_tool_is_verified(tool))
                    })
                    .map(|(package, _)| package.clone())
                    .collect::<HashSet<_>>();
                let verified_native_tools = native_tools.iter().all(|(_, value)| {
                    value.as_deref().is_none_or(|tool| {
                        tool.is_empty()
                            || linker_has_verified_toolchain_identity(
                                Path::new(tool),
                                build_runner,
                                effective_executable_path.as_deref(),
                            )
                    })
                }) && verified_implicit_native_tools
                    && effective_environment("CC_KNOWN_WRAPPER_CUSTOM")
                        .is_none_or(|wrapper| wrapper.is_empty())
                    && !opaque_native_selector;
                let verified_rustdoc = rustdoc.as_deref().is_some_and(|rustdoc| {
                    rustdoc_has_verified_toolchain_identity(
                        rustdoc,
                        build_runner,
                        effective_executable_path.as_deref(),
                    )
                });
                let effective_bootstrap = effective_environment("RUSTC_BOOTSTRAP");
                let effective_compiler_version =
                    effective_environment("RUSTC_OVERRIDE_VERSION_STRING");
                let apple_deployment_targets = [
                    "MACOSX_DEPLOYMENT_TARGET",
                    "IPHONEOS_DEPLOYMENT_TARGET",
                    "WATCHOS_DEPLOYMENT_TARGET",
                    "TVOS_DEPLOYMENT_TARGET",
                    "XROS_DEPLOYMENT_TARGET",
                ]
                .into_iter()
                .map(|name| (name, effective_environment(name)))
                .collect::<Vec<_>>();
                let target_applies_to_host = context.target_applies_to_host().ok();
                let effective_host_runner = if target_applies_to_host == Some(false) {
                    let configured_runner = build_runner
                        .bcx
                        .target_data
                        .target_config(CompileKind::Host)
                        .runner
                        .as_ref()
                        .map(|runner| &runner.val)
                        .or_else(|| {
                            context.target_cfgs().ok().and_then(|configurations| {
                                let host_configuration =
                                    build_runner.bcx.target_data.info(CompileKind::Host).cfg();
                                configurations
                                    .iter()
                                    .find_map(|(condition, configuration)| {
                                        CfgExpr::matches_key(condition, host_configuration)
                                            .then_some(configuration.runner.as_ref())
                                            .flatten()
                                            .map(|runner| &runner.val)
                                    })
                            })
                        });
                    configured_runner.map(|runner| {
                        (
                            runner.path.clone().resolve_program(context),
                            runner.args.clone(),
                            effective_executable_path.clone(),
                        )
                    })
                } else {
                    None
                };
                let trusted_context = compiler.wrapper.is_none()
                    && compiler_has_verified_toolchain_identity(
                        build_runner,
                        effective_executable_path.as_deref(),
                    )
                    && verified_linkers
                    && verified_native_tools
                    && verified_rustdoc
                    && effective_host_runner.is_none()
                    && !injected_loader
                    && !configured_compiler_logger
                    && compiler_file_identity.is_some()
                    && verified_compiler_driver
                    && cargo.is_some()
                    && verified_environment_spelling
                    && target_applies_to_host.is_some();
                let mut immutable_units = HashMap::default();
                if trusted_context {
                    let mut eligibility = HashMap::default();
                    let mut custom_codegen_backends = HashMap::default();
                    for unit in metas.keys() {
                        immutable_units.insert(
                            unit.clone(),
                            is_immutable_registry_unit(
                                unit,
                                build_runner,
                                false,
                                false,
                                &untrusted_native_tool_packages,
                                &mut eligibility,
                                &mut custom_codegen_backends,
                            ),
                        );
                    }
                }
                let rustc = util::short_hash(&(
                    "ohm-ordered-shared-unit-locks-v2",
                    (
                        &compiler.verbose_version,
                        &compiler.path,
                        &compiler_file_identity,
                        &compiler_driver_identity,
                    ),
                    (&rustdoc, &cargo, &rustup_environment),
                    context.home().as_path_unlocked(),
                    build_runner.bcx.jobs(),
                    (&linkers, &host_linker),
                    &configured_environment,
                    (&native_environment, &native_tools),
                    (
                        &effective_bootstrap,
                        &effective_compiler_version,
                        context.cli_unstable().host_config,
                        &target_applies_to_host,
                        &effective_host_runner,
                        &apple_deployment_targets,
                        context.extra_verbose(),
                    ),
                ));
                // Registry trust is established after unit identities are computed. Partition
                // this compiler namespace before changing the effective registry hash policy
                // so earlier hashed artifacts can never alias the new unhashed metadata.
                let rustc = if context.cli_unstable().ohm_defaults() {
                    util::short_hash(&(rustc, "ohm-immutable-registry-public-api-hash-v1"))
                } else {
                    rustc
                };
                let rustc = if context.cli_unstable().ohm_proc_macro_trust == OhmProcMacroTrust::All
                {
                    format!("{rustc}-all")
                } else {
                    rustc
                };
                let rustc = match context.cli_unstable().ohm_native_tool_trust {
                    OhmNativeToolTrust::Strict => rustc,
                    OhmNativeToolTrust::BuildScripts => format!("{rustc}-native-build-scripts"),
                    OhmNativeToolTrust::All => format!("{rustc}-native-all"),
                };

                let isolated_clippy = trusted_context
                    && matches!(
                        build_runner.bcx.build_config.intent,
                        UserIntent::Check { .. }
                    )
                    && context
                        .cli_unstable()
                        .ohm_clippy_seed_isolation
                        .unwrap_or_else(|| context.cli_unstable().ohm_worktree_seeds())
                    && compiler.has_bundled_clippy_wrapper(
                        context,
                        &build_runner.bcx.target_data.info(CompileKind::Host).sysroot,
                    )
                    && context
                        .cli_unstable()
                        .ohm_clippy_seed_isolation
                        .unwrap_or_else(|| {
                            std::iter::once(&host).chain(target.values()).all(|layout| {
                                let workspaces = layout.build_dir().build().join("workspaces");
                                let namespace =
                                    Layout::shared_workspace_namespace(build_runner.bcx.ws);
                                let incremental = layout.build_dir().incremental();
                                // Probe this target's filesystem. Importing also verifies that
                                // the recipient's target supports cloning from this donor.
                                util::file_clone::supported_between(
                                    &workspaces.join(namespace),
                                    &workspaces,
                                ) && util::file_clone::supported_between(
                                    incremental,
                                    incremental.parent().unwrap(),
                                )
                            })
                        });
                let mut workspace = Layout::shared_workspace_namespace(build_runner.bcx.ws);
                if isolated_clippy {
                    workspace.push('/');
                    workspace.push_str(crate::compiler::OHM_WORKTREE_CLIPPY_DIRECTORY);
                }
                SharedRegistryCache {
                    workspace,
                    isolated_clippy,
                    rustc,
                    compiler_driver: compiler_driver_identity.map(|driver| driver.path),
                    trusted_context,
                    #[cfg(windows)]
                    implicit_native_tools,
                    immutable_units,
                }
            })
        } else {
            None
        };
        let mut files = CompilationFiles {
            ws: build_runner.bcx.ws,
            host,
            target,
            export_dir: build_runner.bcx.build_config.export_dir.clone(),
            roots: build_runner.bcx.roots.clone(),
            shared_registry_cache,
            metas,
            outputs,
        };

        if !files.shared_cache_compiler_directories_are_safe(build_runner)
            && let Some(cache) = files.shared_registry_cache.as_mut()
        {
            cache.immutable_units.clear();
            cache.trusted_context = false;
            cache.isolated_clippy = false;
            cache.workspace = Layout::shared_workspace_namespace(build_runner.bcx.ws);
        }

        files
    }

    /// Records the admission policy before any selected compiler can create outputs.
    ///
    /// A profile can retain units from older graphs, so opaque inputs permanently
    /// taint the whole private namespace. Authenticated Clippy uses an excluded
    /// child namespace, so its denial cannot taint ordinary build outputs.
    /// Local macros are recorded independently of the current trust setting: only the eventual import decides whether to
    /// trust their cached outputs. Deleting a macro cannot erase that history.
    pub(super) fn record_worktree_seed_policy(
        &self,
        build_runner: &BuildRunner<'_, '_>,
    ) -> CargoResult<()> {
        let prepared = self.ws.gctx().cli_unstable().ohm_worktree_seeds();
        let Some(cache) = &self.shared_registry_cache else {
            return Ok(());
        };
        if !prepared {
            let mut previously_prepared = false;
            for layout in std::iter::once(&self.host).chain(self.target.values()) {
                previously_prepared |= layout
                    .build_dir()
                    .build()
                    .join("workspaces")
                    .join(&cache.workspace)
                    .join(crate::compiler::OHM_WORKTREE_SEED_MARKER)
                    .try_exists()?;
            }
            if !previously_prepared {
                return Ok(());
            }
        }
        let local_proc_macro = self
            .metas
            .keys()
            .any(|unit| unit.target.proc_macro() && unit.pkg.package_id().source_id().is_path());
        let mut custom_codegen_backends = HashMap::default();
        let denied = !cache.trusted_context
            || build_runner.bcx.rustc().workspace_wrapper.is_some()
            || self.metas.keys().any(|unit| {
                (unit.target.proc_macro()
                    && !unit.pkg.package_id().source_id().is_path()
                    && !self.is_shared_registry_unit(unit))
                    || unit_uses_custom_codegen_backend(
                        unit,
                        build_runner,
                        &mut custom_codegen_backends,
                    )
            });
        if !prepared && !denied && !local_proc_macro {
            return Ok(());
        }
        let mut namespaces = HashSet::default();
        for unit in self.metas.keys() {
            if self.is_shared_registry_unit(unit) {
                continue;
            }
            let namespace = self
                .layout(unit.kind)
                .build_dir()
                .build()
                .join("workspaces")
                .join(&cache.workspace);
            if !namespaces.insert(namespace.clone()) {
                continue;
            }
            let marker = namespace.join(crate::compiler::OHM_WORKTREE_SEED_MARKER);
            // Once prepared, the namespace can retain outputs from ordinary
            // invocations too. Temporarily disabling the mode cannot make an
            // opaque compilation disappear from its history.
            if !prepared && !marker.try_exists()? {
                continue;
            }
            paths::create_dir_all(&namespace)?;
            if denied {
                paths::write_atomic(
                    &namespace.join(crate::compiler::OHM_WORKTREE_SEED_DENY_MARKER),
                    b"untrusted compile-time inputs\n",
                )?;
            }
            if local_proc_macro {
                paths::write_atomic(
                    &namespace.join(crate::compiler::OHM_WORKTREE_SEED_LOCAL_PROC_MACRO_MARKER),
                    b"local procedural-macro outputs require trust at import time\n",
                )?;
            }
            if prepared {
                paths::write_atomic(&marker, b"7\n")?;
            }
        }
        Ok(())
    }

    /// Checks generated loader paths before selecting shared outputs and again under their leases.
    ///
    /// `Compilation::fill_env` adds generated dependency paths before the inherited loader
    /// paths. Derive them from the layouts because `prepare` has not populated `deps_output`.
    pub(super) fn shared_cache_compiler_directories_are_safe(
        &self,
        _build_runner: &BuildRunner<'_, '_>,
    ) -> bool {
        if let Some(driver) = self
            .shared_registry_cache
            .as_ref()
            .filter(|cache| cache.immutable_units.values().any(|immutable| *immutable))
            .and_then(|cache| cache.compiler_driver.as_deref())
        {
            let mut directories = HashSet::default();
            return self
                .metas
                .keys()
                .flat_map(|unit| {
                    #[cfg(windows)]
                    let root = self
                        .layout(unit.kind)
                        .artifact_dir()
                        .map(|layout| layout.dest().to_path_buf());
                    #[cfg(not(windows))]
                    let root = None;
                    #[cfg(windows)]
                    let build_script = (unit.target.is_custom_build()
                        && !unit.mode.is_run_custom_build())
                    .then(|| self.build_script_dir(unit));
                    #[cfg(not(windows))]
                    let build_script = None;

                    [self.host_deps(unit), self.deps_dir(unit)]
                        .into_iter()
                        .chain(root)
                        .chain(build_script)
                })
                .all(|directory| {
                    if !directories.insert(directory.clone()) {
                        return true;
                    }
                    if !compiler_driver_search_directory_is_safe(&directory, driver) {
                        return false;
                    }

                    #[cfg(windows)]
                    {
                        let Some(cache) = self.shared_registry_cache.as_ref() else {
                            return false;
                        };
                        for executable in &cache.implicit_native_tools {
                            let candidate = directory.join(executable);
                            let candidate = if candidate.extension().is_none() {
                                candidate.with_extension(std::env::consts::EXE_EXTENSION)
                            } else {
                                candidate
                            };
                            match std::fs::metadata(&candidate) {
                                Ok(metadata)
                                    if metadata.is_file()
                                        && linker_has_verified_toolchain_identity(
                                            &candidate,
                                            _build_runner,
                                            None,
                                        ) => {}
                                Ok(_) => return false,
                                Err(error)
                                    if matches!(
                                        error.kind(),
                                        std::io::ErrorKind::NotFound
                                            | std::io::ErrorKind::NotADirectory
                                    ) => {}
                                Err(_) => return false,
                            }
                        }
                    }

                    true
                });
        }
        true
    }

    /// Returns the appropriate directory layout for either a plugin or not.
    pub fn layout(&self, kind: CompileKind) -> &Layout {
        match kind {
            CompileKind::Host => &self.host,
            CompileKind::Target(target) => &self.target[&target],
        }
    }

    /// Gets the metadata for the given unit.
    ///
    /// See [`Metadata`] and [`fingerprint`] module for more.
    ///
    /// [`fingerprint`]: super::super::fingerprint#fingerprints-and-metadata
    pub fn metadata(&self, unit: &Unit) -> Metadata {
        self.metas[unit]
    }

    /// Gets the short hash based only on the `PackageId`.
    /// Used for the metadata when `c_extra_filename` returns `None`.
    fn target_short_hash(&self, unit: &Unit) -> String {
        let hashable = unit.pkg.package_id().stable_hash(self.ws.root());
        util::short_hash(&(METADATA_VERSION, hashable))
    }

    /// Returns the directory where the artifacts for the given unit are
    /// initially created.
    pub fn output_dir(&self, unit: &Unit) -> PathBuf {
        // Docscrape units need to have doc/ set as the out_dir so sources for reverse-dependencies
        // will be put into doc/ and not into deps/ where the *.examples files are stored.
        if unit.mode.is_doc() || unit.mode.is_doc_scrape() {
            self.layout(unit.kind)
                .artifact_dir()
                .expect("artifact-dir was not locked")
                .doc()
                .to_path_buf()
        } else if unit.mode.is_doc_test() {
            panic!("doc tests do not have an out dir");
        } else if unit.target.is_custom_build() {
            self.build_script_dir(unit)
        } else if unit.target.is_example() && !self.ws.gctx().cli_unstable().build_dir_new_layout {
            self.layout(unit.kind).build_dir().examples().to_path_buf()
        } else if unit.artifact.is_true() {
            self.artifact_dir(unit)
        } else {
            self.deps_dir(unit).to_path_buf()
        }
    }

    /// Additional export directory from `--artifact-dir`.
    pub fn export_dir(&self) -> Option<PathBuf> {
        self.export_dir.clone()
    }

    /// Directory name to use for a package in the form `{NAME}/{HASH}`.
    ///
    /// Note that some units may share the same directory, so care should be
    /// taken in those cases!
    fn pkg_dir(&self, unit: &Unit) -> String {
        let name = unit.pkg.package_id().name();
        let hash = self.unit_hash(unit);
        if let Some(cache) = &self.shared_registry_cache {
            if cache.immutable_units.get(unit).copied().unwrap_or(false) {
                return format!("registries/{}/{name}/{hash}", cache.rustc);
            }
            return format!(
                "workspaces/{}/{}/{name}/{hash}",
                cache.workspace, cache.rustc
            );
        }
        let separator = match self.ws.gctx().cli_unstable().build_dir_new_layout {
            true => "/",
            false => "-",
        };
        format!("{name}{separator}{hash}")
    }

    /// The directory hash to use for a given unit
    pub fn unit_hash(&self, unit: &Unit) -> String {
        self.metas[unit]
            .pkg_dir()
            .map(|h| h.to_string())
            .unwrap_or_else(|| self.target_short_hash(unit))
    }

    /// Returns the final artifact path for the host (`/…/target/debug`)
    pub fn host_dest(&self) -> Option<&Path> {
        self.host.artifact_dir().map(|v| v.dest())
    }

    /// Returns the root against which this unit's fingerprint paths are encoded.
    pub(crate) fn build_root(&self, unit: &Unit) -> PathBuf {
        if self.is_shared_registry_unit(unit) {
            self.ws.configured_build_dir().into_path_unlocked()
        } else {
            self.ws.build_dir().into_path_unlocked()
        }
    }

    /// The actual canonical compiler driver trusted by the shared registry namespace.
    pub(crate) fn shared_registry_compiler_driver(&self) -> Option<&Path> {
        self.shared_registry_cache
            .as_ref()
            .and_then(|cache| cache.compiler_driver.as_deref())
    }

    /// Native executable names that must not be shadowed in Windows loader search directories.
    pub(crate) fn shared_registry_implicit_native_tools(&self) -> Option<&[String]> {
        #[cfg(windows)]
        {
            self.shared_registry_cache
                .as_ref()
                .map(|cache| cache.implicit_native_tools.as_slice())
        }
        #[cfg(not(windows))]
        {
            None
        }
    }

    /// Whether this exact unit's artifacts use the cross-workspace registry namespace.
    pub(crate) fn is_shared_registry_unit(&self, unit: &Unit) -> bool {
        self.shared_registry_cache
            .as_ref()
            .and_then(|cache| cache.immutable_units.get(unit))
            .copied()
            .unwrap_or(false)
    }

    /// Returns the host `deps` directory path for a given build unit.
    pub fn host_deps(&self, unit: &Unit) -> PathBuf {
        let dir = self.pkg_dir(unit);
        self.host.build_dir().deps(&dir)
    }

    /// Returns the directories where Rust crate dependencies are found for the
    /// specified unit.
    pub fn deps_dir(&self, unit: &Unit) -> PathBuf {
        let dir = self.pkg_dir(unit);
        self.layout(unit.kind).build_dir().deps(&dir)
    }

    /// Returns the directories where Rust crate dependencies are found for the
    /// specified unit. (new layout)
    ///
    /// New features should consider using this so we can avoid their migrations.
    pub fn out_dir_new_layout(&self, unit: &Unit) -> PathBuf {
        let dir = self.pkg_dir(unit);
        self.layout(unit.kind)
            .build_dir()
            .out_force_new_layout(&dir)
    }

    /// Directory where the fingerprint for the given unit should go.
    pub fn fingerprint_dir(&self, unit: &Unit) -> PathBuf {
        let dir = self.pkg_dir(unit);
        self.layout(unit.kind).build_dir().fingerprint(&dir)
    }

    /// The lock location for a given build unit.
    pub fn build_unit_lock(&self, unit: &Unit) -> PathBuf {
        let dir = self.pkg_dir(unit);
        self.layout(unit.kind)
            .build_dir()
            .build_unit(&dir)
            .join(".lock")
    }

    /// Private namespace whose admission policy covers this unit's outputs.
    pub(crate) fn worktree_seed_namespace(&self, unit: &Unit) -> PathBuf {
        self.layout(unit.kind)
            .build_dir()
            .build()
            .join("workspaces")
            .join(&self.shared_registry_cache.as_ref().unwrap().workspace)
    }

    /// Directory where incremental output for the given unit should go.
    pub fn incremental_dir(&self, unit: &Unit) -> PathBuf {
        let root = self.layout(unit.kind).build_dir().incremental();
        if self
            .shared_registry_cache
            .as_ref()
            .is_some_and(|cache| cache.isolated_clippy)
        {
            root.join(crate::compiler::OHM_WORKTREE_CLIPPY_DIRECTORY)
        } else {
            root.to_path_buf()
        }
    }

    /// Directory where timing output should go.
    pub fn timings_dir(&self) -> Option<&Path> {
        self.host.artifact_dir().map(|v| v.timings())
    }

    /// Returns the path for a file in the fingerprint directory.
    ///
    /// The "prefix" should be something to distinguish the file from other
    /// files in the fingerprint directory.
    pub fn fingerprint_file_path(&self, unit: &Unit, prefix: &str) -> PathBuf {
        // Different targets need to be distinguished in the
        let kind = unit.target.kind().description();
        let flavor = if unit.mode.is_any_test() {
            "test-"
        } else if unit.mode.is_doc() {
            "doc-"
        } else if unit.mode.is_run_custom_build() {
            "run-"
        } else {
            ""
        };
        let name = format!("{}{}{}-{}", prefix, flavor, kind, unit.target.name());
        self.fingerprint_dir(unit).join(name)
    }

    /// Path where compiler output is cached.
    pub fn message_cache_path(&self, unit: &Unit) -> PathBuf {
        self.fingerprint_file_path(unit, "output-")
    }

    /// Returns the directory where a compiled build script is stored.
    /// `/path/to/target/{debug,release}/build/PKG-HASH`
    pub fn build_script_dir(&self, unit: &Unit) -> PathBuf {
        assert!(unit.target.is_custom_build());
        assert!(!unit.mode.is_run_custom_build());
        assert!(self.metas.contains_key(unit));
        let dir = self.pkg_dir(unit);
        self.layout(CompileKind::Host)
            .build_dir()
            .build_script(&dir)
    }

    /// Returns the directory for compiled artifacts files.
    /// `/path/to/target/{debug,release}/deps/artifact/KIND/PKG-HASH`
    fn artifact_dir(&self, unit: &Unit) -> PathBuf {
        assert!(self.metas.contains_key(unit));
        assert!(unit.artifact.is_true());
        let dir = self.pkg_dir(unit);
        let kind = match unit.target.kind() {
            TargetKind::Bin => "bin",
            TargetKind::Lib(lib_kinds) => match lib_kinds.as_slice() {
                &[CrateType::Cdylib] => "cdylib",
                &[CrateType::Staticlib] => "staticlib",
                invalid => unreachable!(
                    "BUG: unexpected artifact library type(s): {:?} - these should have been split",
                    invalid
                ),
            },
            invalid => unreachable!(
                "BUG: {:?} are not supposed to be used as artifacts",
                invalid
            ),
        };
        self.layout(unit.kind).build_dir().artifact(&dir, kind)
    }

    /// Returns the directory where information about running a build script
    /// is stored.
    /// `/path/to/target/{debug,release}/build/PKG-HASH`
    pub fn build_script_run_dir(&self, unit: &Unit) -> PathBuf {
        assert!(unit.target.is_custom_build());
        assert!(unit.mode.is_run_custom_build());
        let dir = self.pkg_dir(unit);
        self.layout(unit.kind)
            .build_dir()
            .build_script_execution(&dir)
    }

    /// Returns the "`OUT_DIR`" directory for running a build script.
    /// `/path/to/target/{debug,release}/build/PKG-HASH/out`
    pub fn build_script_out_dir(&self, unit: &Unit) -> PathBuf {
        self.build_script_run_dir(unit).join("out")
    }

    /// Returns the path to the executable binary for the given bin target.
    ///
    /// This should only to be used when a `Unit` is not available.
    pub fn bin_link_for_target(
        &self,
        target: &Target,
        kind: CompileKind,
        bcx: &BuildContext<'_, '_>,
    ) -> CargoResult<Option<PathBuf>> {
        assert!(target.is_bin());
        let Some(dest) = self.layout(kind).artifact_dir().map(|v| v.dest()) else {
            return Ok(None);
        };
        let info = bcx.target_data.info(kind);
        let (file_types, _) = info
            .rustc_outputs(
                CompileMode::Build,
                &TargetKind::Bin,
                bcx.target_data.short_name(&kind),
                bcx.gctx,
            )
            .expect("target must support `bin`");

        let file_type = file_types
            .iter()
            .find(|file_type| file_type.flavor == FileFlavor::Normal)
            .expect("target must support `bin`");

        Ok(Some(dest.join(file_type.uplift_filename(target))))
    }

    /// Returns the filenames that the given unit will generate.
    ///
    /// Note: It is not guaranteed that all of the files will be generated.
    pub(super) fn outputs(
        &self,
        unit: &Unit,
        bcx: &BuildContext<'a, 'gctx>,
    ) -> CargoResult<Arc<Vec<OutputFile>>> {
        self.outputs[unit]
            .try_borrow_with(|| self.calc_outputs(unit, bcx))
            .map(Arc::clone)
    }

    /// Returns the path where the output for the given unit and `FileType`
    /// should be uplifted to.
    ///
    /// Returns `None` if the unit shouldn't be uplifted (for example, a
    /// dependent rlib).
    fn uplift_to(
        &self,
        unit: &Unit,
        file_type: &FileType,
        from_path: &Path,
        bcx: &BuildContext<'_, '_>,
    ) -> Option<PathBuf> {
        // Tests, check, doc, etc. should not be uplifted.
        if unit.mode != CompileMode::Build || file_type.flavor == FileFlavor::Rmeta {
            return None;
        }

        // Artifact dependencies are never uplifted.
        if unit.artifact.is_true() {
            return None;
        }

        // Build script bins are never uplifted.
        if bcx.gctx.cli_unstable().build_dir_new_layout && unit.target.is_custom_build() {
            return None;
        }

        // - Binaries: The user always wants to see these, even if they are
        //   implicitly built (for example for integration tests).
        // - dylibs: This ensures that the dynamic linker pulls in all the
        //   latest copies (even if the dylib was built from a previous cargo
        //   build). There are complex reasons for this, see #8139, #6167, #6162.
        // - Things directly requested from the command-line (the "roots").
        //   This one is a little questionable for rlibs (see #6131), but is
        //   historically how Cargo has operated. This is primarily useful to
        //   give the user access to staticlibs and cdylibs.
        if !unit.target.is_bin()
            && !unit.target.is_custom_build()
            && file_type.crate_type != Some(CrateType::Dylib)
            && !self.roots.contains(unit)
        {
            return None;
        }

        let filename = file_type.uplift_filename(&unit.target);
        let uplift_path = if unit.target.is_example() {
            // Examples live in their own little world.
            self.layout(unit.kind)
                .artifact_dir()?
                .examples()
                .join(filename)
        } else if unit.target.is_custom_build() {
            self.build_script_dir(unit).join(filename)
        } else {
            self.layout(unit.kind).artifact_dir()?.dest().join(filename)
        };
        if from_path == uplift_path {
            // This can happen with things like examples that reside in the
            // same directory, do not have a metadata hash (like on Windows),
            // and do not have hyphens.
            return None;
        }
        Some(uplift_path)
    }

    /// Calculates the filenames that the given unit will generate.
    /// Should use [`CompilationFiles::outputs`] instead
    /// as it caches the result of this function.
    fn calc_outputs(
        &self,
        unit: &Unit,
        bcx: &BuildContext<'a, 'gctx>,
    ) -> CargoResult<Arc<Vec<OutputFile>>> {
        let ret = match unit.mode {
            _ if unit.skip_non_compile_time_dep => {
                // This skips compilations so no outputs
                vec![]
            }
            CompileMode::Doc => {
                let wants_json_doc = bcx.build_config.intent.wants_doc_json_output();

                let path = if wants_json_doc {
                    // Always use 'new' layout for '--output-format=json'.
                    let crate_name = unit.target.crate_name();
                    self.out_dir_new_layout(unit)
                        .join(format!("{crate_name}.json"))
                } else {
                    self.output_dir(unit)
                        .join(unit.target.crate_name())
                        .join("index.html")
                };

                // Uplift if output is json, from 'new' layout location for backward compatibility
                // See #16773.
                let hardlink = if wants_json_doc {
                    Some(
                        self.output_dir(unit)
                            .join(format!("{}.json", unit.target.crate_name())),
                    )
                } else {
                    None
                };

                let mut outputs = vec![OutputFile {
                    path,
                    hardlink,
                    export_path: None,
                    flavor: FileFlavor::Normal,
                }];

                if bcx.gctx.cli_unstable().rustdoc_mergeable_info && !wants_json_doc {
                    // `-Zrustdoc-mergeable-info` always uses the new layout.
                    outputs.push(OutputFile {
                        path: self
                            .out_dir_new_layout(unit)
                            .join(unit.target.crate_name())
                            .with_extension("json"),
                        hardlink: None,
                        export_path: None,
                        flavor: FileFlavor::DocParts,
                    })
                }

                outputs
            }
            CompileMode::RunCustomBuild => {
                // At this time, this code path does not handle build script
                // outputs.
                vec![]
            }
            CompileMode::Doctest => {
                // Doctests are built in a temporary directory and then
                // deleted. There is the `--persist-doctests` unstable flag,
                // but Cargo does not know about that.
                vec![]
            }
            CompileMode::Docscrape => {
                // The file name needs to be stable across Cargo sessions.
                // This originally used unit.buildkey(), but that isn't stable,
                // so we use metadata instead (prefixed with name for debugging).
                let file_name = format!(
                    "{}-{}.examples",
                    unit.pkg.name(),
                    self.metadata(unit).unit_id()
                );
                let path = self.deps_dir(unit).join(file_name);
                vec![OutputFile {
                    path,
                    hardlink: None,
                    export_path: None,
                    flavor: FileFlavor::Normal,
                }]
            }
            CompileMode::Test | CompileMode::Build | CompileMode::Check { .. } => {
                let mut outputs = self.calc_outputs_rustc(unit, bcx)?;
                if bcx.build_config.sbom && bcx.gctx.cli_unstable().sbom {
                    let sbom_files: Vec<_> = outputs
                        .iter()
                        .filter(|o| matches!(o.flavor, FileFlavor::Normal | FileFlavor::Linkable))
                        .map(|output| OutputFile {
                            path: Self::append_sbom_suffix(&output.path),
                            hardlink: output.hardlink.as_ref().map(Self::append_sbom_suffix),
                            export_path: output.export_path.as_ref().map(Self::append_sbom_suffix),
                            flavor: FileFlavor::Sbom,
                        })
                        .collect();
                    outputs.extend(sbom_files.into_iter());
                }

                // Only generates unremap files for root units.
                if bcx.roots.contains(unit) && trim_paths::should_emit_unremap_file(unit) {
                    let unremap_files: Vec<_> = outputs
                        .iter()
                        .filter(|o| matches!(o.flavor, FileFlavor::Normal | FileFlavor::Linkable))
                        .map(|output| OutputFile {
                            path: trim_paths::append_unremap_suffix(&output.path),
                            hardlink: output
                                .hardlink
                                .as_ref()
                                .map(trim_paths::append_unremap_suffix),
                            export_path: output
                                .export_path
                                .as_ref()
                                .map(trim_paths::append_unremap_suffix),
                            flavor: FileFlavor::Unremap,
                        })
                        .collect();
                    outputs.extend(unremap_files.into_iter());
                }
                outputs
            }
        };
        debug!("Target filenames: {:?}", ret);

        Ok(Arc::new(ret))
    }

    /// Append the SBOM suffix to the file name.
    fn append_sbom_suffix(link: &PathBuf) -> PathBuf {
        const SBOM_FILE_EXTENSION: &str = ".cargo-sbom.json";
        let mut link_buf = link.clone().into_os_string();
        link_buf.push(SBOM_FILE_EXTENSION);
        PathBuf::from(link_buf)
    }

    /// Computes the actual, full pathnames for all the files generated by rustc.
    ///
    /// The `OutputFile` also contains the paths where those files should be
    /// "uplifted" to.
    fn calc_outputs_rustc(
        &self,
        unit: &Unit,
        bcx: &BuildContext<'a, 'gctx>,
    ) -> CargoResult<Vec<OutputFile>> {
        let out_dir = self.output_dir(unit);

        let info = bcx.target_data.info(unit.kind);
        let triple = bcx.target_data.short_name(&unit.kind);
        let (file_types, unsupported) =
            info.rustc_outputs(unit.mode, unit.target.kind(), triple, bcx.gctx)?;
        if file_types.is_empty() {
            if !unsupported.is_empty() {
                let unsupported_strs: Vec<_> = unsupported.iter().map(|ct| ct.as_str()).collect();
                anyhow::bail!(
                    "cannot produce {} for `{}` as the target `{}` \
                     does not support these crate types",
                    unsupported_strs.join(", "),
                    unit.pkg,
                    triple,
                )
            }
            anyhow::bail!(
                "cannot compile `{}` as the target `{}` does not \
                 support any of the output crate types",
                unit.pkg,
                triple,
            );
        }

        // Convert FileType to OutputFile.
        let mut outputs = Vec::new();
        for file_type in file_types {
            let meta = self.metas[unit];
            let meta_opt = meta.c_extra_filename().map(|h| h.to_string());
            let path = out_dir.join(file_type.output_filename(&unit.target, meta_opt.as_deref()));

            // If, the `different_binary_name` feature is enabled, the name of the hardlink will
            // be the name of the binary provided by the user in `Cargo.toml`.
            let hardlink = self.uplift_to(unit, &file_type, &path, bcx);
            let export_path = if unit.target.is_custom_build() {
                None
            } else {
                self.export_dir.as_ref().and_then(|export_dir| {
                    hardlink
                        .as_ref()
                        .map(|hardlink| export_dir.join(hardlink.file_name().unwrap()))
                })
            };
            outputs.push(OutputFile {
                path,
                hardlink,
                export_path,
                flavor: file_type.flavor,
            });
        }
        Ok(outputs)
    }
}

/// Appends every plain, host, target, and toolchain-specific native-tool selector.
///
/// Sharing must reject opaque executables under every spelling consumed by build helpers.
fn append_native_environment_names(
    names: &mut Vec<String>,
    name: &str,
    build_runner: &BuildRunner<'_, '_>,
) {
    names.extend([
        name.to_owned(),
        format!("HOST_{name}"),
        format!("TARGET_{name}"),
    ]);
    for kind in &build_runner.bcx.all_kinds {
        let target = build_runner.bcx.target_data.short_name(kind);
        names.extend(native_target_environment_names(name, target));
    }
}

/// Covers the incompatible target-name normalization used by `cc`, CMake, and pkg-config.
///
/// CMake and pkg-config preserve dots that `cc` replaces with underscores.
fn native_target_environment_names(name: &str, target: &str) -> [String; 3] {
    [
        format!("{name}_{target}"),
        format!("{name}_{}", target.replace('-', "_")),
        format!("{name}_{}", target.replace(['-', '.'], "_")),
    ]
}

/// External executables selected implicitly by the known native-build helper families.
///
/// Keep these names associated with their originating helper so an unrelated Rust-only
/// registry package does not inherit the helper's opaque, workspace-specific toolchain.
fn package_implicit_native_tools(package: &str, targets: &[String]) -> Vec<String> {
    let tools: &[&str] = match package {
        "cc" => &[
            "nvcc",
            "cl",
            "cl.exe",
            "clang-cl",
            "clang-cl.exe",
            "emcc",
            "emcc.bat",
            "em++",
            "em++.bat",
            "emar",
            "emar.bat",
            "emranlib",
            "emranlib.bat",
            "cmd",
            "cmd.exe",
            "llvm-ar",
            "llvm-ranlib",
            "llvm-lib",
            "lib",
            "lib.exe",
            "wr-cc",
            "wr-c++",
            "qcc",
            "q++",
        ],
        "cmake" => &["cmake", "emcmake", "emmake", "make", "mingw32-make"],
        "pkg-config" => &["pkg-config", "pkgconf"],
        "openssl-src" => &["make", "gmake", "nasm", "nmake.exe"],
        _ => &[],
    };
    let mut tools = tools
        .iter()
        .map(|tool| (*tool).to_owned())
        .collect::<Vec<_>>();

    if package == "cc" {
        for target in targets {
            for tool in [
                "gcc",
                "g++",
                "clang",
                "clang++",
                "ar",
                "gcc-ar",
                "ranlib",
                "gcc-ranlib",
            ] {
                tools.push(format!("{target}-{tool}"));
            }
        }
    }

    tools
}

/// Rejects Windows configuration aliases that can bypass Cargo's case-sensitive lookups.
fn configured_environment_has_sensitive_case_alias(
    configured: &[(String, OsString)],
    case_insensitive: bool,
) -> bool {
    case_insensitive
        && configured
            .iter()
            .any(|(name, _)| name.bytes().any(|byte| byte.is_ascii_lowercase()))
}

/// Registry units remain shareable only when their entire dependency closure is immutable.
///
/// A `[patch.crates-io]` override can make an otherwise immutable registry crate depend on a
/// workspace-local package. Such crates must remain private to the workspace that patched them.
/// A user-configured source replacement maps downloaded packages back to the original registry
/// identity. Only remote registry replacements are immutable enough to share; their effective
/// source identity and package checksum are included in the unit metadata below.
/// Sharing build-script output additionally relies on scripts declaring their external inputs;
/// Cargo-provided compiler, documentation-tool, linker, configuration, and job-count context is
/// already incorporated into the shared namespace. The explicit opt-in trusts build scripts not
/// to persist Cargo's synthesized, workspace-private dynamic-library search paths or jobserver
/// handles as generated source. Arbitrary global rustc wrappers and direct compiler shims are
/// rejected. Procedural macros can observe external inputs without tracking them, so the
/// selected trust policy controls which canonical, lockfile-authenticated macro and runtime
/// dependency closures may be shared.
///
/// By default, an opaque package-specific native tool taints its helper, every build script,
/// and their downstream consumers. Explicit permissive policies can instead trust authenticated
/// build scripts or the complete native-tool closure; their executable dependency closures must
/// always come from canonical, checksum-authenticated crates.io packages, fetched directly or
/// through HTTP(S) registry mirrors. Local and vendored replacements remain private.
fn native_tool_policy_allows_unit(
    trust: OhmNativeToolTrust,
    untrusted_native_helper: bool,
    build_script: bool,
    opaque_native_tools: bool,
) -> bool {
    (!untrusted_native_helper || trust == OhmNativeToolTrust::All)
        && (!opaque_native_tools || !build_script || trust != OhmNativeToolTrust::Strict)
}

fn is_immutable_registry_unit(
    unit: &Unit,
    build_runner: &BuildRunner<'_, '_>,
    audited_macro_runtime: bool,
    permissive_native_runtime: bool,
    untrusted_native_tool_packages: &HashSet<String>,
    eligibility: &mut HashMap<(Unit, bool, bool), bool>,
    custom_codegen_backends: &mut HashMap<CompileKind, bool>,
) -> bool {
    let audited_macro_runtime = audited_macro_runtime || unit.pkg.proc_macro();
    let package_id = unit.pkg.package_id();
    let native_helper = untrusted_native_tool_packages.contains(package_id.name().as_str());
    let build_script = unit.target.is_custom_build() || unit.mode.is_run_custom_build();
    let native_trust = build_runner.bcx.gctx.cli_unstable().ohm_native_tool_trust;
    let permissive_native_runtime = permissive_native_runtime
        || (native_helper && native_trust == OhmNativeToolTrust::All)
        || (build_script
            && !untrusted_native_tool_packages.is_empty()
            && native_trust != OhmNativeToolTrust::Strict);
    let cache_key = (
        unit.clone(),
        audited_macro_runtime,
        permissive_native_runtime,
    );
    if let Some(eligible) = eligibility.get(&cache_key) {
        return *eligible;
    }

    let source_id = package_id.source_id();
    let eligible = source_id.is_remote_registry()
        // Documentation and integration-test scratch paths refer to this target tree.
        && !unit.mode.is_doc()
        && !unit.mode.is_doc_scrape()
        && !unit.mode.is_doc_test()
        && !unit.target.is_test()
        && !unit.target.is_bench()
        && native_tool_policy_allows_unit(
            native_trust,
            native_helper,
            build_script,
            !untrusted_native_tool_packages.is_empty(),
        )
        && (!permissive_native_runtime
            || build_runner
                .bcx
                .authenticated_native_tool_packages
                .contains(&package_id))
        && build_runner
            .bcx
            .packages
            .sources()
            .get(source_id)
            .is_some_and(|source| {
                source.replaced_source_id().is_remote_registry()
                    && (!audited_macro_runtime
                        || build_runner
                            .bcx
                            .audited_proc_macro_packages
                            .contains(&package_id))
            })
        && !unit_uses_custom_codegen_backend(unit, build_runner, custom_codegen_backends)
        && build_runner.unit_deps(unit).iter().all(|dependency| {
            is_immutable_registry_unit(
                &dependency.unit,
                build_runner,
                audited_macro_runtime,
                permissive_native_runtime,
                untrusted_native_tool_packages,
                eligibility,
                custom_codegen_backends,
            )
        });
    eligibility.insert(cache_key, eligible);
    eligible
}

/// Rejects compiler options and target specifications that can execute opaque external code.
///
/// Response files, dynamic LLVM extensions, custom targets, and linker overrides remain private.
fn unit_uses_custom_codegen_backend(
    unit: &Unit,
    build_runner: &BuildRunner<'_, '_>,
    custom_codegen_backends: &mut HashMap<CompileKind, bool>,
) -> bool {
    let host_sysroot = &build_runner.bcx.target_data.info(CompileKind::Host).sysroot;
    let target_sysroot = &build_runner.bcx.target_data.info(unit.kind).sysroot;
    let host = build_runner.bcx.host_triple();
    if unit.profile.codegen_backend.is_some()
        || *custom_codegen_backends
            .entry(CompileKind::Host)
            .or_insert_with(|| sysroot_has_custom_codegen_backends(host_sysroot, host.as_str()))
        || (target_sysroot != host_sysroot
            && *custom_codegen_backends.entry(unit.kind).or_insert_with(|| {
                sysroot_has_custom_codegen_backends(target_sysroot, host.as_str())
            }))
    {
        return true;
    }

    match unit.kind {
        CompileKind::Target(CompileTarget::Json { .. }) => return true,
        CompileKind::Target(CompileTarget::Tuple(target)) => {
            let Ok(configured_environment) = build_runner.bcx.gctx.env_config() else {
                return true;
            };
            let target_path = configured_environment
                .get("RUST_TARGET_PATH")
                .map(std::ffi::OsString::as_os_str)
                .or_else(|| build_runner.bcx.gctx.get_env_os("RUST_TARGET_PATH"));
            if target_path.is_some_and(|path| !path.is_empty()) {
                return true;
            }

            let target_filename = format!("{target}.json");
            let target_specifications = [
                target_sysroot
                    .join("lib")
                    .join("rustlib")
                    .join(target.as_str())
                    .join("target.json"),
                build_runner.bcx.gctx.cwd().join(&target_filename),
                unit.pkg.root().join(&target_filename),
            ];
            for target_specification in target_specifications {
                match std::fs::metadata(target_specification) {
                    Ok(_) => return true,
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                    Err(_) => return true,
                }
            }
        }
        CompileKind::Host => {}
    }

    let target_info = build_runner.bcx.target_data.info(unit.kind);
    let rustflags = rustflags_for_cache_admission(
        &unit.rustflags,
        &target_info.rustflags,
        target_info.ohm_linker_flags,
    );
    let flags = unit
        .pkg
        .manifest()
        .lint_rustflags()
        .iter()
        .map(String::as_str)
        .chain(unit.profile.rustflags.iter().map(|flag| flag.as_str()))
        .chain(rustflags.iter().map(String::as_str))
        .chain(
            build_runner
                .bcx
                .extra_args_for(unit)
                .into_iter()
                .flatten()
                .map(String::as_str),
        );

    unit_compiler_arguments_use_opaque_execution(unit, host.as_str(), target_sysroot, flags)
}

/// Excludes only the bundled-linker suffix recorded during target discovery.
///
/// Cargo's generated flags remain in fingerprints and compiler invocations. User flags,
/// including identical linker arguments without this provenance, still require inspection.
pub(super) fn rustflags_for_cache_admission<'a>(
    rustflags: &'a [String],
    target_rustflags: &[String],
    bundled_linker_flags: usize,
) -> &'a [String] {
    let Some(start) = target_rustflags.len().checked_sub(bundled_linker_flags) else {
        return rustflags;
    };
    rustflags
        .strip_suffix(&target_rustflags[start..])
        .unwrap_or(rustflags)
}

/// Executable compile-time units additionally run platform-specific native tools.
pub(super) fn unit_compiler_arguments_use_opaque_execution<'a>(
    unit: &Unit,
    host_triple: &str,
    sysroot: &Path,
    flags: impl IntoIterator<Item = &'a str>,
) -> bool {
    let executable_unit =
        unit.mode == CompileMode::Build && unit.target.is_compile_time_dependency();
    let apple_executable = executable_unit
        && match unit.kind {
            CompileKind::Host => host_triple.contains("-apple-"),
            CompileKind::Target(target) => target.short_name().contains("-apple-"),
        };

    let profile_debuginfo_enabled = unit.profile.debuginfo.is_turned_on();
    let trusted_objcopy = || sysroot_contains_trusted_objcopy(sysroot, host_triple);
    if apple_executable {
        let strip = unit.profile.strip.into_inner();
        if apple_executable_profile_uses_external_tools(
            strip,
            unit.profile
                .split_debuginfo
                .as_ref()
                .map(|value| value.as_str()),
            profile_debuginfo_enabled,
            matches!(strip, StripInner::None) || trusted_objcopy(),
        ) {
            return true;
        }
    }

    compiler_arguments_use_opaque_execution(
        flags,
        executable_unit,
        apple_executable,
        profile_debuginfo_enabled,
        trusted_objcopy,
    )
}

/// Accept only the tool rustc resolves before consulting ambient PATH entries.
fn sysroot_contains_trusted_objcopy(sysroot: &Path, host_triple: &str) -> bool {
    let Ok(sysroot) = sysroot.canonicalize() else {
        return false;
    };
    let directory = sysroot
        .join("lib")
        .join("rustlib")
        .join(host_triple)
        .join("bin");
    let executable = directory.join("rust-objcopy");
    let Ok(executable) = executable.canonicalize() else {
        return false;
    };
    if !executable.starts_with(&sysroot) {
        return false;
    }
    let Ok(metadata) = std::fs::metadata(executable) else {
        return false;
    };
    if !metadata.is_file() {
        return false;
    }

    #[cfg(unix)]
    {
        let permissions = metadata.permissions().mode();
        let Ok(directory_metadata) = std::fs::metadata(directory) else {
            return false;
        };
        permissions & 0o111 != 0
            && permissions & 0o022 == 0
            && directory_metadata.is_dir()
            && directory_metadata.permissions().mode() & 0o022 == 0
    }
    #[cfg(not(unix))]
    {
        false
    }
}

/// Packed Apple debug info or an untrusted stripping utility remain opaque.
fn apple_executable_profile_uses_external_tools(
    strip: StripInner,
    split_debuginfo: Option<&str>,
    debuginfo_enabled: bool,
    trusted_objcopy: bool,
) -> bool {
    (!matches!(strip, StripInner::None) && !trusted_objcopy)
        || (debuginfo_enabled && split_debuginfo == Some("packed"))
}

/// Recognizes every spelling that can inject native code or opaque compiler tools.
fn compiler_arguments_use_opaque_execution<'a>(
    flags: impl IntoIterator<Item = &'a str>,
    executable_unit: bool,
    apple_executable: bool,
    profile_debuginfo_enabled: bool,
    trusted_objcopy: impl Fn() -> bool,
) -> bool {
    let mut flags = flags.into_iter();
    while let Some(flag) = flags.next() {
        if apple_executable && !profile_debuginfo_enabled && flag == "-g" {
            return true;
        }
        if flag.starts_with('@')
            || flag.starts_with("-l")
            || matches!(
                flag,
                "--target" | "--sysroot" | "--extern" | "--library-path"
            )
            || flag.starts_with("--target=")
            || flag.starts_with("--sysroot=")
            || flag.starts_with("--extern=")
            || flag.starts_with("--library-path=")
        {
            return true;
        }
        if flag == "-L" {
            let Some(search_path) = flags.next() else {
                return true;
            };
            if executable_unit
                || (!search_path.starts_with("native=") && !search_path.starts_with("framework="))
            {
                return true;
            }
            continue;
        }
        if let Some(search_path) = flag.strip_prefix("-L") {
            if executable_unit
                || (!search_path.starts_with("native=") && !search_path.starts_with("framework="))
            {
                return true;
            }
            continue;
        }
        let option = if matches!(flag, "-C" | "-Z" | "--codegen") {
            let Some(option) = flags.next() else {
                return true;
            };
            Some(option)
        } else {
            flag.strip_prefix("-C")
                .or_else(|| flag.strip_prefix("-Z"))
                .or_else(|| flag.strip_prefix("--codegen="))
        };
        if option.is_some_and(|option| {
            option.is_empty()
                || compiler_option_uses_opaque_execution(option)
                || (apple_executable
                    && compiler_option_uses_apple_auxiliary_tools(
                        option,
                        profile_debuginfo_enabled,
                        &trusted_objcopy,
                    ))
        }) {
            return true;
        }
    }

    false
}

/// Apple links spawn auxiliary tools for nontrivial stripping and packed debug data.
fn compiler_option_uses_apple_auxiliary_tools(
    option: &str,
    profile_debuginfo_enabled: bool,
    trusted_objcopy: impl Fn() -> bool,
) -> bool {
    let (name, value) = option.split_once('=').unwrap_or((option, ""));
    match name {
        "strip" => value != "none" && !trusted_objcopy(),
        "split-debuginfo" | "split_debuginfo" => value == "packed",
        "debuginfo" => !profile_debuginfo_enabled && !matches!(value, "0" | "none"),
        _ => false,
    }
}

/// Executable compiler extensions and command-line linker overrides bypass toolchain identity.
fn compiler_option_uses_opaque_execution(option: &str) -> bool {
    option.starts_with('@')
        || matches!(
            option.split('=').next(),
            Some(
                "codegen-backend"
                    | "codegen_backend"
                    | "llvm-plugins"
                    | "llvm_plugins"
                    | "autodiff"
                    | "default-linker-libraries"
                    | "default_linker_libraries"
                    | "link-self-contained"
                    | "link_self_contained"
                    | "linker"
                    | "linker-flavor"
                    | "linker_flavor"
                    | "linker-features"
                    | "linker_features"
                    | "dlltool"
                    | "link-arg"
                    | "link_arg"
                    | "link-args"
                    | "link_args"
                    | "pre-link-arg"
                    | "pre_link_arg"
                    | "pre-link-args"
                    | "pre_link_args"
                    | "linker-plugin-lto"
                    | "linker_plugin_lto"
            )
        )
}

/// A toolchain can embed an external default backend without exposing any rustc flags.
fn sysroot_has_custom_codegen_backends(sysroot: &Path, host: &str) -> bool {
    let backends = sysroot
        .join("lib")
        .join("rustlib")
        .join(host)
        .join("codegen-backends");
    !matches!(backends.try_exists(), Ok(false))
}

/// Identifies the sole readable, sysroot-contained runtime driver without hashing its contents.
///
/// Missing, ambiguous, unreadable, or escaped drivers make the selected toolchain unshareable.
fn compiler_driver_identity_for_sysroot(sysroot: &Path) -> Option<CompilerDriverIdentity> {
    let directory = sysroot.join(if cfg!(windows) { "bin" } else { "lib" });
    let driver_prefix = format!("{}rustc_driver-", std::env::consts::DLL_PREFIX);
    let mut candidates = std::fs::read_dir(directory)
        .ok()?
        .filter_map(Result::ok)
        .filter(|entry| {
            entry.file_name().to_str().is_some_and(|name| {
                name.starts_with(&driver_prefix) && name.ends_with(std::env::consts::DLL_SUFFIX)
            })
        });
    let path = candidates.next()?.path().canonicalize().ok()?;
    if candidates.next().is_some() || !path.starts_with(sysroot.canonicalize().ok()?) {
        return None;
    }
    let metadata = std::fs::File::open(&path).ok()?.metadata().ok()?;
    if !metadata.is_file() {
        return None;
    }

    Some(CompilerDriverIdentity {
        path,
        length: metadata.len(),
        modified: metadata.modified().ok()?,
        #[cfg(unix)]
        device: metadata.dev(),
        #[cfg(unix)]
        inode: metadata.ino(),
        #[cfg(unix)]
        changed: metadata.ctime(),
        #[cfg(unix)]
        changed_nanoseconds: metadata.ctime_nsec(),
        #[cfg(not(unix))]
        created: metadata.created().ok(),
    })
}

/// Accepts absent driver names and genuine aliases while rejecting shadowed runtime drivers.
fn compiler_driver_search_directory_is_safe(directory: &Path, expected: &Path) -> bool {
    let Some(filename) = expected.file_name() else {
        return false;
    };
    let candidate = directory.join(filename);

    match std::fs::metadata(&candidate) {
        Ok(metadata) => {
            metadata.is_file()
                && candidate
                    .canonicalize()
                    .is_ok_and(|candidate| candidate == expected)
        }
        Err(error)
            if matches!(
                error.kind(),
                std::io::ErrorKind::NotFound | std::io::ErrorKind::NotADirectory
            ) =>
        {
            true
        }
        Err(_) => false,
    }
}

/// Only an actual toolchain compiler has an identity Cargo can verify across workspaces.
///
/// A direct `RUSTC` executable can otherwise be an opaque, environment-sensitive shim whose
/// reported compiler version and path remain unchanged while its compilation behavior changes.
fn compiler_has_verified_toolchain_identity(
    build_runner: &BuildRunner<'_, '_>,
    executable_search_path: Option<&OsStr>,
) -> bool {
    if cfg!(windows) && !build_runner.bcx.rustc().path.is_absolute() {
        return false;
    }
    let Ok(Some(compiler)) =
        resolve_effective_executable(&build_runner.bcx.rustc().path, executable_search_path)
    else {
        return false;
    };
    let Ok(compiler) = compiler.canonicalize() else {
        return false;
    };
    let expected = build_runner
        .bcx
        .target_data
        .info(CompileKind::Host)
        .sysroot
        .join("bin")
        .join("rustc")
        .with_extension(std::env::consts::EXE_EXTENSION);

    expected
        .canonicalize()
        .is_ok_and(|expected| expected == compiler)
}

/// Accepts the selected toolchain's rustdoc, its exact missing path, or an authenticated proxy.
///
/// Build scripts can execute `RUSTDOC` without tracking the wrapper's private inputs.
fn rustdoc_has_verified_toolchain_identity(
    rustdoc: &Path,
    build_runner: &BuildRunner<'_, '_>,
    executable_search_path: Option<&OsStr>,
) -> bool {
    if cfg!(windows) && !rustdoc.is_absolute() {
        return false;
    }
    let expected = build_runner
        .bcx
        .target_data
        .info(CompileKind::Host)
        .sysroot
        .join("bin")
        .join("rustdoc")
        .with_extension(std::env::consts::EXE_EXTENSION);

    match expected.canonicalize() {
        Ok(expected) => resolve_effective_executable(rustdoc, executable_search_path)
            .ok()
            .flatten()
            .and_then(|actual| actual.canonicalize().ok())
            .is_some_and(|actual| actual == expected),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            rustdoc == expected.as_path()
                || (rustdoc
                    == Path::new("rustdoc")
                        .with_extension(std::env::consts::EXE_EXTENSION)
                        .as_path()
                    && rustdoc_is_authenticated_rustup_proxy(
                        rustdoc,
                        build_runner,
                        executable_search_path,
                    ))
        }
        Err(_) => false,
    }
}

/// Authenticate a fallback rustdoc proxy without trusting PATH, HOME, or CARGO_HOME.
fn rustdoc_is_authenticated_rustup_proxy(
    rustdoc: &Path,
    build_runner: &BuildRunner<'_, '_>,
    executable_search_path: Option<&OsStr>,
) -> bool {
    let sysroot = &build_runner.bcx.target_data.info(CompileKind::Host).sysroot;
    let Some(toolchains) = sysroot.parent() else {
        return false;
    };
    if toolchains.file_name() != Some(OsStr::new("toolchains")) {
        return false;
    }
    let Some(toolchain_owner) = toolchains.parent() else {
        return false;
    };
    let user_home = if toolchain_owner.file_name() == Some(OsStr::new(".rustup")) {
        toolchain_owner.parent()
    } else if toolchain_owner.file_name() == Some(OsStr::new("ohm")) {
        let Some(share) = toolchain_owner.parent() else {
            return false;
        };
        let Some(local) = share.parent() else {
            return false;
        };
        if share.file_name() != Some(OsStr::new("share"))
            || local.file_name() != Some(OsStr::new(".local"))
        {
            return false;
        }
        local.parent()
    } else {
        None
    };
    let Some(user_home) = user_home else {
        return false;
    };

    let compiler =
        resolve_effective_executable(&build_runner.bcx.rustc().path, executable_search_path)
            .ok()
            .flatten()
            .and_then(|compiler| compiler.canonicalize().ok());
    let actual_sysroot = compiler
        .as_deref()
        .and_then(Path::parent)
        .and_then(Path::parent)
        .and_then(|sysroot| sysroot.canonicalize().ok());
    if !sysroot
        .canonicalize()
        .ok()
        .is_some_and(|expected| Some(expected.as_path()) == actual_sysroot.as_deref())
    {
        return false;
    }

    let Some(toolchain) = build_runner.bcx.gctx.get_env_os("RUSTUP_TOOLCHAIN") else {
        return false;
    };
    if toolchain.is_empty()
        || Path::new(toolchain).components().count() != 1
        || toolchain.to_string_lossy().contains(&['/', '\\'])
    {
        return false;
    }
    let rustup_home = build_runner
        .bcx
        .gctx
        .get_env_os("RUSTUP_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| user_home.join(".rustup"));
    let selected_sysroot = rustup_home.join("toolchains").join(toolchain);
    if !selected_sysroot
        .canonicalize()
        .ok()
        .is_some_and(|selected| Some(selected.as_path()) == actual_sysroot.as_deref())
    {
        return false;
    }

    let trusted_proxy = user_home
        .join(".cargo")
        .join("bin")
        .join("rustup")
        .with_extension(std::env::consts::EXE_EXTENSION);
    resolve_effective_executable(rustdoc, executable_search_path)
        .ok()
        .flatten()
        .is_some_and(|actual| same_file::is_same_file(actual, trusted_proxy).unwrap_or(false))
}

/// Resolves a tool using the child process's actual configured executable search path.
///
/// Relative paths and search entries are unsafe because registry processes change their cwd.
fn resolve_effective_executable(
    executable: &Path,
    executable_search_path: Option<&OsStr>,
) -> Result<Option<PathBuf>, std::io::Error> {
    if executable.is_absolute() {
        return Ok(Some(executable.to_path_buf()));
    }
    if executable.components().count() != 1 {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "relative executable path depends on the package working directory",
        ));
    }
    let Some(search_path) = executable_search_path else {
        return Err(std::io::Error::new(
            std::io::ErrorKind::NotFound,
            "executable search path is unavailable",
        ));
    };
    if std::env::split_paths(search_path).any(|directory| !directory.is_absolute()) {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "relative executable search directory depends on the package working directory",
        ));
    }

    for directory in std::env::split_paths(search_path) {
        let candidate = directory.join(executable);
        let candidate = if cfg!(windows) && candidate.extension().is_none() {
            candidate.with_extension(std::env::consts::EXE_EXTENSION)
        } else {
            candidate
        };
        match std::fs::metadata(&candidate) {
            Ok(metadata) if metadata.is_file() => return Ok(Some(candidate)),
            Ok(_) => {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    "executable search candidate is not a regular file",
                ));
            }
            Err(error)
                if matches!(
                    error.kind(),
                    std::io::ErrorKind::NotFound | std::io::ErrorKind::NotADirectory
                ) => {}
            Err(error) => return Err(error),
        }
    }

    Ok(None)
}

/// Explicit linkers can bypass compiler identity when they are opaque user-controlled wrappers.
///
/// Keep the normal system linkers and the selected toolchain's own executables shareable, but
/// leave arbitrary scripts private to each workspace even when their configured paths match.
fn linker_has_verified_toolchain_identity(
    linker: &Path,
    build_runner: &BuildRunner<'_, '_>,
    executable_search_path: Option<&OsStr>,
) -> bool {
    let resolved = resolve_effective_executable(linker, executable_search_path)
        .ok()
        .flatten();
    let Some(linker) = resolved.and_then(|path| path.canonicalize().ok()) else {
        return false;
    };

    if build_runner
        .bcx
        .target_data
        .info(CompileKind::Host)
        .sysroot
        .canonicalize()
        .is_ok_and(|sysroot| linker.starts_with(sysroot))
    {
        return true;
    }

    #[cfg(windows)]
    {
        std::env::var_os("SystemRoot")
            .map(PathBuf::from)
            .and_then(|root| root.canonicalize().ok())
            .is_some_and(|root| linker.starts_with(root))
    }

    #[cfg(not(windows))]
    {
        let system_tool = [
            "/usr/bin",
            "/bin",
            "/usr/libexec",
            "/Library/Developer/CommandLineTools/usr/bin",
            "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin",
        ]
        .into_iter()
        .filter_map(|directory| Path::new(directory).canonicalize().ok())
        .any(|directory| linker.starts_with(directory));

        #[cfg(target_os = "linux")]
        {
            system_tool
                || (distribution_llvm_toolchain_path(&linker)
                    && linker
                        .ancestors()
                        .take_while(|ancestor| *ancestor != Path::new("/"))
                        .all(|ancestor| {
                            std::fs::metadata(ancestor).is_ok_and(|metadata| {
                                metadata.uid() == 0 && metadata.mode() & 0o022 == 0
                            })
                        }))
        }

        #[cfg(not(target_os = "linux"))]
        {
            system_tool
        }
    }
}

/// Recognizes only versioned, distribution-managed LLVM native tool executables.
///
/// The caller separately authenticates the canonical executable and every ancestor as
/// root-owned and inaccessible to group or world writes before trusting this layout.
#[cfg(any(target_os = "linux", all(unix, test)))]
fn distribution_llvm_toolchain_path(executable: &Path) -> bool {
    let Some(filename) = executable.file_name().and_then(OsStr::to_str) else {
        return false;
    };
    let numeric_version = |version: &str| {
        !version.is_empty()
            && version.split('.').all(|component| {
                !component.is_empty() && component.bytes().all(|byte| byte.is_ascii_digit())
            })
    };
    let tool = filename
        .rsplit_once('-')
        .filter(|(_, version)| numeric_version(version))
        .map_or(filename, |(name, _)| name);
    if !matches!(
        tool,
        "clang"
            | "clang++"
            | "clang-cl"
            | "clang-cpp"
            | "llvm-ar"
            | "llvm-ranlib"
            | "llvm-lib"
            | "ld.lld"
            | "lld"
            | "lld-link"
            | "wasm-ld"
    ) {
        return false;
    }

    let Some(directory) = executable.parent() else {
        return false;
    };
    if directory.file_name() != Some(OsStr::new("bin")) {
        return false;
    }
    let Some(toolchain) = directory.parent() else {
        return false;
    };
    if !toolchain
        .file_name()
        .and_then(OsStr::to_str)
        .and_then(|name| name.strip_prefix("llvm-"))
        .is_some_and(numeric_version)
    {
        return false;
    }

    matches!(
        toolchain.parent(),
        Some(directory) if directory == Path::new("/usr/lib") || directory == Path::new("/usr/lib64")
    )
}

/// Gets the metadata hash for the given [`Unit`].
///
/// When a metadata hash doesn't exist for the given unit,
/// this calls itself recursively to compute metadata hashes of all its dependencies.
/// See [`compute_metadata`] for how a single metadata hash is computed.
fn metadata_of<'a>(
    unit: &Unit,
    build_runner: &BuildRunner<'_, '_>,
    metas: &'a mut HashMap<Unit, Metadata>,
) -> &'a Metadata {
    if !metas.contains_key(unit) {
        let meta = compute_metadata(unit, build_runner, metas);
        metas.insert(unit.clone(), meta);
        for dep in build_runner.unit_deps(unit) {
            metadata_of(&dep.unit, build_runner, metas);
        }
    }
    &metas[unit]
}

/// Computes the metadata hash for the given [`Unit`].
fn compute_metadata(
    unit: &Unit,
    build_runner: &BuildRunner<'_, '_>,
    metas: &mut HashMap<Unit, Metadata>,
) -> Metadata {
    let bcx = &build_runner.bcx;
    let deps_metadata = build_runner
        .unit_deps(unit)
        .iter()
        .map(|dep| *metadata_of(&dep.unit, build_runner, metas))
        .collect::<Vec<_>>();
    let c_extra_filename = use_extra_filename(bcx, unit);
    let pkg_dir = use_pkg_dir(bcx, unit);

    let mut shared_hasher = StableHasher::new();

    METADATA_VERSION.hash(&mut shared_hasher);

    let ws_root = if unit.is_std {
        // SourceId for stdlib crates is an absolute path inside the sysroot.
        // Pass the sysroot as workspace root so that we hash a relative path.
        // This avoids the metadata hash changing depending on where the user installed rustc.
        &bcx.target_data.get_info(unit.kind).unwrap().sysroot
    } else {
        bcx.ws.root()
    };

    // Unique metadata per (name, source, version) triple. This'll allow us
    // to pull crates from anywhere without worrying about conflicts.
    unit.pkg
        .package_id()
        .stable_hash(ws_root)
        .hash(&mut shared_hasher);

    if bcx.ws.shared_registry_cache_enabled()
        && unit.pkg.package_id().source_id().is_remote_registry()
        && let Some(source_id) = bcx
            .packages
            .sources()
            .get(unit.pkg.package_id().source_id())
            .map(|source| source.replaced_source_id())
    {
        // Source replacement deliberately maps packages back to the original registry identity.
        // Include the actual remote source and archive checksum so distinct mirrors cannot share
        // an artifact merely because they publish the same package name and version. Dependency
        // metadata below recursively carries the same provenance into each reverse dependency.
        source_id.stable_hash(ws_root, &mut shared_hasher);
        unit.pkg.summary().checksum().hash(&mut shared_hasher);
    }

    // Also mix in enabled features to our metadata. This'll ensure that
    // when changing feature sets each lib is separately cached.
    unit.features.hash(&mut shared_hasher);

    // Throw in the profile we're compiling with. This helps caching
    // `panic=abort` and `panic=unwind` artifacts, additionally with various
    // settings like debuginfo and whatnot.
    unit.profile.hash(&mut shared_hasher);
    let shared_stages = crate::compiler::unit_uses_ohm_shared_stages(build_runner, unit);
    if shared_stages {
        // A stable compiler identity also selects the same rustc incremental
        // directory. Keep the real mode in Cargo's unit ID below so a checked
        // rmeta never satisfies a build or overwrites a built artifact.
        CompileMode::Build.hash(&mut shared_hasher);
        "ohm-shared-stages-v1".hash(&mut shared_hasher);
    } else {
        unit.mode.hash(&mut shared_hasher);
    }
    build_runner.lto[unit].hash(&mut shared_hasher);

    // Artifacts compiled for the host should have a different
    // metadata piece than those compiled for the target, so make sure
    // we throw in the unit's `kind` as well.  Use `fingerprint_hash`
    // so that the StableHash doesn't change based on the pathnames
    // of the custom target JSON spec files.
    unit.kind.fingerprint_hash().hash(&mut shared_hasher);

    // Finally throw in the target name/kind. This ensures that concurrent
    // compiles of targets in the same crate don't collide.
    unit.target.name().hash(&mut shared_hasher);
    unit.target.kind().hash(&mut shared_hasher);

    hash_rustc_version(bcx, &mut shared_hasher, unit);

    if build_runner.bcx.ws.is_member(&unit.pkg) {
        // This is primarily here for clippy. This ensures that the clippy
        // artifacts are separate from the `check` ones.
        if let Some(path) = &build_runner.bcx.rustc().workspace_wrapper {
            path.hash(&mut shared_hasher);
        }
    }

    // Seed the contents of `__CARGO_DEFAULT_LIB_METADATA` to the hasher if present.
    // This should be the release channel, to get a different hash for each channel.
    if let Ok(ref channel) = build_runner
        .bcx
        .gctx
        .get_env("__CARGO_DEFAULT_LIB_METADATA")
    {
        channel.hash(&mut shared_hasher);
    }

    // std units need to be kept separate from user dependencies. std crates
    // are differentiated in the Unit with `is_std` (for things like
    // `-Zforce-unstable-if-unmarked`), so they are always built separately.
    // This isn't strictly necessary for build dependencies which probably
    // don't need unstable support. A future experiment might be to set
    // `is_std` to false for build dependencies so that they can be shared
    // with user dependencies.
    unit.is_std.hash(&mut shared_hasher);

    // While we don't hash RUSTFLAGS because it may contain absolute paths that
    // hurts reproducibility, we track whether a unit's RUSTFLAGS is from host
    // config, so that we can generate a different metadata hash for runtime
    // and compile-time units.
    //
    // HACK: This is a temporary hack for fixing rust-lang/cargo#14253
    // Need to find a long-term solution to replace this fragile workaround.
    // See https://github.com/rust-lang/cargo/pull/14432#discussion_r1725065350
    if unit.kind.is_host() && !bcx.gctx.target_applies_to_host().unwrap_or_default() {
        let host_info = bcx.target_data.info(CompileKind::Host);
        let target_configs_are_different = unit.rustflags != host_info.rustflags
            || unit.rustdocflags != host_info.rustdocflags
            || bcx
                .target_data
                .target_config(CompileKind::Host)
                .links_overrides
                != unit.links_overrides;
        target_configs_are_different.hash(&mut shared_hasher);
    }

    let mut c_metadata_hasher = shared_hasher.clone();
    // Mix in the target-metadata of all the dependencies of this target.
    let mut dep_c_metadata_hashes = deps_metadata
        .iter()
        .map(|m| m.c_metadata)
        .collect::<Vec<_>>();
    dep_c_metadata_hashes.sort();
    dep_c_metadata_hashes.hash(&mut c_metadata_hasher);

    let mut unit_id_hasher = shared_hasher.clone();
    if shared_stages {
        unit.mode.hash(&mut unit_id_hasher);
    }
    // Mix in the target-metadata of all the dependencies of this target.
    let mut dep_unit_id_hashes = deps_metadata.iter().map(|m| m.unit_id).collect::<Vec<_>>();
    dep_unit_id_hashes.sort();
    dep_unit_id_hashes.hash(&mut unit_id_hasher);
    // Avoid trashing the caches on RUSTFLAGS changing via `unit_id`
    //
    // Limited to `unit_id` to help with reproducible build / PGO issues.
    let default = Vec::new();
    let extra_args = build_runner.bcx.extra_args_for(unit).unwrap_or(&default);
    if !has_remap_path_prefix(&extra_args) {
        extra_args.hash(&mut unit_id_hasher);
    }
    if unit.mode.is_doc() || unit.mode.is_doc_scrape() {
        if !has_remap_path_prefix(&unit.rustdocflags) {
            unit.rustdocflags.hash(&mut unit_id_hasher);
        }
    } else {
        if !has_remap_path_prefix(&unit.rustflags) {
            unit.rustflags.hash(&mut unit_id_hasher);
        }
    }
    // A package can be checked directly or consumed by another checked unit.
    // Keep the unhashed terminal artifact separate without changing its symbol
    // metadata, so switching between those roles does not evict either cache.
    if crate::compiler::unit_suppresses_default_public_api_hash(build_runner, unit) {
        "ohm-terminal-check-no-public-api-hash".hash(&mut unit_id_hasher);
    }
    if crate::compiler::unit_uses_ohm_incremental_codegen(build_runner, unit) {
        "ohm-incremental-codegen-defaults".hash(&mut unit_id_hasher);
    }
    if crate::compiler::unit_uses_ohm_incremental_mono_partitions(build_runner, unit) {
        "ohm-incremental-mono-partition-defaults".hash(&mut unit_id_hasher);
    }

    let c_metadata = UnitHash(Hasher::finish(&c_metadata_hasher));
    let unit_id = UnitHash(Hasher::finish(&unit_id_hasher));

    Metadata {
        unit_id,
        c_metadata,
        c_extra_filename,
        pkg_dir,
    }
}

/// HACK: Detect the *potential* presence of `--remap-path-prefix`
///
/// As CLI parsing is contextual and dependent on the CLI definition to understand the context, we
/// can't say for sure whether `--remap-path-prefix` is present, so we guess if anything looks like
/// it.
/// If we could, we'd strip it out for hashing.
/// Instead, we use this to avoid hashing rustflags if it might be present to avoid the risk of taking
/// a flag that is trying to make things reproducible and making things less reproducible by the
/// `-Cextra-filename` showing up in the rlib, even with `split-debuginfo`.
fn has_remap_path_prefix(args: &[String]) -> bool {
    args.iter()
        .any(|s| s.starts_with("--remap-path-prefix=") || s == "--remap-path-prefix")
}

/// Hash the version of rustc being used during the build process.
fn hash_rustc_version(bcx: &BuildContext<'_, '_>, hasher: &mut StableHasher, unit: &Unit) {
    let vers = &bcx.rustc().version;
    if vers.pre.is_empty() || bcx.gctx.cli_unstable().separate_nightlies {
        // For stable, keep the artifacts separate. This helps if someone is
        // testing multiple versions, to avoid recompiles. Note though that for
        // cross-compiled builds the `host:` line of `verbose_version` is
        // omitted since rustc should produce the same output for each target
        // regardless of the host.
        for line in bcx.rustc().verbose_version.lines() {
            if unit.kind.is_host() || !line.starts_with("host: ") {
                line.hash(hasher);
            }
        }
        return;
    }
    // On "nightly"/"beta"/"dev"/etc, keep each "channel" separate. Don't hash
    // the date/git information, so that whenever someone updates "nightly",
    // they won't have a bunch of stale artifacts in the target directory.
    //
    // This assumes that the first segment is the important bit ("nightly",
    // "beta", "dev", etc.). Skip other parts like the `.3` in `-beta.3`.
    vers.pre.split('.').next().hash(hasher);
    // Keep "host" since some people switch hosts to implicitly change
    // targets, (like gnu vs musl or gnu vs msvc). In the future, we may want
    // to consider hashing `unit.kind.short_name()` instead.
    if unit.kind.is_host() {
        bcx.rustc().host.hash(hasher);
    }
    // None of the other lines are important. Currently they are:
    // binary: rustc  <-- or "rustdoc"
    // commit-hash: 38114ff16e7856f98b2b4be7ab4cd29b38bed59a
    // commit-date: 2020-03-21
    // host: x86_64-apple-darwin
    // release: 1.44.0-nightly
    // LLVM version: 9.0
    //
    // The backend version ("LLVM version") might become more relevant in
    // the future when cranelift sees more use, and people want to switch
    // between different backends without recompiling.
}

/// Returns whether or not this unit should use a hash in the filename to make it unique.
fn use_extra_filename(bcx: &BuildContext<'_, '_>, unit: &Unit) -> bool {
    if unit.mode.is_doc_test() || unit.mode.is_doc() {
        // Doc tests do not have metadata.
        return false;
    }
    if bcx.gctx.cli_unstable().build_dir_new_layout {
        if unit.mode.is_any_test() || unit.mode.is_check() {
            // These always use metadata.
            return true;
        }

        if unit.target.is_custom_build() {
            // Build scripts never use metadata
            return false;
        }
        // No metadata in these cases:
        //
        // - dylib, cdylib, executable: `pkg_dir` avoids collisions for us and rustc isn't
        // looking these up by `-Cextra-filename`
        //
        // The __CARGO_DEFAULT_LIB_METADATA env var is used to override this to
        // force metadata in the hash. This is only used for building libstd. For
        // example, if libstd is placed in a common location, we don't want a file
        // named /usr/lib/libstd.so which could conflict with other rustc
        // installs. In addition it prevents accidentally loading a libstd of a
        // different compiler at runtime.
        // See https://github.com/rust-lang/cargo/issues/3005
        if (unit.target.is_dylib() || unit.target.is_cdylib() || unit.target.is_executable())
            && bcx.gctx.get_env("__CARGO_DEFAULT_LIB_METADATA").is_err()
        {
            return false;
        }
    } else {
        if unit.mode.is_any_test() || unit.mode.is_check() {
            // These always use metadata.
            return true;
        }
        // No metadata in these cases:
        //
        // - dylibs:
        //   - if any dylib names are encoded in executables, so they can't be renamed.
        //   - TODO: Maybe use `-install-name` on macOS or `-soname` on other UNIX systems
        //     to specify the dylib name to be used by the linker instead of the filename.
        // - Windows MSVC executables: The path to the PDB is embedded in the
        //   executable, and we don't want the PDB path to include the hash in it.
        // - wasm32-unknown-emscripten executables: When using emscripten, the path to the
        //   .wasm file is embedded in the .js file, so we don't want the hash in there.
        //
        // This is only done for local packages, as we don't expect to export
        // dependencies.
        //
        // The __CARGO_DEFAULT_LIB_METADATA env var is used to override this to
        // force metadata in the hash. This is only used for building libstd. For
        // example, if libstd is placed in a common location, we don't want a file
        // named /usr/lib/libstd.so which could conflict with other rustc
        // installs. In addition it prevents accidentally loading a libstd of a
        // different compiler at runtime.
        // See https://github.com/rust-lang/cargo/issues/3005
        let short_name = bcx.target_data.short_name(&unit.kind);
        if (unit.target.is_dylib()
            || unit.target.is_cdylib()
            || (unit.target.is_executable() && short_name == "wasm32-unknown-emscripten")
            || (unit.target.is_executable() && short_name.contains("msvc")))
            && unit.pkg.package_id().source_id().is_path()
            && bcx.gctx.get_env("__CARGO_DEFAULT_LIB_METADATA").is_err()
        {
            return false;
        }
    }
    true
}

/// Returns whether or not this unit should use a hash in the pkg_dir to make it unique.
fn use_pkg_dir(bcx: &BuildContext<'_, '_>, unit: &Unit) -> bool {
    if unit.mode.is_doc_test() || unit.mode.is_doc() {
        // Doc tests do not have metadata.
        return false;
    }
    if bcx.gctx.cli_unstable().build_dir_new_layout {
        // These always use metadata.
        return true;
    }
    if unit.mode.is_any_test() || unit.mode.is_check() {
        // These always use metadata.
        return true;
    }
    // No metadata in these cases:
    //
    // - dylibs:
    //   - if any dylib names are encoded in executables, so they can't be renamed.
    //   - TODO: Maybe use `-install-name` on macOS or `-soname` on other UNIX systems
    //     to specify the dylib name to be used by the linker instead of the filename.
    // - Windows MSVC executables: The path to the PDB is embedded in the
    //   executable, and we don't want the PDB path to include the hash in it.
    // - wasm32-unknown-emscripten executables: When using emscripten, the path to the
    //   .wasm file is embedded in the .js file, so we don't want the hash in there.
    //
    // This is only done for local packages, as we don't expect to export
    // dependencies.
    //
    // The __CARGO_DEFAULT_LIB_METADATA env var is used to override this to
    // force metadata in the hash. This is only used for building libstd. For
    // example, if libstd is placed in a common location, we don't want a file
    // named /usr/lib/libstd.so which could conflict with other rustc
    // installs. In addition it prevents accidentally loading a libstd of a
    // different compiler at runtime.
    // See https://github.com/rust-lang/cargo/issues/3005
    let short_name = bcx.target_data.short_name(&unit.kind);
    if (unit.target.is_dylib()
        || unit.target.is_cdylib()
        || (unit.target.is_executable() && short_name == "wasm32-unknown-emscripten")
        || (unit.target.is_executable() && short_name.contains("msvc")))
        && unit.pkg.package_id().source_id().is_path()
        && bcx.gctx.get_env("__CARGO_DEFAULT_LIB_METADATA").is_err()
    {
        return false;
    }
    true
}

#[cfg(test)]
mod shared_registry_tests {
    #[cfg(unix)]
    use super::distribution_llvm_toolchain_path;
    use super::{
        StripInner, apple_executable_profile_uses_external_tools,
        compiler_arguments_use_opaque_execution, compiler_driver_identity_for_sysroot,
        compiler_driver_search_directory_is_safe, compiler_option_uses_opaque_execution,
        configured_environment_has_sensitive_case_alias, native_target_environment_names,
        native_tool_policy_allows_unit, package_implicit_native_tools,
        resolve_effective_executable, rustflags_for_cache_admission,
        sysroot_contains_trusted_objcopy, sysroot_has_custom_codegen_backends,
    };
    use crate::workspace::features::OhmNativeToolTrust;

    #[test]
    fn native_tool_trust_policies_preserve_helper_and_build_script_boundaries() {
        for trust in [
            OhmNativeToolTrust::Strict,
            OhmNativeToolTrust::BuildScripts,
            OhmNativeToolTrust::All,
        ] {
            assert!(native_tool_policy_allows_unit(trust, false, false, true));
            assert!(native_tool_policy_allows_unit(trust, false, true, false));
            assert_eq!(
                native_tool_policy_allows_unit(trust, false, true, true),
                trust != OhmNativeToolTrust::Strict
            );
            assert_eq!(
                native_tool_policy_allows_unit(trust, true, false, true),
                trust == OhmNativeToolTrust::All
            );
            assert_eq!(
                native_tool_policy_allows_unit(trust, true, true, true),
                trust == OhmNativeToolTrust::All
            );
        }
    }

    #[test]
    fn native_target_aliases_preserve_dots_for_external_build_tools() {
        assert_eq!(
            native_target_environment_names("CMAKE", "thumbv8m.main-none-eabi"),
            [
                "CMAKE_thumbv8m.main-none-eabi",
                "CMAKE_thumbv8m.main_none_eabi",
                "CMAKE_thumbv8m_main_none_eabi",
            ]
        );
        assert_eq!(
            native_target_environment_names("CMAKE_TOOLCHAIN_FILE", "thumbv8m.main-none-eabi"),
            [
                "CMAKE_TOOLCHAIN_FILE_thumbv8m.main-none-eabi",
                "CMAKE_TOOLCHAIN_FILE_thumbv8m.main_none_eabi",
                "CMAKE_TOOLCHAIN_FILE_thumbv8m_main_none_eabi",
            ]
        );
    }

    #[test]
    fn implicit_native_tools_remain_scoped_to_their_build_helper_families() {
        let targets = ["thumbv8m.main-none-eabi".to_owned()];
        let compiler_tools = package_implicit_native_tools("cc", &targets);
        assert!(compiler_tools.contains(&"nvcc".to_owned()));
        assert!(compiler_tools.contains(&"thumbv8m.main-none-eabi-gcc".to_owned()));
        assert!(!compiler_tools.contains(&"cmake".to_owned()));

        let cmake_tools = package_implicit_native_tools("cmake", &targets);
        assert!(cmake_tools.contains(&"cmake".to_owned()));
        assert!(cmake_tools.contains(&"make".to_owned()));
        assert!(!cmake_tools.contains(&"pkg-config".to_owned()));

        let pkg_config_tools = package_implicit_native_tools("pkg-config", &targets);
        assert!(pkg_config_tools.contains(&"pkg-config".to_owned()));
        assert!(pkg_config_tools.contains(&"pkgconf".to_owned()));
        assert!(!pkg_config_tools.contains(&"cmake".to_owned()));

        let openssl_tools = package_implicit_native_tools("openssl-src", &targets);
        assert!(openssl_tools.contains(&"make".to_owned()));
        assert!(openssl_tools.contains(&"nasm".to_owned()));
        assert!(!openssl_tools.contains(&"cmake".to_owned()));

        assert!(package_implicit_native_tools("unrelated-registry", &targets).is_empty());
    }

    #[cfg(unix)]
    #[test]
    fn distribution_llvm_tools_require_exact_versioned_system_layouts() {
        for tool in [
            "/usr/lib/llvm-18/bin/clang",
            "/usr/lib/llvm-18/bin/clang-18",
            "/usr/lib/llvm-18.1/bin/clang++-18.1",
            "/usr/lib64/llvm-19/bin/llvm-ar",
            "/usr/lib64/llvm-19/bin/llvm-ranlib-19",
        ] {
            assert!(
                distribution_llvm_toolchain_path(std::path::Path::new(tool)),
                "distribution LLVM executable should be recognized: {tool}"
            );
        }

        for tool in [
            "/usr/lib/llvm-18/bin/opaque-wrapper",
            "/usr/lib/llvm-18/bin/clang-wrapper",
            "/usr/lib/llvm-18/bin/clang-18-wrapper",
            "/usr/lib/llvm-18/bin/nested/clang",
            "/usr/lib/llvm-18/lib/clang",
            "/usr/lib/llvm-/bin/clang",
            "/usr/lib/llvm-18./bin/clang",
            "/usr/lib/llvm-custom/bin/clang",
            "/usr/local/lib/llvm-18/bin/clang",
            "/tmp/llvm-18/bin/clang",
        ] {
            assert!(
                !distribution_llvm_toolchain_path(std::path::Path::new(tool)),
                "untrusted LLVM executable should remain private: {tool}"
            );
        }
    }

    #[test]
    fn windows_configured_environment_cannot_alias_compiler_or_native_tools() {
        for name in [
            "Path",
            "ld_library_path",
            "Rustc_Bootstrap",
            "Rustc_Override_Version_String",
            "sdkroot",
            "cc_AARCH64-UNKNOWN-WINDOWS",
            "RustDoc",
            "cargo_feature_untracked",
        ] {
            let configured = [(name.to_owned(), std::ffi::OsString::from("opaque"))];
            assert!(configured_environment_has_sensitive_case_alias(
                &configured,
                true
            ));
            assert!(!configured_environment_has_sensitive_case_alias(
                &configured,
                false
            ));
        }

        for name in ["PATH", "SDKROOT", "CC_AARCH64_UNKNOWN_WINDOWS"] {
            let configured = [(name.to_owned(), std::ffi::OsString::from("trusted"))];
            assert!(!configured_environment_has_sensitive_case_alias(
                &configured,
                true
            ));
        }
    }

    #[test]
    fn executable_resolution_uses_the_actual_absolute_child_search_path() {
        let directory = tempfile::tempdir().expect("create isolated executable search directory");
        let genuine = directory.path().join("genuine");
        let configured = directory.path().join("configured");
        std::fs::create_dir_all(&genuine).expect("create genuine executable directory");
        std::fs::create_dir_all(&configured).expect("create configured executable directory");
        let filename = if cfg!(windows) {
            "compiler.exe"
        } else {
            "compiler"
        };
        let genuine_compiler = genuine.join(filename);
        let configured_compiler = configured.join(filename);
        std::fs::write(&genuine_compiler, "genuine compiler").expect("write genuine executable");
        std::fs::write(&configured_compiler, "opaque compiler")
            .expect("write configured executable");
        let actual_path = std::env::join_paths([&configured, &genuine])
            .expect("construct configured executable search path");

        assert_eq!(
            resolve_effective_executable(
                std::path::Path::new("compiler"),
                Some(actual_path.as_os_str()),
            )
            .expect("inspect the configured executable path"),
            Some(configured_compiler)
        );
        assert_eq!(
            resolve_effective_executable(&genuine_compiler, None)
                .expect("absolute executables do not require PATH"),
            Some(genuine_compiler)
        );
        assert!(
            resolve_effective_executable(
                std::path::Path::new("relative/compiler"),
                Some(actual_path.as_os_str()),
            )
            .is_err()
        );

        for unsafe_directory in ["", ".", "relative-tools"] {
            let unsafe_path = std::env::join_paths([
                std::path::Path::new(unsafe_directory),
                configured.as_path(),
            ])
            .expect("construct unsafe executable search path");
            assert!(
                resolve_effective_executable(
                    std::path::Path::new("compiler"),
                    Some(unsafe_path.as_os_str()),
                )
                .is_err(),
                "relative search entry {unsafe_directory:?} must not depend on package cwd"
            );
        }
    }

    #[test]
    fn executable_compiler_extensions_and_linker_overrides_are_opaque() {
        for option in [
            "codegen-backend=llvm",
            "codegen_backend=llvm",
            "llvm-plugins=",
            "llvm_plugins=",
            "autodiff=Enable",
            "default-linker-libraries=yes",
            "default_linker_libraries=yes",
            "link-self-contained=-linker",
            "link_self_contained=-linker",
            "linker=opaque-wrapper",
            "linker-flavor=gnu",
            "linker_flavor=gnu",
            "linker-features=+lld",
            "linker_features=+lld",
            "dlltool=opaque-wrapper",
            "link-arg=opaque-argument",
            "link_arg=opaque-argument",
            "link-args=opaque-arguments",
            "link_args=opaque-arguments",
            "pre-link-arg=opaque-argument",
            "pre_link_arg=opaque-argument",
            "pre-link-args=opaque-arguments",
            "pre_link_args=opaque-arguments",
            "linker-plugin-lto=opaque-plugin",
            "linker_plugin_lto=opaque-plugin",
            "@opaque-response-file",
        ] {
            assert!(compiler_option_uses_opaque_execution(option));
        }

        assert!(!compiler_option_uses_opaque_execution("opt-level=2"));
        assert!(!compiler_option_uses_opaque_execution("debuginfo=1"));
    }

    #[test]
    fn bundled_linker_provenance_preserves_explicit_execution_boundaries() {
        let bundled = [
            "-Clinker-features=-lld",
            "-Clink-self-contained=-linker",
            "-Clink-arg=-B/toolchain/lib/rustlib/host/bin/wild-ld",
            "-Clink-arg=-fuse-ld=bfd",
        ]
        .map(str::to_owned);
        let opaque = |flags: &[String], generated: usize| {
            compiler_arguments_use_opaque_execution(
                rustflags_for_cache_admission(flags, &bundled, generated)
                    .iter()
                    .map(String::as_str),
                false,
                false,
                false,
                || false,
            )
        };
        assert!(!opaque(&bundled, bundled.len()));
        assert!(opaque(&bundled, 0));
        assert!(opaque(&bundled, bundled.len() + 1));

        for explicit in ["-Clinker=custom", "-Clink-arg=-fuse-ld=bfd", "@flags"] {
            let mut before = vec![explicit.to_owned()];
            before.extend_from_slice(&bundled);
            assert!(opaque(&before, bundled.len()), "{explicit}");
            let mut after = bundled.to_vec();
            after.push(explicit.to_owned());
            assert!(opaque(&after, bundled.len()), "{explicit}");
        }
        let mut altered = bundled.clone();
        altered[2] = "-Clink-arg=-B/other-toolchain/bin".to_owned();
        assert!(opaque(&altered, bundled.len()));
    }

    #[test]
    fn compiler_argument_spellings_cannot_hide_native_execution() {
        let opaque: &[&[&str]] = &[
            &["-C", "link-arg=--unused"],
            &["-Clink-args=--unused"],
            &["-Cdefault-linker-libraries=yes"],
            &["--codegen=link_self_contained=-linker"],
            &["--codegen", "linker=/opaque/linker"],
            &["--codegen", "linker-flavor=gnu"],
            &["-Clinker_features=+lld"],
            &["--codegen=linker-plugin-lto=/opaque/plugin"],
            &["-C", "dlltool=/opaque/dlltool"],
            &["-Z", "pre-link-arg=--unused"],
            &["-Zpre_link_args=--unused"],
            &["-Z", "llvm-plugins="],
            &["-l", "injected"],
            &["-linjected"],
            &["--library-path", "/opaque/libraries"],
            &["--library-path=/opaque/libraries"],
            &["@opaque-response-file"],
            &["-C", "@opaque-response-file"],
            &["-C"],
            &["-Z"],
            &["--codegen"],
            &["--codegen="],
        ];
        for flags in opaque {
            assert!(
                compiler_arguments_use_opaque_execution(
                    flags.iter().copied(),
                    false,
                    false,
                    false,
                    || false,
                ),
                "opaque compiler arguments were accepted: {flags:?}",
            );
            assert!(
                compiler_arguments_use_opaque_execution(
                    flags.iter().copied(),
                    true,
                    false,
                    false,
                    || false,
                ),
                "executable compiler arguments were accepted: {flags:?}",
            );
        }

        let safe: &[&[&str]] = &[
            &["-C", "opt-level=2"],
            &["-Cdebuginfo=1"],
            &["--codegen", "opt-level=3"],
            &["--codegen=debuginfo=1"],
            &["-Zunstable-options"],
            &["-L", "native=/verified/native"],
            &["-Lframework=/verified/framework"],
        ];
        for flags in safe {
            assert!(
                !compiler_arguments_use_opaque_execution(
                    flags.iter().copied(),
                    false,
                    false,
                    false,
                    || false,
                ),
                "ordinary compiler arguments were rejected: {flags:?}",
            );
        }

        for flags in [
            &["-L", "native=/untrusted/native"][..],
            &["-Lnative=/untrusted/native"][..],
            &["-L", "framework=/untrusted/framework"][..],
            &["-Lframework=/untrusted/framework"][..],
        ] {
            assert!(
                compiler_arguments_use_opaque_execution(
                    flags.iter().copied(),
                    true,
                    false,
                    false,
                    || false,
                ),
                "executable native search paths were accepted: {flags:?}",
            );
        }

        assert!(!compiler_arguments_use_opaque_execution(
            ["-C", "opt-level=2"],
            true,
            true,
            false,
            || false,
        ));

        for flags in [
            &["-Cstrip=debuginfo"][..],
            &["--codegen", "strip=symbols"][..],
            &["-C", "split-debuginfo=packed"][..],
            &["--codegen=split_debuginfo=packed"][..],
        ] {
            assert!(
                compiler_arguments_use_opaque_execution(
                    flags.iter().copied(),
                    true,
                    true,
                    true,
                    || false,
                ),
                "Apple auxiliary compiler tools were accepted: {flags:?}",
            );
            assert!(
                !compiler_arguments_use_opaque_execution(
                    flags.iter().copied(),
                    true,
                    false,
                    false,
                    || false,
                ),
                "non-Apple compiler arguments were rejected: {flags:?}",
            );
        }

        for flags in [
            &["-g"][..],
            &["-Cdebuginfo=1"][..],
            &["-C", "debuginfo=2"][..],
            &["--codegen=debuginfo=full"][..],
        ] {
            assert!(
                compiler_arguments_use_opaque_execution(
                    flags.iter().copied(),
                    true,
                    true,
                    false,
                    || true,
                ),
                "implicit Apple packed debuginfo was accepted: {flags:?}",
            );
            assert!(
                !compiler_arguments_use_opaque_execution(
                    flags.iter().copied(),
                    true,
                    true,
                    true,
                    || true,
                ),
                "already-configured Apple debuginfo was rejected: {flags:?}",
            );
        }

        for flags in [
            &["-Cstrip=none"][..],
            &["-Cdebuginfo=0"][..],
            &["-Cdebuginfo=none"][..],
            &["-Csplit-debuginfo=off"][..],
            &["-Csplit_debuginfo=unpacked"][..],
        ] {
            assert!(
                !compiler_arguments_use_opaque_execution(
                    flags.iter().copied(),
                    true,
                    true,
                    false,
                    || false,
                ),
                "safe Apple compiler arguments were rejected: {flags:?}",
            );
        }

        for flags in [
            &["-Cstrip=debuginfo"][..],
            &["--codegen", "strip=symbols"][..],
        ] {
            assert!(
                !compiler_arguments_use_opaque_execution(
                    flags.iter().copied(),
                    true,
                    true,
                    false,
                    || true,
                ),
                "trusted toolchain objcopy was rejected: {flags:?}",
            );
        }
    }

    #[test]
    fn apple_executable_profiles_reject_only_external_native_tools() {
        assert!(apple_executable_profile_uses_external_tools(
            StripInner::Named("debuginfo".into()),
            None,
            false,
            false,
        ));
        assert!(apple_executable_profile_uses_external_tools(
            StripInner::Named("symbols".into()),
            None,
            false,
            false,
        ));
        assert!(!apple_executable_profile_uses_external_tools(
            StripInner::Named("symbols".into()),
            None,
            false,
            true,
        ));
        assert!(apple_executable_profile_uses_external_tools(
            StripInner::None,
            Some("packed"),
            true,
            true,
        ));
        assert!(!apple_executable_profile_uses_external_tools(
            StripInner::None,
            Some("packed"),
            false,
            true,
        ));
        assert!(!apple_executable_profile_uses_external_tools(
            StripInner::None,
            Some("unpacked"),
            true,
            true,
        ));
        assert!(!apple_executable_profile_uses_external_tools(
            StripInner::None,
            Some("off"),
            true,
            true,
        ));
    }

    #[cfg(unix)]
    #[test]
    fn apple_objcopy_must_be_executable_and_remain_inside_the_selected_sysroot() {
        use std::os::unix::fs::{PermissionsExt, symlink};

        let sysroot = tempfile::tempdir().expect("create isolated compiler sysroot");
        let host = "aarch64-apple-darwin";
        let bin = sysroot
            .path()
            .join("lib")
            .join("rustlib")
            .join(host)
            .join("bin");
        std::fs::create_dir_all(&bin).expect("create isolated compiler tool directory");
        let executable = bin.join("rust-objcopy");

        assert!(!sysroot_contains_trusted_objcopy(sysroot.path(), host));

        std::fs::write(&executable, "authenticated toolchain executable")
            .expect("create isolated compiler tool");
        std::fs::set_permissions(&executable, std::fs::Permissions::from_mode(0o644))
            .expect("clear isolated tool executable permissions");
        assert!(!sysroot_contains_trusted_objcopy(sysroot.path(), host));

        std::fs::set_permissions(&executable, std::fs::Permissions::from_mode(0o755))
            .expect("set isolated tool executable permissions");
        assert!(sysroot_contains_trusted_objcopy(sysroot.path(), host));

        std::fs::set_permissions(&bin, std::fs::Permissions::from_mode(0o775))
            .expect("set isolated tool directory group-write permissions");
        assert!(!sysroot_contains_trusted_objcopy(sysroot.path(), host));
        std::fs::set_permissions(&bin, std::fs::Permissions::from_mode(0o755))
            .expect("restore isolated tool directory permissions");

        std::fs::set_permissions(&executable, std::fs::Permissions::from_mode(0o775))
            .expect("set isolated tool group-write permissions");
        assert!(!sysroot_contains_trusted_objcopy(sysroot.path(), host));

        std::fs::remove_file(&executable).expect("remove isolated compiler tool");
        let external = tempfile::tempdir().expect("create external compiler tool directory");
        let external_tool = external.path().join("external-objcopy");
        std::fs::write(&external_tool, "external unauthenticated executable")
            .expect("create external compiler tool");
        std::fs::set_permissions(&external_tool, std::fs::Permissions::from_mode(0o755))
            .expect("set external tool executable permissions");
        symlink(&external_tool, &executable).expect("create escaped compiler tool symlink");
        assert!(!sysroot_contains_trusted_objcopy(sysroot.path(), host));
    }

    #[test]
    fn sysroot_default_codegen_backends_cannot_be_shared() {
        let sysroot = tempfile::tempdir().expect("create isolated compiler sysroot");
        let host = "isolated-host-triple";

        assert!(!sysroot_has_custom_codegen_backends(sysroot.path(), host));

        let backends = sysroot
            .path()
            .join("lib")
            .join("rustlib")
            .join(host)
            .join("codegen-backends");
        std::fs::create_dir_all(&backends).expect("create isolated external backend directory");
        std::fs::write(
            backends.join(format!(
                "{}rustc_codegen_mock{}",
                std::env::consts::DLL_PREFIX,
                std::env::consts::DLL_SUFFIX
            )),
            "isolated externally loaded compiler backend",
        )
        .expect("write mock external compiler backend");

        assert!(sysroot_has_custom_codegen_backends(sysroot.path(), host));
    }

    #[test]
    fn runtime_compiler_driver_changes_invalidate_its_identity() {
        let sysroot = tempfile::tempdir().expect("create isolated compiler sysroot");
        let directory = sysroot
            .path()
            .join(if cfg!(windows) { "bin" } else { "lib" });
        std::fs::create_dir_all(&directory).expect("create isolated compiler library directory");
        let driver = directory.join(format!(
            "{}rustc_driver-test{}",
            std::env::consts::DLL_PREFIX,
            std::env::consts::DLL_SUFFIX
        ));

        assert!(compiler_driver_identity_for_sysroot(sysroot.path()).is_none());
        std::fs::write(&driver, "first driver").expect("write isolated compiler implementation");
        let initial = compiler_driver_identity_for_sysroot(sysroot.path())
            .expect("identify the isolated compiler implementation");
        std::fs::write(&driver, "replacement compiler implementation")
            .expect("replace isolated compiler implementation");
        let replaced = compiler_driver_identity_for_sysroot(sysroot.path())
            .expect("identify the replaced compiler implementation");
        assert_ne!(initial, replaced);

        std::fs::remove_file(&driver).expect("remove isolated compiler implementation");
        assert!(compiler_driver_identity_for_sysroot(sysroot.path()).is_none());
    }

    #[test]
    fn ambiguous_runtime_compiler_drivers_cannot_be_shared() {
        let sysroot = tempfile::tempdir().expect("create isolated compiler sysroot");
        let directory = sysroot
            .path()
            .join(if cfg!(windows) { "bin" } else { "lib" });
        std::fs::create_dir_all(&directory).expect("create isolated compiler library directory");

        for name in ["first", "second"] {
            let driver = directory.join(format!(
                "{}rustc_driver-{name}{}",
                std::env::consts::DLL_PREFIX,
                std::env::consts::DLL_SUFFIX
            ));
            std::fs::write(driver, name).expect("write ambiguous compiler implementation");
        }

        assert!(compiler_driver_identity_for_sysroot(sysroot.path()).is_none());
    }

    #[test]
    fn loader_search_directories_cannot_shadow_the_verified_compiler_driver() {
        let sysroot = tempfile::tempdir().expect("create isolated compiler sysroot");
        let runtime = sysroot
            .path()
            .join(if cfg!(windows) { "bin" } else { "lib" });
        let search = sysroot.path().join("external-loader-search");
        std::fs::create_dir_all(&runtime).expect("create the verified runtime directory");
        std::fs::create_dir_all(&search)
            .expect("create an initially empty loader search directory");
        let filename = format!(
            "{}rustc_driver-identity{}",
            std::env::consts::DLL_PREFIX,
            std::env::consts::DLL_SUFFIX
        );
        let genuine = runtime.join(&filename);
        std::fs::write(&genuine, "genuine compiler driver").expect("write the genuine driver");
        let genuine = genuine
            .canonicalize()
            .expect("canonicalize the genuine driver");

        assert!(compiler_driver_search_directory_is_safe(&search, &genuine));
        std::fs::write(search.join(&filename), "shadow compiler driver")
            .expect("write a same-basename external compiler driver");
        assert!(!compiler_driver_search_directory_is_safe(&search, &genuine));
        std::fs::remove_file(search.join(&filename)).expect("remove the external compiler driver");
        assert!(compiler_driver_search_directory_is_safe(&search, &genuine));
        assert!(compiler_driver_search_directory_is_safe(&runtime, &genuine));
    }

    #[cfg(unix)]
    #[test]
    fn canonical_driver_aliases_remain_safe_in_loader_search_directories() {
        use std::os::unix::fs::symlink;

        let directory = tempfile::tempdir().expect("create isolated compiler sysroot");
        let runtime = directory.path().join("lib");
        let aliases = directory.path().join("aliases");
        std::fs::create_dir_all(&runtime).expect("create the verified runtime directory");
        std::fs::create_dir_all(&aliases).expect("create the aliased search directory");
        let filename = format!(
            "{}rustc_driver-identity{}",
            std::env::consts::DLL_PREFIX,
            std::env::consts::DLL_SUFFIX
        );
        let genuine = runtime.join(&filename);
        std::fs::write(&genuine, "genuine compiler driver").expect("write the genuine driver");
        let genuine = genuine
            .canonicalize()
            .expect("canonicalize the genuine driver");
        symlink(&genuine, aliases.join(filename)).expect("alias the genuine compiler driver");

        assert!(compiler_driver_search_directory_is_safe(&aliases, &genuine));
    }
}
