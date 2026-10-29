use crate::prelude::*;
use cargo_test_support::{basic_manifest, project};
use std::fs;

// Keep the producer alive after metadata until its consumer finishes. This
// exercises Cargo's scheduler deterministically, without requiring patched rustc.
fn check_pipeline(producer_fails: bool, consumer_fails: bool, binary: bool) {
    let wrapper = project()
        .at("wrapper")
        .file("Cargo.toml", &basic_manifest("wrapper", "0.1.0"))
        .file(
            "src/main.rs",
            r#"
            use std::{env, fs, io::{BufRead, BufReader}, path::PathBuf,
                process::{Command, Stdio}, thread, time::{Duration, Instant}};
            fn main() {
                let mut args = env::args_os().skip(1);
                let rustc = args.next().unwrap();
                let args: Vec<_> = args.filter(|arg| arg != "-Zohm-early-metadata").collect();
                let name = args.windows(2).find(|a| a[0] == "--crate-name")
                    .map(|a| a[1].to_string_lossy().into_owned()).unwrap_or_default();
                let control = env::var_os("PIPELINE_CONTROL").map(PathBuf::from);
                let mut child = Command::new(rustc).args(args)
                    .stderr(Stdio::piped()).spawn().unwrap();
                for line in BufReader::new(child.stderr.take().unwrap()).lines() {
                    let line = line.unwrap();
                    eprintln!("{line}");
                    if name == "dep" && line.contains("\"artifact\":") && line.contains(".rmeta") {
                        if let Some(control) = &control {
                            let deadline = Instant::now() + Duration::from_secs(15);
                            while !control.join("consumer-finished").exists() {
                                assert!(Instant::now() < deadline, "consumer did not start early");
                                thread::sleep(Duration::from_millis(5));
                            }
                            fs::write(control.join("overlapped"), "yes").unwrap();
                        }
                    }
                }
                let status = child.wait().unwrap();
                if name == "app" {
                    if let Some(control) = &control {
                        fs::write(control.join("consumer-finished"), "yes").unwrap();
                    }
                }
                if name == "dep" && env::var_os("FAIL_PRODUCER").is_some() {
                    eprintln!("producer failed after metadata");
                    std::process::exit(1);
                }
                std::process::exit(status.code().unwrap_or(1));
            }
        "#,
        )
        .build();
    wrapper
        .cargo("-Zohm-defaults=no build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .run();
    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "app"
            version = "0.1.0"
            edition = "2024"
            [dependencies]
            middle = { path = "middle" }
        "#,
        )
        .file(
            if binary { "src/main.rs" } else { "src/lib.rs" },
            &format!(
                "{} {}",
                if consumer_fails {
                    "pub fn app() { downstream_missing(); middle::value(); }"
                } else {
                    "pub fn app() { middle::value(); } fn downstream_warning() {}"
                },
                if binary { "fn main() { app(); }" } else { "" },
            ),
        )
        .file(
            "middle/Cargo.toml",
            r#"
            [package]
            name = "middle"
            version = "0.1.0"
            edition = "2024"
            [dependencies]
            dep = { path = "../dep" }
        "#,
        )
        .file("middle/src/lib.rs", "pub fn value() { dep::value(); }")
        .file("dep/Cargo.toml", &basic_manifest("dep", "0.1.0"))
        .file("dep/src/lib.rs", "pub fn value() {}")
        .build();
    let mut check = p.cargo("-Zohm-defaults=no -Zheadstart check -j2 --keep-going");
    check
        .masquerade_as_nightly_cargo(&["ohm-defaults", "headstart"])
        .env("RUSTC_WRAPPER", wrapper.bin("wrapper"))
        .env("PIPELINE_CONTROL", p.root());
    if producer_fails {
        check
            .env("FAIL_PRODUCER", "1")
            .with_status(101)
            .with_stderr_contains("producer failed after metadata")
            .with_stderr_does_not_contain("[..]downstream_missing[..]")
            .with_stderr_does_not_contain("[..]downstream_warning[..]");
    } else if consumer_fails {
        check
            .with_status(101)
            .with_stderr_contains("[..]downstream_missing[..]");
    } else {
        check.with_stderr_contains("[..]downstream_warning[..]");
    }
    check.run();
    assert!(p.root().join("overlapped").exists());

    // A consumer that finished while its dependency later failed must be
    // rechecked on recovery, including when its previous compilation succeeded.
    if producer_fails {
        fs::remove_file(p.root().join("consumer-finished")).unwrap();
        let mut recovery = p.cargo("-Zohm-defaults=no -Zheadstart check -j2");
        recovery
            .masquerade_as_nightly_cargo(&["ohm-defaults", "headstart"])
            .env("RUSTC_WRAPPER", wrapper.bin("wrapper"))
            .env("PIPELINE_CONTROL", p.root());
        if consumer_fails {
            recovery
                .with_status(101)
                .with_stderr_contains("[..]downstream_missing[..]");
        } else {
            recovery.with_stderr_contains("[..]downstream_warning[..]");
        }
        recovery.run();
        assert!(p.root().join("consumer-finished").exists());
    }
}

