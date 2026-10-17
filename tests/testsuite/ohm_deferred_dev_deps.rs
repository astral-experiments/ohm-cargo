#![cfg(unix)]

use crate::prelude::*;
use cargo_test_support::{Execs, Project, project};
use std::fs;
use std::hash::{DefaultHasher, Hash, Hasher};
use std::path::{Path, PathBuf};

use super::freshness::relink_only_wrapper;

fn fixture(name: &str) -> Project {
    project()
        .at(name)
        .file(
            "Cargo.toml",
            "[workspace]\nmembers=[\"app\",\"helper\"]\nresolver=\"3\"\n",
        )
        .file(
            "app/Cargo.toml",
            r#"
            [package]
            name = "app"
            version = "0.1.0"
            edition = "2024"
            [features]
            from-helper = []
            other = []
            [dev-dependencies]
            helper = { path = "../helper" }
        "#,
        )
        .file("app/src/lib.rs", &source(1, false))
        .file(
            "helper/Cargo.toml",
            r#"
            [package]
            name = "helper"
            version = "0.1.0"
            edition = "2024"
            [dependencies]
            app = { path = "../app", features = ["from-helper"] }
        "#,
        )
        .file(
            "helper/src/lib.rs",
            "pub fn value() -> u32 { app::value() }",
        )
        .build()
}

fn source(value: u32, used: bool) -> String {
    let expression = if used { "helper::value()" } else { "value()" };
    format!(
        r#"
        #[cfg(not(feature = "from-helper"))]
        compile_error!("dev dependency feature contribution was lost");
        #[inline(never)]
        pub fn value() -> u32 {{ {value} }}
        #[test]
        fn selected() {{
            assert_eq!({expression}, {value});
            use std::io::Write;
            writeln!(std::fs::OpenOptions::new().create(true).append(true)
                .open(std::env::var_os("UNUSED_TEST_RUNS").unwrap()).unwrap(), "ran").unwrap();
        }}
    "#
    )
}

fn command(p: &Project, wrapper: &Path, flags: &str) -> Execs {
    // The wrapper emulates public hashes on stock rustc, whose crate hash still
    // changes with private edits. Rebuild consumers when that metadata changes.
    let mut source_hash = DefaultHasher::new();
    fs::read(p.root().join("app/src/lib.rs"))
        .unwrap()
        .hash(&mut source_hash);
    let mut command = p.cargo(&format!(
        "test --offline -p app --lib -Zohm-defaults -Zohm-linker=lld {flags} selected -- --exact"
    ));
    command
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-linker", "ohm-defer-dev-deps"])
        .env("RUSTC_WRAPPER", wrapper)
        .env("RELINK_WRAPPER_LOG", p.root().join("compiler.log"))
        .env("UNUSED_INTEGRATION_DEPENDENCY_PROOF", "1")
        .env(
            "UNUSED_INTEGRATION_PUBLIC_HASH",
            format!("{:032x}", source_hash.finish()),
        )
        .env("UNUSED_TEST_CRATE", "app")
        .env("UNUSED_TEST_RESULTS", p.root().join("results.log"))
        .env("UNUSED_TEST_RUNS", p.root().join("runs.log"))
        .env("CARGO_LOG", "cargo::compiler::ohm_deferred_dev_deps=info");
    command
}

fn seed(p: &Project, wrapper: &Path) -> PathBuf {
    command(p, wrapper, "-Zohm-defer-dev-deps=no").run();
    let manifest = walkdir::WalkDir::new(p.root().join("target"))
        .into_iter()
        .filter_map(Result::ok)
        .map(|entry| entry.into_path())
        .find(|path| {
            path.file_name()
                .unwrap()
                .to_str()
                .is_some_and(|name| name.starts_with("app-") && name.ends_with(".rlink-cache.json"))
        })
        .expect("test executable's unused-extern proof");
    clear(p);
    manifest
}

fn clear(p: &Project) {
    for file in ["compiler.log", "results.log", "runs.log"] {
        fs::write(p.root().join(file), "").unwrap();
    }
}

