//! Tests for setting custom rustc flags.

use std::path::PathBuf;
use std::{env, fs};

use crate::prelude::*;
use cargo_test_support::registry::Package;
use cargo_test_support::{
    RawOutput, basic_manifest, paths, project, project_in_home, rustc_host, str,
};
use serde_json::Value;
use snapbox::assert_data_eq;
use walkdir::WalkDir;

fn ohm_defaults_wrapper() -> PathBuf {
    let wrapper = project()
        .at("ohm-defaults-wrapper")
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "ohm-defaults-wrapper"
                version = "0.1.0"
                edition = "2024"
            "#,
        )
        .file(
            "src/main.rs",
            r#"
                use std::env;
                use std::fs::OpenOptions;
                use std::io::Write;
                use std::process::{Command, exit};

                fn is_ohm_rustflag(arg: &std::ffi::OsString) -> bool {
                    let arg = arg.to_string_lossy();
                    arg.starts_with("-Zpublic-api-hash")
                        || arg.starts_with("-Zpublic_api_hash")
                        || arg.starts_with("-Zcache-proc-macros")
                        || arg.starts_with("-Zohm-caller-local-cgus")
                        || arg.starts_with("-Zohm-stable-cgu-merging")
                        || arg.starts_with("-Zohm-incremental-mono-partitions")
                        || arg.starts_with("-Zthreads=")
                }

                fn main() {
                    let mut wrapper_args = env::args_os().skip(1);
                    let rustc = wrapper_args.next().expect("rustc path");
                    let args = wrapper_args.collect::<Vec<_>>();
                    let rendered = args
                        .iter()
                        .map(|arg| arg.to_string_lossy())
                        .collect::<Vec<_>>()
                        .join("\t");
                    OpenOptions::new()
                        .create(true)
                        .append(true)
                        .open(env::var_os("OHM_DEFAULTS_LOG").expect("log path"))
                        .expect("open log")
                        .write_all(format!("{rendered}\n").as_bytes())
                        .expect("write log");
                    if env::var_os("OHM_INCREMENTAL_UNSUPPORTED").is_some()
                        && args.iter().any(|arg| arg == "--print=sysroot")
                        && args.iter().any(|arg| arg == "-Zohm-caller-local-cgus")
                    {
                        exit(1);
                    }
                    if env::var_os("OHM_MONO_PARTITIONS_UNSUPPORTED")
                        .is_some_and(|value| value == "1")
                        && args.iter().any(|arg| arg == "--print=sysroot")
                        && args.iter().any(|arg| arg == "-Zohm-incremental-mono-partitions")
                    {
                        exit(1);
                    }
                    // Record thread options without requiring the test compiler
                    // to support newer values such as `threads=sync`.
                    let mut forwarded = Vec::new();
                    let mut args = args.iter().peekable();
                    while let Some(arg) = args.next() {
                        if arg == "-Z"
                            && args.peek().is_some_and(|arg| {
                                arg.to_string_lossy().starts_with("threads=")
                            })
                        {
                            args.next();
                        } else if !is_ohm_rustflag(arg) {
                            forwarded.push(arg);
                        }
                    }
                    let status = Command::new(rustc)
                        .args(forwarded)
                        .env("RUSTC_BOOTSTRAP", "1")
                        .status()
                        .expect("rustc should run");
                    exit(status.code().unwrap_or(1));
                }
            "#,
        )
        .build();
    wrapper
        .cargo("-Zohm-defaults=no build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .run();
    wrapper.bin("ohm-defaults-wrapper")
}

