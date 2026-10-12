use crate::prelude::*;
use cargo_test_support::{Execs, Project, basic_manifest, paths, project};
use std::path::{Path, PathBuf};
use std::{env, fs};

fn compiler() -> PathBuf {
    let helper = project()
        .at("stage-compiler")
        .file("Cargo.toml", &basic_manifest("stage-compiler", "0.1.0"))
        .file(
            "src/main.rs",
            r#"
            use std::{env, fs::OpenOptions, io::Write, process::{Command, exit}};

            fn main() {
                let mut args: Vec<String> = env::args().skip(1).collect();
                if args.first().is_some_and(|arg| !arg.starts_with('-')) {
                    args.remove(0);
                }
                if args.iter().any(|arg| arg == "-Zohm-shared-stages")
                    && env::var_os("OHM_STAGES_UNSUPPORTED").is_some()
                {
                    exit(1);
                }
                if let Some(name) = args.windows(2)
                    .find(|pair| pair[0] == "--crate-name")
                    .map(|pair| &pair[1])
                {
                    if name != "___" {
                        let mut log = OpenOptions::new().create(true).append(true)
                            .open(env::var_os("OHM_STAGES_LOG").unwrap()).unwrap();
                        writeln!(log, "{}", args.join("\u{1f}")).unwrap();
                    }
                }
                args.retain(|arg| arg != "-Zohm-shared-stages");
                let status = Command::new(env::var_os("OHM_REAL_RUSTC").unwrap())
                    .args(args).status().unwrap();
                exit(status.code().unwrap_or(1));
            }
        "#,
        )
        .build();
    helper
        .cargo("-Zohm-defaults=no build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .run();
    helper.bin("stage-compiler")
}

fn cargo(p: &Project, compiler: &Path, command: &str) -> Execs {
    let mut exec = p.cargo(&format!("-Zohm-defaults=no {command}"));
    exec.masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-shared-stages"])
        .env("RUSTC", compiler)
        .env("RUSTC_BOOTSTRAP", "1")
        .env("CARGO_INCREMENTAL", "1")
        .env(
            "OHM_REAL_RUSTC",
            Path::new(&paths::sysroot())
                .join("bin/rustc")
                .with_extension(env::consts::EXE_EXTENSION),
        )
        .env("OHM_STAGES_LOG", paths::root().join("stages.log"));
    exec
}

fn invocations() -> Vec<Vec<String>> {
    fs::read_to_string(paths::root().join("stages.log"))
        .unwrap_or_default()
        .lines()
        .map(|line| line.split('\u{1f}').map(str::to_owned).collect())
        .collect()
}

fn clear_invocations() {
    fs::write(paths::root().join("stages.log"), "").unwrap();
}

fn app_library(calls: &[Vec<String>]) -> &Vec<String> {
    calls
        .iter()
        .find(|args| {
            args.windows(2)
                .any(|pair| pair == ["--crate-name", "stage_app"])
                && args.windows(2).any(|pair| pair == ["--crate-type", "lib"])
        })
        .unwrap()
}

fn option<'a>(args: &'a [String], prefix: &str) -> &'a str {
    args.iter()
        .find_map(|arg| arg.strip_prefix(prefix))
        .unwrap()
}

