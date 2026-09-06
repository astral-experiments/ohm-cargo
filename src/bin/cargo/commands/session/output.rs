//! Request-scoped capture of both Shell and direct process-descriptor writes.

use std::fmt;
use std::fs::File;
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};

const MAX_OUTPUT_BYTES: u64 = 8 * 1024 * 1024;

pub(super) struct CapturedOutput {
    pub stdout: String,
    pub stderr: String,
}

#[derive(Debug)]
pub(super) struct OutputLimitExceeded;

impl fmt::Display for OutputLimitExceeded {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "session output exceeds {MAX_OUTPUT_BYTES} bytes; run an ordinary cargo check to receive the complete output"
        )
    }
}

impl std::error::Error for OutputLimitExceeded {}

/// A serialized server may redirect process descriptors while executing Cargo.
/// Temporary files avoid pipe capacity deadlocks. Dropping an obsolete attempt
/// restores descriptors and discards all of that attempt's diagnostics.
pub(super) struct OutputCapture {
    stdout: File,
    stderr: File,
    saved_stdout: OwnedFd,
    saved_stderr: OwnedFd,
    active: bool,
}

impl OutputCapture {
    pub(super) fn start() -> io::Result<Self> {
        let mut capture = Self {
            stdout: tempfile::tempfile()?,
            stderr: tempfile::tempfile()?,
            saved_stdout: duplicate(libc::STDOUT_FILENO)?,
            saved_stderr: duplicate(libc::STDERR_FILENO)?,
            active: false,
        };
        io::stdout().flush()?;
        io::stderr().flush()?;
        capture.active = true;
        redirect(capture.stdout.as_raw_fd(), libc::STDOUT_FILENO)?;
        redirect(capture.stderr.as_raw_fd(), libc::STDERR_FILENO)?;
        Ok(capture)
    }

    fn restore(&mut self) -> io::Result<()> {
        if self.active {
            let flush_stdout = io::stdout().flush();
            let flush_stderr = io::stderr().flush();
            let stdout = redirect(self.saved_stdout.as_raw_fd(), libc::STDOUT_FILENO);
            let stderr = redirect(self.saved_stderr.as_raw_fd(), libc::STDERR_FILENO);
            self.active = stdout.is_err() || stderr.is_err();
            stdout?;
            stderr?;
            flush_stdout?;
            flush_stderr?;
        }
        Ok(())
    }

    pub(super) fn finish(mut self) -> cargo::CargoResult<CapturedOutput> {
        self.restore()?;
        read_output(&mut self.stdout, &mut self.stderr)
    }
}

fn read_output(stdout: &mut File, stderr: &mut File) -> cargo::CargoResult<CapturedOutput> {
    if stdout
        .metadata()?
        .len()
        .saturating_add(stderr.metadata()?.len())
        > MAX_OUTPUT_BYTES
    {
        return Err(OutputLimitExceeded.into());
    }
    fn read(file: &mut File, remaining: &mut u64) -> cargo::CargoResult<String> {
        file.seek(SeekFrom::Start(0))?;
        let mut bytes = Vec::new();
        file.take(*remaining + 1).read_to_end(&mut bytes)?;
        if bytes.len() as u64 > *remaining {
            return Err(OutputLimitExceeded.into());
        }
        *remaining -= bytes.len() as u64;
        Ok(String::from_utf8_lossy(&bytes).into_owned())
    }
    // Recheck while reading in case a subprocess still has a descriptor open.
    let mut remaining = MAX_OUTPUT_BYTES;
    Ok(CapturedOutput {
        stdout: read(stdout, &mut remaining)?,
        stderr: read(stderr, &mut remaining)?,
    })
}

impl Drop for OutputCapture {
    fn drop(&mut self) {
        let _ = self.restore();
    }
}

fn duplicate(fd: i32) -> io::Result<OwnedFd> {
    // SAFETY: fcntl duplicates a live standard descriptor without taking
    // ownership. CLOEXEC keeps the saved descriptor out of compiler children.
    let duplicate = unsafe { libc::fcntl(fd, libc::F_DUPFD_CLOEXEC, 3) };
    if duplicate < 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: this newly allocated descriptor has one owner.
    Ok(unsafe { OwnedFd::from_raw_fd(duplicate) })
}

fn redirect(source: i32, destination: i32) -> io::Result<()> {
    // SAFETY: both arguments are open descriptors owned by this request or
    // the process; dup2 atomically replaces only stdout or stderr here.
    if unsafe { libc::dup2(source, destination) } < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn capture_materialization_preserves_channels_and_rejects_oversized_output() {
        let mut stdout = tempfile::tempfile().unwrap();
        let mut stderr = tempfile::tempfile().unwrap();
        stdout.write_all(b"{\"message\":\"ok\"}\n").unwrap();
        stderr.write_all(b"warning: example\n").unwrap();
        let output = read_output(&mut stdout, &mut stderr).unwrap();
        assert_eq!(output.stdout, "{\"message\":\"ok\"}\n");
        assert_eq!(output.stderr, "warning: example\n");
        stdout.set_len(MAX_OUTPUT_BYTES).unwrap();
        let error = read_output(&mut stdout, &mut stderr).err().unwrap();
        assert!(error.is::<OutputLimitExceeded>());
    }
}
