//! Serialized workspace commands with independently validated retained plans.

use super::output::{OutputCapture, OutputLimitExceeded};
use super::protocol::{self, ErrorKind, Operation, Response, ResponseStatus, SessionInfo};
use super::transport::{self, SessionListener};
use crate::command_prelude::*;
use cargo::CargoResult;
use cargo::core::Workspace;
use cargo::core::compiler::UnitInterner;
use cargo::ops::{CompileOptions, CompileOutcome, PreparedBuild, TestOptions};
use cargo::util::data_structures::HashMap;
use cargo::util::session_inputs::{InputTracker, SessionInputs};
use std::collections::BTreeMap;
use std::ffi::OsString;
use std::os::fd::AsRawFd;
use std::os::unix::ffi::OsStringExt;
use std::os::unix::net::UnixStream;
use std::time::Instant;
use typed_arena::Arena;

const MAX_ATTEMPTS: u8 = 3;

/// One socket fixes the launch environment and supplies command defaults. The
/// factory applies request options to a context with fresh typed caches.
struct SessionConfig<'a, F> {
    initial: &'a GlobalContext,
    args: ArgMatches,
    configure: F,
}

struct State {
    info: SessionInfo,
    checks: u64,
    preparations: u64,
    command: Option<Operation>,
    plan_id: Option<u64>,
    cached_plans: usize,
    revision: u64,
    reused: bool,
    reprepare_reason: Option<String>,
    reuse_disabled_reason: Option<String>,
    compiler_worker: Option<cargo::util::session_worker::WorkerStats>,
}

impl State {
    fn new(info: SessionInfo) -> Self {
        Self {
            info,
            checks: 0,
            preparations: 0,
            command: None,
            plan_id: None,
            cached_plans: 0,
            revision: 0,
            reused: false,
            reprepare_reason: None,
            reuse_disabled_reason: None,
            compiler_worker: None,
        }
    }

    fn response(&self) -> Response {
        Response {
            version: protocol::VERSION,
            session: self.info.clone(),
            status: ResponseStatus::Complete,
            error_kind: None,
            pid: std::process::id(),
            checks: self.checks,
            preparations: self.preparations,
            command: self.command,
            plan_id: self.plan_id,
            cached_plans: self.cached_plans,
            revision: self.revision,
            reprepare_reason: self.reprepare_reason.clone(),
            reuse_disabled_reason: self.reuse_disabled_reason.clone(),
            reused: self.reused,
            compiler_worker: self.compiler_worker.clone(),
            returncode: 0,
            elapsed_ms: 0.0,
            stdout: String::new(),
            stderr: String::new(),
        }
    }
}

/// Request state never lives in the retained plan. Retries keep the original
/// connection and wall-clock timer, but each attempt gets its own output files.
struct PendingRequest {
    key: PlanKey,
    connection: UnixStream,
    started: Instant,
    attempts: u8,
    reprepare_reason: Option<String>,
}

enum Completion {
    Cargo(i32),
    Failure(ErrorKind, String),
    Cancelled,
}

impl PendingRequest {
    fn begin_attempt(&mut self, state: &mut State, reused: bool) {
        self.attempts += 1;
        state.reused = reused;
        state.command = Some(self.key.operation);
        state.plan_id = None;
        state.reprepare_reason = self.reprepare_reason.clone();
        state.reuse_disabled_reason = None;
        state.compiler_worker = None;
    }

    fn disconnected(&self) -> bool {
        let mut descriptor = libc::pollfd {
            fd: self.connection.as_raw_fd(),
            events: 0,
            revents: 0,
        };
        // SAFETY: the request owns this descriptor throughout the poll. A
        // hangup can cancel a retry, but never interrupts an executing job.
        (unsafe { libc::poll(&mut descriptor, 1, 0) }) > 0
            && descriptor.revents & (libc::POLLHUP | libc::POLLERR | libc::POLLNVAL) != 0
    }

