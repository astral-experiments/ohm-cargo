//! Constructs the dependency graph for compilation.
//!
//! Rust code is typically organized as a set of Cargo packages. The
//! dependencies between the packages themselves are stored in the
//! [`Resolve`] struct. However, we can't use that information as is for
//! compilation! A package typically contains several targets, or crates,
//! and these targets has inter-dependencies. For example, you need to
//! compile the `lib` target before the `bin` one, and you need to compile
//! `build.rs` before either of those.
//!
//! So, we need to lower the `Resolve`, which specifies dependencies between
//! *packages*, to a graph of dependencies between their *targets*, and this
//! is exactly what this module is doing! Well, almost exactly: another
//! complication is that we might want to compile the same target several times
//! (for example, with and without tests), so we actually build a dependency
//! graph of [`Unit`]s, which capture these properties.

use crate::util::data_structures::{HashMap, HashSet};

use std::cell::{OnceCell, RefCell};

use tracing::trace;

use crate::CargoResult;
use crate::compiler::OHM_COMPILER_LOADER_INJECTION_ENVIRONMENT;
use crate::compiler::UserIntent;
use crate::compiler::artifact::match_artifacts_kind_with_targets;
use crate::compiler::build_runner::{
    OHM_RUSTC_LOG_ENVIRONMENT, resolve_effective_compiler_executable,
};
use crate::compiler::unit_graph::{UnitDep, UnitGraph};
use crate::compiler::{CompileKind, CompileMode, CrateType, RustcTargetData, Unit, UnitInterner};
use crate::ops::resolve_all_features;
use crate::resolver::features::{FeaturesFor, ResolvedFeatures};
use crate::resolver::{ForceAllTargets, HasDevUnits, Resolve};
use crate::sources::CRATES_IO_INDEX;
use crate::sources::registry::CRATES_IO_HTTP_INDEX;
use crate::util::GlobalContext;
use crate::util::Unhashed;
use crate::util::interning::InternedString;
use crate::workspace::dependency::{Artifact, ArtifactKind, ArtifactTarget, DepKind};
use crate::workspace::features::OhmProcMacroTrust;
use crate::workspace::profiles::{Profile, Profiles, UnitFor};
use crate::workspace::{
    Dependency, Feature, Package, PackageId, PackageSet, SourceId, Target, TargetKind, Workspace,
};

const IS_NO_ARTIFACT_DEP: Option<&'static Artifact> = None;

/// Collection of stuff used while creating the [`UnitGraph`].
struct State<'a, 'gctx> {
    ws: &'a Workspace<'gctx>,
    gctx: &'gctx GlobalContext,
    /// Stores the result of building the [`UnitGraph`].
    unit_dependencies: UnitGraph,
    package_set: &'a PackageSet<'gctx>,
    usr_resolve: &'a Resolve,
    usr_features: &'a ResolvedFeatures,
    /// Like `usr_resolve` but for building standard library (`-Zbuild-std`).
    std_resolve: Option<&'a Resolve>,
    /// Like `usr_features` but for building standard library (`-Zbuild-std`).
    std_features: Option<&'a ResolvedFeatures>,
    /// `true` while generating the dependencies for the standard library.
    is_std: bool,
    /// The high-level operation requested by the user.
    /// Used for preventing from building lib thrice.
    intent: UserIntent,
    target_data: &'a RustcTargetData<'gctx>,
    profiles: &'a Profiles,
    interner: &'a UnitInterner,
    // Units for `-Zrustdoc-scrape-examples`.
    scrape_units: &'a [Unit],

    /// A set of edges in `unit_dependencies` where (a, b) means that the
    /// dependency from a to b was added purely because it was a dev-dependency.
    /// This is used during `connect_run_custom_build_deps`.
    dev_dependency_edges: HashSet<(Unit, Unit)>,

    /// Whether this graph may tentatively reuse complete registry builds.
    /// Exact artifact and fingerprint validation happens after graph creation.
    reuse_built_registry_dependencies: bool,

    /// Packages whose existing build artifacts failed exact reuse validation.
    /// They and their stale dependents retain ordinary metadata-only checks.
    rejected_built_registry_packages: HashSet<PackageId>,

    /// Compiler identity and global policy do not vary between registry targets in this graph.
    trusted_registry_reuse_compiler: OnceCell<bool>,

    /// Whether the dependencies actually compiled for a registry unit form an
    /// immutable closure for its active platform, features, and target kind.
    immutable_registry_closures: RefCell<HashMap<(Unit, bool), bool>>,
}

/// A boolean-like to indicate if a `Unit` is an artifact or not.
#[derive(Copy, Clone, Hash, PartialEq, Eq, PartialOrd, Ord)]
pub enum IsArtifact {
    Yes,
    No,
}

impl IsArtifact {
    pub fn is_true(&self) -> bool {
        matches!(self, IsArtifact::Yes)
    }
}

/// Then entry point for building a dependency graph of compilation units.
///
/// You can find some information for arguments from doc of [`State`].
#[tracing::instrument(skip_all)]
pub fn build_unit_dependencies<'a, 'gctx>(
    ws: &'a Workspace<'gctx>,
    package_set: &'a PackageSet<'gctx>,
    resolve: &'a Resolve,
    features: &'a ResolvedFeatures,
    std_resolve: Option<&'a (Resolve, ResolvedFeatures)>,
    roots: &[Unit],
    scrape_units: &[Unit],
    std_roots: &HashMap<CompileKind, Vec<Unit>>,
    intent: UserIntent,
    target_data: &'a RustcTargetData<'gctx>,
    profiles: &'a Profiles,
    interner: &'a UnitInterner,
    reuse_built_registry_dependencies: bool,
    rejected_built_registry_packages: &HashSet<PackageId>,
) -> CargoResult<UnitGraph> {
    if roots.is_empty() {
        // If -Zbuild-std, don't attach units if there is nothing to build.
        // Otherwise, other parts of the code may be confused by seeing units
        // in the dep graph without a root.
        return Ok(HashMap::default());
    }
    let (std_resolve, std_features) = match std_resolve {
        Some((r, f)) => (Some(r), Some(f)),
        None => (None, None),
    };
    let mut state = State {
        ws,
        gctx: ws.gctx(),
        unit_dependencies: HashMap::default(),
        package_set,
        usr_resolve: resolve,
        usr_features: features,
        std_resolve,
        std_features,
        is_std: false,
        intent,
        target_data,
        profiles,
        interner,
        scrape_units,
        dev_dependency_edges: HashSet::default(),
        reuse_built_registry_dependencies,
        rejected_built_registry_packages: rejected_built_registry_packages.clone(),
        trusted_registry_reuse_compiler: OnceCell::new(),
        immutable_registry_closures: RefCell::default(),
    };

    let std_unit_deps = calc_deps_of_std(&mut state, std_roots)?;

    deps_of_roots(roots, &mut state)?;
    super::links::validate_links(state.resolve(), &state.unit_dependencies)?;
    // Hopefully there aren't any links conflicts with the standard library?

    if let Some(std_unit_deps) = std_unit_deps {
        attach_std_deps(&mut state, std_roots, std_unit_deps);
    }

    connect_run_custom_build_deps(&mut state);

    // Dependencies are used in tons of places throughout the backend, many of
    // which affect the determinism of the build itself. As a result be sure
    // that dependency lists are always sorted to ensure we've always got a
    // deterministic output.
    for (unit, list) in &mut state.unit_dependencies {
        let is_multiple_build_scripts_enabled = unit
            .pkg
            .manifest()
            .unstable_features()
            .require(Feature::multiple_build_scripts())
            .is_ok();

        if is_multiple_build_scripts_enabled {
            list.sort_by_key(|unit_dep| {
                if unit_dep.unit.target.is_custom_build() {
                    // We do not sort build scripts to preserve the user-defined order.
                    // In terms of determinism, we are assuming nothing interferes with order from when the user set it in `Cargo.toml` to here
                    (0, None)
                } else {
                    (1, Some(unit_dep.clone()))
                }
            });
        } else {
            list.sort();
        }
    }
    trace!("ALL UNIT DEPENDENCIES {:#?}", state.unit_dependencies);

    Ok(state.unit_dependencies)
}

/// Compute all the dependencies for the standard library.
fn calc_deps_of_std(
    state: &mut State<'_, '_>,
    std_roots: &HashMap<CompileKind, Vec<Unit>>,
) -> CargoResult<Option<UnitGraph>> {
    if std_roots.is_empty() {
        return Ok(None);
    }
    // Compute dependencies for the standard library.
    state.is_std = true;
    for roots in std_roots.values() {
        deps_of_roots(roots, state)?;
    }
    state.is_std = false;
    Ok(Some(std::mem::take(&mut state.unit_dependencies)))
}

/// Add the standard library units to the `unit_dependencies`.
fn attach_std_deps(
    state: &mut State<'_, '_>,
    std_roots: &HashMap<CompileKind, Vec<Unit>>,
    std_unit_deps: UnitGraph,
) {
    // Attach the standard library as a dependency of every target unit.
    let mut found = false;
    for (unit, deps) in state.unit_dependencies.iter_mut() {
        if !unit.kind.is_host() && !unit.mode.is_run_custom_build() {
            deps.extend(std_roots[&unit.kind].iter().map(|unit| UnitDep {
                unit: unit.clone(),
                unit_for: UnitFor::new_normal(unit.kind),
                extern_crate_name: unit.pkg.name(),
                dep_name: None,
                // TODO: Does this `public` make sense?
                public: true,
                noprelude: true,
                nounused: true,
                // Artificial dependency
                manifest_deps: Unhashed(None),
            }));
            found = true;
        }
    }
    // And also include the dependencies of the standard library itself. Don't
    // include these if no units actually needed the standard library.
    if found {
        for (unit, deps) in std_unit_deps.into_iter() {
            if let Some(other_unit) = state.unit_dependencies.insert(unit, deps) {
                panic!("std unit collision with existing unit: {:?}", other_unit);
            }
        }
    }
}

