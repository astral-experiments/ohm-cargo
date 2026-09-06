//! Tests for retaining Cargo's check state in a development session.

#![cfg(unix)]

use std::ffi::OsString;
use std::fs;
use std::io::{BufRead, BufReader, Read, Seek, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::UnixStream;
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::{Child, Command, Output};
use std::time::Instant;

use crate::prelude::*;
use cargo_test_support::{Execs, Project, is_coarse_mtime, project, sleep_ms, slow_cpu_multiplier};
use serde_json::Value;

const MANIFEST: &str = r#"
    [package]
    name = "app"
    version = "0.1.0"
    edition = "2021"

    [workspace]
    members = ["dep"]
    resolver = "2"

    [dependencies]
    dep = { path = "dep" }

    [features]
    selected = []
    changed = []
"#;

fn fixture() -> Project {
    let p = project()
        .at("workspace with spaces")
        .file("Cargo.toml", MANIFEST)
        .file("src/lib.rs", "pub fn answer() -> u32 { dep::value() }")
        .file(
            "dep/Cargo.toml",
            r#"
                [package]
                name = "dep"
                version = "0.1.0"
                edition = "2021"
            "#,
        )
        .file("dep/src/lib.rs", "pub fn value() -> u32 { 1 }")
        .build();
    p.cargo("generate-lockfile --offline").run();
    p
}

fn change(p: &Project, path: &str, source: &str) {
    if is_coarse_mtime() {
        sleep_ms(1100);
    }
    p.change_file(path, source);
}

/// Capture client output in files so a broken server cannot fill a pipe or hang a test.
fn run_command(mut command: Command) -> Output {
    let mut stdout = tempfile::tempfile().unwrap();
    let mut stderr = tempfile::tempfile().unwrap();
    let mut child = command
        .stdout(stdout.try_clone().unwrap())
        .stderr(stderr.try_clone().unwrap())
        .spawn()
        .unwrap();
    let deadline = Instant::now() + slow_cpu_multiplier(30);
    let status = loop {
        if let Some(status) = child.try_wait().unwrap() {
            break status;
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            panic!("session client timed out: {command:?}");
        }
        sleep_ms(10);
    };
    stdout.rewind().unwrap();
    stderr.rewind().unwrap();
    let mut output = Output {
        status,
        stdout: Vec::new(),
        stderr: Vec::new(),
    };
    stdout.read_to_end(&mut output.stdout).unwrap();
    stderr.read_to_end(&mut output.stderr).unwrap();
    output
}

struct Session<'a> {
    project: &'a Project,
    socket: PathBuf,
    log: PathBuf,
    child: Option<Child>,
    environment: Vec<(String, OsString)>,
    _directory: tempfile::TempDir,
}

impl<'a> Session<'a> {
    fn start(project: &'a Project, flags: &[&str]) -> Self {
        Self::start_with_env(project, flags, &[])
    }

    fn start_with_env(
        project: &'a Project,
        flags: &[&str],
        environment: &[(&str, OsString)],
    ) -> Self {
        Self::start_command(project, "session serve", flags, environment)
    }