    fn complete(mut self, state: &State, capture: Option<OutputCapture>, completion: Completion) {
        let mut response = state.response();
        match completion {
            Completion::Cargo(code) => response.returncode = code,
            Completion::Failure(kind, error) => {
                response.status = ResponseStatus::Failed;
                response.error_kind = Some(kind);
                response.returncode = 101;
                response.stderr = format!("error: {error}\n");
            }
            Completion::Cancelled => {
                response.status = ResponseStatus::Cancelled;
                response.error_kind = Some(ErrorKind::ShuttingDown);
                response.returncode = 130;
                response.stderr = "error: the Cargo session is shutting down\n".to_owned();
            }
        }
        if let Some(capture) = capture {
            match capture.finish() {
                Ok(output) => {
                    response.stdout = output.stdout;
                    response.stderr.insert_str(0, &output.stderr);
                }
                Err(error) => {
                    response.status = ResponseStatus::Failed;
                    response.error_kind = Some(if error.is::<OutputLimitExceeded>() {
                        ErrorKind::OutputLimit
                    } else {
                        ErrorKind::Internal
                    });
                    response.returncode = 101;
                    response.stdout.clear();
                    response.stderr = format!("error: could not capture Cargo output: {error:#}\n");
                }
            }
        }
        response.elapsed_ms = self.started.elapsed().as_secs_f64() * 1000.0;
        // Delivery failure belongs to this connection, not to the plan epoch.
        let _ =
            protocol::write_response(transport::response_writer(&mut self.connection), &response);
    }
}

/// Returning from an epoch drops every context-backed planning object before
/// the server prepares again or waits without a usable plan.
enum EpochExit {
    Reprepare(PendingRequest),
    Idle,
    Shutdown,
}

fn next_request(
    listener: &SessionListener,
    state: &mut State,
) -> CargoResult<Option<PendingRequest>> {
    while let Some(mut connection) = listener.accept()? {
        let request = match protocol::read_request(listener.request_reader(&mut connection)) {
            Ok(request) => request,
            Err(error) => {
                if listener.shutdown_requested() {
                    return Ok(None);
                }
                reject(
                    &mut connection,
                    state,
                    ErrorKind::Protocol,
                    error.to_string(),
                );
                continue;
            }
        };
        if matches!(request.command, Operation::Status | Operation::Stop)
            && !request.args.is_empty()
        {
            reject(
                &mut connection,
                state,
                ErrorKind::Protocol,
                "session administration requests do not accept Cargo arguments".to_owned(),
            );
            continue;
        }
        match request.command {
            Operation::Status => {
                let _ = protocol::write_response(
                    transport::response_writer(&mut connection),
                    &state.response(),
                );
            }
            Operation::Stop => {
                let _ = protocol::write_response(
                    transport::response_writer(&mut connection),
                    &state.response(),
                );
                return Ok(None);
            }
            Operation::Check
            | Operation::Build
            | Operation::Clippy
            | Operation::Test
            | Operation::Bench => {
                // Management commands can address an explicitly named socket
                // from another directory or environment. Build commands cannot drift.
                if request.identity != state.info.identity {
                    reject(
                        &mut connection,
                        state,
                        ErrorKind::Identity,
                        "the session's working directory, environment, or Cargo executable changed; restart the session".to_owned(),
                    );
                    continue;
                }
                state.checks += 1;
                return Ok(Some(PendingRequest {
                    key: PlanKey {
                        operation: request.command,
                        args: request.args.into_iter().map(OsString::from_vec).collect(),
                    },
                    connection,
                    started: Instant::now(),
                    attempts: 0,
                    reprepare_reason: None,
                }));
            }
        }
    }
    Ok(None)
}

fn reject(connection: &mut UnixStream, state: &State, kind: ErrorKind, error: String) {
    let mut response = state.response();
    response.status = ResponseStatus::Rejected;
    response.error_kind = Some(kind);
    response.returncode = 1;
    response.stderr = format!("error: {error}\n");
    let _ = protocol::write_response(transport::response_writer(connection), &response);
}

#[derive(Clone, Eq, Hash, PartialEq)]
struct PlanKey {
    operation: Operation,
    args: Vec<OsString>,
}

enum CommandOptions {
    Compile(CompileOptions),
    Test(TestOptions, Vec<String>),
    Bench(TestOptions, Vec<String>),
}

impl CommandOptions {
    fn compile(&self) -> &CompileOptions {
        match self {
            Self::Compile(options) => options,
            Self::Test(options, _) | Self::Bench(options, _) => &options.compile_opts,
        }
    }

