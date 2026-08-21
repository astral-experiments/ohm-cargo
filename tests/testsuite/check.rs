//! Tests for the `cargo check` command.

use std::fmt::{self, Write};

use crate::prelude::*;
use crate::utils::tools;
use cargo_test_support::compare::assert_e2e;
use cargo_test_support::install::exe;
use cargo_test_support::registry::Package;
use cargo_test_support::str;
use cargo_test_support::{Project, basic_bin_manifest, basic_manifest, git, project};

fn ohm_registry_project() -> Project {
    project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [dependencies]
                dependency = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { dependency::value() }",
        )
        .build()
}

fn ohm_compiler_supports_defaults() -> bool {
    cargo_test_support::process("rustc")
        .arg("-Zpublic-api-hash")
        .arg("-Zcache-proc-macros")
        .arg("--print=sysroot")
        .exec_with_output()
        .is_ok()
}

#[cargo_test]
fn check_success() {
    let foo = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [dependencies.bar]
                path = "../bar"
            "#,
        )
        .file(
            "src/main.rs",
            "extern crate bar; fn main() { ::bar::baz(); }",
        )
        .build();
    let _bar = project()
        .at("bar")
        .file("Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("src/lib.rs", "pub fn baz() {}")
        .build();

    foo.cargo("check").run();
}

