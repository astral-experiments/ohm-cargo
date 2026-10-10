//! Own a single private compiler and validate each request through Cargo's build graph.

use std::collections::BTreeMap;
use std::ffi::OsString;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Stdio};
use std::sync::{Mutex, mpsc};
use std::time::{Duration, Instant};

use anyhow::{Context, bail, ensure};
use cargo_util::ProcessBuilder;
use serde::Deserialize;
use serde_json::json;

use crate::compiler::{BuildRunner, CompileMode, DefaultExecutor, Executor, Unit};
use crate::util::CargoResult;
use crate::workspace::{PackageId, Target};

const TIMEOUT: Duration = Duration::from_secs(300);
const OUTPUT_LIMIT: usize = 64 * 1024 * 1024;

#[derive(Clone)]
struct Root {
    package: PackageId,
    target: Target,
    compiler: String,
    compiler_fingerprint: Option<u64>,
    retain: bool,
    trust_proc_macros: bool,
    directory: PathBuf,
}

#[derive(PartialEq, Eq)]
struct Invocation {
    program: OsString,
    arguments: Vec<OsString>,
    environment: BTreeMap<String, Option<OsString>>,
    cwd: Option<PathBuf>,
    compiler: String,
    compiler_fingerprint: Option<u64>,
    trust_proc_macros: bool,
}

#[derive(Default)]
struct State {
    worker: Option<Worker>,
    invocation: Option<Invocation>,
    scratch: Option<tempfile::TempDir>,
    generations: u64,
}

/// A session owns the compiler process; no worker is shared with another Cargo invocation.
pub struct CheckSession {
    source: PathBuf,
    root: Mutex<Option<Root>>,
    state: Mutex<State>,
}

impl CheckSession {
    /// Select the source whose restricted edits may reuse frontend state.
    pub fn new(source: PathBuf) -> Self {
        Self {
            source,
            root: Mutex::new(None),
            state: Mutex::new(State::default()),
        }
    }

    /// Discard retained state after a failed dependency or request setup.
    pub fn invalidate(&self) {
        self.state.lock().unwrap().worker = None;
    }

    /// Whether the next compatible request can reuse a live compiler.
    pub fn is_warm(&self) -> bool {
        self.state.lock().unwrap().worker.is_some()
    }
}

impl Executor for CheckSession {
    fn is_check_session(&self) -> bool {
        true
    }

    fn init(&self, runner: &BuildRunner<'_, '_>, unit: &Unit) {
        if !runner.bcx.roots.contains(unit) {
            return;
        }
        let compiler = runner.bcx.rustc();
        // Proc macros may read inputs that neither Cargo nor rustc can enumerate.
        let trust_proc_macros = runner
            .bcx
            .gctx
            .cli_unstable()
            .ohm_check_session_trust_proc_macros;
        let compiler_fingerprint = compiler.check_session_fingerprint();
        let retain = compiler_fingerprint.is_some()
            && compiler.wrapper.is_none()
            && compiler.workspace_wrapper.is_none()
            && (trust_proc_macros
                || !runner
                    .bcx
                    .unit_graph
                    .keys()
                    .any(|unit| unit.target.proc_macro()));
        *self.root.lock().unwrap() = Some(Root {
            package: unit.pkg.package_id(),
            target: unit.target.clone(),
            compiler: compiler.verbose_version.clone(),
            compiler_fingerprint,
            retain,
            trust_proc_macros,
            directory: runner
                .bcx
                .ws
                .target_dir()
                .as_path_unlocked()
                .join(".ohm-check-sessions"),
        });
    }