#[cargo_test]
fn ohm_defaults_apply_to_host_and_target_units() {
    let wrapper = ohm_defaults_wrapper();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2024"
                build = "build.rs"

                [dependencies]
                dep = { path = "dep" }

                [workspace]
                members = [".", "dep"]
            "#,
        )
        .file("build.rs", "fn main() {}")
        .file("src/lib.rs", "pub fn value() -> i32 { dep::value() }")
        .file(
            "tests/integration.rs",
            "#[test] fn value_is_positive() { assert!(foo::value() > 0); }",
        )
        .file("dep/Cargo.toml", &basic_manifest("dep", "0.1.0"))
        .file("dep/src/lib.rs", "pub fn value() -> i32 { 1 }")
        .build();
    let log = p.root().join("ohm-defaults.log");

    let default_check = if cfg!(feature = "ohm-defaults") {
        "check --target"
    } else {
        "-Zohm-defaults check --target"
    };
    p.cargo(default_check)
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .arg(rustc_host())
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .run();
    let invocations = fs::read_to_string(&log).unwrap();
    for crate_name in ["build_script_build", "dep"] {
        let invocation = rustc_invocation(&invocations, crate_name);
        assert!(invocation.contains(&"-Zpublic-api-hash"));
        assert!(invocation.contains(&"-Zcache-proc-macros"));
        assert_eq!(frontend_threads(&invocation), ["8"]);
        assert!(!invocation.contains(&"-Zpublic-api-hash=no"));
        assert!(ohm_incremental_codegen_rustflags(&invocation).is_empty());
    }
    assert_eq!(
        frontend_threads(&rustc_invocation(&invocations, "foo")),
        ["8"]
    );
    assert_eq!(
        ohm_rustflags(&rustc_invocation(&invocations, "foo")),
        [
            "-Zpublic-api-hash",
            "-Zcache-proc-macros",
            "-Zpublic-api-hash=no",
        ]
    );

    p.cargo("clean").run();
    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults check --tests")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .run();
    let invocations = fs::read_to_string(&log).unwrap();
    let library = invocations
        .lines()
        .map(|line| line.split('\t').collect::<Vec<_>>())
        .find(|args| {
            args.windows(2).any(|args| args == ["--crate-name", "foo"]) && !args.contains(&"--test")
        })
        .unwrap();
    assert!(!library.contains(&"-Zpublic-api-hash=no"));
    assert_eq!(frontend_threads(&library), ["8"]);
    assert_eq!(
        frontend_threads(&rustc_invocation(&invocations, "integration")),
        ["8"]
    );
    assert!(rustc_invocation(&invocations, "integration").contains(&"-Zpublic-api-hash=no"));

    p.cargo("clean").run();
    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults -Zrelink-only=no test --no-run")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "relink-only"])
        .env("CARGO_INCREMENTAL", "1")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .run();
    let invocations = fs::read_to_string(&log).unwrap();
    for crate_name in ["foo", "integration"] {
        let invocation = invocations
            .lines()
            .map(|line| line.split('\t').collect::<Vec<_>>())
            .find(|args| {
                args.windows(2)
                    .any(|args| args == ["--crate-name", crate_name])
                    && args.contains(&"--test")
            })
            .unwrap_or_else(|| panic!("missing test invocation for {crate_name}"));
        assert_eq!(frontend_threads(&invocation), ["8"]);
        assert_eq!(
            ohm_rustflags(&invocation),
            [
                "-Zpublic-api-hash",
                "-Zcache-proc-macros",
                "-Zpublic-api-hash=no",
            ],
            "terminal test target `{crate_name}` should not hash an unconsumed public API"
        );
    }
    for crate_name in ["foo", "dep"] {
        let library = invocations
            .lines()
            .map(|line| line.split('\t').collect::<Vec<_>>())
            .find(|args| {
                args.windows(2)
                    .any(|args| args == ["--crate-name", crate_name])
                    && !args.contains(&"--test")
            })
            .unwrap_or_else(|| panic!("missing library invocation for {crate_name}"));
        assert!(
            !library.contains(&"-Zpublic-api-hash=no"),
            "library dependency `{crate_name}` must retain its public API hash"
        );
    }
    for crate_name in ["foo", "dep", "integration"] {
        assert_eq!(
            ohm_incremental_codegen_rustflags(&rustc_invocation(&invocations, crate_name)),
            [
                "-Zohm-caller-local-cgus",
                "-Zohm-stable-cgu-merging",
                "-Zohm-incremental-mono-partitions",
            ],
            "workspace target `{crate_name}` should use incremental codegen defaults"
        );
    }
    assert!(
        ohm_incremental_codegen_rustflags(&rustc_invocation(&invocations, "build_script_build"))
            .is_empty()
    );

    p.cargo("clean").run();
    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("CARGO_INCREMENTAL", "1")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .env("CARGO_PROFILE_DEV_OPT_LEVEL", "1")
        .run();
    let invocations = fs::read_to_string(&log).unwrap();
    for crate_name in ["foo", "dep"] {
        assert_eq!(
            ohm_incremental_codegen_rustflags(&rustc_invocation(&invocations, crate_name)),
            [
                "-Zohm-caller-local-cgus",
                "-Zohm-stable-cgu-merging",
                "-Zohm-incremental-mono-partitions",
            ]
        );
    }

    p.cargo("clean").run();
    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("CARGO_INCREMENTAL", "1")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .env("CARGO_PROFILE_DEV_OPT_LEVEL", "2")
        .run();
    assert!(
        ohm_incremental_codegen_rustflags(&rustc_invocation(
            &fs::read_to_string(&log).unwrap(),
            "foo"
        ))
        .is_empty()
    );

    p.cargo("clean").run();
    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults build --release")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("CARGO_INCREMENTAL", "1")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .env("CARGO_PROFILE_RELEASE_INCREMENTAL", "true")
        .run();
    assert_eq!(
        frontend_threads(&rustc_invocation(&fs::read_to_string(&log).unwrap(), "foo")),
        ["8"]
    );
    assert!(
        ohm_incremental_codegen_rustflags(&rustc_invocation(
            &fs::read_to_string(&log).unwrap(),
            "foo"
        ))
        .is_empty()
    );

    p.cargo("clean").run();
    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("CARGO_INCREMENTAL", "1")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .env("RUSTFLAGS", "-Cinstrument-coverage=no")
        .run();
    assert!(
        ohm_incremental_codegen_rustflags(&rustc_invocation(
            &fs::read_to_string(&log).unwrap(),
            "foo"
        ))
        .is_empty()
    );

    p.cargo("clean").run();
    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("CARGO_INCREMENTAL", "1")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .env(
            "RUSTFLAGS",
            "-Zohm-caller-local-cgus=no -Zohm-stable-cgu-merging=no",
        )
        .run();
    assert_eq!(
        ohm_incremental_codegen_rustflags(&rustc_invocation(
            &fs::read_to_string(&log).unwrap(),
            "foo"
        )),
        [
            "-Zohm-caller-local-cgus",
            "-Zohm-stable-cgu-merging",
            "-Zohm-incremental-mono-partitions",
            "-Zohm-caller-local-cgus=no",
            "-Zohm-stable-cgu-merging=no",
        ]
    );

    p.cargo("clean").run();
    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("CARGO_INCREMENTAL", "1")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .env("OHM_INCREMENTAL_UNSUPPORTED", "1")
        .run();
    assert!(
        ohm_incremental_codegen_rustflags(&rustc_invocation(
            &fs::read_to_string(&log).unwrap(),
            "foo"
        ))
        .is_empty()
    );

    p.cargo("clean").run();
    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults check --target")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .arg(rustc_host())
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .env("RUSTFLAGS", "-Zpublic-api-hash=yes")
        .run();
    assert_eq!(
        ohm_rustflags(&rustc_invocation(&fs::read_to_string(&log).unwrap(), "foo")),
        [
            "-Zpublic-api-hash",
            "-Zcache-proc-macros",
            "-Zpublic-api-hash=yes",
        ]
    );

    for public_api_hash_flag in [
        "-Zpublic-api-hash=yes",
        "-Zpublic_api_hash=yes",
        "-Zpublic_api_hash=no",
    ] {
        p.cargo("clean").run();
        fs::write(&log, "").unwrap();
        p.cargo("-Zohm-defaults -Zrelink-only=no test --no-run")
            .masquerade_as_nightly_cargo(&["ohm-defaults", "relink-only"])
            .env("RUSTC_WRAPPER", &wrapper)
            .env("OHM_DEFAULTS_LOG", &log)
            .env("RUSTFLAGS", public_api_hash_flag)
            .run();
        let invocations = fs::read_to_string(&log).unwrap();
        for crate_name in ["foo", "integration"] {
            let invocation = invocations
                .lines()
                .map(|line| line.split('\t').collect::<Vec<_>>())
                .find(|args| {
                    args.windows(2)
                        .any(|args| args == ["--crate-name", crate_name])
                        && args.contains(&"--test")
                })
                .unwrap_or_else(|| panic!("missing test invocation for {crate_name}"));
            assert_eq!(
                ohm_rustflags(&invocation),
                [
                    "-Zpublic-api-hash",
                    "-Zcache-proc-macros",
                    public_api_hash_flag,
                ],
                "explicit public API hashing must override the terminal test default"
            );
        }
    }

    p.cargo("clean").run();
    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults=no check --target")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .arg(rustc_host())
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .run();
    let invocations = fs::read_to_string(&log).unwrap();
    assert!(!invocations.contains("public-api-hash"));
    assert!(!invocations.contains("cache-proc-macros"));
    assert!(frontend_threads(&rustc_invocation(&invocations, "foo")).is_empty());

    p.cargo("clean").run();
    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults check --target")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .arg(rustc_host())
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .env("RUSTFLAGS", "-Zpublic-api-hash=no -Zcache-proc-macros=no")
        .run();
    let invocations = fs::read_to_string(&log).unwrap();
    assert_eq!(
        ohm_rustflags(&rustc_invocation(&invocations, "foo")),
        [
            "-Zpublic-api-hash",
            "-Zcache-proc-macros",
            "-Zpublic-api-hash=no",
            "-Zcache-proc-macros=no",
        ]
    );

    p.cargo("clean").run();
    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults rustc --lib -- -Zpublic-api-hash=no -Zcache-proc-macros=no")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .run();
    assert_eq!(
        ohm_rustflags(&rustc_invocation(&fs::read_to_string(&log).unwrap(), "foo",)),
        [
            "-Zpublic-api-hash",
            "-Zcache-proc-macros",
            "-Zpublic-api-hash=no",
            "-Zcache-proc-macros=no",
        ]
    );

    let subcommand = project()
        .at("cargo-reinvoke")
        .file("Cargo.toml", &basic_manifest("cargo-reinvoke", "0.1.0"))
        .file(
            "src/main.rs",
            r#"
                use std::env;
                use std::process::{Command, exit};

                fn main() {
                    if let Ok(expected) = env::var("EXPECTED_INHERITED_WORKTREE_SEEDS") {
                        assert_eq!(
                            env::var("__CARGO_OHM_WORKTREE_SEEDS").as_deref(),
                            Ok(expected.as_str())
                        );
                    }
                    if let Ok(expected) = env::var("EXPECTED_INHERITED_RELINK_ONLY") {
                        assert_eq!(
                            env::var("__CARGO_RELINK_ONLY").as_deref(),
                            Ok(expected.as_str())
                        );
                    }
                    let nested_build = if let Ok(expected) =
                        env::var("EXPECTED_INHERITED_NO_EMBED_METADATA")
                    {
                        assert_eq!(
                            env::var("__CARGO_NO_EMBED_METADATA").as_deref(),
                            Ok(expected.as_str())
                        );
                        true
                    } else {
                        false
                    };
                    let mut cargo = Command::new(env::var_os("CARGO").expect("CARGO path"));
                    if let Ok(value) = env::var("NESTED_WORKTREE_SEEDS") {
                        cargo.arg(format!("-Zohm-worktree-seeds={value}"));
                    }
                    if let Ok(value) = env::var("NESTED_NO_EMBED_METADATA") {
                        cargo.arg(format!("-Zno-embed-metadata={value}"));
                    }
                    let status = cargo
                        .arg(if nested_build { "build" } else { "check" })
                        .status()
                        .expect("nested Cargo should run");
                    exit(status.code().unwrap_or(1));
                }
            "#,
        )
        .build();
    subcommand
        .cargo("-Zohm-defaults=no build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .run();
    let mut path = env::split_paths(&env::var_os("PATH").unwrap_or_default()).collect::<Vec<_>>();
    path.insert(0, subcommand.target_debug_dir());
    let path = env::join_paths(path).unwrap();

    p.cargo("clean").run();
    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults -Zrelink-only=no reinvoke")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "relink-only"])
        .env("PATH", &path)
        .env("EXPECTED_INHERITED_RELINK_ONLY", "no")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .run();
    let invocations = fs::read_to_string(&log).unwrap();
    let invocation = rustc_invocation(&invocations, "foo");
    assert!(invocation.contains(&"-Zpublic-api-hash"));
    assert!(invocation.contains(&"-Zcache-proc-macros"));
    assert_eq!(frontend_threads(&invocation), ["8"]);

    p.cargo("clean").run();
    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults=no reinvoke")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("PATH", &path)
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .run();
    let invocations = fs::read_to_string(&log).unwrap();
    assert!(!invocations.contains("public-api-hash"));
    assert!(!invocations.contains("cache-proc-macros"));
    assert!(frontend_threads(&rustc_invocation(&invocations, "foo")).is_empty());

    for (defaults, inherited, nested_override, prepared) in [
        ("yes", "no", None, false),
        ("no", "yes", None, true),
        ("yes", "no", Some("yes"), true),
        ("no", "yes", Some("no"), false),
    ] {
        p.cargo("clean").run();
        fs::write(&log, "").unwrap();
        let mut invocation = p.cargo(&format!(
            "-Zohm-defaults={defaults} -Zohm-worktree-seeds={inherited} reinvoke"
        ));
        invocation
            .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-worktree-seeds"])
            .env("PATH", &path)
            .env("EXPECTED_INHERITED_WORKTREE_SEEDS", inherited)
            .env("RUSTC_WRAPPER", &wrapper)
            .env("OHM_DEFAULTS_LOG", &log);
        if let Some(nested_override) = nested_override {
            invocation.env("NESTED_WORKTREE_SEEDS", nested_override);
        }
        invocation.run();

        let invocations = fs::read_to_string(&log).unwrap();
        assert_eq!(
            rustc_invocation(&invocations, "foo")
                .iter()
                .any(|arg| arg.starts_with("-Zremap-cwd-prefix=")),
            prepared,
            "unexpected seeding mode for inherited={inherited:?}, nested={nested_override:?}"
        );
    }

    Package::new("metadata-dependency", "0.1.0")
        .file("src/lib.rs", "pub fn value() -> i32 { 1 }")
        .publish();
    let nested = project()
        .at("ohm-no-embed-metadata-inheritance")
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "metadata-root"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                metadata-dependency = "0.1.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> i32 { metadata_dependency::value() }",
        )
        .build();

    for (inherited, nested_override, metadata_is_separate) in [
        ("no", None, false),
        ("yes", None, true),
        ("no", Some("yes"), true),
        ("yes", Some("no"), false),
    ] {
        nested.cargo("clean").run();
        fs::write(&log, "").unwrap();

        let mut invocation = nested.cargo(&format!(
            "-Zohm-defaults -Zno-embed-metadata={inherited} reinvoke"
        ));
        invocation
            .masquerade_as_nightly_cargo(&["ohm-defaults", "no-embed-metadata"])
            .env("PATH", &path)
            .env("EXPECTED_INHERITED_NO_EMBED_METADATA", inherited)
            .env("RUSTC_WRAPPER", &wrapper)
            .env("OHM_DEFAULTS_LOG", &log);
        if let Some(nested_override) = nested_override {
            invocation.env("NESTED_NO_EMBED_METADATA", nested_override);
        }
        invocation.run();

        let invocations = fs::read_to_string(&log).unwrap();
        let dependency = rustc_invocation(&invocations, "metadata_dependency");
        assert_eq!(
            dependency.contains(&"embed-metadata=no"),
            metadata_is_separate,
            "unexpected metadata mode for inherited={inherited:?}, nested={nested_override:?}"
        );
    }
}

