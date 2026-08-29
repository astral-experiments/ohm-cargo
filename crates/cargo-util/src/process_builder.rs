use crate::process_error::ProcessError;
use crate::read2;

use anyhow::{Context, Result, bail};
use jobserver::Client;
use shell_escape::escape;
use tempfile::NamedTempFile;

use std::collections::BTreeMap;
use std::env;
use std::ffi::{OsStr, OsString};
use std::fmt;
#[cfg(unix)]
use std::fs::File;
use std::io::{self, Write};
use std::iter::once;
use std::path::Path;
use std::process::{Command, ExitStatus, Output, Stdio};
#[cfg(unix)]
use std::sync::Arc;

/// A builder object for an external process, similar to [`std::process::Command`].
#[derive(Clone, Debug)]
pub struct ProcessBuilder {
    /// The program to execute.
    program: OsString,
    /// Best-effort replacement for arg0
    arg0: Option<OsString>,
    /// A list of arguments to pass to the program.
    args: Vec<OsString>,
    /// Any environment variables that should be set for the program.
    env: BTreeMap<String, Option<OsString>>,
    /// The directory to run the program from.
    cwd: Option<OsString>,
    /// A list of wrappers that wrap the original program when calling
    /// [`ProcessBuilder::wrapped`]. The last one is the outermost one.
    wrappers: Vec<OsString>,
    /// The `make` jobserver. See the [jobserver crate] for
    /// more information.
    ///
    /// [jobserver crate]: https://docs.rs/jobserver/
    jobserver: Option<Client>,
    /// Files whose descriptors must remain open across the child's exec.
    #[cfg(unix)]
    inherited_files: Vec<Arc<File>>,
    /// `true` to include environment variable in display.
    display_env_vars: bool,
    /// `true` to retry with an argfile if hitting "command line too big" error.
    /// See [`ProcessBuilder::retry_with_argfile`] for more information.
    retry_with_argfile: bool,
    /// Data to write to stdin.
    stdin: Option<Vec<u8>>,
}

impl fmt::Display for ProcessBuilder {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "`")?;

        if self.display_env_vars {
            for (key, val) in self.env.iter() {
                if let Some(val) = val {
                    let val = escape(val.to_string_lossy());
                    if cfg!(windows) {
                        write!(f, "set {}={}&& ", key, val)?;
                    } else {
                        write!(f, "{}={} ", key, val)?;
                    }
                }
            }
        }

        write!(f, "{}", self.get_program().to_string_lossy())?;

        for arg in self.get_args() {
            write!(f, " {}", escape(arg.to_string_lossy()))?;
        }

        write!(f, "`")
    }
}

impl ProcessBuilder {
    /// Creates a new [`ProcessBuilder`] with the given executable path.
    pub fn new<T: AsRef<OsStr>>(cmd: T) -> ProcessBuilder {
        ProcessBuilder {
            program: cmd.as_ref().to_os_string(),
            arg0: None,
            args: Vec::new(),
            cwd: None,
            env: BTreeMap::new(),
            wrappers: Vec::new(),
            jobserver: None,
            #[cfg(unix)]
            inherited_files: Vec::new(),
            display_env_vars: false,
            retry_with_argfile: false,
            stdin: None,
        }
    }

    /// (chainable) Sets the executable for the process.
    pub fn program<T: AsRef<OsStr>>(&mut self, program: T) -> &mut ProcessBuilder {
        self.program = program.as_ref().to_os_string();
        self
    }

    /// (chainable) Overrides `arg0` for this program.
    pub fn arg0<T: AsRef<OsStr>>(&mut self, arg: T) -> &mut ProcessBuilder {
        self.arg0 = Some(arg.as_ref().to_os_string());
        self
    }

    /// (chainable) Adds `arg` to the args list.
    pub fn arg<T: AsRef<OsStr>>(&mut self, arg: T) -> &mut ProcessBuilder {
        self.args.push(arg.as_ref().to_os_string());
        self
    }

    /// (chainable) Adds multiple `args` to the args list.
    pub fn args<T: AsRef<OsStr>>(&mut self, args: &[T]) -> &mut ProcessBuilder {
        self.args
            .extend(args.iter().map(|t| t.as_ref().to_os_string()));
        self
    }

