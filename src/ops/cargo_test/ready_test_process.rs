//! Cancellation and terminal job control for an early test process group.
//!
//! A terminal test owns the foreground while it runs. A small relay in that
//! group forwards cancellation to Cargo's original job and participates in tty stops.
//! The relay ends with the test; it never survives the Cargo invocation.

use crate::util::CargoResult;
use std::process::{Child, Command, ExitStatus};
use std::sync::atomic::{AtomicBool, AtomicI32, Ordering};

#[cfg(unix)]
use std::{
    fs::File,
    io::{IsTerminal, Read, Write},
    os::{
        fd::AsRawFd,
        unix::process::{CommandExt, ExitStatusExt},
    },
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
            libc::SIGCONT | libc::SIGTSTP | libc::SIGTTIN | libc::SIGTTOU => {
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

    /// Defer cancellation until spawn is registered and synchronize tty ownership
    /// with the kernel's stop notification for the active test group.
    #[cfg_attr(not(unix), allow(unused_variables, unused_mut))]
    pub(super) fn check(&self, mut active: Option<&mut ProcessGroup>) {
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
            let requested = JOB_CONTROL.swap(0, Ordering::SeqCst);
            let stopped = requested == 0
                && self.terminal.is_some()
                && active
                    .as_deref_mut()
                    .is_some_and(|job| job.observe_stops(false));
            match requested {
                0 if !stopped => break,
                libc::SIGCONT => {
                    // A late notification for our own resume must not wake a
                    // background reader a second time after SIGTTIN stops it.
                    if let Some(terminal) = &self.terminal
                        && terminal.foreground() != unsafe { libc::getpgrp() }
                    {
                        continue;
                    }
                }
                _ => {
                    if group > 0 {
                        // Include a child registered after the signal arrived.
                        unsafe { libc::kill(-group, libc::SIGSTOP) };
                        if let Some(terminal) = &self.terminal {
                            // A pending SIGSTOP still lets a reader consume the shell's input.
                            if let Some(job) = active.as_deref_mut() {
                                job.observe_stops(true);
                            }
                            wait_for_readers(group);
                            if INTERRUPTED.load(Ordering::SeqCst) != 0 {
                                continue;
                            }
                            terminal.restore(group);
                        }
                    }
                    // A terminal job owns its process group. Include compiling
                    // children in the shell stop, then suspend this scheduler thread.
                    // Headless Cargo can share its caller's group.
                    unsafe {
                        if self.terminal.is_some() {
                            signal_members(libc::getpgrp(), libc::SIGTSTP);
                        }
                        libc::raise(libc::SIGSTOP);
                        if self.terminal.is_some() {
                            signal_members(libc::getpgrp(), libc::SIGCONT);
                        }
                    }
                    // Returning from suspension means the shell has continued Cargo.
                    JOB_CONTROL.store(0, Ordering::SeqCst);
                }
            }
            if group > 0 {
                // `fg` grants the terminal to Cargo; `bg` does not.
                if let Some(terminal) = &self.terminal {
                    let _ = terminal.handoff(group);
                }
                if let Some(job) = active.as_deref_mut() {
                    for child in job.test.iter_mut().chain(job.relay.iter_mut()) {
                        child.stopped = None;
                    }
                }
                signal_members(group, libc::SIGCONT);
            }
        }
    }
}

/// Resume the relay before readers can stop it again with SIGTTIN. Delivering
/// stop/continue to each existing process also keeps a concurrent compiler fork
/// from inheriting a process-group stop after its parent has already resumed.
#[cfg(unix)]
fn signal_members(group: i32, signal: i32) {
    let Some(members) = group_members(group) else {
        // If membership is unavailable, keep signaling just the owned group.
        unsafe { libc::kill(-group, signal) };
        return;
    };
    let this = unsafe { libc::getpid() };
    for pid in std::iter::once(group).chain(members.into_iter().filter(|&pid| pid != group)) {
        if pid > 0 && pid != this && unsafe { libc::getpgid(pid) } == group {
            unsafe { libc::kill(pid, signal) };
        }
    }
}

