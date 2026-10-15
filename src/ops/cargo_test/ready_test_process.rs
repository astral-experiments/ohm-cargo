//! Cancellation and terminal job control for an early test process group.
//!
//! A terminal test owns the foreground while it runs. A small relay in that
//! group forwards terminal signals to Cargo's original job, including compilers.
//! The relay ends with the test; it never survives the Cargo invocation.

use crate::util::CargoResult;
use std::process::{Child, Command};
use std::sync::atomic::{AtomicBool, AtomicI32, Ordering};

#[cfg(unix)]
use std::{
    fs::File,
    io::{IsTerminal, Read, Write},
    os::{fd::AsRawFd, unix::process::CommandExt},
    process::Stdio,
    sync::Arc,
};

static SIGNALS_IN_USE: AtomicBool = AtomicBool::new(false);
static ACTIVE_GROUP: AtomicI32 = AtomicI32::new(0);
static INTERRUPTED: AtomicI32 = AtomicI32::new(0);
static JOB_CONTROL: AtomicI32 = AtomicI32::new(0);

#[cfg(unix)]
const SIGNALS: [i32; 8] = [
    libc::SIGINT,
    libc::SIGTERM,
    libc::SIGHUP,
    libc::SIGQUIT,
    libc::SIGTSTP,
    libc::SIGTTIN,
    libc::SIGTTOU,
    libc::SIGCONT,
];

/// Save signal dispositions and keep the controlling terminal open until every
/// early test has finished. Unsupported handlers leave ordinary execution intact.
pub(super) struct Signals {
    #[cfg(unix)]
    previous: Vec<(i32, libc::sigaction)>,
    #[cfg(unix)]
    terminal: Option<Arc<Terminal>>,
}

#[cfg(unix)]
extern "C" fn forward_signal(signal: i32) {
    let saved_errno = errno::errno();
    let group = ACTIVE_GROUP.load(Ordering::SeqCst);
    // SAFETY: only async-signal-safe operations and atomics. Terminal changes
    // happen in check(), on the same thread as process-group setup and cleanup.
    unsafe {
        match signal {
            libc::SIGCONT => {
                JOB_CONTROL.store(signal, Ordering::SeqCst);
            }
            libc::SIGTSTP | libc::SIGTTIN | libc::SIGTTOU => {
                if group > 0 {
                    libc::kill(-group, libc::SIGSTOP);
                }
                JOB_CONTROL.store(signal, Ordering::SeqCst);
            }
            _ => {
                if group > 0 {
                    libc::kill(-group, libc::SIGKILL);
                }
                let _ = INTERRUPTED.compare_exchange(0, signal, Ordering::SeqCst, Ordering::SeqCst);
            }
        }
    }
    errno::set_errno(saved_errno);
}

#[cfg(unix)]
fn signal_action(handler: extern "C" fn(i32)) -> libc::sigaction {
    // SAFETY: initialize a valid sigaction and block our other callbacks while
    // handling a signal, including SIGCONT until suspension has completed.
    unsafe {
        let mut action: libc::sigaction = std::mem::zeroed();
        action.sa_sigaction = handler as *const () as usize;
        action.sa_flags = libc::SA_RESTART;
        libc::sigemptyset(&mut action.sa_mask);
        for signal in SIGNALS {
            libc::sigaddset(&mut action.sa_mask, signal);
        }
        action
    }
}