    /// (chainable) Replaces the args list with the given `args`.
    pub fn args_replace<T: AsRef<OsStr>>(&mut self, args: &[T]) -> &mut ProcessBuilder {
        if let Some(program) = self.wrappers.pop() {
            // User intend to replace all args, so we
            // - use the outermost wrapper as the main program, and
            // - cleanup other inner wrappers.
            self.program = program;
            self.wrappers = Vec::new();
        }
        self.args = args.iter().map(|t| t.as_ref().to_os_string()).collect();
        self
    }

    /// Replaces the first argument exactly matching `from`.
    ///
    /// Unlike [`ProcessBuilder::args_replace`], this preserves compiler
    /// wrappers and every other argument on the command line.
    pub fn replace_arg<T: AsRef<OsStr>, U: AsRef<OsStr>>(&mut self, from: T, to: U) -> bool {
        let Some(argument) = self
            .args
            .iter_mut()
            .find(|argument| argument.as_os_str() == from.as_ref())
        else {
            return false;
        };
        *argument = to.as_ref().to_os_string();
        true
    }

    /// (chainable) Sets the current working directory of the process.
    pub fn cwd<T: AsRef<OsStr>>(&mut self, path: T) -> &mut ProcessBuilder {
        self.cwd = Some(path.as_ref().to_os_string());
        self
    }

    /// (chainable) Sets an environment variable for the process.
    pub fn env<T: AsRef<OsStr>>(&mut self, key: &str, val: T) -> &mut ProcessBuilder {
        self.env
            .insert(key.to_string(), Some(val.as_ref().to_os_string()));
        self
    }

    /// (chainable) Unsets an environment variable for the process.
    pub fn env_remove(&mut self, key: &str) -> &mut ProcessBuilder {
        self.env.insert(key.to_string(), None);
        self
    }

    /// Gets the executable name.
    pub fn get_program(&self) -> &OsString {
        self.wrappers.last().unwrap_or(&self.program)
    }

    /// Gets the program arg0.
    pub fn get_arg0(&self) -> Option<&OsStr> {
        self.arg0.as_deref()
    }

    /// Gets the program arguments.
    pub fn get_args(&self) -> impl Iterator<Item = &OsString> {
        self.wrappers
            .iter()
            .rev()
            .chain(once(&self.program))
            .chain(self.args.iter())
            .skip(1) // Skip the main `program
    }

    /// Gets the current working directory for the process.
    pub fn get_cwd(&self) -> Option<&Path> {
        self.cwd.as_ref().map(Path::new)
    }

    /// Gets an environment variable as the process will see it (will inherit from environment
    /// unless explicitly unset).
    pub fn get_env(&self, var: &str) -> Option<OsString> {
        self.env
            .get(var)
            .cloned()
            .or_else(|| Some(env::var_os(var)))
            .and_then(|s| s)
    }

    /// Gets all environment variables explicitly set or unset for the process (not inherited
    /// vars).
    pub fn get_envs(&self) -> &BTreeMap<String, Option<OsString>> {
        &self.env
    }

    /// Sets the `make` jobserver. See the [jobserver crate][jobserver_docs] for
    /// more information.
    ///
    /// [jobserver_docs]: https://docs.rs/jobserver/latest/jobserver/
    pub fn inherit_jobserver(&mut self, jobserver: &Client) -> &mut Self {
        self.jobserver = Some(jobserver.clone());
        self
    }

    /// Keeps a file open in the child, including across `exec`.
    ///
    /// Builder clones and commands retain the file until they are dropped.
    /// Spawning clears close-on-exec only in the child, leaving the parent's
    /// descriptor flags unchanged. An inherited file lock must not be explicitly
    /// unlocked by the parent while the child still needs it.
    #[cfg(unix)]
    pub fn inherit_file(&mut self, file: Arc<File>) -> &mut Self {
        self.inherited_files.push(file);
        self
    }

    /// Enables environment variable display.
    pub fn display_env_vars(&mut self) -> &mut Self {
        self.display_env_vars = true;
        self
    }

    /// Enables retrying with an argfile if hitting "command line too big" error
    ///
    /// This is primarily for the `@path` arg of rustc and rustdoc, which treat
    /// each line as an command-line argument, so `LF` and `CRLF` bytes are not
    /// valid as an argument for argfile at this moment.
    /// For example, `RUSTDOCFLAGS="--crate-version foo\nbar" cargo doc` is
    /// valid when invoking from command-line but not from argfile.
    ///
    /// To sum up, the limitations of the argfile are:
    ///
    /// - Must be valid UTF-8 encoded.
    /// - Must not contain any newlines in each argument.
    ///
    /// Ref:
    ///
    /// - <https://doc.rust-lang.org/rustdoc/command-line-arguments.html#path-load-command-line-flags-from-a-path>
    /// - <https://doc.rust-lang.org/rustc/command-line-arguments.html#path-load-command-line-flags-from-a-path>
    pub fn retry_with_argfile(&mut self, enabled: bool) -> &mut Self {
        self.retry_with_argfile = enabled;
        self
    }

