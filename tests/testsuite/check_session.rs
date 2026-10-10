//! Exercise the session controller independently of the experimental compiler implementation.
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, Stdio};
use std::sync::{Mutex, OnceLock, mpsc};
use std::time::Duration;

use crate::prelude::*;
use cargo_test_support::{Project, basic_manifest, paths, project};

fn compiler() -> PathBuf {
    static COMPILER: OnceLock<Mutex<Option<PathBuf>>> = OnceLock::new();
    let mut cached = COMPILER.get_or_init(|| Mutex::new(None)).lock().unwrap();
    if let Some(path) = &*cached {
        return path.clone();
    }
    let p = project()
        .at(paths::global_root().join("check-session-compiler"))
        .file(
            "Cargo.toml",
            &basic_manifest("check-session-compiler", "0.0.0"),
        )
        .file("src/main.rs", include_str!("check_session/mock_rustc.rs"))
        .build();
    p.cargo("build").run();
    let path = p.bin("check-session-compiler");
    *cached = Some(path.clone());
    path
}

struct Session {
    child: Child,
    lines: mpsc::Receiver<String>,
}

impl Session {
    fn start(p: &Project, mock: bool) -> Self {
        Self::with_compiler(p, mock.then(compiler))
    }

    fn with_compiler(p: &Project, compiler: Option<PathBuf>) -> Self {
        let mut command = p
            .cargo("-Zohm-check-session check --lib --session src/edit.rs")
            .masquerade_as_nightly_cargo(&["ohm-check-session"])
            .build_command();
        if let Some(compiler) = compiler {
            command.env("RUSTC", compiler);
        }
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let stderr = child.stderr.take().unwrap();
        let (sender, lines) = mpsc::channel();
        std::thread::spawn(move || {
            for line in BufReader::new(stderr).lines() {
                if sender.send(line.unwrap()).is_err() {
                    break;
                }
            }
        });
        Self { child, lines }
    }

    fn response(&mut self) -> String {
        let mut output = String::new();
        loop {
            let line = self
                .lines
                .recv_timeout(Duration::from_secs(120))
                .unwrap_or_else(|error| panic!("{error}: {output}"));
            output.push_str(&line);
            output.push('\n');
            if line.contains("press Enter to check again") {
                return output;
            }
        }
    }

    fn check(&mut self) -> String {
        self.child.stdin.as_mut().unwrap().write_all(b"\n").unwrap();
        self.response()
    }

    fn stop(mut self) -> i32 {
        self.child.stdin.take();
        self.child.wait().unwrap().code().unwrap()
    }
}

impl Drop for Session {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn fixture() -> Project {
    project()
        .file(
            "src/lib.rs",
            "mod edit; pub fn value() -> u32 { edit::value() }",
        )
        .file("src/edit.rs", "pub(crate) fn value() -> u32 { 1 }")
        .build()
}

#[cargo_test]
fn errors_repairs_and_private_outputs() {
    let p = fixture();
    let mut session = Session::start(&p, true);
    assert!(!session.response().contains("error:"));
    // A live worker must not keep Cargo's build locks, and a session must not publish metadata.
    assert!(
        !fs::read_dir(p.target_debug_dir().join("deps"))
            .unwrap()
            .any(|entry| entry
                .unwrap()
                .path()
                .extension()
                .is_some_and(|ext| ext == "rmeta"))
    );
    p.cargo("check --lib").run();
    p.change_file("src/edit.rs", "pub(crate) fn value() -> u32 { false }");
    assert!(session.check().contains("mismatched types"));
    p.change_file(
        "src/edit.rs",
        "pub(crate) fn value() -> u32 { let unused = 1; 2 }",
    );
    assert!(session.check().contains("unused variable"));
    p.change_file("src/edit.rs", "pub(crate) fn value() -> u32 { 3 }");
    let repaired = session.check();
    assert!(!repaired.contains("mismatched types") && !repaired.contains("unused variable"));
    assert_eq!(
        fs::read_to_string(p.root().join("worker-starts"))
            .unwrap()
            .lines()
            .count(),
        1
    );
    assert_eq!(session.stop(), 0);
    assert_eq!(
        fs::read_dir(p.build_dir().join(".ohm-check-sessions"))
            .unwrap()
            .count(),
        0
    );
    p.cargo("check --lib")
        .with_stderr_contains("[CHECKING] foo v0.0.1 [..]")
        .run();
}

#[cargo_test]
fn unsupported_protocol_discards_provisional_diagnostics() {
    let p = fixture();
    let mut session = Session::start(&p, true);
    session.response();
    p.change_file("decline", "");
    p.change_file("src/edit.rs", "pub(crate) fn value() -> u32 { false }");
    let output = session.check();
    assert!(output.contains("mismatched types"));
    assert!(!output.contains("discard this provisional diagnostic"));
    let scratch = fs::read_dir(p.build_dir().join(".ohm-check-sessions"))
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path();
    assert!(!fs::read_dir(scratch).unwrap().any(|entry| {
        entry
            .unwrap()
            .file_name()
            .to_string_lossy()
            .starts_with("worker-")
    }));
    assert_eq!(session.stop(), 101);
}

#[cargo_test]
fn fresh_fallback_and_configuration_repair() {
    let p = fixture();
    let mut session = Session::start(&p, false);
    assert!(!session.response().contains("error:"));
    p.change_file(
        ".cargo/config.toml",
        "[build]\nrustflags = ['--cfg', 'session_config']\n",
    );
    p.change_file("src/edit.rs", "#[cfg(session_config)] compile_error!(\"changed config was read\"); pub(crate) fn value() -> u32 { 1 }");
    assert!(session.check().contains("changed config was read"));
    p.change_file(".cargo/config.toml", "");
    p.change_file("src/edit.rs", "pub(crate) fn value() -> u32 { 2 }");
    assert!(!session.check().contains("changed config was read"));
    assert_eq!(session.stop(), 0);
}

#[cfg(unix)]
#[cargo_test]
fn changing_the_compiler_invalidates_even_when_its_version_is_unchanged() {
    let p = fixture();
    let path = p.root().join("compiler");
    fs::copy(compiler(), &path).unwrap();
    let mut session = Session::with_compiler(&p, Some(path.clone()));
    session.response();
    filetime::set_file_mtime(
        &path,
        filetime::FileTime::from_system_time(std::time::SystemTime::now() + Duration::from_secs(2)),
    )
    .unwrap();
    assert!(!session.check().contains("error:"));
    assert_eq!(
        fs::read_to_string(p.root().join("worker-starts"))
            .unwrap()
            .lines()
            .count(),
        2
    );
    assert_eq!(session.stop(), 0);
}
