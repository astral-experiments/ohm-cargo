//! Lab-only linker wrapper for a private GNU jobserver and an unchanged Wild.
use std::env;
use std::ffi::OsStr;
use std::fs;
use std::io;
use std::os::unix::ffi::OsStrExt;
use std::process::{Command, ExitCode};

fn run() -> io::Result<ExitCode> {
    // The caller creates this private jobserver, marks its two FDs inheritable,
    // and retains both pipe ends for the lifetime of the measured subprocess.
    let jobserver = unsafe { jobserver::Client::from_env() }
        .ok_or_else(|| io::Error::other("missing private jobserver"))?;
    let mut tokens = Vec::new();
    while let Some(token) = jobserver.try_acquire()? {
        tokens.push(token);
        if tokens.len() == 15 {
            break;
        }
    }
    let width = tokens.len() + 1;
    let argv: Vec<_> = env::args_os().skip(1).collect();
    let mut receipt = Vec::new();
    for arg in &argv {
        receipt.extend_from_slice(arg.as_os_str().as_bytes());
        receipt.push(0);
    }
    fs::write(env::var_os("OHM_PROBE_ARGV").expect("isolated receipt path"), receipt)?;
    if argv.iter().any(|arg| arg == OsStr::new("--") || arg.to_string_lossy().contains("threads")) {
        return Err(io::Error::other("unexpected width override"));
    }
    let status = Command::new(env::var_os("OHM_PROBE_WILD").expect("exact stock binary"))
        .arg(format!("--threads={width}"))
        .args(argv)
        .status()?;
    drop(tokens);
    fs::write(env::var_os("OHM_PROBE_WIDTH").expect("isolated receipt path"), width.to_string())?;
    Ok(ExitCode::from(status.code().unwrap_or(1) as u8))
}

fn main() -> io::Result<ExitCode> {
    run()
}