    /// Sets a value that will be written to stdin of the process on launch.
    pub fn stdin<T: Into<Vec<u8>>>(&mut self, stdin: T) -> &mut Self {
        self.stdin = Some(stdin.into());
        self
    }

    fn should_retry_with_argfile(&self, err: &io::Error) -> bool {
        self.retry_with_argfile && imp::command_line_too_big(err)
    }

    /// Like [`Command::status`] but with a better error message.
    pub fn status(&self) -> Result<ExitStatus> {
        self._status()
            .with_context(|| ProcessError::could_not_execute(self))
    }

    fn _status(&self) -> io::Result<ExitStatus> {
        if !debug_force_argfile(self.retry_with_argfile) {
            let mut cmd = self.build_command();
            match cmd.spawn() {
                Err(ref e) if self.should_retry_with_argfile(e) => {}
                Err(e) => return Err(e),
                Ok(mut child) => return child.wait(),
            }
        }
        let (mut cmd, argfile) = self.build_command_with_argfile()?;
        let status = cmd.spawn()?.wait();
        close_tempfile_and_log_error(argfile);
        status
    }

    /// Runs the process, waiting for completion, and mapping non-success exit codes to an error.
    pub fn exec(&self) -> Result<()> {
        let exit = self.status()?;
        if exit.success() {
            Ok(())
        } else {
            Err(ProcessError::new(
                &format!("process didn't exit successfully: {}", self),
                Some(exit),
                None,
            )
            .into())
        }
    }

    /// Replaces the current process with the target process.
    ///
    /// On Unix, this executes the process using the Unix syscall `execvp`, which will block
    /// this process, and will only return if there is an error.
    ///
    /// On Windows this isn't technically possible. Instead we emulate it to the best of our
    /// ability. One aspect we fix here is that we specify a handler for the Ctrl-C handler.
    /// In doing so (and by effectively ignoring it) we should emulate proxying Ctrl-C
    /// handling to the application at hand, which will either terminate or handle it itself.
    /// According to Microsoft's documentation at
    /// <https://docs.microsoft.com/en-us/windows/console/ctrl-c-and-ctrl-break-signals>.
    /// the Ctrl-C signal is sent to all processes attached to a terminal, which should
    /// include our child process. If the child terminates then we'll reap them in Cargo
    /// pretty quickly, and if the child handles the signal then we won't terminate
    /// (and we shouldn't!) until the process itself later exits.
    pub fn exec_replace(&self) -> Result<()> {
        imp::exec_replace(self)
    }

    /// Like [`Command::output`] but with a better error message.
    pub fn output(&self) -> Result<Output> {
        self._output()
            .with_context(|| ProcessError::could_not_execute(self))
    }

    fn _output(&self) -> io::Result<Output> {
        if !debug_force_argfile(self.retry_with_argfile) {
            let mut cmd = self.build_command();
            match piped(&mut cmd, self.stdin.is_some()).spawn() {
                Err(ref e) if self.should_retry_with_argfile(e) => {}
                Err(e) => return Err(e),
                Ok(mut child) => {
                    if let Some(stdin) = &self.stdin {
                        child.stdin.take().unwrap().write_all(stdin)?;
                    }
                    return child.wait_with_output();
                }
            }
        }
        let (mut cmd, argfile) = self.build_command_with_argfile()?;
        let mut child = piped(&mut cmd, self.stdin.is_some()).spawn()?;
        if let Some(stdin) = &self.stdin {
            child.stdin.take().unwrap().write_all(stdin)?;
        }
        let output = child.wait_with_output();
        close_tempfile_and_log_error(argfile);
        output
    }

    /// Executes the process, returning the stdio output, or an error if non-zero exit status.
    pub fn exec_with_output(&self) -> Result<Output> {
        let output = self.output()?;
        if output.status.success() {
            Ok(output)
        } else {
            Err(ProcessError::new(
                &format!("process didn't exit successfully: {}", self),
                Some(output.status),
                Some(&output),
            )
            .into())
        }
    }

