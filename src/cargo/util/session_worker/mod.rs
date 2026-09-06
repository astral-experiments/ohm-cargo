//! Opt-in execution of one metadata-only root in a persistent compiler process.

use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fs::{self, File};
use std::io::{Read, Write};
use std::os::fd::{AsRawFd, OwnedFd};
use std::os::unix::fs::MetadataExt;
use std::os::unix::net::UnixStream;
use std::os::unix::process::ExitStatusExt;
use std::path::{Path, PathBuf};
use std::process::{Child, ExitStatus, Stdio};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use anyhow::{Context as _, bail, ensure};
use cargo_util::{ProcessBuilder, ProcessError, Sha256};
use jobserver::Client;
use serde::{Deserialize, Serialize};

use crate::core::compiler::{
    BuildContext, BuildRunner, CompileMode, DefaultExecutor, Executor,
    OHM_COMPILER_LOADER_INJECTION_ENVIRONMENT,
};
use crate::core::{PackageId, Target};
use crate::util::CargoResult;
use crate::util::session_inputs::InputTracker;

#[allow(dead_code)] // The worker uses the protocol's writer half.
mod protocol;

/// Counters describe actual compiler requests, including requests with diagnostics.
#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct WorkerStats {
    pub pid: Option<u32>,
    pub starts: u64,
    pub requests: u64,
    pub fallback_reason: Option<String>,
}

#[derive(Debug, Eq, PartialEq)]
struct FileIdentity {
    path: PathBuf,
    device: u64,
    inode: u64,
    length: u64,
    modified: (i64, i64),
    changed: (i64, i64),
}

impl FileIdentity {
    fn read(path: &Path) -> CargoResult<Self> {
        let path = fs::canonicalize(path)?;
        let metadata = fs::metadata(&path)?;
        ensure!(metadata.is_file(), "{} is not a file", path.display());
        Ok(Self {
            path,
            device: metadata.dev(),
            inode: metadata.ino(),
            length: metadata.len(),
            modified: (metadata.mtime(), metadata.mtime_nsec()),
            changed: (metadata.ctime(), metadata.ctime_nsec()),
        })
    }
}

#[derive(Eq, PartialEq)]
struct Invocation {
    compiler: FileIdentity,
    worker: FileIdentity,
    args: Vec<OsString>,
    cwd: PathBuf,
    environment: BTreeMap<OsString, OsString>,
}

impl Invocation {
    #[expect(
        clippy::disallowed_methods,
        reason = "the key includes every environment value inherited by the compiler"
    )]
    fn new(cmd: &ProcessBuilder, worker: &Path) -> CargoResult<Self> {
        let command = cmd.build_command();
        let mut environment: BTreeMap<_, _> = std::env::vars_os().collect();
        for (key, value) in command.get_envs() {
            match value {
                Some(value) => {
                    environment.insert(key.to_owned(), value.to_owned());
                }
                None => {
                    environment.remove(key);
                }
            }
        }
        let cwd = match command.get_current_dir() {
            Some(path) => fs::canonicalize(path)?,
            None => std::env::current_dir()?.canonicalize()?,
        };
        Ok(Self {
            compiler: FileIdentity::read(Path::new(cmd.get_program()))?,
            worker: FileIdentity::read(worker)?,
            args: cmd.get_args().cloned().collect(),
            cwd,
            environment,
        })
    }
}

struct Selection {
    package: PackageId,
    target: Target,
    mode: CompileMode,
    compiler: PathBuf,
    identity: protocol::Identity,
}

#[derive(Default)]
struct State {
    worker: Option<Worker>,
    stats: WorkerStats,
}

impl State {
    fn retire(&mut self) {
        self.worker = None;
        self.stats.pid = None;
    }
}

/// This service owns only execution resources. BuildRunner still owns jobs,
/// fingerprints and locks, and dropping the prepared epoch kills its one worker.
pub struct WorkerExecutor {
    path: PathBuf,
    selection: Option<Selection>,
    jobserver: Client,
    state: Mutex<State>,
}

