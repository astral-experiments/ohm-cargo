#![cfg(unix)]

use crate::prelude::*;
use cargo_test_support::{Execs, Project, basic_manifest, project, rustc_host, rustc_host_env};
use std::fs;
use std::path::{Path, PathBuf};
#[cfg(target_os = "linux")]
use std::process::Stdio;
#[cfg(target_os = "linux")]
use std::time::{Duration, Instant};

// The slow compiler waits for a real test to run. This demonstrates overlap
// without asserting a wall-clock speedup or depending on compiler throughput.
fn wrapper() -> PathBuf {
    let p = project()
        .at("ready-wrapper")
        .file("Cargo.toml", &basic_manifest("ready-wrapper", "0.1.0"))
        .file(
            "src/main.rs",
            r#"
            use std::{env, fs, path::PathBuf, process::Command, thread,
                time::{Duration, Instant}};

            fn main() {
                let mut args = env::args_os().skip(1);
                let program = args.next().unwrap();
                let args: Vec<_> = args.collect();
                let slow = args.windows(2).any(|a| a[0] == "--crate-name" && a[1] == "z")
                    && args.iter().any(|a| a == "--test");
                let status = Command::new(program).args(args).status().unwrap();
                if slow {
                    if let Some(control) = env::var_os("READY_CONTROL") {
                        let control = PathBuf::from(control);
                        let mode = env::var("READY_MODE").unwrap();
                        if mode != "fallback" {
                            let marker = if mode == "build-failure" || mode == "signal" {
                                "active"
                            } else {
                                "a-timing"
                            };
                            let deadline = Instant::now() + Duration::from_secs(15);
                            while !control.join(marker).exists() {
                                assert!(Instant::now() < deadline, "ready test never started");
                                thread::sleep(Duration::from_millis(5));
                            }
                        }
                        if mode == "build-failure" {
                            eprintln!("intentional late compiler failure");
                            std::process::exit(1);
                        }
                        if mode == "signal" {
                            thread::sleep(Duration::from_secs(30));
                        }
                        fs::write(control.join("slow-finished"), "yes").unwrap();
                    }
                }
                std::process::exit(status.code().unwrap_or(1));
            }
            "#,
        )
        .build();
    p.cargo("-Zohm-defaults=no build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .run();
    p.bin("ready-wrapper")
}

fn fixture() -> Project {
    project()
        .file(
            "Cargo.toml",
            "[workspace]\nmembers = [\"a\", \"z\"]\nresolver = \"3\"\n",
        )
        .file("a/Cargo.toml", &basic_manifest("a", "0.1.0"))
        .file("z/Cargo.toml", &basic_manifest("z", "0.1.0"))
        .file(
            "a/src/lib.rs",
            r#"
            #[test]
            fn selected() {
                use std::io::Write;
                let control = std::path::PathBuf::from(std::env::var_os("READY_CONTROL").unwrap());
                let mode = std::env::var("READY_MODE").unwrap();
                let mut runs = std::fs::OpenOptions::new().create(true).append(true)
                    .open(control.join("runs")).unwrap();
                writeln!(runs, "a").unwrap();
                std::fs::write(control.join("a-timing"),
                    if control.join("slow-finished").exists() { "after" } else { "during" }).unwrap();
                if mode == "test-failure" { panic!("intentional test failure"); }
                if mode == "runtime" {
                    assert_eq!(std::env::var("READY_VALUE").unwrap(), "new");
                    let out = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
                    assert_eq!(std::fs::read_to_string(out.join("value")).unwrap(), "new");
                }
                if mode == "build-failure" || mode == "signal" {
                    let child = std::process::Command::new("sleep").arg("30").spawn().unwrap();
                    std::fs::write(control.join("descendant"), child.id().to_string()).unwrap();
                    std::fs::write(control.join("active"), std::process::id().to_string()).unwrap();
                    std::thread::sleep(std::time::Duration::from_secs(30));
                }
            }
            #[test]
            fn excluded() { panic!("the test filter was lost"); }
            "#,
        )
        .file("z/src/lib.rs", "#[test] fn selected() {}")
        .build()
}

fn command(p: &Project, wrapper: &Path, mode: &str) -> Execs {
    let mut cmd = p.cargo("test --workspace --lib -j2 -Zohm-defaults=no -Zohm-ready-tests");
    cmd.masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-ready-tests"])
        .env("RUSTC_WRAPPER", wrapper)
        .env("READY_CONTROL", p.root().join("control"))
        .env("READY_MODE", mode);
    cmd
}

fn seed(p: &Project, wrapper: &Path) {
    fs::create_dir(p.root().join("control")).unwrap();
    command(p, wrapper, "fallback").arg("--no-run").run();
    assert!(!p.root().join("control/runs").exists());
}

fn change(p: &Project, revision: usize) {
    fs::remove_dir_all(p.root().join("control")).unwrap();
    fs::create_dir(p.root().join("control")).unwrap();
    p.change_file(
        "z/src/lib.rs",
        &format!(
            r#"#[test] fn selected() {{
                assert_eq!({revision}, {revision});
                std::fs::write(std::path::Path::new(&std::env::var("READY_CONTROL").unwrap())
                    .join("z-ran"), "yes").unwrap();
            }}"#
        ),
    );
}