    /// Executes a command, passing each line of stdout and stderr to the supplied callbacks, which
    /// can mutate the string data.
    ///
    /// If any invocations of these function return an error, it will be propagated.
    ///
    /// If `capture_output` is true, then all the output will also be buffered
    /// and stored in the returned `Output` object. If it is false, no caching
    /// is done, and the callbacks are solely responsible for handling the
    /// output.
    pub fn exec_with_streaming(
        &self,
        on_stdout_line: &mut dyn FnMut(&str) -> Result<()>,
        on_stderr_line: &mut dyn FnMut(&str) -> Result<()>,
        capture_output: bool,
    ) -> Result<Output> {
        let mut stdout = Vec::new();
        let mut stderr = Vec::new();

        let mut callback_error = None;
        let mut stdout_pos = 0;
        let mut stderr_pos = 0;

        let spawn = |mut cmd| {
            if !debug_force_argfile(self.retry_with_argfile) {
                match piped(&mut cmd, false).spawn() {
                    Err(ref e) if self.should_retry_with_argfile(e) => {}
                    Err(e) => return Err(e),
                    Ok(child) => return Ok((child, None)),
                }
            }
            let (mut cmd, argfile) = self.build_command_with_argfile()?;
            Ok((piped(&mut cmd, false).spawn()?, Some(argfile)))
        };

        let status = (|| {
            let cmd = self.build_command();
            let (mut child, argfile) = spawn(cmd)?;
            let out = child.stdout.take().unwrap();
            let err = child.stderr.take().unwrap();
            read2(out, err, &mut |is_out, data, eof| {
                let pos = if is_out {
                    &mut stdout_pos
                } else {
                    &mut stderr_pos
                };
                let idx = if eof {
                    data.len()
                } else {
                    match data[*pos..].iter().rposition(|b| *b == b'\n') {
                        Some(i) => *pos + i + 1,
                        None => {
                            *pos = data.len();
                            return;
                        }
                    }
                };

                let new_lines = &data[..idx];

                for line in String::from_utf8_lossy(new_lines).lines() {
                    if callback_error.is_some() {
                        break;
                    }
                    let callback_result = if is_out {
                        on_stdout_line(line)
                    } else {
                        on_stderr_line(line)
                    };
                    if let Err(e) = callback_result {
                        callback_error = Some(e);
                        break;
                    }
                }

                if capture_output {
                    let dst = if is_out { &mut stdout } else { &mut stderr };
                    dst.extend(new_lines);
                }

                data.drain(..idx);
                *pos = 0;
            })?;
            let status = child.wait();
            if let Some(argfile) = argfile {
                close_tempfile_and_log_error(argfile);
            }
            status
        })()
        .with_context(|| ProcessError::could_not_execute(self))?;
        let output = Output {
            status,
            stdout,
            stderr,
        };

        {
            let to_print = if capture_output { Some(&output) } else { None };
            if let Some(e) = callback_error {
                let cx = ProcessError::new(
                    &format!("failed to parse process output: {}", self),
                    Some(output.status),
                    to_print,
                );
                bail!(anyhow::Error::new(cx).context(e));
            } else if !output.status.success() {
                bail!(ProcessError::new(
                    &format!("process didn't exit successfully: {}", self),
                    Some(output.status),
                    to_print,
                ));
            }
        }

        Ok(output)
    }

    /// Builds the command with an `@<path>` argfile that contains all the
    /// arguments. This is primarily served for rustc/rustdoc command family.
    fn build_command_with_argfile(&self) -> io::Result<(Command, NamedTempFile)> {
        use std::io::Write as _;

        let mut tmp = tempfile::Builder::new()
            .prefix("cargo-argfile.")
            .tempfile()?;

        let mut arg = OsString::from("@");
        arg.push(tmp.path());
        let mut cmd = self.build_command_without_args();
        cmd.arg(arg);
        tracing::debug!("created argfile at {} for {self}", tmp.path().display());

        let cap = self.get_args().map(|arg| arg.len() + 1).sum::<usize>();
        let mut buf = Vec::with_capacity(cap);
        for arg in &self.args {
            let arg = arg.to_str().ok_or_else(|| {
                io::Error::new(
                    io::ErrorKind::Other,
                    format!(
                        "argument for argfile contains invalid UTF-8 characters: `{}`",
                        arg.to_string_lossy()
                    ),
                )
            })?;
            if arg.contains('\n') {
                return Err(io::Error::new(
                    io::ErrorKind::Other,
                    format!("argument for argfile contains newlines: `{arg}`"),
                ));
            }
            writeln!(buf, "{arg}")?;
        }
        tmp.write_all(&mut buf)?;
        Ok((cmd, tmp))
    }