impl WorkerExecutor {
    pub fn new(
        bcx: &BuildContext<'_, '_>,
        path: &Path,
        inputs: &InputTracker,
    ) -> CargoResult<Self> {
        let path = bcx.gctx.cwd().join(path);
        // Worker replacement retires the prepared epoch just like compiler replacement.
        let resolved = inputs.executable(
            &path,
            bcx.gctx.cwd(),
            bcx.gctx.get_env_os("PATH").unwrap_or_default(),
        );
        let selection: CargoResult<_> = (|| {
            ensure!(
                cfg!(target_os = "linux"),
                "compiler workers currently require Linux"
            );
            ensure!(
                inputs.reuse_reason().is_none(),
                "planning inputs require fresh preparation"
            );
            ensure!(
                bcx.rustc()
                    .wrapper
                    .iter()
                    .chain(bcx.rustc().workspace_wrapper.iter())
                    .all(|wrapper| wrapper.as_os_str().is_empty()),
                "compiler workers do not support compiler wrappers"
            );
            ensure!(
                resolved.is_some(),
                "compiler worker executable could not be resolved"
            );
            ensure!(
                bcx.roots.len() == 1,
                "compiler workers require one selected root"
            );
            let root = &bcx.roots[0];
            ensure!(
                root.mode.is_check(),
                "compiler workers require a check root"
            );
            ensure!(
                bcx.target_data.short_name(&root.kind) == bcx.host_triple().as_str(),
                "compiler workers currently require the host target"
            );
            ensure!(
                !bcx.unit_graph.keys().any(|unit| unit.target.proc_macro()),
                "the unit graph contains procedural macros"
            );
            let compiler = fs::canonicalize(&bcx.rustc().path)?;
            let sysroot = fs::canonicalize(&bcx.target_data.info(root.kind).sysroot)?;
            let drivers: Vec<_> = fs::read_dir(sysroot.join("lib"))?
                .filter_map(Result::ok)
                .map(|entry| entry.path())
                .filter(|path| {
                    path.file_name()
                        .and_then(|name| name.to_str())
                        .is_some_and(|name| {
                            name.starts_with("librustc_driver-") && name.ends_with(".so")
                        })
                })
                .collect();
            ensure!(drivers.len() == 1, "compiler driver identity is ambiguous");
            let driver = fs::canonicalize(&drivers[0])?;
            let identity = protocol::Identity {
                compiler: utf8_path(&compiler)?,
                compiler_sha256: digest(&compiler)?,
                driver: utf8_path(&driver)?,
                driver_sha256: digest(&driver)?,
                sysroot: utf8_path(&sysroot)?,
                verbose_version: bcx.rustc().verbose_version.trim().to_owned(),
            };
            Ok(Selection {
                package: root.pkg.package_id(),
                target: root.target.clone(),
                mode: root.mode,
                compiler,
                identity,
            })
        })();
        let mut state = State::default();
        let selection = match selection {
            Ok(selection) => Some(selection),
            Err(error) => {
                state.stats.fallback_reason = Some(format!("{error:#}"));
                None
            }
        };
        Ok(Self {
            path,
            selection,
            jobserver: BuildRunner::create_jobserver(bcx)?,
            state: Mutex::new(state),
        })
    }

    pub fn jobserver(&self) -> &Client {
        &self.jobserver
    }

    pub fn stats(&self) -> WorkerStats {
        self.state.lock().unwrap().stats.clone()
    }

    fn run(
        &self,
        cmd: &ProcessBuilder,
        selection: &Selection,
    ) -> CargoResult<Option<protocol::Response>> {
        let mut state = self.state.lock().unwrap();
        let admission: CargoResult<_> = (|| {
            ensure!(
                !cmd.has_inherited_files(),
                "command inherits request-scoped file handles"
            );
            ensure!(cmd.get_arg0().is_none(), "command overrides argv[0]");
            let args: Vec<_> = cmd.get_args().map(|arg| arg.to_str()).collect();
            ensure!(
                args.iter().all(Option::is_some),
                "compiler arguments must be UTF-8"
            );
            let args: Vec<_> = args.into_iter().flatten().collect();
            let emits: Vec<_> = args
                .iter()
                .copied()
                .filter(|arg| arg.starts_with("--emit"))
                .collect();
            ensure!(
                !emits.is_empty()
                    && emits.iter().all(|arg| {
                        matches!(*arg, "--emit=dep-info,metadata" | "--emit=metadata")
                    }),
                "compiler workers only support metadata output"
            );
            ensure!(
                !args.iter().any(|arg| {
                    arg.starts_with('@')
                        || arg.starts_with("-Z")
                        || arg.starts_with("--sysroot")
                        || arg.contains("llvm-args")
                        || *arg == "-"
                        || arg.starts_with("--print")
                        || arg.starts_with("--out-dir=")
                }),
                "compiler command has unsupported options"
            );
            let invocation = Invocation::new(cmd, &self.path)?;
            ensure!(
                OHM_COMPILER_LOADER_INJECTION_ENVIRONMENT
                    .iter()
                    .all(|name| {
                        invocation
                            .environment
                            .get(std::ffi::OsStr::new(name))
                            .is_none_or(|value| value.is_empty())
                    }),
                "compiler loader injection has undeclared process state"
            );
            ensure!(
                invocation.compiler.path == selection.compiler,
                "compiler executable changed"
            );
            Ok(invocation)
        })();
        let invocation = match admission {
            Ok(invocation) => invocation,
            Err(error) => {
                state.retire();
                state.stats.fallback_reason = Some(format!("{error:#}"));
                return Ok(None);
            }
        };
        if state
            .worker
            .as_ref()
            .is_some_and(|worker| worker.invocation != invocation)
        {
            state.retire();
        }
        if let Some(worker) = &mut state.worker {
            if worker.child.try_wait()?.is_some() {
                state.retire();
            }
        }
        if state.worker.is_none() {
            match Worker::start(cmd, &self.path, invocation, &selection.identity) {
                Ok(worker) => {
                    state.stats.pid = Some(worker.child.id());
                    state.stats.starts += 1;
                    state.stats.fallback_reason = None;
                    state.worker = Some(worker);
                }
                Err(error) => {
                    // The identity handshake precedes all compiler work, so ordinary
                    // execution is safe if the worker cannot start or is incompatible.
                    state.stats.fallback_reason = Some(format!("{error:#}"));
                    return Ok(None);
                }
            }
        }
        state.stats.requests += 1;
        let response = state.worker.as_mut().unwrap().check();
        match response {
            Ok(response) => {
                if !response.reusable {
                    state.retire();
                    state.stats.fallback_reason =
                        Some("worker loaded additional native code".to_owned());
                }
                Ok(Some(response))
            }
            Err(error) => {
                state.retire();
                state.stats.fallback_reason = Some("worker failed after dispatch".to_owned());
                Err(error.context(
                    "compiler worker failed after dispatch; it was retired, retry the check",
                ))
            }
        }
    }
}

