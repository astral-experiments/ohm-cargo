use std::env;
use std::ffi::{OsStr, OsString};
use std::fs;
use std::io::{self, Write};
use std::os::unix::process::{CommandExt, ExitStatusExt};
use std::path::{Path, PathBuf};
#[cfg(target_os = "macos")]
use std::process::Command;
use std::process::{ExitStatus, Output};

#[cfg(target_os = "macos")]
use super::Entry;
#[cfg(target_os = "macos")]
use super::apple;
use super::declared;

#[cfg(target_os = "macos")]
fn cc(args: &[OsString]) -> Command {
    let mut command = Command::new("cc");
    command.args(args);
    command
}

fn exit_status(status: ExitStatus) -> i32 {
    if let Some(code) = status.code() {
        return code;
    }
    let signal = status
        .signal()
        .expect("terminated linker has a signal or exit code");
    // Forward a fatal linker signal to rustc just as a direct child process would.
    unsafe {
        libc::signal(signal, libc::SIG_DFL);
        libc::raise(signal);
    }
    128 + signal
}

pub fn run_if_driver() -> Option<i32> {
    let mut args = env::args_os();
    let alias = PathBuf::from(args.next()?);
    if !alias.is_absolute()
        || !matches!(
            alias.file_name()?.to_str()?,
            "ohm-link-cc" | "ohm-declared-cc"
        )
        || alias.parent()?.extension()? != "rlink-objects"
    {
        return None;
    }
    let args: Vec<_> = args.collect();
    let configured = alias.file_name()? == "ohm-declared-cc";
    let driver = if configured {
        Some(env::var_os(declared::DRIVER).unwrap_or_default())
    } else {
        None
    };
    if driver.as_deref() == Some(OsStr::new("")) {
        eprintln!("missing configured native linker");
        return Some(1);
    }
    if let Some(result) = checked(&alias, &args, driver.as_deref()) {
        return Some(match result {
            Ok(output) => {
                if io::stdout().lock().write_all(&output.stdout).is_err()
                    || io::stderr().lock().write_all(&output.stderr).is_err()
                {
                    1
                } else {
                    exit_status(output.status)
                }
            }
            Err(err) => {
                eprintln!("could not run cc: {err}");
                1
            }
        });
    }

    let mut command = declared::command(driver.as_deref().unwrap_or(OsStr::new("cc")), &args);
    let err = command.exec();
    eprintln!("could not run cc: {err}");
    Some(if err.kind() == io::ErrorKind::NotFound {
        127
    } else {
        126
    })
}

fn checked(alias: &Path, args: &[OsString], driver: Option<&OsStr>) -> Option<io::Result<Output>> {
    let objects = alias.parent()?;
    let mut outputs = args.windows(2).filter(|pair| pair[0] == "-o");
    let output = PathBuf::from(&outputs.next()?[1]);
    if outputs.next().is_some()
        || !output.is_absolute()
        || objects != output.with_extension("rlink-objects")
        || !fs::symlink_metadata(objects).ok()?.is_dir()
    {
        return None;
    }

    // A full compilation owns this directory; a link-only run authenticates the
    // retained objects through Cargo's .rlink manifest before invoking rustc.
    let mut codegen = Vec::new();
    for entry in fs::read_dir(objects).ok()? {
        let entry = entry.ok()?;
        let path = entry.path();
        if path.extension() == Some(OsStr::new("o")) {
            if !entry.file_type().ok()?.is_file() {
                return None;
            }
            codegen.push(path);
        }
    }
    if codegen.is_empty() {
        return None;
    }
    codegen.sort();
    #[cfg(target_os = "macos")]
    let codegen: Vec<_> = codegen.iter().map(PathBuf::as_path).collect();
    let mut symbols = args
        .iter()
        .map(Path::new)
        .filter(|p| p.file_name() == Some(OsStr::new("symbols.o")) && p.parent() != Some(objects));
    let tempdir = symbols.next()?.parent()?;
    if symbols.next().is_some()
        || tempdir.parent()? != output.parent()?
        || !tempdir
            .file_name()?
            .as_encoded_bytes()
            .starts_with(b"rustc")
        || !fs::symlink_metadata(tempdir).ok()?.is_dir()
    {
        return None;
    }

    if let Some(driver) = driver {
        return declared::checked(driver, args, &output, tempdir, objects);
    }
    #[cfg(not(target_os = "macos"))]
    return None;
    #[cfg(target_os = "macos")]
    {
        let cache = Entry::open(&objects.join("native-link")).ok()?;
        let command = cc(args);
        let prepare = || apple::prepare(&command, &output, tempdir, &codegen);
        let plan = prepare();
        let before = plan.as_ref().and_then(|p| p.inputs.snapshot().ok());
        if let Some(snapshot) = before
            && let Some(stderr) = cache.reuse(snapshot.action, &output).ok().flatten()
        {
            return Some(Ok(Output {
                status: ExitStatus::from_raw(0),
                stdout: vec![],
                stderr,
            }));
        }
        cache.invalidate().ok()?;
        let (plan, before) = (plan?, before?);
        if !plan.authorizes_cold() {
            return None;
        }
        let report_dir = tempfile::tempdir_in(tempdir).ok()?;
        let report = report_dir.path().join("inputs");
        let namespace = super::namespace::Guard::capture(&plan.inputs).ok()?;
        let result = cc(args).args(plan.report_args(&report)).output();

        if let Ok(child) = &result
            && child.status.success()
            && child.stdout.is_empty()
            && plan.cacheable_stderr(&child.stderr)
            && let Some(after) = prepare()
            && after.reconciles(&report, &output)
            && after.inputs.snapshot().ok() == Some(before)
            && namespace.unchanged()
        {
            let _ = cache.publish(before.action, &output, &child.stderr);
        }
        Some(result)
    }
}