    /// Builds a command from `ProcessBuilder` for everything but not `args`.
    fn build_command_without_args(&self) -> Command {
        let mut command = {
            let mut iter = self.wrappers.iter().rev().chain(once(&self.program));
            let mut cmd = Command::new(iter.next().expect("at least one `program` exists"));
            cmd.args(iter);
            cmd
        };
        #[cfg(unix)]
        if let Some(arg0) = self.get_arg0() {
            use std::os::unix::process::CommandExt as _;
            command.arg0(arg0);
        }
        if let Some(cwd) = self.get_cwd() {
            command.current_dir(cwd);
        }
        for (k, v) in &self.env {
            match *v {
                Some(ref v) => {
                    command.env(k, v);
                }
                None => {
                    command.env_remove(k);
                }
            }
        }
        if let Some(ref c) = self.jobserver {
            c.configure(&mut command);
        }
        #[cfg(unix)]
        if !self.inherited_files.is_empty() {
            use std::os::fd::AsRawFd;
            use std::os::unix::process::CommandExt as _;

            let files = self.inherited_files.clone();
            // SAFETY: The captured files keep these descriptors open. After fork
            // this callback only inspects them and calls async-signal-safe fcntl;
            // it does not allocate or acquire locks. Spawning does not change
            // the parent descriptors; exec_replace restores them on failure.
            unsafe {
                command.pre_exec(move || {
                    for file in &files {
                        let fd = file.as_raw_fd();
                        let flags = libc::fcntl(fd, libc::F_GETFD);
                        if flags == -1
                            || libc::fcntl(fd, libc::F_SETFD, flags & !libc::FD_CLOEXEC) == -1
                        {
                            return Err(io::Error::last_os_error());
                        }
                    }
                    Ok(())
                });
            }
        }
        command
    }

    /// Converts `ProcessBuilder` into a `std::process::Command`, and handles
    /// the jobserver, if present.
    ///
    /// Note that this method doesn't take argfile fallback into account. The
    /// caller should handle it by themselves.
    pub fn build_command(&self) -> Command {
        let mut command = self.build_command_without_args();
        for arg in &self.args {
            command.arg(arg);
        }
        command
    }

    /// Wraps an existing command with the provided wrapper, if it is present and valid.
    ///
    /// # Examples
    ///
    /// ```rust
    /// use cargo_util::ProcessBuilder;
    /// // Running this would execute `rustc`
    /// let cmd = ProcessBuilder::new("rustc");
    ///
    /// // Running this will execute `sccache rustc`
    /// let cmd = cmd.wrapped(Some("sccache"));
    /// ```
    pub fn wrapped(mut self, wrapper: Option<impl AsRef<OsStr>>) -> Self {
        if let Some(wrapper) = wrapper.as_ref() {
            let wrapper = wrapper.as_ref();
            if !wrapper.is_empty() {
                self.wrappers.push(wrapper.to_os_string());
            }
        }
        self
    }
}

/// Forces the command to use `@path` argfile.
///
/// You should set `__CARGO_TEST_FORCE_ARGFILE` to enable this.
fn debug_force_argfile(retry_enabled: bool) -> bool {
    cfg!(debug_assertions) && env::var("__CARGO_TEST_FORCE_ARGFILE").is_ok() && retry_enabled
}

/// Creates new pipes for stderr, stdout, and optionally stdin.
fn piped(cmd: &mut Command, pipe_stdin: bool) -> &mut Command {
    cmd.stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .stdin(if pipe_stdin {
            Stdio::piped()
        } else {
            Stdio::null()
        })
}

fn close_tempfile_and_log_error(file: NamedTempFile) {
    file.close().unwrap_or_else(|e| {
        tracing::warn!("failed to close temporary file: {e}");
    });
}

#[cfg(unix)]
mod imp {
    use super::{ProcessBuilder, ProcessError, close_tempfile_and_log_error, debug_force_argfile};
    use anyhow::Result;
    use std::io;
    use std::os::fd::AsRawFd;
    use std::os::unix::process::CommandExt;