#[cargo_test]
fn ohm_parallel_frontend_user_flags_take_precedence() {
    let wrapper = ohm_defaults_wrapper();
    let p = project().file("src/lib.rs", "").build();
    let log = p.root().join("ohm-defaults.log");

    for (variable, flags, expected) in [
        ("RUSTFLAGS", "-Zthreads=1", "1"),
        ("RUSTFLAGS", "-Z threads=1", "1"),
        ("RUSTFLAGS", "-Zthreads=4", "4"),
        ("RUSTFLAGS", "-Zthreads=sync", "sync"),
        ("RUSTFLAGS", "-Zthreads=0", "0"),
        ("CARGO_ENCODED_RUSTFLAGS", "-Z\x1fthreads=1", "1"),
    ] {
        p.cargo("clean").run();
        fs::write(&log, "").expect("clear compiler log");
        p.cargo("-Zohm-defaults check")
            .masquerade_as_nightly_cargo(&["ohm-defaults"])
            .env("RUSTC_WRAPPER", &wrapper)
            .env("OHM_DEFAULTS_LOG", &log)
            .env("RUSTFLAGS", "-Zthreads=2")
            .env(variable, flags)
            .run();
        let invocations = fs::read_to_string(&log).expect("read compiler log");
        assert_eq!(
            frontend_threads(&rustc_invocation(&invocations, "foo")),
            ["8", expected],
            "{variable}={flags:?} must override the packaged thread count"
        );
    }

    for config in [
        "build.rustflags=[\"-Zthreads=1\"]".to_owned(),
        format!("target.{}.rustflags=[\"-Z\",\"threads=1\"]", rustc_host()),
        "profile.dev.rustflags=[\"-Zthreads=1\"]".to_owned(),
    ] {
        p.cargo("clean").run();
        fs::write(&log, "").expect("clear compiler log");
        p.cargo("-Zohm-defaults -Zprofile-rustflags check")
            .masquerade_as_nightly_cargo(&["ohm-defaults", "profile-rustflags"])
            .arg("--config")
            .arg(&config)
            .env("RUSTC_WRAPPER", &wrapper)
            .env("OHM_DEFAULTS_LOG", &log)
            .run();
        let invocations = fs::read_to_string(&log).expect("read compiler log");
        assert_eq!(
            frontend_threads(&rustc_invocation(&invocations, "foo")),
            ["8", "1"],
            "{config} must override the packaged thread count"
        );
    }

    for flags in ["-Zthreads=1", "-Z threads=1"] {
        p.cargo("clean").run();
        fs::write(&log, "").expect("clear compiler log");
        p.cargo(&format!("-Zohm-defaults rustc --lib -- {flags}"))
            .masquerade_as_nightly_cargo(&["ohm-defaults"])
            .env("RUSTC_WRAPPER", &wrapper)
            .env("OHM_DEFAULTS_LOG", &log)
            .run();
        let invocations = fs::read_to_string(&log).expect("read compiler log");
        assert_eq!(
            frontend_threads(&rustc_invocation(&invocations, "foo")),
            ["8", "1"]
        );
    }

    p.cargo("clean").run();
    fs::write(&log, "").expect("clear compiler log");
    p.cargo("-Zohm-defaults=no check")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .env("RUSTFLAGS", "-Zthreads=1")
        .run();
    let invocations = fs::read_to_string(&log).expect("read compiler log");
    assert_eq!(
        frontend_threads(&rustc_invocation(&invocations, "foo")),
        ["1"]
    );
}

