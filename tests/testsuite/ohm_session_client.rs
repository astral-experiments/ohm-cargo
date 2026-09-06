//! Compatibility of direct session clients with Cargo's full CLI.

#![cfg(unix)]

use std::ffi::{OsStr, OsString};
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::os::unix::ffi::{OsStrExt, OsStringExt};
use std::os::unix::net::UnixListener;
use std::process::{Command, Output};
use std::thread;
use std::time::Instant;

use crate::prelude::*;
use cargo_test_support::{project, sleep_ms, slow_cpu_multiplier};
use serde_json::{Value, json};

const STDOUT: &str = "\x1b[32mcheck output\x1b[0m\n";
const STDERR: &str = "\x1b[31mcheck diagnostic\x1b[0m\n";

/// Respond without running rustc, and retain the exact request for comparison.
fn exchange(mut command: Command, equals_socket: bool, returncode: i32) -> (Value, Output) {
    // Short paths avoid Unix socket limits, including long test names.
    let directory = tempfile::tempdir().unwrap();
    // The macOS CI filesystem rejects non-UTF-8 filenames.
    let socket_name = if cfg!(target_os = "macos") {
        OsStr::new("session.sock")
    } else {
        OsStr::from_bytes(b"session-\xff.sock")
    };
    let socket = directory.path().join(socket_name);
    let listener = UnixListener::bind(&socket).unwrap();
    listener.set_nonblocking(true).unwrap();
    let server = thread::spawn(move || {
        let timeout = slow_cpu_multiplier(30);
        let deadline = Instant::now() + timeout;
        let mut connection = loop {
            match listener.accept() {
                Ok((connection, _)) => break connection,
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    assert!(Instant::now() < deadline, "client did not connect");
                    sleep_ms(10);
                }
                Err(error) => panic!("could not accept client: {error}"),
            }
        };
        connection.set_nonblocking(false).unwrap();
        connection.set_read_timeout(Some(timeout)).unwrap();
        connection.set_write_timeout(Some(timeout)).unwrap();
        let mut frame = String::new();
        BufReader::new(&connection)
            .take(1024 * 1024 + 1)
            .read_line(&mut frame)
            .unwrap();
        let request: Value = serde_json::from_str(&frame).unwrap();
        let response = json!({
            "version": request["version"],
            "session": {
                "id": "client-test",
                "identity": request["identity"],
                "configuration": {"command": []},
            },
            "status": "complete",
            "error_kind": null,
            "pid": 42,
            "checks": 1,
            "preparations": 1,
            "command": request["command"],
            "plan_id": 1,
            "cached_plans": 1,
            "revision": 1,
            "reprepare_reason": null,
            "reuse_disabled_reason": null,
            "reused": true,
            "returncode": returncode,
            "elapsed_ms": 0.0,
            "stdout": STDOUT,
            "stderr": STDERR,
        });
        serde_json::to_writer(&mut connection, &response).unwrap();
        connection.write_all(b"\n").unwrap();
        request
    });
    if equals_socket {
        let mut arg = OsString::from("--socket=");
        arg.push(&socket);
        command.arg(arg);
    } else {
        command.arg("--socket").arg(socket);
    }
    let output = command.output().unwrap();
    let request = server.join().unwrap();
    (request, output)
}

