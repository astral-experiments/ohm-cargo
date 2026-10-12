//! Retain one compiler behind an explicitly started workspace session.

use std::collections::BTreeMap;
use std::ffi::OsString;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Mutex, mpsc};
use std::time::{Duration, Instant};

use anyhow::{Context, ensure};
use cargo_util::ProcessBuilder;
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::util::CargoResult;

pub mod workspace;

const TIMEOUT: Duration = Duration::from_secs(300);
const OUTPUT_LIMIT: usize = 64 * 1024 * 1024;

#[derive(Clone, Serialize, Deserialize)]
struct CompilerConfiguration {
    compiler: String,
    compiler_fingerprint: Option<u64>,
    directory: PathBuf,
    jobs: u32,
}

#[derive(PartialEq, Eq)]
struct Invocation {
    program: OsString,
    arguments: Vec<OsString>,
    arg0: Option<OsString>,
    environment: BTreeMap<OsString, OsString>,
    cwd: Option<PathBuf>,
    compiler: String,
    compiler_fingerprint: Option<u64>,
    jobs: u32,
}

#[derive(Default)]
struct State {
    worker: Option<Worker>,
    invocation: Option<Invocation>,
    scratch: Option<tempfile::TempDir>,
}

struct CompilerSession {
    source: PathBuf,
    state: Mutex<State>,
}

#[derive(Serialize, Deserialize)]
struct Checked {
    diagnostics: Vec<String>,
    errors: bool,
    retained: bool,
    worker_pid: u32,
    macro_validation_seconds: f64,
}

impl CompilerSession {
    fn new(source: PathBuf) -> Self {
        Self {
            source,
            state: Mutex::new(State::default()),
        }
    }

    fn check(
        &self,
        config: &CompilerConfiguration,
        command: &ProcessBuilder,
        environment: BTreeMap<OsString, OsString>,
        cancelled: &AtomicBool,
    ) -> CargoResult<Option<Checked>> {
        let invocation = Invocation {
            program: command.get_program().clone(),
            arguments: command.get_args().cloned().collect(),
            arg0: command.get_arg0().map(ToOwned::to_owned),
            environment,
            cwd: command.get_cwd().map(Path::to_path_buf),
            compiler: config.compiler.clone(),
            compiler_fingerprint: config.compiler_fingerprint,
            jobs: config.jobs,
        };
        let mut state = self.state.lock().unwrap();
        if state.invocation.as_ref() != Some(&invocation) {
            state.worker = None;
        }
        if state.scratch.is_none() {
            std::fs::create_dir_all(&config.directory)?;
            state.scratch = Some(
                tempfile::Builder::new()
                    .prefix("session-")
                    .tempdir_in(&config.directory)?,
            );
        }
        let scratch = state.scratch.as_ref().unwrap().path().to_owned();
        state.invocation = Some(invocation);
        let environment = state.invocation.as_ref().unwrap().environment.clone();
        let mut macro_validation_seconds = 0.0;
        let response = if let Some(worker) = &mut state.worker {
            (|| {
                let expansion = if let Some(previous) = &worker.expansion {
                    let started = Instant::now();
                    let outputs = tempfile::Builder::new()
                        .prefix("expansion-")
                        .tempdir_in(&scratch)?;
                    let mut command = isolated_command(
                        command,
                        outputs.path(),
                        CompilerMode::Expansion,
                        &self.source,
                    )?;
                    let mut validator =
                        Worker::start(&mut command, outputs, &environment, config.jobs)?;
                    let (boundary, diagnostics) = validator.response("expanded", 0, cancelled)?;
                    ensure!(
                        diagnostics.is_empty(),
                        "macro validation produced diagnostics"
                    );
                    validator.finish_validation(cancelled)?;
                    let expansion = boundary
                        .expansion
                        .context("missing macro expansion proof")?;
                    ensure!(
                        previous.fingerprint == expansion.fingerprint,
                        "macro expansion changed outside the supported edit"
                    );
                    macro_validation_seconds = started.elapsed().as_secs_f64();
                    Some(expansion)
                } else {
                    None
                };
                worker.check(expansion.as_ref(), cancelled)
            })()
        } else {
            let outputs = tempfile::Builder::new()
                .prefix("worker-")
                .tempdir_in(&scratch)?;
            let mut worker_command = isolated_command(
                command,
                outputs.path(),
                CompilerMode::Retained,
                &self.source,
            )?;
            let mut worker =
                Worker::start(&mut worker_command, outputs, &environment, config.jobs)?;
            let response = worker.response("ready", 0, cancelled);
            state.worker = Some(worker);
            response
        };
        match response {
            Ok((boundary, diagnostics)) => {
                let worker_pid = state.worker.as_ref().unwrap().child.id();
                if !boundary.retained {
                    state.worker = None;
                }
                Ok(Some(Checked {
                    diagnostics,
                    errors: boundary.errors,
                    retained: boundary.retained,
                    worker_pid,
                    macro_validation_seconds,
                }))
            }
            Err(error) => {
                tracing::debug!(%error, "discarding check-session worker before fresh compilation");
                state.worker = None;
                Err(error)
            }
        }
    }
}