#[cargo_test]
fn check_fail() {
    let foo = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [dependencies.bar]
                path = "../bar"
            "#,
        )
        .file(
            "src/main.rs",
            "extern crate bar; fn main() { ::bar::baz(42); }",
        )
        .build();
    let _bar = project()
        .at("bar")
        .file("Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("src/lib.rs", "pub fn baz() {}")
        .build();

    foo.cargo("check")
        .with_status(101)
        .with_stderr_data(str![[r#"
...
error[E0061]: this function takes 0 arguments but 1 argument was supplied
...
"#]])
        .run();
}

#[cargo_test]
fn custom_derive() {
    let foo = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [dependencies.bar]
                path = "../bar"
            "#,
        )
        .file(
            "src/main.rs",
            r#"
            #[macro_use]
            extern crate bar;

            trait B {
                fn b(&self);
            }

            #[derive(B)]
            struct A;

            fn main() {
                let a = A;
                a.b();
            }
            "#,
        )
        .build();
    let _bar = project()
        .at("bar")
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "bar"
                version = "0.1.0"
                edition = "2015"
                authors = []
                [lib]
                proc-macro = true
            "#,
        )
        .file(
            "src/lib.rs",
            r#"
            extern crate proc_macro;

            use proc_macro::TokenStream;

            #[proc_macro_derive(B)]
            pub fn derive(_input: TokenStream) -> TokenStream {
                format!("impl B for A {{ fn b(&self) {{}} }}").parse().unwrap()
            }
            "#,
        )
        .build();

    foo.cargo("check").run();
}

#[cargo_test]
fn check_build() {
    let foo = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [dependencies.bar]
                path = "../bar"
            "#,
        )
        .file(
            "src/main.rs",
            "extern crate bar; fn main() { ::bar::baz(); }",
        )
        .build();

    let _bar = project()
        .at("bar")
        .file("Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("src/lib.rs", "pub fn baz() {}")
        .build();

    foo.cargo("check").run();
    foo.cargo("build").run();
}

#[cargo_test]
fn build_check() {
    let foo = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [dependencies.bar]
                path = "../bar"
            "#,
        )
        .file(
            "src/main.rs",
            "extern crate bar; fn main() { ::bar::baz(); }",
        )
        .build();

    let _bar = project()
        .at("bar")
        .file("Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("src/lib.rs", "pub fn baz() {}")
        .build();

    foo.cargo("build -v").run();
    foo.cargo("check -v").run();
}

#[cargo_test]
fn ohm_reuses_built_registry_dependency_closure() {
    Package::new("leaf", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();
    Package::new("middle", "1.0.0")
        .dep("leaf", "1.0.0")
        .file(
            "src/lib.rs",
            "extern crate leaf; pub fn value() -> u32 { leaf::value() }",
        )
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [dependencies]
                leaf = "1.0.0"
                middle = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { leaf::value() + middle::value() }",
        )
        .build();

    p.cargo("build").run();
    p.cargo("-Zohm-reuse-built-deps check -v")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_data(str![[r#"
[FRESH] leaf v1.0.0
[FRESH] middle v1.0.0
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_remains_opt_in_without_ohm_defaults() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("-Zohm-defaults=no build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .run();
    p.cargo("-Zohm-defaults=no check")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .with_stderr_data(str![[r#"
[CHECKING] dependency v1.0.0
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_is_enabled_by_ohm_defaults() {
    if !ohm_compiler_supports_defaults() {
        return;
    }

    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .run();
    assert!(
        p.root().join("target/.ohm-built-registry-ready").is_file(),
        "a successful registry build must make its artifacts discoverable before resolution",
    );
    p.cargo("check -v")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .with_stderr_data(str![[r#"
[FRESH] dependency v1.0.0
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc -Zpublic-api-hash -Zcache-proc-macros -Zpublic-api-hash=no --crate-name foo [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("clean")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .run();
    assert!(
        !p.root().join("target/.ohm-built-registry-ready").exists(),
        "cleaning the owning build directory must remove its readiness hint",
    );
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_skips_speculation_before_a_real_build() {
    if !ohm_compiler_supports_defaults() {
        return;
    }

    Package::new("build-helper", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 11 }")
        .publish();
    Package::new("dependency", "1.0.0")
        .build_dep("build-helper", "1.0.0")
        .file("build.rs", "fn main() { let _ = build_helper::value(); }")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();
    let readiness = p.root().join("target/.ohm-built-registry-ready");

    for invocation in 0..3 {
        if invocation == 2 {
            p.change_file(
                "src/lib.rs",
                "pub fn value() -> u32 { dependency::value() + 1 }",
            );
        }

        let mut check = p.cargo("check -Zbuild-analysis");
        check
            .masquerade_as_nightly_cargo(&["build-analysis", "ohm-defaults"])
            .env("CARGO_BUILD_ANALYSIS_ENABLED", "true")
            .env("__CARGO_OHM_DEFAULTS", "yes");
        if invocation == 0 {
            check.with_stderr_contains("[COMPILING] build-helper v1.0.0");
        }
        check.run();

        assert!(
            !readiness.exists(),
            "incidental build-script dependencies must not mark a check as a completed build",
        );

        let analysis = std::fs::read_to_string(cargo_test_support::paths::log_file(invocation))
            .expect("read build analysis events");
        let resolutions = analysis
            .lines()
            .map(|line| serde_json::from_str::<serde_json::Value>(line))
            .map(|event| event.expect("valid build analysis event"))
            .filter(|event| event["reason"] == "resolution-started")
            .count();
        assert_eq!(
            resolutions, 1,
            "cold, no-op, and directly edited checks must resolve their dependency graph once",
        );
    }
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_preserves_explicit_policy_without_readiness() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();
    let readiness = p.root().join("target/.ohm-built-registry-ready");

    p.cargo("-Zohm-defaults=no build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .run();
    assert!(
        !readiness.exists(),
        "ordinary builds must not change their layout when Ohm's defaults are disabled",
    );

    p.cargo("-Zohm-defaults=no -Zohm-reuse-built-deps check -v")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-reuse-built-deps"])
        .with_stderr_data(str![[r#"
[FRESH] dependency v1.0.0
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_keeps_readiness_in_the_build_directory() {
    if !ohm_compiler_supports_defaults() {
        return;
    }

    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();
    let build_directory = p.root().join("shared-build");
    let readiness = build_directory.join(".ohm-built-registry-ready");

    p.cargo("build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .env("CARGO_BUILD_BUILD_DIR", &build_directory)
        .run();
    assert!(readiness.is_file());
    assert!(!p.root().join("target/.ohm-built-registry-ready").exists());

    p.cargo("check -v")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .env("CARGO_BUILD_BUILD_DIR", &build_directory)
        .with_stderr_contains("[FRESH] dependency v1.0.0")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_respects_aggregate_default_opt_out() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("-Zohm-defaults=no build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .run();
    p.cargo("-Zohm-defaults=no check")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .with_stderr_data(str![[r#"
[CHECKING] dependency v1.0.0
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_preserves_unflagged_fingerprints() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").env("RUSTC_BOOTSTRAP", "1").run();
    let fingerprint = p
        .glob("target/debug/.fingerprint/dependency-*/lib-dependency")
        .next()
        .expect("registry fingerprint")
        .expect("existing registry fingerprint path");
    let original = std::fs::read(&fingerprint).expect("read original registry fingerprint");

    // The opt-in reuse policy must not change ordinary Cargo's fingerprint
    // contract or force every existing registry dependency to rebuild.
    p.cargo("build -v")
        .env("RUSTC_BOOTSTRAP", "-1")
        .with_stderr_contains("[FRESH] dependency v1.0.0")
        .run();
    assert_eq!(
        std::fs::read(&fingerprint).expect("read preserved registry fingerprint"),
        original,
        "ordinary builds must preserve the existing Cargo fingerprint",
    );

    // Cross-mode reuse still validates the policy captured by the build's
    // separate provenance, even though the normal fingerprint did not change.
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC_BOOTSTRAP", "-1")
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_artifacts_without_provenance() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").run();
    let provenance = p
        .glob("target/debug/.fingerprint/dependency-*/ohm-message-provenance-lib-dependency")
        .next()
        .expect("registry build provenance")
        .expect("existing registry build provenance path");
    std::fs::remove_file(provenance).expect("simulate an artifact from an older Cargo");

    // An artifact produced before the opt-in feature remains perfectly usable
    // for ordinary builds and must not force a global dependency rebuild.
    p.cargo("build -v")
        .with_stderr_contains("[FRESH] dependency v1.0.0")
        .run();

    // Without its compiler and diagnostics provenance, the same artifact is
    // deliberately ineligible for the more aggressive cross-mode shortcut.
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_revalidates_actual_compiler_driver() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").run();
    let provenance_path = p
        .glob("target/debug/.fingerprint/dependency-*/ohm-message-provenance-lib-dependency")
        .next()
        .expect("registry compiler provenance")
        .expect("existing compiler provenance path");
    let mut provenance = serde_json::from_slice::<serde_json::Value>(
        &std::fs::read(&provenance_path).expect("read registry compiler provenance"),
    )
    .expect("parse registry compiler provenance");
    let driver = &provenance["compiler_driver"];
    let driver_path = std::path::Path::new(driver["path"].as_str().expect("compiler driver path"));
    let metadata = std::fs::metadata(driver_path).expect("actual compiler driver metadata");
    assert!(metadata.is_file(), "compiler implementation must be a file");
    assert_eq!(driver["length"], metadata.len());
    assert!(
        driver_path
            .file_name()
            .and_then(|name| name.to_str())
            .is_some_and(|name| name.contains("rustc_driver-")),
        "provenance must fingerprint rustc's loaded driver, not only its launcher",
    );

    // Simulate the implementation changing while its small executable
    // launcher and `rustc -vV` output remain unchanged.
    provenance["compiler_driver"]["length"] = serde_json::json!(metadata.len() + 1);
    std::fs::write(
        &provenance_path,
        serde_json::to_vec(&provenance).expect("encode changed compiler provenance"),
    )
    .expect("simulate a changed compiler implementation");

    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_shadowed_compiler_drivers() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();
    let search_variable = if cfg!(target_os = "macos") {
        "LD_LIBRARY_PATH"
    } else {
        "DYLD_LIBRARY_PATH"
    };
    let search_directory = p.root().join("driver-search");
    std::fs::create_dir_all(&search_directory).expect("create isolated loader search directory");

    p.cargo("build")
        .env(search_variable, &search_directory)
        .run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env(search_variable, &search_directory)
        .with_stderr_does_not_contain("[CHECKING] dependency v1.0.0")
        .run();

    let provenance_path = p
        .glob("target/debug/.fingerprint/dependency-*/ohm-message-provenance-lib-dependency")
        .next()
        .expect("registry compiler provenance")
        .expect("existing registry compiler provenance");
    let provenance = serde_json::from_slice::<serde_json::Value>(
        &std::fs::read(provenance_path).expect("read registry compiler provenance"),
    )
    .expect("parse registry compiler provenance");
    let expected_driver = std::path::Path::new(
        provenance["compiler_driver"]["path"]
            .as_str()
            .expect("actual compiler driver path"),
    );
    let shadow = search_directory.join(
        expected_driver
            .file_name()
            .expect("actual compiler driver filename"),
    );
    std::fs::write(&shadow, "opaque replacement compiler implementation")
        .expect("add a different compiler driver to an unchanged search path");

    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env(search_variable, &search_directory)
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();

    std::fs::remove_file(&shadow).expect("remove the shadow compiler implementation");
    #[cfg(unix)]
    std::os::unix::fs::symlink(expected_driver, &shadow)
        .expect("add a safe alias to the actual compiler implementation");
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env(search_variable, &search_directory)
        .with_stderr_does_not_contain("[CHECKING] dependency v1.0.0")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_cargo_generated_driver_shadows() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_does_not_contain("[CHECKING] dependency v1.0.0")
        .run();

    let provenance_path = p
        .glob("target/debug/.fingerprint/dependency-*/ohm-message-provenance-lib-dependency")
        .next()
        .expect("registry compiler provenance")
        .expect("existing registry compiler provenance");
    let provenance = serde_json::from_slice::<serde_json::Value>(
        &std::fs::read(provenance_path).expect("read registry compiler provenance"),
    )
    .expect("parse registry compiler provenance");
    let expected_driver = std::path::Path::new(
        provenance["compiler_driver"]["path"]
            .as_str()
            .expect("actual compiler driver path"),
    );
    let generated_search_directory = p.root().join("target/debug/deps");
    assert!(
        provenance["compiler_search_directories"]
            .as_array()
            .expect("actual compiler search directories")
            .iter()
            .any(|directory| {
                directory.as_str().is_some_and(|directory| {
                    std::path::Path::new(directory) == generated_search_directory
                })
            }),
        "the provenance must include Cargo's synthesized host dependency directory",
    );
    let shadow = generated_search_directory.join(
        expected_driver
            .file_name()
            .expect("actual compiler driver filename"),
    );
    std::fs::write(
        &shadow,
        "opaque compiler driver in Cargo's generated search path",
    )
    .expect("add a different driver after the successful dependency build");

    let mut check = p.cargo("-Zohm-reuse-built-deps check");
    check
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_contains("[CHECKING] dependency v1.0.0");
    if cfg!(target_os = "macos") {
        // macOS uses DYLD_FALLBACK_LIBRARY_PATH, so the compiler's valid
        // install name remains usable even though reuse must be rejected.
        check.run();
    } else {
        // On platforms where the generated path precedes the install name,
        // an invalid replacement must surface the normal compiler failure.
        check.with_status(101).run();
    }
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_uses_actual_platform_loader_precedence() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();
    let platform_loader = cargo_util::paths::dylib_path_envvar();
    let configured_directory = p.root().join("configured-driver-search");
    let inherited_directory = p.root().join("actual-driver-search");
    std::fs::create_dir_all(&configured_directory).expect("create forced-config search directory");
    std::fs::create_dir_all(&inherited_directory).expect("create inherited search directory");
    p.change_file(
        ".cargo/config.toml",
        &format!(
            "[env]\n{platform_loader} = {{ value = {}, force = true }}\n",
            toml::Value::String(configured_directory.display().to_string()),
        ),
    );

    p.cargo("build")
        .env(platform_loader, &inherited_directory)
        .run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env(platform_loader, &inherited_directory)
        .with_stderr_does_not_contain("[CHECKING] dependency v1.0.0")
        .run();

    let provenance_path = p
        .glob("target/debug/.fingerprint/dependency-*/ohm-message-provenance-lib-dependency")
        .next()
        .expect("registry compiler provenance")
        .expect("existing registry compiler provenance");
    let provenance = serde_json::from_slice::<serde_json::Value>(
        &std::fs::read(provenance_path).expect("read registry compiler provenance"),
    )
    .expect("parse registry compiler provenance");
    let expected_driver = std::path::Path::new(
        provenance["compiler_driver"]["path"]
            .as_str()
            .expect("actual compiler driver path"),
    );
    let shadow = inherited_directory.join(
        expected_driver
            .file_name()
            .expect("actual compiler driver filename"),
    );
    std::fs::write(
        &shadow,
        "opaque compiler driver in the inherited loader directory",
    )
    .expect("add a different compiler driver to the actual search path");

    let mut check = p.cargo("-Zohm-reuse-built-deps check");
    check
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env(platform_loader, &inherited_directory)
        .with_stderr_contains("[CHECKING] dependency v1.0.0");
    if cfg!(target_os = "macos") {
        check.run();
    } else {
        check.with_status(101).run();
    }
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_preserves_cold_checks() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_data(str![[r#"
[UPDATING] `dummy-registry` index
[LOCKING] 1 package to highest compatible version
[DOWNLOADING] crates ...
[DOWNLOADED] dependency v1.0.0 (registry `dummy-registry`)
[CHECKING] dependency v1.0.0
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_keeps_path_dependencies_checked() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [dependencies]
                local = { path = "local" }
            "#,
        )
        .file(
            "local/Cargo.toml",
            r#"
                [package]
                name = "local"
                version = "1.0.0"
                edition = "2021"

                [dependencies]
                dependency = "1.0.0"
            "#,
        )
        .file(
            "local/src/lib.rs",
            "pub fn value() -> u32 { dependency::value() }",
        )
        .file("src/lib.rs", "pub fn value() -> u32 { local::value() }")
        .build();

    p.cargo("build").run();
    p.cargo("-Zohm-reuse-built-deps check -v")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_data(str![[r#"
[FRESH] dependency v1.0.0
[CHECKING] local v1.0.0 ([ROOT]/foo/local)
[RUNNING] `rustc --crate-name local [..]`
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_patched_path_closures() {
    Package::new("leaf", "1.0.0").publish();
    Package::new("middle", "1.0.0")
        .dep("leaf", "1.0.0")
        .file(
            "src/lib.rs",
            "extern crate leaf; pub fn value() -> u32 { leaf::value() }",
        )
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [dependencies]
                middle = "1.0.0"

                [patch.crates-io]
                leaf = { path = "leaf" }
            "#,
        )
        .file(
            "leaf/Cargo.toml",
            r#"
                [package]
                name = "leaf"
                version = "1.0.0"
                edition = "2021"
            "#,
        )
        .file("leaf/src/lib.rs", "pub fn value() -> u32 { 19 }")
        .file("src/lib.rs", "pub fn value() -> u32 { middle::value() }")
        .build();

    p.cargo("build").run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_data(str![[r#"
[CHECKING] leaf v1.0.0 ([ROOT]/foo/leaf)
[CHECKING] middle v1.0.0
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_verifies_replaced_vendored_sources() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("vendor --respect-source-config").run();
    p.change_file(
        ".cargo/config.toml",
        r#"
            [source.crates-io]
            replace-with = "vendor"

            [source.vendor]
            directory = "vendor"
        "#,
    );
    p.cargo("build").run();
    p.change_file(
        "vendor/dependency/src/lib.rs",
        r#"compile_error!("a vendored registry source was modified");"#,
    );

    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_status(101)
        .with_stderr_contains(
            "[ERROR] the listed checksum of `[ROOT]/foo/vendor/dependency/src/lib.rs` has changed:",
        )
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_revalidates_features() {
    Package::new("dependency", "1.0.0")
        .feature("extra", &[])
        .file(
            "src/lib.rs",
            r#"
                #[cfg(feature = "extra")]
                pub fn extra() -> u32 { 19 }

                #[cfg(feature = "extra")]
                #[export_name = "duplicate_backend_symbol"]
                pub fn first() {}

                #[cfg(feature = "extra")]
                #[export_name = "duplicate_backend_symbol"]
                pub fn second() {}
            "#,
        )
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [features]
                extra = ["dependency/extra"]

                [dependencies]
                dependency = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "#[cfg(feature = \"extra\")] pub fn value() -> u32 { dependency::extra() }",
        )
        .build();

    p.cargo("build").run();
    p.cargo("-Zohm-reuse-built-deps check --features extra")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_data(str![[r#"
[CHECKING] dependency v1.0.0
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_revalidates_compiler_feature_policy() {
    Package::new("dependency", "1.0.0")
        .file(
            "src/lib.rs",
            "#![feature(never_type)]\npub fn value() -> u32 { 19 }",
        )
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").env("RUSTC_BOOTSTRAP", "1").run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC_BOOTSTRAP", "-1")
        .with_status(101)
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .with_stderr_contains(
            "error[E0554]: `#![feature]` may not be used on the [..] release channel",
        )
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_revalidates_overridden_compiler_version() {
    Package::new("dependency", "1.0.0")
        .file(
            "src/lib.rs",
            r#"
                #![feature(cfg_version)]

                #[cfg(not(version("1.80")))]
                compile_error!("the compiler version changed");

                pub fn value() -> u32 { 19 }
            "#,
        )
        .publish();

    let p = ohm_registry_project();

    p.cargo("build")
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTC_OVERRIDE_VERSION_STRING", "1.99.0")
        .run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTC_OVERRIDE_VERSION_STRING", "1.50.0")
        .with_status(101)
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .with_stderr_contains("[ERROR] the compiler version changed")
        .run();
}

#[cfg(unix)]
#[cargo_test]
fn ohm_built_registry_dependency_reuse_revalidates_direct_compiler_identity() {
    Package::new("dependency", "1.0.0")
        .file(
            "src/lib.rs",
            r#"
                #[cfg(ohm_changed_direct_compiler)]
                compile_error!("the direct compiler changed");

                pub fn value() -> u32 { 19 }
            "#,
        )
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [dependencies]
                dependency = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { dependency::value() }",
        )
        .executable("rustc-before", "#!/bin/sh\nexec rustc \"$@\"\n")
        .executable(
            "rustc-after",
            r#"#!/bin/sh
previous=
for argument in "$@"; do
    if [ "$previous" = "--crate-name" ] && [ "$argument" = "dependency" ]; then
        exec rustc "$@" --cfg ohm_changed_direct_compiler
    fi
    previous="$argument"
done
exec rustc "$@"
"#,
        )
        .build();

    p.cargo("build")
        .env("RUSTC", p.root().join("rustc-before"))
        .run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC", p.root().join("rustc-after"))
        .with_status(101)
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .with_stderr_contains("[ERROR] the direct compiler changed")
        .run();
}

#[cfg(unix)]
#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_ambient_compiler_shims() {
    Package::new("dependency", "1.0.0")
        .file(
            "src/lib.rs",
            r#"
                #[cfg(ohm_changed_direct_compiler)]
                compile_error!("the same compiler shim changed behavior");

                pub fn value() -> u32 { 19 }
            "#,
        )
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [dependencies]
                dependency = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { dependency::value() }",
        )
        .executable(
            "rustc-shim",
            r#"#!/bin/sh
if [ "$OHM_DRIVER_MODE" = "deny" ]; then
    previous=
    for argument in "$@"; do
        if [ "$previous" = "--crate-name" ] && [ "$argument" = "dependency" ]; then
            exec rustc "$@" --cfg ohm_changed_direct_compiler
        fi
        previous="$argument"
    done
fi
exec rustc "$@"
"#,
        )
        .build();

    p.cargo("build")
        .env("RUSTC", p.root().join("rustc-shim"))
        .env("OHM_DRIVER_MODE", "allow")
        .run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC", p.root().join("rustc-shim"))
        .env("OHM_DRIVER_MODE", "deny")
        .with_status(101)
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .with_stderr_contains("[ERROR] the same compiler shim changed behavior")
        .run();
}

#[cfg(unix)]
#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_compilers_from_configured_path() {
    Package::new("dependency", "1.0.0")
        .file(
            "src/lib.rs",
            r#"
                #[cfg(not(ohm_configured_compiler_permitted))]
                compile_error!("configured PATH selected an opaque compiler");

                pub fn value() -> u32 { 19 }
            "#,
        )
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [dependencies]
                dependency = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { dependency::value() }",
        )
        .executable(
            "opaque-compiler/rustc",
            r#"#!/bin/sh
if [ "$OHM_COMPILER_MODE" = "allow" ]; then
    previous=
    for argument in "$@"; do
        if [ "$previous" = "--crate-name" ] && [ "$argument" = "dependency" ]; then
            exec "$OHM_REAL_RUSTC" "$@" --cfg ohm_configured_compiler_permitted
        fi
        previous="$argument"
    done
fi
exec "$OHM_REAL_RUSTC" "$@"
"#,
        )
        .build();

    let sysroot = std::process::Command::new("rustc")
        .args(["--print", "sysroot"])
        .output()
        .expect("discover the genuine compiler sysroot");
    assert!(
        sysroot.status.success(),
        "query the genuine compiler sysroot"
    );
    let sysroot = String::from_utf8(sysroot.stdout).expect("UTF-8 compiler sysroot");
    let compiler = std::path::Path::new(sysroot.trim()).join("bin/rustc");
    let inherited_path = std::env::var_os("PATH").expect("inherited executable search path");
    let parent_path = std::env::join_paths(
        std::iter::once(compiler.parent().expect("compiler directory").to_path_buf())
            .chain(std::env::split_paths(&inherited_path)),
    )
    .expect("prepend the genuine compiler to Cargo's inherited PATH");
    let child_path = std::env::join_paths(
        std::iter::once(p.root().join("opaque-compiler"))
            .chain(std::env::split_paths(&parent_path)),
    )
    .expect("prepend the opaque compiler to rustc's configured PATH");
    p.change_file(
        ".cargo/config.toml",
        &format!(
            "[env]\nPATH = {{ value = {:?}, force = true }}\n",
            child_path.to_str().expect("UTF-8 configured search path")
        ),
    );

    p.cargo("build")
        .env("RUSTC", "rustc")
        .env("PATH", &parent_path)
        .env("OHM_REAL_RUSTC", &compiler)
        .env("OHM_COMPILER_MODE", "allow")
        .run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC", "rustc")
        .env("PATH", &parent_path)
        .env("OHM_REAL_RUSTC", &compiler)
        .env("OHM_COMPILER_MODE", "deny")
        .with_status(101)
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .with_stderr_contains("[ERROR] configured PATH selected an opaque compiler")
        .run();

    // A build produced by the configured wrapper also cannot become trusted
    // after that configuration disappears and bare rustc resolves normally.
    p.change_file(".cargo/config.toml", "");
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC", "rustc")
        .env("PATH", &parent_path)
        .with_status(101)
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .with_stderr_contains("[ERROR] configured PATH selected an opaque compiler")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_preserves_compiler_logging() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC_LOG", "rustc_metadata=info")
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_preserves_configured_compiler_log_output() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").run();

    let output = p.root().join("configured-compiler.log");
    p.change_file(
        ".cargo/config.toml",
        &format!(
            "[env]\nRUSTC_LOG_OUTPUT_TARGET = {{ value = {:?}, force = true }}\n",
            output.to_str().expect("UTF-8 compiler logging path")
        ),
    );

    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC_LOG_OUTPUT_TARGET", "")
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();

    assert!(
        output.is_file(),
        "rustc must create its configured log target"
    );
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_build_script_compiler_logging() {
    Package::new("dependency", "1.0.0")
        .file(
            "build.rs",
            r#"
                fn main() {
                    let output = std::path::Path::new(&std::env::var_os("OUT_DIR").unwrap())
                        .join("compiler.log");
                    println!("cargo::rustc-env=RUSTC_LOG_OUTPUT_TARGET={}", output.display());
                }
            "#,
        )
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_compiler_loader_injection() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    // Select the other platform's loader variable so the real dynamic loader
    // ignores this harmless sentinel while Cargo still rejects interposition.
    let loader_override = if cfg!(target_os = "macos") {
        "LD_PRELOAD"
    } else {
        "DYLD_INSERT_LIBRARIES"
    };

    p.cargo("build").run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env(loader_override, "ohm-test-interposer")
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_revalidates_seed_loader_environment() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    let loader_override = if cfg!(target_os = "macos") {
        "LD_PRELOAD"
    } else {
        "DYLD_INSERT_LIBRARIES"
    };

    // Even when the current check has a clean loader environment, it must not
    // trust an artifact compiled under an unrecorded prior interposer.
    p.cargo("build")
        .env(loader_override, "ohm-test-interposer")
        .run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_configured_loader_injection() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").run();

    let loader_override = if cfg!(target_os = "macos") {
        "LD_PRELOAD"
    } else {
        "DYLD_INSERT_LIBRARIES"
    };
    p.change_file(
        ".cargo/config.toml",
        &format!(
            "[env]\n{loader_override} = {{ value = \"ohm-test-interposer\", force = true }}\n"
        ),
    );

    // A forced Cargo configuration overrides the inherited empty value, so
    // checking only the process snapshot would incorrectly allow reuse.
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env(loader_override, "")
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_build_script_loader_injection() {
    // The other platform ignores this harmless value, but Cargo must still
    // recognize that a build script injected it into this registry compiler.
    let loader_override = if cfg!(target_os = "macos") {
        "LD_PRELOAD"
    } else {
        "DYLD_INSERT_LIBRARIES"
    };
    Package::new("dependency", "1.0.0")
        .file(
            "build.rs",
            &format!(
                r#"fn main() {{ println!("cargo::rustc-env={loader_override}=ohm-test-interposer"); }}"#
            ),
        )
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_build_script_loader_search_overrides() {
    let search_variable = if cfg!(target_os = "macos") {
        "LD_LIBRARY_PATH"
    } else {
        "DYLD_LIBRARY_PATH"
    };
    Package::new("dependency", "1.0.0")
        .file(
            "build.rs",
            &format!(
                r#"fn main() {{
                    println!("cargo::rustc-env={search_variable}={{}}", std::env::var("OHM_DRIVER_SEARCH").unwrap());
                    println!("cargo::rerun-if-env-changed=OHM_DRIVER_SEARCH");
                }}"#
            ),
        )
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    for search_override in ["opaque-search-path", ""] {
        p.cargo("build")
            .env("OHM_DRIVER_SEARCH", search_override)
            .run();
        p.cargo("-Zohm-reuse-built-deps check")
            .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
            .env("OHM_DRIVER_SEARCH", search_override)
            .with_stderr_contains("[CHECKING] dependency v1.0.0")
            .run();
    }
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_revalidates_build_script_compiler_policy() {
    Package::new("dependency", "1.0.0")
        .file(
            "build.rs",
            r#"
                fn main() {
                    println!("cargo::rustc-env=RUSTC_OVERRIDE_VERSION_STRING=1.99.0");
                }
            "#,
        )
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();
}

#[cfg(windows)]
#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_windows_build_script_policy_aliases() {
    Package::new("dependency", "1.0.0")
        .file(
            "build.rs",
            r#"
                fn main() {
                    println!("cargo::rustc-env=rustc_override_version_string=1.99.0");
                }
            "#,
        )
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();
}

#[cfg(windows)]
#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_windows_configured_path_aliases() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").run();
    p.change_file(
        ".cargo/config.toml",
        "[env]\nPath = { value = \"opaque-linker-directory\", force = true }\n",
    );
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rechecks_untrusted_procedural_macro_environment() {
    // A matching package name and major version in another registry must not
    // inherit the explicitly audited crates.io producer's trust.
    Package::new("serde_derive", "1.0.0")
        .proc_macro(true)
        .file(
            "src/lib.rs",
            r#"
                extern crate proc_macro;

                #[proc_macro_attribute]
                pub fn gate(
                    _attribute: proc_macro::TokenStream,
                    input: proc_macro::TokenStream,
                ) -> proc_macro::TokenStream {
                    if std::env::var("OHM_MACRO_MODE").as_deref() == Ok("deny") {
                        "compile_error!(\"the procedural macro observed changed environment\");"
                            .parse()
                            .expect("valid compiler error")
                    } else {
                        input
                    }
                }
            "#,
        )
        .publish();
    Package::new("dependency", "1.0.0")
        .dep("serde_derive", "1.0.0")
        .file(
            "src/lib.rs",
            r#"
                extern crate serde_derive;

                #[serde_derive::gate]
                pub fn value() -> u32 { 19 }
            "#,
        )
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").env("OHM_MACRO_MODE", "allow").run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("OHM_MACRO_MODE", "deny")
        .with_status(101)
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .with_stderr_contains("[ERROR] the procedural macro observed changed environment")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rechecks_untracked_procedural_macro_files() {
    Package::new("file-macro", "1.0.0")
        .proc_macro(true)
        .file(
            "src/lib.rs",
            r#"
                extern crate proc_macro;

                #[proc_macro_attribute]
                pub fn gate(
                    _attribute: proc_macro::TokenStream,
                    input: proc_macro::TokenStream,
                ) -> proc_macro::TokenStream {
                    let path = std::env::var("OHM_MACRO_STATE")
                        .expect("procedural macro state path");
                    if std::fs::read_to_string(path)
                        .expect("procedural macro state")
                        .trim()
                        == "deny"
                    {
                        "compile_error!(\"the procedural macro observed changed external input\");"
                            .parse()
                            .expect("valid compiler error")
                    } else {
                        input
                    }
                }
            "#,
        )
        .publish();
    Package::new("dependency", "1.0.0")
        .dep("file-macro", "1.0.0")
        .file(
            "src/lib.rs",
            r#"
                extern crate file_macro;

                #[file_macro::gate]
                pub fn value() -> u32 { 19 }
            "#,
        )
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [dependencies]
                dependency = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { dependency::value() }",
        )
        .file("external-state.txt", "allow")
        .build();
    let state_path = p.root().join("external-state.txt");

    p.cargo("build").env("OHM_MACRO_STATE", &state_path).run();
    p.change_file("external-state.txt", "deny");
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("OHM_MACRO_STATE", &state_path)
        .with_status(101)
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .with_stderr_contains("[ERROR] the procedural macro observed changed external input")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rechecks_missing_future_incompat_messages() {
    Package::new("leaf", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { let unused = 1; 19 }")
        .publish();
    Package::new("dependency", "1.0.0")
        .dep("leaf", "1.0.0")
        .file(
            "src/lib.rs",
            "extern crate leaf; pub fn value() -> u32 { leaf::value() }",
        )
        .publish();

    let p = ohm_registry_project();

    p.cargo("build")
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTFLAGS", "-Zfuture-incompat-test")
        .run();
    let cached_messages = p
        .glob("target/debug/.fingerprint/leaf-*/output-lib-leaf")
        .next()
        .expect("registry compiler messages")
        .expect("existing compiler message path");
    std::fs::remove_file(cached_messages).expect("remove only cached compiler diagnostics");

    p.cargo("-Zohm-reuse-built-deps check --future-incompat-report")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTFLAGS", "-Zfuture-incompat-test")
        .with_stderr_contains("[CHECKING] leaf v1.0.0")
        .with_stderr_contains(
            "[WARNING] the following packages contain code that will be rejected by a future version of Rust: leaf v1.0.0",
        )
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rechecks_truncated_future_incompat_messages() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { let unused = 1; 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build")
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTFLAGS", "-Zfuture-incompat-test")
        .run();
    let cached_messages = p
        .glob("target/debug/.fingerprint/dependency-*/output-lib-dependency")
        .next()
        .expect("registry compiler messages")
        .expect("existing compiler message path");
    std::fs::write(&cached_messages, []).expect("truncate cached compiler diagnostics");

    p.cargo("-Zohm-reuse-built-deps check --future-incompat-report")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTFLAGS", "-Zfuture-incompat-test")
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .with_stderr_contains(
            "[WARNING] the following packages contain code that will be rejected by a future version of Rust: dependency v1.0.0",
        )
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rechecks_replaced_future_incompat_messages() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { let unused = 1; 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build")
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTFLAGS", "-Zfuture-incompat-test")
        .run();
    let cached_messages = p
        .glob("target/debug/.fingerprint/dependency-*/output-lib-dependency")
        .next()
        .expect("registry compiler messages")
        .expect("existing compiler message path");
    let length = std::fs::read(&cached_messages)
        .expect("read cached compiler diagnostics")
        .len();
    std::fs::write(&cached_messages, vec![b' '; length])
        .expect("replace cached diagnostics without changing their length");

    p.cargo("-Zohm-reuse-built-deps check --future-incompat-report")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTFLAGS", "-Zfuture-incompat-test")
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .with_stderr_contains(
            "[WARNING] the following packages contain code that will be rejected by a future version of Rust: dependency v1.0.0",
        )
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_revalidates_build_script_environment() {
    Package::new("dependency", "1.0.0")
        .file(
            "build.rs",
            r#"
                fn main() {
                    println!("cargo:rerun-if-env-changed=OHM_REUSE_BUILD_INPUT");
                    let value = std::env::var("OHM_REUSE_BUILD_INPUT").unwrap_or_default();
                    println!("cargo:rustc-env=OHM_REUSE_BUILD_VALUE={value}");
                }
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> &'static str { env!(\"OHM_REUSE_BUILD_VALUE\") }",
        )
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [dependencies]
                dependency = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> &'static str { dependency::value() }",
        )
        .build();

    p.cargo("build")
        .env("OHM_REUSE_BUILD_INPUT", "before")
        .run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("OHM_REUSE_BUILD_INPUT", "after")
        .with_stderr_data(str![[r#"
[COMPILING] dependency v1.0.0
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    // Cargo labels the rerun build script as `Compiling`, but the registry
    // library itself must remain metadata-only after fallback.
    assert_eq!(p.glob("target/debug/deps/libdependency-*.rlib").count(), 1);
    assert_eq!(p.glob("target/debug/deps/libdependency-*.rmeta").count(), 2);
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_preserves_extra_verbose_warnings() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "fn unused() {}")
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [dependencies]
                dependency = "1.0.0"
            "#,
        )
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .build();

    p.cargo("build").run();
    p.cargo("-Zohm-reuse-built-deps check -vv")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_data(str![[r#"
...
[CHECKING] dependency v1.0.0
...
[WARNING] function `unused` is never used
...
[CHECKING] foo v0.0.1 ([ROOT]/foo)
...
"#]])
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_preserves_check_json_artifacts() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").run();
    p.cargo("-Zohm-reuse-built-deps check --message-format=json")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_data(str![[r#"
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .with_stdout_data(
            str![[r#"
[
  {
    "executable": null,
    "features": [],
    "filenames": [
      "[ROOT]/foo/target/debug/deps/libdependency-[HASH].rmeta"
    ],
    "fresh": true,
    "manifest_path": "[..]/dependency-1.0.0/Cargo.toml",
    "package_id": "[..]dependency@1.0.0",
    "profile": "{...}",
    "reason": "compiler-artifact",
    "target": "{...}"
  },
  {
    "executable": null,
    "features": [],
    "filenames": [
      "[ROOT]/foo/target/debug/deps/libfoo-[HASH].rmeta"
    ],
    "fresh": false,
    "manifest_path": "[ROOT]/foo/Cargo.toml",
    "package_id": "path+[ROOTURL]/foo#0.0.1",
    "profile": "{...}",
    "reason": "compiler-artifact",
    "target": "{...}"
  },
  {
    "reason": "build-finished",
    "success": true
  }
]
"#]]
            .is_json()
            .against_jsonlines(),
        )
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_preserves_transitive_check_json_artifacts() {
    Package::new("leaf", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();
    Package::new("middle", "1.0.0")
        .dep("leaf", "1.0.0")
        .file(
            "src/lib.rs",
            "extern crate leaf; pub fn value() -> u32 { leaf::value() }",
        )
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [dependencies]
                middle = "1.0.0"
            "#,
        )
        .file("src/lib.rs", "pub fn value() -> u32 { middle::value() }")
        .build();

    p.cargo("build").run();
    let output = p
        .cargo("-Zohm-reuse-built-deps check --message-format=json")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_does_not_contain("[CHECKING] leaf v1.0.0")
        .with_stderr_does_not_contain("[CHECKING] middle v1.0.0")
        .run();
    let stdout = String::from_utf8(output.stdout).expect("UTF-8 Cargo output");
    let messages = stdout
        .lines()
        .map(|line| serde_json::from_str::<serde_json::Value>(line).expect("JSON Cargo message"))
        .collect::<Vec<_>>();

    for name in ["leaf", "middle"] {
        let artifact = messages
            .iter()
            .find(|message| {
                message["reason"] == "compiler-artifact"
                    && message["package_id"]
                        .as_str()
                        .is_some_and(|package_id| package_id.contains(&format!("{name}@1.0.0")))
            })
            .expect("promoted registry artifact");
        let filenames = artifact["filenames"]
            .as_array()
            .expect("promoted registry artifact filenames");
        assert!(!filenames.is_empty(), "missing {name} metadata");
        assert!(
            filenames.iter().all(|filename| filename
                .as_str()
                .is_some_and(|path| path.ends_with(".rmeta"))),
            "a transitive check dependency must retain check-mode JSON: {artifact}",
        );
    }
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_preserves_build_helper_json_artifacts() {
    Package::new("helper-leaf", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();
    Package::new("build-helper", "1.0.0")
        .dep("helper-leaf", "1.0.0")
        .file(
            "src/lib.rs",
            "extern crate helper_leaf; pub fn value() -> u32 { helper_leaf::value() }",
        )
        .publish();
    Package::new("dependency", "1.0.0")
        .build_dep("build-helper", "1.0.0")
        .file("build.rs", "fn main() { let _ = build_helper::value(); }")
        .file("src/lib.rs", "pub fn value() -> u32 { 23 }")
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [dependencies]
                build-helper = "1.0.0"
                dependency = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { build_helper::value() + dependency::value() }",
        )
        .build();

    p.cargo("build").run();
    let output = p
        .cargo("-Zohm-reuse-built-deps check --message-format=json")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_stderr_does_not_contain("[CHECKING] build-helper v1.0.0")
        .with_stderr_does_not_contain("[CHECKING] dependency v1.0.0")
        .run();
    let stdout = String::from_utf8(output.stdout).expect("UTF-8 Cargo output");
    let messages = stdout
        .lines()
        .map(|line| serde_json::from_str::<serde_json::Value>(line).expect("JSON Cargo message"))
        .collect::<Vec<_>>();

    let helper_artifacts = messages
        .iter()
        .filter(|message| {
            message["reason"] == "compiler-artifact"
                && message["package_id"]
                    .as_str()
                    .is_some_and(|package_id| package_id.contains("build-helper@1.0.0"))
        })
        .collect::<Vec<_>>();
    assert!(
        !helper_artifacts.is_empty(),
        "registry build-helper artifacts"
    );
    assert!(
        helper_artifacts.iter().any(|helper| {
            helper["filenames"]
                .as_array()
                .expect("build-helper artifact filenames")
                .iter()
                .any(|filename| {
                    filename
                        .as_str()
                        .is_some_and(|path| path.ends_with(".rlib"))
                })
        }),
        "a genuine build-script dependency must retain its linkable library: {helper_artifacts:?}",
    );
    assert!(
        helper_artifacts.iter().any(|helper| {
            let filenames = helper["filenames"]
                .as_array()
                .expect("build-helper artifact filenames");
            !filenames.is_empty()
                && filenames.iter().all(|filename| {
                    filename
                        .as_str()
                        .is_some_and(|path| path.ends_with(".rmeta"))
                })
        }),
        "a mixed build and check dependency must retain both artifact events: {helper_artifacts:?}",
    );

    let helper_leaf_artifacts = messages
        .iter()
        .filter(|message| {
            message["reason"] == "compiler-artifact"
                && message["package_id"]
                    .as_str()
                    .is_some_and(|package_id| package_id.contains("helper-leaf@1.0.0"))
        })
        .collect::<Vec<_>>();
    assert!(
        helper_leaf_artifacts.iter().any(|artifact| {
            artifact["filenames"]
                .as_array()
                .expect("transitive build-script artifact filenames")
                .iter()
                .any(|filename| {
                    filename
                        .as_str()
                        .is_some_and(|path| path.ends_with(".rlib"))
                })
        }),
        "a transitive build-script dependency must retain its linkable library: {helper_leaf_artifacts:?}",
    );
    assert!(
        helper_leaf_artifacts.iter().any(|artifact| {
            let filenames = artifact["filenames"]
                .as_array()
                .expect("transitive build-script artifact filenames");
            !filenames.is_empty()
                && filenames.iter().all(|filename| {
                    filename
                        .as_str()
                        .is_some_and(|path| path.ends_with(".rmeta"))
                })
        }),
        "a transitive mixed dependency must retain both artifact events: {helper_leaf_artifacts:?}",
    );

    let dependency = messages
        .iter()
        .find(|message| {
            message["reason"] == "compiler-artifact"
                && message["package_id"]
                    .as_str()
                    .is_some_and(|package_id| package_id.contains("dependency@1.0.0"))
                && message["target"]["kind"]
                    .as_array()
                    .is_some_and(|kinds| kinds.iter().any(|kind| kind == "lib"))
        })
        .expect("promoted registry library artifact");
    assert!(
        dependency["filenames"]
            .as_array()
            .expect("promoted registry artifact filenames")
            .iter()
            .all(|filename| filename
                .as_str()
                .is_some_and(|path| path.ends_with(".rmeta"))),
        "a solely promoted registry dependency must retain check-mode JSON: {dependency}",
    );
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_supports_new_build_layout() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build")
        .masquerade_as_nightly_cargo(&["build-dir-new-layout", "fine-grain-locking"])
        .run();
    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking -Zohm-reuse-built-deps check -v")
        .masquerade_as_nightly_cargo(&[
            "build-dir-new-layout",
            "fine-grain-locking",
            "ohm-reuse-built-deps",
        ])
        .with_stderr_data(str![[r#"
[FRESH] dependency v1.0.0
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_preserves_binary_artifact_dependencies() {
    Package::new("artifact", "1.0.0")
        .file("src/main.rs", "fn main() {}")
        .publish();
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [dependencies]
                artifact = { version = "1.0.0", artifact = "bin" }
                dependency = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            r#"
                pub fn value() -> u32 {
                    let _ = include_bytes!(env!("CARGO_BIN_FILE_ARTIFACT"));
                    dependency::value()
                }
            "#,
        )
        .build();

    p.cargo("-Zbindeps build")
        .masquerade_as_nightly_cargo(&["bindeps"])
        .run();
    let output = p
        .cargo("-Zbindeps -Zohm-reuse-built-deps check --message-format=json")
        .masquerade_as_nightly_cargo(&["bindeps", "ohm-reuse-built-deps"])
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .with_stdout_does_not_contain(r#""filenames":[]"#)
        .run();
    let stdout = String::from_utf8(output.stdout).expect("UTF-8 Cargo output");
    let artifact = stdout
        .lines()
        .map(|line| serde_json::from_str::<serde_json::Value>(line).expect("JSON Cargo message"))
        .find(|message| {
            message["reason"] == "compiler-artifact"
                && message["package_id"]
                    .as_str()
                    .is_some_and(|package_id| package_id.contains("artifact@1.0.0"))
        })
        .expect("binary artifact dependency");
    assert!(
        artifact["filenames"]
            .as_array()
            .expect("binary artifact filenames")
            .iter()
            .any(|filename| filename
                .as_str()
                .is_some_and(|path| path.contains("/bin/artifact"))),
        "a genuine binary artifact dependency must retain its executable: {artifact}",
    );
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_rustflags_codegen_backends() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [dependencies]
                dependency = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { dependency::value() }",
        )
        .file("codegen-backend.rsp", "codegen_backend=llvm")
        .build();

    let response_rustflags = format!("-Z @{}", p.root().join("codegen-backend.rsp").display());
    for rustflags in [
        "-Zcodegen-backend=llvm",
        "-Zcodegen_backend=llvm",
        "-Z codegen-backend=llvm",
        "-Z codegen_backend=llvm",
        "-Zllvm-plugins=",
        "-Zllvm_plugins=",
        "-Z llvm-plugins=",
        "-Z llvm_plugins=",
        "-Zautodiff",
        "-Z autodiff",
        "-Lcrate=.",
        "-L dependency=.",
        response_rustflags.as_str(),
    ] {
        p.cargo("build")
            .env("RUSTC_BOOTSTRAP", "1")
            .env("RUSTFLAGS", rustflags)
            .run();
        p.cargo("-Zohm-reuse-built-deps check")
            .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
            .env("RUSTC_BOOTSTRAP", "1")
            .env("RUSTFLAGS", rustflags)
            .with_stderr_contains("[CHECKING] dependency v1.0.0")
            .run();
    }

    p.cargo("build")
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTFLAGS", "-Lnative=.")
        .run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTFLAGS", "-Lnative=.")
        .with_stderr_does_not_contain("[CHECKING] dependency v1.0.0")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_custom_target_codegen_backends() {
    let mut target_specification =
        serde_json::from_str::<serde_json::Value>(cargo_test_support::target_spec_json())
            .expect("valid custom target specification");
    target_specification["default-codegen-backend"] = serde_json::json!("llvm");
    let target_specification = serde_json::to_string(&target_specification)
        .expect("serialize custom target specification");

    Package::new("dependency", "1.0.0")
        .file(
            "src/lib.rs",
            r#"
                #![allow(internal_features)]
                #![feature(no_core, lang_items)]
                #![no_core]

                #[lang = "pointee_sized"]
                pub trait PointeeSized {}

                #[lang = "meta_sized"]
                pub trait MetaSized: PointeeSized {}

                #[lang = "sized"]
                pub trait Sized: MetaSized {}

                #[lang = "copy"]
                pub trait Copy {}

                pub fn value() -> u32 { 19 }
            "#,
        )
        .file("cwd-target.json", &target_specification)
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [dependencies]
                dependency = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            r#"
                #![allow(internal_features)]
                #![feature(no_core, lang_items, auto_traits)]
                #![no_core]

                extern crate dependency;

                pub fn value() -> u32 { dependency::value() }

                #[lang = "freeze"]
                unsafe auto trait Freeze {}
            "#,
        )
        .file("custom-target.json", &target_specification)
        .file("lookup-target.json", &target_specification)
        .file("cwd-target.json", &target_specification)
        .build();

    p.cargo("-Zjson-target-spec build --lib --target custom-target.json")
        .masquerade_as_nightly_cargo(&["json-target-spec"])
        .env("RUSTC_BOOTSTRAP", "1")
        .run();
    p.cargo("-Zjson-target-spec -Zohm-reuse-built-deps check --lib --target custom-target.json")
        .masquerade_as_nightly_cargo(&["json-target-spec", "ohm-reuse-built-deps"])
        .env("RUSTC_BOOTSTRAP", "1")
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();

    p.cargo("build --lib --target lookup-target")
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTFLAGS", "-Zunstable-options")
        .env("RUST_TARGET_PATH", p.root())
        .run();
    p.cargo("-Zohm-reuse-built-deps check --lib --target lookup-target")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTFLAGS", "-Zunstable-options")
        .env("RUST_TARGET_PATH", p.root())
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();

    // Rustc treats an absent target search path as a current-directory entry.
    // Its initial probe runs from the workspace while registry compilation
    // changes cwd to the downloaded dependency, so both roots need the spec.
    p.cargo("build --lib --target cwd-target")
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTFLAGS", "-Zunstable-options")
        .env_remove("RUST_TARGET_PATH")
        .run();
    p.cargo("-Zohm-reuse-built-deps check --lib --target cwd-target")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTFLAGS", "-Zunstable-options")
        .env_remove("RUST_TARGET_PATH")
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_profile_codegen_backends() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2021"

                [dependencies]
                dependency = "1.0.0"
            "#,
        )
        .file(
            ".cargo/config.toml",
            "[profile.dev]\ncodegen-backend = \"llvm\"\n",
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { dependency::value() }",
        )
        .build();

    p.cargo("-Zcodegen-backend build")
        .masquerade_as_nightly_cargo(&["codegen-backend"])
        .env("RUSTC_BOOTSTRAP", "1")
        .run();
    p.cargo("-Zcodegen-backend -Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["codegen-backend", "ohm-reuse-built-deps"])
        .env("RUSTC_BOOTSTRAP", "1")
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_rejects_global_compiler_wrappers() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build")
        .env("RUSTC_WRAPPER", tools::echo_wrapper())
        .run();
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC_WRAPPER", tools::echo_wrapper())
        .with_stderr_contains("[CHECKING] dependency v1.0.0")
        .with_stderr_contains("WRAPPER CALLED: rustc --crate-name dependency [..]")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_allows_workspace_compiler_wrappers() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build")
        .env("RUSTC_WORKSPACE_WRAPPER", tools::echo_wrapper())
        .run();
    p.cargo("-Zohm-reuse-built-deps check -v")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("RUSTC_WORKSPACE_WRAPPER", tools::echo_wrapper())
        .with_stderr_contains("[FRESH] dependency v1.0.0")
        .with_stderr_contains("WRAPPER CALLED: rustc --crate-name foo [..]")
        .with_stderr_does_not_contain("[CHECKING] dependency v1.0.0")
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_preserves_root_diagnostics() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").run();
    p.change_file(
        "src/lib.rs",
        "pub fn value() -> u32 { dependency::value(19) }",
    );
    p.cargo("-Zohm-reuse-built-deps check")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .with_status(101)
        .with_stderr_data(str![[r#"
[CHECKING] foo v0.0.1 ([ROOT]/foo)
error[E0061]: this function takes 0 arguments but 1 argument was supplied
...
[ERROR] could not compile `foo` (lib) due to 1 previous error

"#]])
        .run();
}

#[cargo_test]
fn ohm_built_registry_dependency_reuse_can_be_enabled_by_config_environment() {
    Package::new("dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let p = ohm_registry_project();

    p.cargo("build").run();
    p.cargo("check -v")
        .masquerade_as_nightly_cargo(&["ohm-reuse-built-deps"])
        .env("CARGO_UNSTABLE_OHM_REUSE_BUILT_DEPS", "true")
        .with_stderr_data(str![[r#"
[FRESH] dependency v1.0.0
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

// Checks that where a project has both a lib and a bin, the lib is only checked
// not built.
#[cargo_test]
fn issue_3418() {
    let foo = project()
        .file("src/lib.rs", "")
        .file("src/main.rs", "fn main() {}")
        .build();

    foo.cargo("check -v")
        .with_stderr_data(str![[r#"
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..] src/lib.rs [..]--emit=[..]metadata [..]`
[RUNNING] `rustc --crate-name foo [..] src/main.rs [..]--emit=[..]metadata [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

// Check on a dylib should have a different metadata hash than build.
#[cargo_test]
fn dylib_check_preserves_build_cache() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2015"
                authors = []

                [lib]
                crate-type = ["dylib"]

                [dependencies]
            "#,
        )
        .file("src/lib.rs", "")
        .build();

    p.cargo("build")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.1.0 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("check").run();

    p.cargo("build")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

// test `cargo rustc --profile check`
#[cargo_test]
fn rustc_check() {
    let foo = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [dependencies.bar]
                path = "../bar"
            "#,
        )
        .file(
            "src/main.rs",
            "extern crate bar; fn main() { ::bar::baz(); }",
        )
        .build();
    let _bar = project()
        .at("bar")
        .file("Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("src/lib.rs", "pub fn baz() {}")
        .build();

    foo.cargo("rustc --profile check -- --emit=metadata").run();

    // Verify compatible usage of --profile with --release, issue #7488
    foo.cargo("rustc --profile check --release -- --emit=metadata")
        .with_status(1)
        .with_stderr_data(str![[r#"
[ERROR] the argument '--profile <PROFILE-NAME>' cannot be used with '--release'

Usage: cargo[EXE] rustc --profile <PROFILE-NAME> [ARGS]...

For more information, try '--help'.

"#]])
        .run();

    foo.cargo("rustc --profile test --release -- --emit=metadata")
        .with_status(1)
        .with_stderr_data(str![[r#"
[ERROR] the argument '--profile <PROFILE-NAME>' cannot be used with '--release'

Usage: cargo[EXE] rustc --profile <PROFILE-NAME> [ARGS]...

For more information, try '--help'.

"#]])
        .run();
}

#[cargo_test]
fn rustc_check_err() {
    let foo = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [dependencies.bar]
                path = "../bar"
            "#,
        )
        .file(
            "src/main.rs",
            "extern crate bar; fn main() { ::bar::qux(); }",
        )
        .build();
    let _bar = project()
        .at("bar")
        .file("Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("src/lib.rs", "pub fn baz() {}")
        .build();

    foo.cargo("rustc --profile check -- --emit=metadata")
        .with_status(101)
        .with_stderr_data(str![[r#"
[LOCKING] 1 package to highest compatible version
[CHECKING] bar v0.1.0 ([ROOT]/bar)
[CHECKING] foo v0.0.1 ([ROOT]/foo)
error[E0425]: [..]
...
"#]])
        .run();
}

#[cargo_test]
fn check_all() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [workspace]
                [dependencies]
                b = { path = "b" }
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .file("examples/a.rs", "fn main() {}")
        .file("tests/a.rs", "")
        .file("src/lib.rs", "")
        .file("b/Cargo.toml", &basic_manifest("b", "0.0.1"))
        .file("b/src/main.rs", "fn main() {}")
        .file("b/src/lib.rs", "")
        .build();

    p.cargo("check --workspace -v")
        .with_stderr_data(
            str![[r#"
[CHECKING] b v0.0.1 ([ROOT]/foo/b)
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..] src/lib.rs [..]`
[RUNNING] `rustc --crate-name foo [..] src/main.rs [..]`
[RUNNING] `rustc --crate-name b [..] b/src/lib.rs [..]`
[RUNNING] `rustc --crate-name b [..] b/src/main.rs [..]`
...
"#]]
            .unordered(),
        )
        .run();
}

#[cargo_test]
fn check_all_exclude() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [workspace]
                members = ["bar", "baz"]
            "#,
        )
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("bar/src/lib.rs", "pub fn bar() {}")
        .file("baz/Cargo.toml", &basic_manifest("baz", "0.1.0"))
        .file("baz/src/lib.rs", "pub fn baz() { break_the_build(); }")
        .build();

    p.cargo("check --workspace --exclude baz")
        .with_stderr_does_not_contain("[CHECKING] baz v0.1.0 [..]")
        .with_stderr_data(str![[r#"
[CHECKING] bar v0.1.0 ([ROOT]/foo/bar)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn check_all_exclude_glob() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [workspace]
                members = ["bar", "baz"]
            "#,
        )
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("bar/src/lib.rs", "pub fn bar() {}")
        .file("baz/Cargo.toml", &basic_manifest("baz", "0.1.0"))
        .file("baz/src/lib.rs", "pub fn baz() { break_the_build(); }")
        .build();

    p.cargo("check --workspace --exclude '*z'")
        .with_stderr_does_not_contain("[CHECKING] baz v0.1.0 [..]")
        .with_stderr_data(str![[r#"
[CHECKING] bar v0.1.0 ([ROOT]/foo/bar)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn check_virtual_all_implied() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [workspace]
                members = ["bar", "baz"]
            "#,
        )
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("bar/src/lib.rs", "pub fn bar() {}")
        .file("baz/Cargo.toml", &basic_manifest("baz", "0.1.0"))
        .file("baz/src/lib.rs", "pub fn baz() {}")
        .build();

    p.cargo("check -v")
        .with_stderr_data(
            str![[r#"
[CHECKING] baz v0.1.0 ([ROOT]/foo/baz)
[CHECKING] bar v0.1.0 ([ROOT]/foo/bar)
[RUNNING] `rustc --crate-name baz [..] baz/src/lib.rs [..]`
[RUNNING] `rustc --crate-name bar [..] bar/src/lib.rs [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]
            .unordered(),
        )
        .run();
}

#[cargo_test]
fn check_virtual_manifest_one_project() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [workspace]
                members = ["bar", "baz"]
            "#,
        )
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("bar/src/lib.rs", "pub fn bar() {}")
        .file("baz/Cargo.toml", &basic_manifest("baz", "0.1.0"))
        .file("baz/src/lib.rs", "pub fn baz() { break_the_build(); }")
        .build();

    p.cargo("check -p bar")
        .with_stderr_does_not_contain("[CHECKING] baz v0.1.0 [..]")
        .with_stderr_data(str![[r#"
[CHECKING] bar v0.1.0 ([ROOT]/foo/bar)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn check_virtual_manifest_one_bin_project_not_in_default_members() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [workspace]
                members = ["bar"]
                default-members = []
                resolver = "3"
            "#,
        )
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("bar/src/main.rs", "fn main() { let _ = (1); }")
        .build();

    p.cargo("check -p bar")
        .with_stderr_contains("[..]run `cargo fix --bin \"bar\" -p bar` to apply[..]")
        .run();
}

#[cargo_test]
fn check_virtual_manifest_glob() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [workspace]
                members = ["bar", "baz"]
            "#,
        )
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("bar/src/lib.rs", "pub fn bar() {  break_the_build(); }")
        .file("baz/Cargo.toml", &basic_manifest("baz", "0.1.0"))
        .file("baz/src/lib.rs", "pub fn baz() {}")
        .build();

    p.cargo("check -p '*z'")
        .with_stderr_does_not_contain("[CHECKING] bar v0.1.0 [..]")
        .with_stderr_data(str![[r#"
[CHECKING] baz v0.1.0 ([ROOT]/foo/baz)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn exclude_warns_on_non_existing_package() {
    let p = project().file("src/lib.rs", "").build();
    p.cargo("check --workspace --exclude bar")
        .with_stdout_data("")
        .with_stderr_data(str![[r#"
[WARNING] excluded package(s) `bar` not found in workspace `[ROOT]/foo`
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn targets_selected_default() {
    let foo = project()
        .file("src/main.rs", "fn main() {}")
        .file("src/lib.rs", "pub fn smth() {}")
        .file("examples/example1.rs", "fn main() {}")
        .file("tests/test2.rs", "#[test] fn t() {}")
        .file("benches/bench3.rs", "")
        .build();

    foo.cargo("check -v")
        .with_stderr_contains("[..] --crate-name foo [..] src/lib.rs [..]")
        .with_stderr_contains("[..] --crate-name foo [..] src/main.rs [..]")
        .with_stderr_does_not_contain("[..] --crate-name example1 [..] examples/example1.rs [..]")
        .with_stderr_does_not_contain("[..] --crate-name test2 [..] tests/test2.rs [..]")
        .with_stderr_does_not_contain("[..] --crate-name bench3 [..] benches/bench3.rs [..]")
        .run();
}

#[cargo_test]
fn targets_selected_all() {
    let foo = project()
        .file("src/main.rs", "fn main() {}")
        .file("src/lib.rs", "pub fn smth() {}")
        .file("examples/example1.rs", "fn main() {}")
        .file("tests/test2.rs", "#[test] fn t() {}")
        .file("benches/bench3.rs", "")
        .build();

    foo.cargo("check --all-targets -v")
        .with_stderr_data(
            str![[r#"
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..] src/lib.rs [..]`
[RUNNING] `rustc --crate-name foo [..] src/main.rs [..]`
[RUNNING] `rustc --crate-name example1 [..] examples/example1.rs [..]`
[RUNNING] `rustc --crate-name test2 [..] tests/test2.rs [..]`
[RUNNING] `rustc --crate-name bench3 [..] benches/bench3.rs [..]`
...
"#]]
            .unordered(),
        )
        .run();
}

#[cargo_test]
fn check_unit_test_profile() {
    let foo = project()
        .file(
            "src/lib.rs",
            r#"
                #[cfg(test)]
                mod tests {
                    #[test]
                    fn it_works() {
                        badtext
                    }
                }
            "#,
        )
        .build();

    foo.cargo("check").run();
    foo.cargo("check --profile test")
        .with_status(101)
        .with_stderr_data(str![[r#"
[CHECKING] foo v0.0.1 ([ROOT]/foo)
error[E0425]: cannot find value `badtext` in this scope
...
"#]])
        .run();
}

// Verify what is checked with various command-line filters.
#[cargo_test]
fn check_filters() {
    let p = project()
        .file(
            "src/lib.rs",
            r#"
                fn unused_normal_lib() {}
                #[cfg(test)]
                mod tests {
                    fn unused_unit_lib() {}
                }
            "#,
        )
        .file(
            "src/main.rs",
            r#"
                fn main() {}
                fn unused_normal_bin() {}
                #[cfg(test)]
                mod tests {
                    fn unused_unit_bin() {}
                }
            "#,
        )
        .file(
            "tests/t1.rs",
            r#"
                fn unused_normal_t1() {}
                #[cfg(test)]
                mod tests {
                    fn unused_unit_t1() {}
                }
            "#,
        )
        .file(
            "examples/ex1.rs",
            r#"
                fn main() {}
                fn unused_normal_ex1() {}
                #[cfg(test)]
                mod tests {
                    fn unused_unit_ex1() {}
                }
            "#,
        )
        .file(
            "benches/b1.rs",
            r#"
                fn unused_normal_b1() {}
                #[cfg(test)]
                mod tests {
                    fn unused_unit_b1() {}
                }
            "#,
        )
        .build();

    p.cargo("check")
        .with_stderr_contains("[..]unused_normal_lib[..]")
        .with_stderr_contains("[..]unused_normal_bin[..]")
        .with_stderr_does_not_contain("[..]unused_normal_t1[..]")
        .with_stderr_does_not_contain("[..]unused_normal_ex1[..]")
        .with_stderr_does_not_contain("[..]unused_normal_b1[..]")
        .with_stderr_does_not_contain("[..]unused_unit_[..]")
        .run();
    p.root().join("target").rm_rf();
    p.cargo("check --tests -v")
        .with_stderr_contains("[..] --crate-name foo [..] src/lib.rs [..] --test [..]")
        .with_stderr_contains("[..] --crate-name foo [..] src/lib.rs [..] --crate-type lib [..]")
        .with_stderr_contains("[..] --crate-name foo [..] src/main.rs [..] --test [..]")
        .with_stderr_contains("[..]unused_unit_lib[..]")
        .with_stderr_contains("[..]unused_unit_bin[..]")
        .with_stderr_contains("[..]unused_normal_lib[..]")
        .with_stderr_contains("[..]unused_normal_bin[..]")
        .with_stderr_contains("[..]unused_unit_t1[..]")
        .with_stderr_does_not_contain("[..]unused_normal_ex1[..]")
        .with_stderr_does_not_contain("[..]unused_unit_ex1[..]")
        .with_stderr_does_not_contain("[..]unused_normal_b1[..]")
        .with_stderr_does_not_contain("[..]unused_unit_b1[..]")
        .with_stderr_does_not_contain("[..]--crate-type bin[..]")
        .run();
    p.root().join("target").rm_rf();
    p.cargo("check --test t1 -v")
        .with_stderr_contains("[..]unused_normal_lib[..]")
        .with_stderr_contains("[..]unused_unit_t1[..]")
        .with_stderr_does_not_contain("[..]unused_unit_lib[..]")
        .with_stderr_does_not_contain("[..]unused_normal_bin[..]")
        .with_stderr_does_not_contain("[..]unused_unit_bin[..]")
        .with_stderr_does_not_contain("[..]unused_normal_ex1[..]")
        .with_stderr_does_not_contain("[..]unused_normal_b1[..]")
        .with_stderr_does_not_contain("[..]unused_unit_ex1[..]")
        .with_stderr_does_not_contain("[..]unused_unit_b1[..]")
        .run();
    p.root().join("target").rm_rf();
    p.cargo("check --all-targets -v")
        .with_stderr_contains("[..]unused_normal_lib[..]")
        .with_stderr_contains("[..]unused_normal_bin[..]")
        .with_stderr_contains("[..]unused_normal_t1[..]")
        .with_stderr_contains("[..]unused_normal_ex1[..]")
        .with_stderr_contains("[..]unused_normal_b1[..]")
        .with_stderr_contains("[..]unused_unit_b1[..]")
        .with_stderr_contains("[..]unused_unit_t1[..]")
        .with_stderr_contains("[..]unused_unit_lib[..]")
        .with_stderr_contains("[..]unused_unit_bin[..]")
        .with_stderr_does_not_contain("[..]unused_unit_ex1[..]")
        .run();
}

#[cargo_test]
fn check_artifacts() {
    // Verify which artifacts are created when running check (#4059).
    let p = project()
        .file("src/lib.rs", "")
        .file("src/main.rs", "fn main() {}")
        .file("tests/t1.rs", "")
        .file("examples/ex1.rs", "fn main() {}")
        .file("benches/b1.rs", "")
        .build();

    p.cargo("check").run();
    assert!(!p.root().join("target/debug/libfoo.rmeta").is_file());
    assert!(!p.root().join("target/debug/libfoo.rlib").is_file());
    assert!(!p.root().join("target/debug").join(exe("foo")).is_file());
    assert_eq!(p.glob("target/debug/deps/libfoo-*.rmeta").count(), 2);

    p.root().join("target").rm_rf();
    p.cargo("check --lib").run();
    assert!(!p.root().join("target/debug/libfoo.rmeta").is_file());
    assert!(!p.root().join("target/debug/libfoo.rlib").is_file());
    assert!(!p.root().join("target/debug").join(exe("foo")).is_file());
    assert_eq!(p.glob("target/debug/deps/libfoo-*.rmeta").count(), 1);

    p.root().join("target").rm_rf();
    p.cargo("check --bin foo").run();
    assert!(!p.root().join("target/debug/libfoo.rmeta").is_file());
    assert!(!p.root().join("target/debug/libfoo.rlib").is_file());
    assert!(!p.root().join("target/debug").join(exe("foo")).is_file());
    assert_eq!(p.glob("target/debug/deps/libfoo-*.rmeta").count(), 2);

    p.root().join("target").rm_rf();
    p.cargo("check --test t1").run();
    assert!(!p.root().join("target/debug/libfoo.rmeta").is_file());
    assert!(!p.root().join("target/debug/libfoo.rlib").is_file());
    assert!(!p.root().join("target/debug").join(exe("foo")).is_file());
    assert_eq!(p.glob("target/debug/t1-*").count(), 0);
    assert_eq!(p.glob("target/debug/deps/libfoo-*.rmeta").count(), 1);
    assert_eq!(p.glob("target/debug/deps/libt1-*.rmeta").count(), 1);

    p.root().join("target").rm_rf();
    p.cargo("check --example ex1").run();
    assert!(!p.root().join("target/debug/libfoo.rmeta").is_file());
    assert!(!p.root().join("target/debug/libfoo.rlib").is_file());
    assert!(
        !p.root()
            .join("target/debug/examples")
            .join(exe("ex1"))
            .is_file()
    );
    assert_eq!(p.glob("target/debug/deps/libfoo-*.rmeta").count(), 1);
    assert_eq!(p.glob("target/debug/examples/libex1-*.rmeta").count(), 1);

    p.root().join("target").rm_rf();
    p.cargo("check --bench b1").run();
    assert!(!p.root().join("target/debug/libfoo.rmeta").is_file());
    assert!(!p.root().join("target/debug/libfoo.rlib").is_file());
    assert!(!p.root().join("target/debug").join(exe("foo")).is_file());
    assert_eq!(p.glob("target/debug/b1-*").count(), 0);
    assert_eq!(p.glob("target/debug/deps/libfoo-*.rmeta").count(), 1);
    assert_eq!(p.glob("target/debug/deps/libb1-*.rmeta").count(), 1);
}

#[cargo_test]
fn short_message_format() {
    let foo = project()
        .file("src/lib.rs", "fn foo() { let _x: bool = 'a'; }")
        .build();
    foo.cargo("check --message-format=short")
        .with_status(101)
        .with_stderr_data(str![[r#"
[CHECKING] foo v0.0.1 ([ROOT]/foo)
src/lib.rs:1:27: error[E0308]: mismatched types[..]
[ERROR] could not compile `foo` (lib) due to 1 previous error

"#]])
        .run();
}

#[cargo_test]
fn proc_macro() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "demo"
                version = "0.0.1"
                edition = "2015"

                [lib]
                proc-macro = true
            "#,
        )
        .file(
            "src/lib.rs",
            r#"
                extern crate proc_macro;

                use proc_macro::TokenStream;

                #[proc_macro_derive(Foo)]
                pub fn demo(_input: TokenStream) -> TokenStream {
                    "".parse().unwrap()
                }
            "#,
        )
        .file(
            "src/main.rs",
            r#"
                #[macro_use]
                extern crate demo;

                #[derive(Foo)]
                struct A;

                fn main() {}
            "#,
        )
        .build();
    p.cargo("check -v").env("CARGO_LOG", "cargo=trace").run();
}

#[cargo_test]
fn check_keep_going() {
    let foo = project()
        .file("src/bin/one.rs", "compile_error!(\"ONE\"); fn main() {}")
        .file("src/bin/two.rs", "compile_error!(\"TWO\"); fn main() {}")
        .build();

    // Due to -j1, without --keep-going only one of the two bins would be built.
    foo.cargo("check -j1 --keep-going")
        .with_status(101)
        .with_stderr_data(
            str![[r#"
[ERROR] ONE
[ERROR] TWO
...
"#]]
            .unordered(),
        )
        .run();
}

#[cargo_test]
fn does_not_use_empty_rustc_wrapper() {
    // An empty RUSTC_WRAPPER environment variable won't be used.
    // The env var will also override the config, essentially unsetting it.
    let p = project()
        .file("src/lib.rs", "")
        .file(
            ".cargo/config.toml",
            r#"
                [build]
                rustc-wrapper = "do-not-execute-me"
            "#,
        )
        .build();
    p.cargo("check").env("RUSTC_WRAPPER", "").run();
}

#[cargo_test]
fn does_not_use_empty_rustc_workspace_wrapper() {
    let p = project().file("src/lib.rs", "").build();
    p.cargo("check").env("RUSTC_WORKSPACE_WRAPPER", "").run();
}

#[cargo_test]
fn error_from_deep_recursion() -> Result<(), fmt::Error> {
    let mut big_macro = String::new();
    writeln!(big_macro, "macro_rules! m {{")?;
    for i in 0..130 {
        writeln!(big_macro, "({}) => {{ m!({}); }};", i, i + 1)?;
    }
    writeln!(big_macro, "}}")?;
    writeln!(big_macro, "m!(0);")?;

    let p = project().file("src/lib.rs", &big_macro).build();
    p.cargo("check --message-format=json")
        .with_status(101)
        .with_stdout_data(str![[r#"
{"reason":"compiler-message",[..]"message":"recursion limit reached while expanding `m!`",[..]rendered":"[..]recursion limit reached while expanding `m!`[..]"}}
...
"#]])
        .run();

    Ok(())
}

#[cargo_test]
fn rustc_workspace_wrapper_affects_all_workspace_members() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [workspace]
                members = ["bar", "baz"]
            "#,
        )
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("bar/src/lib.rs", "pub fn bar() {}")
        .file("baz/Cargo.toml", &basic_manifest("baz", "0.1.0"))
        .file("baz/src/lib.rs", "pub fn baz() {}")
        .build();

    p.cargo("check")
        .env("RUSTC_WORKSPACE_WRAPPER", tools::echo_wrapper())
        .with_stderr_data(
            str![[r#"
WRAPPER CALLED: rustc --crate-name bar [..]
WRAPPER CALLED: rustc --crate-name baz [..]
...
"#]]
            .unordered(),
        )
        .run();
}

#[cargo_test]
fn rustc_workspace_wrapper_includes_path_deps() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2015"
                authors = []

                [workspace]
                members = ["bar"]

                [dependencies]
                baz = { path = "baz" }
            "#,
        )
        .file("src/lib.rs", "")
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("bar/src/lib.rs", "pub fn bar() {}")
        .file("baz/Cargo.toml", &basic_manifest("baz", "0.1.0"))
        .file("baz/src/lib.rs", "pub fn baz() {}")
        .build();

    p.cargo("check --workspace")
        .env("RUSTC_WORKSPACE_WRAPPER", tools::echo_wrapper())
        .with_stderr_data(
            str![[r#"
WRAPPER CALLED: rustc --crate-name bar [..]
WRAPPER CALLED: rustc --crate-name baz [..]
WRAPPER CALLED: rustc --crate-name foo [..]
...
"#]]
            .unordered(),
        )
        .run();
}

#[cargo_test]
fn rustc_workspace_wrapper_respects_primary_units() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [workspace]
                members = ["bar", "baz"]
            "#,
        )
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("bar/src/lib.rs", "pub fn bar() {}")
        .file("baz/Cargo.toml", &basic_manifest("baz", "0.1.0"))
        .file("baz/src/lib.rs", "pub fn baz() {}")
        .build();

    p.cargo("check -p bar")
        .env("RUSTC_WORKSPACE_WRAPPER", tools::echo_wrapper())
        .with_stderr_contains("WRAPPER CALLED: rustc --crate-name bar [..]")
        .with_stdout_does_not_contain("WRAPPER CALLED: rustc --crate-name baz [..]")
        .run();
}

#[cargo_test]
fn rustc_workspace_wrapper_excludes_published_deps() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2015"
                authors = []

                [workspace]
                members = ["bar"]

                [dependencies]
                baz = "1.0.0"
            "#,
        )
        .file("src/lib.rs", "")
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("bar/src/lib.rs", "pub fn bar() {}")
        .build();

    Package::new("baz", "1.0.0").publish();

    p.cargo("check --workspace -v")
        .env("RUSTC_WORKSPACE_WRAPPER", tools::echo_wrapper())
        .with_stderr_contains("WRAPPER CALLED: rustc --crate-name foo [..]")
        .with_stderr_contains("WRAPPER CALLED: rustc --crate-name bar [..]")
        .with_stderr_contains("[CHECKING] baz [..]")
        .with_stdout_does_not_contain("WRAPPER CALLED: rustc --crate-name baz [..]")
        .run();
}

#[cargo_test]
fn warn_manifest_with_project() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [project]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("check")
        .with_stderr_data(str![[r#"
[WARNING] Cargo.toml: `[project]` is deprecated in favor of `[package]`
[WARNING] `foo` (manifest) generated 1 warning
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn error_manifest_with_project_on_2024() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [project]
                name = "foo"
                version = "0.0.1"
                edition = "2024"
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("check")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to parse manifest at `[ROOT]/foo/Cargo.toml`

Caused by:
  `[project]` is not supported as of the 2024 Edition, please use `[package]`

"#]])
        .run();
}

#[cargo_test]
fn warn_manifest_package_and_project() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"

                [project]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("check")
        .with_stderr_data(str![[r#"
[WARNING] Cargo.toml: `[project]` is deprecated in favor of `[package]`
[WARNING] `foo` (manifest) generated 1 warning
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn git_manifest_package_and_project() {
    let p = project();
    let git_project = git::new("bar", |p| {
        p.file(
            "Cargo.toml",
            r#"
            [package]
            name = "bar"
            version = "0.0.1"
            edition = "2015"

            [project]
            name = "bar"
            version = "0.0.1"
            edition = "2015"
            "#,
        )
        .file("src/lib.rs", "")
    });

    let p = p
        .file(
            "Cargo.toml",
            &format!(
                r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"

                [dependencies.bar]
                version = "0.0.1"
                git  = '{}'

            "#,
                git_project.url()
            ),
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("check")
        .with_stderr_data(str![[r#"
[UPDATING] git repository `[ROOTURL]/bar`
[LOCKING] 1 package to highest compatible version
[CHECKING] bar v0.0.1 ([ROOTURL]/bar#[..])
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn git_manifest_with_project() {
    let p = project();
    let git_project = git::new("bar", |p| {
        p.file(
            "Cargo.toml",
            r#"
            [project]
            name = "bar"
            version = "0.0.1"
            edition = "2015"
            "#,
        )
        .file("src/lib.rs", "")
    });

    let p = p
        .file(
            "Cargo.toml",
            &format!(
                r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"

                [dependencies.bar]
                version = "0.0.1"
                git  = '{}'

            "#,
                git_project.url()
            ),
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("check")
        .with_stderr_data(str![[r#"
[UPDATING] git repository `[ROOTURL]/bar`
[LOCKING] 1 package to highest compatible version
[CHECKING] bar v0.0.1 ([ROOTURL]/bar#[..])
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn check_fixable_warning() {
    let foo = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
            "#,
        )
        .file("src/lib.rs", "use std::io;")
        .build();

    foo.cargo("check")
        .with_stderr_data(str![[r#"
...
[WARNING] `foo` (lib) generated 1 warning (run `cargo fix --lib -p foo` to apply 1 suggestion)
...
"#]])
        .run();
}

#[cargo_test]
fn check_fixable_test_warning() {
    let foo = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
            "#,
        )
        .file(
            "src/lib.rs",
            "\
mod tests {
    #[test]
    fn t1() {
        use std::io;
    }
}
            ",
        )
        .build();

    foo.cargo("check --all-targets")
        .with_stderr_data(str![[r#"
...
[WARNING] `foo` (lib test) generated 1 warning (run `cargo fix --lib -p foo --tests` to apply 1 suggestion)
...
"#]])
        .run();
    foo.cargo("fix --lib -p foo --tests --allow-no-vcs").run();
    assert!(!foo.read_file("src/lib.rs").contains("use std::io;"));
}

#[cargo_test]
fn check_fixable_error_no_fix() {
    let foo = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
            "#,
        )
        .file(
            "src/lib.rs",
            "use std::io;\n#[derive(Debug(x))]\nstruct Foo;",
        )
        .build();

    foo.cargo("check")
        .with_status(101)
        .with_stderr_data(
            str![[r#"
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[ERROR] traits in `#[derive(...)]` don't accept arguments
[WARNING] unused import: `std::io`
[WARNING] `foo` (lib) generated 1 warning
[ERROR] could not compile `foo` (lib) due to 1 previous error; 1 warning emitted
...
"#]]
            .unordered(),
        )
        .run();
}

#[cargo_test]
fn check_fixable_warning_workspace() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [workspace]
                members = ["foo", "bar"]
            "#,
        )
        .file(
            "foo/Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
            "#,
        )
        .file("foo/src/lib.rs", "use std::io;")
        .file(
            "bar/Cargo.toml",
            r#"
                [package]
                name = "bar"
                version = "0.0.1"
                edition = "2015"

                [dependencies]
                foo = { path = "../foo" }
            "#,
        )
        .file("bar/src/lib.rs", "use std::io;")
        .build();

    p.cargo("check")
        .with_stderr_data(
            str![[r#"
[WARNING] `foo` (lib) generated 1 warning (run `cargo fix --lib -p foo` to apply 1 suggestion)
[WARNING] `bar` (lib) generated 1 warning (run `cargo fix --lib -p bar` to apply 1 suggestion)
...
"#]]
            .unordered(),
        )
        .run();
}

#[cargo_test]
fn check_fixable_example() {
    let p = project()
        .file("Cargo.toml", &basic_bin_manifest("foo"))
        .file(
            "src/main.rs",
            r#"
            fn hello() -> &'static str {
                "hello"
            }

            pub fn main() {
                println!("{}", hello())
            }
            "#,
        )
        .file("examples/ex1.rs", "use std::fmt; fn main() {}")
        .build();
    p.cargo("check --all-targets")
        .with_stderr_data(str![[r#"
...
[WARNING] `foo` (example "ex1") generated 1 warning (run `cargo fix --example "ex1" -p foo` to apply 1 suggestion)
...
"#]])
        .run();
}

#[cargo_test(nightly, reason = "bench")]
fn check_fixable_bench() {
    let p = project()
        .file("Cargo.toml", &basic_bin_manifest("foo"))
        .file(
            "src/main.rs",
            r#"
            #![feature(test)]
            #[cfg(test)]
            extern crate test;

            fn hello() -> &'static str {
                "hello"
            }

            pub fn main() {
                println!("{}", hello())
            }

            #[bench]
            fn bench_hello(_b: &mut test::Bencher) {
                use std::io;
                assert_eq!(hello(), "hello")
            }
            "#,
        )
        .file(
            "benches/bench.rs",
            "
            #![feature(test)]
            extern crate test;

            #[bench]
            fn bench(_b: &mut test::Bencher) { use std::fmt; }
        ",
        )
        .build();
    p.cargo("check --all-targets")
        .with_stderr_data(str![[r#"
...
[WARNING] `foo` (bench "bench") generated 1 warning (run `cargo fix --bench "bench" -p foo` to apply 1 suggestion)
...
"#]])
        .run();
}

#[cargo_test(nightly, reason = "bench")]
fn check_fixable_mixed() {
    let p = project()
        .file("Cargo.toml", &basic_bin_manifest("foo"))
        .file(
            "src/main.rs",
            r#"
            #![feature(test)]
            #[cfg(test)]
            extern crate test;

            fn hello() -> &'static str {
                "hello"
            }

            pub fn main() {
                println!("{}", hello())
            }

            #[bench]
            fn bench_hello(_b: &mut test::Bencher) {
                use std::io;
                assert_eq!(hello(), "hello")
            }
            #[test]
            fn t1() {
                use std::fmt;
            }
            "#,
        )
        .file("examples/ex1.rs", "use std::fmt; fn main() {}")
        .file(
            "benches/bench.rs",
            "
            #![feature(test)]
            extern crate test;

            #[bench]
            fn bench(_b: &mut test::Bencher) { use std::fmt; }
        ",
        )
        .build();
    p.cargo("check --all-targets")
        .with_stderr_data(str![[r#"
[WARNING] `foo` (example "ex1") generated 1 warning (run `cargo fix --example "ex1" -p foo` to apply 1 suggestion)
[WARNING] `foo` (bench "bench") generated 1 warning (run `cargo fix --bench "bench" -p foo` to apply 1 suggestion)
[WARNING] `foo` (bin "foo" test) generated 2 warnings (run `cargo fix --bin "foo" -p foo --tests` to apply 2 suggestions)
...
"#]].unordered())
        .run();
}

#[cargo_test]
fn check_fixable_warning_for_clippy() {
    let foo = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
            "#,
        )
        // We don't want to show a warning that is `clippy`
        // specific since we are using a `rustc` wrapper
        // inplace of `clippy`
        .file("src/lib.rs", "use std::io;")
        .build();

    foo.cargo("check")
        // We can't use `clippy` so we use a `rustc` workspace wrapper instead
        .env("RUSTC_WORKSPACE_WRAPPER", tools::wrapped_clippy_driver())
        .with_stderr_data(str![[r#"
...
[WARNING] `foo` (lib) generated 1 warning (run `cargo clippy --fix --lib -p foo` to apply 1 suggestion)
...
"#]])
        .run();

    foo.cargo("check")
        .env("RUSTC_WORKSPACE_WRAPPER", tools::wrapped_clippy_driver())
        .env("CLIPPY_ARGS", "-Wclippy::pedantic__CLIPPY_HACKERY__-Aclippy::allow_attributes__CLIPPY_HACKERY__") // Set -Wclippy::pedantic
        .with_stderr_data(str![[r#"
...
[WARNING] `foo` (lib) generated 1 warning (run `cargo clippy --fix --lib -p foo -- -Wclippy::pedantic -Aclippy::allow_attributes` to apply 1 suggestion)
...
"#]])
        .run();
}

#[cargo_test]
fn check_unused_manifest_keys() {
    Package::new("dep", "0.1.0").publish();
    Package::new("foo", "0.1.0").publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "bar"
            version = "0.2.0"
            edition = "2015"
            authors = []

            [dependencies]
            dep = { version = "0.1.0", wxz = "wxz" }
            foo = { version = "0.1.0", abc = "abc" }

            [dev-dependencies]
            foo = { version = "0.1.0", wxz = "wxz" }

            [build-dependencies]
            foo = { version = "0.1.0", wxz = "wxz" }

            [target.'cfg(windows)'.dependencies]
            foo = { version = "0.1.0", wxz = "wxz" }

            [target.wasm32-wasip1.dev-dependencies]
            foo = { version = "0.1.0", wxz = "wxz" }

            [target.bar.build-dependencies]
            foo = { version = "0.1.0", wxz = "wxz" }
        "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("check")
        .with_stderr_data(
            str![[r#"
[WARNING] Cargo.toml: unused manifest key: dependencies.dep.wxz
[WARNING] Cargo.toml: unused manifest key: dependencies.foo.abc
[WARNING] Cargo.toml: unused manifest key: dev-dependencies.foo.wxz
[WARNING] Cargo.toml: unused manifest key: build-dependencies.foo.wxz
[WARNING] Cargo.toml: unused manifest key: target.bar.build-dependencies.foo.wxz
[WARNING] Cargo.toml: unused manifest key: target.cfg(windows).dependencies.foo.wxz
[WARNING] Cargo.toml: unused manifest key: target.wasm32-wasip1.dev-dependencies.foo.wxz
[WARNING] `bar` (manifest) generated 7 warnings
[UPDATING] `dummy-registry` index
[LOCKING] 2 packages to highest compatible versions
[DOWNLOADING] crates ...
[DOWNLOADED] foo v0.1.0 (registry `dummy-registry`)
[DOWNLOADED] dep v0.1.0 (registry `dummy-registry`)
[CHECKING] foo v0.1.0
[CHECKING] dep v0.1.0
[CHECKING] bar v0.2.0 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]
            .unordered(),
        )
        .run();
}

#[cargo_test]
fn versionless_package() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                description = "foo"
                edition = "2015"
            "#,
        )
        .file("src/lib.rs", "")
        .build();
    p.cargo("check")
        .with_stderr_data(str![[r#"
[CHECKING] foo v0.0.0 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn pkgid_querystring_works() {
    let git_project = git::new("gitdep", |p| {
        p.file("Cargo.toml", &basic_manifest("gitdep", "1.0.0"))
            .file("src/lib.rs", "")
    });
    let p = project()
        .file(
            "Cargo.toml",
            &format!(
                r#"
                [package]
                name = "foo"
                edition = "2015"

                [dependencies]
                gitdep = {{ git = "{}", branch = "master" }}
                "#,
                git_project.url()
            ),
        )
        .file("src/lib.rs", "")
        .build();

    p.cargo("generate-lockfile").run();

    let output = p.cargo("pkgid").arg("gitdep").run();
    let gitdep_pkgid = String::from_utf8(output.stdout).unwrap();
    let gitdep_pkgid = gitdep_pkgid.trim();
    assert_e2e().eq(
        gitdep_pkgid,
        str!["git+[ROOTURL]/gitdep?branch=master#1.0.0"],
    );

    p.cargo("build -p")
        .arg(gitdep_pkgid)
        .with_stderr_data(str![[r#"
[COMPILING] gitdep v1.0.0 ([ROOTURL]/gitdep?branch=master#[..])
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn check_build_should_not_output_files_to_artifact_dir() {
    let p = project()
        .file("src/main.rs", r#"fn main() { println!("Hello, World!") }"#)
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            target-dir = "target-dir"
            build-dir = "build-dir"
            "#,
        )
        .build();

    p.cargo("check").enable_mac_dsym().run();

    p.root()
        .join("target-dir")
        .assert_build_dir_layout(str![[r#"
[ROOT]/foo/target-dir/CACHEDIR.TAG
[ROOT]/foo/target-dir/debug/.cargo-lock

"#]]);
}

#[cargo_test]
fn check_build_should_lock_target_dir_when_artifact_dir_is_same_as_build_dir() {
    let p = project()
        .file("src/main.rs", r#"fn main() { println!("Hello, World!") }"#)
        .build();

    p.cargo("check").enable_mac_dsym().run();
    assert!(p.root().join("target/debug/.cargo-build-lock").exists());
}

#[cargo_test]
fn check_build_should_not_lock_artifact_dir_when_build_dir_is_not_same_dir() {
    let p = project()
        .file("src/main.rs", r#"fn main() { println!("Hello, World!") }"#)
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            target-dir = "target-dir"
            build-dir = "build-dir"
            "#,
        )
        .build();

    p.cargo("check").enable_mac_dsym().run();

    // Verify we did NOT take the artifact-dir lock
    assert!(
        !p.root()
            .join("target-dir/debug/.cargo-artifact-lock")
            .exists()
    );
    // Verify we did take the build-dir lock
    assert!(p.root().join("build-dir/debug/.cargo-build-lock").exists());
}

// Regression test for #16305
#[cargo_test]
fn check_build_should_not_uplift_proc_macro_dylib_deps() {
    let p = project()
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            target-dir = "target-dir"
            build-dir = "build-dir"
            "#,
        )
        .file(
            "Cargo.toml",
            r#"
                [workspace]
                members = ["foo", "bar", "baz"]
            "#,
        )
        // Bin
        .file(
            "foo/Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"

                [dependencies]
                bar = { path = "../bar" }
            "#,
        )
        .file("foo/src/main.rs", "fn main() {}")
        // Proc macro
        .file(
            "bar/Cargo.toml",
            r#"
                [package]
                name = "bar"
                version = "0.0.1"
                edition = "2015"

                [lib]
                proc-macro = true

                [dependencies]
                baz = { path = "../baz" }
            "#,
        )
        .file(
            "bar/src/lib.rs",
            r#"
            extern crate proc_macro;

            use proc_macro::TokenStream;

            #[proc_macro_derive(B)]
            pub fn derive(input: TokenStream) -> TokenStream {
                input
            }
            "#,
        )
        // Dylib
        .file(
            "baz/Cargo.toml",
            r#"
                [package]
                name = "baz"
                version = "0.1.0"
                edition = "2015"
                authors = []

                [lib]
                crate-type = ["dylib"]

                [dependencies]
            "#,
        )
        .file("baz/src/lib.rs", "pub fn baz() { }")
        .build();

    p.cargo("check").enable_mac_dsym().run();

    p.root()
        .join("target-dir")
        .assert_build_dir_layout(str![[r#"
[ROOT]/foo/target-dir/CACHEDIR.TAG
[ROOT]/foo/target-dir/debug/.cargo-lock

"#]]);
}