#[cargo_test]
fn ohm_parallel_frontend_flags_are_fingerprinted() {
    let wrapper = ohm_defaults_wrapper();
    let p = project().file("src/lib.rs", "").build();
    let log = p.root().join("ohm-defaults.log");

    for (rustflags, fresh) in [
        (None, false),
        (None, true),
        (Some("-Zthreads=1"), false),
        (Some("-Zthreads=1"), true),
        (None, true),
    ] {
        let mut check = p.cargo("-Zohm-defaults check -v");
        check
            .masquerade_as_nightly_cargo(&["ohm-defaults"])
            .env("RUSTC_WRAPPER", &wrapper)
            .env("OHM_DEFAULTS_LOG", &log);
        if let Some(rustflags) = rustflags {
            check.env("RUSTFLAGS", rustflags);
        }
        if fresh {
            check.with_stderr_data(str![[r#"
[FRESH] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]);
        } else {
            check.with_stderr_data(str![[r#"
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `[..] --crate-name foo [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]);
        }
        check.run();
    }

    let mut rustflags = WalkDir::new(p.build_dir())
        .into_iter()
        .map(|entry| entry.expect("read fingerprint directory"))
        .filter(|entry| entry.file_name() == "lib-foo.json")
        .map(|entry| {
            let contents = fs::read(entry.path()).expect("read fingerprint");
            let fingerprint: Value = serde_json::from_slice(&contents).expect("parse fingerprint");
            serde_json::from_value::<Vec<String>>(fingerprint["rustflags"].clone())
                .expect("fingerprinted rustflags")
        })
        .collect::<Vec<_>>();
    rustflags.sort();
    assert_eq!(
        rustflags,
        [
            vec!["-Zpublic-api-hash", "-Zcache-proc-macros", "-Zthreads=8"],
            vec![
                "-Zpublic-api-hash",
                "-Zcache-proc-macros",
                "-Zthreads=8",
                "-Zthreads=1",
            ],
        ]
    );
}

#[cargo_test]
fn ohm_incremental_mono_partitions_follow_compiler_capability() {
    let wrapper = ohm_defaults_wrapper();
    let p = project()
        .file(
            "src/lib.rs",
            "#[test] fn selected() { assert_eq!(1 + 1, 2); }",
        )
        .build();
    let log = p.root().join("ohm-defaults.log");

    for wrapper_variable in ["RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"] {
        for (defaults, unsupported, user_flags, expected) in [
            (
                "yes",
                false,
                None,
                vec!["-Zohm-incremental-mono-partitions"],
            ),
            ("yes", true, None, vec![]),
            ("no", false, None, vec![]),
            (
                "yes",
                false,
                Some("-Zohm-incremental-mono-partitions=no"),
                vec![
                    "-Zohm-incremental-mono-partitions",
                    "-Zohm-incremental-mono-partitions=no",
                ],
            ),
        ] {
            p.cargo("clean").run();
            fs::write(&log, "").expect("clear compiler log");
            let mut command = p.cargo(&format!(
                "-Zohm-defaults={defaults} -Zrelink-only=no test --lib --no-run"
            ));
            command
                .masquerade_as_nightly_cargo(&["ohm-defaults", "relink-only"])
                .env("CARGO_INCREMENTAL", "1")
                .env(wrapper_variable, &wrapper)
                .env("OHM_DEFAULTS_LOG", &log);
            if unsupported {
                command.env("OHM_MONO_PARTITIONS_UNSUPPORTED", "1");
            }
            if let Some(user_flags) = user_flags {
                command.env("RUSTFLAGS", user_flags);
            }
            command.run();

            let invocations = fs::read_to_string(&log).expect("read compiler log");
            let invocation = rustc_invocation(&invocations, "foo");
            assert!(invocation.contains(&"--test"));
            assert_eq!(
                invocation.contains(&"-Zpublic-api-hash=no"),
                defaults == "yes"
            );
            assert_eq!(
                invocation
                    .iter()
                    .copied()
                    .filter(|flag| flag.starts_with("-Zohm-incremental-mono-partitions"))
                    .collect::<Vec<_>>(),
                expected
            );
            for flag in ["-Zohm-caller-local-cgus", "-Zohm-stable-cgu-merging"] {
                assert_eq!(invocation.contains(&flag), defaults == "yes");
            }
        }
    }
}

#[cargo_test]
fn ohm_incremental_mono_partitions_are_fingerprinted() {
    let wrapper = ohm_defaults_wrapper();
    let p = project().file("src/lib.rs", "").build();
    let log = p.root().join("ohm-defaults.log");
    let mut identities = Vec::new();

    for (unsupported, fresh) in [
        (false, false),
        (false, true),
        (true, false),
        (true, true),
        (false, true),
    ] {
        p.change_file(
            ".cargo/config.toml",
            &format!(
                "[env]\nOHM_MONO_PARTITIONS_UNSUPPORTED = {{ value = \"{}\", force = true }}\n",
                u8::from(unsupported)
            ),
        );
        fs::write(&log, "").expect("clear compiler log");
        let mut build = p.cargo("-Zohm-defaults build --lib -v");
        build
            .masquerade_as_nightly_cargo(&["ohm-defaults"])
            .env("CARGO_INCREMENTAL", "1")
            .env("RUSTC_WORKSPACE_WRAPPER", &wrapper)
            .env("OHM_DEFAULTS_LOG", &log);
        if fresh {
            build.with_stderr_data(str![[r#"
[FRESH] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]);
        } else {
            build.with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `[..] --crate-name foo [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]);
        }
        build.run();
        if !fresh {
            let invocations = fs::read_to_string(&log).expect("read compiler log");
            let invocation = rustc_invocation(&invocations, "foo");
            assert_eq!(
                invocation.contains(&"-Zohm-incremental-mono-partitions"),
                !unsupported
            );
            let metadata = invocation
                .iter()
                .find(|argument| argument.starts_with("metadata="))
                .expect("compiler symbol metadata");
            let extra_filename = invocation
                .iter()
                .find(|argument| argument.starts_with("extra-filename="))
                .expect("compiler artifact identity");
            identities.push((metadata.to_string(), extra_filename.to_string()));
        }
    }
    assert_eq!(identities.len(), 2);
    assert_eq!(identities[0].0, identities[1].0);
    assert_ne!(identities[0].1, identities[1].1);
}

#[cargo_test]
fn ohm_incremental_mono_partitions_invalidate_unhashed_artifacts() {
    let wrapper = ohm_defaults_wrapper();
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2024"

                [lib]
                crate-type = ["cdylib"]
            "#,
        )
        .file("src/lib.rs", "")
        .build();
    let log = p.root().join("ohm-defaults.log");

    for (revision, (unsupported, fresh)) in [
        (false, false),
        (false, true),
        (true, false),
        (true, true),
        (false, false),
    ]
    .into_iter()
    .enumerate()
    {
        p.change_file(
            ".cargo/config.toml",
            &format!(
                "[env]\nOHM_MONO_PARTITIONS_UNSUPPORTED = {{ value = \"{}\", force = true }}\n",
                u8::from(unsupported)
            ),
        );
        fs::write(&log, "").expect("clear compiler log");
        let mut build = p.cargo("-Zohm-defaults build --lib -v");
        build
            .masquerade_as_nightly_cargo(&["ohm-defaults"])
            .env("CARGO_INCREMENTAL", "1")
            .env("CARGO_UNSTABLE_BUILD_DIR_NEW_LAYOUT", "false")
            .env("CARGO_UNSTABLE_FINE_GRAIN_LOCKING", "false")
            .env("CARGO_UNSTABLE_OHM_SHARED_REGISTRY_CACHE", "false")
            .env("RUSTC_WORKSPACE_WRAPPER", &wrapper)
            .env("OHM_DEFAULTS_LOG", &log);
        if fresh {
            build.with_stderr_data(str![[r#"
[FRESH] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]);
        } else if revision == 0 {
            build.with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `[..] --crate-name foo [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]);
        } else {
            build.with_stderr_data(str![[r#"
[DIRTY] foo v0.0.1 ([ROOT]/foo): the config settings changed
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `[..] --crate-name foo [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]);
        }
        build.run();
        if !fresh {
            let invocations = fs::read_to_string(&log).expect("read compiler log");
            let invocation = rustc_invocation(&invocations, "foo");
            assert_eq!(
                invocation.contains(&"-Zohm-incremental-mono-partitions"),
                !unsupported
            );
            assert!(
                !invocation
                    .iter()
                    .any(|argument| argument.starts_with("extra-filename="))
            );
        }
    }
    // This layout overwrites one artifact and fingerprint instead of retaining
    // separate unit-id-suffixed outputs for the two capability states.
    assert_eq!(
        WalkDir::new(p.build_dir())
            .into_iter()
            .map(|entry| entry.expect("read fingerprint directory"))
            .filter(|entry| entry.file_name() == "lib-foo.json")
            .count(),
        1
    );
}

#[cargo_test]
fn ohm_lto_share_generics_respects_lto_and_user_flags() {
    let wrapper = ohm_defaults_wrapper();
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                dep = { path = "dep" }

                [build-dependencies]
                host_dep = { path = "host-dep" }

                [profile.release]
                lto = "fat"
            "#,
        )
        .file("src/main.rs", "fn main() { assert_eq!(dep::value(3), 3); }")
        .file("build.rs", "fn main() { host_dep::value(); }")
        .file("dep/Cargo.toml", &basic_manifest("dep", "0.1.0"))
        .file("dep/src/lib.rs", "pub fn value<T>(value: T) -> T { value }")
        .file("host-dep/Cargo.toml", &basic_manifest("host_dep", "0.1.0"))
        .file("host-dep/src/lib.rs", "pub fn value() {}")
        .build();
    let log = p.root().join("ohm-defaults.log");

    p.cargo("-Zohm-defaults=no -Zohm-lto-share-generics run --release")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-lto-share-generics"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .run();
    let invocations = fs::read_to_string(&log).unwrap();
    assert!(rustc_invocation(&invocations, "foo").contains(&"-Zshare-generics=yes"));
    assert!(rustc_invocation(&invocations, "dep").contains(&"-Zshare-generics=yes"));
    assert!(!rustc_invocation(&invocations, "host_dep").contains(&"-Zshare-generics=yes"));
    assert!(
        !rustc_invocation(&invocations, "build_script_build").contains(&"-Zshare-generics=yes")
    );

    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults=no -Zohm-lto-share-generics run --release")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-lto-share-generics"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .env("CARGO_PROFILE_RELEASE_LTO", "thin")
        .env("RUSTFLAGS", "-Zshare-generics=no")
        .run();
    let invocations = fs::read_to_string(&log).unwrap();
    let invocation = rustc_invocation(&invocations, "foo");
    assert_eq!(
        invocation
            .iter()
            .copied()
            .filter(|arg| arg.starts_with("-Zshare-generics="))
            .collect::<Vec<_>>(),
        ["-Zshare-generics=yes", "-Zshare-generics=no"]
    );

    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults=no -Zohm-lto-share-generics run --release")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-lto-share-generics"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .env("CARGO_PROFILE_RELEASE_LTO", "off")
        .run();
    let invocations = fs::read_to_string(&log).unwrap();
    assert!(!invocations.contains("-Zshare-generics"));
}

#[cargo_test]
fn ohm_lto_share_generics_preserves_mixed_outputs() {
    let wrapper = ohm_defaults_wrapper();
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2024"

                [lib]
                crate-type = ["rlib", "cdylib"]

                [dependencies]
                dep = { path = "dep" }

                [profile.release]
                lto = "fat"
            "#,
        )
        .file("src/lib.rs", "pub fn value() -> u32 { dep::value(3) }")
        .file("dep/Cargo.toml", &basic_manifest("dep", "0.1.0"))
        .file("dep/src/lib.rs", "pub fn value<T>(value: T) -> T { value }")
        .build();
    let log = p.root().join("ohm-defaults.log");
    p.cargo("-Zohm-defaults=no -Zohm-lto-share-generics build --release")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-lto-share-generics"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .run();
    let invocations = fs::read_to_string(&log).unwrap();
    assert!(!rustc_invocation(&invocations, "foo").contains(&"-Zshare-generics=yes"));
    assert!(!rustc_invocation(&invocations, "dep").contains(&"-Zshare-generics=yes"));
}

#[cargo_test]
fn ohm_lto_share_generics_invalidates_unhashed_outputs() {
    let wrapper = ohm_defaults_wrapper();
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2024"

                [lib]
                crate-type = ["cdylib"]

                [profile.release]
                lto = "fat"
            "#,
        )
        .file("src/lib.rs", "pub fn value<T>(value: T) -> T { value }")
        .build();
    let log = p.root().join("ohm-defaults.log");
    p.cargo("-Zohm-defaults=no build --release")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .run();
    let invocations = fs::read_to_string(&log).unwrap();
    let invocation = rustc_invocation(&invocations, "foo");
    assert!(!invocation.contains(&"-Zshare-generics=yes"));
    assert!(
        !invocation
            .iter()
            .any(|arg| arg.starts_with("extra-filename="))
    );

    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults=no -Zohm-lto-share-generics build --release")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-lto-share-generics"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .run();
    let invocations = fs::read_to_string(&log).unwrap();
    assert!(rustc_invocation(&invocations, "foo").contains(&"-Zshare-generics=yes"));

    fs::write(&log, "").unwrap();
    p.cargo("-Zohm-defaults=no -Zohm-lto-share-generics build --release")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-lto-share-generics"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .run();
    assert!(fs::read_to_string(&log).unwrap().is_empty());

    p.cargo("-Zohm-defaults=no build --release")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("OHM_DEFAULTS_LOG", &log)
        .run();
    let invocations = fs::read_to_string(&log).unwrap();
    assert!(!rustc_invocation(&invocations, "foo").contains(&"-Zshare-generics=yes"));
}

