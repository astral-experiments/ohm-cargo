//! Unix socket ownership and process shutdown, independent of check planning.

use crate::command_prelude::*;
use anyhow::{Context as _, ensure};
use cargo::CargoResult;
use cargo_util::Sha256;
use std::fs;
use std::io::{self, Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{DirBuilderExt, FileTypeExt, MetadataExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicI32, Ordering};
use std::time::{Duration, Instant};

const FRAME_TIMEOUT: Duration = Duration::from_secs(30);

const STOP_SIGNALS: [i32; 2] = [libc::SIGINT, libc::SIGTERM];
static STOP_REQUESTED: AtomicBool = AtomicBool::new(false);
static WAKE_FD: AtomicI32 = AtomicI32::new(-1);

extern "C" fn request_stop(_signal: i32) {
    STOP_REQUESTED.store(true, Ordering::Release);
    let fd = WAKE_FD.load(Ordering::Relaxed);
    if fd >= 0 {
        // SAFETY: this nonblocking descriptor stays open while our handlers
        // are installed. write is async-signal-safe and allocates no memory.
        // A full wakeup buffer is already readable, so failure is harmless.
        unsafe { libc::write(fd, b"x".as_ptr().cast(), 1) };
    }
}

struct StopSignals {
    wake: (UnixStream, UnixStream),
    original: [libc::sigaction; 2],
    installed: usize,
}

impl StopSignals {
    fn install() -> io::Result<Self> {
        let wake = UnixStream::pair()?;
        for endpoint in [&wake.0, &wake.1] {
            endpoint.set_nonblocking(true)?;
            // SAFETY: the endpoint owns a live descriptor. Do not expose
            // this process-local wakeup channel to compiler children.
            if unsafe { libc::fcntl(endpoint.as_raw_fd(), libc::F_SETFD, libc::FD_CLOEXEC) } < 0 {
                return Err(io::Error::last_os_error());
            }
        }
        // SAFETY: zeroed sigaction storage is initialized by sigaction;
        // the new action's mask is initialized explicitly below.
        let mut guard = Self {
            wake,
            original: unsafe { std::mem::zeroed() },
            installed: 0,
        };
        let mut action: libc::sigaction = unsafe { std::mem::zeroed() };
        action.sa_sigaction = request_stop as *const () as usize;
        unsafe { libc::sigemptyset(&mut action.sa_mask) };
        STOP_REQUESTED.store(false, Ordering::Release);
        WAKE_FD.store(guard.wake.1.as_raw_fd(), Ordering::Relaxed);
        for (index, signal) in STOP_SIGNALS.into_iter().enumerate() {
            // SAFETY: action and previous-action storage are valid, and the
            // handler performs only atomics and an async-signal-safe write.
            if unsafe { libc::sigaction(signal, &action, &mut guard.original[index]) } < 0 {
                return Err(io::Error::last_os_error());
            }
            guard.installed += 1;
        }
        Ok(guard)
    }

    fn wait(&self, listener: &UnixListener) -> io::Result<bool> {
        while !STOP_REQUESTED.load(Ordering::Acquire) {
            let mut descriptors = [
                libc::pollfd {
                    fd: listener.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: self.wake.0.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
            ];
            // SAFETY: both descriptors stay open for the whole call. The
            // wakeup byte closes the flag-check/poll lost-signal window.
            if unsafe { libc::poll(descriptors.as_mut_ptr(), 2, -1) } < 0 {
                let error = io::Error::last_os_error();
                if error.kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(error);
            }
            if STOP_REQUESTED.load(Ordering::Acquire) || descriptors[1].revents != 0 {
                return Ok(false);
            }
            if descriptors[0].revents & libc::POLLIN != 0 {
                return Ok(true);
            }
            return Err(io::Error::other("Cargo session listener is unavailable"));
        }
        Ok(false)
    }
}

impl Drop for StopSignals {
    fn drop(&mut self) {
        for index in (0..self.installed).rev() {
            // SAFETY: restore the exact previous dispositions before the
            // wakeup endpoints are dropped and their descriptors can close.
            unsafe {
                libc::sigaction(
                    STOP_SIGNALS[index],
                    &self.original[index],
                    std::ptr::null_mut(),
                )
            };
        }
        WAKE_FD.store(-1, Ordering::Relaxed);
    }
}

pub(super) struct SessionListener {
    // Field order removes our socket before restoring default dispositions.
    _socket: SocketGuard,
    listener: UnixListener,
    signals: StopSignals,
}

pub(super) fn socket_path(gctx: &GlobalContext, args: &ArgMatches) -> CargoResult<PathBuf> {
    socket_path_for(
        gctx.cwd(),
        args.get_one::<PathBuf>("socket").map(PathBuf::as_path),
    )
}

pub(super) fn socket_path_for(cwd: &Path, socket: Option<&Path>) -> CargoResult<PathBuf> {
    if let Some(path) = socket {
        return Ok(cwd.join(path));
    }
    let cwd = cwd.canonicalize()?;
    let mut hash = Sha256::new();
    hash.update(cwd.as_os_str().as_bytes());
    // SAFETY: getuid has no preconditions.
    let uid = unsafe { libc::getuid() };
    Ok(PathBuf::from(format!(
        "/tmp/cargo-session-{uid}-{}/server.sock",
        &hash.finish_hex()[..16]
    )))
}

struct SocketGuard {
    path: PathBuf,
    device: u64,
    inode: u64,
}

impl SocketGuard {
    fn bind(path: PathBuf) -> CargoResult<(UnixListener, Self)> {
        let parent = path
            .parent()
            .context("session socket has no parent directory")?;
        fs::DirBuilder::new()
            .recursive(true)
            .mode(0o700)
            .create(parent)?;
        let directory = fs::symlink_metadata(parent)?;
        // SAFETY: getuid has no preconditions.
        let uid = unsafe { libc::getuid() };
        ensure!(
            directory.is_dir()
                && directory.uid() == uid
                && directory.permissions().mode() & 0o077 == 0,
            "the session socket must be in a directory owned by you with mode 0700"
        );
        // In particular, do not unlink a socket belonging to another server.
        let listener = UnixListener::bind(&path)
            .with_context(|| format!("could not bind session socket {}", path.display()))?;
        let metadata = fs::symlink_metadata(&path)?;
        Ok((
            listener,
            Self {
                path,
                device: metadata.dev(),
                inode: metadata.ino(),
            },
        ))
    }
}

impl Drop for SocketGuard {
    fn drop(&mut self) {
        if let Ok(metadata) = fs::symlink_metadata(&self.path) {
            if metadata.file_type().is_socket()
                && metadata.dev() == self.device
                && metadata.ino() == self.inode
            {
                let _ = fs::remove_file(&self.path);
            }
        }
    }
}

impl SessionListener {
    pub(super) fn bind(path: PathBuf) -> CargoResult<Self> {
        let signals = StopSignals::install()?;
        let (listener, socket) = SocketGuard::bind(path)?;
        Ok(Self {
            _socket: socket,
            listener,
            signals,
        })
    }

    pub(super) fn shutdown_requested(&self) -> bool {
        STOP_REQUESTED.load(Ordering::Acquire)
    }

    pub(super) fn request_reader<'a>(&'a self, connection: &'a mut UnixStream) -> impl Read + 'a {
        FrameIo {
            connection,
            signals: Some(&self.signals),
            deadline: Instant::now() + FRAME_TIMEOUT,
        }
    }

    pub(super) fn accept(&self) -> CargoResult<Option<UnixStream>> {
        loop {
            if !self.signals.wait(&self.listener)? {
                return Ok(None);
            }
            let connection = match self.listener.accept() {
                Ok((connection, _)) => connection,
                Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
                Err(error) => return Err(error.into()),
            };
            // FrameIo supplies one overall deadline and an interruptible wait.
            // Per-read timeouts alone allow a slow sender to occupy us forever.
            connection.set_nonblocking(true)?;
            return Ok(Some(connection));
        }
    }
}

/// A completed check gets a bounded opportunity to deliver its response even
/// after SIGTERM. A stalled reader cannot keep the server alive indefinitely.
pub(super) fn response_writer(connection: &mut UnixStream) -> impl Write + '_ {
    FrameIo {
        connection,
        signals: None,
        deadline: Instant::now() + FRAME_TIMEOUT,
    }
}

struct FrameIo<'a> {
    connection: &'a mut UnixStream,
    signals: Option<&'a StopSignals>,
    deadline: Instant,
}