    pub fn exec_replace(process_builder: &ProcessBuilder) -> Result<()> {
        // Unlike spawn, exec runs pre_exec callbacks in this process. Restore
        // descriptor flags if replacement fails and the caller continues running.
        let file_flags = process_builder
            .inherited_files
            .iter()
            .map(|file| {
                // SAFETY: The builder keeps the descriptor alive.
                let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFD) };
                if flags == -1 {
                    Err(io::Error::last_os_error())
                } else {
                    Ok((file, flags))
                }
            })
            .collect::<io::Result<Vec<_>>>()?;
        let result = exec_replace_inner(process_builder);
        for (file, flags) in file_flags {
            // SAFETY: The builder keeps the descriptor alive, and these flags
            // were read from the same descriptor before attempting replacement.
            if unsafe { libc::fcntl(file.as_raw_fd(), libc::F_SETFD, flags) } == -1 {
                return Err(io::Error::last_os_error().into());
            }
        }
        result
    }

    fn exec_replace_inner(process_builder: &ProcessBuilder) -> Result<()> {
        let mut error;
        let mut file = None;
        if debug_force_argfile(process_builder.retry_with_argfile) {
            let (mut command, argfile) = process_builder.build_command_with_argfile()?;
            file = Some(argfile);
            error = command.exec()
        } else {
            let mut command = process_builder.build_command();
            error = command.exec();
            if process_builder.should_retry_with_argfile(&error) {
                let (mut command, argfile) = process_builder.build_command_with_argfile()?;
                file = Some(argfile);
                error = command.exec()
            }
        }
        if let Some(file) = file {
            close_tempfile_and_log_error(file);
        }

        Err(anyhow::Error::from(error).context(ProcessError::new(
            &format!("could not execute process {}", process_builder),
            None,
            None,
        )))
    }

    pub fn command_line_too_big(err: &io::Error) -> bool {
        err.raw_os_error() == Some(libc::E2BIG)
    }
}

#[cfg(windows)]
mod imp {
    use super::{ProcessBuilder, ProcessError};
    use anyhow::Result;
    use std::io;
    use windows_sys::Win32::Foundation::{FALSE, TRUE};
    use windows_sys::Win32::System::Console::SetConsoleCtrlHandler;
    use windows_sys::core::BOOL;

    unsafe extern "system" fn ctrlc_handler(_: u32) -> BOOL {
        // Do nothing; let the child process handle it.
        TRUE
    }

    pub fn exec_replace(process_builder: &ProcessBuilder) -> Result<()> {
        unsafe {
            if SetConsoleCtrlHandler(Some(ctrlc_handler), TRUE) == FALSE {
                return Err(ProcessError::new("Could not set Ctrl-C handler.", None, None).into());
            }
        }

        // Just execute the process as normal.
        process_builder.exec()
    }

    pub fn command_line_too_big(err: &io::Error) -> bool {
        use windows_sys::Win32::Foundation::ERROR_FILENAME_EXCED_RANGE;
        err.raw_os_error() == Some(ERROR_FILENAME_EXCED_RANGE as i32)
    }
}

#[cfg(test)]
mod tests {
    use super::ProcessBuilder;
    use std::fs;

    #[test]
    fn argfile_build_succeeds() {
        let mut cmd = ProcessBuilder::new("echo");
        cmd.args(["foo", "bar"].as_slice());
        let (cmd, argfile) = cmd.build_command_with_argfile().unwrap();

        assert_eq!(cmd.get_program(), "echo");
        let cmd_args: Vec<_> = cmd.get_args().map(|s| s.to_str().unwrap()).collect();
        assert_eq!(cmd_args.len(), 1);
        assert!(cmd_args[0].starts_with("@"));
        assert!(cmd_args[0].contains("cargo-argfile."));

        let buf = fs::read_to_string(argfile.path()).unwrap();
        assert_eq!(buf, "foo\nbar\n");
    }

    #[test]
    fn argfile_build_fails_if_arg_contains_newline() {
        let mut cmd = ProcessBuilder::new("echo");
        cmd.arg("foo\n");
        let err = cmd.build_command_with_argfile().unwrap_err();
        assert_eq!(
            err.to_string(),
            "argument for argfile contains newlines: `foo\n`"
        );
    }