fn rustc_invocation<'a>(log: &'a str, crate_name: &str) -> Vec<&'a str> {
    log.lines()
        .map(|line| line.split('\t').collect::<Vec<_>>())
        .find(|args| {
            args.windows(2)
                .any(|args| args == ["--crate-name", crate_name])
        })
        .unwrap_or_else(|| panic!("missing rustc invocation for {crate_name}"))
}

fn ohm_rustflags<'a>(invocation: &'a [&str]) -> Vec<&'a str> {
    invocation
        .iter()
        .copied()
        .filter(|flag| {
            flag.starts_with("-Zpublic-api-hash")
                || flag.starts_with("-Zpublic_api_hash")
                || flag.starts_with("-Zcache-proc-macros")
        })
        .collect()
}

fn ohm_incremental_codegen_rustflags<'a>(invocation: &'a [&str]) -> Vec<&'a str> {
    invocation
        .iter()
        .copied()
        .filter(|flag| {
            flag.starts_with("-Zohm-caller-local-cgus")
                || flag.starts_with("-Zohm-stable-cgu-merging")
                || flag.starts_with("-Zohm-incremental-mono-partitions")
        })
        .collect()
}

fn frontend_threads<'a>(invocation: &[&'a str]) -> Vec<&'a str> {
    let mut threads = Vec::new();
    let mut args = invocation.iter().copied();
    while let Some(arg) = args.next() {
        let option = if arg == "-Z" {
            args.next()
        } else {
            arg.strip_prefix("-Z")
        };
        if let Some(value) = option.and_then(|option| option.strip_prefix("threads=")) {
            threads.push(value);
        }
    }
    threads
}

#[cargo_test]
fn env_rustflags_normal_source() {
    let p = project()
        .file("src/lib.rs", "")
        .file("src/bin/a.rs", "fn main() {}")
        .file("examples/b.rs", "fn main() {}")
        .file("tests/c.rs", "#[test] fn f() { }")
        .file(
            "benches/d.rs",
            r#"
            #![feature(test)]
            extern crate test;
            #[bench] fn run1(_ben: &mut test::Bencher) { }
            "#,
        )
        .build();

    // Use RUSTFLAGS to pass an argument that will generate an error
    p.cargo("check --lib")
        .env("RUSTFLAGS", "-Z bogus")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("check --bin=a")
        .env("RUSTFLAGS", "-Z bogus")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("check --example=b")
        .env("RUSTFLAGS", "-Z bogus")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("test")
        .env("RUSTFLAGS", "-Z bogus")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("bench")
        .env("RUSTFLAGS", "-Z bogus")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
}

#[cargo_test]
fn env_rustflags_build_script() {
    // RUSTFLAGS should be passed to rustc for build scripts
    // when --target is not specified.
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                build = "build.rs"
            "#,
        )
        .file("src/lib.rs", "")
        .file(
            "build.rs",
            r#"
                fn main() { assert!(cfg!(foo)); }
            "#,
        )
        .build();

    p.cargo("check").env("RUSTFLAGS", "--cfg foo").run();
}

#[cargo_test]
fn env_rustflags_build_script_dep() {
    // RUSTFLAGS should be passed to rustc for build scripts
    // when --target is not specified.
    // In this test if --cfg foo is not passed the build will fail.
    let foo = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                build = "build.rs"

                [build-dependencies.bar]
                path = "../bar"
            "#,
        )
        .file("src/lib.rs", "")
        .file("build.rs", "fn main() {}")
        .build();
    let _bar = project()
        .at("bar")
        .file("Cargo.toml", &basic_manifest("bar", "0.0.1"))
        .file(
            "src/lib.rs",
            r#"
                fn bar() { }
                #[cfg(not(foo))]
                fn bar() { }
            "#,
        )
        .build();

    foo.cargo("check").env("RUSTFLAGS", "--cfg foo").run();
}

#[cargo_test]
fn env_rustflags_normal_source_with_target() {
    let p = project()
        .file("src/lib.rs", "")
        .file("src/bin/a.rs", "fn main() {}")
        .file("examples/b.rs", "fn main() {}")
        .file("tests/c.rs", "#[test] fn f() { }")
        .file(
            "benches/d.rs",
            r#"
            #![feature(test)]
            extern crate test;
            #[bench] fn run1(_ben: &mut test::Bencher) { }
            "#,
        )
        .build();

    let host = &rustc_host();

    // Use RUSTFLAGS to pass an argument that will generate an error
    p.cargo("check --lib --target")
        .arg(host)
        .env("RUSTFLAGS", "-Z bogus")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("check --bin=a --target")
        .arg(host)
        .env("RUSTFLAGS", "-Z bogus")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("check --example=b --target")
        .arg(host)
        .env("RUSTFLAGS", "-Z bogus")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("test --target")
        .arg(host)
        .env("RUSTFLAGS", "-Z bogus")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("bench --target")
        .arg(host)
        .env("RUSTFLAGS", "-Z bogus")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
}

#[cargo_test]
fn env_rustflags_build_script_with_target() {
    // RUSTFLAGS should not be passed to rustc for build scripts
    // when --target is specified.
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                build = "build.rs"
            "#,
        )
        .file("src/lib.rs", "")
        .file(
            "build.rs",
            r#"
                fn main() { assert!(!cfg!(foo)); }
            "#,
        )
        .build();

    let host = rustc_host();
    p.cargo("check --target")
        .arg(host)
        .env("RUSTFLAGS", "--cfg foo")
        .run();
}

#[cargo_test]
fn env_rustflags_build_script_with_target_doesnt_apply_to_host_kind() {
    // RUSTFLAGS should *not* be passed to rustc for build scripts when --target is specified as the
    // host triple even if target-applies-to-host-kind is enabled, to match legacy Cargo behavior.
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                build = "build.rs"
            "#,
        )
        .file("src/lib.rs", "")
        .file(
            "build.rs",
            r#"
                fn main() { assert!(!cfg!(foo)); }
            "#,
        )
        .file(
            ".cargo/config.toml",
            r#"
                target-applies-to-host = true
            "#,
        )
        .build();

    let host = rustc_host();
    p.cargo("check --target")
        .masquerade_as_nightly_cargo(&["target-applies-to-host"])
        .arg(host)
        .arg("-Ztarget-applies-to-host")
        .env("RUSTFLAGS", "--cfg foo")
        .run();
}

#[cargo_test]
fn env_rustflags_build_script_dep_with_target() {
    // RUSTFLAGS should not be passed to rustc for build scripts
    // when --target is specified.
    // In this test if --cfg foo is passed the build will fail.
    let foo = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                build = "build.rs"

                [build-dependencies.bar]
                path = "../bar"
            "#,
        )
        .file("src/lib.rs", "")
        .file("build.rs", "fn main() {}")
        .build();
    let _bar = project()
        .at("bar")
        .file("Cargo.toml", &basic_manifest("bar", "0.0.1"))
        .file(
            "src/lib.rs",
            r#"
                fn bar() { }
                #[cfg(foo)]
                fn bar() { }
            "#,
        )
        .build();

    let host = rustc_host();
    foo.cargo("check --target")
        .arg(host)
        .env("RUSTFLAGS", "--cfg foo")
        .run();
}

#[cargo_test]
fn env_rustflags_recompile() {
    let p = project().file("src/lib.rs", "").build();

    p.cargo("check").run();
    // Setting RUSTFLAGS forces a recompile
    p.cargo("check")
        .env("RUSTFLAGS", "-Z bogus")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
}

#[cargo_test]
fn env_rustflags_recompile2() {
    let p = project().file("src/lib.rs", "").build();

    p.cargo("check").env("RUSTFLAGS", "--cfg foo").run();
    // Setting RUSTFLAGS forces a recompile
    p.cargo("check")
        .env("RUSTFLAGS", "-Z bogus")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
}

#[cargo_test]
fn env_rustflags_no_recompile() {
    let p = project().file("src/lib.rs", "").build();

    p.cargo("check").env("RUSTFLAGS", "--cfg foo").run();
    p.cargo("check")
        .env("RUSTFLAGS", "--cfg foo")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn build_rustflags_normal_source() {
    let p = project()
        .file("src/lib.rs", "")
        .file("src/bin/a.rs", "fn main() {}")
        .file("examples/b.rs", "fn main() {}")
        .file("tests/c.rs", "#[test] fn f() { }")
        .file(
            "benches/d.rs",
            r#"
            #![feature(test)]
            extern crate test;
            #[bench] fn run1(_ben: &mut test::Bencher) { }
            "#,
        )
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            rustflags = ["-Z", "bogus"]
            "#,
        )
        .build();

    p.cargo("check --lib")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("check --bin=a")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("check --example=b")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("test")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("bench")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
}

#[cargo_test]
fn build_rustflags_build_script() {
    // RUSTFLAGS should be passed to rustc for build scripts
    // when --target is not specified.
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                build = "build.rs"
            "#,
        )
        .file("src/lib.rs", "")
        .file(
            "build.rs",
            r#"
                fn main() { assert!(cfg!(foo)); }
            "#,
        )
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            rustflags = ["--cfg", "foo"]
            "#,
        )
        .build();

    p.cargo("check").run();
}

