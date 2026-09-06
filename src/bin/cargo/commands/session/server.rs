//! Serialized request execution with a scoped, transaction-validated plan epoch.

use super::output::{OutputCapture, OutputLimitExceeded};
use super::protocol::{self, ErrorKind, Operation, Response, ResponseStatus, SessionInfo};
use super::transport::{self, SessionListener};
use crate::command_prelude::*;
use cargo::CargoResult;
use cargo::core::compiler::UnitInterner;
use cargo::ops::{CheckOutcome, PreparedCheck};
use cargo::util::session_inputs::{InputTracker, SessionInputs};
use std::os::fd::AsRawFd;
use std::os::unix::net::UnixStream;
use std::time::Instant;

const MAX_ATTEMPTS: u8 = 3;

/// One socket selects one immutable invocation. The factory replays expanded
/// global options, including aliases, into a context with fresh typed caches.
struct SessionConfig<'a, F> {
    initial: &'a GlobalContext,
    args: ArgMatches,
    configure: F,
}

struct State {
    info: SessionInfo,
    checks: u64,
    preparations: u64,
    revision: u64,
    reused: bool,
    reprepare_reason: Option<String>,
    reuse_disabled_reason: Option<String>,
}

impl State {
    fn new(info: SessionInfo) -> Self {
        Self {
            info,
            checks: 0,
            preparations: 0,
            revision: 0,
            reused: false,
            reprepare_reason: None,
            reuse_disabled_reason: None,
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
            revision: self.revision,
            reprepare_reason: self.reprepare_reason.clone(),
            reuse_disabled_reason: self.reuse_disabled_reason.clone(),
            reused: self.reused,
            returncode: 0,
            elapsed_ms: 0.0,
            stdout: String::new(),
            stderr: String::new(),
        }
    }
}