    #[test]
    fn argfile_build_fails_if_arg_contains_invalid_utf8() {
        let mut cmd = ProcessBuilder::new("echo");

        #[cfg(windows)]
        let invalid_arg = {
            use std::os::windows::prelude::*;
            std::ffi::OsString::from_wide(&[0x0066, 0x006f, 0xD800, 0x006f])
        };

        #[cfg(unix)]
        let invalid_arg = {
            use std::os::unix::ffi::OsStrExt;
            std::ffi::OsStr::from_bytes(&[0x66, 0x6f, 0x80, 0x6f]).to_os_string()
        };

        cmd.arg(invalid_arg);
        let err = cmd.build_command_with_argfile().unwrap_err();
        assert_eq!(
            err.to_string(),
            "argument for argfile contains invalid UTF-8 characters: `fo�o`"
        );
    }

    #[cfg(any(target_os = "linux", target_os = "macos"))]
    mod inherited_files {
        use super::ProcessBuilder;
        use std::env;
        use std::fs::{self, File};
        use std::os::fd::{AsRawFd, FromRawFd, RawFd};
        use std::os::unix::fs::{MetadataExt, PermissionsExt};
        use std::path::Path;
        use std::process::{Child, Stdio};
        use std::sync::Arc;
        use std::thread;
        use std::time::{Duration, Instant};

        const ROLE: &str = "__CARGO_UTIL_INHERITED_FILE_TEST_ROLE";
        const CHILD_TEST: &str = "process_builder::tests::inherited_files::child";

        struct ChildGuard(Child);

        impl ChildGuard {
            fn wait_until(&mut self, condition: impl Fn() -> bool) {
                let deadline = Instant::now() + Duration::from_secs(15);
                while !condition() {
                    assert!(self.0.try_wait().unwrap().is_none(), "child exited early");
                    assert!(Instant::now() < deadline, "child did not become ready");
                    thread::sleep(Duration::from_millis(10));
                }
            }

            fn wait_success(&mut self) {
                let deadline = Instant::now() + Duration::from_secs(15);
                loop {
                    if let Some(status) = self.0.try_wait().unwrap() {
                        assert!(status.success(), "child failed: {status}");
                        return;
                    }
                    assert!(Instant::now() < deadline, "child did not exit");
                    thread::sleep(Duration::from_millis(10));
                }
            }
        }

        impl Drop for ChildGuard {
            fn drop(&mut self) {
                let _ = self.0.kill();
                let _ = self.0.wait();
            }
        }

        fn descriptor_flags(fd: RawFd) -> libc::c_int {
            // SAFETY: fcntl only inspects the descriptor; an invalid one reports an error.
            let flags = unsafe { libc::fcntl(fd, libc::F_GETFD) };
            assert_ne!(flags, -1, "{}", std::io::Error::last_os_error());
            flags
        }

        fn descriptor_is_file(fd: RawFd, path: &Path) -> bool {
            let expected = fs::metadata(path).unwrap();
            let mut stat = std::mem::MaybeUninit::<libc::stat>::uninit();
            // SAFETY: stat points to writable storage. An inherited descriptor
            // that was closed during exec may since have been reused by libtest.
            if unsafe { libc::fstat(fd, stat.as_mut_ptr()) } != 0 {
                return false;
            }
            // SAFETY: fstat initialized stat on success.
            let stat = unsafe { stat.assume_init() };
            stat.st_dev as u64 == expected.dev() && stat.st_ino as u64 == expected.ino()
        }

        fn child_command(role: &str, directory: &Path, fd: RawFd) -> ProcessBuilder {
            let mut command = ProcessBuilder::new(env::current_exe().unwrap());
            command
                .args(&["--exact", CHILD_TEST, "--nocapture"])
                .env(ROLE, role)
                .env("__CARGO_UTIL_INHERITED_FILE_TEST_DIR", directory)
                .env("__CARGO_UTIL_INHERITED_FILE_TEST_FD", fd.to_string());
            command
        }