    fn exec(
        &self,
        command: &ProcessBuilder,
        package: PackageId,
        target: &Target,
        mode: CompileMode,
        stdout: &mut dyn FnMut(&str) -> CargoResult<()>,
        stderr: &mut dyn FnMut(&str) -> CargoResult<()>,
    ) -> CargoResult<()> {
        let root = self
            .root
            .lock()
            .unwrap()
            .clone()
            .context("missing check-session root")?;
        if package != root.package
            || *target != root.target
            || mode != (CompileMode::Check { test: false })
        {
            self.invalidate();
            return DefaultExecutor.exec(command, package, target, mode, stdout, stderr);
        }

        let invocation = Invocation {
            program: command.get_program().clone(),
            arguments: command.get_args().cloned().collect(),
            environment: command.get_envs().clone(),
            cwd: command.get_cwd().map(Path::to_path_buf),
            compiler: root.compiler,
            compiler_fingerprint: root.compiler_fingerprint,
            trust_proc_macros: root.trust_proc_macros,
        };
        let mut state = self.state.lock().unwrap();
        if state.invocation.as_ref() != Some(&invocation) || !root.retain {
            state.worker = None;
        }
        if state.scratch.is_none() {
            std::fs::create_dir_all(&root.directory)?;
            state.scratch = Some(
                tempfile::Builder::new()
                    .prefix("session-")
                    .tempdir_in(&root.directory)?,
            );
        }
        let scratch = state.scratch.as_ref().unwrap().path().to_owned();
        state.invocation = Some(invocation);

        if root.retain {
            let reused = state.worker.is_some();
            let response = if let Some(worker) = &mut state.worker {
                worker.check()
            } else {
                let outputs = tempfile::Builder::new()
                    .prefix("worker-")
                    .tempdir_in(&scratch)?;
                let mut worker_command =
                    isolated_command(command, outputs.path(), true, &self.source)?;
                if root.trust_proc_macros {
                    worker_command.arg("-Zohm-check-session-trust-proc-macros");
                }
                match Worker::start(&mut worker_command, outputs) {
                    Ok(mut worker) => {
                        let response = worker.response("ready", 0);
                        state.generations += 1;
                        state.worker = Some(worker);
                        response
                    }
                    Err(error) => Err(error),
                }
            };
            match response {
                Ok((boundary, diagnostics)) => {
                    tracing::debug!(
                        reused,
                        generation = state.generations,
                        revision = boundary.revision,
                        "completed resident check-session request"
                    );
                    if !boundary.retained {
                        state.worker = None;
                    }
                    for diagnostic in diagnostics {
                        stderr(&diagnostic)?;
                    }
                    if boundary.errors {
                        bail!("compiler reported errors");
                    }
                    return Ok(());
                }
                Err(error) => {
                    tracing::debug!(%error, "discarding check-session worker before fresh compilation");
                    state.worker = None;
                }
            }
        }

        let fresh = isolated_command(command, &scratch.join("fresh"), false, &self.source)?;
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
}

fn is_artifact(line: &str) -> bool {
    serde_json::from_str::<serde_json::Value>(line)
        .is_ok_and(|value| matches!(value["$message_type"].as_str(), Some("artifact")))
}

fn isolated_command(
    original: &ProcessBuilder,
    output: &Path,
    resident: bool,
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
    if resident {
        arguments.push("-Zohm-check-session".into());
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
}

struct Worker {
    child: Child,
    input: Option<ChildStdin>,
    output: mpsc::Receiver<CargoResult<String>>,
    revision: u64,
    // Cargo removes snapshots after reaping the child, even if it exited without destructors.
    _outputs: tempfile::TempDir,
}

impl Worker {
    fn start(command: &mut ProcessBuilder, outputs: tempfile::TempDir) -> CargoResult<Self> {
        command.clear_inherited_files();
        let mut child = command
            .build_command()
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
            _outputs: outputs,
        })
    }

    fn check(&mut self) -> CargoResult<(Boundary, Vec<String>)> {
        self.revision += 1;
        let input = self.input.as_mut().context("closed worker input")?;
        serde_json::to_writer(
            &mut *input,
            &json!({"command":"check", "revision":self.revision}),
        )?;
        input.write_all(b"\n")?;
        input.flush()?;
        self.response("checked", self.revision)
    }

    fn response(&mut self, kind: &str, revision: u64) -> CargoResult<(Boundary, Vec<String>)> {
        let deadline = Instant::now() + TIMEOUT;
        let mut diagnostics = Vec::new();
        let mut bytes = 0;
        let mut errors = false;
        loop {
            let line = self
                .output
                .recv_timeout(deadline.saturating_duration_since(Instant::now()))
                .context("compiler did not complete a session request")??;
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
        let resident = isolated_command(&original, scratch.path(), true, source).unwrap();
        let arguments: Vec<_> = resident
            .get_args()
            .map(|arg| arg.to_string_lossy())
            .collect();
        assert!(arguments.iter().all(|arg| !arg.contains("canonical")
            && !arg.contains("old.rs")
            && !arg.contains("trust-proc-macros")));
        assert!(arguments.contains(&std::borrow::Cow::Borrowed("-Copt-level=1")));
        assert!(arguments.contains(&std::borrow::Cow::Borrowed("-Zthreads=8")));
        let fresh = isolated_command(&original, scratch.path(), false, source).unwrap();
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
                isolated_command(&command, scratch.path(), true, Path::new("edit.rs")).is_err(),
                "{args:?}"
            );
        }
    }
}