impl Executor for WorkerExecutor {
    fn exec(
        &self,
        cmd: &ProcessBuilder,
        id: PackageId,
        target: &Target,
        mode: CompileMode,
        on_stdout_line: &mut dyn FnMut(&str) -> CargoResult<()>,
        on_stderr_line: &mut dyn FnMut(&str) -> CargoResult<()>,
    ) -> CargoResult<()> {
        let response = match &self.selection {
            Some(selection)
                if selection.package == id
                    && selection.target == *target
                    && selection.mode == mode =>
            {
                self.run(cmd, selection)?
            }
            _ => None,
        };
        let Some(response) = response else {
            return DefaultExecutor.exec(cmd, id, target, mode, on_stdout_line, on_stderr_line);
        };
        // Cargo's normal JSON/diagnostic callbacks remain authoritative. The
        // complete framed response is drained before a callback can fail.
        let status = ExitStatus::from_raw(i32::from(response.code) << 8);
        let emit = |bytes: &[u8], callback: &mut dyn FnMut(&str) -> CargoResult<()>| {
            for line in String::from_utf8_lossy(bytes).lines() {
                callback(line).map_err(|error| {
                    anyhow::Error::new(ProcessError::new(
                        &format!("failed to parse process output: {cmd}"),
                        Some(status),
                        None,
                    ))
                    .context(error)
                })?;
            }
            Ok::<_, anyhow::Error>(())
        };
        emit(&response.stdout, on_stdout_line)?;
        emit(&response.stderr, on_stderr_line)?;
        if !status.success() {
            bail!(ProcessError::new(
                &format!("process didn't exit successfully: {cmd}"),
                Some(status),
                None,
            ));
        }
        Ok(())
    }
}

struct Worker {
    child: Child,
    control: UnixStream,
    invocation: Invocation,
}

impl Worker {
    fn start(
        original: &ProcessBuilder,
        path: &Path,
        invocation: Invocation,
        expected: &protocol::Identity,
    ) -> CargoResult<Self> {
        let (control, endpoint) = UnixStream::pair()?;
        control.set_read_timeout(Some(Duration::from_secs(30)))?;
        let endpoint: OwnedFd = endpoint.into();
        let endpoint = Arc::new(File::from(endpoint));
        let mut args = vec![
            OsString::from(format!("--cargo-session-fd={}", endpoint.as_raw_fd())),
            OsString::from("--"),
        ];
        args.extend(original.get_args().cloned());
        let mut command = original.clone();
        command
            .program(path)
            .args_replace(&args)
            .inherit_file(endpoint);
        let child = command
            .build_command()
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()?;
        drop(command);
        let mut worker = Self {
            child,
            control,
            invocation,
        };
        let actual = protocol::read_identity(&mut worker.control)
            .context("compiler worker did not provide a valid identity")?;
        ensure!(
            &actual == expected,
            "compiler worker does not match the selected compiler installation"
        );
        worker.control.set_read_timeout(None)?;
        Ok(worker)
    }

    fn check(&mut self) -> CargoResult<protocol::Response> {
        self.control.write_all(&[protocol::CHECK])?;
        Ok(protocol::read_response(&mut self.control)?)
    }
}

impl Drop for Worker {
    fn drop(&mut self) {
        if self.child.try_wait().ok().flatten().is_none() {
            let _ = self.child.kill();
        }
        let _ = self.child.wait();
    }
}

fn utf8_path(path: &Path) -> CargoResult<String> {
    path.to_str()
        .map(str::to_owned)
        .context("compiler worker paths must be UTF-8")
}

fn digest(path: &Path) -> CargoResult<String> {
    let mut file = File::open(path)?;
    let mut hash = Sha256::new();
    let mut bytes = [0; 64 * 1024];
    loop {
        let count = file.read(&mut bytes)?;
        if count == 0 {
            break;
        }
        hash.update(&bytes[..count]);
    }
    Ok(hash.finish_hex())
}