/// A grandchild can be blocked in read(2) even after both direct children stop.
/// Let every reader leave that syscall before the shell can accept the next command.
#[cfg(unix)]
fn wait_for_readers(group: i32) {
    while INTERRUPTED.load(Ordering::SeqCst) == 0
        && group_members(group).is_some_and(|pids| {
            pids.into_iter()
                .any(|pid| process_stopped(pid) == Some(false))
        })
    {
        // Include any descendants that joined the group during the first stop.
        unsafe { libc::kill(-group, libc::SIGSTOP) };
        std::thread::sleep(std::time::Duration::from_millis(1));
    }
}

#[cfg(target_os = "linux")]
fn process_stopped(pid: i32) -> Option<bool> {
    // A libtest reader may run on a different thread from the process leader.
    let tasks = std::fs::read_dir(format!("/proc/{pid}/task")).ok()?;
    for task in tasks.flatten() {
        if let Ok(stat) = std::fs::read(task.path().join("stat"))
            && let Some(&state) = stat.rsplit(|&byte| byte == b')').next()?.get(1)
            && !matches!(state, b'T' | b't' | b'Z' | b'X')
        {
            return Some(false);
        }
    }
    Some(true)
}

#[cfg(target_vendor = "apple")]
fn process_stopped(pid: i32) -> Option<bool> {
    let mut info = std::mem::MaybeUninit::<libc::proc_bsdinfo>::uninit();
    let size = std::mem::size_of_val(&info) as i32;
    // SAFETY: only read the result after libproc fills the entire structure.
    unsafe {
        let bytes = libc::proc_pidinfo(
            pid,
            libc::PROC_PIDTBSDINFO,
            0,
            info.as_mut_ptr().cast(),
            size,
        );
        (bytes == size).then(|| matches!(info.assume_init().pbi_status, libc::SSTOP | libc::SZOMB))
    }
}

#[cfg(all(unix, not(any(target_os = "linux", target_vendor = "apple"))))]
fn process_stopped(pid: i32) -> Option<bool> {
    let output = Command::new("ps")
        .args(["-p", &pid.to_string(), "-o", "stat="])
        .output()
        .ok()?;
    let state = std::str::from_utf8(&output.stdout)
        .ok()?
        .trim_start()
        .as_bytes()
        .first()?;
    Some(matches!(state, b'T' | b'Z' | b'X'))
}

/// Snapshot job membership before any reader is resumed.
#[cfg(target_os = "linux")]
fn group_members(group: i32) -> Option<Vec<i32>> {
    Some(
        std::fs::read_dir("/proc")
            .ok()?
            .flatten()
            .filter_map(|entry| {
                let pid: i32 = entry.file_name().to_str()?.parse().ok()?;
                (unsafe { libc::getpgid(pid) } == group).then_some(pid)
            })
            .collect(),
    )
}

#[cfg(target_vendor = "apple")]
fn group_members(group: i32) -> Option<Vec<i32>> {
    let mut pids = vec![0; 16];
    loop {
        let bytes = std::mem::size_of_val(pids.as_slice()).try_into().ok()?;
        // SAFETY: libproc writes at most `bytes` into the provided pid buffer.
        let count = unsafe { libc::proc_listpgrppids(group, pids.as_mut_ptr().cast(), bytes) };
        let count = usize::try_from(count).ok()?;
        if count < pids.len() {
            pids.truncate(count);
            return Some(pids);
        }
        pids.resize(pids.len().checked_mul(2)?, 0);
    }
}

#[cfg(all(unix, not(any(target_os = "linux", target_vendor = "apple"))))]
fn group_members(group: i32) -> Option<Vec<i32>> {
    let output = Command::new("ps")
        .args(["-A", "-o", "pid=", "-o", "pgid="])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    Some(
        std::str::from_utf8(&output.stdout)
            .ok()?
            .lines()
            .filter_map(|line| {
                let mut fields = line.split_whitespace();
                let pid = fields.next()?.parse().ok()?;
                (fields.next()?.parse::<i32>().ok()? == group).then_some(pid)
            })
            .collect(),
    )
}