/// Request state never lives in the retained plan. Retries keep the original
/// connection and wall-clock timer, but each attempt gets its own output files.
struct PendingCheck {
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

impl PendingCheck {
    fn begin_attempt(&mut self, state: &mut State, reused: bool) {
        self.attempts += 1;
        state.reused = reused;
        state.reprepare_reason = self.reprepare_reason.clone();
        state.reuse_disabled_reason = None;
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
    Reprepare(PendingCheck),
    Idle,
    Shutdown,
}

fn next_check(listener: &SessionListener, state: &mut State) -> CargoResult<Option<PendingCheck>> {
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
            Operation::Check => {
                // Management commands can address an explicitly named socket
                // from another directory or environment. Checks cannot drift.
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
                return Ok(Some(PendingCheck {
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

pub fn serve(
    gctx: &mut GlobalContext,
    args: &ArgMatches,
    configure: impl Fn(&mut GlobalContext) -> CliResult,
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
            EpochExit::Idle => match next_check(&listener, &mut state)? {
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

fn run_epoch(
    config: &SessionConfig<'_, impl Fn(&mut GlobalContext) -> CliResult>,
    listener: &SessionListener,
    inputs: &SessionInputs,
    state: &mut State,
    mut request: PendingCheck,
) -> CargoResult<EpochExit> {
    if listener.shutdown_requested() {
        request.complete(state, None, Completion::Cancelled);
        return Ok(EpochExit::Shutdown);
    }
    if request.disconnected() {
        return Ok(EpochExit::Idle);
    }
    request.begin_attempt(state, false);
    let capture = match OutputCapture::start() {
        Ok(capture) => capture,
        Err(error) => {
            request.complete(
                state,
                None,
                Completion::Failure(ErrorKind::Internal, error.to_string()),
            );
            return Ok(EpochExit::Idle);
        }
    };
    state.preparations += 1;
    let tracker = inputs.begin();
    let mut gctx = config.initial.fresh_for_session(tracker.clone());
    // Every fallible preparation stage validates the reads it observed before
    // deciding whether its diagnostics belong to a current transaction.
    if let Err(error) = (config.configure)(&mut gctx) {
        let error = error.error.unwrap_or_else(|| {
            anyhow::anyhow!("Cargo configuration exited with {}", error.exit_code)
        });
        return Ok(preparation_failed(
            listener, state, &tracker, &gctx, request, capture, error,
        ));
    }
    gctx.begin_session_check();
    let ws = match config.args.workspace(&gctx) {
        Ok(workspace) => workspace,
        Err(error) => {
            return Ok(preparation_failed(
                listener, state, &tracker, &gctx, request, capture, error,
            ));
        }
    };
    let test = config.args.get_one::<String>("profile").map(String::as_str) == Some("test");
    let options = match config.args.compile_options(
        &gctx,
        UserIntent::Check { test },
        Some(&ws),
        ProfileChecking::LegacyTestOnly,
    ) {
        Ok(options) => options,
        Err(error) => {
            return Ok(preparation_failed(
                listener, state, &tracker, &gctx, request, capture, error,
            ));
        }
    };
    let interner = UnitInterner::new();
    let prepared = match PreparedCheck::new(&ws, &options, &interner) {
        Ok(prepared) => prepared,
        Err(error) => {
            return Ok(preparation_failed(
                listener, state, &tracker, &gctx, request, capture, error,
            ));
        }
    };
    let mut capture = capture;
    loop {
        if listener.shutdown_requested() {
            request.complete(state, Some(capture), Completion::Cancelled);
            return Ok(EpochExit::Shutdown);
        }
        let outcome = prepared.check();
        state.revision = tracker.revision();
        state.reuse_disabled_reason = tracker.reuse_reason().or_else(|| {
            (!prepared.can_reuse()).then(|| "the previous plan is no longer reusable".to_owned())
        });
        match outcome {
            Ok(CheckOutcome::InputsChanged(reason)) => {
                return Ok(reprepare(
                    listener,
                    state,
                    request,
                    capture,
                    reason.to_string(),
                ));
            }
            Ok(CheckOutcome::Complete(result)) => {
                let code = match result {
                    Ok(_) => 0,
                    Err(error) => {
                        cargo::display_error(&error, &mut gctx.shell());
                        101
                    }
                };
                request.complete(state, Some(capture), Completion::Cargo(code));
            }
            Err(error) => {
                return Ok(preparation_failed(
                    listener, state, &tracker, &gctx, request, capture, error,
                ));
            }
        }
        let Some(next) = next_check(listener, state)? else {
            return Ok(EpochExit::Shutdown);
        };
        request = next;
        if !prepared.can_reuse() {
            request.reprepare_reason = state.reuse_disabled_reason.clone();
            return Ok(EpochExit::Reprepare(request));
        }
        request.begin_attempt(state, true);
        capture = match OutputCapture::start() {
            Ok(capture) => capture,
            Err(error) => {
                request.complete(
                    state,
                    None,
                    Completion::Failure(ErrorKind::Internal, error.to_string()),
                );
                return Ok(EpochExit::Idle);
            }
        };
    }
}

fn preparation_failed(
    listener: &SessionListener,
    state: &mut State,
    tracker: &InputTracker,
    gctx: &GlobalContext,
    request: PendingCheck,
    capture: OutputCapture,
    error: anyhow::Error,
) -> EpochExit {
    let validation = tracker.validate();
    state.revision = tracker.revision();
    state.reuse_disabled_reason = tracker.reuse_reason();
    match validation {
        Err(reason) => reprepare(listener, state, request, capture, reason.to_string()),
        Ok(()) => {
            cargo::display_error(&error, &mut gctx.shell());
            request.complete(state, Some(capture), Completion::Cargo(101));
            EpochExit::Idle
        }
    }
}

fn reprepare(
    listener: &SessionListener,
    state: &mut State,
    mut request: PendingCheck,
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
                format!("workspace inputs changed repeatedly during session preparation; retry the check ({reason})"),
            ),
        );
        EpochExit::Idle
    } else {
        EpochExit::Reprepare(request)
    }
}
