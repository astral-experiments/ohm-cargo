//! Local transport for a workspace's explicitly started compiler owner.
//!
//! Each Cargo client owns its build graph, dependencies, diagnostics, and locks. The host
//! executes only terminal library checks, one at a time, and never caches Cargo's graph.

use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, mpsc};
use std::time::{Duration, SystemTime};

use anyhow::{Context, bail, ensure};
use cargo_util::ProcessBuilder;
use serde::{Deserialize, Serialize, de::DeserializeOwned};

use super::{Checked, CompilerConfiguration, CompilerSession, OUTPUT_LIMIT, TIMEOUT, fresh_check};
use crate::compiler::{BuildRunner, CompileMode, DefaultExecutor, Executor, Unit};
use crate::util::{CargoResult, flock, short_hash};
use crate::workspace::{PackageId, Target};

const PROTOCOL: u32 = 1;
const REQUEST_LIMIT: usize = 16 * 1024 * 1024;
const POLL: Duration = Duration::from_millis(20);
static STOPPING: AtomicBool = AtomicBool::new(false);

#[derive(Clone, Serialize, Deserialize)]
pub struct Info {
    protocol: u32,
    workspace: PathBuf,
    executable: String,
    generation: String,
    source: PathBuf,
    trust_proc_macros: bool,
    /// PID of the workspace host, which owns the compiler until `cargo stop`.
    pub pid: u32,
}

#[derive(Serialize, Deserialize)]
struct Bootstrap {
    workspace: PathBuf,
    source: PathBuf,
    trust_proc_macros: bool,
}

#[derive(Serialize, Deserialize)]
enum Request {
    Info,
    Invalidate {
        generation: String,
    },
    Stop {
        generation: String,
    },
    Check {
        generation: String,
        config: CompilerConfiguration,
        process: Process,
    },
}

#[derive(Serialize, Deserialize)]
enum Response {
    Info(Info),
    Checked(Option<Checked>),
    Stopped,
    Invalidated,
    Busy,
    Error(String),
}

#[derive(Serialize, Deserialize)]
struct Process {
    program: OsString,
    arguments: Vec<OsString>,
    arg0: Option<OsString>,
    cwd: PathBuf,
    // A sequence permits non-UTF-8 environment names and values in JSON.
    environment: Vec<(OsString, OsString)>,
}

impl Process {
    fn capture(
        command: &ProcessBuilder,
        inherited: &BTreeMap<OsString, OsString>,
    ) -> CargoResult<Self> {
        let mut environment = inherited.clone();
        for (key, value) in command.get_envs() {
            if let Some(value) = value {
                environment.insert(key.into(), value.clone());
            } else {
                environment.remove(&OsString::from(key));
            }
        }
        Ok(Self {
            program: command.get_program().clone(),
            arguments: command.get_args().cloned().collect(),
            arg0: command.get_arg0().map(ToOwned::to_owned),
            cwd: command
                .get_cwd()
                .map(ToOwned::to_owned)
                .unwrap_or(std::env::current_dir()?),
            environment: environment.into_iter().collect(),
        })
    }

    fn command(&self) -> ProcessBuilder {
        let mut command = ProcessBuilder::new(&self.program);
        command.args(&self.arguments).cwd(&self.cwd);
        if let Some(arg0) = &self.arg0 {
            command.arg0(arg0);
        }
        command
    }
}

struct Endpoint {
    workspace: PathBuf,
    directory: PathBuf,
    socket: PathBuf,
    lock: PathBuf,
}

impl Endpoint {
    fn new(workspace: &Path) -> CargoResult<Self> {
        let workspace = fs::canonicalize(workspace)?;
        // Keep socket paths below macOS's 104-byte limit, independently of workspace,
        // CARGO_HOME, and TMPDIR lengths. Never trust a directory owned by another uid.
        let uid = unsafe { libc::geteuid() };
        let directory = PathBuf::from(format!("/tmp/ohm-check-sessions-{uid}"));
        if directory.try_exists()? {
            let metadata = fs::symlink_metadata(&directory)?;
            ensure!(
                metadata.is_dir() && metadata.uid() == uid && metadata.mode() & 0o777 == 0o700,
                "unsafe workspace session directory: {}",
                directory.display()
            );
        }
        let key = short_hash(&workspace);
        Ok(Self {
            workspace,
            socket: directory.join(format!("{key}.sock")),
            lock: directory.join(format!("{key}.lock")),
            directory,
        })
    }