impl FrameIo<'_> {
    fn wait(&self, events: libc::c_short) -> io::Result<()> {
        loop {
            if self.signals.is_some() && STOP_REQUESTED.load(Ordering::Acquire) {
                // BufRead deliberately retries Interrupted. Aborted framing
                // must escape that loop so normal server cleanup can run.
                return Err(io::Error::new(
                    io::ErrorKind::ConnectionAborted,
                    "Cargo session is shutting down",
                ));
            }
            let Some(remaining) = self.deadline.checked_duration_since(Instant::now()) else {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "Cargo session frame deadline exceeded",
                ));
            };
            let timeout = remaining.as_millis().max(1).min(i32::MAX as u128) as i32;
            let mut descriptors = [
                libc::pollfd {
                    fd: self.connection.as_raw_fd(),
                    events,
                    revents: 0,
                },
                libc::pollfd {
                    // A negative descriptor is ignored by poll. Response
                    // delivery has a deadline but is allowed during shutdown.
                    fd: self
                        .signals
                        .map_or(-1, |signals| signals.wake.0.as_raw_fd()),
                    events: libc::POLLIN,
                    revents: 0,
                },
            ];
            // SAFETY: the adapter borrows both descriptors for the whole wait.
            let result = unsafe { libc::poll(descriptors.as_mut_ptr(), 2, timeout) };
            if result < 0 {
                let error = io::Error::last_os_error();
                if error.kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(error);
            }
            if result == 0 {
                continue;
            }
            if self.signals.is_some()
                && (STOP_REQUESTED.load(Ordering::Acquire) || descriptors[1].revents != 0)
            {
                return Err(io::Error::new(
                    io::ErrorKind::ConnectionAborted,
                    "Cargo session is shutting down",
                ));
            }
            if descriptors[0].revents & libc::POLLNVAL != 0 {
                return Err(io::Error::other("Cargo session connection is unavailable"));
            }
            if descriptors[0].revents & (events | libc::POLLHUP | libc::POLLERR) != 0 {
                return Ok(());
            }
        }
    }
}

