//! Retained command plans must preserve ordinary build, test, and bench behavior.

#![cfg(unix)]

use std::fs;

use crate::ohm_session::{Session, change, fixture};
use crate::prelude::*;
use cargo_test_support::{rustc_host, str};
use serde_json::Value;

fn plan_id(response: &Value) -> u64 {
    response["plan_id"]
        .as_u64()
        .unwrap_or_else(|| panic!("missing command plan: {response}"))
}

fn assert_same_plan(response: &Value, previous: &Value) {
    assert_eq!(response["pid"], previous["pid"], "{response}");
    assert_eq!(plan_id(response), plan_id(previous), "{response}");
    assert_eq!(response["reused"], true, "{response}");
}

fn app_artifact(response: &Value) -> Value {
    response["stdout"]
        .as_str()
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).unwrap())
        .find(|message| {
            message["reason"] == "compiler-artifact" && message["target"]["name"] == "app"
        })
        .unwrap_or_else(|| panic!("missing app artifact: {response}"))
}

fn installed_clippy_rustc() -> Option<std::path::PathBuf> {
    // Clippy is optional in Cargo's test toolchain. Check only availability and
    // compiler identity here; any failure through the session remains a failure.
    let sysroot = cargo_test_support::process("rustc")
        .args(&["--print", "sysroot"])
        .exec_with_output()
        .unwrap();
    let sysroot = std::path::PathBuf::from(String::from_utf8(sysroot.stdout).unwrap().trim());
    let rustc = sysroot.join("bin/rustc");
    let driver = sysroot.join("bin/clippy-driver");
    if !driver.is_file() {
        eprintln!(
            "skipping real Clippy test: no installed driver at {}",
            driver.display()
        );
        return None;
    }
    let rustc_version = cargo_test_support::process(&rustc)
        .arg("-vV")
        .exec_with_output()
        .unwrap();
    let Ok(driver_version) = cargo_test_support::process(&driver)
        .args(&["--rustc", "-vV"])
        .exec_with_output()
    else {
        eprintln!("skipping real Clippy test: installed driver cannot run");
        return None;
    };
    if rustc_version.stdout != driver_version.stdout {
        eprintln!("skipping real Clippy test: installed driver does not match rustc");
        return None;
    }

    Some(rustc)
}

#[cargo_test]
fn commands_keep_distinct_plans_and_tests_execute_on_every_request() {
    let p = fixture();
    p.change_file(
        "src/lib.rs",
        r#"
            pub fn answer() -> u32 { dep::value() }

            #[test]
            fn records_execution() {
                use std::io::Write;
                std::fs::OpenOptions::new().create(true).append(true)
                    .open("test-runs").unwrap().write_all(b"x").unwrap();
            }
        "#,
    );
    p.change_file("test-runs", "");
    let session = Session::start(&p, &[]);
    let checked = session.request("check", &[], true);
    let built = session.request("build", &[], true);
    let tested = session.request("test", &[], true);
    assert_ne!(plan_id(&checked), plan_id(&built));
    assert_ne!(plan_id(&built), plan_id(&tested));
    assert_ne!(plan_id(&checked), plan_id(&tested));
    assert_eq!(tested["preparations"], 3, "{tested}");
    assert_eq!(tested["cached_plans"], 3, "{tested}");
    assert_eq!(p.read_file("test-runs"), "x");

    let checked_again = session.request("check", &[], true);
    assert_same_plan(&checked_again, &checked);
    assert_eq!(checked_again["preparations"], 3, "{checked_again}");
    let tested_again = session.request("test", &[], true);
    assert_same_plan(&tested_again, &tested);
    assert_eq!(tested_again["preparations"], 3, "{tested_again}");
    assert_eq!(tested_again["checks"], 5, "{tested_again}");
    assert_eq!(p.read_file("test-runs"), "xx");
}