fn fresh_check(
    command: &ProcessBuilder,
    directory: &Path,
    source: &Path,
    stdout: &mut dyn FnMut(&str) -> CargoResult<()>,
    stderr: &mut dyn FnMut(&str) -> CargoResult<()>,
) -> CargoResult<()> {
    std::fs::create_dir_all(directory)?;
    let scratch = tempfile::Builder::new()
        .prefix("fresh-")
        .tempdir_in(directory)?;
    let fresh = isolated_command(command, scratch.path(), CompilerMode::Fresh, source)?;
    tracing::debug!("running fresh check-session fallback");
    fresh
        .exec_with_streaming(
            stdout,
            &mut |line| {
                if !is_artifact(line) {
                    stderr(line)?;
                }
                Ok(())
            },
            false,
        )
        .map(drop)
}

fn is_artifact(line: &str) -> bool {
    serde_json::from_str::<serde_json::Value>(line)
        .is_ok_and(|value| matches!(value["$message_type"].as_str(), Some("artifact")))
}

enum CompilerMode {
    Retained,
    Expansion,
    Fresh,
}

fn isolated_command(
    original: &ProcessBuilder,
    output: &Path,
    mode: CompilerMode,
    source: &Path,
) -> CargoResult<ProcessBuilder> {
    std::fs::create_dir_all(output)?;
    let mut command = original.clone();
    let original_arguments: Vec<_> = original.get_args().cloned().collect();
    let mut arguments = Vec::new();
    let mut index = 0;
    while index < original_arguments.len() {
        let argument = &original_arguments[index];
        let text = argument.to_string_lossy();
        ensure!(
            !text.starts_with("-o")
                && !text.starts_with('@')
                && !text.starts_with("--print")
                && !(text.starts_with("--emit=") && text[7..].contains('='))
                && !(argument == "--emit"
                    && original_arguments
                        .get(index + 1)
                        .is_some_and(|value| value.to_string_lossy().contains('='))),
            "check sessions do not support response files, print modes, or explicit output paths"
        );
        if argument == "--out-dir" {
            ensure!(
                index + 1 < original_arguments.len(),
                "missing compiler output directory"
            );
            arguments.extend([argument.clone(), output.as_os_str().to_owned()]);
            index += 2;
            continue;
        }
        if text.starts_with("--out-dir=") {
            let mut replacement = OsString::from("--out-dir=");
            replacement.push(output);
            arguments.push(replacement);
            index += 1;
            continue;
        }
        let paired = argument == "-C" || argument == "-Z";
        let option = if paired {
            original_arguments
                .get(index + 1)
                .context("missing compiler option")?
                .to_string_lossy()
        } else if text.starts_with("-C") || text.starts_with("-Z") {
            std::borrow::Cow::Borrowed(&text[2..])
        } else {
            std::borrow::Cow::Borrowed("")
        };
        let key = option.split('=').next().unwrap();
        let codegen = argument == "-C" || text.starts_with("-C");
        if (codegen && key == "incremental")
            || (!codegen
                && (key.starts_with("ohm-resident-") || key.starts_with("ohm-check-session")))
        {
            index += if paired { 2 } else { 1 };
            continue;
        }
        arguments.push(argument.clone());
        index += 1;
    }
    let flag = match mode {
        CompilerMode::Retained => Some("-Zohm-check-session"),
        CompilerMode::Expansion => Some("-Zohm-check-session-validate-macros"),
        CompilerMode::Fresh => None,
    };
    if let Some(flag) = flag {
        arguments.push(flag.into());
        let mut option = OsString::from("-Zohm-resident-frontend=");
        option.push(source);
        arguments.push(option);
    } else {
        let mut option = OsString::from("incremental=");
        option.push(output.join("incremental"));
        arguments.extend(["-C".into(), option]);
    }
    command.args_replace(&arguments);
    Ok(command)
}

