//! Exercise the session controller independently of the experimental compiler implementation.
#![cfg(unix)]

use std::fs;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

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

struct Session<'a> {
    project: &'a Project,
    compiler: Option<PathBuf>,
    initial: Option<String>,
    status: i32,
    host: u32,
}

impl<'a> Session<'a> {
    fn start(p: &'a Project, mock: bool) -> Self {
        Self::with_compiler(p, mock.then(compiler))
    }

    fn with_compiler(p: &'a Project, compiler: Option<PathBuf>) -> Self {
        let mut session = Self {
            project: p,
            compiler,
            initial: None,
            status: 0,
            host: 0,
        };
        let output = session.run("-Zohm-check-session start --lib --source src/edit.rs", &[]);
        session.host = output
            .split("workspace host pid=")
            .nth(1)
            .unwrap_or_else(|| panic!("{output}"))
            .split(';')
            .next()
            .unwrap()
            .parse()
            .unwrap();
        session.initial = Some(output);
        session
    }

    fn command(&self, args: &str) -> Command {
        let mut command = self
            .project
            .cargo(args)
            .masquerade_as_nightly_cargo(&["ohm-check-session"])
            .build_command();
        command.env("CARGO_LOG", "cargo::ops::check_session=debug");
        if let Some(compiler) = &self.compiler {
            command.env("RUSTC", compiler);
        }
        command
    }

    fn run(&mut self, args: &str, environment: &[(&str, Option<&str>)]) -> String {
        let mut command = self.command(args);
        for (key, value) in environment {
            if let Some(value) = value {
                command.env(key, value);
            } else {
                command.env_remove(key);
            }
        }
        let output = command.output().unwrap();
        self.status = output.status.code().unwrap();
        format!(
            "{}{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        )
    }

    fn response(&mut self) -> String {
        self.initial.take().unwrap()
    }
    fn check(&mut self) -> String {
        self.run("check --lib", &[])
    }
    fn stop(mut self) -> i32 {
        let output = self.run("stop", &[]);
        assert!(output.contains("stopped"), "{output}");
        assert!(self.workers().iter().all(|pid| !alive(*pid)));
        self.host = 0;
        self.status
    }
    fn workers(&self) -> Vec<u32> {
        fs::read_to_string(self.project.root().join("worker-starts"))
            .unwrap_or_default()
            .lines()
            .map(|line| line.parse().unwrap())
            .collect()
    }
}

impl Drop for Session<'_> {
    fn drop(&mut self) {
        if self.host != 0 {
            let _ = self.command("stop").output();
        }
    }
}