/// Compute all the dependencies of the given root units.
/// The result is stored in `state.unit_dependencies`.
fn deps_of_roots(roots: &[Unit], state: &mut State<'_, '_>) -> CargoResult<()> {
    for unit in roots.iter() {
        // Dependencies of tests/benches should not have `panic` set.
        // We check the user intent to see if we are running in `cargo test` in
        // which case we ensure all dependencies have `panic` cleared, and
        // avoid building the lib thrice (once with `panic`, once without, once
        // for `--test`). In particular, the lib included for Doc tests and
        // examples are `Build` mode here.
        let root_compile_kind = unit.kind;
        let unit_for = if unit.mode.is_any_test() || state.intent.is_rustc_test() {
            if unit.target.proc_macro() {
                // Special-case for proc-macros, which are forced to for-host
                // since they need to link with the proc_macro crate.
                UnitFor::new_host_test(state.gctx, root_compile_kind)
            } else {
                UnitFor::new_test(state.gctx, root_compile_kind)
            }
        } else if unit.target.is_custom_build() {
            // This normally doesn't happen, except `clean` aggressively
            // generates all units.
            UnitFor::new_host(false, root_compile_kind)
        } else if unit.target.proc_macro() {
            UnitFor::new_host(true, root_compile_kind)
        } else if unit.target.for_host() {
            // Plugin should never have panic set.
            UnitFor::new_compiler(root_compile_kind)
        } else {
            UnitFor::new_normal(root_compile_kind)
        };
        deps_of(unit, state, unit_for)?;
    }

    Ok(())
}

/// Compute the dependencies of a single unit, recursively computing all
/// transitive dependencies.
///
/// The result is stored in `state.unit_dependencies`.
fn deps_of(unit: &Unit, state: &mut State<'_, '_>, unit_for: UnitFor) -> CargoResult<()> {
    // Currently the `unit_dependencies` map does not include `unit_for`. This should
    // be safe for now. `TestDependency` only exists to clear the `panic`
    // flag, and you'll never ask for a `unit` with `panic` set as a
    // `TestDependency`. `CustomBuild` should also be fine since if the
    // requested unit's settings are the same as `Any`, `CustomBuild` can't
    // affect anything else in the hierarchy.
    if !state.unit_dependencies.contains_key(unit) {
        let unit_deps = compute_deps(unit, state, unit_for)?;
        state
            .unit_dependencies
            .insert(unit.clone(), unit_deps.clone());
        for unit_dep in unit_deps {
            deps_of(&unit_dep.unit, state, unit_dep.unit_for)?;
        }
    }
    Ok(())
}

/// Returns the direct unit dependencies for the given `Unit`.
fn compute_deps(
    unit: &Unit,
    state: &mut State<'_, '_>,
    unit_for: UnitFor,
) -> CargoResult<Vec<UnitDep>> {
    if unit.mode.is_run_custom_build() {
        return compute_deps_custom_build(unit, unit_for, state);
    } else if unit.mode.is_doc() {
        // Note: this does not include doc test.
        return compute_deps_doc(unit, state, unit_for);
    }

    let mut ret = Vec::new();
    let mut dev_deps = Vec::new();
    for (dep_pkg_id, deps) in state.deps(unit, unit_for) {
        let Some(dep_lib) = calc_artifact_deps(unit, unit_for, dep_pkg_id, &deps, state, &mut ret)?
        else {
            continue;
        };
        let dep_pkg = state.get(dep_pkg_id);
        let dep_unit_for = unit_for.with_dependency(unit, dep_lib, unit_for.root_compile_kind());
        let mut mode = check_or_build_mode(unit.mode, dep_lib);
        if mode.is_check()
            && state.can_reuse_built_registry_dependency(unit, dep_pkg_id, dep_lib, dep_unit_for)
        {
            mode = CompileMode::Build;
        }

        let manifest_deps = deps.iter().map(|d| (*d).clone()).collect::<Vec<_>>();

        let start = ret.len();
        if state.gctx.cli_unstable().dual_proc_macros
            && dep_lib.proc_macro()
            && !unit.kind.is_host()
        {
            let unit_dep = new_unit_dep(
                state,
                unit,
                dep_pkg,
                dep_lib,
                Some(manifest_deps.clone()),
                dep_unit_for,
                unit.kind,
                mode,
                IS_NO_ARTIFACT_DEP,
            )?;
            ret.push(unit_dep);
            let unit_dep = new_unit_dep(
                state,
                unit,
                dep_pkg,
                dep_lib,
                Some(manifest_deps),
                dep_unit_for,
                CompileKind::Host,
                mode,
                IS_NO_ARTIFACT_DEP,
            )?;
            ret.push(unit_dep);
        } else {
            let unit_dep = new_unit_dep(
                state,
                unit,
                dep_pkg,
                dep_lib,
                Some(manifest_deps),
                dep_unit_for,
                unit.kind.for_target(dep_lib),
                mode,
                IS_NO_ARTIFACT_DEP,
            )?;
            ret.push(unit_dep);
        }

        // If the unit added was a dev-dependency unit, then record that in the
        // dev-dependencies array. We'll add this to
        // `state.dev_dependency_edges` at the end and process it later in
        // `connect_run_custom_build_deps`.
        if deps.iter().all(|d| !d.is_transitive()) {
            for dep in ret[start..].iter() {
                dev_deps.push((unit.clone(), dep.unit.clone()));
            }
        }
    }
    state.dev_dependency_edges.extend(dev_deps);

    // If this target is a build script, then what we've collected so far is
    // all we need. If this isn't a build script, then it depends on the
    // build script if there is one.
    if unit.target.is_custom_build() {
        return Ok(ret);
    }
    ret.extend(
        dep_build_script(unit, unit_for, state)?
            .into_iter()
            .flatten(),
    );

    // If this target is a binary, test, example, etc, then it depends on
    // the library of the same package. The call to `resolve.deps` above
    // didn't include `pkg` in the return values, so we need to special case
    // it here and see if we need to push `(pkg, pkg_lib_target)`.
    if unit.target.is_lib() && unit.mode != CompileMode::Doctest {
        return Ok(ret);
    }
    ret.extend(maybe_lib(unit, state, unit_for)?);

    // If any integration tests/benches are being run, make sure that
    // binaries are built as well.
    if !unit.mode.is_check()
        && unit.mode.is_any_test()
        && (unit.target.is_test() || unit.target.is_bench())
    {
        let id = unit.pkg.package_id();
        ret.extend(
            unit.pkg
                .targets()
                .iter()
                .filter(|t| {
                    // Skip binaries with required features that have not been selected.
                    match t.required_features() {
                        Some(rf) if t.is_bin() => {
                            let features = resolve_all_features(
                                state.resolve(),
                                state.features(),
                                state.package_set,
                                id,
                                HasDevUnits::No,
                                &[unit.kind],
                                state.target_data,
                                ForceAllTargets::No,
                            );
                            rf.iter().all(|f| features.contains(f))
                        }
                        None if t.is_bin() => true,
                        _ => false,
                    }
                })
                .map(|t| {
                    new_unit_dep(
                        state,
                        unit,
                        &unit.pkg,
                        t,
                        None, // artificial
                        UnitFor::new_normal(unit_for.root_compile_kind()),
                        unit.kind.for_target(t),
                        CompileMode::Build,
                        IS_NO_ARTIFACT_DEP,
                    )
                })
                .collect::<CargoResult<Vec<UnitDep>>>()?,
        );
    }

    Ok(ret)
}

/// Find artifacts for all `deps` of `unit` and add units that build these artifacts
/// to `ret`.
fn calc_artifact_deps<'a>(
    unit: &Unit,
    unit_for: UnitFor,
    dep_id: PackageId,
    deps: &[&Dependency],
    state: &State<'a, '_>,
    ret: &mut Vec<UnitDep>,
) -> CargoResult<Option<&'a Target>> {
    let mut has_artifact_lib = false;
    let mut maybe_non_artifact_lib = false;
    let artifact_pkg = state.get(dep_id);
    for dep in deps {
        let Some(artifact) = dep.artifact() else {
            maybe_non_artifact_lib = true;
            continue;
        };
        has_artifact_lib |= artifact.is_lib();
        // Custom build scripts (build/compile) never get artifact dependencies,
        // but the run-build-script step does (where it is handled).
        if !unit.target.is_custom_build() {
            debug_assert!(
                !unit.mode.is_run_custom_build(),
                "BUG: This should be handled in a separate branch"
            );
            ret.extend(artifact_targets_to_unit_deps(
                unit,
                unit_for.with_artifact_features(artifact),
                state,
                artifact
                    .target()
                    .and_then(|t| match t {
                        ArtifactTarget::BuildDependencyAssumeTarget => None,
                        ArtifactTarget::Force(kind) => Some(CompileKind::Target(kind)),
                    })
                    .unwrap_or(unit.kind),
                artifact_pkg,
                dep,
            )?);
        }
    }
    if has_artifact_lib || maybe_non_artifact_lib {
        Ok(artifact_pkg.targets().iter().find(|t| t.is_lib()))
    } else {
        Ok(None)
    }
}

/// Returns the dependencies needed to run a build script.
///
/// The `unit` provided must represent an execution of a build script, and
/// the returned set of units must all be run before `unit` is run.
fn compute_deps_custom_build(
    unit: &Unit,
    unit_for: UnitFor,
    state: &State<'_, '_>,
) -> CargoResult<Vec<UnitDep>> {
    if let Some(links) = unit.pkg.manifest().links() {
        if unit.links_overrides.get(links).is_some() {
            // Overridden build scripts don't have any dependencies.
            return Ok(Vec::new());
        }
    }
    // All dependencies of this unit should use profiles for custom builds.
    // If this is a build script of a proc macro, make sure it uses host
    // features.
    let script_unit_for = unit_for.for_custom_build();
    // When not overridden, then the dependencies to run a build script are:
    //
    // 1. Compiling the build script itself.
    // 2. For each immediate dependency of our package which has a `links`
    //    key, the execution of that build script.
    //
    // We don't have a great way of handling (2) here right now so this is
    // deferred until after the graph of all unit dependencies has been
    // constructed.
    let compile_script_unit = new_unit_dep(
        state,
        unit,
        &unit.pkg,
        &unit.target,
        None, // artificial
        script_unit_for,
        // Build scripts always compiled for the host.
        CompileKind::Host,
        CompileMode::Build,
        IS_NO_ARTIFACT_DEP,
    )?;

    let mut result = vec![compile_script_unit];

    // Include any artifact dependencies.
    //
    // This is essentially the same as `calc_artifact_deps`, but there are some
    // subtle differences that require this to be implemented differently.
    //
    // Produce units that build all required artifact kinds (like binaries,
    // static libraries, etc) with the correct compile target.
    //
    // Computing the compile target for artifact units is more involved as it has to handle
    // various target configurations specific to artifacts, like `target = "target"` and
    // `target = "<triple>"`, which makes knowing the root units compile target
    // `root_unit_compile_target` necessary.
    let root_unit_compile_target = unit_for.root_compile_kind();
    let unit_for = UnitFor::new_host(/*host_features*/ true, root_unit_compile_target);
    for (dep_pkg_id, deps) in state.deps(unit, script_unit_for) {
        for dep in deps {
            if dep.kind() != DepKind::Build || dep.artifact().is_none() {
                continue;
            }
            let artifact_pkg = state.get(dep_pkg_id);
            let artifact = dep.artifact().expect("artifact dep");
            let resolved_artifact_compile_kind = artifact
                .target()
                .map(|target| target.to_resolved_compile_kind(root_unit_compile_target));

            result.extend(artifact_targets_to_unit_deps(
                unit,
                unit_for.with_artifact_features_from_resolved_compile_kind(
                    resolved_artifact_compile_kind,
                ),
                state,
                resolved_artifact_compile_kind.unwrap_or(CompileKind::Host),
                artifact_pkg,
                dep,
            )?);
        }
    }

    Ok(result)
}

