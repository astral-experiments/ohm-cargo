//! Retain Cargo's compilation front end for a command configuration.
//!
//! A session keeps a `BuildContext`, but creates a new `BuildRunner` for every
//! command. Mutable fingerprints, build-script outputs, jobs, and build locks have
//! the same lifetime as in an ordinary Cargo invocation.

use std::cell::Cell;
use std::path::Path;
use std::sync::Arc;

use anyhow::{Context as _, bail};

use crate::core::Workspace;
use crate::core::compiler::build_runner::StaleBuiltRegistryDependency;
use crate::core::compiler::{
    BuildContext, BuildRunner, Compilation, DefaultExecutor, Executor, UnitInterner,
};
use crate::ops::CompileOptions;
use crate::util::CargoResult;
use crate::util::context::WarningHandling;
use crate::util::session_inputs::{InputTracker, Invalidation};
use crate::util::session_worker::{WorkerExecutor, WorkerStats};

/// A build result is publishable only after its planning inputs validate.
pub enum CompileOutcome<'gctx> {
    Complete(CargoResult<Compilation<'gctx>>),
    InputsChanged(Invalidation),
}

/// A prepared compilation of a workspace with fixed command-line configuration.
///
/// The server owns the workspace, options, and interner in bounded arenas. A
/// planning input change retires this plan and its context-backed caches; the
/// next preparation uses a fresh `GlobalContext`.
pub struct PreparedBuild<'a, 'gctx> {
    bcx: BuildContext<'a, 'gctx>,
    options: &'a CompileOptions,
    inputs: InputTracker,
    invalidated: Cell<bool>,
    executor: Arc<dyn Executor>,
    worker: Option<Arc<WorkerExecutor>>,
}

impl<'a, 'gctx> PreparedBuild<'a, 'gctx> {
    pub fn new(
        ws: &'a Workspace<'gctx>,
        options: &'a CompileOptions,
        interner: &'a UnitInterner,
        compiler_worker: Option<&Path>,
    ) -> CargoResult<Self> {
        if ws.gctx().cli_unstable().build_analysis {
            bail!("`cargo session` does not yet support `-Zbuild-analysis`");
        }
        let inputs = ws
            .gctx()
            .session_inputs()
            .context("session input tracking must start before workspace construction")?
            .clone();
        if ws.gctx().cli_unstable().json_target_spec {
            inputs.require_fresh("custom target specifications have undeclared compiler inputs");
        }
        if ws.gctx().cli_unstable().build_std.is_some() {
            inputs.require_fresh("building the standard library requires fresh preparation");
        }
        let bcx = super::create_bcx(ws, options, interner, None)?;
        let worker = compiler_worker
            .map(|path| WorkerExecutor::new(&bcx, path, &inputs).map(Arc::new))
            .transpose()?;
        let executor: Arc<dyn Executor> = match &worker {
            Some(worker) => worker.clone(),
            None => Arc::new(DefaultExecutor),
        };
        Ok(Self {
            bcx,
            options,
            inputs,
            invalidated: Cell::new(false),
            executor,
            worker,
        })
    }

    pub fn compiler_worker_stats(&self) -> Option<WorkerStats> {
        self.worker.as_ref().map(|worker| worker.stats())
    }

    /// Whether all queries in this plan have a complete dependency contract.
    pub fn can_reuse(&self) -> bool {
        self.inputs.reuse_reason().is_none() && !self.invalidated.get()
    }

    /// Execute with fresh request state and validate even an unsuccessful build.
    ///
    /// The caller discards diagnostics and retires this plan on an input
    /// change. A stable compiler error remains a normal, publishable result.
    pub fn compile(&self) -> CargoResult<CompileOutcome<'gctx>> {
        if let Err(changed) = self.inputs.validate() {
            return Ok(CompileOutcome::InputsChanged(changed));
        }
        let result = self.compile_inner();
        if let Err(changed) = self.inputs.validate() {
            return Ok(CompileOutcome::InputsChanged(changed));
        }
        Ok(CompileOutcome::Complete(result))
    }

    fn compile_inner(&self) -> CargoResult<Compilation<'gctx>> {
        self.bcx.gctx.begin_session_check();
        self.bcx.rustc().reset_session_caches();
        let parse_output = crate::diagnostics::passes::emit_parse_diagnostics(
            self.bcx.ws,
            crate::diagnostics::rules::PARSE_PASS_RULES,
        )?;
        let exec = self.executor.clone();
        let result = if self.options.build_config.unit_graph {
            crate::core::compiler::unit_graph::emit_serialized_unit_graph(
                &self.bcx.roots,
                &self.bcx.unit_graph,
                self.bcx.gctx,
            )?;
            Compilation::new(&self.bcx)
        } else {
            crate::core::global_cache_tracker::refresh_session_usage(self.bcx.gctx)?;
            crate::core::gc::auto_gc(self.bcx.gctx);
            let runner = BuildRunner::new_with_jobserver(
                &self.bcx,
                self.worker.as_ref().map(|worker| worker.jobserver()),
            )?;
            if self.options.build_config.dry_run {
                runner.dry_run()
            } else {
                runner.compile(&exec)
            }
        };
        let result = match result {
            Err(error) if error.is::<StaleBuiltRegistryDependency>() => {
                // Keep Ohm's existing graph-regeneration and registry fallback
                // logic authoritative. The speculative retained graph is retired.
                self.invalidated.set(true);
                super::cargo_compile::compile_ws(self.bcx.ws, self.options, &exec)
            }
            result => result,
        };
        let compilation = result?;
        if self.bcx.gctx.warning_handling()? == WarningHandling::Deny
            && compilation.lint_warning_count + parse_output.lint_warning_count > 0
        {
            bail!("warnings are denied by `build.warnings` configuration");
        }
        Ok(compilation)
    }
}