#[cargo_test]
fn build_rustflags_build_script_dep() {
    // RUSTFLAGS should be passed to rustc for build scripts
    // when --target is not specified.
    // In this test if --cfg foo is not passed the build will fail.
    let foo = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                build = "build.rs"

                [build-dependencies.bar]
                path = "../bar"
            "#,
        )
        .file("src/lib.rs", "")
        .file("build.rs", "fn main() {}")
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            rustflags = ["--cfg", "foo"]
            "#,
        )
        .build();
    let _bar = project()
        .at("bar")
        .file("Cargo.toml", &basic_manifest("bar", "0.0.1"))
        .file(
            "src/lib.rs",
            r#"
                fn bar() { }
                #[cfg(not(foo))]
                fn bar() { }
            "#,
        )
        .build();

    foo.cargo("check").run();
}

#[cargo_test]
fn build_rustflags_normal_source_with_target() {
    let p = project()
        .file("src/lib.rs", "")
        .file("src/bin/a.rs", "fn main() {}")
        .file("examples/b.rs", "fn main() {}")
        .file("tests/c.rs", "#[test] fn f() { }")
        .file(
            "benches/d.rs",
            r#"
            #![feature(test)]
            extern crate test;
            #[bench] fn run1(_ben: &mut test::Bencher) { }
            "#,
        )
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            rustflags = ["-Z", "bogus"]
            "#,
        )
        .build();

    let host = &rustc_host();

    // Use build.rustflags to pass an argument that will generate an error
    p.cargo("check --lib --target")
        .arg(host)
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("check --bin=a --target")
        .arg(host)
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("check --example=b --target")
        .arg(host)
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("test --target")
        .arg(host)
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("bench --target")
        .arg(host)
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
}

#[cargo_test]
fn build_rustflags_build_script_with_target() {
    // RUSTFLAGS should not be passed to rustc for build scripts
    // when --target is specified.
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                build = "build.rs"
            "#,
        )
        .file("src/lib.rs", "")
        .file(
            "build.rs",
            r#"
                fn main() { assert!(!cfg!(foo)); }
            "#,
        )
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            rustflags = ["--cfg", "foo"]
            "#,
        )
        .build();

    let host = rustc_host();
    p.cargo("check --target").arg(host).run();
}

#[cargo_test]
fn build_rustflags_build_script_dep_with_target() {
    // RUSTFLAGS should not be passed to rustc for build scripts
    // when --target is specified.
    // In this test if --cfg foo is passed the build will fail.
    let foo = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                build = "build.rs"

                [build-dependencies.bar]
                path = "../bar"
            "#,
        )
        .file("src/lib.rs", "")
        .file("build.rs", "fn main() {}")
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            rustflags = ["--cfg", "foo"]
            "#,
        )
        .build();
    let _bar = project()
        .at("bar")
        .file("Cargo.toml", &basic_manifest("bar", "0.0.1"))
        .file(
            "src/lib.rs",
            r#"
                fn bar() { }
                #[cfg(foo)]
                fn bar() { }
            "#,
        )
        .build();

    let host = rustc_host();
    foo.cargo("check --target").arg(host).run();
}

#[cargo_test]
fn build_rustflags_recompile() {
    let p = project().file("src/lib.rs", "").build();

    p.cargo("check").run();

    // Setting RUSTFLAGS forces a recompile
    let config = r#"
        [build]
        rustflags = ["-Z", "bogus"]
        "#;
    let config_file = paths::root().join("foo/.cargo/config.toml");
    fs::create_dir_all(config_file.parent().unwrap()).unwrap();
    fs::write(config_file, config).unwrap();

    p.cargo("check")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
}

#[cargo_test]
fn build_rustflags_recompile2() {
    let p = project().file("src/lib.rs", "").build();

    p.cargo("check").env("RUSTFLAGS", "--cfg foo").run();

    // Setting RUSTFLAGS forces a recompile
    let config = r#"
        [build]
        rustflags = ["-Z", "bogus"]
        "#;
    let config_file = paths::root().join("foo/.cargo/config.toml");
    fs::create_dir_all(config_file.parent().unwrap()).unwrap();
    fs::write(config_file, config).unwrap();

    p.cargo("check")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
}

#[cargo_test]
fn build_rustflags_no_recompile() {
    let p = project()
        .file("src/lib.rs", "")
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            rustflags = ["--cfg", "foo"]
            "#,
        )
        .build();

    p.cargo("check").env("RUSTFLAGS", "--cfg foo").run();
    p.cargo("check")
        .env("RUSTFLAGS", "--cfg foo")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn build_rustflags_with_home_config() {
    // We need a config file inside the home directory
    let home = paths::home();
    let home_config = home.join(".cargo");
    fs::create_dir(&home_config).unwrap();
    fs::write(
        &home_config.join("config"),
        r#"
            [build]
            rustflags = ["-Cllvm-args=-x86-asm-syntax=intel"]
        "#,
    )
    .unwrap();

    // And we need the project to be inside the home directory
    // so the walking process finds the home project twice.
    let p = project_in_home("foo").file("src/lib.rs", "").build();

    p.cargo("check -v").run();
}