/// Given a `parent` unit containing a dependency `dep` whose package is `artifact_pkg`,
/// find all targets in `artifact_pkg` which refer to the `dep`s artifact declaration
/// and turn them into units.
/// Due to the nature of artifact dependencies, a single dependency in a manifest can
/// cause one or more targets to be build, for instance with
/// `artifact = ["bin:a", "bin:b", "staticlib"]`, which is very different from normal
/// dependencies which cause only a single unit to be created.
///
/// `compile_kind` is the computed kind for the future artifact unit
/// dependency, only the caller can pick the correct one.
fn artifact_targets_to_unit_deps(
    parent: &Unit,
    parent_unit_for: UnitFor,
    state: &State<'_, '_>,
    compile_kind: CompileKind,
    artifact_pkg: &Package,
    dep: &Dependency,
) -> CargoResult<Vec<UnitDep>> {
    let ret =
        match_artifacts_kind_with_targets(dep, artifact_pkg.targets(), parent.pkg.name().as_str())?
            .into_iter()
            .flat_map(|(artifact_kind, target)| {
                // We split target libraries into individual units, even though rustc is able
                // to produce multiple kinds in a single invocation for the sole reason that
                // each artifact kind has its own output directory, something we can't easily
                // teach rustc for now.
                match target.kind() {
                    TargetKind::Lib(kinds) => Box::new(
                        kinds
                            .iter()
                            .filter(move |tk| match (tk, artifact_kind) {
                                (CrateType::Cdylib, ArtifactKind::Cdylib) => true,
                                (CrateType::Staticlib, ArtifactKind::Staticlib) => true,
                                _ => false,
                            })
                            .map(|target_kind| {
                                new_unit_dep(
                                    state,
                                    parent,
                                    artifact_pkg,
                                    target
                                        .clone()
                                        .set_kind(TargetKind::Lib(vec![target_kind.clone()])),
                                    None, // TBD
                                    parent_unit_for,
                                    compile_kind,
                                    CompileMode::Build,
                                    dep.artifact(),
                                )
                            }),
                    ) as Box<dyn Iterator<Item = _>>,
                    _ => Box::new(std::iter::once(new_unit_dep(
                        state,
                        parent,
                        artifact_pkg,
                        target,
                        None, // TBD
                        parent_unit_for,
                        compile_kind,
                        CompileMode::Build,
                        dep.artifact(),
                    ))),
                }
            })
            .collect::<Result<Vec<_>, _>>()?;
    Ok(ret)
}

/// Returns the dependencies necessary to document a package.
fn compute_deps_doc(
    unit: &Unit,
    state: &mut State<'_, '_>,
    unit_for: UnitFor,
) -> CargoResult<Vec<UnitDep>> {
    // To document a library, we depend on dependencies actually being
    // built. If we're documenting *all* libraries, then we also depend on
    // the documentation of the library being built.
    let mut ret = Vec::new();
    for (id, deps) in state.deps(unit, unit_for) {
        let Some(dep_lib) = calc_artifact_deps(unit, unit_for, id, &deps, state, &mut ret)? else {
            continue;
        };
        let dep_pkg = state.get(id);
        // Rustdoc only needs rmeta files for regular dependencies.
        // However, for plugins/proc macros, deps should be built like normal.
        let mode = check_or_build_mode(unit.mode, dep_lib);
        let dep_unit_for = unit_for.with_dependency(unit, dep_lib, unit_for.root_compile_kind());
        let lib_unit_dep = new_unit_dep(
            state,
            unit,
            dep_pkg,
            dep_lib,
            None, // not checking unused deps
            dep_unit_for,
            unit.kind.for_target(dep_lib),
            mode,
            IS_NO_ARTIFACT_DEP,
        )?;
        ret.push(lib_unit_dep);
        if dep_lib.documented() && state.intent.wants_deps_docs() {
            // Document this lib as well.
            let doc_unit_dep = new_unit_dep(
                state,
                unit,
                dep_pkg,
                dep_lib,
                None, // not checking unused deps
                dep_unit_for,
                unit.kind.for_target(dep_lib),
                unit.mode,
                IS_NO_ARTIFACT_DEP,
            )?;
            ret.push(doc_unit_dep);
        }
    }

    // Be sure to build/run the build script for documented libraries.
    ret.extend(
        dep_build_script(unit, unit_for, state)?
            .into_iter()
            .flatten(),
    );

    // If we document a binary/example, we need the library available.
    if unit.target.is_bin() || unit.target.is_example() {
        // build the lib
        ret.extend(maybe_lib(unit, state, unit_for)?);
        // and also the lib docs for intra-doc links
        if let Some(lib) = unit
            .pkg
            .targets()
            .iter()
            .find(|t| t.is_linkable() && t.documented())
        {
            let dep_unit_for = unit_for.with_dependency(unit, lib, unit_for.root_compile_kind());
            let lib_doc_unit = new_unit_dep(
                state,
                unit,
                &unit.pkg,
                lib,
                None, // not checking unused deps
                dep_unit_for,
                unit.kind.for_target(lib),
                unit.mode,
                IS_NO_ARTIFACT_DEP,
            )?;
            ret.push(lib_doc_unit);
        }
    }

    // Add all units being scraped for examples as a dependency of top-level Doc units.
    if state.ws.unit_needs_doc_scrape(unit) {
        for scrape_unit in state.scrape_units.iter() {
            let scrape_unit_for = UnitFor::new_normal(scrape_unit.kind);
            deps_of(scrape_unit, state, scrape_unit_for)?;
            ret.push(new_unit_dep(
                state,
                scrape_unit,
                &scrape_unit.pkg,
                &scrape_unit.target,
                None, // not checking unused deps
                scrape_unit_for,
                scrape_unit.kind,
                scrape_unit.mode,
                IS_NO_ARTIFACT_DEP,
            )?);
        }
    }

    Ok(ret)
}

fn maybe_lib(
    unit: &Unit,
    state: &mut State<'_, '_>,
    unit_for: UnitFor,
) -> CargoResult<Option<UnitDep>> {
    unit.pkg
        .targets()
        .iter()
        .find(|t| t.is_linkable())
        .map(|t| {
            let mode = check_or_build_mode(unit.mode, t);
            let dep_unit_for = unit_for.with_dependency(unit, t, unit_for.root_compile_kind());
            new_unit_dep(
                state,
                unit,
                &unit.pkg,
                t,
                None,
                dep_unit_for,
                unit.kind.for_target(t),
                mode,
                IS_NO_ARTIFACT_DEP,
            )
        })
        .transpose()
}

/// If a build script is scheduled to be run for the package specified by
/// `unit`, this function will return the unit to run that build script.
///
/// Overriding a build script simply means that the running of the build
/// script itself doesn't have any dependencies, so even in that case a unit
/// of work is still returned. `None` is only returned if the package has no
/// build script.
fn dep_build_script(
    unit: &Unit,
    unit_for: UnitFor,
    state: &State<'_, '_>,
) -> CargoResult<Option<Vec<UnitDep>>> {
    Some(
        unit.pkg
            .targets()
            .iter()
            .filter(|t| t.is_custom_build())
            .map(|t| {
                // The profile stored in the Unit is the profile for the thing
                // the custom build script is running for.
                let profile = state.profiles.get_profile_run_custom_build(&unit.profile);
                // UnitFor::for_custom_build is used because we want the `host` flag set
                // for all of our build dependencies (so they all get
                // build-override profiles), including compiling the build.rs
                // script itself.
                //
                // If `is_for_host_features` here is `false`, that means we are a
                // build.rs script for a normal dependency and we want to set the
                // CARGO_FEATURE_* environment variables to the features as a
                // normal dep.
                //
                // If `is_for_host_features` here is `true`, that means that this
                // package is being used as a build dependency or proc-macro, and
                // so we only want to set CARGO_FEATURE_* variables for the host
                // side of the graph.
                //
                // Keep in mind that the RunCustomBuild unit and the Compile
                // build.rs unit use the same features. This is because some
                // people use `cfg!` and `#[cfg]` expressions to check for enabled
                // features instead of just checking `CARGO_FEATURE_*` at runtime.
                // In the case with the new feature resolver (decoupled host
                // deps), and a shared dependency has different features enabled
                // for normal vs. build, then the build.rs script will get
                // compiled twice. I believe it is not feasible to only build it
                // once because it would break a large number of scripts (they
                // would think they have the wrong set of features enabled).
                let script_unit_for = unit_for.for_custom_build();
                new_unit_dep_with_profile(
                    state,
                    unit,
                    &unit.pkg,
                    t,
                    None, // artificial
                    script_unit_for,
                    unit.kind,
                    CompileMode::RunCustomBuild,
                    profile,
                    IS_NO_ARTIFACT_DEP,
                )
            })
            .collect(),
    )
    .transpose()
}