#[cargo_test]
fn test_compile_errors_and_process_exit_codes_recover_independently() {
    let p = fixture();
    p.change_file(
        "Cargo.toml",
        &format!(
            "{}\n[[test]]\nname = \"outcome\"\nharness = false\n",
            p.read_file("Cargo.toml")
        ),
    );
    p.change_file("tests/outcome.rs", "fn main() { let _: u32 = \"broken\"; }");
    p.change_file("exit-code", "42");
    p.change_file("test-runs", "");
    let session = Session::start(&p, &[]);
    let args = ["--test", "outcome"];
    let broken = session.request("test", &args, false);
    assert_eq!(broken["returncode"], 101, "{broken}");
    assert!(
        broken["stderr"]
            .as_str()
            .unwrap()
            .contains("mismatched types"),
        "{broken}"
    );
    assert_eq!(p.read_file("test-runs"), "");

    change(
        &p,
        "tests/outcome.rs",
        r#"
            fn main() {
                use std::io::Write;
                std::fs::OpenOptions::new().create(true).append(true)
                    .open("test-runs").unwrap().write_all(b"x").unwrap();
                let code = std::fs::read_to_string("exit-code").unwrap()
                    .trim().parse().unwrap();
                std::process::exit(code);
            }
        "#,
    );
    let failed = session.request("test", &args, false);
    assert_same_plan(&failed, &broken);
    assert_eq!(failed["returncode"], 42, "{failed}");
    assert_eq!(p.read_file("test-runs"), "x");

    // Only a runtime input changes: fresh test artifacts must still execute.
    p.change_file("exit-code", "0");
    let recovered = session.request("test", &args, true);
    assert_same_plan(&recovered, &broken);
    assert_eq!(p.read_file("test-runs"), "xx");
}

#[cargo_test]
fn tests_that_change_the_manifest_execute_once_and_retire_the_plan() {
    let p = fixture();
    p.change_file(
        "src/lib.rs",
        r#"
            #[test]
            fn changes_planning_inputs() {
                use std::io::Write;
                std::fs::OpenOptions::new().create(true).append(true)
                    .open("test-runs").unwrap().write_all(b"x").unwrap();
                std::fs::OpenOptions::new().append(true)
                    .open("Cargo.toml").unwrap()
                    .write_all(b"\n# changed by the test\n").unwrap();
            }
        "#,
    );
    p.change_file("test-runs", "");
    let session = Session::start(&p, &[]);
    let first = session.request("test", &[], true);
    assert_eq!(p.read_file("test-runs"), "x");
    assert_eq!(first["cached_plans"], 0, "{first}");

    let second = session.request("test", &[], true);
    assert_eq!(p.read_file("test-runs"), "xx");
    assert_ne!(plan_id(&second), plan_id(&first));
    assert_eq!(second["preparations"], 2, "{second}");
    assert_eq!(second["checks"], 2, "{second}");
    assert_eq!(second["cached_plans"], 0, "{second}");
}

#[cargo_test]
fn test_filters_no_run_and_doctests_match_ordinary_commands() {
    let p = fixture();
    p.change_file(
        "src/lib.rs",
        r#"
            /// Records one invocation.
            ///
            ///     app::record("doc-runs");
            pub fn record(path: &str) {
                use std::io::Write;
                std::fs::OpenOptions::new().create(true).append(true)
                    .open(path).unwrap().write_all(b"x").unwrap();
            }

            #[cfg(test)]
            mod tests {
                #[test]
                fn selected() { super::record("selected-runs"); }

                #[test]
                fn selected_suffix() { panic!("the exact filter was lost"); }
            }
        "#,
    );
    p.change_file("selected-runs", "");
    p.change_file("doc-runs", "");
    let session = Session::start(&p, &[]);
    let args = ["--lib", "tests::selected", "--", "--exact"];
    session.request("test", &args, true);
    assert_eq!(p.read_file("selected-runs"), "x");
    assert_eq!(p.read_file("doc-runs"), "");

    session.request("test", &["--lib", "--no-run"], true);
    assert_eq!(p.read_file("selected-runs"), "x");
    session.request("test", &["--doc"], true);
    assert_eq!(p.read_file("selected-runs"), "x");
    assert_eq!(p.read_file("doc-runs"), "x");
    let invalid = session.request("test", &["--doc", "--no-run"], false);
    assert!(
        invalid["stderr"]
            .as_str()
            .unwrap()
            .contains("can't skip running doc tests with --no-run"),
        "{invalid}"
    );

    p.cargo("test --offline -p app").args(&args).run();
    p.cargo("test --offline -p app --doc").run();
    assert_eq!(p.read_file("selected-runs"), "xx");
    assert_eq!(p.read_file("doc-runs"), "xx");
}

