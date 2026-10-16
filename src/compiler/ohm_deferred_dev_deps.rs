//! Targeted tests validate the dependencies their executable actually uses.
//! Resolution and compiler identities retain the complete graph; only scheduling
//! omits previously unused pure-Rust dev dependencies. Fresh proof is mandatory
//! before accepting any output, and an inconclusive attempt retries once normally.

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

use super::{BuildRunner, CompileKind, CompileMode, Unit};
use crate::util::data_structures::HashSet;
use crate::util::interning::InternedString;
use crate::workspace::dependency::DepKind;

#[derive(Default)]
pub(crate) struct State {
    pub(crate) disabled: bool,
    /// Only direct edges from the selected root; retained transitive edges still build.
    pub(crate) dependencies: HashSet<Unit>,
    pub(crate) retry: Arc<AtomicBool>,
}

impl State {
    pub(crate) fn retry_requested(&self) -> bool {
        self.retry.load(Ordering::Relaxed)
    }
}

#[derive(Debug, thiserror::Error)]
#[error("retrying with the complete development dependency graph")]
pub(crate) struct Retry;

/// Record proof even when opted out, without altering rustc's tracked inputs.
/// Unsupported commands retain the ordinary build path.
pub(crate) fn supported(runner: &BuildRunner<'_, '_>, unit: &Unit) -> bool {
    runner.bcx.gctx.cli_unstable().ohm_defaults()
        && runner.bcx.gctx.cli_unstable().relink_only()
        && !runner.bcx.gctx.cli_unstable().cargo_lints
        && runner.bcx.roots.len() == 1
        && runner.bcx.roots[0] == *unit
        && unit.mode == CompileMode::Test
        && unit.target.is_lib()
        && !unit.target.proc_macro()
        && runner.bcx.ws.is_member_id(unit.pkg.package_id())
        && runner.bcx.build_config.primary_unit_rustc.is_none()
        && !runner.bcx.build_config.dry_run
        && !runner.bcx.build_config.sbom
        && !runner.bcx.build_config.future_incompat_report
        && unit.kind == CompileKind::Host
        && runner.compilation.target_linker(unit.kind).is_none()
        && !super::has_opaque_integration_linker_flags(runner, unit)
        && runner
            .bcx
            .rustc()
            .supports_transparent_unused_externs(runner.bcx.gctx)
        && matches!(
            runner.lto[unit],
            super::lto::Lto::Off | super::lto::Lto::OnlyObject
        )
}

/// Remove only scheduling edges. The original graph remains authoritative for
/// feature resolution, metadata hashes, rustc arguments, and fingerprints.
pub(crate) fn plan(
    runner: &mut BuildRunner<'_, '_>,
    unit: &Unit,
    previous_unused: Option<&HashSet<InternedString>>,
) -> Vec<InternedString> {
    if runner.deferred_dev_deps.disabled
        || !runner.bcx.gctx.cli_unstable().ohm_defer_dev_deps()
        || !supported(runner, unit)
        || runner.fingerprints.get(unit).is_none_or(|fp| {
            fp.is_early_cutoff_candidate()
                || !matches!(fp.fs_status(), super::fingerprint::FsStatus::StaleItem(_))
        })
    {
        return Vec::new();
    }
    let Some(previous_unused) = previous_unused else {
        return Vec::new();
    };
    let (candidates, _) =
        super::unused_integration_workspace_dependencies(runner, unit, previous_unused);
    let dependencies = runner.unit_deps(unit);
    let deferred = dependencies
        .iter()
        .filter(|dep| {
            candidates.contains(&runner.bcx.unit_to_index[&dep.unit])
                && dep.manifest_deps.0.as_ref().is_some_and(|deps| {
                    !deps.is_empty() && deps.iter().all(|dep| dep.kind() == DepKind::Development)
                })
        })
        .map(|dep| dep.unit.clone())
        .collect::<HashSet<_>>();
    if deferred.is_empty() {
        return Vec::new();
    }

    let closure = |roots: Vec<Unit>| {
        let mut pending = roots;
        let mut visited = HashSet::default();
        while let Some(dep) = pending.pop() {
            if visited.insert(dep.clone()) {
                pending.extend(runner.unit_deps(&dep).iter().map(|dep| dep.unit.clone()));
            }
        }
        visited
    };
    let retained = closure(
        dependencies
            .iter()
            .filter(|dep| !deferred.contains(&dep.unit))
            .map(|dep| dep.unit.clone())
            .collect(),
    );
    let removed = closure(deferred.iter().cloned().collect());
    // Build scripts, proc macros, artifact dependencies and native links can
    // contribute effects beyond a direct --extern. Do not speculate over them.
    if removed.difference(&retained).any(|dep| {
        dep.mode != CompileMode::Build
            || !dep.target.is_lib()
            || dep.target.proc_macro()
            || dep.artifact.is_true()
            || dep.pkg.manifest().links().is_some()
            || runner.find_build_script_units(dep).is_some()
            || super::has_opaque_integration_linker_flags(runner, dep)
            || dep
                .target
                .rustc_crate_types()
                .iter()
                .any(|kind| !matches!(kind, super::CrateType::Lib | super::CrateType::Rlib))
    }) {
        return Vec::new();
    }
    let names = dependencies
        .iter()
        .filter(|dep| deferred.contains(&dep.unit))
        .map(|dep| dep.extern_crate_name)
        .collect::<Vec<_>>();
    tracing::info!(target: "cargo::compiler::ohm_deferred_dev_deps", ?names, "deferring unused dev dependencies");
    runner.deferred_dev_deps.dependencies = deferred;
    names
}