    fn start_command(
        project: &'a Project,
        command: &str,
        flags: &[&str],
        environment: &[(&str, OsString)],
    ) -> Self {
        // Test roots include the full test name and can exceed Unix socket limits.
        let directory = tempfile::Builder::new()
            .prefix("cargo-session-test-")
            .tempdir()
            .unwrap();
        fs::set_permissions(directory.path(), fs::Permissions::from_mode(0o700)).unwrap();
        let socket = directory.path().join("server.sock");
        let log = directory.path().join("server.log");
        let stdout = fs::File::create(&log).unwrap();
        let stderr = stdout.try_clone().unwrap();
        let mut environment: Vec<_> = environment
            .iter()
            .map(|(key, value)| ((*key).to_owned(), value.clone()))
            .collect();
        if cfg!(target_os = "macos") {
            // Cargo adds system fallback directories when launching this test
            // binary. Keep those ambient trees out of the fixture's compiler
            // inputs; explicit test overrides below still take precedence.
            environment.insert(0, ("DYLD_FALLBACK_LIBRARY_PATH".into(), OsString::new()));
        }
        let mut command = project.cargo(&format!("{command} --offline -p app --lib"));
        command.args(flags).arg("--socket").arg(&socket);
        for (key, value) in &environment {
            command.env(key, value);
        }
        let child = command
            .build_command()
            .process_group(0)
            .stdout(stdout)
            .stderr(stderr)
            .spawn()
            .unwrap();
        let mut session = Self {
            project,
            socket,
            log,
            child: Some(child),
            environment,
            _directory: directory,
        };
        let deadline = Instant::now() + slow_cpu_multiplier(30);
        loop {
            if let Some(status) = session.child.as_mut().unwrap().try_wait().unwrap() {
                session.child = None;
                panic!("session server exited with {status}: {}", session.log());
            }
            if session.socket.exists()
                && run_command(session.command("status").build_command())
                    .status
                    .success()
            {
                return session;
            }
            assert!(
                Instant::now() < deadline,
                "session did not start: {}",
                session.log()
            );
            sleep_ms(10);
        }
    }

    fn log(&self) -> String {
        fs::read_to_string(&self.log).unwrap_or_default()
    }

    fn command(&self, command: &str) -> Execs {
        let mut cargo = self.project.cargo(&format!("session {command}"));
        cargo.arg("--socket").arg(&self.socket);
        for (key, value) in &self.environment {
            cargo.env(key, value);
        }
        cargo
    }

    fn json(&self, mut command: Execs, success: bool) -> Value {
        let output = run_command(command.arg("--json").build_command());
        assert_eq!(
            output.status.success(),
            success,
            "client: {output:?}\nserver: {}",
            self.log()
        );
        let response: Value = serde_json::from_slice(&output.stdout)
            .unwrap_or_else(|error| panic!("invalid session JSON: {error}: {output:?}"));
        assert_eq!(response["version"], 1, "{response}");
        if let Some(code) = response.get("returncode") {
            assert_eq!(code.as_i64(), output.status.code().map(i64::from));
        }
        response
    }

    fn check(&self, success: bool) -> Value {
        let response = self.json(self.command("check"), success);
        assert!(response["elapsed_ms"].is_number(), "{response}");
        assert!(response["stdout"].is_string(), "{response}");
        assert!(response["stderr"].is_string(), "{response}");
        response
    }

    fn stop(&mut self) {
        assert_eq!(self.json(self.command("stop"), true)["returncode"], 0);
        self.wait_for_exit();
    }

    fn wait_for_exit(&mut self) {
        let deadline = Instant::now() + slow_cpu_multiplier(10);
        loop {
            if let Some(status) = self.child.as_mut().unwrap().try_wait().unwrap() {
                self.child = None;
                assert!(status.success(), "{}", self.log());
                assert!(!self.socket.exists());
                return;
            }
            assert!(Instant::now() < deadline, "session did not stop");
            sleep_ms(10);
        }
    }
}