fn log(p: &Project, name: &str) -> String {
    fs::read_to_string(p.root().join(name)).unwrap()
}

#[cargo_test]
fn default_preserves_features_and_opt_out_checks_unused_helpers() {
    let wrapper = relink_only_wrapper();
    let p = fixture("default-and-opt-out");
    seed(&p, &wrapper);
    p.change_file("app/src/lib.rs", &source(2, false));
    p.change_file(
        "helper/src/lib.rs",
        "compile_error!(\"unused helper is broken\");",
    );
    command(&p, &wrapper, "")
        .with_stderr_contains("[..]accepted current unused-dependency proof[..]")
        .run();
    assert_eq!(log(&p, "compiler.log"), "compile-link:app\n");
    assert_eq!(log(&p, "runs.log"), "ran\n");

    for (index, (flags, environment)) in [
        ("-Zohm-defer-dev-deps=no", None),
        ("--config unstable.ohm-defer-dev-deps=false", None),
        ("", Some(("CARGO_UNSTABLE_OHM_DEFER_DEV_DEPS", "false"))),
        ("", Some(("__CARGO_OHM_DEFER_DEV_DEPS", "no"))),
        ("-Zohm-defaults=no", None),
    ]
    .into_iter()
    .enumerate()
    {
        clear(&p);
        p.change_file("app/src/lib.rs", &source(index as u32 + 3, false));
        let mut cmd = command(&p, &wrapper, flags);
        if let Some((name, value)) = environment {
            cmd.env(name, value);
        }
        cmd.with_status(101)
            .with_stderr_contains("[..]unused helper is broken[..]")
            .with_stderr_does_not_contain("[..]deferring unused dev dependencies[..]")
            .run();
        assert!(log(&p, "runs.log").is_empty());
    }
}

#[cargo_test]
fn native_link_inputs_rebuild_unused_archives_before_running_tests() {
    let wrapper = relink_only_wrapper();
    let p = fixture("native-link-inputs");
    p.change_file(
        "helper/Cargo.toml",
        "[package]\nname=\"helper\"\nversion=\"0.1.0\"\nedition=\"2024\"\n",
    );
    let app_manifest = fs::read_to_string(p.root().join("app/Cargo.toml")).unwrap();
    p.change_file(
        "app/Cargo.toml",
        &app_manifest.replace("[features]", "[features]\ndefault = [\"from-helper\"]"),
    );
    p.change_file(
        "app/build.rs",
        r#"fn main() {
            println!("cargo:rustc-check-cfg=cfg(script_ready)");
            println!("cargo:rustc-cfg=script_ready");
            println!("cargo:rustc-env=SCRIPT_VALUE=ready");
        }"#,
    );
    let helper = |value| {
        format!("#[unsafe(no_mangle)] pub extern \"C\" fn helper_value() -> u32 {{ {value} }}\n")
    };
    p.change_file("helper/src/lib.rs", &helper(1));
    let manifest = seed(&p, &wrapper);

    // Harmless script outputs still allow deferring a dirty helper.
    p.change_file("app/src/lib.rs", &source(2, false));
    p.change_file("helper/src/lib.rs", &helper(2));
    command(&p, &wrapper, "")
        .with_stderr_contains("[..]accepted current unused-dependency proof[..]")
        .run();
    assert_eq!(log(&p, "compiler.log"), "compile-link:app\n");

    let archive = walkdir::WalkDir::new(p.root().join("target"))
        .into_iter()
        .filter_map(Result::ok)
        .map(|entry| entry.into_path())
        .find(|path| {
            path.file_name()
                .unwrap()
                .to_str()
                .is_some_and(|name| name.starts_with("libhelper-") && name.ends_with(".rlib"))
        })
        .expect("previously compiled helper archive");
    p.change_file(
        "app/build.rs",
        &format!("fn main() {{ println!(\"cargo:rustc-link-arg={{}}\", {archive:?}); }}"),
    );
    let native_test = |value| {
        format!(
            "{}\n#[cfg(test)] unsafe extern \"C\" {{ fn helper_value() -> u32; }}\n",
            source(value, false).replace(
                "assert_eq!(value(),",
                "assert_eq!(unsafe { helper_value() },"
            )
        )
    };
    p.change_file("app/src/lib.rs", &native_test(2));
    clear(&p);
    command(&p, &wrapper, "")
        .with_stderr_contains("[..]native linker inputs require complete graph[..]")
        .with_stderr_contains("[..]retrying complete graph[..]")
        .run();
    assert!(log(&p, "compiler.log").contains("compile:helper\n"));
    assert_eq!(log(&p, "results.log"), "0\n", "retry before invoking rustc");
    assert_eq!(log(&p, "runs.log"), "ran\n");
    let proof: serde_json::Value = serde_json::from_slice(&fs::read(&manifest).unwrap()).unwrap();
    assert!(proof.get("unused_extern_names").is_none());

    // Established native-link builds must not repeatedly speculate and retry.
    p.change_file("app/src/lib.rs", &native_test(3));
    p.change_file("helper/src/lib.rs", &helper(3));
    clear(&p);
    command(&p, &wrapper, "")
        .with_stderr_does_not_contain("[..]deferring unused dev dependencies[..]")
        .run();
    assert_eq!(log(&p, "results.log"), "0\n");
    assert_eq!(log(&p, "runs.log"), "ran\n");
}