    /// Execute runtime work only after compilation validates. Once a harness
    /// starts, its result is returned without retrying the request.
    fn finish(
        &self,
        ws: &Workspace<'_>,
        compilation: cargo::core::compiler::Compilation<'_>,
    ) -> CliResult {
        match self {
            Self::Compile(_) => Ok(()),
            Self::Test(options, args) => cargo::ops::run_compiled_tests(
                ws,
                options,
                &args.iter().map(String::as_str).collect::<Vec<_>>(),
                compilation,
            ),
            Self::Bench(options, args) => cargo::ops::run_compiled_benches(
                ws,
                options,
                &args.iter().map(String::as_str).collect::<Vec<_>>(),
                compilation,
            ),
        }
    }
}

struct Plan<'a> {
    id: u64,
    workspace: &'a Workspace<'a>,
    options: &'a CommandOptions,
    prepared: PreparedBuild<'a, 'a>,
    tracker: InputTracker,
}

pub fn serve(
    gctx: &mut GlobalContext,
    args: &ArgMatches,
    configure: impl Fn(&mut GlobalContext, &ArgMatches) -> CliResult,
) -> CliResult {
    let config = SessionConfig {
        initial: gctx,
        args: args.clone(),
        configure,
    };
    let path = transport::socket_path(gctx, args)?;
    let listener = SessionListener::bind(path.clone())?;
    gctx.shell().status("Listening", path.display())?;
    let inputs = SessionInputs::default();
    let mut state = State::new(SessionInfo::new(gctx)?);
    let mut transition = EpochExit::Idle;
    loop {
        transition = match transition {
            EpochExit::Idle => match next_request(&listener, &mut state)? {
                Some(request) => EpochExit::Reprepare(request),
                None => EpochExit::Shutdown,
            },
            EpochExit::Reprepare(request) => {
                run_epoch(&config, &listener, &inputs, &mut state, request)?
            }
            EpochExit::Shutdown => break,
        };
    }
    Ok(())
}