/// A terminal stop and a test exit are reported by the same Unix wait operation.
/// Keep any observed exit status for the ordinary completion path.
struct JobChild {
    child: Child,
    status: Option<ExitStatus>,
    #[cfg(unix)]
    stopped: Option<i32>,
}

impl JobChild {
    fn new(child: Child) -> Self {
        Self {
            child,
            status: None,
            #[cfg(unix)]
            stopped: None,
        }
    }

    /// Observe a stop without losing an exit that wins the race with SIGSTOP.
    #[cfg(unix)]
    fn observe_stop(&mut self, group: i32, wait: bool) -> Option<i32> {
        if self.stopped.is_some() {
            return self.stopped;
        }
        if self.status.is_some() {
            return None;
        }
        // A test can leave its assigned group. Only wait for a stop we sent.
        if wait && unsafe { libc::getpgid(self.child.id() as _) } != group {
            return None;
        }
        let options = libc::WUNTRACED | if wait { 0 } else { libc::WNOHANG };
        let mut status = 0;
        loop {
            // SAFETY: wait for this child only, with initialized status storage.
            let result = unsafe { libc::waitpid(self.child.id() as _, &mut status, options) };
            if result > 0 {
                if libc::WIFSTOPPED(status) {
                    self.stopped = Some(libc::WSTOPSIG(status));
                    return self.stopped;
                }
                self.status = Some(ExitStatus::from_raw(status));
                return None;
            }
            if result == 0 || errno::errno().0 != libc::EINTR {
                return None;
            }
        }
    }

    fn try_wait(&mut self) -> std::io::Result<Option<ExitStatus>> {
        if self.status.is_none() {
            self.status = self.child.try_wait()?;
        }
        Ok(self.status)
    }