/// Choose the correct mode for dependencies.
fn check_or_build_mode(mode: CompileMode, target: &Target) -> CompileMode {
    match mode {
        CompileMode::Check { .. } | CompileMode::Doc { .. } | CompileMode::Docscrape => {
            if target.for_host() {
                // Plugin and proc macro targets should be compiled like
                // normal.
                CompileMode::Build
            } else {
                // Regular dependencies should not be checked with --test.
                // Regular dependencies of doc targets should emit rmeta only.
                CompileMode::Check { test: false }
            }
        }
        _ => CompileMode::Build,
    }
}

/// Create a new Unit for a dependency from `parent` to `pkg` and `target`.
fn new_unit_dep(
    state: &State<'_, '_>,
    parent: &Unit,
    pkg: &Package,
    target: &Target,
    manifest_deps: Option<Vec<Dependency>>,
    unit_for: UnitFor,
    kind: CompileKind,
    mode: CompileMode,
    artifact: Option<&Artifact>,
) -> CargoResult<UnitDep> {
    let is_local = pkg.package_id().source_id().is_path() && !state.is_std;
    let profile = state.profiles.get_profile(
        pkg.package_id(),
        state.ws.is_member(pkg),
        is_local,
        unit_for,
        kind,
    );
    new_unit_dep_with_profile(
        state,
        parent,
        pkg,
        target,
        manifest_deps,
        unit_for,
        kind,
        mode,
        profile,
        artifact,
    )
}

fn new_unit_dep_with_profile(
    state: &State<'_, '_>,
    parent: &Unit,
    pkg: &Package,
    target: &Target,
    manifest_deps: Option<Vec<Dependency>>,
    unit_for: UnitFor,
    kind: CompileKind,
    mode: CompileMode,
    profile: Profile,
    artifact: Option<&Artifact>,
) -> CargoResult<UnitDep> {
    let (extern_crate_name, dep_name) = state.resolve().extern_crate_name_and_dep_name(
        parent.pkg.package_id(),
        pkg.package_id(),
        target,
    )?;
    let public = state
        .resolve()
        .is_public_dep(parent.pkg.package_id(), pkg.package_id());
    let features_for = unit_for.map_to_features_for(artifact);
    let artifact_target = match features_for {
        FeaturesFor::ArtifactDep(target) => Some(target),
        _ => None,
    };
    let features = state.activated_features(pkg.package_id(), features_for);
    let unit = state.interner.intern(
        pkg,
        target,
        profile,
        kind,
        mode,
        features,
        state.target_data.info(kind).rustflags.clone(),
        state.target_data.info(kind).rustdocflags.clone(),
        state
            .target_data
            .target_config(kind)
            .links_overrides
            .clone(),
        state.is_std,
        /*dep_hash*/ 0,
        artifact.map_or(IsArtifact::No, |_| IsArtifact::Yes),
        artifact_target,
        false,
    );
    Ok(UnitDep {
        unit,
        unit_for,
        extern_crate_name,
        dep_name,
        public,
        noprelude: false,
        nounused: false,
        manifest_deps: Unhashed(manifest_deps),
    })
}

/// Fill in missing dependencies for units of the `RunCustomBuild`
///
/// As mentioned above in `compute_deps_custom_build` each build script
/// execution has two dependencies. The first is compiling the build script
/// itself (already added) and the second is that all crates the package of the
/// build script depends on with `links` keys, their build script execution. (a
/// bit confusing eh?)
///
/// Here we take the entire `deps` map and add more dependencies from execution
/// of one build script to execution of another build script.
fn connect_run_custom_build_deps(state: &mut State<'_, '_>) {
    let mut new_deps = Vec::new();

    {
        let state = &*state;
        // First up build a reverse dependency map. This is a mapping of all
        // `RunCustomBuild` known steps to the unit which depends on them. For
        // example a library might depend on a build script, so this map will
        // have the build script as the key and the library would be in the
        // value's set.
        let mut reverse_deps_map = HashMap::default();
        for (unit, deps) in state.unit_dependencies.iter() {
            for dep in deps {
                if dep.unit.mode == CompileMode::RunCustomBuild {
                    reverse_deps_map
                        .entry(dep.unit.clone())
                        .or_insert_with(HashSet::default)
                        .insert(unit);
                }
            }
        }

        // Next, we take a look at all build scripts executions listed in the
        // dependency map. Our job here is to take everything that depends on
        // this build script (from our reverse map above) and look at the other
        // package dependencies of these parents.
        //
        // If we depend on a linkable target and the build script mentions
        // `links`, then we depend on that package's build script! Here we use
        // `dep_build_script` to manufacture an appropriate build script unit to
        // depend on.
        for unit in state
            .unit_dependencies
            .keys()
            .filter(|k| k.mode == CompileMode::RunCustomBuild)
        {
            // This list of dependencies all depend on `unit`, an execution of
            // the build script.
            let Some(reverse_deps) = reverse_deps_map.get(unit) else {
                continue;
            };

            let to_add = reverse_deps
                .iter()
                // Get all sibling dependencies of `unit`
                .flat_map(|reverse_dep| {
                    state.unit_dependencies[reverse_dep]
                        .iter()
                        .map(move |a| (reverse_dep, a))
                })
                // Exclude ourself
                .filter(|(_parent, other)| other.unit.pkg != unit.pkg)
                // Only deps with `links`.
                .filter(|(_parent, other)| {
                    state.gctx.cli_unstable().any_build_script_metadata
                        || (other.unit.target.is_linkable()
                            && other.unit.pkg.manifest().links().is_some())
                })
                // Avoid cycles when using the doc --scrape-examples feature:
                // Say a workspace has crates A and B where A has a build-dependency on B.
                // The Doc units for A and B will have a dependency on the Docscrape for both A and B.
                // So this would add a dependency from B-build to A-build, causing a cycle:
                //   B (build) -> A (build) -> B(build)
                // See the test scrape_examples_avoid_build_script_cycle for a concrete example.
                // To avoid this cycle, we filter out the B -> A (docscrape) dependency.
                .filter(|(_parent, other)| !other.unit.mode.is_doc_scrape())
                // Skip dependencies induced via dev-dependencies since
                // connections between `links` and build scripts only happens
                // via normal dependencies. Otherwise since dev-dependencies can
                // be cyclic we could have cyclic build-script executions.
                .filter_map(move |(parent, other)| {
                    if state
                        .dev_dependency_edges
                        .contains(&((*parent).clone(), other.unit.clone()))
                    {
                        None
                    } else {
                        Some(other)
                    }
                })
                // Get the RunCustomBuild for other lib.
                .filter_map(|other| {
                    state.unit_dependencies[&other.unit]
                        .iter()
                        .find(|other_dep| other_dep.unit.mode == CompileMode::RunCustomBuild)
                        .map(|other_dep| {
                            let mut dep = other_dep.clone();
                            let dep_name = other.dep_name.unwrap_or(other.unit.pkg.name());
                            // Propagate the manifest dep name from the sibling edge.
                            // The RunCustomBuild-RustCustomBuild edge is synthetic
                            // and doesn't carry a usable dep name, but build script
                            // metadata needs one for `CARGO_DEP_<dep_name>_*` env var
                            dep.dep_name = Some(dep_name);
                            dep
                        })
                })
                .collect::<HashSet<_>>();

            if !to_add.is_empty() {
                // (RunCustomBuild, set(other RunCustomBuild))
                new_deps.push((unit.clone(), to_add));
            }
        }
    }

    // And finally, add in all the missing dependencies!
    for (unit, new_deps) in new_deps {
        state
            .unit_dependencies
            .get_mut(&unit)
            .unwrap()
            .extend(new_deps);
    }
}

impl<'a, 'gctx> State<'a, 'gctx> {
    /// Tentatively uses build mode for an immutable registry closure or an
    /// owned workspace member. Once all unit hashes and layouts are known,
    /// `BuildRunner` validates the exact existing artifacts and their complete
    /// fingerprints before allowing the graph to execute.
    fn can_reuse_built_registry_dependency(
        &self,
        parent: &Unit,
        package_id: PackageId,
        target: &Target,
        unit_for: UnitFor,
    ) -> bool {
        let is_workspace_member = self.ws.is_member_id(package_id);
        if !self.reuse_built_registry_dependencies
            || self.is_std
            || (!package_id.source_id().is_remote_registry() && !is_workspace_member)
            || (is_workspace_member && self.target_data.rustc.workspace_wrapper.is_some())
            || self.rejected_built_registry_packages.contains(&package_id)
            || target.for_host()
            || !target.is_lib()
            || !target
                .rustc_crate_types()
                .iter()
                .all(|crate_type| matches!(crate_type, CrateType::Lib | CrateType::Rlib))
            || self.gctx.cli_unstable().bindeps
            || self.target_data.rustc.wrapper.is_some()
            || !*self.trusted_registry_reuse_compiler.get_or_init(|| {
                self.compiler_has_safe_loader_environment()
                    && !self.compiler_has_observable_logging()
                    && self.compiler_has_verified_toolchain_identity()
            })
        {
            return false;
        }

        let Ok(dependency) = new_unit_dep(
            self,
            parent,
            self.get(package_id),
            target,
            None,
            unit_for,
            parent.kind.for_target(target),
            CompileMode::Build,
            IS_NO_ARTIFACT_DEP,
        ) else {
            return false;
        };

        self.registry_closure_is_immutable(
            &dependency.unit,
            unit_for,
            false,
            &mut HashSet::default(),
        )
    }

    /// Loader interposition can turn the genuine toolchain executable into an
    /// opaque compiler wrapper, so cached cross-mode results are unusable.
    fn compiler_has_safe_loader_environment(&self) -> bool {
        let Ok(configured_environment) = self.gctx.env_config() else {
            return false;
        };

        OHM_COMPILER_LOADER_INJECTION_ENVIRONMENT
            .iter()
            .all(|name| {
                configured_environment
                    .get(*name)
                    .map(std::ffi::OsString::as_os_str)
                    .or_else(|| self.gctx.get_env_os(name))
                    .is_none_or(std::ffi::OsStr::is_empty)
            })
    }

    /// Rustc initializes every logger option even when its main filter is absent.
    /// An invalid option can fail compilation and an output target truncates files.
    fn compiler_has_observable_logging(&self) -> bool {
        let Ok(configured_environment) = self.gctx.env_config() else {
            return true;
        };

        OHM_RUSTC_LOG_ENVIRONMENT.iter().any(|name| {
            configured_environment.contains_key(*name) || self.gctx.get_env_os(name).is_some()
        })
    }