#[cfg(target_os = "linux")]
#[cargo_test(requires = "cc", requires = "ar")]
fn retained_native_archive_is_rebuilt_and_unsafe_inputs_retry() {
    let wrapper = relink_only_wrapper();
    for case in [
        "search-path",
        "hard-link",
        "header-linker-script",
        "header-quoted-linker-script",
        "header-archive",
        "header-symlink",
    ] {
        let p = fixture(&format!("retained-native-inputs-{case}"));
        let manifest = fs::read_to_string(p.root().join("app/Cargo.toml")).unwrap();
        p.change_file(
            "app/Cargo.toml",
            &format!("{manifest}\n[dependencies]\nretained = {{ path = \"../retained\" }}\n"),
        );
        fs::create_dir_all(p.root().join("retained/src")).unwrap();
        p.change_file(
            "retained/Cargo.toml",
            "[package]\nname=\"retained\"\nversion=\"0.1.0\"\nedition=\"2024\"\n",
        );
        p.change_file(
        "retained/src/lib.rs",
        "unsafe extern \"C\" { fn native_value() -> u32; }\npub fn value() -> u32 { unsafe { native_value() } }\n",
    );
        let script = r##"
        fn main() {
            let out = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
            assert!(std::process::Command::new("cc").args(["-c", "native.c", "-o"])
                .arg(out.join("native.o")).status().unwrap().success());
            assert!(std::process::Command::new("ar").arg("crs")
                .arg(out.join("libretained.a")).arg(out.join("native.o"))
                .status().unwrap().success());
            // Native crates also leave headers, templates, and extensionless
            // compiler feature-probe objects in their search directories.
            std::fs::create_dir_all(out.join("include/nested")).unwrap();
            std::fs::write(out.join("include/native.h"),
                r#"/* INPUT and GROUP describe the API, not linker commands. */
// The caller's include paths can contain this header.
#define IGNORE_DEPRECATIONS \
  _Pragma("GCC diagnostic ignored \"-Wdeprecated-declarations\"")
unsigned native_value(void);
"#).unwrap();
            std::fs::write(out.join("include/nested/native.h.in"),
                "#define INPUT @INPUT@\n").unwrap();
            std::fs::write(out.join("include/nested/native.inc"),
                "%define native_value prefixed_native_value\n").unwrap();
            std::fs::write(out.join("flag_check.c"), "int main(void) { return 0; }\n").unwrap();
            assert!(std::process::Command::new("cc").arg("-c").arg(out.join("flag_check.c"))
                .arg("-o").arg(out.join("flag_check")).status().unwrap().success());
            println!("cargo:rerun-if-changed=native.c");
            println!("cargo:rustc-link-search=native={}", out.display());
            println!("cargo:rustc-link-lib=static=retained");
            // Like jemalloc, the producer has a link argument that Cargo does
            // not forward to a dependent package's library-test executable.
            println!("cargo:rustc-link-arg=-pthread");
        }
    "##;
        p.change_file("retained/build.rs", script);
        let app = |value| {
            source(value, false).replace("assert_eq!(value(),", "assert_eq!(retained::value(),")
        };
        p.change_file(
            "retained/native.c",
            "unsigned native_value(void) { return 1; }\n",
        );
        p.change_file("app/src/lib.rs", &app(1));
        let proof = seed(&p, &wrapper);
        let proof: serde_json::Value = serde_json::from_slice(&fs::read(proof).unwrap()).unwrap();
        assert!(
            proof["unused_extern_names"]
                .as_array()
                .unwrap()
                .iter()
                .any(|name| name == "helper")
        );

        p.change_file(
            "retained/native.c",
            "unsigned native_value(void) { return 2; }\n",
        );
        p.change_file("app/src/lib.rs", &app(2));
        p.change_file(
            "helper/src/lib.rs",
            "compile_error!(\"unused helper is broken\");\n",
        );
        command(&p, &wrapper, "")
            .with_stderr_contains("[..]accepted current unused-dependency proof[..]")
            .run();
        assert!(!log(&p, "compiler.log").contains("compile:helper\n"));
        assert!(!log(&p, "compiler.log").contains("compile:app\n"));
        assert!(log(&p, "compiler.log").contains("compile:retained\n"));
        assert_eq!(log(&p, "runs.log"), "ran\n");

        // Retaining a script does not make arbitrary paths or file aliases safe.
        // Revalidate its current outputs before invoking the test compiler.
        let unsafe_input = match case {
            "search-path" => {
                "println!(\"cargo:rustc-link-search=native={}\", out.join(\"..\").display());"
            }
            "hard-link" => {
                "std::fs::hard_link(out.join(\"libretained.a\"), out.join(\"alias.a\")).unwrap();"
            }
            "header-linker-script" => {
                // A verbatim native library name can select a misleadingly
                // named header. Quoted comment markers must not hide INPUT.
                r##"std::fs::write(out.join("include/forward.h"), "ASSERT(1, \"# /*\"); INPUT /* a comment */ (old-helper.rlib)\n").unwrap();"##
            }
            "header-quoted-linker-script" => {
                r#"std::fs::write(out.join("include/forward.h"), "\"INPUT\" (old-helper.rlib)\n").unwrap();"#
            }
            "header-archive" => {
                "std::fs::copy(out.join(\"libretained.a\"), out.join(\"include/forward.h\")).unwrap();"
            }
            "header-symlink" => {
                "std::os::unix::fs::symlink(out.join(\"native.o\"), out.join(\"include/forward.h\")).unwrap();"
            }
            _ => unreachable!(),
        };
        p.change_file(
            "retained/build.rs",
            &script.replace(
                "println!(\"cargo:rustc-link-lib=static=retained\");",
                &format!("println!(\"cargo:rustc-link-lib=static=retained\");\n{unsafe_input}"),
            ),
        );
        p.change_file("app/src/lib.rs", &format!("{}\n// another edit\n", app(2)));
        clear(&p);
        command(&p, &wrapper, "")
            .with_status(101)
            .with_stderr_contains("[..]native linker inputs require complete graph[..]")
            .with_stderr_contains("[..]retrying complete graph[..]")
            .with_stderr_contains("[..]unused helper is broken[..]")
            .run();
        assert!(log(&p, "results.log").is_empty());
        assert!(log(&p, "runs.log").is_empty());
    }
}

#[cargo_test]
fn new_usage_retries_even_when_stale_artifacts_compile_successfully() {
    let wrapper = relink_only_wrapper();
    let p = fixture("new-usage");
    seed(&p, &wrapper);
    p.change_file("app/src/lib.rs", &source(2, true));
    let output = command(&p, &wrapper, "--message-format=json")
        .with_stderr_contains("[..]retrying complete graph[..]")
        .run();
    assert_eq!(log(&p, "results.log"), "0\n0\n");
    assert_eq!(log(&p, "runs.log"), "ran\n");
    assert_eq!(
        log(&p, "compiler.log")
            .matches("compile-link:app\n")
            .count(),
        2
    );
    let messages: Vec<serde_json::Value> = String::from_utf8_lossy(&output.stdout)
        .lines()
        .filter_map(|line| serde_json::from_str(line).ok())
        .collect();
    assert_eq!(
        messages
            .iter()
            .filter(|message| message["reason"] == "build-finished")
            .count(),
        1
    );
    assert_eq!(
        messages
            .iter()
            .filter(|message| message["reason"] == "compiler-artifact"
                && message["executable"].is_string())
            .count(),
        1
    );

    clear(&p);
    command(&p, &wrapper, "").run();
    assert!(
        log(&p, "compiler.log").is_empty(),
        "retry must leave usable ordinary fingerprints"
    );
    assert_eq!(log(&p, "runs.log"), "ran\n");
}

#[cargo_test]
fn invalid_prior_proof_and_changed_configuration_keep_the_complete_graph() {
    let wrapper = relink_only_wrapper();
    for case in [
        "missing",
        "malformed",
        "version",
        "executable",
        "stamp",
        "features",
        "build-script",
        "renamed",
        "multiple-roots",
    ] {
        let p = fixture(case);
        let manifest = seed(&p, &wrapper);
        let mut proof: serde_json::Value =
            serde_json::from_slice(&fs::read(&manifest).unwrap()).unwrap();
        let flags = match case {
            "missing" => {
                fs::remove_file(&manifest).unwrap();
                ""
            }
            "malformed" => {
                fs::write(&manifest, "{").unwrap();
                ""
            }
            "version" | "executable" | "stamp" => {
                match case {
                    "version" => proof["version"] = 0.into(),
                    "executable" => proof["executable"]["path"] = "another-executable".into(),
                    "stamp" => proof["executable"]["modified_nanos"] = 0.into(),
                    _ => unreachable!(),
                }
                fs::write(&manifest, serde_json::to_vec(&proof).unwrap()).unwrap();
                ""
            }
            "features" => "--features=other",
            "build-script" => {
                p.change_file("helper/build.rs", "fn main() {}\n");
                ""
            }
            "renamed" => {
                let path = p.root().join("app/Cargo.toml");
                let manifest = fs::read_to_string(&path).unwrap();
                fs::write(
                    path,
                    manifest.replace("helper = { path", "renamed = { package = \"helper\", path"),
                )
                .unwrap();
                ""
            }
            "multiple-roots" => "-p helper",
            _ => unreachable!(),
        };
        p.change_file("app/src/lib.rs", &source(2, false));
        command(&p, &wrapper, flags)
            .with_stderr_does_not_contain("[..]deferring unused dev dependencies[..]")
            .run();
        assert!(log(&p, "compiler.log").contains("compile:app\n"), "{case}");
        assert_eq!(log(&p, "runs.log"), "ran\n", "{case}");
    }
}

#[cargo_test]
fn retained_dependencies_keep_their_transitive_inputs() {
    let wrapper = relink_only_wrapper();
    let p = fixture("shared-dependency");
    p.change_file(
        "Cargo.toml",
        "[workspace]\nmembers=[\"app\",\"helper\",\"bridge\"]\nresolver=\"3\"\n",
    );
    let manifest = fs::read_to_string(p.root().join("app/Cargo.toml")).unwrap();
    p.change_file(
        "app/Cargo.toml",
        &format!("{manifest}\nbridge = {{ path = \"../bridge\" }}\n"),
    );
    fs::create_dir_all(p.root().join("bridge/src")).unwrap();
    p.change_file(
        "bridge/Cargo.toml",
        r#"
        [package]
        name = "bridge"
        version = "0.1.0"
        edition = "2024"
        [dependencies]
        helper = { path = "../helper" }
    "#,
    );
    p.change_file(
        "bridge/src/lib.rs",
        "pub fn value() -> u32 { helper::value() }",
    );
    p.change_file(
        "app/src/lib.rs",
        &source(1, true).replace("helper::", "bridge::"),
    );
    let manifest = seed(&p, &wrapper);
    let proof: serde_json::Value = serde_json::from_slice(&fs::read(manifest).unwrap()).unwrap();
    assert!(
        proof["unused_extern_names"]
            .as_array()
            .unwrap()
            .contains(&"helper".into())
    );
    p.change_file(
        "app/src/lib.rs",
        &source(2, true).replace("helper::", "bridge::"),
    );
    command(&p, &wrapper, "")
        .with_stderr_does_not_contain("[..]deferring unused dev dependencies[..]")
        .run();
    assert!(log(&p, "compiler.log").contains("compile:app\n"));
    assert_eq!(log(&p, "runs.log"), "ran\n");
}

#[cargo_test]
fn current_proof_failure_retries_once_and_failure_invalidates_outputs() {
    let wrapper = relink_only_wrapper();
    for case in [
        "missing",
        "conflicting",
        "malformed",
        "compiler-error",
        "fallback-error",
        "interrupted",
    ] {
        let p = fixture(case);
        if case == "fallback-error" {
            let manifest = fs::read_to_string(p.root().join("Cargo.toml")).unwrap();
            p.change_file(
                "Cargo.toml",
                &format!("{manifest}\n[profile.test]\nsplit-debuginfo = \"packed\"\n"),
            );
        }
        let manifest = seed(&p, &wrapper);
        let proof: serde_json::Value =
            serde_json::from_slice(&fs::read(&manifest).unwrap()).unwrap();
        let executable = PathBuf::from(proof["executable"]["path"].as_str().unwrap());
        p.change_file("app/src/lib.rs", &source(2, case == "fallback-error"));
        let mut cmd = command(&p, &wrapper, "");
        let fails = matches!(case, "compiler-error" | "fallback-error" | "interrupted");
        match case {
            "missing" => {
                cmd.env("EARLY_TEST_MISSING_PROOF", "1");
            }
            "conflicting" => {
                cmd.env("UNUSED_INTEGRATION_CONFLICTING_PROOF", "1");
            }
            "malformed" => {
                cmd.env("UNUSED_INTEGRATION_MALFORMED_PROOF", "1");
            }
            "compiler-error" => {
                p.change_file(
                    "app/src/lib.rs",
                    &format!(
                        "{}\n#[cfg(test)] compile_error!(\"test error\");",
                        source(2, false)
                    ),
                );
                cmd.with_stderr_contains("[..]test error[..]");
            }
            "fallback-error" => {
                p.change_file("helper/src/lib.rs", "compile_error!(\"helper error\");");
                cmd.with_stderr_contains("[..]helper error[..]");
            }
            "interrupted" => {
                cmd.env("UNUSED_TEST_EXIT", "130");
            }
            _ => unreachable!(),
        }
        if fails {
            cmd.with_status(101);
        }
        if case == "interrupted" {
            cmd.with_stderr_does_not_contain("[..]retrying complete graph[..]");
        } else {
            cmd.with_stderr_contains("[..]retrying complete graph[..]");
        }
        cmd.run();
        assert_eq!(
            log(&p, "compiler.log")
                .matches("compile-link:app\n")
                .count(),
            if matches!(case, "fallback-error" | "interrupted") {
                1
            } else {
                2
            },
            "{case}"
        );
        assert_eq!(log(&p, "runs.log").is_empty(), fails, "{case}");
        if fails {
            assert!(!manifest.exists(), "{case}: provisional proof survived");
            assert!(
                !executable.exists(),
                "{case}: provisional executable survived"
            );
            assert!(
                !executable.with_extension("rlink").exists(),
                "{case}: provisional link inputs survived"
            );
            clear(&p);
            p.change_file("app/src/lib.rs", &source(3, true));
            p.change_file(
                "helper/src/lib.rs",
                "pub fn value() -> u32 { app::value() }",
            );
            command(&p, &wrapper, "")
                .with_stderr_does_not_contain("[..]deferring unused dev dependencies[..]")
                .run();
            assert_eq!(log(&p, "runs.log"), "ran\n");
        }
    }
}
