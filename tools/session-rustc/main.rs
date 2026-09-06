//! One fixed compiler invocation, with a fresh rustc session for every request.
#![feature(rustc_private)]
#![allow(dead_code)] // The shared protocol also contains Cargo's reader half.

extern crate rustc_driver;
extern crate rustc_session;

#[path = "../../src/cargo/util/session_worker/protocol/mod.rs"]
mod protocol;

use std::collections::BTreeSet;
use std::fs::{File, OpenOptions};
use std::io::{self, Read, Seek, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::os::unix::net::UnixStream;

#[cfg(not(target_os = "linux"))]
compile_error!("the initial compiler worker requires Linux executable-mapping validation");

unsafe extern "C" {
    fn dup2(old: i32, new: i32) -> i32;
    fn fcntl(fd: i32, command: i32, value: i32) -> i32;
}

fn identity() -> protocol::Identity {
    protocol::Identity {
        compiler: env!("SESSION_WORKER_COMPILER").to_owned(),
        compiler_sha256: env!("SESSION_WORKER_COMPILER_SHA256").to_owned(),
        driver: env!("SESSION_WORKER_DRIVER").to_owned(),
        driver_sha256: env!("SESSION_WORKER_DRIVER_SHA256").to_owned(),
        sysroot: env!("SESSION_WORKER_SYSROOT").to_owned(),
        verbose_version: env!("SESSION_WORKER_VERBOSE_VERSION").to_owned(),
    }
}

/// Track native code loaded since startup. rustc deliberately leaks proc-macro
/// dylibs, which can retain arbitrary state even after its Session is dropped.
fn executable_mappings() -> io::Result<BTreeSet<(u64, u64, u64)>> {
    let maps = std::fs::read_to_string("/proc/self/maps")?;
    Ok(maps
        .lines()
        .filter_map(|line| {
            let mut fields = line.split_whitespace();
            let _address = fields.next()?;
            let permissions = fields.next()?;
            let _offset = fields.next()?;
            let device = fields.next()?;
            let inode = fields.next()?;
            if !permissions.contains('x') || inode == "0" {
                return None;
            }
            let (major, minor) = device.split_once(':')?;
            Some((
                u64::from_str_radix(major, 16).ok()?,
                u64::from_str_radix(minor, 16).ok()?,
                inode.parse().ok()?,
            ))
        })
        .collect())
}

/// Decode Linux's device number into the major/minor fields in `/proc/self/maps`.
fn file_mapping(path: &str) -> io::Result<(u64, u64, u64)> {
    let metadata = std::fs::metadata(path)?;
    let device = metadata.dev();
    let major = ((device >> 8) & 0xfff) | ((device >> 32) & 0xfffff000);
    let minor = (device & 0xff) | ((device >> 12) & 0xffffff00);
    Ok((major, minor, metadata.ino()))
}

/// Use unlinked private files, so each response carries exact channel lengths.
/// These are output buffers, never Cargo's package or build locks.
fn output_file(channel: &str) -> io::Result<File> {
    let mut random = [0; 16];
    File::open("/dev/urandom")?.read_exact(&mut random)?;
    let name = format!(
        "cargo-rustc-worker-{}-{channel}-{random:x?}",
        std::process::id()
    );
    let path = std::env::temp_dir().join(name);
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&path)?;
    std::fs::remove_file(path)?;
    Ok(file)
}

fn output(file: &mut File, remaining: &mut usize) -> io::Result<Vec<u8>> {
    file.rewind()?;
    let mut bytes = Vec::new();
    file.take(*remaining as u64 + 1).read_to_end(&mut bytes)?;
    if bytes.len() > *remaining {
        return Err(io::Error::other(
            "compiler worker output exceeds 8388608 bytes",
        ));
    }
    *remaining -= bytes.len();
    Ok(bytes)
}

fn serve() -> io::Result<()> {
    let mut args = std::env::args();
    let _worker = args.next();
    let fd: i32 = args
        .next()
        .and_then(|arg| arg.strip_prefix("--cargo-session-fd=").map(str::to_owned))
        .and_then(|fd| fd.parse().ok())
        .ok_or_else(|| io::Error::other("expected the private Cargo control descriptor"))?;
    if fd <= 2 || args.next().as_deref() != Some("--") {
        return Err(io::Error::other("invalid compiler worker invocation"));
    }
    // SAFETY: Cargo gives this process sole ownership of the inherited endpoint.
    let mut control = unsafe { UnixStream::from_raw_fd(fd) };
    // SAFETY: Linux F_SETFD=2 and FD_CLOEXEC=1; compiler children must not
    // inherit Cargo's private control channel.
    if unsafe { fcntl(fd, 2, 1) } < 0 {
        return Err(io::Error::last_os_error());
    }
    let identity = identity();
    let mut compiler_args = vec![identity.compiler.clone()];
    compiler_args.extend(args);
    // Moving the driver executable must not change rustc's inferred sysroot.
    compiler_args.extend(["--sysroot".to_owned(), identity.sysroot.clone()]);

    let early =
        rustc_session::EarlyDiagCtxt::new(rustc_session::config::ErrorOutputType::default());
    rustc_driver::init_rustc_env_logger(&early);
    rustc_driver::install_ice_hook(rustc_driver::DEFAULT_BUG_REPORT_URL, |_| {});
    rustc_driver::install_ctrlc_handler();
    let mappings = executable_mappings()?;
    if !mappings.contains(&file_mapping(&identity.driver)?) {
        return Err(io::Error::other(
            "loaded compiler driver does not match the selected installation",
        ));
    }
    let mut stdout = output_file("stdout")?;
    let mut stderr = output_file("stderr")?;
    // SAFETY: these files remain open for the worker's lifetime; requests are serial.
    if unsafe { dup2(stdout.as_raw_fd(), 1) } < 0 || unsafe { dup2(stderr.as_raw_fd(), 2) } < 0 {
        return Err(io::Error::last_os_error());
    }
    protocol::write_identity(&mut control, &identity)?;
    loop {
        let mut request = [0];
        match control.read_exact(&mut request) {
            Err(error) if error.kind() == io::ErrorKind::UnexpectedEof => return Ok(()),
            result => result?,
        }
        if request != [protocol::CHECK] {
            return Err(io::Error::other("invalid compiler worker request"));
        }
        for file in [&mut stdout, &mut stderr] {
            file.set_len(0)?;
            file.rewind()?;
        }
        let status = rustc_driver::catch_with_exit_code(|| {
            let mut callbacks = rustc_driver::TimePassesCallbacks::default();
            rustc_driver::run_compiler(&compiler_args, &mut callbacks);
        });
        io::stdout().flush()?;
        io::stderr().flush()?;
        let reusable = executable_mappings()? == mappings;
        let mut remaining = protocol::MAX_OUTPUT;
        let response = protocol::Response {
            code: u8::from(status != std::process::ExitCode::SUCCESS),
            reusable,
            stdout: output(&mut stdout, &mut remaining)?,
            stderr: output(&mut stderr, &mut remaining)?,
        };
        protocol::write_response(&mut control, &response)?;
        if !reusable {
            return Ok(());
        }
    }
}

fn main() -> std::process::ExitCode {
    match serve() {
        Ok(()) => std::process::ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("compiler worker: {error}");
            std::process::ExitCode::FAILURE
        }
    }
}