    /// Reject opaque compiler shims whose behavior Cargo cannot fingerprint.
    ///
    /// Configuring the actual compiler from any installed or custom toolchain
    /// remains supported. Cargo normally resolves rustup proxies to that
    /// toolchain executable before constructing `RustcTargetData`.
    fn compiler_has_verified_toolchain_identity(&self) -> bool {
        let Some(compiler) =
            resolve_effective_compiler_executable(self.gctx, &self.target_data.rustc.path)
        else {
            return false;
        };
        let expected = self
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

    /// Reject unowned mutable sources and untrusted procedural macros throughout the
    /// actual compilation closure, including active build-script dependencies.
    fn registry_closure_is_immutable(
        &self,
        unit: &Unit,
        unit_for: UnitFor,
        audited_macro_runtime: bool,
        visiting: &mut HashSet<(Unit, bool)>,
    ) -> bool {
        let package_id = unit.pkg.package_id();
        let source_is_replaced = if package_id.source_id().is_remote_registry() {
            let Some((source_is_replaced, effective_source_id)) = self
                .package_set
                .sources()
                .get(package_id.source_id())
                .map(|source| (source.is_replaced(), source.replaced_source_id()))
            else {
                return false;
            };
            // Source replacement preserves the original registry PackageId even
            // when a mutable, checksummed vendor directory supplies the contents.
            // Such sources must follow the ordinary check path so Cargo verifies
            // their integrity before compiling a newly requested target. Registry
            // mirrors remain immutable and their actual source path participates
            // in the existing unit fingerprint.
            if source_is_replaced && !effective_source_id.is_remote_registry() {
                return false;
            }
            source_is_replaced
        } else {
            // Workspace sources can change, so they are eligible only when their
            // exact build fingerprint is revalidated under the workspace lock.
            // Local build scripts and procedural macros may observe untracked
            // inputs, and arbitrary path dependencies are outside that lock.
            if !self.ws.is_member_id(package_id)
                || !unit.target.is_lib()
                || unit.target.for_host()
                || audited_macro_runtime
            {
                return false;
            }
            false
        };

        let audited_macro_runtime = audited_macro_runtime || unit.pkg.proc_macro();
        if audited_macro_runtime
            && !is_canonical_unreplaced_crates_io(package_id.source_id(), source_is_replaced)
        {
            return false;
        }

        let cache_key = (unit.clone(), audited_macro_runtime);
        if let Some(immutable) = self.immutable_registry_closures.borrow().get(&cache_key) {
            return *immutable;
        }
        if !visiting.insert(cache_key.clone()) {
            return true;
        }

        // Stable procedural macros can inspect arbitrary environment variables
        // and external files without recording either in rustc dependency
        // information. By default, reusing their expanded consumers requires an
        // explicitly audited, immutable producer. The existing explicit `all`
        // policy also accepts authenticated crates.io macros, but is potentially
        // unsound. Other macro closures must run the ordinary check compiler
        // regardless of their existing artifacts.
        // A macro's ordinary library dependencies execute inside its compiler
        // process too. Authenticating only the macro package would let an
        // alternate registry or newer semver-compatible helper introduce
        // untracked environment and filesystem reads into that same process.
        let trusted_runtime = if unit.pkg.proc_macro() {
            self.proc_macro_is_audited(unit)
        } else if audited_macro_runtime {
            self.proc_macro_runtime_dependency_is_audited(unit, source_is_replaced)
        } else {
            true
        };
        let immutable = trusted_runtime
            && self.active_registry_dependencies_are_immutable(
                unit,
                unit_for,
                audited_macro_runtime,
                visiting,
            );

        visiting.remove(&cache_key);
        self.immutable_registry_closures
            .borrow_mut()
            .insert(cache_key, immutable);
        immutable
    }

    /// Trust configured macro releases only when their complete source
    /// identities match both the resolved and downloaded checksums.
    fn proc_macro_is_audited(&self, unit: &Unit) -> bool {
        let package_id = unit.pkg.package_id();
        let sources = self.package_set.sources();
        let Some(source) = sources.get(package_id.source_id()) else {
            return false;
        };
        audited_proc_macro_package_identity(
            package_id.source_id(),
            source.is_replaced(),
            package_id.name().as_str(),
            package_id.version(),
            self.resolve()
                .checksums()
                .get(&package_id)
                .and_then(Option::as_deref),
            unit.pkg.summary().checksum(),
            true,
            self.gctx.cli_unstable().ohm_proc_macro_trust,
        )
    }

    /// Authenticate every ordinary library linked into an audited macro.
    fn proc_macro_runtime_dependency_is_audited(
        &self,
        unit: &Unit,
        source_is_replaced: bool,
    ) -> bool {
        let package_id = unit.pkg.package_id();
        audited_proc_macro_runtime_dependency_identity(
            package_id.source_id(),
            source_is_replaced,
            package_id.name().as_str(),
            package_id.version(),
            self.resolve()
                .checksums()
                .get(&package_id)
                .and_then(Option::as_deref),
            unit.pkg.summary().checksum(),
            self.gctx.cli_unstable().ohm_proc_macro_trust,
        )
    }

    /// Traverse the same active dependency edges as unit-graph construction,
    /// instead of treating inactive platforms and optional features as used.
    fn active_registry_dependencies_are_immutable(
        &self,
        unit: &Unit,
        unit_for: UnitFor,
        audited_macro_runtime: bool,
        visiting: &mut HashSet<(Unit, bool)>,
    ) -> bool {
        if unit.mode.is_run_custom_build() {
            return compute_deps_custom_build(unit, unit_for, self).is_ok_and(|dependencies| {
                dependencies.into_iter().all(|dependency| {
                    self.registry_closure_is_immutable(
                        &dependency.unit,
                        dependency.unit_for,
                        audited_macro_runtime,
                        visiting,
                    )
                })
            });
        }

        for (package_id, dependencies) in self.deps(unit, unit_for) {
            if dependencies
                .iter()
                .any(|dependency| dependency.artifact().is_some())
            {
                return false;
            }

            let package = self.get(package_id);
            let Some(target) = package.targets().iter().find(|target| target.is_lib()) else {
                return false;
            };
            let dependency_unit_for =
                unit_for.with_dependency(unit, target, unit_for.root_compile_kind());
            let Ok(dependency) = new_unit_dep(
                self,
                unit,
                package,
                target,
                None,
                dependency_unit_for,
                unit.kind.for_target(target),
                check_or_build_mode(unit.mode, target),
                IS_NO_ARTIFACT_DEP,
            ) else {
                return false;
            };

            if !self.registry_closure_is_immutable(
                &dependency.unit,
                dependency_unit_for,
                audited_macro_runtime,
                visiting,
            ) {
                return false;
            }
        }

        if unit.target.is_custom_build() {
            return true;
        }

        dep_build_script(unit, unit_for, self).is_ok_and(|build_scripts| {
            build_scripts.into_iter().flatten().all(|build_script| {
                self.registry_closure_is_immutable(
                    &build_script.unit,
                    build_script.unit_for,
                    audited_macro_runtime,
                    visiting,
                )
            })
        })
    }

    /// Gets `std_resolve` during building std, otherwise `usr_resolve`.
    fn resolve(&self) -> &'a Resolve {
        if self.is_std {
            self.std_resolve.unwrap()
        } else {
            self.usr_resolve
        }
    }

    /// Gets `std_features` during building std, otherwise `usr_features`.
    fn features(&self) -> &'a ResolvedFeatures {
        if self.is_std {
            self.std_features.unwrap()
        } else {
            self.usr_features
        }
    }

    fn activated_features(
        &self,
        pkg_id: PackageId,
        features_for: FeaturesFor,
    ) -> Vec<InternedString> {
        let features = self.features();
        features.activated_features(pkg_id, features_for)
    }

    fn is_dep_activated(
        &self,
        pkg_id: PackageId,
        features_for: FeaturesFor,
        dep_name: InternedString,
    ) -> bool {
        self.features()
            .is_dep_activated(pkg_id, features_for, dep_name)
    }

    fn get(&self, id: PackageId) -> &'a Package {
        self.package_set
            .get_one(id)
            .unwrap_or_else(|_| panic!("expected {} to be downloaded", id))
    }

    /// Returns a filtered set of dependencies for the given unit.
    fn deps(&self, unit: &Unit, unit_for: UnitFor) -> Vec<(PackageId, Vec<&Dependency>)> {
        let pkg_id = unit.pkg.package_id();
        let kind = unit.kind;
        self.resolve()
            .deps(pkg_id)
            .filter_map(|(id, deps)| {
                assert!(!deps.is_empty());
                let deps: Vec<_> = deps
                    .iter()
                    .filter(|dep| {
                        // If this target is a build command, then we only want build
                        // dependencies, otherwise we want everything *other than* build
                        // dependencies.
                        if unit.target.is_custom_build() != dep.is_build() {
                            return false;
                        }

                        // If this dependency is **not** a transitive dependency, then it
                        // only applies to test/example targets.
                        if !dep.is_transitive()
                            && !unit.target.is_test()
                            && !unit.target.is_example()
                            && !unit.mode.is_any_test()
                        {
                            return false;
                        }

                        // If this dependency is only available for certain platforms,
                        // make sure we're only enabling it for that platform.
                        if !self.target_data.dep_platform_activated(dep, kind) {
                            return false;
                        }

                        // If this is an optional dependency, and the new feature resolver
                        // did not enable it, don't include it.
                        if dep.is_optional() {
                            // This `unit_for` is from parent dep and *SHOULD* contains its own
                            // artifact dep information inside `artifact_target_for_features`.
                            // So, no need to map any artifact info from an incorrect `dep.artifact()`.
                            let features_for = unit_for.map_to_features_for(IS_NO_ARTIFACT_DEP);
                            if !self.is_dep_activated(pkg_id, features_for, dep.name_in_toml()) {
                                return false;
                            }
                        }

                        // If we've gotten past all that, then this dependency is
                        // actually used!
                        true
                    })
                    .collect();
                if deps.is_empty() {
                    None
                } else {
                    Some((id, deps))
                }
            })
            .collect()
    }
}