#[cargo_test]
fn overlapping_check_releases_successful_consumer_output() {
    check_pipeline(false, false, false);
}

#[cargo_test]
fn overlapping_check_releases_consumer_errors() {
    check_pipeline(false, true, false);
}

#[cargo_test]
fn failed_producer_discards_consumer_errors_and_recovers() {
    check_pipeline(true, true, false);
}

#[cargo_test]
fn failed_producer_discards_consumer_success_and_recovers() {
    check_pipeline(true, false, false);
}

#[cargo_test]
fn check_binary_does_not_wait_for_transitive_dependency_completion() {
    check_pipeline(false, false, true);
}

#[cargo_test(nightly, reason = "requires the Ohm early-metadata compiler")]
fn preserves_private_edit_cutoff_and_recovers_from_interface_errors() {
    if cargo_test_support::process("rustc")
        .arg("-Zohm-early-metadata")
        .arg("--print=sysroot")
        .exec_with_output()
        .is_err()
    {
        return;
    }
    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "app"
            version = "0.1.0"
            edition = "2024"
            [dependencies]
            dep = { path = "dep" }
        "#,
        )
        .file("src/lib.rs", "pub fn app() -> u32 { dep::value() }")
        .file("dep/Cargo.toml", &basic_manifest("dep", "0.1.0"))
        .file("dep/src/lib.rs", "pub fn value() -> u32 { 7 }")
        .build();
    let check = || {
        let mut command = p.cargo("-Zohm-defaults=yes check -vv");
        command.masquerade_as_nightly_cargo(&["ohm-defaults"]);
        command
    };
    check().run();
    p.change_file("dep/src/lib.rs", "pub fn value() -> u32 { 8 }");
    check()
        .with_stderr_contains("[RUNNING] [..]--crate-name dep[..]")
        .with_stderr_does_not_contain("[RUNNING] [..]--crate-name app[..]")
        .run();
    p.change_file("dep/src/lib.rs", "pub fn value() -> u64 { false }");
    check()
        .with_status(101)
        .with_stderr_contains("[..]expected `u64`, found `bool`[..]")
        .with_stderr_does_not_contain("[..]expected `u32`, found `u64`[..]")
        .run();
    p.change_file("dep/src/lib.rs", "pub fn value() -> u64 { 8 }");
    check()
        .with_status(101)
        .with_stderr_contains("[..]expected `u32`, found `u64`[..]")
        .run();
    p.change_file("dep/src/lib.rs", "pub fn value() -> u32 { 7 }");
    check().run();
    check()
        .with_stderr_does_not_contain("[RUNNING] [..]--crate-name app[..]")
        .run();
}