    fn request(&self, request: &Request) -> CargoResult<Response> {
        let mut socket = UnixStream::connect(&self.socket)?;
        socket.set_read_timeout(Some(TIMEOUT + Duration::from_secs(10)))?;
        socket.set_write_timeout(Some(Duration::from_secs(10)))?;
        write_packet(&mut socket, request, REQUEST_LIMIT)?;
        let response = read_packet(&mut socket, OUTPUT_LIMIT)?;
        match response {
            Response::Error(message) => bail!("workspace session: {message}"),
            response => Ok(response),
        }
    }

    fn info(&self) -> CargoResult<Info> {
        let Response::Info(info) = self.request(&Request::Info)? else {
            bail!("unexpected workspace session response");
        };
        ensure!(
            info.protocol == PROTOCOL && info.workspace == self.workspace,
            "incompatible workspace session"
        );
        Ok(info)
    }
}

fn executable_identity() -> CargoResult<String> {
    let path = std::env::current_exe()?;
    let metadata = fs::metadata(&path)?;
    Ok(short_hash(&(
        path,
        metadata.dev(),
        metadata.ino(),
        metadata.len(),
        metadata.modified()?,
    )))
}

fn write_packet(output: &mut impl Write, value: &impl Serialize, limit: usize) -> CargoResult<()> {
    let bytes = serde_json::to_vec(value)?;
    ensure!(
        bytes.len() <= limit,
        "workspace session message exceeded its size limit"
    );
    output.write_all(&(bytes.len() as u32).to_le_bytes())?;
    output.write_all(&bytes)?;
    output.flush()?;
    Ok(())
}

fn read_packet<T: DeserializeOwned>(input: &mut impl Read, limit: usize) -> CargoResult<T> {
    let mut length = [0; 4];
    input.read_exact(&mut length)?;
    let length = u32::from_le_bytes(length) as usize;
    ensure!(
        length <= limit,
        "workspace session message exceeded its size limit"
    );
    let mut bytes = vec![0; length];
    input.read_exact(&mut bytes)?;
    Ok(serde_json::from_slice(&bytes)?)
}

/// Start an independent host, or attach to an identical explicitly started session.
pub fn start(workspace: &Path, source: &Path, trust_proc_macros: bool) -> CargoResult<Info> {
    let endpoint = Endpoint::new(workspace)?;
    let source = fs::canonicalize(source).context("cannot read the selected session source")?;
    ensure!(
        source.is_file() && source.starts_with(&endpoint.workspace),
        "session source must be a file in this workspace"
    );
    let validate = |info: Info| -> CargoResult<Info> {
        ensure!(
            info.executable == executable_identity()?
                && info.source == source
                && info.trust_proc_macros == trust_proc_macros,
            "a different workspace session is already running; use `cargo stop` first"
        );
        Ok(info)
    };
    if let Ok(info) = endpoint.info() {
        return validate(info);
    }
    let mut command = Command::new(std::env::current_exe()?);
    command
        .arg("__ohm-check-session-host")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    // The host is explicitly managed by start/stop, independently of its launching terminal.
    unsafe {
        command.pre_exec(|| {
            if libc::setsid() == -1 {
                return Err(std::io::Error::last_os_error());
            }
            libc::umask(0o077);
            Ok(())
        });
    }
    let mut child = command.spawn()?;
    let result = (|| {
        write_packet(
            &mut child.stdin.take().unwrap(),
            &Bootstrap {
                workspace: endpoint.workspace.clone(),
                source: source.clone(),
                trust_proc_macros,
            },
            REQUEST_LIMIT,
        )?;
        let mut output = child.stdout.take().unwrap();
        let (send, receive) = mpsc::channel();
        std::thread::spawn(move || {
            let _ = send.send(read_packet(&mut output, REQUEST_LIMIT));
        });
        match receive
            .recv_timeout(Duration::from_secs(10))
            .context("workspace session did not start")??
        {
            Response::Info(info) => validate(info),
            Response::Busy => {
                // A concurrent start won the persistent lock. It has not necessarily bound
                // its socket yet. Never unlink a socket while another host owns that lock.
                for _ in 0..100 {
                    if let Ok(info) = endpoint.info() {
                        return validate(info);
                    }
                    std::thread::sleep(POLL);
                }
                bail!("another workspace session is starting; retry `cargo start`")
            }
            Response::Error(message) => bail!("cannot start workspace session: {message}"),
            _ => bail!("unexpected workspace session startup response"),
        }
    })();
    if result.is_err() {
        let _ = child.kill();
        let _ = child.wait();
    } else if child.try_wait()?.is_some() {
        let _ = child.wait();
    }
    result
}