#[derive(Deserialize)]
struct Boundary {
    protocol: u64,
    kind: String,
    revision: u64,
    errors: bool,
    retained: bool,
    #[serde(default)]
    reason: String,
    #[serde(default)]
    expansion: Option<ExpansionProof>,
}

#[derive(Clone, Deserialize, Serialize)]
struct ExpansionProof {
    fingerprint: String,
    source_hash: String,
}

struct Worker {
    child: Child,
    input: Option<ChildStdin>,
    output: mpsc::Receiver<CargoResult<String>>,
    revision: u64,
    expansion: Option<ExpansionProof>,
    // Cargo removes snapshots after reaping the child, even if it exited without destructors.
    _outputs: tempfile::TempDir,
    _jobserver: jobserver::Client,
}

impl Worker {
    fn start(
        command: &mut ProcessBuilder,
        outputs: tempfile::TempDir,
        environment: &BTreeMap<OsString, OsString>,
        jobs: u32,
    ) -> CargoResult<Self> {
        command.clear_inherited_files();
        // The requesting client reserves this many slots before sending a check. Its
        // jobserver descriptors cannot outlive that Cargo process; this private budget can.
        let jobserver = jobserver::Client::new(jobs.saturating_sub(1) as usize)?;
        let mut process = command.build_command();
        process.env_clear().envs(environment);
        jobserver.configure(&mut process);
        let mut child = process
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .spawn()?;
        let input = child.stdin.take();
        let stderr = child.stderr.take().unwrap();
        let (sender, output) = mpsc::sync_channel(1);
        std::thread::spawn(move || {
            let mut reader = BufReader::new(stderr);
            loop {
                let mut line = String::new();
                let result =
                    std::io::Read::take(&mut reader, OUTPUT_LIMIT as u64).read_line(&mut line);
                match result {
                    Ok(0) => break,
                    Ok(_) if line.ends_with('\n') => {
                        if sender.send(Ok(line)).is_err() {
                            break;
                        }
                    }
                    _ => {
                        let _ =
                            sender.send(Err(anyhow::anyhow!("invalid compiler diagnostic stream")));
                        break;
                    }
                }
            }
        });
        tracing::debug!(pid = child.id(), "started check-session worker");
        Ok(Self {
            child,
            input,
            output,
            revision: 0,
            expansion: None,
            _outputs: outputs,
            _jobserver: jobserver,
        })
    }

    fn check(
        &mut self,
        expansion: Option<&ExpansionProof>,
        cancelled: &AtomicBool,
    ) -> CargoResult<(Boundary, Vec<String>)> {
        self.revision += 1;
        let input = self.input.as_mut().context("closed worker input")?;
        serde_json::to_writer(
            &mut *input,
            &json!({"command":"check", "revision":self.revision, "expansion": expansion}),
        )?;
        input.write_all(b"\n")?;
        input.flush()?;
        self.response("checked", self.revision, cancelled)
    }

    fn finish_validation(&mut self, cancelled: &AtomicBool) -> CargoResult<()> {
        let deadline = Instant::now() + TIMEOUT;
        loop {
            ensure!(
                !cancelled.load(Ordering::Relaxed),
                "check-session client disconnected"
            );
            ensure!(Instant::now() < deadline, "macro validator did not exit");
            let status = self.child.try_wait()?;
            if let Some(status) = status {
                ensure!(status.success(), "macro validator exited unsuccessfully");
            }
            match self.output.recv_timeout(Duration::from_millis(10)) {
                Ok(_) => anyhow::bail!("macro validator emitted late diagnostics"),
                Err(mpsc::RecvTimeoutError::Disconnected) if status.is_some() => return Ok(()),
                Err(_) => {}
            }
        }
    }