/// Reject replacement mirrors and file-backed registries for executable macro code.
fn is_canonical_unreplaced_crates_io(source_id: SourceId, source_is_replaced: bool) -> bool {
    !source_is_replaced
        && source_id.is_crates_io()
        && matches!(
            source_id.url().as_str(),
            CRATES_IO_INDEX | CRATES_IO_HTTP_INDEX
        )
}

/// Authenticate the actual source and both package checksums of macro runtime code.
fn audited_proc_macro_runtime_dependency_identity(
    source_id: SourceId,
    source_is_replaced: bool,
    name: &str,
    version: &semver::Version,
    resolved_checksum: Option<&str>,
    downloaded_checksum: Option<&str>,
    trust: OhmProcMacroTrust,
) -> bool {
    audited_proc_macro_package_identity(
        source_id,
        source_is_replaced,
        name,
        version,
        resolved_checksum,
        downloaded_checksum,
        false,
        trust,
    )
}

/// Authenticate an exact canonical registry package against both actual checksum sources.
///
/// Procedural macros and the ordinary libraries linked into them use separate audited
/// allowlists by default. An explicit permissive policy bypasses those allowlists, but both
/// policies always enforce the same immutable-source and lockfile identity rules.
pub(crate) fn audited_proc_macro_package_identity(
    source_id: SourceId,
    source_is_replaced: bool,
    name: &str,
    version: &semver::Version,
    resolved_checksum: Option<&str>,
    downloaded_checksum: Option<&str>,
    is_proc_macro: bool,
    trust: OhmProcMacroTrust,
) -> bool {
    is_canonical_unreplaced_crates_io(source_id, source_is_replaced)
        && resolved_checksum.is_some_and(|checksum| {
            downloaded_checksum == Some(checksum)
                && (trust == OhmProcMacroTrust::All
                    || if is_proc_macro {
                        audited_proc_macro_checksum(name, version, checksum)
                    } else {
                        audited_proc_macro_runtime_dependency_checksum(name, version, checksum)
                    })
        })
}

/// Exact upstream releases whose macro entry points and runtime dependency
/// closures have been audited to operate exclusively on their supplied tokens.
fn audited_proc_macro_checksum(name: &str, version: &semver::Version, checksum: &str) -> bool {
    if !version.pre.is_empty() || !version.build.is_empty() {
        return false;
    }

    let expected = match (name, version.major, version.minor, version.patch) {
        ("async-trait", 0, 1, 89) => {
            "9035ad2d096bed7955a320ee7e2230574d28fd3c3a0f186cbea1ff3c7eed5dbb"
        }
        ("bytecheck_derive", 0, 8, 2) => {
            "89385e82b5d1821d2219e0b095efa2cc1f246cbf99080f3be46a1a85c0d392d9"
        }
        ("bytemuck_derive", 1, 10, 2) => {
            "f9abbd1bc6865053c427f7198e6af43bfdedc55ab791faed4fbd361d789575ff"
        }
        ("futures-macro", 0, 3, 32) => {
            "e835b70203e41293343137df5c0664546da5745f82ec9b84d40be8336958447b"
        }
        ("futures-macro", 0, 3, 33) => {
            "2d6d3cde68c518367be28956066ddfef33813991b77a55005a69dae04bf3b10b"
        }
        ("munge_macro", 0, 4, 7) => {
            "4568f25ccbd45ab5d5603dc34318c1ec56b117531781260002151b8530a9f931"
        }
        ("pin-project-internal", 1, 1, 10) => {
            "6e918e4ff8c4549eb882f14b3a4bc8c8bc93de829416eacf579f1207a8fbf861"
        }
        ("pin-project-internal", 1, 1, 11) => {
            "d9b20ed30f105399776b9c883e68e536ef602a16ae6f596d2c473591d6ad64c6"
        }
        ("ptr_meta_derive", 0, 3, 1) => {
            "7347867d0a7e1208d93b46767be83e2b8f978c3dad35f775ac8d8847551d6fe1"
        }
        ("rkyv_derive", 0, 8, 17) => {
            "c0ed1a78a1b19d184b0daa629dd9a024573173ec7d485b287cb369fb3607cc1c"
        }
        ("serde_derive", 1, 0, 219) => {
            "5b0276cf7f2c73365f7157c8123c21cd9a50fbbd844757af28ca1f5925fc2a00"
        }
        ("serde_derive", 1, 0, 228) => {
            "d540f220d3187173da220f885ab66608367b6574e925011a9353e4badda91d79"
        }
        ("serde_derive", 1, 0, 229) => {
            "e7a5d71263a5a7d47b41f6b3f06ba276f10cc18b0931f1799f710578e2309348"
        }
        ("thiserror-impl", 1, 0, 69) => {
            "4fee6c4efc90059e10f81e6d42c60a18f76588c3d74cb83a0b242a2b6c7504c1"
        }
        ("thiserror-impl", 2, 0, 18) => {
            "ebc4ee7f67670e9b64d05fa4253e753e016c6c95ff35b89b7941d6b856dec1d5"
        }
        ("thiserror-impl", 2, 0, 19) => {
            "43cbfe0cf76104d42a574802844187e84a305e531ed54455f11fbde0f10541cd"
        }
        ("tokio-macros", 2, 7, 0) => {
            "385a6cb71ab9ab790c5fe8d67f1645e6c450a7ce006a33de03daa956cf70a496"
        }
        ("tracing-attributes", 0, 1, 31) => {
            "7490cfa5ec963746568740651ac6781f701c9c5ea257c58e057f3ba8cf69e8da"
        }
        ("yoke-derive", 0, 8, 1) => {
            "b659052874eb698efe5b9e8cf382204678a0086ebf46982b79d6ca3182927e5d"
        }
        ("yoke-derive", 0, 8, 2) => {
            "de844c262c8848816172cef550288e7dc6c7b7814b4ee56b3e1553f275f1858e"
        }
        ("zerocopy-derive", 0, 8, 37) => {
            "1328722bbf2115db7e19d69ebcc15e795719e2d66b60827c6a69a117365e37a0"
        }
        ("zerocopy-derive", 0, 8, 42) => {
            "7e6cc098ea4d3bd6246687de65af3f920c430e236bee1e3bf2e441463f08a02f"
        }
        ("zerofrom-derive", 0, 1, 6) => {
            "d71e5d6e06ab090c67b5e44993ec16b72dcbaabc526db883a360057678b48502"
        }
        ("zeroize_derive", 1, 4, 3) => {
            "85a5b4158499876c763cb03bc4e49185d3cccbabb15b33c627f7884f43db852e"
        }
        ("zerovec-derive", 0, 11, 2) => {
            "eadce39539ca5cb3985590102671f2567e659fca9666581ad3411d59207951f3"
        }
        ("zerovec-derive", 0, 11, 3) => {
            "625dc425cab0dca6dc3c3319506e6593dcb08a9f387ea3b284dbd52a92c40555"
        }
        _ => return false,
    };

    checksum == expected
}

/// Exact audited libraries that execute inside an accepted procedural macro.
fn audited_proc_macro_runtime_dependency_checksum(
    name: &str,
    version: &semver::Version,
    checksum: &str,
) -> bool {
    if !version.pre.is_empty() || !version.build.is_empty() {
        return false;
    }

    let expected = match (name, version.major, version.minor, version.patch) {
        ("proc-macro2", 1, 0, 93) => {
            "60946a68e5f9d28b0dc1c21bb8a97ee7d018a8b322fa57838ba31cc878e22d99"
        }
        ("proc-macro2", 1, 0, 95) => {
            "02b3e5e68a3a1a02aad3ec490a98007cbc13c37cbe84a3cd7b8e406d76e7f778"
        }
        ("proc-macro2", 1, 0, 103) => {
            "5ee95bc4ef87b8d5ba32e8b7714ccc834865276eab0aed5c9958d00ec45f49e8"
        }
        ("proc-macro2", 1, 0, 106) => {
            "8fd00f0bb2e90d81d1044c2b32617f68fcb9fa3bb7640c23e9c748e53fb30934"
        }
        ("proc-macro2", 1, 0, 107) => {
            "985e7ec9bb745e6ce6535b544d84d6cd6f7ad8bd711c398938ae983b91a766d9"
        }
        ("quote", 1, 0, 38) => "0e4dccaaaf89514f546c693ddc140f729f958c247918a13380cccc6078391acc",
        ("quote", 1, 0, 40) => "1885c039570dc00dcb4ff087a89e185fd56bae234ddc7f056a945bf36467248d",
        ("quote", 1, 0, 45) => "41f2619966050689382d2b44f664f4bc593e129785a36d6ee376ddf37259b924",
        ("quote", 1, 0, 46) => "dfbc457d0c7a0759a614551b11a6409e5951f6c7537be1f1b7682b9ae9230368",
        ("quote", 1, 0, 47) => "1fbf4db142a473a8d80c26bbf18454ed458bf8d26c8219c331daecfdbd079001",
        ("syn", 1, 0, 109) => "72b64191b275b66ffe2469e8af2c1cfe3bafa67b529ead792a6d0160888b4237",
        ("syn", 2, 0, 96) => "d5d0adab1ae378d7f53bdebc67a39f1f151407ef230f0ce2883572f5d8985c80",
        ("syn", 2, 0, 104) => "17b6f705963418cdb9927482fa304bc562ece2fdd4f616084c50b7023b435a40",
        ("syn", 2, 0, 110) => "a99801b5bd34ede4cf3fc688c5919368fea4e4814a4664359503e6015b280aea",
        ("syn", 2, 0, 117) => "e665b8803e7b1d2a727f4023456bbbbe74da67099c585258af0ad9c5013b9b99",
        ("syn", 2, 0, 118) => "1b9ae57f904213ebb649ce6895b8a66c66f0203b9319718f69a5612a065b1422",
        ("syn", 2, 0, 119) => "872831b642d1a07999a962a351ed35b955ea2cfc8f3862091e2a240a84f17297",
        ("syn", 3, 0, 3) => "53e9bae58849f64dfa4f5d5ae372c8341f7305f82a3868709269343628b659a3",
        ("synstructure", 0, 13, 2) => {
            "728a70f3dbaf5bab7f0c4b1ac8d7ae5ea60a4b5549c8a5914361c99147a709d2"
        }
        ("unicode-ident", 1, 0, 14) => {
            "adb9e6ca4f869e1180728b7950e35922a7fc6397f7b641499e8f3ef06e50dc83"
        }
        ("unicode-ident", 1, 0, 18) => {
            "5a5f39404a5da50712a4c1eecf25e90dd62b613502b7e925fd4e4d19b5c96512"
        }
        ("unicode-ident", 1, 0, 22) => {
            "9312f7c4f6ff9069b165498234ce8be658059c6728633667c526e27dc2cf1df5"
        }
        ("unicode-ident", 1, 0, 24) => {
            "e6e4313cd5fcd3dad5cafa179702e2b244f760991f45397d14d4ebf38247da75"
        }
        _ => return false,
    };

    checksum == expected
}