#[cargo_test]
fn direct_clients_match_aliases_with_inherited_configuration() {
    let p = project()
        .file(
            ".cargo/config.toml",
            r#"
                [alias]
                client_check = "session check"
                client_status = "session status"
                client_stop = "session stop"

                [term]
                color = "always"
            "#,
        )
        .build();
    let directory_name = if cfg!(target_os = "macos") {
        OsStr::new("nested")
    } else {
        OsStr::from_bytes(b"nested-\xfe")
    };
    let cwd = p.root().join(directory_name);
    fs::create_dir(&cwd).unwrap();
    let cwd_bytes = cwd.canonicalize().unwrap().as_os_str().as_bytes().to_vec();

    for operation in ["check", "status", "stop"] {
        for (json_output, returncode) in [(false, 0), (true, 0), (false, 7), (true, 7)] {
            let command = |args: &str| {
                let mut cargo = p.cargo(args);
                cargo.cwd(&cwd).env_remove("CARGO_TERM_COLOR");
                if json_output {
                    cargo.arg("--json");
                }
                let mut command = cargo.build_command();
                command.env(
                    OsStr::from_bytes(b"SESSION_KEY_\xff"),
                    OsStr::from_bytes(b"value-\xfe"),
                );
                command
            };
            let (direct_request, direct) = exchange(
                command(&format!("session {operation}")),
                json_output,
                returncode,
            );
            let (alias_request, alias) = exchange(
                command(&format!("client_{operation}")),
                !json_output,
                returncode,
            );
            assert_eq!(direct_request, alias_request);
            assert_eq!(direct_request["command"], operation);
            assert_eq!(direct_request["identity"]["cwd"], json!(cwd_bytes));
            assert_eq!(direct.status.code(), Some(returncode), "{direct:?}");
            assert_eq!(direct.status, alias.status);
            assert_eq!(direct.stdout, alias.stdout);
            assert_eq!(direct.stderr, alias.stderr);
            if json_output {
                let response: Value = serde_json::from_slice(&direct.stdout).unwrap();
                assert_eq!(response["stdout"], STDOUT);
                assert_eq!(response["stderr"], STDERR);
                assert!(direct.stderr.is_empty());
            } else if operation == "check" || returncode != 0 {
                // The ancestor config controls output even on the direct path.
                assert_eq!(direct.stdout, STDOUT.as_bytes());
                assert_eq!(direct.stderr, STDERR.as_bytes());
            } else {
                assert!(direct.stdout.starts_with(b"{\n"));
                assert!(direct.stderr.is_empty());
            }
        }
    }

    let command = |value: u8| {
        let mut command = p.cargo("session status").cwd(&cwd).build_command();
        command.env("SESSION_RAW_VALUE", OsString::from_vec(vec![value]));
        command
    };
    let (before, _) = exchange(command(0xff), false, 0);
    let (after, _) = exchange(command(0xfe), false, 0);
    assert_ne!(
        before["identity"]["environment"],
        after["identity"]["environment"]
    );
}

#[cargo_test]
fn direct_clients_keep_config_errors_and_builtin_alias_warnings() {
    let p = project()
        .file("nested/placeholder", "")
        .file(
            ".cargo/config.toml",
            "[term]\nverbose = true\nquiet = true\n",
        )
        .build();
    let run = || {
        p.cargo("session status --socket missing.sock")
            .cwd(p.root().join("nested"))
            .env("CARGO_TERM_COLOR", "never")
            .env("__CARGO_TEST_CHANNEL_OVERRIDE_DO_NOT_USE_THIS", "nightly")
            .build_command()
            .output()
            .unwrap()
    };
    let output = run();
    assert_eq!(output.status.code(), Some(101), "{output:?}");
    assert!(
        String::from_utf8_lossy(&output.stderr)
            .contains("cannot set both `term.verbose` and `term.quiet`"),
        "{output:?}"
    );

    p.change_file(".cargo/config.toml", "[malformed\n");
    let output = run();
    assert_eq!(output.status.code(), Some(101), "{output:?}");
    assert!(
        String::from_utf8_lossy(&output.stderr).contains("could not parse TOML configuration"),
        "{output:?}"
    );

    p.change_file(".cargo/config.toml", "[alias]\nsession = 'check'\n");
    let output = run();
    assert_eq!(output.status.code(), Some(101), "{output:?}");
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        stderr.contains("user-defined alias `session` is ignored"),
        "{output:?}"
    );
    assert!(
        stderr.contains("could not connect to Cargo session at"),
        "{output:?}"
    );
}

#[cargo_test]
fn complex_client_arguments_keep_full_cli_diagnostics() {
    let p = project().build();
    for args in [
        "session status --json --json",
        "session status --socket",
        "session status --socket --json",
        "session status --json=true",
        "session status --socket=one --socket=two",
        "session status --unknown",
        "--offline session status",
        "session --offline status",
        "session status --offline",
        "session status --config net.offline=true",
    ] {
        let output = p.cargo(args).build_command().output().unwrap();
        assert!(!output.status.success(), "{args}: {output:?}");
        let stderr = String::from_utf8_lossy(&output.stderr);
        assert!(stderr.contains("error:"), "{args}: {output:?}");
        assert!(
            !stderr.contains("could not connect to Cargo session"),
            "{args}: {output:?}"
        );
    }
    let output = p
        .cargo("session status --help")
        .build_command()
        .output()
        .unwrap();
    assert!(output.status.success(), "{output:?}");
    assert!(
        String::from_utf8_lossy(&output.stdout).contains("--socket"),
        "{output:?}"
    );
}