    fn response(
        &mut self,
        kind: &str,
        revision: u64,
        cancelled: &AtomicBool,
    ) -> CargoResult<(Boundary, Vec<String>)> {
        let deadline = Instant::now() + TIMEOUT;
        let mut diagnostics = Vec::new();
        let mut bytes = 0;
        let mut errors = false;
        loop {
            ensure!(
                !cancelled.load(Ordering::Relaxed),
                "check-session client disconnected"
            );
            let remaining = deadline.saturating_duration_since(Instant::now());
            ensure!(
                !remaining.is_zero(),
                "compiler did not complete a session request"
            );
            let line = match self
                .output
                .recv_timeout(remaining.min(Duration::from_millis(100)))
            {
                Err(mpsc::RecvTimeoutError::Timeout) => continue,
                response => response.context("compiler exited during a session request")??,
            };
            bytes += line.len();
            ensure!(
                bytes <= OUTPUT_LIMIT,
                "compiler diagnostic response exceeded the session limit"
            );
            let value: serde_json::Value = serde_json::from_str(&line)
                .context("unexpected output from check-session compiler")?;
            if value["$message_type"] == "artifact" {
                // Dep-info is written before analysis, inside the worker's private output dir.
                continue;
            }
            if value["$message_type"] == "ohm-check-session" {
                let boundary: Boundary = serde_json::from_value(value)?;
                ensure!(
                    boundary.protocol == 1
                        && boundary.kind == kind
                        && boundary.revision == revision,
                    "compiler declined the session request: {}",
                    boundary.reason
                );
                ensure!(
                    boundary.errors == errors,
                    "compiler status did not match its diagnostics"
                );
                if kind == "ready" {
                    self.expansion = boundary.expansion.clone();
                }
                return Ok((boundary, diagnostics));
            }
            ensure!(
                value["$message_type"] == "diagnostic",
                "unsupported compiler output"
            );
            errors |= value["level"] == "error";
            diagnostics.push(line.trim_end_matches('\n').to_owned());
        }
    }
}

impl Drop for Worker {
    fn drop(&mut self) {
        // Closing the private request pipe also terminates a worker whose Cargo owner died.
        self.input.take();
        let deadline = Instant::now() + Duration::from_secs(2);
        while self.child.try_wait().ok().flatten().is_none() && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(10));
        }
        if self.child.try_wait().ok().flatten().is_none() {
            let _ = self.child.kill();
        }
        let _ = self.child.wait();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn isolate_outputs_and_session_flags() {
        let scratch = tempfile::tempdir().unwrap();
        let mut original = ProcessBuilder::new("rustc");
        original.args(&[
            "src/lib.rs",
            "--out-dir=canonical",
            "--emit=dep-info,metadata",
            "-C",
            "incremental=canonical/incremental",
            "-Copt-level=1",
            "-Zthreads=8",
            "-Zohm-check-session-trust-proc-macros",
            "-Z",
            "ohm-resident-frontend=old.rs",
        ]);
        let source = Path::new("src/edit.rs");
        let resident =
            isolated_command(&original, scratch.path(), CompilerMode::Retained, source).unwrap();
        let arguments: Vec<_> = resident
            .get_args()
            .map(|arg| arg.to_string_lossy())
            .collect();
        assert!(arguments.iter().all(|arg| !arg.contains("canonical")
            && !arg.contains("old.rs")
            && !arg.contains("trust-proc-macros")));
        assert!(arguments.contains(&std::borrow::Cow::Borrowed("-Copt-level=1")));
        assert!(arguments.contains(&std::borrow::Cow::Borrowed("-Zthreads=8")));
        let expansion =
            isolated_command(&original, scratch.path(), CompilerMode::Expansion, source).unwrap();
        let arguments: Vec<_> = expansion
            .get_args()
            .map(|arg| arg.to_string_lossy())
            .collect();
        assert!(
            arguments
                .iter()
                .any(|arg| *arg == "-Zohm-check-session-validate-macros")
        );
        assert!(
            arguments
                .iter()
                .all(|arg| !arg.contains("incremental") && *arg != "-Zohm-check-session")
        );
        let fresh =
            isolated_command(&original, scratch.path(), CompilerMode::Fresh, source).unwrap();
        assert!(
            fresh
                .get_args()
                .all(|arg| !arg.to_string_lossy().contains("ohm-check-session")
                    && !arg.to_string_lossy().contains("ohm-resident"))
        );
        assert!(original.get_args().any(|arg| arg == "--out-dir=canonical"));
    }

    #[test]
    fn reject_paths_that_escape_private_outputs() {
        let scratch = tempfile::tempdir().unwrap();
        for args in [
            vec!["-o", "outside"],
            vec!["-ooutside"],
            vec!["--emit", "metadata=outside"],
            vec!["--emit=metadata=outside"],
            vec!["@args"],
            vec!["--print=cfg"],
        ] {
            let mut command = ProcessBuilder::new("rustc");
            command.args(&args);
            assert!(
                isolated_command(
                    &command,
                    scratch.path(),
                    CompilerMode::Retained,
                    Path::new("edit.rs")
                )
                .is_err(),
                "{args:?}"
            );
        }
    }
}