#[cfg(test)]
mod audited_proc_macro_tests {
    use super::{
        audited_proc_macro_checksum, audited_proc_macro_package_identity,
        audited_proc_macro_runtime_dependency_checksum,
        audited_proc_macro_runtime_dependency_identity, is_canonical_unreplaced_crates_io,
    };
    use crate::workspace::SourceId;
    use crate::workspace::features::OhmProcMacroTrust;

    #[test]
    fn only_the_exact_audited_release_and_checksum_are_trusted() {
        let checksum = "43cbfe0cf76104d42a574802844187e84a305e531ed54455f11fbde0f10541cd";
        let audited = semver::Version::new(2, 0, 19);

        assert!(audited_proc_macro_checksum(
            "thiserror-impl",
            &audited,
            checksum
        ));
        assert!(!audited_proc_macro_checksum(
            "thiserror-impl",
            &audited,
            "bad-checksum",
        ));
        assert!(!audited_proc_macro_checksum(
            "thiserror-impl",
            &semver::Version::new(2, 0, 20),
            checksum,
        ));
        assert!(!audited_proc_macro_checksum(
            "different-macro",
            &audited,
            checksum,
        ));
        assert!(!audited_proc_macro_checksum(
            "thiserror-impl",
            &semver::Version::parse("2.0.19-prerelease").expect("valid test version"),
            checksum,
        ));
    }

    #[test]
    fn macros_with_untracked_runtime_inputs_remain_untrusted() {
        for (name, version, checksum) in [
            (
                "clap_derive",
                semver::Version::new(4, 5, 55),
                "a92793da1a46a5f2a02a6f4c46c6496b28c43638adea8306fcb0caa1634f24e5",
            ),
            (
                "clap_derive",
                semver::Version::new(4, 6, 4),
                "d012d2b9d65aca7f18f4d9878a045bc17899bba951561ba5ec3c2ba1eed9a061",
            ),
            (
                "displaydoc",
                semver::Version::new(0, 2, 5),
                "97369cbbc041bc366949bc74d34658d6cda5621039731c6310521892a3a20ae0",
            ),
        ] {
            assert!(!audited_proc_macro_checksum(name, &version, checksum));
        }
    }

    #[test]
    fn serde_derives_require_exact_audited_releases_and_checksums() {
        let checksum = "e7a5d71263a5a7d47b41f6b3f06ba276f10cc18b0931f1799f710578e2309348";

        assert!(audited_proc_macro_checksum(
            "serde_derive",
            &semver::Version::new(1, 0, 219),
            "5b0276cf7f2c73365f7157c8123c21cd9a50fbbd844757af28ca1f5925fc2a00",
        ));
        assert!(audited_proc_macro_checksum(
            "serde_derive",
            &semver::Version::new(1, 0, 229),
            checksum,
        ));
        assert!(!audited_proc_macro_checksum(
            "serde_derive",
            &semver::Version::new(1, 0, 230),
            checksum,
        ));
        assert!(!audited_proc_macro_checksum(
            "serde_derive",
            &semver::Version::new(1, 0, 229),
            "unaudited-checksum",
        ));
    }

    #[test]
    fn shared_registry_macro_identities_require_canonical_matching_checksums() {
        let source = SourceId::from_url("registry+https://github.com/rust-lang/crates.io-index")
            .expect("canonical registry source");

        for (name, version, checksum) in [
            (
                "bytecheck_derive",
                semver::Version::new(0, 8, 2),
                "89385e82b5d1821d2219e0b095efa2cc1f246cbf99080f3be46a1a85c0d392d9",
            ),
            (
                "munge_macro",
                semver::Version::new(0, 4, 7),
                "4568f25ccbd45ab5d5603dc34318c1ec56b117531781260002151b8530a9f931",
            ),
            (
                "ptr_meta_derive",
                semver::Version::new(0, 3, 1),
                "7347867d0a7e1208d93b46767be83e2b8f978c3dad35f775ac8d8847551d6fe1",
            ),
            (
                "rkyv_derive",
                semver::Version::new(0, 8, 17),
                "c0ed1a78a1b19d184b0daa629dd9a024573173ec7d485b287cb369fb3607cc1c",
            ),
        ] {
            assert!(audited_proc_macro_package_identity(
                source,
                false,
                name,
                &version,
                Some(checksum),
                Some(checksum),
                true,
                OhmProcMacroTrust::Audited,
            ));
            assert!(!audited_proc_macro_package_identity(
                source,
                true,
                name,
                &version,
                Some(checksum),
                Some(checksum),
                true,
                OhmProcMacroTrust::Audited,
            ));
            assert!(!audited_proc_macro_package_identity(
                source,
                false,
                name,
                &version,
                Some(checksum),
                Some("unaudited-download"),
                true,
                OhmProcMacroTrust::Audited,
            ));
            assert!(!audited_proc_macro_package_identity(
                source,
                false,
                name,
                &version,
                None,
                Some(checksum),
                true,
                OhmProcMacroTrust::Audited,
            ));
            assert!(!audited_proc_macro_package_identity(
                source,
                false,
                name,
                &version,
                Some(checksum),
                Some(checksum),
                false,
                OhmProcMacroTrust::Audited,
            ));
        }
    }

    #[test]
    fn permissive_macro_trust_still_requires_canonical_matching_checksums() {
        let canonical = SourceId::from_url("registry+https://github.com/rust-lang/crates.io-index")
            .expect("canonical registry source");
        let alternative = SourceId::from_url("registry+file:///tmp/alternative-registry")
            .expect("alternate registry source");

        for (name, version, checksum, is_proc_macro) in [
            (
                "clap_derive",
                semver::Version::new(4, 6, 4),
                "d012d2b9d65aca7f18f4d9878a045bc17899bba951561ba5ec3c2ba1eed9a061",
                true,
            ),
            (
                "heck",
                semver::Version::new(0, 5, 0),
                "2304e00983f87ffb38b55b444b5e3b60a884b5d30c0fca7d82fe33449bbe55ea",
                false,
            ),
        ] {
            assert!(!audited_proc_macro_package_identity(
                canonical,
                false,
                name,
                &version,
                Some(checksum),
                Some(checksum),
                is_proc_macro,
                OhmProcMacroTrust::Audited,
            ));
            assert!(audited_proc_macro_package_identity(
                canonical,
                false,
                name,
                &version,
                Some(checksum),
                Some(checksum),
                is_proc_macro,
                OhmProcMacroTrust::All,
            ));

            for (source, replaced, resolved, downloaded) in [
                (canonical, true, Some(checksum), Some(checksum)),
                (alternative, false, Some(checksum), Some(checksum)),
                (canonical, false, None, Some(checksum)),
                (canonical, false, Some(checksum), None),
                (canonical, false, Some(checksum), Some("different-checksum")),
            ] {
                assert!(!audited_proc_macro_package_identity(
                    source,
                    replaced,
                    name,
                    &version,
                    resolved,
                    downloaded,
                    is_proc_macro,
                    OhmProcMacroTrust::All,
                ));
            }
        }
    }

    #[test]
    fn permissive_native_tool_identities_require_canonical_matching_checksums() {
        let canonical = SourceId::from_url("registry+https://github.com/rust-lang/crates.io-index")
            .expect("canonical registry source");
        let alternative = SourceId::from_url("registry+file:///tmp/alternative-registry")
            .expect("alternate registry source");
        let version = semver::Version::new(1, 0, 0);
        let checksum = "authenticated-package-checksum";

        for name in ["cmake", "pkg-config", "serde", "direct-native-helper"] {
            assert!(audited_proc_macro_package_identity(
                canonical,
                false,
                name,
                &version,
                Some(checksum),
                Some(checksum),
                false,
                OhmProcMacroTrust::All,
            ));

            for (source, replaced, resolved, downloaded) in [
                (canonical, true, Some(checksum), Some(checksum)),
                (alternative, false, Some(checksum), Some(checksum)),
                (canonical, false, None, Some(checksum)),
                (canonical, false, Some(checksum), None),
                (canonical, false, Some(checksum), Some("changed-download")),
            ] {
                assert!(!audited_proc_macro_package_identity(
                    source,
                    replaced,
                    name,
                    &version,
                    resolved,
                    downloaded,
                    false,
                    OhmProcMacroTrust::All,
                ));
            }
        }
    }

    #[test]
    fn macro_runtime_dependencies_require_exact_audited_identities() {
        for (name, version, checksum) in [
            (
                "proc-macro2",
                semver::Version::new(1, 0, 107),
                "985e7ec9bb745e6ce6535b544d84d6cd6f7ad8bd711c398938ae983b91a766d9",
            ),
            (
                "quote",
                semver::Version::new(1, 0, 47),
                "1fbf4db142a473a8d80c26bbf18454ed458bf8d26c8219c331daecfdbd079001",
            ),
            (
                "syn",
                semver::Version::new(3, 0, 3),
                "53e9bae58849f64dfa4f5d5ae372c8341f7305f82a3868709269343628b659a3",
            ),
            (
                "synstructure",
                semver::Version::new(0, 13, 2),
                "728a70f3dbaf5bab7f0c4b1ac8d7ae5ea60a4b5549c8a5914361c99147a709d2",
            ),
            (
                "unicode-ident",
                semver::Version::new(1, 0, 24),
                "e6e4313cd5fcd3dad5cafa179702e2b244f760991f45397d14d4ebf38247da75",
            ),
        ] {
            assert!(audited_proc_macro_runtime_dependency_checksum(
                name, &version, checksum,
            ));
            assert!(!audited_proc_macro_runtime_dependency_checksum(
                name,
                &version,
                "unaudited-checksum",
            ));
            assert!(!audited_proc_macro_runtime_dependency_checksum(
                name,
                &semver::Version::new(version.major, version.minor, version.patch + 1),
                checksum,
            ));
        }
    }