    /// A child whose status we already consumed no longer owns its PID.
    fn cancel(&mut self) {
        if self.status.is_none() {
            let _ = self.child.kill();
            let _ = self.child.wait();
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
    test: Option<JobChild>,
    #[cfg(unix)]
    relay: Option<JobChild>,
    #[cfg(unix)]
    terminal: Option<Arc<Terminal>>,
}

impl ProcessGroup {
    /// Spawn the test in its owned group; restore the terminal and reap the relay
    /// if startup fails.
    #[cfg_attr(not(unix), allow(unused_variables))]
    pub(super) fn spawn(signals: &Signals, command: &mut Command) -> CargoResult<Self> {
        let mut group = Self {
            id: 0,
            test: None,
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
            group.relay = Some(JobChild::new(child));
            ACTIVE_GROUP.store(group.id, Ordering::SeqCst);
            let stdout = group.relay.as_mut().unwrap().child.stdout.as_mut().unwrap();
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
            signals.check(None);
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
        group.test = Some(JobChild::new(child));
        Ok(group)
    }

    /// The relay also stops when a test ignores a terminal signal. Observe both
    /// children so a delayed signal cannot stop the compiling side after `fg`.
    #[cfg(unix)]
    fn observe_stops(&mut self, wait: bool) -> bool {
        let test = self
            .test
            .as_mut()
            .and_then(|child| child.observe_stop(self.id, wait));
        let relay = self
            .relay
            .as_mut()
            .and_then(|child| child.observe_stop(self.id, wait));
        // A separately paused relay can still forward Ctrl-C at teardown.
        let stopped =
            test.is_some() || matches!(relay, Some(libc::SIGTSTP | libc::SIGTTIN | libc::SIGTTOU));
        // A surviving reader can stop the relay after the test has already exited.
        stopped
            && self
                .test
                .as_mut()
                .is_some_and(|test| !matches!(test.try_wait(), Ok(Some(_))))
    }

    pub(super) fn try_wait(&mut self) -> CargoResult<Option<ExitStatus>> {
        let Some(status) = self.test.as_mut().unwrap().try_wait()? else {
            return Ok(None);
        };
        Ok(self.finish()?.then_some(status))
    }

    /// After the test exits, give the relay time to forward any terminal signal.
    /// The scheduler continues servicing job control while the relay exits.
    fn finish(&mut self) -> CargoResult<bool> {
        #[cfg(unix)]
        if let Some(relay) = &mut self.relay {
            let input = relay.child.stdin.take();
            if input.is_some()
                && let Some(terminal) = &self.terminal
            {
                terminal.restore(self.id);
            }
            // A reader can stop the relay again after the initial resume. Let it
            // forward pending Ctrl-C and consume the finish command in either case.
            if (relay.stopped.take().is_some() || input.is_some()) && relay.status.is_none() {
                // SAFETY: resume only the owned relay.
                unsafe { libc::kill(self.id, libc::SIGCONT) };
            }
            if let Some(mut input) = input
                && let Err(error) = input.write_all(b"F")
                && error.kind() != std::io::ErrorKind::BrokenPipe
            {
                return Err(error.into());
            }
            if relay.try_wait()?.is_none() {
                return Ok(false);
            }
            self.relay = None;
        }
        Ok(true)
    }

    pub(super) fn cancel(&mut self) {
        #[cfg(unix)]
        if self.id > 0 {
            // SAFETY: this group belongs to the current early test and relay.
            unsafe { libc::kill(-self.id, libc::SIGKILL) };
        }
        if let Some(test) = &mut self.test {
            test.cancel();
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
                // Startup or teardown failed before the relay finished.
                relay.cancel();
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
        // Redirecting every standard stream does not detach a shell job from
        // its controlling terminal. Only headless jobs can omit the relay.
        let terminal = match File::open("/dev/tty") {
            Ok(terminal) => Self(terminal),
            Err(error)
                if streams.iter().all(|terminal| !terminal)
                    && matches!(
                        error.raw_os_error(),
                        Some(libc::ENXIO | libc::ENODEV | libc::ENOENT)
                    ) =>
            {
                return Ok(None);
            }
            Err(error) => return Err(error.into()),
        };
        // A pipeline's pager or a wrapper may also need foreground input. Only
        // take the terminal from a direct Cargo job with terminal stdio; otherwise
        // keep the shell's shared process group and ordinary test execution.
        // SAFETY: getpid and getpgrp have no preconditions.
        anyhow::ensure!(
            streams.iter().all(|terminal| *terminal)
                && unsafe { libc::getpid() == libc::getpgrp() },
            "shared terminal job requires ordinary test execution"
        );
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
    // Leave tty stop signals at their default disposition. Cargo observes this
    // child's stop before suspending the original job, even if the test ignores it.
    for signal in [libc::SIGINT, libc::SIGTERM, libc::SIGHUP, libc::SIGQUIT] {
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
    let mut command = [0];
    loop {
        match std::io::stdin().read(&mut command) {
            Ok(1) if command == *b"F" => return true,
            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
            _ => break,
        }
    }
    // EOF without a finish command means Cargo disappeared. Cancel its tests.
    unsafe { libc::kill(0, libc::SIGKILL) };
    true
}

#[cfg(all(test, unix))]
#[test]
fn a_stopped_relay_finishes_after_its_test_exits() {
    let mut command = Command::new("sh");
    command.args(["-c", "kill -TTIN $$; cat >/dev/null; kill -TTIN $$"]);
    command.stdin(Stdio::piped()).process_group(0);
    // SAFETY: restore the default disposition in the child before executing sh.
    unsafe {
        command.pre_exec(|| {
            libc::signal(libc::SIGTTIN, libc::SIG_DFL);
            Ok(())
        });
    }
    let relay = command.spawn().unwrap();
    let id = relay.id() as i32;
    let test = Command::new("sh")
        .args(["-c", "exit 7"])
        .process_group(id)
        .spawn()
        .unwrap();
    let mut group = ProcessGroup {
        id,
        test: Some(JobChild::new(test)),
        relay: Some(JobChild::new(relay)),
        terminal: None,
    };

    assert!(!group.observe_stops(true));
    assert!(group.try_wait().unwrap().is_none());
    // The reader stops the relay again after Cargo has sent its finish command.
    assert!(!group.observe_stops(true));
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
    loop {
        if let Some(status) = group.try_wait().unwrap() {
            assert_eq!(status.code(), Some(7));
            break;
        }
        assert!(
            std::time::Instant::now() < deadline,
            "the relay stayed stopped"
        );
        std::thread::sleep(std::time::Duration::from_millis(1));
    }
}