#[cargo_test]
fn features_profiles_and_targets_select_isolated_reusable_plans() {
    let p = fixture();
    p.change_file(
        "src/lib.rs",
        r#"
            #[cfg(all(feature = "selected", feature = "changed"))]
            compile_error!("request features should replace startup defaults");
            pub fn answer() -> u32 { dep::value() }
        "#,
    );
    let session = Session::start(&p, &["--features", "selected"]);
    let args = ["--message-format=json"];
    let debug = session.request("check", &args, true);
    assert_eq!(
        app_artifact(&debug)["features"],
        serde_json::json!(["selected"])
    );
    assert_eq!(app_artifact(&debug)["profile"]["opt_level"], "0");

    let changed = session.request(
        "check",
        &["--features", "changed", "--message-format=json"],
        true,
    );
    assert_eq!(
        app_artifact(&changed)["features"],
        serde_json::json!(["changed"])
    );
    let release = session.request("check", &["--release", "--message-format=json"], true);
    assert_eq!(app_artifact(&release)["profile"]["opt_level"], "3");

    let host = rustc_host();
    let targeted = session.request("check", &["--target", &host, "--message-format=json"], true);
    assert!(
        app_artifact(&targeted)["filenames"]
            .as_array()
            .unwrap()
            .iter()
            .all(|filename| filename
                .as_str()
                .unwrap()
                .contains(&format!("/{host}/debug/"))),
        "{targeted}"
    );
    let ids = [
        plan_id(&debug),
        plan_id(&changed),
        plan_id(&release),
        plan_id(&targeted),
    ];
    for (index, id) in ids.iter().enumerate() {
        assert!(
            !ids[..index].contains(id),
            "plans were not isolated: {ids:?}"
        );
    }

    let returned = session.request("check", &args, true);
    assert_same_plan(&returned, &debug);
    assert_eq!(returned["preparations"], 4, "{returned}");
    assert_eq!(returned["cached_plans"], 4, "{returned}");
    assert_eq!(
        app_artifact(&returned)["features"],
        serde_json::json!(["selected"])
    );
}

#[cargo_test]
fn reaching_the_plan_limit_releases_the_arena_and_assigns_new_ids() {
    let p = fixture();
    let session = Session::start(&p, &["--max-plans", "2"]);
    let checked = session.request("check", &[], true);
    let built = session.request("build", &[], true);
    assert_eq!(built["cached_plans"], 2, "{built}");

    let tested = session.request("test", &["--no-run"], true);
    assert_eq!(tested["cached_plans"], 1, "{tested}");
    assert_eq!(tested["preparations"], 3, "{tested}");
    let checked_again = session.request("check", &[], true);
    assert_ne!(plan_id(&checked_again), plan_id(&checked));
    assert_eq!(checked_again["reused"], false, "{checked_again}");
    assert_eq!(checked_again["cached_plans"], 2, "{checked_again}");
    assert_eq!(checked_again["preparations"], 4, "{checked_again}");
    assert_eq!(checked_again["checks"], 4, "{checked_again}");
}