impl Signals {
    pub(super) fn new() -> CargoResult<Self> {
        #[cfg(not(unix))]
        anyhow::bail!("early test execution is only supported on Unix");
        #[cfg(unix)]
        {
            let terminal = Terminal::open()?.map(Arc::new);
            anyhow::ensure!(
                SIGNALS_IN_USE
                    .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
                    .is_ok(),
                "signal forwarding already active"
            );
            let mut signals = Self {
                previous: Vec::new(),
                terminal,
            };
            let action = signal_action(forward_signal);
            for signal in SIGNALS {
                // SAFETY: valid signals and initialized sigaction structures.
                unsafe {
                    let mut previous: libc::sigaction = std::mem::zeroed();
                    if libc::sigaction(signal, std::ptr::null(), &mut previous) != 0 {
                        return Err(std::io::Error::last_os_error().into());
                    }
                    anyhow::ensure!(
                        previous.sa_sigaction == libc::SIG_DFL,
                        "custom signal handler requires ordinary test execution"
                    );
                    if libc::sigaction(signal, &action, std::ptr::null_mut()) != 0 {
                        return Err(std::io::Error::last_os_error().into());
                    }
                    signals.previous.push((signal, previous));
                }
            }
            Ok(signals)
        }
    }

    /// Defer termination until a just-spawned child is registered, closing the
    /// spawn/handler race before restoring Cargo's original default disposition.
    pub(super) fn check(&self) {
        #[cfg(unix)]
        loop {
            let group = ACTIVE_GROUP.load(Ordering::SeqCst);
            let signal = INTERRUPTED.load(Ordering::SeqCst);
            if signal != 0 {
                if let Some(terminal) = &self.terminal {
                    terminal.restore(group);
                }
                // SAFETY: signal only the owned group and this Cargo process.
                unsafe {
                    if group > 0 {
                        libc::kill(-group, libc::SIGKILL);
                    }
                    libc::signal(signal, libc::SIG_DFL);
                    libc::raise(signal);
                }
                std::process::exit(128 + signal);
            }
            match JOB_CONTROL.swap(0, Ordering::SeqCst) {
                0 => break,
                libc::SIGCONT => {
                    if group > 0 {
                        // `fg` grants the terminal to Cargo; `bg` does not.
                        // Restore foreground ownership before resuming readers.
                        if let Some(terminal) = &self.terminal {
                            let _ = terminal.handoff(group);
                        }
                        unsafe { libc::kill(-group, libc::SIGCONT) };
                    }
                }
                _ => {
                    if group > 0 {
                        // Include a child registered after the signal arrived.
                        unsafe { libc::kill(-group, libc::SIGSTOP) };
                        if let Some(terminal) = &self.terminal {
                            terminal.restore(group);
                        }
                    }
                    // The relay signalled the other original job members.
                    // Stop Cargo so the parent shell sees a stopped job, then
                    // process its SIGCONT before returning to the scheduler.
                    unsafe { libc::kill(libc::getpid(), libc::SIGSTOP) };
                }
            }
        }
    }
}

impl Drop for Signals {
    fn drop(&mut self) {
        #[cfg(unix)]
        {
            for (signal, previous) in self.previous.drain(..) {
                // SAFETY: restore the saved disposition before closing the tty.
                unsafe { libc::sigaction(signal, &previous, std::ptr::null_mut()) };
            }
        }
        ACTIVE_GROUP.store(0, Ordering::SeqCst);
        INTERRUPTED.store(0, Ordering::SeqCst);
        JOB_CONTROL.store(0, Ordering::SeqCst);
        SIGNALS_IN_USE.store(false, Ordering::SeqCst);
    }
}

/// A separately cancellable test group, optionally owning the terminal. The
/// terminal and relay are restored even when spawning the test itself fails.
pub(super) struct ProcessGroup {
    id: i32,
    #[cfg(unix)]
    relay: Option<Child>,
    #[cfg(unix)]
    terminal: Option<Arc<Terminal>>,
}