/// Stop this workspace's host and wait until its compiler and private outputs are gone.
pub fn stop(workspace: &Path) -> CargoResult<bool> {
    let endpoint = Endpoint::new(workspace)?;
    let info = match endpoint.info() {
        Ok(info) => info,
        Err(_) if !endpoint.socket.try_exists()? => return Ok(false),
        Err(error) => {
            // A stale socket is harmless, and the next start removes it under the lock.
            if let Ok(file) = OpenOptions::new()
                .read(true)
                .write(true)
                .open(&endpoint.lock)
                && flock::try_lock_exclusive(&file).is_ok()
            {
                fs::remove_file(&endpoint.socket)?;
                return Ok(false);
            }
            return Err(error);
        }
    };
    ensure!(
        matches!(
            endpoint.request(&Request::Stop {
                generation: info.generation
            })?,
            Response::Stopped
        ),
        "unexpected workspace session shutdown response"
    );
    Ok(true)
}

struct SocketGuard(PathBuf);
impl Drop for SocketGuard {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
    }
}

extern "C" fn stop_signal(_: libc::c_int) {
    STOPPING.store(true, Ordering::Relaxed);
}

/// Internal entry point for the detached Cargo child; called before initializing Cargo.
pub fn host() -> CargoResult<()> {
    let result = run_host();
    if let Err(error) = &result {
        let _ = write_packet(
            &mut std::io::stdout(),
            &Response::Error(format!("{error:#}")),
            REQUEST_LIMIT,
        );
    }
    result
}

