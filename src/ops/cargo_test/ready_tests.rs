//! Execute confirmed test binaries serially while other targets compile.
//!
//! Runtime inputs must finish first. Unsupported invocations and tests that have
//! not started retain Cargo's ordinary post-build execution path.

use super::cmd_builds;
use crate::compiler::{BuildRunner, Compilation, CompileKind, CompileMode, Unit, UnitOutput};
use crate::util::data_structures::HashSet;
use crate::util::{CargoResult, GlobalContext};
use cargo_util::{ProcessBuilder, ProcessError};
use std::collections::VecDeque;
use std::io::IsTerminal;
use std::process::{Child, ExitStatus};
use std::sync::atomic::{AtomicBool, AtomicI32, Ordering};

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
        // A separate process group lets a failed build cancel the whole test tree.
        // Keep terminal job control and unsupported platforms on the ordinary path.
        if !cfg!(unix) || std::io::stdin().is_terminal() {
            return None;
        }
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
            if let Some(status) = active.child.try_wait()? {
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
        let mut command = cmd.build_command();
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            command.process_group(0);
        }
        match command.spawn() {
            Ok(child) => {
                self.signals
                    .group
                    .store(child.id() as i32, Ordering::SeqCst);
                self.active = Some(ActiveTest {
                    child,
                    cmd,
                    unit: output.unit,
                    reaped: false,
                });
                self.signals.check();
            }
            Err(_) => {
                // No test executed: let the ordinary path retry after the build.
                self.stopped = true;
            }
        }
        Ok(())
    }

    fn complete(&mut self, status: ExitStatus) {
        let mut active = self.active.take().unwrap();
        active.reaped = true;
        self.signals.group.store(0, Ordering::SeqCst);
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
        if let Some(active) = &mut self.active {
            let status = active.child.wait()?;
            self.complete(status);
        }
        self.signals.check();
        Ok(std::mem::take(&mut self.results))
    }

    fn cancel(&mut self) {
        self.stopped = true;
        self.pending.clear();
        self.active.take();
        self.signals.group.store(0, Ordering::SeqCst);
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
}

impl Drop for ActiveTest {
    fn drop(&mut self) {
        if !self.reaped {
            #[cfg(unix)]
            unsafe {
                libc::kill(-(self.child.id() as i32), libc::SIGKILL);
            }
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}

// Cargo normally leaves these termination signals at their default disposition.
// An embedding application with its own handlers conservatively gets fallback.
static SIGNALS_IN_USE: AtomicBool = AtomicBool::new(false);
static ACTIVE_GROUP: AtomicI32 = AtomicI32::new(0);
static INTERRUPTED: AtomicI32 = AtomicI32::new(0);

/// Defer Cargo's default signal action until a just-spawned child is registered,
/// closing the spawn/handler race while keeping signal callbacks async-safe.
struct Signals {
    group: &'static AtomicI32,
    #[cfg(unix)]
    previous: Vec<(i32, libc::sigaction)>,
}

#[cfg(unix)]
extern "C" fn forward_signal(signal: i32) {
    let _ = INTERRUPTED.compare_exchange(0, signal, Ordering::SeqCst, Ordering::SeqCst);
    let id = ACTIVE_GROUP.load(Ordering::SeqCst);
    if id > 0 {
        // SAFETY: kill is async-signal-safe; this is our child's process group.
        unsafe {
            libc::kill(-id, libc::SIGKILL);
        }
    }
}

impl Signals {
    fn new() -> CargoResult<Self> {
        #[cfg(not(unix))]
        anyhow::bail!("early test execution is only supported on Unix");
        #[cfg(unix)]
        {
            anyhow::ensure!(
                SIGNALS_IN_USE
                    .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
                    .is_ok(),
                "signal forwarding already active"
            );
            let mut signals = Self {
                group: &ACTIVE_GROUP,
                previous: Vec::new(),
            };
            for signal in [libc::SIGINT, libc::SIGTERM, libc::SIGHUP, libc::SIGQUIT] {
                // SAFETY: valid signal numbers, initialized sigaction structures,
                // and an extern C callback using only atomics and kill.
                unsafe {
                    let mut previous: libc::sigaction = std::mem::zeroed();
                    if libc::sigaction(signal, std::ptr::null(), &mut previous) != 0 {
                        return Err(std::io::Error::last_os_error().into());
                    }
                    anyhow::ensure!(
                        previous.sa_sigaction == libc::SIG_DFL,
                        "custom signal handler requires ordinary test execution"
                    );
                    let mut action: libc::sigaction = std::mem::zeroed();
                    action.sa_sigaction = forward_signal as *const () as usize;
                    libc::sigemptyset(&mut action.sa_mask);
                    if libc::sigaction(signal, &action, std::ptr::null_mut()) != 0 {
                        return Err(std::io::Error::last_os_error().into());
                    }
                    signals.previous.push((signal, previous));
                }
            }
            Ok(signals)
        }
    }

    fn check(&self) {
        #[cfg(unix)]
        {
            let signal = INTERRUPTED.load(Ordering::SeqCst);
            if signal != 0 {
                // SAFETY: kill the owned process group before restoring and
                // delivering the signal's original default action to Cargo.
                unsafe {
                    let id = self.group.load(Ordering::SeqCst);
                    if id > 0 {
                        libc::kill(-id, libc::SIGKILL);
                    }
                    libc::signal(signal, libc::SIG_DFL);
                    libc::raise(signal);
                }
                std::process::exit(128 + signal);
            }
        }
    }
}

impl Drop for Signals {
    fn drop(&mut self) {
        #[cfg(unix)]
        for (signal, previous) in self.previous.drain(..) {
            // SAFETY: restore the disposition saved before installing our handler.
            unsafe {
                libc::sigaction(signal, &previous, std::ptr::null_mut());
            }
        }
        ACTIVE_GROUP.store(0, Ordering::SeqCst);
        INTERRUPTED.store(0, Ordering::SeqCst);
        SIGNALS_IN_USE.store(false, Ordering::SeqCst);
    }
}