/// Arenas own every borrowed Cargo object and are dropped in dependency order.
/// No lifetime is extended and no object is leaked. A bounded number of total
/// preparations (including retired plans) limits each arena generation.
fn run_epoch(
    config: &SessionConfig<'_, impl Fn(&mut GlobalContext, &ArgMatches) -> CliResult>,
    listener: &SessionListener,
    inputs: &SessionInputs,
    state: &mut State,
    first: PendingRequest,
) -> CargoResult<EpochExit> {
    let _generation = inputs.begin();
    let contexts = Arena::new();
    let workspaces = Arena::new();
    let options = Arena::new();
    let interners = Arena::new();
    let mut plans = HashMap::<PlanKey, Plan<'_>>::default();
    let mut allocations = 0usize;
    let capacity = usize::from(*config.args.get_one::<u16>("max-plans").unwrap());
    let mut pending = Some(first);
    state.cached_plans = 0;
    loop {
        let mut request = match pending.take() {
            Some(request) => request,
            None => match next_request(listener, state)? {
                Some(request) => request,
                None => return Ok(EpochExit::Shutdown),
            },
        };
        if listener.shutdown_requested() {
            request.complete(state, None, Completion::Cancelled);
            return Ok(EpochExit::Shutdown);
        }
        if request.disconnected() {
            continue;
        }
        let key = request.key.clone();
        let reused = plans.contains_key(&key);
        if !reused && allocations == capacity {
            request.reprepare_reason.get_or_insert_with(|| {
                "command-plan capacity reached; releasing retained state".to_owned()
            });
            return Ok(EpochExit::Reprepare(request));
        }
        request.begin_attempt(state, reused);
        let capture = match OutputCapture::start() {
            Ok(capture) => capture,
            Err(error) => {
                request.complete(
                    state,
                    None,
                    Completion::Failure(ErrorKind::Internal, error.to_string()),
                );
                continue;
            }
        };
        if !reused {
            allocations += 1;
            state.preparations += 1;
            let tracker = inputs.track();
            let result = prepare_command(config, &key, &tracker);
            match result {
                Ok((mut gctx, parsed)) if parsed.clippy_fix => {
                    // Cargo fix owns its diagnostic server and may edit sources.
                    // Invoke its ordinary execution path once; never retry it.
                    if let Err(reason) = tracker.validate() {
                        match reprepare(listener, state, request, capture, reason.to_string()) {
                            EpochExit::Reprepare(next) => pending = Some(next),
                            EpochExit::Idle => (),
                            EpochExit::Shutdown => return Ok(EpochExit::Shutdown),
                        }
                        continue;
                    }
                    if request.disconnected() {
                        drop(capture);
                        continue;
                    }
                    let (_, args) = parsed.root.subcommand().unwrap();
                    let result = super::super::fix::exec(&mut gctx, args);
                    state.revision = tracker.revision();
                    state.reuse_disabled_reason =
                        Some("Clippy fix uses ordinary request-scoped execution".to_owned());
                    let code = result_code(&gctx, result);
                    request.complete(state, Some(capture), Completion::Cargo(code));
                    continue;
                }
                Ok((gctx, parsed)) => {
                    let gctx = contexts.alloc(gctx);
                    let result = prepare_plan(
                        config,
                        &key,
                        &parsed.root,
                        gctx,
                        &workspaces,
                        &options,
                        &interners,
                        tracker.clone(),
                        state.preparations,
                    );
                    match result {
                        Ok(plan) => {
                            plans.insert(key.clone(), plan);
                        }
                        Err(error) => {
                            if let Err(reason) = tracker.validate() {
                                match reprepare(
                                    listener,
                                    state,
                                    request,
                                    capture,
                                    reason.to_string(),
                                ) {
                                    EpochExit::Reprepare(next) => pending = Some(next),
                                    EpochExit::Idle => (),
                                    EpochExit::Shutdown => return Ok(EpochExit::Shutdown),
                                }
                            } else {
                                state.revision = tracker.revision();
                                state.reuse_disabled_reason = tracker.reuse_reason();
                                let code = result_code(gctx, Err(error));
                                request.complete(state, Some(capture), Completion::Cargo(code));
                            }
                            continue;
                        }
                    }
                }
                Err(error) => {
                    if let Err(reason) = tracker.validate() {
                        match reprepare(listener, state, request, capture, reason.to_string()) {
                            EpochExit::Reprepare(next) => pending = Some(next),
                            EpochExit::Idle => (),
                            EpochExit::Shutdown => return Ok(EpochExit::Shutdown),
                        }
                    } else {
                        state.revision = tracker.revision();
                        state.reuse_disabled_reason = tracker.reuse_reason();
                        let code = result_code(config.initial, Err(error));
                        request.complete(state, Some(capture), Completion::Cargo(code));
                    }
                    continue;
                }
            }
        }
        let plan = &plans[&key];
        state.plan_id = Some(plan.id);
        state.cached_plans = plans.len();
        let outcome = plan.prepared.compile();
        state.compiler_worker = plan.prepared.compiler_worker_stats();
        state.revision = plan.tracker.revision();
        state.reuse_disabled_reason = plan.tracker.reuse_reason().or_else(|| {
            (!plan.prepared.can_reuse())
                .then(|| "the previous plan is no longer reusable".to_owned())
        });
        match outcome {
            Ok(CompileOutcome::InputsChanged(reason)) => {
                plans.remove(&key);
                state.cached_plans = plans.len();
                match reprepare(listener, state, request, capture, reason.to_string()) {
                    EpochExit::Reprepare(next) => pending = Some(next),
                    EpochExit::Idle => (),
                    EpochExit::Shutdown => return Ok(EpochExit::Shutdown),
                }
            }
            result => {
                let result = match result {
                    Ok(CompileOutcome::Complete(Ok(compilation))) => {
                        if request.disconnected() {
                            if !plan.prepared.can_reuse() {
                                plans.remove(&key);
                                state.cached_plans = plans.len();
                            }
                            drop(capture);
                            continue;
                        }
                        plan.options.finish(plan.workspace, compilation)
                    }
                    Ok(CompileOutcome::Complete(Err(error))) | Err(error) => Err(error.into()),
                    Ok(CompileOutcome::InputsChanged(_)) => unreachable!(),
                };
                let code = result_code(plan.workspace.gctx(), result);
                // Runtime results are final. Any inputs changed by the harness
                // are validated before the next use of this plan, just like
                // external edits between requests.
                state.revision = plan.tracker.revision();
                if !plan.prepared.can_reuse() {
                    plans.remove(&key);
                    state.cached_plans = plans.len();
                }
                request.complete(state, Some(capture), Completion::Cargo(code));
            }
        }
    }
}