impl Read for FrameIo<'_> {
    fn read(&mut self, bytes: &mut [u8]) -> io::Result<usize> {
        if bytes.is_empty() {
            return Ok(0);
        }
        loop {
            self.wait(libc::POLLIN)?;
            match self.connection.read(bytes) {
                Err(error)
                    if matches!(
                        error.kind(),
                        io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                    ) => {}
                result => return result,
            }
        }
    }
}

impl Write for FrameIo<'_> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if bytes.is_empty() {
            return Ok(0);
        }
        loop {
            self.wait(libc::POLLOUT)?;
            match self.connection.write(bytes) {
                Err(error)
                    if matches!(
                        error.kind(),
                        io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                    ) => {}
                result => return result,
            }
        }
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn frame_deadlines_bound_peers_that_keep_making_progress() {
        let (mut connection, mut peer) = UnixStream::pair().unwrap();
        connection.set_nonblocking(true).unwrap();
        let deadline = Instant::now() + Duration::from_millis(25);
        let sender = std::thread::spawn(move || {
            for _ in 0..20 {
                if peer.write_all(b" ").is_err() {
                    break;
                }
                std::thread::sleep(Duration::from_millis(5));
            }
        });
        let error = FrameIo {
            connection: &mut connection,
            signals: None,
            deadline,
        }
        .read_exact(&mut [0; 100])
        .unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::TimedOut);
        drop(connection);
        sender.join().unwrap();

        let (mut connection, mut peer) = UnixStream::pair().unwrap();
        connection.set_nonblocking(true).unwrap();
        // Fill the socket before starting a deliberately slow receiver.
        loop {
            match connection.write(&[0; 8192]) {
                Ok(_) => {}
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => break,
                Err(error) => panic!("could not fill socket: {error}"),
            }
        }
        let deadline = Instant::now() + Duration::from_millis(25);
        let receiver = std::thread::spawn(move || {
            for _ in 0..20 {
                if peer.read(&mut [0; 4096]).unwrap_or(0) == 0 {
                    break;
                }
                std::thread::sleep(Duration::from_millis(5));
            }
        });
        let error = FrameIo {
            connection: &mut connection,
            signals: None,
            deadline,
        }
        .write_all(&vec![0; 1024 * 1024])
        .unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::TimedOut);
        drop(connection);
        receiver.join().unwrap();
    }
}