#[cargo_test]
fn target_rustflags_normal_source() {
    let p = project()
        .file("src/lib.rs", "")
        .file("src/bin/a.rs", "fn main() {}")
        .file("examples/b.rs", "fn main() {}")
        .file("tests/c.rs", "#[test] fn f() { }")
        .file(
            "benches/d.rs",
            r#"
            #![feature(test)]
            extern crate test;
            #[bench] fn run1(_ben: &mut test::Bencher) { }
            "#,
        )
        .file(
            ".cargo/config.toml",
            &format!(
                "
            [target.{}]
            rustflags = [\"-Z\", \"bogus\"]
            ",
                rustc_host()
            ),
        )
        .build();

    p.cargo("check --lib")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("check --bin=a")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("check --example=b")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("test")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("bench")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
}

#[cargo_test]
fn target_rustflags_also_for_build_scripts() {
    let p = project()
        .file("src/lib.rs", "")
        .file(
            "build.rs",
            r#"
                fn main() { assert!(cfg!(foo)); }
            "#,
        )
        .file(
            ".cargo/config.toml",
            &format!(
                "
            [target.{}]
            rustflags = [\"--cfg=foo\"]
            ",
                rustc_host()
            ),
        )
        .build();

    p.cargo("check").run();
}

#[cargo_test]
fn target_rustflags_not_for_build_scripts_with_target() {
    let host = rustc_host();
    let p = project()
        .file("src/lib.rs", "")
        .file(
            "build.rs",
            r#"
                fn main() { assert!(!cfg!(foo)); }
            "#,
        )
        .file(
            ".cargo/config.toml",
            &format!(
                "
            [target.{}]
            rustflags = [\"--cfg=foo\"]
            ",
                host
            ),
        )
        .build();

    p.cargo("check --target").arg(host).run();

    // Enabling -Ztarget-applies-to-host should not make a difference without the config setting
    p.cargo("check --target")
        .arg(host)
        .masquerade_as_nightly_cargo(&["target-applies-to-host"])
        .arg("-Ztarget-applies-to-host")
        .run();

    // Even with the setting, the rustflags from `target.` should not apply, to match the legacy
    // Cargo behavior.
    p.change_file(
        ".cargo/config.toml",
        &format!(
            "
        target-applies-to-host = true

        [target.{}]
        rustflags = [\"--cfg=foo\"]
        ",
            host
        ),
    );
    p.cargo("check --target")
        .arg(host)
        .masquerade_as_nightly_cargo(&["target-applies-to-host"])
        .arg("-Ztarget-applies-to-host")
        .run();
}

#[cargo_test]
fn build_rustflags_for_build_scripts() {
    let host = rustc_host();
    let p = project()
        .file("src/lib.rs", "")
        .file(
            "build.rs",
            r#"
                fn main() { assert!(cfg!(foo), "CFG FOO!"); }
            "#,
        )
        .file(
            ".cargo/config.toml",
            "
            [build]
            rustflags = [\"--cfg=foo\"]
            ",
        )
        .build();

    // With "legacy" behavior, build.rustflags should apply to build scripts without --target
    p.cargo("check").run();

    // But should _not_ apply _with_ --target
    p.cargo("check --target")
        .arg(host)
        .with_status(101)
        .with_stderr_data("...\n[..]CFG FOO![..]\n...")
        .run();

    // Enabling -Ztarget-applies-to-host should not make a difference without the config setting
    p.cargo("check")
        .masquerade_as_nightly_cargo(&["target-applies-to-host"])
        .arg("-Ztarget-applies-to-host")
        .run();
    p.cargo("check --target")
        .arg(host)
        .masquerade_as_nightly_cargo(&["target-applies-to-host"])
        .arg("-Ztarget-applies-to-host")
        .with_status(101)
        .with_stderr_data("...\n[..]CFG FOO![..]\n...")
        .run();

    // When set to false though, the "proper" behavior where host artifacts _only_ pick up on
    // [host] should be applied.
    p.change_file(
        ".cargo/config.toml",
        "
        target-applies-to-host = false

        [build]
        rustflags = [\"--cfg=foo\"]
        ",
    );
    p.cargo("check")
        .masquerade_as_nightly_cargo(&["target-applies-to-host"])
        .arg("-Ztarget-applies-to-host")
        .with_status(101)
        .with_stderr_data("...\n[..]CFG FOO![..]\n...")
        .run();
    p.cargo("check --target")
        .arg(host)
        .masquerade_as_nightly_cargo(&["target-applies-to-host"])
        .arg("-Ztarget-applies-to-host")
        .with_status(101)
        .with_stderr_data("...\n[..]CFG FOO![..]\n...")
        .run();
}

#[cargo_test]
fn host_rustflags_for_build_scripts() {
    let host = rustc_host();
    let p = project()
        .file("src/lib.rs", "")
        .file(
            "build.rs",
            r#"
                // Ensure that --cfg=foo is passed.
                fn main() { assert!(cfg!(foo)); }
            "#,
        )
        .file(
            ".cargo/config.toml",
            &format!(
                "
                target-applies-to-host = false

                [host.{}]
                rustflags = [\"--cfg=foo\"]
                ",
                host
            ),
        )
        .build();

    p.cargo("check --target")
        .arg(host)
        .masquerade_as_nightly_cargo(&["target-applies-to-host", "host-config"])
        .arg("-Ztarget-applies-to-host")
        .arg("-Zhost-config")
        .run();
}

// target.{}.rustflags takes precedence over build.rustflags
#[cargo_test]
fn target_rustflags_precedence() {
    let p = project()
        .file("src/lib.rs", "")
        .file("src/bin/a.rs", "fn main() {}")
        .file("examples/b.rs", "fn main() {}")
        .file("tests/c.rs", "#[test] fn f() { }")
        .file(
            ".cargo/config.toml",
            &format!(
                "
            [build]
            rustflags = [\"--cfg\", \"foo\"]

            [target.{}]
            rustflags = [\"-Z\", \"bogus\"]
            ",
                rustc_host()
            ),
        )
        .build();

    p.cargo("check --lib")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("check --bin=a")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("check --example=b")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("test")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
    p.cargo("bench")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to run `rustc` to learn about target-specific information

Caused by:
  [..]bogus[..]
...
"#]])
        .run();
}

#[cargo_test]
fn cfg_rustflags_normal_source() {
    let p = project()
        .file("src/lib.rs", "pub fn t() {}")
        .file("src/bin/a.rs", "fn main() {}")
        .file("examples/b.rs", "fn main() {}")
        .file("tests/c.rs", "#[test] fn f() { }")
        .file(
            ".cargo/config.toml",
            &format!(
                r#"
                [target.'cfg({})']
                rustflags = ["--cfg", "bar"]
                "#,
                if rustc_host().contains("-windows-") {
                    "windows"
                } else {
                    "not(windows)"
                }
            ),
        )
        .build();

    p.cargo("build --lib -v")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..] --cfg bar`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("build --bin=a -v")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name a [..] --cfg bar`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("build --example=b -v")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name b [..] --cfg bar`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("test --no-run -v")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc [..] --cfg bar`
[RUNNING] `rustc [..] --cfg bar`
[RUNNING] `rustc [..] --cfg bar`
[FINISHED] `test` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[EXECUTABLE] `[ROOT]/foo/target/debug/deps/foo-[HASH][EXE]`
[EXECUTABLE] `[ROOT]/foo/target/debug/deps/a-[HASH][EXE]`
[EXECUTABLE] `[ROOT]/foo/target/debug/deps/c-[HASH][EXE]`

"#]])
        .run();

    p.cargo("bench --no-run -v")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc [..] --cfg bar`
[RUNNING] `rustc [..] --cfg bar`
[RUNNING] `rustc [..] --cfg bar`
[FINISHED] `bench` profile [optimized] target(s) in [ELAPSED]s
[EXECUTABLE] `[ROOT]/foo/target/release/deps/foo-[HASH][EXE]`
[EXECUTABLE] `[ROOT]/foo/target/release/deps/a-[HASH][EXE]`

"#]])
        .run();
}

// target.'cfg(...)'.rustflags takes precedence over build.rustflags
#[cargo_test]
fn cfg_rustflags_precedence() {
    let p = project()
        .file("src/lib.rs", "pub fn t() {}")
        .file("src/bin/a.rs", "fn main() {}")
        .file("examples/b.rs", "fn main() {}")
        .file("tests/c.rs", "#[test] fn f() { }")
        .file(
            ".cargo/config.toml",
            &format!(
                r#"
                [build]
                rustflags = ["--cfg", "foo"]

                [target.'cfg({})']
                rustflags = ["--cfg", "bar"]
                "#,
                if rustc_host().contains("-windows-") {
                    "windows"
                } else {
                    "not(windows)"
                }
            ),
        )
        .build();

    p.cargo("build --lib -v")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..] --cfg bar`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("build --bin=a -v")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name a [..] --cfg bar`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("build --example=b -v")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name b [..] --cfg bar`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("test --no-run -v")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc [..] --cfg bar`
[RUNNING] `rustc [..] --cfg bar`
[RUNNING] `rustc [..] --cfg bar`
[FINISHED] `test` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[EXECUTABLE] `[ROOT]/foo/target/debug/deps/foo-[HASH][EXE]`
[EXECUTABLE] `[ROOT]/foo/target/debug/deps/a-[HASH][EXE]`
[EXECUTABLE] `[ROOT]/foo/target/debug/deps/c-[HASH][EXE]`

"#]])
        .run();

    p.cargo("bench --no-run -v")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc [..] --cfg bar`
[RUNNING] `rustc [..] --cfg bar`
[RUNNING] `rustc [..] --cfg bar`
[FINISHED] `bench` profile [optimized] target(s) in [ELAPSED]s
[EXECUTABLE] `[ROOT]/foo/target/release/deps/foo-[HASH][EXE]`
[EXECUTABLE] `[ROOT]/foo/target/release/deps/a-[HASH][EXE]`

"#]])
        .run();
}

#[cargo_test]
fn target_rustflags_string_and_array_form1() {
    let p1 = project()
        .file("src/lib.rs", "")
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            rustflags = ["--cfg", "foo"]
            "#,
        )
        .build();

    p1.cargo("check -v")
        .with_stderr_data(str![[r#"
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..] --cfg foo`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    let p2 = project()
        .file("src/lib.rs", "")
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            rustflags = "--cfg foo"
            "#,
        )
        .build();

    p2.cargo("check -v")
        .with_stderr_data(str![[r#"
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..] --cfg foo`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn target_rustflags_string_and_array_form2() {
    let p1 = project()
        .file(
            ".cargo/config.toml",
            &format!(
                r#"
                    [target.{}]
                    rustflags = ["--cfg", "foo"]
                "#,
                rustc_host()
            ),
        )
        .file("src/lib.rs", "")
        .build();

    p1.cargo("check -v")
        .with_stderr_data(str![[r#"
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..] --cfg foo`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    let p2 = project()
        .file(
            ".cargo/config.toml",
            &format!(
                r#"
                    [target.{}]
                    rustflags = "--cfg foo"
                "#,
                rustc_host()
            ),
        )
        .file("src/lib.rs", "")
        .build();

    p2.cargo("check -v")
        .with_stderr_data(str![[r#"
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..] --cfg foo`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn two_matching_in_config() {
    let p1 = project()
        .file(
            ".cargo/config.toml",
            r#"
                [target.'cfg(unix)']
                rustflags = ["--cfg", 'foo="a"']
                [target.'cfg(windows)']
                rustflags = ["--cfg", 'foo="a"']
                [target.'cfg(target_pointer_width = "32")']
                rustflags = ["--cfg", 'foo="b"']
                [target.'cfg(target_pointer_width = "64")']
                rustflags = ["--cfg", 'foo="b"']
            "#,
        )
        .file(
            "src/main.rs",
            r#"
                #![allow(unexpected_cfgs)]
                fn main() {
                    if cfg!(foo = "a") {
                        println!("a");
                    } else if cfg!(foo = "b") {
                        println!("b");
                    } else {
                        panic!()
                    }
                }
            "#,
        )
        .build();

    p1.cargo("run").run();
    p1.cargo("build")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn env_rustflags_misspelled() {
    let p = project().file("src/main.rs", "fn main() { }").build();

    for cmd in &["check", "build", "run", "test", "bench"] {
        p.cargo(cmd)
            .env("RUST_FLAGS", "foo")
            .with_stderr_data(str![[r#"
[WARNING] ignoring environment variable `RUST_FLAGS`
  |
  = [HELP] rust flags are passed via `RUSTFLAGS`
...
"#]])
            .run();
    }
}

#[cargo_test]
fn env_rustflags_misspelled_build_script() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"
                build = "build.rs"
            "#,
        )
        .file("src/lib.rs", "")
        .file("build.rs", "fn main() { }")
        .build();

    p.cargo("check")
        .env("RUST_FLAGS", "foo")
        .with_stderr_data(str![[r#"
[WARNING] ignoring environment variable `RUST_FLAGS`
  |
  = [HELP] rust flags are passed via `RUSTFLAGS`
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn remap_path_prefix_works() {
    // Check that remap-path-prefix works.
    Package::new("bar", "0.1.0")
        .file("src/lib.rs", "pub fn f() -> &'static str { file!() }")
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "foo"
            version = "0.1.0"

            [dependencies]
            bar = "0.1"
            "#,
        )
        .file(
            "src/main.rs",
            r#"
            fn main() {
                println!("{}", bar::f());
            }
            "#,
        )
        .build();

    p.cargo("run")
        .env(
            "RUSTFLAGS",
            format!("--remap-path-prefix={}=/foo", paths::root().display()),
        )
        .with_stdout_data(str![[r#"
/foo/home/.cargo/registry/src/-[HASH]/bar-0.1.0/src/lib.rs

"#]])
        .run();
}

#[cargo_test]
fn rustflags_remap_path_prefix_ignored_for_c_metadata() {
    let p = project().file("src/lib.rs", "").build();

    let build_output = p
        .cargo("build -v")
        .env(
            "RUSTFLAGS",
            "--remap-path-prefix=/abc=/zoo --remap-path-prefix /spaced=/zoo",
        )
        .run();
    let first_c_metadata = dbg!(get_c_metadata(build_output));

    p.cargo("clean").run();

    let build_output = p
        .cargo("build -v")
        .env(
            "RUSTFLAGS",
            "--remap-path-prefix=/def=/zoo --remap-path-prefix /earth=/zoo",
        )
        .run();
    let second_c_metadata = dbg!(get_c_metadata(build_output));

    assert_data_eq!(first_c_metadata, second_c_metadata);
}

#[cargo_test]
fn rustc_remap_path_prefix_ignored_for_c_metadata() {
    let p = project().file("src/lib.rs", "").build();

    let build_output = p
        .cargo("rustc -v -- --remap-path-prefix=/abc=/zoo --remap-path-prefix /spaced=/zoo")
        .run();
    let first_c_metadata = dbg!(get_c_metadata(build_output));

    p.cargo("clean").run();

    let build_output = p
        .cargo("rustc -v -- --remap-path-prefix=/def=/zoo --remap-path-prefix /earth=/zoo")
        .run();
    let second_c_metadata = dbg!(get_c_metadata(build_output));

    assert_data_eq!(first_c_metadata, second_c_metadata);
}

// `--remap-path-prefix` is meant to take two different binaries and make them the same but the
// rlib name, including `-Cextra-filename`, can still end up in the binary so it can't change
#[cargo_test]
fn rustflags_remap_path_prefix_ignored_for_c_extra_filename() {
    let p = project().file("src/lib.rs", "").build();

    let build_output = p
        .cargo("build -v")
        .env(
            "RUSTFLAGS",
            "--remap-path-prefix=/abc=/zoo --remap-path-prefix /spaced=/zoo",
        )
        .run();
    let first_c_extra_filename = dbg!(get_c_extra_filename(build_output));

    p.cargo("clean").run();

    let build_output = p
        .cargo("build -v")
        .env(
            "RUSTFLAGS",
            "--remap-path-prefix=/def=/zoo --remap-path-prefix /earth=/zoo",
        )
        .run();
    let second_c_extra_filename = dbg!(get_c_extra_filename(build_output));

    assert_data_eq!(first_c_extra_filename, second_c_extra_filename);
}

// `--remap-path-prefix` is meant to take two different binaries and make them the same but the
// rlib name, including `-Cextra-filename`, can still end up in the binary so it can't change
#[cargo_test]
fn rustc_remap_path_prefix_ignored_for_c_extra_filename() {
    let p = project().file("src/lib.rs", "").build();

    let build_output = p
        .cargo("rustc -v -- --remap-path-prefix=/abc=/zoo --remap-path-prefix /spaced=/zoo")
        .run();
    let first_c_extra_filename = dbg!(get_c_extra_filename(build_output));

    p.cargo("clean").run();

    let build_output = p
        .cargo("rustc -v -- --remap-path-prefix=/def=/zoo --remap-path-prefix /earth=/zoo")
        .run();
    let second_c_extra_filename = dbg!(get_c_extra_filename(build_output));

    assert_data_eq!(first_c_extra_filename, second_c_extra_filename);
}

fn get_c_metadata(output: RawOutput) -> String {
    let get_c_metadata_re =
        regex::Regex::new(r".* (--crate-name [^ ]+).* (-C ?metadata=[^ ]+).*").unwrap();

    let stderr = String::from_utf8(output.stderr).unwrap();
    let mut c_metadata = get_c_metadata_re
        .captures_iter(&stderr)
        .map(|c| {
            let (_, [name, c_metadata]) = c.extract();
            format!("{name} {c_metadata}")
        })
        .collect::<Vec<_>>();
    assert!(
        !c_metadata.is_empty(),
        "`{get_c_metadata_re:?}` did not match:\n```\n{stderr}\n```"
    );
    c_metadata.sort();
    c_metadata.join("\n")
}

fn get_c_extra_filename(output: RawOutput) -> String {
    let get_c_extra_filename_re =
        regex::Regex::new(r".* (--crate-name [^ ]+).* (-C ?extra-filename=[^ ]+).*").unwrap();

    let stderr = String::from_utf8(output.stderr).unwrap();
    let mut c_extra_filename = get_c_extra_filename_re
        .captures_iter(&stderr)
        .map(|c| {
            let (_, [name, c_extra_filename]) = c.extract();
            format!("{name} {c_extra_filename}")
        })
        .collect::<Vec<_>>();
    assert!(
        !c_extra_filename.is_empty(),
        "`{get_c_extra_filename_re:?}` did not match:\n```\n{stderr}\n```"
    );
    c_extra_filename.sort();
    c_extra_filename.join("\n")
}

#[cargo_test]
fn host_config_rustflags_with_target() {
    // regression test for https://github.com/rust-lang/cargo/issues/10206
    let p = project()
        .file("src/lib.rs", "")
        .file("build.rs", "fn main() { assert!(cfg!(foo)); }")
        .file(".cargo/config.toml", "target-applies-to-host = false")
        .build();

    p.cargo("check")
        .masquerade_as_nightly_cargo(&["target-applies-to-host", "host-config"])
        .arg("-Zhost-config")
        .arg("-Ztarget-applies-to-host")
        .arg("-Zunstable-options")
        .arg("--config")
        .arg("host.rustflags=[\"--cfg=foo\"]")
        .run();
}

#[cargo_test]
fn target_applies_to_host_rustflags_works() {
    // Ensures that rustflags are passed to the target when
    // target_applies_to_host=false
    let p = project()
        .file(
            "src/lib.rs",
            r#"#[cfg(feature = "flag")] compile_error!("flag passed");"#,
        )
        .build();

    // Use RUSTFLAGS to pass an argument that will generate an error.
    p.cargo("check")
        .masquerade_as_nightly_cargo(&["target-applies-to-host"])
        .arg("-Ztarget-applies-to-host")
        .env("CARGO_TARGET_APPLIES_TO_HOST", "false")
        .env("RUSTFLAGS", r#"--cfg feature="flag""#)
        .with_status(101)
        .with_stderr_data(
            "[CHECKING] foo v0.0.1 ([ROOT]/foo)
[ERROR] flag passed
...",
        )
        .run();
}

#[cargo_test]
fn target_applies_to_host_rustdocflags_works() {
    // Ensures that rustflags are passed to the target when
    // target_applies_to_host=false
    let p = project()
        .file(
            "src/lib.rs",
            r#"#[cfg(feature = "flag")] compile_error!("flag passed");"#,
        )
        .build();

    // Use RUSTFLAGS to pass an argument that would generate an error
    // but it is ignored.
    p.cargo("doc")
        .masquerade_as_nightly_cargo(&["target-applies-to-host"])
        .arg("-Ztarget-applies-to-host")
        .env("CARGO_TARGET_APPLIES_TO_HOST", "false")
        .env("RUSTDOCFLAGS", r#"--cfg feature="flag""#)
        .with_status(101)
        .with_stderr_data(
            "[DOCUMENTING] foo v0.0.1 ([ROOT]/foo)
[ERROR] flag passed
...",
        )
        .run();
}

#[cargo_test]
fn host_config_shared_build_dep() {
    // rust-lang/cargo#14253
    Package::new("cc", "1.0.0").publish();
    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "bootstrap"
            edition = "2021"

            [dependencies]
            cc = "1.0.0"

            [build-dependencies]
            cc = "1.0.0"

            [profile.dev]
            debug = 0
            "#,
        )
        .file("src/lib.rs", "")
        .file("build.rs", "fn main() {}")
        .file(
            ".cargo/config.toml",
            "
            target-applies-to-host=false

            [host]
            rustflags = ['--cfg', 'from_host']

            [build]
            rustflags = ['--cfg', 'from_target']
            ",
        )
        .build();

    p.cargo("build -v")
        .masquerade_as_nightly_cargo(&["target-applies-to-host"])
        .arg("-Ztarget-applies-to-host")
        .arg("-Zhost-config")
        .with_stderr_data(
            str![[r#"
[UPDATING] `dummy-registry` index
[LOCKING] 1 package to highest compatible version
[DOWNLOADING] crates ...
[DOWNLOADED] cc v1.0.0 (registry `dummy-registry`)
[COMPILING] cc v1.0.0
[RUNNING] `rustc --crate-name cc [..]--cfg from_host[..]`
[RUNNING] `rustc --crate-name cc [..]--cfg from_target[..]`
[COMPILING] bootstrap v0.0.0 ([ROOT]/foo)
[RUNNING] `rustc --crate-name build_script_build [..]--cfg from_host[..]`
[RUNNING] `[ROOT]/foo/target/debug/build/bootstrap-[HASH]/build-script-build`
[RUNNING] `rustc --crate-name bootstrap[..]--cfg from_target[..]`
[FINISHED] `dev` profile [unoptimized] target(s) in [ELAPSED]s

"#]]
            .unordered(),
        )
        .run();
}