fn prepare_command(
    config: &SessionConfig<'_, impl Fn(&mut GlobalContext, &ArgMatches) -> CliResult>,
    key: &PlanKey,
    tracker: &InputTracker,
) -> Result<(GlobalContext, super::arguments::ParsedCommand), CliError> {
    let mut gctx = config.initial.fresh_for_session(tracker.clone());
    let parsed = super::arguments::parse(&gctx, &config.args, key.operation, &key.args)?;
    (config.configure)(&mut gctx, &parsed.root)?;
    if let Some(args) = &parsed.clippy_args {
        let driver = gctx.resolve_session_clippy_driver()?;
        let overlay = BTreeMap::from([
            (
                "RUSTC_WORKSPACE_WRAPPER".to_owned(),
                driver.as_os_str().to_owned(),
            ),
            ("CLIPPY_ARGS".to_owned(), OsString::from(args)),
            // The protocol captures non-interactive output, as cargo-clippy does with pipes.
            ("CLIPPY_TERMINAL_WIDTH".to_owned(), OsString::from("0")),
        ]);
        gctx = config
            .initial
            .fresh_for_session_with_env(tracker.clone(), overlay, Some(driver));
        (config.configure)(&mut gctx, &parsed.root)?;
    }
    Ok((gctx, parsed))
}

#[allow(clippy::too_many_arguments)]
fn prepare_plan<'a>(
    config: &SessionConfig<'_, impl Fn(&mut GlobalContext, &ArgMatches) -> CliResult>,
    key: &PlanKey,
    parsed: &ArgMatches,
    gctx: &'a GlobalContext,
    workspaces: &'a Arena<Workspace<'a>>,
    options: &'a Arena<CommandOptions>,
    interners: &'a Arena<UnitInterner>,
    tracker: InputTracker,
    id: u64,
) -> Result<Plan<'a>, CliError> {
    let (_, args) = parsed.subcommand().unwrap();
    let workspace = workspaces.alloc(args.workspace(gctx)?);
    let value = match key.operation {
        Operation::Check | Operation::Clippy => {
            CommandOptions::Compile(super::super::check::compile_options(gctx, args, workspace)?)
        }
        Operation::Build => {
            CommandOptions::Compile(super::super::build::compile_options(gctx, args, workspace)?)
        }
        Operation::Test => {
            let (options, args) = super::super::test::options(gctx, args, workspace)?;
            CommandOptions::Test(options, args)
        }
        Operation::Bench => {
            let (options, args) = super::super::bench::options(gctx, args, workspace)?;
            CommandOptions::Bench(options, args)
        }
        Operation::Status | Operation::Stop => unreachable!(),
    };
    let options = options.alloc(value);
    let interner = interners.alloc(UnitInterner::new());
    let prepared = PreparedBuild::new(
        workspace,
        options.compile(),
        interner,
        config
            .args
            .get_one::<std::path::PathBuf>("compiler-worker")
            .map(std::path::PathBuf::as_path),
    )?;
    Ok(Plan {
        id,
        workspace,
        options,
        prepared,
        tracker,
    })
}

fn result_code(gctx: &GlobalContext, result: CliResult) -> i32 {
    match result {
        Ok(()) => 0,
        Err(error) => {
            if let Some(error) = error.error {
                cargo::display_error(&error, &mut gctx.shell());
            }
            error.exit_code
        }
    }
}

fn reprepare(
    listener: &SessionListener,
    state: &mut State,
    mut request: PendingRequest,
    capture: OutputCapture,
    reason: String,
) -> EpochExit {
    // Drop restores stdout/stderr before either retrying or responding. Output
    // from an obsolete transaction must never be presented as the result.
    drop(capture);
    state.reprepare_reason = Some(reason.clone());
    request.reprepare_reason = Some(reason.clone());
    if listener.shutdown_requested() {
        request.complete(state, None, Completion::Cancelled);
        EpochExit::Shutdown
    } else if request.disconnected() {
        EpochExit::Idle
    } else if request.attempts >= MAX_ATTEMPTS {
        request.complete(
            state,
                None,
            Completion::Failure(
                ErrorKind::InputsChanged,
                format!("workspace inputs changed repeatedly during session preparation; retry the command ({reason})"),
            ),
        );
        EpochExit::Idle
    } else {
        EpochExit::Reprepare(request)
    }
}