fn alive(pid: u32) -> bool {
    unsafe { libc::kill(pid as i32, 0) == 0 }
}
fn wait_for(mut ready: impl FnMut() -> bool) {
    let deadline = Instant::now() + Duration::from_secs(10);
    while !ready() {
        assert!(
            Instant::now() < deadline,
            "timed out waiting for session state"
        );
        std::thread::sleep(Duration::from_millis(20));
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
fn macro_validation_reuses_matching_expansion_and_discards_changed_or_failed_proofs() {
    let p = fixture();
    p.change_file("macro-output", "first");
    let mut session = Session::start(&p, true);
    assert!(session.response().contains("retained=true"));
    let output = session.check();
    assert!(output.contains("retained=true"), "{output}");
    assert_eq!(session.workers().len(), 1);

    p.change_file("macro-output", "second");
    assert!(
        session
            .check()
            .contains("running fresh check-session fallback")
    );
    assert_eq!(session.status, 0);
    assert!(session.check().contains("retained=true"));
    assert_eq!(session.workers().len(), 2);

    p.change_file("late-validator-diagnostic", "");
    let output = session.check();
    assert!(
        output.contains("running fresh check-session fallback"),
        "{output}"
    );
    assert!(!output.contains("discard this late diagnostic"), "{output}");
    assert_eq!(session.status, 0);
    fs::remove_file(p.root().join("late-validator-diagnostic")).unwrap();
    assert!(session.check().contains("retained=true"));

    p.change_file("failed-validator", "");
    assert!(
        session
            .check()
            .contains("running fresh check-session fallback")
    );
    assert_eq!(session.status, 0);
    let validators: Vec<u32> = fs::read_to_string(p.root().join("validator-starts"))
        .unwrap()
        .lines()
        .map(|line| line.parse().unwrap())
        .collect();
    assert_eq!(validators.len(), 4);
    assert!(validators.iter().all(|pid| !alive(*pid)));
    assert_eq!(session.stop(), 0);
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
    p.cargo("check --lib --no-session").run();
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
    assert_eq!(session.status, 101);
    assert_eq!(session.stop(), 0);
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

#[cargo_test]
fn environment_and_target_selection_belong_to_each_client() {
    let p = fixture();
    let mut session = Session::start(&p, true);
    session.response();
    p.change_file("src/lib.rs", "mod edit; const _: () = assert!(env!(\"SESSION_VALUE\").as_bytes()[0] == b'b'); pub fn value() -> u32 { edit::value() }");
    assert!(
        session
            .run("check --lib", &[("SESSION_VALUE", Some("a"))])
            .contains("evaluation")
    );
    assert_eq!(session.status, 101);
    assert!(
        !session
            .run("check --lib", &[("SESSION_VALUE", Some("b"))])
            .contains("error:")
    );
    assert_eq!(session.status, 0);
    assert!(
        session
            .run("check --lib", &[("SESSION_VALUE", None)])
            .contains("not defined")
    );
    assert_eq!(session.status, 101);
    assert_eq!(session.workers().len(), 4);
    p.change_file(
        "src/lib.rs",
        "mod edit; pub fn value() -> u32 { edit::value() }",
    );
    p.change_file("src/main.rs", "fn main() { let _: bool = foo::value(); }");
    // The default multi-target command uses normal Cargo, including producing library
    // metadata needed by the binary, even while a library-only session exists.
    assert!(session.run("check", &[]).contains("mismatched types"));
    assert_eq!(session.status, 101);
    assert_eq!(session.workers().len(), 4);
    assert!(!session.check().contains("error:"));
    assert_eq!(session.stop(), 0);
}

#[cargo_test]
fn concurrent_start_and_checks_share_one_host_and_worker() {
    let p = fixture();
    let mut session = Session::start(&p, true);
    session.response();
    let host = session.host;
    let output = session.run("-Zohm-check-session start --lib --source src/edit.rs", &[]);
    assert!(
        output.contains(&format!("workspace host pid={host};")),
        "{output}"
    );
    let mut first = session
        .command("check --lib")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let mut second = session
        .command("check --lib")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    assert!(first.wait().unwrap().success());
    assert!(second.wait().unwrap().success());
    assert_eq!(session.workers().len(), 1);
    assert_eq!(session.stop(), 0);
    p.cargo("stop")
        .with_stderr_contains("[..]Session not running")
        .run();
}

#[cargo_test]
fn disconnected_client_retires_the_worker_without_stopping_the_host() {
    let p = fixture();
    let mut session = Session::start(&p, true);
    session.response();
    let worker = session.workers()[0];
    p.change_file("pause", "");
    let mut client = session
        .command("check --lib")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    wait_for(|| p.root().join("checking").exists());
    client.kill().unwrap();
    client.wait().unwrap();
    wait_for(|| !alive(worker));
    assert!(alive(session.host));
    fs::remove_file(p.root().join("pause")).unwrap();
    assert!(!session.check().contains("error:"));
    assert_eq!(session.workers().len(), 2);
    assert_eq!(session.stop(), 0);
}

#[cargo_test]
fn terminated_and_killed_hosts_can_be_restarted() {
    let p = fixture();
    for signal in [libc::SIGTERM, libc::SIGKILL] {
        let mut session = Session::start(&p, true);
        session.response();
        let worker = *session.workers().last().unwrap();
        assert_eq!(unsafe { libc::kill(session.host as i32, signal) }, 0);
        wait_for(|| !alive(worker));
        // A dead host must never make an ordinary check appear successful.
        p.change_file("src/edit.rs", "pub(crate) fn value() -> u32 { false }");
        assert!(session.check().contains("mismatched types"));
        assert_eq!(session.status, 101);
        p.change_file("src/edit.rs", "pub(crate) fn value() -> u32 { 1 }");
        let mut restarted = Session::start(&p, true);
        assert_ne!(session.host, restarted.host);
        session.host = 0;
        assert!(!restarted.response().contains("error:"));
        assert_eq!(restarted.stop(), 0);
    }
}

#[cargo_test]
fn simultaneous_cold_starts_and_subdirectory_clients_share_the_workspace() {
    let p = fixture();
    let mut session = Session {
        project: &p,
        compiler: Some(compiler()),
        initial: None,
        status: 0,
        host: 0,
    };
    let args = "-Zohm-check-session start --lib --source src/edit.rs";
    let first = session
        .command(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let second = session
        .command(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    for child in [first, second] {
        let output = child.wait_with_output().unwrap();
        let stderr = String::from_utf8_lossy(&output.stderr);
        assert!(output.status.success(), "{stderr}");
        let host = stderr
            .split("workspace host pid=")
            .nth(1)
            .unwrap()
            .split(';')
            .next()
            .unwrap()
            .parse()
            .unwrap();
        if session.host != 0 {
            assert_eq!(session.host, host);
        }
        session.host = host;
    }
    let output = session
        .command("check --lib")
        .current_dir(p.root().join("src"))
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(session.workers().len(), 1);
    assert_eq!(session.stop(), 0);
}

#[cargo_test]
fn failed_start_can_be_repaired_and_stopping_one_workspace_does_not_stop_another() {
    let p = fixture();
    p.change_file("src/edit.rs", "pub(crate) fn value() -> u32 { false }");
    let mut first = Session::start(&p, true);
    assert!(first.response().contains("mismatched types"));
    assert_eq!(first.status, 101);
    p.change_file("src/edit.rs", "pub(crate) fn value() -> u32 { 1 }");
    assert!(!first.check().contains("error:"));
    assert_eq!(first.workers().len(), 1);
    let other = project()
        .at("other")
        .file("src/lib.rs", "mod edit;")
        .file("src/edit.rs", "pub fn value() -> u32 { 1 }")
        .build();
    let mut second = Session::start(&other, true);
    second.response();
    assert_ne!(first.host, second.host);
    assert_eq!(first.stop(), 0);
    assert!(alive(second.host));
    assert!(!second.check().contains("error:"));
    assert_eq!(second.workers().len(), 1);
    assert_eq!(second.stop(), 0);
}
