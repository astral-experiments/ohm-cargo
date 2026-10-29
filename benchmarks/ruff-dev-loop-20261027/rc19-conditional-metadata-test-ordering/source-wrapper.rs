use std::env;
use std::ffi::OsStr;
use std::fs::{self, OpenOptions};
use std::io::{self, BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio, exit};
use std::thread;
use std::time::{Duration, Instant};

fn main() {
    let mut arguments = env::args_os().skip(1);
    let rustc = arguments.next().expect("rustc path");
    let arguments = arguments.collect::<Vec<_>>();
    let crate_name = arguments
        .windows(2)
        .find(|arguments| arguments[0] == OsStr::new("--crate-name"))
        .and_then(|arguments| arguments[1].to_str())
        .map(str::to_owned);
    let control = env::var_os("CONDITIONAL_PIPELINE_CONTROL").map(PathBuf::from);
    let phase = env::var("CONDITIONAL_PIPELINE_PHASE").ok();

    if let Some(path) = env::var_os("CONDITIONAL_PIPELINE_LOG")
        && let Some(crate_name) = &crate_name
        && crate_name != "___"
    {
        writeln!(
            OpenOptions::new()
                .create(true)
                .append(true)
                .open(path)
                .expect("wrapper log"),
            "{crate_name}"
        )
        .expect("write wrapper log");
    }

    if crate_name.as_deref() == Some("app")
        && let Some(control) = &control
        && phase.is_some()
    {
        if control.join("dependency-metadata").exists()
            && !control.join("dependency-finished").exists()
        {
            fs::write(control.join("parent-started-early"), b"ready")
                .expect("record early parent");
        }
        if control.join("middle-metadata").exists()
            && !control.join("middle-finished").exists()
        {
            fs::write(control.join("parent-started-before-middle-finish"), b"ready")
                .expect("record parent before intermediate completion");
        }
        fs::write(control.join("parent-started"), b"ready")
            .expect("record parent");
    }

    if crate_name.as_deref() == Some("middle")
        && let Some(control) = &control
        && phase.is_some()
    {
        if control.join("dependency-metadata").exists()
            && !control.join("dependency-finished").exists()
        {
            fs::write(control.join("middle-started-early"), b"ready")
                .expect("record early intermediate");
        }
        fs::write(control.join("middle-started"), b"ready")
            .expect("record intermediate");
    }

    let arguments = arguments.into_iter().filter(|argument| {
        !matches!(
            argument.to_str(),
            Some(
                "-Zpublic-api-hash"
                    | "-Zpublic-api-hash=no"
                    | "-Zcache-proc-macros"
                    | "-Zcache-proc-macros=no"
            )
        )
    });
    let mut child = Command::new(rustc)
        .args(arguments)
        .stdout(Stdio::inherit())
        .stderr(Stdio::piped())
        .spawn()
        .expect("rustc should start");
    let stderr = child.stderr.take().expect("rustc stderr");

    for line in BufReader::new(stderr).lines() {
        let line = line.expect("read rustc stderr");
        if line.contains("\"artifact\":")
            && line.contains(".rmeta")
            && let Some(prefix) = line.strip_suffix('}')
        {
            let public_api_hash = if matches!(
                phase.as_deref(),
                Some("changed" | "failure" | "committed-failure")
            ) && (crate_name.as_deref() == Some("dep")
                || (crate_name.as_deref() == Some("middle")
                    && env::var_os("CONDITIONAL_PIPELINE_CHANGE_MIDDLE").is_some()))
            {
                "11111111111111111111111111111111"
            } else {
                "00000000000000000000000000000000"
            };
            eprintln!(
                "{prefix},\"public_api_hash\":{{\"version\":1,\
                 \"value\":\"{public_api_hash}\"}}}}"
            );
            io::stderr().flush().expect("flush metadata notification");

            if crate_name.as_deref() == Some("dep")
                && let Some(control) = &control
                && let Some(phase) = &phase
            {
                fs::write(control.join("dependency-metadata"), b"ready")
                    .expect("record dependency metadata");
                if phase == "unchanged" {
                    thread::sleep(Duration::from_millis(150));
                } else {
                    let expected = if phase == "committed-failure" {
                        PathBuf::from(
                            env::var_os("CONDITIONAL_PIPELINE_PARENT_FINGERPRINT")
                                .expect("parent fingerprint path"),
                        )
                    } else if env::var_os("CONDITIONAL_PIPELINE_WAIT_FOR")
                        .as_deref()
                        == Some(OsStr::new("middle"))
                    {
                        control.join("middle-started")
                    } else {
                        control.join("parent-started")
                    };
                    let deadline = Instant::now() + Duration::from_secs(5);
                    while !fs::metadata(&expected)
                        .is_ok_and(|metadata| metadata.len() != 0)
                        && Instant::now() < deadline
                    {
                        thread::sleep(Duration::from_millis(5));
                    }
                    if !fs::metadata(&expected)
                        .is_ok_and(|metadata| metadata.len() != 0)
                    {
                        fs::write(control.join("parent-timed-out"), b"timeout")
                            .expect("record timeout");
                    }
                    if matches!(phase.as_str(), "failure" | "committed-failure") {
                        let _ = child.kill();
                        let _ = child.wait();
                        fs::write(control.join("dependency-failed"), b"failed")
                            .expect("record dependency failure");
                        exit(1);
                    }
                }
            } else if crate_name.as_deref() == Some("middle")
                && let Some(control) = &control
                && env::var_os("CONDITIONAL_PIPELINE_HOLD_MIDDLE").is_some()
            {
                fs::write(control.join("middle-metadata"), b"ready")
                    .expect("record intermediate metadata");
                thread::sleep(Duration::from_millis(150));
            }
        } else {
            eprintln!("{line}");
        }
    }

    let status = child.wait().expect("rustc should finish");
    if crate_name.as_deref() == Some("dep")
        && let Some(control) = &control
        && phase.is_some()
    {
        fs::write(control.join("dependency-finished"), b"finished")
            .expect("record dependency completion");
    }
    if crate_name.as_deref() == Some("middle")
        && let Some(control) = &control
        && env::var_os("CONDITIONAL_PIPELINE_HOLD_MIDDLE").is_some()
    {
        fs::write(control.join("middle-finished"), b"finished")
            .expect("record intermediate completion");
    }
    exit(status.code().unwrap_or(1));
}