impl ProcessGroup {
    /// Spawn the test in its owned group; restore the terminal and reap the relay
    /// if startup fails.
    #[cfg_attr(not(unix), allow(unused_variables))]
    pub(super) fn spawn(signals: &Signals, command: &mut Command) -> CargoResult<(Child, Self)> {
        let mut group = Self {
            id: 0,
            #[cfg(unix)]
            relay: None,
            #[cfg(unix)]
            terminal: signals.terminal.clone(),
        };
        #[cfg(unix)]
        if let Some(terminal) = &group.terminal {
            terminal.check()?;
            let child = Command::new(std::env::current_exe()?)
                .arg("--ohm-ready-test-relay")
                // SAFETY: getpgrp has no preconditions.
                .arg(unsafe { libc::getpgrp() }.to_string())
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::null())
                .process_group(0)
                .spawn()?;
            group.id = child.id() as i32;
            group.relay = Some(child);
            ACTIVE_GROUP.store(group.id, Ordering::SeqCst);
            let stdout = group.relay.as_mut().unwrap().stdout.as_mut().unwrap();
            // A bounded handshake also gives library embedders whose executable
            // does not implement our internal relay command a safe fallback.
            let mut poll = libc::pollfd {
                fd: stdout.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            // SAFETY: poll points to one initialized descriptor.
            anyhow::ensure!(
                unsafe { libc::poll(&mut poll, 1, 1000) } > 0,
                "relay not ready"
            );
            let mut ready = [0];
            stdout.read_exact(&mut ready)?;
            anyhow::ensure!(ready == [b'R'], "invalid relay handshake");
            signals.check();
            // Only hand off a terminal we own. Background launches stay in the
            // background and retain ordinary SIGTTIN / `fg` behavior.
            terminal.handoff(group.id)?;
        }
        #[cfg(unix)]
        command.process_group(group.id);
        let child = command.spawn()?;
        if group.id == 0 {
            group.id = child.id() as i32;
        }
        ACTIVE_GROUP.store(group.id, Ordering::SeqCst);
        Ok((child, group))
    }

    pub(super) fn cancel(&self) {
        #[cfg(unix)]
        if self.id > 0 {
            // SAFETY: this group belongs to the current early test and relay.
            unsafe { libc::kill(-self.id, libc::SIGKILL) };
        }
    }
}

impl Drop for ProcessGroup {
    fn drop(&mut self) {
        // A concurrent SIGCONT must not hand the tty back to a finishing group.
        ACTIVE_GROUP.store(0, Ordering::SeqCst);
        #[cfg(unix)]
        {
            if let Some(terminal) = &self.terminal {
                terminal.restore(self.id);
            }
            if let Some(relay) = &mut self.relay {
                // Kill just the relay on normal completion. Tests may have
                // deliberately left children running, as with ordinary Cargo.
                let _ = relay.kill();
                let _ = relay.wait();
            }
        }
    }
}

#[cfg(unix)]
struct Terminal(File);

#[cfg(unix)]
impl Terminal {
    fn open() -> CargoResult<Option<Self>> {
        let streams = [
            std::io::stdin().is_terminal(),
            std::io::stdout().is_terminal(),
            std::io::stderr().is_terminal(),
        ];
        if streams.iter().all(|terminal| !terminal) {
            return Ok(None);
        }
        // A pipeline's pager or a wrapper may also need foreground input. Only
        // take the terminal from a direct Cargo job with terminal stdio; otherwise
        // keep the shell's shared process group and ordinary test execution.
        // SAFETY: getpid and getpgrp have no preconditions.
        anyhow::ensure!(
            streams.iter().all(|terminal| *terminal)
                && unsafe { libc::getpid() == libc::getpgrp() },
            "shared terminal job requires ordinary test execution"
        );
        let terminal = Self(File::open("/dev/tty")?);
        terminal.check()?;
        Ok(Some(terminal))
    }

    fn check(&self) -> CargoResult<()> {
        // TOSTOP would suspend the compiling side while the test is foreground.
        // Preserve that uncommon terminal policy by retaining ordinary execution.
        // SAFETY: initialize termios and inspect our open controlling terminal.
        unsafe {
            let mut attrs: libc::termios = std::mem::zeroed();
            if libc::tcgetattr(self.0.as_raw_fd(), &mut attrs) != 0 {
                return Err(std::io::Error::last_os_error().into());
            }
            anyhow::ensure!(attrs.c_lflag & libc::TOSTOP == 0, "terminal uses TOSTOP");
        }
        Ok(())
    }