        #[test]
        fn lock_survives_builder_clones_parent_close_and_exec() {
            for mode in ["spawn", "argfile", "replace"] {
                let directory = tempfile::tempdir().unwrap();
                let path = directory.path().join("lock");
                let file = Arc::new(File::create(&path).unwrap());
                let fd = file.as_raw_fd();
                // SAFETY: fd is an open file descriptor held by file.
                assert_eq!(unsafe { libc::flock(fd, libc::LOCK_EX) }, 0);
                let original_flags = descriptor_flags(fd);
                assert_ne!(original_flags & libc::FD_CLOEXEC, 0);

                let mut builder = child_command(mode, directory.path(), fd);
                builder.inherit_file(Arc::clone(&file));
                let mut cloned = builder.clone();
                drop(builder);

                let (mut command, _argfile) = if mode == "argfile" {
                    let script = directory.path().join("read-argfile");
                    fs::write(
                        &script,
                        "#!/bin/sh\nfile=${1#@}\nset --\nwhile IFS= read -r arg; do\n  set -- \"$@\" \"$arg\"\ndone < \"$file\"\nexec \"$__CARGO_UTIL_INHERITED_FILE_TEST_EXE\" \"$@\"\n",
                    )
                    .unwrap();
                    fs::set_permissions(&script, fs::Permissions::from_mode(0o700)).unwrap();
                    cloned.program(&script).env(
                        "__CARGO_UTIL_INHERITED_FILE_TEST_EXE",
                        env::current_exe().unwrap(),
                    );
                    let (command, argfile) = cloned.build_command_with_argfile().unwrap();
                    (command, Some(argfile))
                } else {
                    (cloned.build_command(), None)
                };
                drop(cloned);
                command.stdin(Stdio::null());
                let mut child = ChildGuard(command.spawn().unwrap());
                drop(command);

                child.wait_until(|| directory.path().join("ready").exists());
                assert_eq!(descriptor_flags(fd), original_flags);
                let mut unrelated = ChildGuard(
                    child_command("unrelated", directory.path(), fd)
                        .build_command()
                        .spawn()
                        .unwrap(),
                );
                unrelated.wait_success();
                drop(file);

                let probe = File::open(&path).unwrap();
                // SAFETY: probe owns the descriptor. This must remain locked
                // after all parent owners of the inherited descriptor are gone.
                let result =
                    unsafe { libc::flock(probe.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) };
                assert_eq!(result, -1, "{mode}: child lost its inherited lock");
                assert_eq!(
                    std::io::Error::last_os_error().kind(),
                    std::io::ErrorKind::WouldBlock
                );

                fs::write(directory.path().join("release"), b"").unwrap();
                child.wait_success();
                // SAFETY: probe owns the descriptor and the child has exited.
                assert_eq!(
                    unsafe { libc::flock(probe.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
                    0,
                    "{mode}: exited child retained its lock"
                );
            }
        }

        #[test]
        fn failed_exec_replace_restores_descriptor_flags() {
            let directory = tempfile::tempdir().unwrap();
            let file = Arc::new(File::create(directory.path().join("lock")).unwrap());
            let mut command = child_command("failed-replace", directory.path(), file.as_raw_fd());
            command.inherit_file(file);
            let mut child = ChildGuard(command.build_command().spawn().unwrap());
            child.wait_success();
        }

        #[test]
        fn child() {
            let Ok(role) = env::var(ROLE) else {
                return;
            };
            let directory = env::var_os("__CARGO_UTIL_INHERITED_FILE_TEST_DIR").unwrap();
            let directory = Path::new(&directory);
            let fd: RawFd = env::var("__CARGO_UTIL_INHERITED_FILE_TEST_FD")
                .unwrap()
                .parse()
                .unwrap();
            if role == "unrelated" {
                assert!(!descriptor_is_file(fd, &directory.join("lock")));
                return;
            }
            assert!(descriptor_is_file(fd, &directory.join("lock")));
            assert_eq!(descriptor_flags(fd) & libc::FD_CLOEXEC, 0);

            if role == "replace" || role == "failed-replace" {
                // SAFETY: This test subprocess received ownership of fd across exec.
                let file = Arc::new(unsafe { File::from_raw_fd(fd) });
                if role == "replace" {
                    child_command("spawn", directory, fd)
                        .inherit_file(file)
                        .exec_replace()
                        .unwrap();
                    unreachable!("exec_replace returned successfully");
                }
                let flags = descriptor_flags(fd) | libc::FD_CLOEXEC;
                // SAFETY: file owns fd. This subprocess is isolated from the test runner.
                assert_eq!(unsafe { libc::fcntl(fd, libc::F_SETFD, flags) }, 0);
                assert!(
                    ProcessBuilder::new(directory.join("missing-executable"))
                        .inherit_file(Arc::clone(&file))
                        .exec_replace()
                        .is_err()
                );
                assert_eq!(descriptor_flags(fd), flags);
                return;
            }

            fs::write(directory.join("ready"), b"").unwrap();
            let deadline = Instant::now() + Duration::from_secs(15);
            while !directory.join("release").exists() {
                assert!(Instant::now() < deadline, "parent did not release child");
                thread::sleep(Duration::from_millis(10));
            }
        }
    }
}