impl Drop for Session<'_> {
    fn drop(&mut self) {
        if let Some(mut child) = self.child.take() {
            // SAFETY: The unreaped child owns this process group, including any
            // compiler or build script still running when a test assertion fails.
            unsafe { libc::kill(-(child.id() as i32), libc::SIGKILL) };
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn assert_reused(response: &Value, prepared: &Value) {
    assert_eq!(response["pid"], prepared["pid"], "{response}");
    assert_eq!(response["session"], prepared["session"], "{response}");
    assert_eq!(
        response["preparations"], prepared["preparations"],
        "{response}"
    );
    assert_eq!(response["reused"], true, "{response}");
}

fn assert_reprepared(response: &Value, previous: &Value) {
    assert_eq!(response["pid"], previous["pid"]);
    assert_eq!(response["session"], previous["session"]);
    assert!(
        response["preparations"].as_u64().unwrap() > previous["preparations"].as_u64().unwrap(),
        "{response}"
    );
    assert_eq!(response["reused"], false, "{response}");
}

fn unit_graph_has_target(response: &Value, name: &str) -> bool {
    let graph: Value = serde_json::from_str(response["stdout"].as_str().unwrap()).unwrap();
    graph["units"]
        .as_array()
        .unwrap()
        .iter()
        .any(|unit| unit["target"]["name"] == name)
}

#[cargo_test]
fn repeated_checks_keep_options_and_recover_from_leaf_errors() {
    let p = fixture();
    p.change_file(
        "src/main.rs",
        "compile_error!(\"only the library was selected\");",
    );
    p.change_file(
        "src/lib.rs",
        r#"
            #[cfg(not(feature = "selected"))]
            compile_error!("the fixed feature selection was lost");
            pub fn answer() -> u32 { dep::value() }
        "#,
    );
    let mut session = Session::start(&p, &["--features", "selected"]);
    let initial = session.json(session.command("status"), true);
    assert_eq!(initial["checks"], 0);
    assert!(
        initial["session"]["id"]
            .as_str()
            .is_some_and(|id| !id.is_empty())
    );
    let command = initial["session"]["configuration"]["command"]
        .as_array()
        .unwrap();
    for expected in ["serve", "--lib", "--features", "selected"] {
        assert!(
            command.iter().any(|arg| arg.as_str() == Some(expected)),
            "{initial}"
        );
    }
    let first = session.check(true);
    assert_eq!(first["session"], initial["session"]);
    assert_eq!(first["checks"], 1);
    assert_eq!(first["preparations"], 1);
    assert_eq!(first["reused"], false);
    assert_reused(&session.check(true), &first);
    let ordinary = run_command(
        p.cargo("check --offline -p app --lib --features selected")
            .build_command(),
    );
    assert!(ordinary.status.success(), "{ordinary:?}");

    change(&p, "src/lib.rs", "pub fn answer() -> u32 { \"broken\" }");
    let broken = session.check(false);
    assert_reused(&broken, &first);
    assert!(
        broken["stderr"]
            .as_str()
            .unwrap()
            .contains("mismatched types")
    );
    change(
        &p,
        "src/lib.rs",
        "pub fn answer() -> u32 { dep::value() + 1 }",
    );
    assert_reused(&session.check(true), &first);
    let status = session.json(session.command("status"), true);
    assert_eq!(status["checks"], 4);
    assert_eq!(status["preparations"], first["preparations"]);
    session.stop();
}

#[cargo_test]
fn identical_manifest_replacement_keeps_the_prepared_plan() {
    let p = fixture();
    let session = Session::start(&p, &[]);
    let prepared = session.check(true);
    assert_reused(&session.check(true), &prepared);

    let replacement = p.root().join("replacement.toml");
    fs::write(&replacement, p.read_file("Cargo.toml")).unwrap();
    fs::rename(replacement, p.root().join("Cargo.toml")).unwrap();
    assert_reused(&session.check(true), &prepared);
}

#[cargo_test]
fn dependency_inputs_are_rechecked_with_the_retained_plan() {
    let p = fixture();
    p.change_file("dep/src/lib.rs", "include!(\"../../shared source.rs\");");
    p.change_file("shared source.rs", "pub fn value() -> u32 { 1 }");
    let session = Session::start(&p, &[]);
    let first = session.check(true);
    assert_reused(&session.check(true), &first);
    change(&p, "shared source.rs", "pub fn value() -> i32 { 1 }");
    let broken = session.check(false);
    assert_reused(&broken, &first);
    assert!(
        broken["stderr"]
            .as_str()
            .unwrap()
            .contains("mismatched types")
    );
    change(&p, "shared source.rs", "pub fn value() -> u32 { 2 }");
    assert_reused(&session.check(true), &first);
}

#[cargo_test]
fn build_scripts_recheck_changed_generated_inputs() {
    let p = fixture();
    p.change_file(
        "build.rs",
        r#"
            fn main() {
                println!("cargo:rerun-if-changed=build-input.rs");
                let out = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
                std::fs::copy("build-input.rs", out.join("generated.rs")).unwrap();
            }
        "#,
    );
    p.change_file("build-input.rs", "pub fn generated() -> u32 { 1 }");
    p.change_file(
        "src/lib.rs",
        r#"
            include!(concat!(env!("OUT_DIR"), "/generated.rs"));
            pub fn answer() -> u32 { generated() }
        "#,
    );
    let session = Session::start(&p, &[]);
    let first = session.check(true);
    assert_reused(&session.check(true), &first);
    change(&p, "build-input.rs", "pub fn generated() -> bool { true }");
    let broken = session.check(false);
    assert_reused(&broken, &first);
    assert!(
        broken["stderr"]
            .as_str()
            .unwrap()
            .contains("mismatched types")
    );
    change(&p, "build-input.rs", "pub fn generated() -> u32 { 2 }");
    assert_reused(&session.check(true), &first);
}

#[cargo_test]
fn procedural_macro_edits_recompile_the_selected_library() {
    let p = fixture();
    p.change_file(
        "dep/Cargo.toml",
        &format!(
            "{}\n[lib]\nproc-macro = true\n",
            p.read_file("dep/Cargo.toml")
        ),
    );
    let source = |expansion: &str| {
        format!(
            r#"
                extern crate proc_macro;
                #[proc_macro]
                pub fn value(_: proc_macro::TokenStream) -> proc_macro::TokenStream {{
                    {expansion:?}.parse().unwrap()
                }}
            "#
        )
    };
    p.change_file("dep/src/lib.rs", &source("1u32"));
    p.change_file("src/lib.rs", "pub fn answer() -> u32 { dep::value!() }");
    let session = Session::start(&p, &[]);
    let first = session.check(true);
    change(&p, "dep/src/lib.rs", &source("false"));
    let broken = session.check(false);
    assert_reused(&broken, &first);
    assert!(
        broken["stderr"]
            .as_str()
            .unwrap()
            .contains("mismatched types")
    );
    change(&p, "dep/src/lib.rs", &source("2u32"));
    assert_reused(&session.check(true), &first);
}

#[cargo_test]
fn client_drift_is_rejected_and_configuration_changes_reprepare() {
    let p = fixture();
    p.change_file(
        "src/lib.rs",
        r#"
            #![allow(unexpected_cfgs)]
            #[cfg(session_error)]
            compile_error!("the new configuration reached rustc");
            pub fn answer() -> u32 { dep::value() }
        "#,
    );
    let session = Session::start(&p, &[]);
    let first = session.check(true);
    for (name, value) in [
        ("RUSTFLAGS", "--cfg=session_error"),
        ("MAKEFLAGS", "FEATURE=two"),
    ] {
        let mut changed = session.command("check");
        changed.env(name, value);
        let rejected = session.json(changed, false);
        assert!(rejected.to_string().contains("environment"), "{rejected}");
    }
    let mut changed = session.command("check");
    changed.cwd("dep");
    let rejected = session.json(changed, false);
    assert!(
        rejected.to_string().contains("working directory"),
        "{rejected}"
    );
    assert_eq!(
        session.json(session.command("status"), true)["checks"],
        first["checks"]
    );

    change(
        &p,
        ".cargo/config.toml",
        "[build]\nrustflags = [\"--cfg=session_error\"]\n",
    );
    let broken = session.check(false);
    assert_reprepared(&broken, &first);
    assert!(
        broken["stderr"]
            .as_str()
            .unwrap()
            .contains("the new configuration reached rustc")
    );
    fs::remove_file(p.root().join(".cargo/config.toml")).unwrap();
    let fixed = session.check(true);
    assert_reprepared(&fixed, &broken);
    assert_reused(&session.check(true), &fixed);

    change(
        &p,
        ".cargo/config.toml",
        "include = [{ path = \"flags.toml\", optional = true }]\n",
    );
    let optional = session.check(true);
    assert_reprepared(&optional, &fixed);
    change(
        &p,
        ".cargo/flags.toml",
        "[build]\nrustflags = [\"--cfg=session_error\"]\n",
    );
    let included = session.check(false);
    assert_reprepared(&included, &optional);
    assert!(
        included["stderr"]
            .as_str()
            .unwrap()
            .contains("the new configuration reached rustc")
    );
    fs::remove_file(p.root().join(".cargo/flags.toml")).unwrap();
    let removed = session.check(true);
    assert_reprepared(&removed, &included);
    assert_reused(&session.check(true), &removed);

    p.change_file(
        ".cargo/config.toml",
        r#"
            [alias]
            a = "--offline b"
            b = "session check"
        "#,
    );
    let output = run_command(
        p.cargo("a")
            .arg("--socket")
            .arg(p.root().join("missing-session.sock"))
            .build_command(),
    );
    assert!(!output.status.success(), "{output:?}");
    assert!(
        String::from_utf8_lossy(&output.stderr)
            .contains("session clients accept only --socket and --json"),
        "{output:?}"
    );
}

#[cargo_test]
fn nested_server_aliases_preserve_configuration_across_preparations() {
    let p = fixture();
    p.change_file(
        ".cargo/config.toml",
        r#"
            [alias]
            outer = ["--config", "env.SESSION_ALIAS_OUTER='outer'", "middle"]
            middle = ["--config", "env.SESSION_ALIAS_MARKER='present'", "inner"]
            inner = ["session", "serve"]
        "#,
    );
    p.change_file(
        "src/lib.rs",
        r#"
            const _: [(); 5] = [(); env!("SESSION_ALIAS_OUTER").len()];
            const _: [(); 7] = [(); env!("SESSION_ALIAS_MARKER").len()];
            pub fn answer() -> u32 { dep::value() }
        "#,
    );
    let session = Session::start_command(&p, "outer", &[], &[]);
    let first = session.check(true);
    assert_reused(&session.check(true), &first);

    change(&p, "Cargo.toml", &MANIFEST.replace("0.1.0", "0.2.0"));
    let changed = session.check(true);
    assert_reprepared(&changed, &first);
    assert_reused(&session.check(true), &changed);
}

#[cargo_test]
fn manifest_and_workspace_membership_changes_reload_resolution() {
    let p = fixture();
    let manifest = MANIFEST.replace("members = [\"dep\"]", "members = [\"dep\", \"extras/*\"]");
    p.change_file("Cargo.toml", &manifest);
    p.change_file(
        "extras/one/Cargo.toml",
        "[package]\nname = \"one\"\nversion = \"0.1.0\"\nedition = \"2021\"\n",
    );
    p.change_file("extras/one/src/lib.rs", "");
    p.change_file(
        "src/lib.rs",
        r#"
            #[cfg(feature = "changed")]
            compile_error!("the new manifest feature reached rustc");
            pub fn answer() -> u32 { dep::value() }
        "#,
    );
    p.cargo("generate-lockfile --offline").run();
    let session = Session::start(&p, &[]);
    let first = session.check(true);
    change(
        &p,
        "Cargo.toml",
        &format!("{manifest}\ndefault = [\"changed\"]\n"),
    );
    let broken = session.check(false);
    assert_reprepared(&broken, &first);
    assert!(
        broken["stderr"]
            .as_str()
            .unwrap()
            .contains("the new manifest feature reached rustc")
    );
    change(&p, "Cargo.toml", &manifest);
    let fixed = session.check(true);
    assert_reprepared(&fixed, &broken);

    fs::create_dir(p.root().join("extras/empty")).unwrap();
    let empty = session.check(false);
    assert_eq!(empty["reused"], false);
    assert!(
        empty["stderr"]
            .as_str()
            .unwrap()
            .contains("extras/empty/Cargo.toml")
    );
    fs::remove_dir(p.root().join("extras/empty")).unwrap();
    let recovered = session.check(true);
    assert_reused(&session.check(true), &recovered);

    p.change_file(
        "extras/two/Cargo.toml",
        "[package]\nname = \"app\"\nversion = \"0.1.0\"\nedition = \"2021\"\n",
    );
    p.change_file("extras/two/src/lib.rs", "");
    let broken = session.check(false);
    assert_eq!(broken["reused"], false);
    assert!(
        broken["stderr"]
            .as_str()
            .unwrap()
            .contains("two packages named")
    );
    fs::remove_dir_all(p.root().join("extras/two")).unwrap();
    let fixed = session.check(true);
    assert_reused(&session.check(true), &fixed);
}

#[cargo_test]
fn new_implicit_targets_and_build_scripts_reload_the_plan() {
    let p = fixture();
    p.change_file(
        "src/lib.rs",
        r#"
            #![allow(unexpected_cfgs)]
            #[cfg(new_build_script)]
            compile_error!("the new build script ran");
            pub fn answer() -> u32 { dep::value() }
        "#,
    );
    let session = Session::start(&p, &["--bins"]);
    let first = session.check(true);
    p.change_file(
        "src/bin/added.rs",
        "fn main() { compile_error!(\"the new implicit binary was discovered\"); }",
    );
    let broken = session.check(false);
    assert_reprepared(&broken, &first);
    assert!(
        broken["stderr"]
            .as_str()
            .unwrap()
            .contains("the new implicit binary was discovered")
    );
    fs::remove_dir_all(p.root().join("src/bin")).unwrap();
    let fixed = session.check(true);
    assert_reprepared(&fixed, &broken);

    p.change_file(
        "build.rs",
        "fn main() { println!(\"cargo:rustc-cfg=new_build_script\"); }",
    );
    let broken = session.check(false);
    assert_reprepared(&broken, &fixed);
    assert!(
        broken["stderr"]
            .as_str()
            .unwrap()
            .contains("the new build script ran")
    );
    fs::remove_file(p.root().join("build.rs")).unwrap();
    let fixed = session.check(true);
    assert_reprepared(&fixed, &broken);
    assert_reused(&session.check(true), &fixed);
}

#[cargo_test]
fn sigterm_cleans_up_the_socket_and_releases_the_build_lock() {
    let p = fixture();
    let mut session = Session::start(&p, &[]);
    let first = session.check(true);
    assert_reused(&session.check(true), &first);
    let mut connection = UnixStream::connect(&session.socket).unwrap();
    connection
        .set_write_timeout(Some(slow_cpu_multiplier(5)))
        .unwrap();
    let capacity: libc::c_int = 4096;
    // SAFETY: the connection owns this socket, and the option points to a valid integer.
    assert_eq!(
        unsafe {
            libc::setsockopt(
                connection.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_SNDBUF,
                (&capacity as *const libc::c_int).cast(),
                std::mem::size_of_val(&capacity) as libc::socklen_t,
            )
        },
        0,
        "{}",
        std::io::Error::last_os_error()
    );
    // Exceeding the send buffer proves the server has started consuming this
    // incomplete frame before SIGTERM, without relying on a scheduling sleep.
    connection.write_all(&vec![b' '; 64 * 1024]).unwrap();
    let pid = session.child.as_ref().unwrap().id();
    // SAFETY: This unreaped child is the server started by this test.
    assert_eq!(unsafe { libc::kill(pid as i32, libc::SIGTERM) }, 0);
    session.wait_for_exit();
    let output = run_command(p.cargo("check --offline -p app --lib").build_command());
    assert!(output.status.success(), "{output:?}");
}

#[cargo_test]
fn relative_compiler_search_paths_allow_checks_without_retaining_a_plan() {
    let p = fixture();
    let mut path = std::env::var_os("PATH").unwrap();
    path.push(":.");
    let session = Session::start_with_env(
        &p,
        &[],
        &[("RUSTC", OsString::from("rustc")), ("PATH", path)],
    );
    let first = session.check(true);
    assert_eq!(first["reused"], false);
    assert_reprepared(&session.check(true), &first);
}

#[cargo_test]
fn explicit_compiler_path_is_authoritative_for_toolchain_reuse() {
    let mut rustup = Command::new("rustup");
    rustup.args(["which", "rustc"]);
    let output = run_command(rustup);
    assert!(output.status.success(), "{output:?}");
    let rustc = String::from_utf8(output.stdout).unwrap();
    let p = fixture();
    let session = Session::start_with_env(
        &p,
        &[],
        &[
            ("RUSTC", OsString::from(rustc.trim())),
            ("RUSTUP_TOOLCHAIN", OsString::from("stable")),
        ],
    );
    let first = session.check(true);
    assert_reused(&session.check(true), &first);
}

#[cargo_test]
fn registry_sources_prepare_afresh_after_the_cache_is_warm() {
    cargo_test_support::registry::Package::new("registry_dep", "1.0.0").publish();
    let p = fixture();
    p.change_file(
        "Cargo.toml",
        &MANIFEST.replace("[dependencies]", "[dependencies]\nregistry_dep = \"1\""),
    );
    p.cargo("check -p app --lib").run();
    let session = Session::start(&p, &[]);
    let first = session.check(true);
    let second = session.check(true);
    assert_reprepared(&second, &first);
    for response in [&first, &second] {
        assert!(
            response["reuse_disabled_reason"]
                .as_str()
                .is_some_and(|reason| reason.contains("source ")),
            "{response}"
        );
    }
}

#[cargo_test]
fn response_file_inputs_from_earlier_compiler_probes_prevent_reuse() {
    let p = fixture();
    p.change_file(
        "Cargo.toml",
        &MANIFEST.replace(
            "[dependencies]",
            "[target.'cfg(session_flag)'.dependencies]",
        ),
    );
    p.change_file(
        ".cargo/config.toml",
        r#"
            [build]
            rustflags = ["@flags"]

            [target.'cfg(session_flag)']
            rustflags = ["--cfg=session_flag"]
        "#,
    );
    p.change_file("flags", "--cfg=session_flag\n");
    let session = Session::start_with_env(
        &p,
        &["--unit-graph", "-Zunstable-options"],
        &[(
            "__CARGO_TEST_CHANNEL_OVERRIDE_DO_NOT_USE_THIS",
            OsString::from("nightly"),
        )],
    );
    let first = session.check(true);
    assert!(unit_graph_has_target(&first, "dep"), "{first}");
    assert_reprepared(&session.check(true), &first);

    p.change_file("flags", "");
    let changed = session.check(true);
    assert_reprepared(&changed, &first);
    assert!(!unit_graph_has_target(&changed, "dep"), "{changed}");
}

#[cargo_test]
fn named_custom_target_changes_reprepare_conditional_dependencies() {
    let p = fixture();
    p.change_file(
        "Cargo.toml",
        &MANIFEST.replace(
            "[dependencies]",
            r#"[target.'cfg(target_vendor = "before")'.dependencies]"#,
        ),
    );
    let mut target: Value = serde_json::from_str(cargo_test_support::target_spec_json()).unwrap();
    target["vendor"] = Value::from("before");
    p.change_file("targets/session-target.json", &target.to_string());
    let session = Session::start_with_env(
        &p,
        &[
            "--unit-graph",
            "-Zunstable-options",
            "--target",
            "session-target",
        ],
        &[
            (
                "__CARGO_TEST_CHANNEL_OVERRIDE_DO_NOT_USE_THIS",
                OsString::from("nightly"),
            ),
            ("RUSTC_BOOTSTRAP", OsString::from("1")),
            ("RUSTFLAGS", OsString::from("-Zunstable-options")),
            (
                "RUST_TARGET_PATH",
                p.root().join("targets").into_os_string(),
            ),
        ],
    );
    let first = session.check(true);
    assert!(unit_graph_has_target(&first, "dep"), "{first}");
    assert_reprepared(&session.check(true), &first);

    target["vendor"] = Value::from("after");
    p.change_file("targets/session-target.json", &target.to_string());
    let changed = session.check(true);
    assert_reprepared(&changed, &first);
    assert!(!unit_graph_has_target(&changed, "dep"), "{changed}");
}

#[cargo_test]
fn inherited_workspace_changes_reprepare_with_future_manifest_mtimes() {
    use cargo_test_support::paths::CargoPathExt;

    let workspace = r#"
        [workspace]
        members = ["../dep"]
        resolver = "2"

        [workspace.package]
        version = "0.1.0"
        edition = "2021"
    "#;
    let p = project()
        .at("app")
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                dep = { path = "../dep" }

                [workspace]
                resolver = "2"
            "#,
        )
        .file("src/lib.rs", "")
        .file(
            "../dep/Cargo.toml",
            r#"
                [package]
                name = "dep"
                version.workspace = true
                edition.workspace = true
                workspace = "../shared"
            "#,
        )
        .file("../dep/src/lib.rs", "")
        .file("../shared/Cargo.toml", workspace)
        .build();
    p.root().join("Cargo.toml").move_into_the_future();
    let session = Session::start_with_env(
        &p,
        &["--unit-graph", "-Zunstable-options"],
        &[(
            "__CARGO_TEST_CHANNEL_OVERRIDE_DO_NOT_USE_THIS",
            OsString::from("nightly"),
        )],
    );
    let assert_version = |response: &Value, version: &str| {
        let graph: Value = serde_json::from_str(response["stdout"].as_str().unwrap()).unwrap();
        let dependency = graph["units"]
            .as_array()
            .unwrap()
            .iter()
            .find(|unit| unit["target"]["name"] == "dep")
            .unwrap();
        assert!(
            dependency["pkg_id"].as_str().unwrap().ends_with(version),
            "{graph}"
        );
    };
    let first = session.check(true);
    assert_version(&first, "#0.1.0");
    assert_reused(&session.check(true), &first);

    change(
        &p,
        "../shared/Cargo.toml",
        &workspace.replace("0.1.0", "0.2.0"),
    );
    let updated = session.check(true);
    assert_reprepared(&updated, &first);
    assert_version(&updated, "#0.2.0");
    assert_reused(&session.check(true), &updated);
}

#[cargo_test]
fn invalid_protocol_requests_leave_the_session_usable() {
    let p = fixture();
    let session = Session::start(&p, &[]);
    let prepared = session.check(true);
    let mut oversized = vec![b' '; 1024 * 1024];
    oversized.push(b'\n');
    let requests = [
        ("malformed", b"{\n".to_vec(), None),
        (
            "version",
            b"{\"version\":999,\"command\":\"status\"}\n".to_vec(),
            Some("unsupported protocol version"),
        ),
        (
            "oversized",
            oversized,
            Some("session request exceeds 1048576 bytes"),
        ),
    ];
    for (case, request, message) in requests {
        let before = session.json(session.command("status"), true);
        let mut connection = UnixStream::connect(&session.socket).unwrap();
        connection
            .set_read_timeout(Some(slow_cpu_multiplier(5)))
            .unwrap();
        connection
            .set_write_timeout(Some(slow_cpu_multiplier(5)))
            .unwrap();
        connection.write_all(&request).unwrap();
        let mut line = String::new();
        BufReader::new(connection).read_line(&mut line).unwrap();
        let response: Value = serde_json::from_str(&line).unwrap();
        assert_eq!(response["version"], 1, "{case}: {response}");
        assert_eq!(response["status"], "rejected", "{case}: {response}");
        assert_eq!(response["error_kind"], "protocol", "{case}: {response}");
        assert_eq!(response["returncode"], 1, "{case}: {response}");
        if let Some(message) = message {
            assert!(
                response["stderr"].as_str().unwrap().contains(message),
                "{case}: {response}"
            );
        }
        let after = session.json(session.command("status"), true);
        for field in ["pid", "checks", "preparations", "session"] {
            assert_eq!(response[field], before[field], "{case}: {response}");
            assert_eq!(after[field], before[field], "{case}: {after}");
        }
        assert_reused(&session.check(true), &prepared);
    }
}