fn assert_run(p: &Project, timing: &str) {
    assert_eq!(
        fs::read_to_string(p.root().join("control/runs")).unwrap(),
        "a\n"
    );
    assert_eq!(
        fs::read_to_string(p.root().join("control/a-timing")).unwrap(),
        timing
    );
}

#[cargo_test]
fn overlaps_fresh_tests_and_preserves_opt_out_and_fallbacks() {
    let wrapper = wrapper();
    let p = fixture();
    seed(&p, &wrapper);
    for (revision, case) in ["enabled", "opt-out", "json", "runner", "target"]
        .iter()
        .enumerate()
    {
        change(&p, revision);
        let mut cmd = command(
            &p,
            &wrapper,
            if *case == "enabled" {
                "normal"
            } else {
                "fallback"
            },
        );
        match *case {
            "opt-out" => {
                cmd.arg("-Zohm-ready-tests=no");
            }
            "json" => {
                cmd.arg("--message-format=json");
            }
            "runner" => {
                cmd.env(
                    &format!("CARGO_TARGET_{}_RUNNER", rustc_host_env()),
                    &wrapper,
                );
            }
            "target" => {
                cmd.arg("--target").arg(rustc_host());
            }
            _ => {}
        }
        cmd.arg("--").arg("selected").run();
        assert_run(
            &p,
            if *case == "enabled" {
                "during"
            } else {
                "after"
            },
        );
        assert!(p.root().join("control/z-ran").exists());
    }
}

#[cargo_test]
fn early_failure_preserves_fail_fast_and_no_fail_fast() {
    let wrapper = wrapper();
    let p = fixture();
    seed(&p, &wrapper);
    for (revision, no_fail_fast) in [false, true].iter().enumerate() {
        change(&p, revision);
        let mut cmd = command(&p, &wrapper, "test-failure");
        if *no_fail_fast {
            cmd.arg("--no-fail-fast");
        }
        cmd.arg("--")
            .arg("selected")
            .with_status(101)
            .with_stdout_contains("[..]intentional test failure[..]")
            .run();
        assert_run(&p, "during");
        assert_eq!(p.root().join("control/z-ran").exists(), *no_fail_fast);
    }
}