fn run_host() -> CargoResult<()> {
    let bootstrap: Bootstrap = read_packet(&mut std::io::stdin(), REQUEST_LIMIT)?;
    let endpoint = Endpoint::new(&bootstrap.workspace)?;
    match fs::DirBuilder::new()
        .mode(0o700)
        .create(&endpoint.directory)
    {
        Ok(()) => {}
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
        Err(error) => return Err(error.into()),
    }
    // Recheck permissions after a concurrent creation.
    let endpoint = Endpoint::new(&bootstrap.workspace)?;
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(&endpoint.lock)?;
    match flock::try_lock_exclusive(&lock) {
        Ok(()) => {}
        Err(std::fs::TryLockError::WouldBlock) => {
            return write_packet(&mut std::io::stdout(), &Response::Busy, REQUEST_LIMIT);
        }
        Err(error) => return Err(error.into()),
    }
    match fs::remove_file(&endpoint.socket) {
        Ok(()) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => return Err(error.into()),
    }
    let listener = UnixListener::bind(&endpoint.socket)?;
    let _socket = SocketGuard(endpoint.socket.clone());
    listener.set_nonblocking(true)?;
    for signal in [libc::SIGINT, libc::SIGTERM, libc::SIGHUP] {
        // This dedicated process has no prior handlers. The handler only sets an atomic;
        // the main loop performs all cleanup outside signal context.
        unsafe {
            libc::signal(signal, stop_signal as *const () as libc::sighandler_t);
        }
    }
    let info = Info {
        protocol: PROTOCOL,
        workspace: endpoint.workspace,
        executable: executable_identity()?,
        generation: format!("{}-{:?}", std::process::id(), SystemTime::now()),
        source: bootstrap.source,
        trust_proc_macros: bootstrap.trust_proc_macros,
        pid: std::process::id(),
    };
    let session = CompilerSession::new(info.source.clone());
    write_packet(
        &mut std::io::stdout(),
        &Response::Info(info.clone()),
        REQUEST_LIMIT,
    )?;
    loop {
        if STOPPING.load(Ordering::Relaxed) {
            break;
        }
        let (mut socket, _) = match listener.accept() {
            Ok(connection) => connection,
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(POLL);
                continue;
            }
            Err(error) => return Err(error.into()),
        };
        // Use blocking, bounded framed I/O on accepted streams on every platform.
        socket.set_nonblocking(false)?;
        socket.set_read_timeout(Some(Duration::from_secs(10)))?;
        socket.set_write_timeout(Some(Duration::from_secs(10)))?;
        let request = match read_packet(&mut socket, REQUEST_LIMIT) {
            Ok(request) => request,
            Err(error) => {
                let _ = write_packet(
                    &mut socket,
                    &Response::Error(format!("invalid request: {error:#}")),
                    REQUEST_LIMIT,
                );
                continue;
            }
        };
        let response = match request {
            Request::Info => Response::Info(info.clone()),
            Request::Invalidate { generation } if generation == info.generation => {
                session.state.lock().unwrap().worker = None;
                Response::Invalidated
            }
            Request::Stop { generation } if generation == info.generation => {
                drop(session);
                drop(_socket);
                write_packet(&mut socket, &Response::Stopped, REQUEST_LIMIT)?;
                return Ok(());
            }
            Request::Check {
                generation,
                config,
                process,
            } if generation == info.generation => {
                let cancelled = Arc::new(AtomicBool::new(false));
                let finished = Arc::new(AtomicBool::new(false));
                let mut disconnect = socket.try_clone()?;
                disconnect.set_read_timeout(Some(POLL))?;
                let monitor = {
                    let cancelled = cancelled.clone();
                    let finished = finished.clone();
                    std::thread::spawn(move || {
                        while !finished.load(Ordering::Relaxed) {
                            if STOPPING.load(Ordering::Relaxed) {
                                break;
                            }
                            match disconnect.read(&mut [0]) {
                                Err(error)
                                    if matches!(
                                        error.kind(),
                                        std::io::ErrorKind::WouldBlock
                                            | std::io::ErrorKind::TimedOut
                                            | std::io::ErrorKind::Interrupted
                                    ) => {}
                                _ => break,
                            }
                        }
                        if !finished.load(Ordering::Relaxed) {
                            cancelled.store(true, Ordering::Relaxed);
                        }
                    })
                };
                let result = session.check(
                    &config,
                    &process.command(),
                    process.environment.into_iter().collect(),
                    &cancelled,
                );
                finished.store(true, Ordering::Relaxed);
                let _ = monitor.join();
                match result {
                    Ok(checked) => Response::Checked(checked),
                    Err(error) => Response::Error(format!("{error:#}")),
                }
            }
            _ => Response::Error("workspace session was replaced; retry the check".into()),
        };
        if write_packet(&mut socket, &response, OUTPUT_LIMIT).is_err() {
            // No client received this diagnostic boundary. Retire the worker rather than
            // letting a cancelled request silently advance a subsequent client's state.
            session.state.lock().unwrap().worker = None;
        }
    }
    Ok(())
}

#[derive(Clone)]
struct Root {
    package: PackageId,
    target: Target,
    retain: bool,
    config: CompilerConfiguration,
    environment: BTreeMap<OsString, OsString>,
    jobserver: jobserver::Client,
}

/// A per-invocation executor that forwards only a supported terminal root to the host.
pub struct Client {
    endpoint: Endpoint,
    info: Info,
    root: Mutex<Option<Root>>,
    dependencies_changed: AtomicBool,
}

impl Client {
    /// Discover an explicit session. Missing, dead, or incompatible hosts use ordinary Cargo.
    pub fn connect(workspace: &Path) -> CargoResult<Option<Self>> {
        let endpoint = Endpoint::new(workspace)?;
        let info = match endpoint.info() {
            Ok(info) if info.executable == executable_identity()? => info,
            _ => return Ok(None),
        };
        Ok(Some(Self {
            endpoint,
            info,
            root: Mutex::new(None),
            dependencies_changed: AtomicBool::new(false),
        }))
    }
}

