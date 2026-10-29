//! Execute confirmed test binaries serially while other targets compile.
//!
//! Runtime inputs must finish first. Unsupported invocations and tests that have
//! not started retain Cargo's ordinary post-build execution path.

use super::cmd_builds;
use super::ready_test_process::{ProcessGroup, Signals};
use crate::compiler::{BuildRunner, Compilation, CompileKind, CompileMode, Unit, UnitOutput};
use crate::util::data_structures::HashSet;
use crate::util::{CargoResult, GlobalContext};
use cargo_util::{ProcessBuilder, ProcessError};
use std::collections::VecDeque;
use std::process::{Child, ExitStatus};

#[derive(Clone, Debug)]
pub(crate) struct ReadyTestOptions {
    pub args: Vec<String>,
    pub no_fail_fast: bool,
}

pub(crate) struct ReadyTests {
    options: ReadyTestOptions,
    runtime_pending: HashSet<Unit>,
    runtime_ready: bool,
    pending: VecDeque<UnitOutput>,
    active: Option<ActiveTest>,
    results: Vec<(Unit, CargoResult<()>)>,
    stopped: bool,
    signals: Signals,
}

impl ReadyTests {
    /// Install cancellation support only when terminal and signal behavior can
    /// be preserved. A failed setup leaves ordinary execution in place.
    pub(crate) fn new(options: ReadyTestOptions) -> Option<Self> {
        Some(Self {
            options,
            runtime_pending: HashSet::default(),
            runtime_ready: false,
            pending: VecDeque::new(),
            active: None,
            results: Vec::new(),
            stopped: false,
            signals: Signals::new().ok()?,
        })
    }

    /// Wait for the actual queued runtime artifacts, including fresh ones. Old files
    /// on disk and provisional compiler results never establish runtime readiness.
    pub(crate) fn prepare(build: &mut BuildRunner<'_, '_>) {
        build.compilation.prepare_ready_tests(build.bcx);
        let Some(ready) = build.compilation.ready_tests.as_mut() else {
            return;
        };
        ready.runtime_pending = build
            .compiled
            .iter()
            .filter(|unit| {
                unit.mode != CompileMode::Test
                    && !unit.mode.is_doc_test()
                    && (unit.mode.is_run_custom_build()
                        || unit.target.is_executable()
                        || unit.target.is_dylib()
                        || unit.target.is_cdylib())
            })
            .cloned()
            .collect();
    }

    /// Queue a root test only after Cargo has accepted all of its build outputs.
    pub(crate) fn unit_finished(build: &mut BuildRunner<'_, '_>, unit: &Unit) -> CargoResult<()> {
        let Some(mut ready) = build.compilation.ready_tests.take() else {
            return Ok(());
        };
        let result = (|| {
            ready.runtime_pending.remove(unit);
            if !ready.runtime_ready && ready.runtime_pending.is_empty() {
                build.collect_runtime_environment();
                ready.runtime_ready = true;
            }
            if !ready.stopped
                && unit.mode == CompileMode::Test
                && unit.kind == CompileKind::Host
                && build.compilation.target_runner(unit.kind).is_none()
                && build.bcx.roots.contains(unit)
            {
                for output in build.outputs(unit)?.iter() {
                    if output.flavor == crate::compiler::FileFlavor::Normal {
                        ready
                            .pending
                            .push_back(build.unit_output(unit, &output.path)?);
                    }
                }
            }
            Ok(())
        })();
        build.compilation.ready_tests = Some(ready);
        result
    }

    /// Advance serial execution, or cancel the active test after a build error.
    pub(crate) fn poll(build: &mut BuildRunner<'_, '_>, cancel: bool) -> CargoResult<()> {
        let Some(mut ready) = build.compilation.ready_tests.take() else {
            return Ok(());
        };
        let result = if cancel {
            ready.cancel();
            Ok(())
        } else {
            ready.tick(build.bcx.gctx, &build.compilation)
        };
        build.compilation.ready_tests = Some(ready);
        result
    }

    fn tick(&mut self, gctx: &GlobalContext, compilation: &Compilation<'_>) -> CargoResult<()> {
        self.signals.check();
        if let Some(active) = &mut self.active {
            if let Some(status) = active.try_wait()? {
                self.complete(status);
            }
        }
        if self.active.is_some() || self.stopped || !self.runtime_ready {
            return Ok(());
        }
        let Some(output) = self.pending.pop_front() else {
            return Ok(());
        };
        let args = self
            .options
            .args
            .iter()
            .map(String::as_str)
            .collect::<Vec<_>>();
        let (display, mut cmd) = cmd_builds(
            gctx,
            gctx.cwd(),
            &output.unit,
            &output.path,
            output.script_metas.as_ref(),
            &output.env,
            &args,
            compilation,
            "unittests",
        )?;
        if gctx.extra_verbose() {
            cmd.display_env_vars();
        }
        gctx.shell()
            .concise(|shell| shell.status("Running", &display))?;
        gctx.shell()
            .verbose(|shell| shell.status("Running", &cmd))?;
        match ProcessGroup::spawn(&self.signals, &mut cmd.build_command()) {
            Ok((child, group)) => {
                self.active = Some(ActiveTest {
                    child,
                    cmd,
                    unit: output.unit,
                    reaped: false,
                    group,
                });
            }
            Err(_) => {
                // No test executed: let the ordinary path retry after the build.
                self.stopped = true;
            }
        }
        self.signals.check();
        Ok(())
    }

    fn complete(&mut self, status: ExitStatus) {
        let mut active = self.active.take().unwrap();
        active.reaped = true;
        let result = if status.success() {
            Ok(())
        } else {
            Err(ProcessError::new(
                &format!("process didn't exit successfully: {}", active.cmd),
                Some(status),
                None,
            )
            .into())
        };
        self.stopped |= result.is_err() && !self.options.no_fail_fast;
        self.results.push((active.unit.clone(), result));
    }

    /// Finish only the active binary after build locks have been released. Tests
    /// not yet started remain in Compilation.tests and use the ordinary runner.
    pub(crate) fn finish(&mut self) -> CargoResult<Vec<(Unit, CargoResult<()>)>> {
        while let Some(active) = &mut self.active {
            // Keep servicing terminal suspend/resume after compilation ends.
            // A blocking wait would never resume a test stopped by Ctrl-Z.
            self.signals.check();
            if let Some(status) = active.try_wait()? {
                self.complete(status);
            } else {
                std::thread::sleep(std::time::Duration::from_millis(10));
            }
        }
        self.signals.check();
        Ok(std::mem::take(&mut self.results))
    }

    fn cancel(&mut self) {
        self.stopped = true;
        self.pending.clear();
        self.active.take();
        self.signals.check();
    }
}

impl Drop for ReadyTests {
    fn drop(&mut self) {
        self.cancel();
    }
}

struct ActiveTest {
    child: Child,
    cmd: ProcessBuilder,
    unit: Unit,
    reaped: bool,
    group: ProcessGroup,
}

impl ActiveTest {
    fn try_wait(&mut self) -> CargoResult<Option<ExitStatus>> {
        let Some(status) = self.child.try_wait()? else {
            return Ok(None);
        };
        Ok(self.group.finish()?.then_some(status))
    }
}

impl Drop for ActiveTest {
    fn drop(&mut self) {
        if !self.reaped {
            self.group.cancel();
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}