#[cargo_test]
fn uses_current_runtime_inputs_and_ignores_disabled_binaries() {
    let wrapper = wrapper();
    let p = fixture();
    p.change_file("a/Cargo.toml", &format!(
        "{}\n[features]\noptional=[]\n[[bin]]\nname=\"a\"\npath=\"src/main.rs\"\n[[bin]]\nname=\"disabled\"\npath=\"src/disabled.rs\"\nrequired-features=[\"optional\"]\n",
        basic_manifest("a", "0.1.0")
    ));
    p.change_file(
        "a/src/disabled.rs",
        "compile_error!(\"disabled binary must not be built\");",
    );
    p.change_file("a/src/main.rs", "fn main() { print!(\"old\"); }");
    p.change_file("a/build.rs", "fn main() {}");
    p.change_file(
        "a/tests/runtime.rs",
        r#"
        #[test] fn selected() {
            let output = std::process::Command::new(env!("CARGO_BIN_EXE_a")).output().unwrap();
            assert!(output.status.success());
            assert_eq!(output.stdout, b"new");
            std::fs::write(std::path::Path::new(&std::env::var("READY_CONTROL").unwrap())
                .join("current-binary"), "yes").unwrap();
        }
    "#,
    );
    fs::create_dir(p.root().join("control")).unwrap();
    command(&p, &wrapper, "fallback")
        .arg("--tests")
        .arg("--no-run")
        .run();
    assert!(!p.root().join("control/runs").exists());
    p.change_file("a/src/main.rs", "fn main() { print!(\"new\"); }");
    p.change_file("a/build.rs", r#"fn main() {
        println!("cargo::rustc-env=READY_VALUE=new");
        std::fs::write(std::path::Path::new(&std::env::var("OUT_DIR").unwrap()).join("value"), "new").unwrap();
    }"#);
    change(&p, 1);
    command(&p, &wrapper, "runtime")
        .arg("--tests")
        .arg("--")
        .arg("selected")
        .run();
    assert_run(&p, "during");
    assert!(p.root().join("control/current-binary").exists());
}

#[cfg(target_os = "linux")]
fn assert_process_tree_stopped(p: &Project) {
    for name in ["active", "descendant"] {
        let pid = fs::read_to_string(p.root().join("control").join(name)).unwrap();
        let stat = fs::read_to_string(format!("/proc/{pid}/stat"));
        assert!(
            stat.is_err() || stat.unwrap().split_once(") ").unwrap().1.starts_with('Z'),
            "{name} process {pid} is still running"
        );
    }
}

#[cargo_test]
#[cfg(target_os = "linux")]
fn build_failure_cancels_the_active_test_and_descendants() {
    let wrapper = wrapper();
    let p = fixture();
    seed(&p, &wrapper);
    change(&p, 1);
    command(&p, &wrapper, "build-failure")
        .arg("--")
        .arg("selected")
        .with_status(101)
        .with_stderr_contains("[..]intentional late compiler failure[..]")
        .run();
    assert_run(&p, "during");
    assert_process_tree_stopped(&p);
}

#[cargo_test]
#[cfg(target_os = "linux")]
fn interrupt_cancels_the_active_test_and_descendants() {
    use std::os::unix::process::{CommandExt, ExitStatusExt};

    let wrapper = wrapper();
    let p = fixture();
    seed(&p, &wrapper);
    change(&p, 1);
    let mut cmd = command(&p, &wrapper, "signal");
    cmd.arg("--").arg("selected");
    let mut child = cmd
        .build_command()
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(fs::File::create(p.root().join("signal.log")).unwrap())
        .process_group(0)
        .spawn()
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(15);
    while !p.root().join("control/active").exists() {
        assert!(
            child.try_wait().unwrap().is_none() && Instant::now() < deadline,
            "test did not start: {}",
            fs::read_to_string(p.root().join("signal.log")).unwrap()
        );
        std::thread::sleep(Duration::from_millis(5));
    }
    // SAFETY: this is the isolated process group created for the test command.
    assert_eq!(unsafe { libc::kill(-(child.id() as i32), libc::SIGINT) }, 0);
    let status = loop {
        if let Some(status) = child.try_wait().unwrap() {
            break status;
        }
        assert!(
            Instant::now() < deadline,
            "Cargo did not handle interruption"
        );
        std::thread::sleep(Duration::from_millis(5));
    };
    assert!(status.signal() == Some(libc::SIGINT) || status.code() == Some(130));
    assert_process_tree_stopped(&p);
}