impl Executor for Client {
    fn is_check_session(&self, roots: &[Unit]) -> bool {
        roots.len() == 1
            && roots[0].is_local()
            && roots[0].target.is_lib()
            && !roots[0].target.for_host()
            && roots[0].mode == (CompileMode::Check { test: false })
            && fs::canonicalize(roots[0].pkg.root())
                .is_ok_and(|root| self.info.source.starts_with(root))
    }

    fn init(&self, runner: &BuildRunner<'_, '_>, unit: &Unit) {
        if !self.is_check_session(&runner.bcx.roots) || !runner.bcx.roots.contains(unit) {
            return;
        }
        let compiler = runner.bcx.rustc();
        let compiler_fingerprint = compiler.check_session_fingerprint();
        tracing::debug!(fingerprint = ?compiler_fingerprint, wrapped = compiler.wrapper.is_some(), workspace_wrapped = compiler.workspace_wrapper.is_some(), external_jobserver = runner.bcx.gctx.jobserver_from_env().is_some(), "preparing workspace session root");
        *self.root.lock().unwrap() = Some(Root {
            package: unit.pkg.package_id(),
            target: unit.target.clone(),
            jobserver: runner.jobserver.clone(),
            environment: runner
                .bcx
                .gctx
                .env_os()
                .map(|(k, v)| (k.to_owned(), v.to_owned()))
                .collect(),
            retain: compiler_fingerprint.is_some()
                && compiler.wrapper.is_none()
                && compiler.workspace_wrapper.is_none()
                && runner.bcx.gctx.jobserver_from_env().is_none()
                && (self.info.trust_proc_macros
                    || !runner
                        .bcx
                        .unit_graph
                        .keys()
                        .any(|unit| unit.target.proc_macro())),
            config: CompilerConfiguration {
                compiler: compiler.verbose_version.clone(),
                compiler_fingerprint,
                trust_proc_macros: self.info.trust_proc_macros,
                directory: runner
                    .bcx
                    .ws
                    .target_dir()
                    .as_path_unlocked()
                    .join(".ohm-check-sessions"),
                jobs: runner.bcx.build_config.jobs,
            },
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
        let root = self.root.lock().unwrap().clone();
        if root
            .as_ref()
            .is_some_and(|root| root.package != package || root.target != *target)
            && !self.dependencies_changed.swap(true, Ordering::Relaxed)
        {
            // A rebuilt dependency invalidates the private snapshot before the root runs.
            // The compiler also validates files, including changes made outside Cargo.
            let _ = self.endpoint.request(&Request::Invalidate {
                generation: self.info.generation.clone(),
            });
        }
        let Some(root) = root.filter(|root| {
            root.package == package
                && root.target == *target
                && mode == (CompileMode::Check { test: false })
        }) else {
            return DefaultExecutor.exec(command, package, target, mode, stdout, stderr);
        };
        if root.retain {
            // The host cannot retain descriptors from a short-lived Cargo client. Reserve
            // this client's remaining tokens while the host uses an equivalent private
            // budget. Early-metadata dependency jobs can finish before granting the tokens.
            // Cargo already accounts for the root's one implicit token. External jobservers
            // use fresh checks, so this reservation cannot starve another build tool.
            let _tokens = (1..root.config.jobs)
                .map(|_| root.jobserver.acquire())
                .collect::<std::io::Result<Vec<_>>>()?;
            let response = self.endpoint.request(&Request::Check {
                generation: self.info.generation.clone(),
                config: root.config.clone(),
                process: Process::capture(command, &root.environment)?,
            });
            match response {
                Ok(Response::Checked(Some(checked))) => {
                    tracing::debug!(
                        pid = checked.worker_pid,
                        retained = checked.retained,
                        "completed workspace session check"
                    );
                    for line in checked.diagnostics {
                        stderr(&line)?;
                    }
                    ensure!(!checked.errors, "compiler reported errors");
                    return Ok(());
                }
                Err(error) => tracing::debug!(%error, "workspace session requires a fresh check"),
                other => {
                    tracing::debug!(
                        failed = other.is_err(),
                        "workspace session requires a fresh check"
                    );
                }
            }
        }
        fresh_check(
            command,
            &root.config.directory,
            &self.info.source,
            stdout,
            stderr,
        )
    }
}