    #[test]
    fn existing_serde_workspaces_have_complete_audited_macro_closures() {
        for (macro_version, macro_checksum, helpers) in [
            (
                semver::Version::new(1, 0, 228),
                "d540f220d3187173da220f885ab66608367b6574e925011a9353e4badda91d79",
                [
                    (
                        "proc-macro2",
                        semver::Version::new(1, 0, 106),
                        "8fd00f0bb2e90d81d1044c2b32617f68fcb9fa3bb7640c23e9c748e53fb30934",
                    ),
                    (
                        "quote",
                        semver::Version::new(1, 0, 46),
                        "dfbc457d0c7a0759a614551b11a6409e5951f6c7537be1f1b7682b9ae9230368",
                    ),
                    (
                        "syn",
                        semver::Version::new(2, 0, 118),
                        "1b9ae57f904213ebb649ce6895b8a66c66f0203b9319718f69a5612a065b1422",
                    ),
                    (
                        "unicode-ident",
                        semver::Version::new(1, 0, 24),
                        "e6e4313cd5fcd3dad5cafa179702e2b244f760991f45397d14d4ebf38247da75",
                    ),
                ],
            ),
            (
                semver::Version::new(1, 0, 228),
                "d540f220d3187173da220f885ab66608367b6574e925011a9353e4badda91d79",
                [
                    (
                        "proc-macro2",
                        semver::Version::new(1, 0, 103),
                        "5ee95bc4ef87b8d5ba32e8b7714ccc834865276eab0aed5c9958d00ec45f49e8",
                    ),
                    (
                        "quote",
                        semver::Version::new(1, 0, 45),
                        "41f2619966050689382d2b44f664f4bc593e129785a36d6ee376ddf37259b924",
                    ),
                    (
                        "syn",
                        semver::Version::new(2, 0, 110),
                        "a99801b5bd34ede4cf3fc688c5919368fea4e4814a4664359503e6015b280aea",
                    ),
                    (
                        "unicode-ident",
                        semver::Version::new(1, 0, 22),
                        "9312f7c4f6ff9069b165498234ce8be658059c6728633667c526e27dc2cf1df5",
                    ),
                ],
            ),
            (
                semver::Version::new(1, 0, 228),
                "d540f220d3187173da220f885ab66608367b6574e925011a9353e4badda91d79",
                [
                    (
                        "proc-macro2",
                        semver::Version::new(1, 0, 93),
                        "60946a68e5f9d28b0dc1c21bb8a97ee7d018a8b322fa57838ba31cc878e22d99",
                    ),
                    (
                        "quote",
                        semver::Version::new(1, 0, 38),
                        "0e4dccaaaf89514f546c693ddc140f729f958c247918a13380cccc6078391acc",
                    ),
                    (
                        "syn",
                        semver::Version::new(2, 0, 96),
                        "d5d0adab1ae378d7f53bdebc67a39f1f151407ef230f0ce2883572f5d8985c80",
                    ),
                    (
                        "unicode-ident",
                        semver::Version::new(1, 0, 14),
                        "adb9e6ca4f869e1180728b7950e35922a7fc6397f7b641499e8f3ef06e50dc83",
                    ),
                ],
            ),
            (
                semver::Version::new(1, 0, 219),
                "5b0276cf7f2c73365f7157c8123c21cd9a50fbbd844757af28ca1f5925fc2a00",
                [
                    (
                        "proc-macro2",
                        semver::Version::new(1, 0, 95),
                        "02b3e5e68a3a1a02aad3ec490a98007cbc13c37cbe84a3cd7b8e406d76e7f778",
                    ),
                    (
                        "quote",
                        semver::Version::new(1, 0, 40),
                        "1885c039570dc00dcb4ff087a89e185fd56bae234ddc7f056a945bf36467248d",
                    ),
                    (
                        "syn",
                        semver::Version::new(2, 0, 104),
                        "17b6f705963418cdb9927482fa304bc562ece2fdd4f616084c50b7023b435a40",
                    ),
                    (
                        "unicode-ident",
                        semver::Version::new(1, 0, 18),
                        "5a5f39404a5da50712a4c1eecf25e90dd62b613502b7e925fd4e4d19b5c96512",
                    ),
                ],
            ),
        ] {
            assert!(audited_proc_macro_checksum(
                "serde_derive",
                &macro_version,
                macro_checksum,
            ));
            for (name, version, checksum) in helpers {
                assert!(
                    audited_proc_macro_runtime_dependency_checksum(name, &version, checksum),
                    "missing the audited {name} {version} runtime dependency",
                );
                assert!(!audited_proc_macro_runtime_dependency_checksum(
                    name,
                    &version,
                    "unaudited-checksum",
                ));
            }
        }
    }

    #[test]
    fn ruff_workspaces_have_complete_audited_macro_runtime_closures() {
        assert!(audited_proc_macro_checksum(
            "async-trait",
            &semver::Version::new(0, 1, 89),
            "9035ad2d096bed7955a320ee7e2230574d28fd3c3a0f186cbea1ff3c7eed5dbb",
        ));

        for (name, version, checksum) in [
            (
                "proc-macro2",
                semver::Version::new(1, 0, 107),
                "985e7ec9bb745e6ce6535b544d84d6cd6f7ad8bd711c398938ae983b91a766d9",
            ),
            (
                "quote",
                semver::Version::new(1, 0, 47),
                "1fbf4db142a473a8d80c26bbf18454ed458bf8d26c8219c331daecfdbd079001",
            ),
            (
                "syn",
                semver::Version::new(2, 0, 119),
                "872831b642d1a07999a962a351ed35b955ea2cfc8f3862091e2a240a84f17297",
            ),
            (
                "synstructure",
                semver::Version::new(0, 13, 2),
                "728a70f3dbaf5bab7f0c4b1ac8d7ae5ea60a4b5549c8a5914361c99147a709d2",
            ),
            (
                "unicode-ident",
                semver::Version::new(1, 0, 24),
                "e6e4313cd5fcd3dad5cafa179702e2b244f760991f45397d14d4ebf38247da75",
            ),
        ] {
            assert!(
                audited_proc_macro_runtime_dependency_checksum(name, &version, checksum),
                "missing the audited {name} {version} runtime dependency",
            );
            assert!(!audited_proc_macro_runtime_dependency_checksum(
                name,
                &version,
                "unaudited-checksum",
            ));
        }

        assert!(!audited_proc_macro_runtime_dependency_checksum(
            "syn",
            &semver::Version::new(2, 0, 120),
            "872831b642d1a07999a962a351ed35b955ea2cfc8f3862091e2a240a84f17297",
        ));
    }

    #[test]
    fn alternate_registries_cannot_supply_macro_runtime_dependencies() {
        let crates_io = SourceId::from_url("registry+https://github.com/rust-lang/crates.io-index")
            .expect("canonical registry source");
        let alternative = SourceId::from_url("registry+file:///tmp/alternative-registry")
            .expect("alternate registry source");

        assert!(is_canonical_unreplaced_crates_io(crates_io, false));
        assert!(!is_canonical_unreplaced_crates_io(crates_io, true));
        assert!(!is_canonical_unreplaced_crates_io(alternative, false));
    }

    #[test]
    fn an_exact_macro_helper_checksum_cannot_authenticate_an_alternate_registry() {
        let crates_io = SourceId::from_url("registry+https://github.com/rust-lang/crates.io-index")
            .expect("canonical registry source");
        let alternative = SourceId::from_url("registry+file:///tmp/alternative-registry")
            .expect("alternate registry source");
        let version = semver::Version::new(3, 0, 3);
        let checksum = "53e9bae58849f64dfa4f5d5ae372c8341f7305f82a3868709269343628b659a3";

        assert!(audited_proc_macro_runtime_dependency_identity(
            crates_io,
            false,
            "syn",
            &version,
            Some(checksum),
            Some(checksum),
            OhmProcMacroTrust::Audited,
        ));
        assert!(!audited_proc_macro_runtime_dependency_identity(
            alternative,
            false,
            "syn",
            &version,
            Some(checksum),
            Some(checksum),
            OhmProcMacroTrust::Audited,
        ));
        assert!(!audited_proc_macro_runtime_dependency_identity(
            crates_io,
            true,
            "syn",
            &version,
            Some(checksum),
            Some(checksum),
            OhmProcMacroTrust::Audited,
        ));
        assert!(!audited_proc_macro_runtime_dependency_identity(
            crates_io,
            false,
            "syn",
            &version,
            Some(checksum),
            Some("unaudited-download"),
            OhmProcMacroTrust::Audited,
        ));
        assert!(!audited_proc_macro_runtime_dependency_identity(
            crates_io,
            false,
            "syn",
            &version,
            None,
            Some(checksum),
            OhmProcMacroTrust::Audited,
        ));
    }

    #[test]
    fn permissive_macro_runtime_trust_still_requires_authenticated_crates_io_sources() {
        let crates_io = SourceId::from_url("registry+https://github.com/rust-lang/crates.io-index")
            .expect("canonical registry source");
        let alternative = SourceId::from_url("registry+file:///tmp/alternative-registry")
            .expect("alternate registry source");
        let version = semver::Version::new(1, 0, 0);
        let checksum = "unaudited-but-authenticated-runtime-helper";

        assert!(!audited_proc_macro_runtime_dependency_identity(
            crates_io,
            false,
            "unaudited-runtime-helper",
            &version,
            Some(checksum),
            Some(checksum),
            OhmProcMacroTrust::Audited,
        ));
        assert!(audited_proc_macro_runtime_dependency_identity(
            crates_io,
            false,
            "unaudited-runtime-helper",
            &version,
            Some(checksum),
            Some(checksum),
            OhmProcMacroTrust::All,
        ));

        for (source, replaced, resolved, downloaded) in [
            (alternative, false, Some(checksum), Some(checksum)),
            (crates_io, true, Some(checksum), Some(checksum)),
            (crates_io, false, None, Some(checksum)),
            (crates_io, false, Some(checksum), None),
            (crates_io, false, Some(checksum), Some("different-checksum")),
        ] {
            assert!(!audited_proc_macro_runtime_dependency_identity(
                source,
                replaced,
                "unaudited-runtime-helper",
                &version,
                resolved,
                downloaded,
                OhmProcMacroTrust::All,
            ));
        }
    }
}