#[cargo_test]
fn test_execution_observes_build_script_and_proc_macro_edits() {
    let p = fixture();
    p.change_file(
        "dep/Cargo.toml",
        &format!(
            "{}\n[lib]\nproc-macro = true\n",
            p.read_file("dep/Cargo.toml")
        ),
    );
    let macro_source = |expansion: &str| {
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
    p.change_file("dep/src/lib.rs", &macro_source("1u32"));
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
    p.change_file("build-input.rs", "pub fn generated() -> u32 { 10 }");
    p.change_file("expected", "11");
    p.change_file(
        "src/lib.rs",
        r#"
            include!(concat!(env!("OUT_DIR"), "/generated.rs"));
            pub fn answer() -> u32 { dep::value!() + generated() }

            #[test]
            fn observes_generated_inputs() {
                use std::io::Write;
                let expected: u32 = std::fs::read_to_string("expected").unwrap()
                    .trim().parse().unwrap();
                assert_eq!(answer(), expected);
                std::fs::OpenOptions::new().create(true).append(true)
                    .open("test-runs").unwrap().write_all(b"x").unwrap();
            }
        "#,
    );
    p.change_file("test-runs", "");
    let session = Session::start(&p, &[]);
    let first = session.request("test", &[], true);
    change(&p, "build-input.rs", "pub fn generated() -> u32 { 20 }");
    p.change_file("expected", "21");
    assert_same_plan(&session.request("test", &[], true), &first);

    change(&p, "dep/src/lib.rs", &macro_source("2u32"));
    p.change_file("expected", "22");
    assert_same_plan(&session.request("test", &[], true), &first);
    assert_eq!(p.read_file("test-runs"), "xxx");

    change(&p, "dep/src/lib.rs", &macro_source("false"));
    let broken = session.request("test", &[], false);
    assert_same_plan(&broken, &first);
    assert_eq!(broken["returncode"], 101, "{broken}");
    assert_eq!(p.read_file("test-runs"), "xxx");

    change(&p, "dep/src/lib.rs", &macro_source("3u32"));
    p.change_file("expected", "23");
    assert_same_plan(&session.request("test", &[], true), &first);
    assert_eq!(p.read_file("test-runs"), "xxxx");
}

#[cargo_test]
fn benchmarks_preserve_no_run_forwarded_arguments_and_failure_modes() {
    let p = fixture();
    p.change_file(
        "Cargo.toml",
        &format!(
            "{}\n[[bench]]\nname = \"first\"\nharness = false\n\
             [[bench]]\nname = \"second\"\nharness = false\n",
            p.read_file("Cargo.toml")
        ),
    );
    for (name, code) in [("first", 7), ("second", 0)] {
        p.change_file(
            &format!("benches/{name}.rs"),
            &format!(
                r#"
                    fn main() {{
                        use std::io::Write;
                        let args: Vec<_> = std::env::args().skip(1).collect();
                        assert_eq!(args, ["needle", "--exact", "--bench"]);
                        std::fs::write("{name}-args", args.join("\n")).unwrap();
                        std::fs::OpenOptions::new().create(true).append(true)
                            .open("{name}-runs").unwrap().write_all(b"x").unwrap();
                        std::process::exit({code});
                    }}
                "#
            ),
        );
    }
    for name in ["first", "second"] {
        p.change_file(&format!("{name}-runs"), "");
        p.change_file(&format!("{name}-args"), "");
    }
    let session = Session::start(&p, &[]);
    session.request(
        "bench",
        &["--bench", "first", "--bench", "second", "--no-run"],
        true,
    );
    assert_eq!(p.read_file("first-runs"), "");
    assert_eq!(p.read_file("second-runs"), "");

    let args = [
        "--bench", "first", "--bench", "second", "needle", "--", "--exact",
    ];
    let failed = session.request("bench", &args, false);
    assert_eq!(failed["returncode"], 7, "{failed}");
    assert_eq!(p.read_file("first-runs"), "x");
    assert_eq!(p.read_file("second-runs"), "");

    let mut all = vec!["--no-fail-fast"];
    all.extend_from_slice(&args);
    let continued = session.request("bench", &all, false);
    assert_eq!(continued["returncode"], 101, "{continued}");
    assert_eq!(p.read_file("first-runs"), "xx");
    assert_eq!(p.read_file("second-runs"), "x");
    for name in ["first", "second"] {
        assert_eq!(
            fs::read_to_string(p.root().join(format!("{name}-args"))).unwrap(),
            "needle\n--exact\n--bench"
        );
    }

    p.cargo("bench --offline -p app")
        .args(&all)
        .with_status(101)
        .with_stderr_data(str![[r#"
...
[FINISHED] `bench` profile [optimized] target(s) in [ELAPSED]s
[RUNNING] benches/first.rs (target/release/deps/first-[HASH][EXE])
[ERROR] bench failed, to rerun pass `-p app --bench first`

Caused by:
  process didn't exit successfully: `[ROOT]/workspace with spaces/target/release/deps/first-[HASH][EXE] needle --exact --bench` ([EXIT_STATUS]: 7)
[RUNNING] benches/second.rs (target/release/deps/second-[HASH][EXE])
[ERROR] 1 target failed:
    `-p app --bench first`

"#]])
        .run();
    assert_eq!(p.read_file("first-runs"), "xxx");
    assert_eq!(p.read_file("second-runs"), "xx");
}

#[cargo_test]
fn aliased_tests_preserve_the_leading_separator_and_ignored_filter() {
    let p = fixture();
    p.change_file(
        ".cargo/config.toml",
        "[alias]\nsession-tests = 'session test'\n",
    );
    p.change_file(
        "src/lib.rs",
        r#"
            #[test]
            fn ordinary() { panic!("the ignored filter was lost"); }

            #[test]
            #[ignore]
            fn requested() {
                use std::io::Write;
                std::fs::OpenOptions::new().append(true)
                    .open("test-runs").unwrap().write_all(b"x").unwrap();
            }
        "#,
    );
    p.change_file("test-runs", "");
    let session = Session::start(&p, &[]);
    let aliased = session.request_alias("session-tests", "test", &["--", "--ignored"], true);
    assert_eq!(p.read_file("test-runs"), "x");
    let direct = session.request("test", &["--", "--ignored"], true);
    assert_same_plan(&direct, &aliased);
    assert_eq!(p.read_file("test-runs"), "xx");
}

#[cargo_test]
fn clippy_aliases_lint_arguments_and_config_changes_preserve_check_isolation() {
    let Some(rustc) = installed_clippy_rustc() else {
        return;
    };

    let p = fixture();
    p.change_file(
        ".cargo/config.toml",
        "[alias]\nsession-lint = 'session clippy'\n",
    );
    p.change_file("clippy.toml", "disallowed-names = []\n");
    p.change_file(
        "src/lib.rs",
        r#"
            #[cfg(feature = "changed")]
            const _: () = assert!(option_env!("CLIPPY_ARGS").is_none());
            #[cfg(feature = "changed")]
            const _: () = assert!(option_env!("RUSTC_WORKSPACE_WRAPPER").is_none());

            pub fn answer() -> u32 {
                let unused = 0;
                let blocked = dep::value();
                std::hint::black_box(blocked)
            }
        "#,
    );
    let session = Session::start_with_env(&p, &[], &[("RUSTC", rustc.into_os_string())]);
    let checked = session.request("check", &[], true);
    let allowed = session.request("clippy", &["--", "-Awarnings"], true);
    let denied = session.request_alias("session-lint", "clippy", &["--", "-Dwarnings"], false);
    assert_eq!(denied["returncode"], 101, "{denied}");
    assert!(
        denied["stderr"]
            .as_str()
            .unwrap()
            .contains("unused variable"),
        "{denied}"
    );
    assert_same_plan(
        &session.request("clippy", &["--", "-Awarnings"], true),
        &allowed,
    );

    // A newly compiled check observes neither the wrapper nor its lint overlay.
    session.request("check", &["--features", "changed"], true);
    let configurable = ["--", "-Aunused_variables", "-Dclippy::disallowed_names"];
    session.request("clippy", &configurable, true);
    change(&p, "clippy.toml", "disallowed-names = ['blocked']\n");
    let configured = session.request("clippy", &configurable, false);
    assert_eq!(configured["returncode"], 101, "{configured}");
    assert!(
        configured["stderr"]
            .as_str()
            .unwrap()
            .contains("disallowed")
            && configured["stderr"].as_str().unwrap().contains("blocked"),
        "{configured}"
    );
    change(&p, "clippy.toml", "disallowed-names = []\n");
    session.request("clippy", &configurable, true);
    assert_same_plan(&session.request("check", &[], true), &checked);
}

#[cargo_test]
fn clippy_fix_applies_corrections_once_and_keeps_the_check_plan_usable() {
    let Some(rustc) = installed_clippy_rustc() else {
        return;
    };
    let p = fixture();
    p.change_file(
        "src/lib.rs",
        "pub fn answer() -> u32 { return dep::value(); }\n",
    );
    let session = Session::start_with_env(&p, &[], &[("RUSTC", rustc.into_os_string())]);
    let checked = session.request("check", &[], true);
    let args = [
        "--fix",
        "--allow-no-vcs",
        "--allow-dirty",
        "--",
        "-Wclippy::needless_return",
    ];

    let fixed = session.request("clippy", &args, true);
    let fixed_source = p.read_file("src/lib.rs");
    assert_eq!(
        fixed_source.split_whitespace().collect::<String>(),
        "pubfnanswer()->u32{dep::value()}"
    );
    assert_eq!(fixed["preparations"], 2, "{fixed}");
    assert_eq!(fixed["checks"], 2, "{fixed}");
    assert!(fixed["plan_id"].is_null(), "{fixed}");
    assert!(
        fixed["reuse_disabled_reason"]
            .as_str()
            .unwrap()
            .contains("ordinary request-scoped execution"),
        "{fixed}"
    );

    assert_same_plan(&session.request("check", &[], true), &checked);
    let unchanged = session.request("clippy", &args, true);
    assert_eq!(p.read_file("src/lib.rs"), fixed_source);
    assert_eq!(unchanged["preparations"], 3, "{unchanged}");
    assert_eq!(unchanged["checks"], 4, "{unchanged}");
}