#[cargo_test]
fn check_and_build_share_compiler_identity_but_not_artifacts() {
    let compiler = compiler();
    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "stage-app"
            version = "0.1.0"
            edition = "2024"
            [dependencies]
            stage-dep = { path = "dep" }
            [build-dependencies]
            stage-dep = { path = "dep" }
            [profile.dev]
            debug = 2
            [profile.dev.build-override]
            debug = false
        "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { stage_dep::value() + 1 }",
        )
        .file(
            "src/main.rs",
            "fn main() { println!(\"{}\", stage_app::value()); }",
        )
        .file(
            "build.rs",
            "fn main() { assert_eq!(stage_dep::value(), 41); }",
        )
        .file("dep/Cargo.toml", &basic_manifest("stage-dep", "0.1.0"))
        .file("dep/src/lib.rs", "pub fn value() -> u32 { 41 }")
        .build();

    cargo(&p, &compiler, "-Zohm-shared-stages check").run();
    let checked = invocations();
    assert!(!p.bin("stage-app").exists());
    assert!(
        app_library(&checked)
            .iter()
            .any(|arg| arg == "-Zohm-shared-stages")
    );
    assert!(
        checked
            .iter()
            .filter(|args| args
                .windows(2)
                .any(|pair| pair == ["--crate-name", "build_script_build"]))
            .all(|args| !args.iter().any(|arg| arg == "-Zohm-shared-stages"))
    );

    clear_invocations();
    cargo(&p, &compiler, "-Zohm-shared-stages build").run();
    let built = invocations();
    let checked = app_library(&checked);
    let built = app_library(&built);
    assert_eq!(option(checked, "metadata="), option(built, "metadata="));
    assert_eq!(
        option(checked, "incremental="),
        option(built, "incremental=")
    );
    assert_ne!(
        option(checked, "extra-filename="),
        option(built, "extra-filename=")
    );
    p.process(&p.bin("stage-app"))
        .with_stdout_contains("42")
        .run();

    clear_invocations();
    cargo(&p, &compiler, "-Zohm-shared-stages build").run();
    assert!(invocations().is_empty());

    p.change_file(
        "src/lib.rs",
        "pub fn value() -> u32 { stage_dep::value() + 2 }",
    );
    cargo(&p, &compiler, "-Zohm-shared-stages check").run();
    cargo(&p, &compiler, "-Zohm-shared-stages build").run();
    p.process(&p.bin("stage-app"))
        .with_stdout_contains("43")
        .run();
}

#[cargo_test]
fn unsupported_compilers_wrappers_and_default_commands_keep_modes_separate() {
    let compiler = compiler();
    for (name, flag, unsupported, wrapper) in [
        ("default", "", false, false),
        ("older", "-Zohm-shared-stages ", true, false),
        ("wrapper", "-Zohm-shared-stages ", false, true),
    ] {
        let p = project()
            .at(name)
            .file("src/lib.rs", "pub fn value() -> u32 { 1 }")
            .build();
        let mut phases = Vec::new();
        for action in ["check", "build"] {
            clear_invocations();
            let mut command = cargo(&p, &compiler, &format!("{flag}{action}"));
            if unsupported {
                command.env("OHM_STAGES_UNSUPPORTED", "1");
            }
            if wrapper {
                command.env("RUSTC_WORKSPACE_WRAPPER", &compiler);
            }
            command.run();
            let calls = invocations();
            assert!(
                calls
                    .iter()
                    .flatten()
                    .all(|arg| arg != "-Zohm-shared-stages")
            );
            phases.push(
                calls
                    .into_iter()
                    .find(|args| args.windows(2).any(|pair| pair == ["--crate-name", "foo"]))
                    .unwrap(),
            );
        }
        assert_ne!(
            option(&phases[0], "metadata="),
            option(&phases[1], "metadata=")
        );
    }
}

#[cargo_test]
fn release_and_test_targets_do_not_share_stages() {
    let compiler = compiler();
    let p = project()
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { 1 } #[test] fn test() { assert_eq!(value(), 1); }",
        )
        .build();
    for command in [
        "check --release",
        "build --release",
        "check --tests",
        "test --no-run",
    ] {
        clear_invocations();
        cargo(&p, &compiler, &format!("-Zohm-shared-stages {command}")).run();
        let calls = invocations();
        let relevant = calls
            .iter()
            .filter(|args| command.contains("release") || args.iter().any(|arg| arg == "--test"));
        assert!(relevant.clone().count() > 0);
        assert!(relevant.flatten().all(|arg| arg != "-Zohm-shared-stages"));
    }
}