    fn foreground(&self) -> i32 {
        // SAFETY: this descriptor stays open for the terminal lease.
        unsafe { libc::tcgetpgrp(self.0.as_raw_fd()) }
    }

    fn handoff(&self, group: i32) -> CargoResult<()> {
        // SAFETY: getpgrp has no preconditions. Do not take the tty from another
        // foreground job when this Cargo command was resumed with `bg`.
        if self.foreground() == unsafe { libc::getpgrp() } {
            self.set_foreground(group)?;
        }
        Ok(())
    }

    fn restore(&self, group: i32) {
        if group > 0 && self.foreground() == group {
            // SAFETY: getpgrp has no preconditions.
            let _ = self.set_foreground(unsafe { libc::getpgrp() });
        }
    }

    fn set_foreground(&self, group: i32) -> CargoResult<()> {
        // SAFETY: block SIGTTOU on this thread while reclaiming the tty from a
        // child. Restore the thread's original mask on success and failure.
        unsafe {
            let mut mask: libc::sigset_t = std::mem::zeroed();
            let mut previous: libc::sigset_t = std::mem::zeroed();
            libc::sigemptyset(&mut mask);
            libc::sigaddset(&mut mask, libc::SIGTTOU);
            let error = libc::pthread_sigmask(libc::SIG_BLOCK, &mask, &mut previous);
            if error != 0 {
                return Err(std::io::Error::from_raw_os_error(error).into());
            }
            let result = libc::tcsetpgrp(self.0.as_raw_fd(), group);
            let error = std::io::Error::last_os_error();
            libc::pthread_sigmask(libc::SIG_SETMASK, &previous, std::ptr::null_mut());
            if result != 0 {
                return Err(error.into());
            }
        }
        Ok(())
    }
}

#[cfg(unix)]
static RELAY_PARENT_GROUP: AtomicI32 = AtomicI32::new(0);

#[cfg(unix)]
extern "C" fn relay_signal(signal: i32) {
    let saved_errno = errno::errno();
    // SAFETY: forward to the original Cargo job, not the relay's own group.
    unsafe { libc::kill(-RELAY_PARENT_GROUP.load(Ordering::SeqCst), signal) };
    errno::set_errno(saved_errno);
}

/// Internal Cargo entry point, before logging, configuration, or worker threads.
/// Keep a signal recipient in the test group even if a test ignores Ctrl-C.
#[cfg(unix)]
#[doc(hidden)]
pub fn run_ready_test_relay() -> bool {
    let mut args = std::env::args_os().skip(1);
    if args.next().as_deref() != Some(std::ffi::OsStr::new("--ohm-ready-test-relay")) {
        return false;
    }
    let parent_group: i32 = args
        .next()
        .and_then(|arg| arg.into_string().ok())
        .and_then(|arg| arg.parse().ok())
        .filter(|group| *group > 0)
        .unwrap_or_else(|| std::process::exit(1));
    RELAY_PARENT_GROUP.store(parent_group, Ordering::SeqCst);
    let action = signal_action(relay_signal);
    for signal in SIGNALS
        .into_iter()
        .filter(|signal| *signal != libc::SIGCONT)
    {
        // SAFETY: install our callback before acknowledging readiness.
        if unsafe { libc::sigaction(signal, &action, std::ptr::null_mut()) } != 0 {
            std::process::exit(1);
        }
    }
    if std::io::stdout()
        .write_all(b"R")
        .and_then(|()| std::io::stdout().flush())
        .is_err()
    {
        std::process::exit(1);
    }
    loop {
        match std::io::stdin().read(&mut [0]) {
            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
            _ => break,
        }
    }
    // The parent keeps this pipe open and kills/reaps the relay on completion.
    // EOF means it disappeared unexpectedly: cancel the otherwise orphaned tests.
    unsafe { libc::kill(0, libc::SIGKILL) };
    true
}
