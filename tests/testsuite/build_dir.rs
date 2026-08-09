//! Tests for `build.build-dir` config property.
//!
//! The testing strategy for build-dir functionality is primarily checking if directories / files
//! are in the expected locations.
//! The rational is that other tests will verify each individual feature, while the tests in this
//! file verify the files saved to disk are in the correct locations according to the `build-dir`
//! configuration.
//!
//! Tests check if directories match some "layout" by using [`CargoPathExt::assert_file_layout`]

use std::path::PathBuf;

use crate::prelude::*;
use crate::utils::tools;
use cargo_test_support::registry::{Package, RegistryBuilder};
use cargo_test_support::{paths, prelude::*, project, project_in, rustc_host, str};
use std::env::consts::{DLL_PREFIX, DLL_SUFFIX, EXE_SUFFIX};

#[cargo_test]
fn binary_with_debug() {
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

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    assert_not_exists(&p.root().join("target"));

    p.root().join("build-dir").assert_build_dir_layout(str![[r#"
[ROOT]/foo/build-dir/.rustc_info.json
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/debug/.cargo-build-lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..].d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/.lock

"#]]);

    p.root()
        .join("target-dir")
        .assert_build_dir_layout(str![[r#"
[ROOT]/foo/target-dir/CACHEDIR.TAG
[ROOT]/foo/target-dir/debug/.cargo-lock
[ROOT]/foo/target-dir/debug/.cargo-artifact-lock
[ROOT]/foo/target-dir/debug/foo[EXE]
[ROOT]/foo/target-dir/debug/foo.d

"#]]);
}

#[cargo_test]
fn binary_with_release() {
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

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build --release")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    assert_exists_patterns_with_base_dir(
        &p.root(),
        &[
            // Check the pre-uplifted binary in the build-dir
            &format!("build-dir/release/build/foo/*/out/foo*{EXE_SUFFIX}"),
            "build-dir/release/build/foo/*/out/foo*.d",
            // Verify the binary was copied to the target-dir
            &format!("target-dir/release/foo{EXE_SUFFIX}"),
            "target-dir/release/foo.d",
        ],
    );
    p.root().join("build-dir").assert_build_dir_layout(str![[r#"
[ROOT]/foo/build-dir/.rustc_info.json
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/release/.cargo-build-lock
[ROOT]/foo/build-dir/release/build/foo/[HASH]/fingerprint/bin-foo
[ROOT]/foo/build-dir/release/build/foo/[HASH]/fingerprint/bin-foo.json
[ROOT]/foo/build-dir/release/build/foo/[HASH]/fingerprint/dep-bin-foo
[ROOT]/foo/build-dir/release/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/release/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/foo/build-dir/release/build/foo/[HASH]/out/foo[..].d
[ROOT]/foo/build-dir/release/build/foo/[HASH]/.lock

"#]]);

    p.root()
        .join("target-dir")
        .assert_build_dir_layout(str![[r#"
[ROOT]/foo/target-dir/CACHEDIR.TAG
[ROOT]/foo/target-dir/release/.cargo-lock
[ROOT]/foo/target-dir/release/.cargo-artifact-lock
[ROOT]/foo/target-dir/release/foo[EXE]
[ROOT]/foo/target-dir/release/foo.d

"#]]);
}

#[cargo_test]
fn libs() {
    // https://doc.rust-lang.org/reference/linkage.html#r-link.staticlib
    let (staticlib_prefix, staticlib_suffix) =
        if cfg!(target_os = "windows") && cfg!(target_env = "msvc") {
            ("", ".lib")
        } else {
            ("lib", ".a")
        };

    // (crate-type, list of final artifacts)
    let lib_types = [
        ("lib", ["libfoo.rlib", "libfoo.d"]),
        (
            "dylib",
            [
                &format!("{DLL_PREFIX}foo{DLL_SUFFIX}"),
                &format!("{DLL_PREFIX}foo.d"),
            ],
        ),
        (
            "cdylib",
            [
                &format!("{DLL_PREFIX}foo{DLL_SUFFIX}"),
                &format!("{DLL_PREFIX}foo.d"),
            ],
        ),
        (
            "staticlib",
            [
                &format!("{staticlib_prefix}foo{staticlib_suffix}"),
                &format!("{staticlib_prefix}foo.d"),
            ],
        ),
    ];

    for (lib_type, expected_files) in lib_types {
        let p = project()
            .file("src/lib.rs", r#"fn foo() { println!("Hello, World!") }"#)
            .file(
                "Cargo.toml",
                &format!(
                    r#"
            [package]
            name = "foo"
            version = "0.0.1"
            authors = []
            edition = "2015"

            [lib]
            crate-type = ["{lib_type}"]
            "#
                ),
            )
            .file(
                ".cargo/config.toml",
                r#"
            [build]
            target-dir = "target-dir"
            build-dir = "build-dir"
            "#,
            )
            .build();

        p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build")
            .masquerade_as_nightly_cargo(&["new build-dir layout"])
            .enable_mac_dsym()
            .run();

        // Verify lib artifacts were copied into the artifact dir
        assert_exists_patterns_with_base_dir(&p.root().join("target-dir/debug"), &expected_files);
    }
}

#[cargo_test]
fn should_default_to_target() {
    let p = project()
        .file("src/main.rs", r#"fn main() { println!("Hello, World!") }"#)
        .build();

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    p.root().join("target").assert_build_dir_layout(str![[r#"
[ROOT]/foo/target/.rustc_info.json
[ROOT]/foo/target/CACHEDIR.TAG
[ROOT]/foo/target/debug/.cargo-lock
[ROOT]/foo/target/debug/.cargo-artifact-lock
[ROOT]/foo/target/debug/.cargo-build-lock
[ROOT]/foo/target/debug/build/foo/[HASH]/fingerprint/bin-foo
[ROOT]/foo/target/debug/build/foo/[HASH]/fingerprint/bin-foo.json
[ROOT]/foo/target/debug/build/foo/[HASH]/fingerprint/dep-bin-foo
[ROOT]/foo/target/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/target/debug/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/foo/target/debug/build/foo/[HASH]/out/foo[..].d
[ROOT]/foo/target/debug/foo[EXE]
[ROOT]/foo/target/debug/foo.d
[ROOT]/foo/target/debug/build/foo/[HASH]/.lock

"#]]);
}

#[cargo_test]
fn should_respect_env_var() {
    let p = project()
        .file("src/main.rs", r#"fn main() { println!("Hello, World!") }"#)
        .build();

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .env("CARGO_BUILD_BUILD_DIR", "build-dir")
        .enable_mac_dsym()
        .run();

    p.root().join("build-dir").assert_build_dir_layout(str![[r#"
[ROOT]/foo/build-dir/.rustc_info.json
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/debug/.cargo-build-lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..].d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/.lock

"#]]);
}

#[cargo_test]
fn build_script_should_output_to_build_dir() {
    let p = project()
        .file("src/main.rs", r#"fn main() { println!("Hello, World!") }"#)
        .file(
            "build.rs",
            r#"
            fn main() {
                std::fs::write(
                    format!("{}/foo.txt", std::env::var("OUT_DIR").unwrap()),
                    "Hello, world!",
                )
                .unwrap();
            }
            "#,
        )
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            target-dir = "target-dir"
            build-dir = "build-dir"
            "#,
        )
        .build();

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    p.root().join("build-dir").assert_build_dir_layout(str![[r#"
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/debug/.cargo-build-lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo.txt
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/build_script_build.d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/build_script_build[EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..].d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo.json
[ROOT]/foo/build-dir/.rustc_info.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/run-build-script-build-script-build
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/run-build-script-build-script-build.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-build-script-build-script-build
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/build-script-build-script-build
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/build-script-build-script-build.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/run/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/run/stdout
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/run/root-output
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/run/stderr
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/.lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/.lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/.lock

"#]]);
}

#[cargo_test]
fn cargo_tmpdir_should_output_to_build_dir() {
    let p = project()
        .file("src/main.rs", r#"fn main() { println!("Hello, World!") }"#)
        .file(
            "tests/foo.rs",
            r#"
            #[test]
            fn test() {
                std::fs::write(
                    format!("{}/foo.txt", env!("CARGO_TARGET_TMPDIR")),
                    "Hello, world!",
                )
                .unwrap();
            }
            "#,
        )
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            target-dir = "target-dir"
            build-dir = "build-dir"
            "#,
        )
        .build();

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking test")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    p.root().join("build-dir").assert_build_dir_layout(str![[r#"
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/debug/.cargo-build-lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo-[HASH].d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo.d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..].d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo-[HASH][EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-test-bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/test-bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/test-bin-foo.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-test-integration-test-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/test-integration-test-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/test-integration-test-foo.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/.lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/.lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/.lock
[ROOT]/foo/build-dir/tmp/foo.txt
[ROOT]/foo/build-dir/.rustc_info.json

"#]]);

    p.root()
        .join("target-dir")
        .assert_build_dir_layout(str![[r#"
[ROOT]/foo/target-dir/CACHEDIR.TAG
[ROOT]/foo/target-dir/debug/.cargo-lock
[ROOT]/foo/target-dir/debug/.cargo-artifact-lock
[ROOT]/foo/target-dir/debug/foo[EXE]

"#]]);
}

#[cargo_test]
fn examples_should_output_to_build_dir_and_uplift_to_target_dir() {
    let p = project()
        .file("src/main.rs", r#"fn main() { println!("Hello, World!") }"#)
        .file("examples/foo.rs", r#"fn main() { }"#)
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            target-dir = "target-dir"
            build-dir = "build-dir"
            "#,
        )
        .build();

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build --examples")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    p.root().join("build-dir").assert_build_dir_layout(str![[r#"
[ROOT]/foo/build-dir/.rustc_info.json
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/debug/.cargo-build-lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-example-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/example-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/example-foo.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..].d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/.lock

"#]]);

    assert!(!p.root().join("build-dir/debug/examples").exists());

    p.root()
        .join("target-dir")
        .assert_build_dir_layout(str![[r#"
[ROOT]/foo/target-dir/CACHEDIR.TAG
[ROOT]/foo/target-dir/debug/.cargo-lock
[ROOT]/foo/target-dir/debug/.cargo-artifact-lock
[ROOT]/foo/target-dir/debug/examples/foo[EXE]
[ROOT]/foo/target-dir/debug/examples/foo.d

"#]]);
}

#[cargo_test]
fn benches_should_output_to_build_dir() {
    let p = project()
        .file("src/main.rs", r#"fn main() { println!("Hello, World!") }"#)
        .file("benches/foo.rs", r#"fn main() { }"#)
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            target-dir = "target-dir"
            build-dir = "build-dir"
            "#,
        )
        .build();

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build --bench=foo")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    p.root().join("build-dir").assert_build_dir_layout(str![[r#"
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/debug/.cargo-build-lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo-[HASH].d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..].d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo-[HASH][EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-test-bench-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/test-bench-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/test-bench-foo.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/.lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/.lock
[ROOT]/foo/build-dir/.rustc_info.json

"#]]);

    p.root()
        .join("target-dir")
        .assert_build_dir_layout(str![[r#"
[ROOT]/foo/target-dir/CACHEDIR.TAG
[ROOT]/foo/target-dir/debug/.cargo-lock
[ROOT]/foo/target-dir/debug/.cargo-artifact-lock
[ROOT]/foo/target-dir/debug/foo[EXE]

"#]]);
}

#[cargo_test]
fn cargo_doc_should_output_to_target_dir() {
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

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking doc")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    let docs_dir = p.root().join("target-dir/doc");

    assert_exists(&docs_dir);
    assert_exists(&docs_dir.join("foo/index.html"));
}

#[cargo_test(nightly, reason = "--output-format is unstable")]
fn cargo_rustdoc_json_should_output_to_target_dir() {
    let p = project()
        .file("src/lib.rs", "")
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            target-dir = "target-dir"
            build-dir = "build-dir"
            "#,
        )
        .build();

    p.cargo("-Zbuild-dir-new-layout -Zunstable-options rustdoc --output-format json")
        .masquerade_as_nightly_cargo(&["new build-dir layout", "rustdoc-output-format"])
        .enable_mac_dsym()
        .run();

    let docs_dir = p.root().join("target-dir/doc");

    assert_exists(&docs_dir);
    assert_exists(&docs_dir.join("foo.json"));

    p.root().join("build-dir").assert_build_dir_layout(str![
        r#"
[ROOT]/foo/build-dir/.rustc_info.json
[ROOT]/foo/build-dir/.rustdoc_fingerprint.json
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/debug/.cargo-build-lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/doc-lib-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/doc-lib-foo.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo.json

"#
    ]);
}

#[cargo_test]
fn cargo_package_should_build_in_build_dir_and_output_to_target_dir() {
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

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking package")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    let package_artifact_dir = p.root().join("target-dir/package");
    assert_exists(&package_artifact_dir);
    assert_exists(&package_artifact_dir.join("foo-0.0.1.crate"));
    assert!(package_artifact_dir.join("foo-0.0.1.crate").is_file());
    // FIXME: The `.cargo-lock` file should be in target-dir not build-dir. See #16707
    p.root().join("build-dir").assert_build_dir_layout(str![[r#"
[ROOT]/foo/build-dir/.rustc_info.json
[ROOT]/foo/build-dir/debug/.cargo-lock
[ROOT]/foo/build-dir/debug/.cargo-artifact-lock
[ROOT]/foo/build-dir/debug/.cargo-build-lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..].d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/.lock
[ROOT]/foo/build-dir/debug/foo[EXE]
[ROOT]/foo/build-dir/debug/foo.d
[ROOT]/foo/build-dir/package/foo-0.0.1/Cargo.lock
[ROOT]/foo/build-dir/package/foo-0.0.1/Cargo.toml
[ROOT]/foo/build-dir/package/foo-0.0.1/Cargo.toml.orig
[ROOT]/foo/build-dir/package/foo-0.0.1/src/main.rs
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/package/tmp-crate/foo-0.0.1.crate

"#]]);

    p.root()
        .join("target-dir")
        .assert_build_dir_layout(str![[r#"
[ROOT]/foo/target-dir/package/foo-0.0.1.crate
[ROOT]/foo/target-dir/CACHEDIR.TAG

"#]]);
}

#[cargo_test]
fn cargo_publish_should_only_touch_build_dir() {
    let registry = RegistryBuilder::new().http_api().http_index().build();

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

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking publish")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .replace_crates_io(registry.index_url())
        .enable_mac_dsym()
        .run();

    let package_artifact_dir = p.root().join("target-dir/package");
    assert!(!package_artifact_dir.exists());

    let package_build_dir = p.root().join("build-dir/package");
    assert_exists(&package_build_dir);
    assert_exists(&package_build_dir.join("foo-0.0.1"));
    assert!(package_build_dir.join("foo-0.0.1").is_dir());
}

#[cargo_test]
fn cargo_clean_should_clean_the_target_dir_and_build_dir() {
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

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    p.root().join("build-dir").assert_build_dir_layout(str![[r#"
[ROOT]/foo/build-dir/.rustc_info.json
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/debug/.cargo-build-lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..].d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/.lock

"#]]);

    p.root()
        .join("target-dir")
        .assert_build_dir_layout(str![[r#"
[ROOT]/foo/target-dir/CACHEDIR.TAG
[ROOT]/foo/target-dir/debug/.cargo-lock
[ROOT]/foo/target-dir/debug/.cargo-artifact-lock
[ROOT]/foo/target-dir/debug/foo[EXE]
[ROOT]/foo/target-dir/debug/foo.d

"#]]);

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking clean")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    assert_not_exists(&p.root().join("build-dir"));
    assert_not_exists(&p.root().join("target-dir"));
}

#[cargo_test]
fn cargo_clean_should_remove_correct_files() {
    Package::new("bar", "0.1.0").publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
                authors = []
                exclude = ["*.txt"]
                license = "MIT"
                description = "foo"

                [dependencies]
                bar = "0.1"
            "#,
        )
        .file("src/main.rs", r#"fn main() { println!("Hello, World!"); }"#)
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            target-dir = "target-dir"
            build-dir = "build-dir"
            "#,
        )
        .build();

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    p.root().join("build-dir").assert_build_dir_layout(str![[r#"
[ROOT]/foo/build-dir/.rustc_info.json
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/debug/.cargo-build-lock
[ROOT]/foo/build-dir/debug/build/bar/[HASH]/out/bar-[HASH].d
[ROOT]/foo/build-dir/debug/build/bar/[HASH]/out/libbar-[HASH].rlib
[ROOT]/foo/build-dir/debug/build/bar/[HASH]/out/libbar-[HASH].rmeta
[ROOT]/foo/build-dir/debug/build/bar/[HASH]/fingerprint/dep-lib-bar
[ROOT]/foo/build-dir/debug/build/bar/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/bar/[HASH]/fingerprint/lib-bar
[ROOT]/foo/build-dir/debug/build/bar/[HASH]/fingerprint/lib-bar.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..].d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/bar/[HASH]/.lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/.lock
[ROOT]/foo/build-dir/debug/build/bar/[HASH]/fingerprint/ohm-message-provenance-lib-bar

"#]]);

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking clean -p bar")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    p.root().join("build-dir").assert_build_dir_layout(str![[r#"
[ROOT]/foo/build-dir/.rustc_info.json
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/debug/.cargo-build-lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..].d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/.lock

"#]]);
}

#[cargo_test]
fn timings_report_should_output_to_target_dir() {
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

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build --timings")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    assert_exists(&p.root().join("target-dir/cargo-timings/cargo-timing.html"));
}

#[cargo_test(
    nightly,
    reason = "-Zfuture-incompat-test requires nightly (permanently)"
)]
fn future_incompat_should_output_to_build_dir() {
    let p = project()
        .file("src/main.rs", r#"fn main() { let x = 1; }"#)
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            target-dir = "target-dir"
            build-dir = "build-dir"
            "#,
        )
        .build();

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .arg("--future-incompat-report")
        .env("RUSTFLAGS", "-Zfuture-incompat-test")
        .run();

    assert_exists(&p.root().join("build-dir/.future-incompat-report.json"));
}

#[cargo_test]
fn template_should_error_for_invalid_variables() {
    let p = project()
        .file("src/main.rs", r#"fn main() { println!("Hello, World!") }"#)
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            build-dir = "{fake}/build-dir"
            target-dir = "target-dir"
            "#,
        )
        .build();

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] unexpected variable `fake` in build.build-dir path `{fake}/build-dir`

[HELP] available template variables are `{workspace-root}`, `{cargo-cache-home}`, `{workspace-path-hash}`

"#]])
        .run();
}

#[cargo_test]
fn template_should_suggest_nearest_variable() {
    let p = project()
        .file("src/lib.rs", "")
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            build-dir = "{workspace-ro}/build-dir"
            "#,
        )
        .build();

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] unexpected variable `workspace-ro` in build.build-dir path `{workspace-ro}/build-dir`

[HELP] a template variable with a similar name exists: `workspace-root`

"#]])
        .run();
}

#[cargo_test]
fn template_workspace_root() {
    let p = project()
        .file("src/main.rs", r#"fn main() { println!("Hello, World!") }"#)
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            build-dir = "{workspace-root}/build-dir"
            target-dir = "target-dir"
            "#,
        )
        .build();

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    // Verify the binary was uplifted to the target-dir
    assert_exists(&p.root().join(&format!("target-dir/debug/foo{EXE_SUFFIX}")));
    p.root().join("build-dir").assert_build_dir_layout(str![[r#"
[ROOT]/foo/build-dir/.rustc_info.json
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/debug/.cargo-build-lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..].d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/.lock

"#]]);

    p.root()
        .join("target-dir")
        .assert_build_dir_layout(str![[r#"
[ROOT]/foo/target-dir/CACHEDIR.TAG
[ROOT]/foo/target-dir/debug/.cargo-lock
[ROOT]/foo/target-dir/debug/.cargo-artifact-lock
[ROOT]/foo/target-dir/debug/foo[EXE]
[ROOT]/foo/target-dir/debug/foo.d

"#]]);
}

#[cargo_test]
fn template_cargo_cache_home() {
    let p = project()
        .file("src/main.rs", r#"fn main() { println!("Hello, World!") }"#)
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            build-dir = "{cargo-cache-home}/build-dir"
            target-dir = "target-dir"
            "#,
        )
        .build();

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    // Verify the binary was uplifted to the target-dir
    assert_exists(&p.root().join(&format!("target-dir/debug/foo{EXE_SUFFIX}")));
    paths::cargo_home()
        .join("build-dir")
        .assert_build_dir_layout(str![[r#"
[ROOT]/home/.cargo/build-dir/.rustc_info.json
[ROOT]/home/.cargo/build-dir/CACHEDIR.TAG
[ROOT]/home/.cargo/build-dir/debug/.cargo-build-lock
[ROOT]/home/.cargo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo
[ROOT]/home/.cargo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo.json
[ROOT]/home/.cargo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-bin-foo
[ROOT]/home/.cargo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/home/.cargo/build-dir/debug/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/home/.cargo/build-dir/debug/build/foo/[HASH]/out/foo[..].d
[ROOT]/home/.cargo/build-dir/debug/build/foo/[HASH]/.lock

"#]]);

    p.root()
        .join("target-dir")
        .assert_build_dir_layout(str![[r#"
[ROOT]/foo/target-dir/CACHEDIR.TAG
[ROOT]/foo/target-dir/debug/.cargo-lock
[ROOT]/foo/target-dir/debug/.cargo-artifact-lock
[ROOT]/foo/target-dir/debug/foo[EXE]
[ROOT]/foo/target-dir/debug/foo.d

"#]]);
}

#[cargo_test]
fn template_workspace_path_hash() {
    let p = project()
        .file("src/main.rs", r#"fn main() { println!("Hello, World!") }"#)
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "foo"
            version = "1.0.0"
            authors = []
            edition = "2015"
            "#,
        )
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            build-dir = "foo/{workspace-path-hash}/build-dir"
            target-dir = "target-dir"
            "#,
        )
        .build();

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    let foo_dir = p.root().join("foo");
    assert_exists(&foo_dir);
    let hash_dir = parse_workspace_manifest_path_hash(&foo_dir);

    let build_dir = hash_dir.as_path().join("build-dir");

    // Verify the binary was uplifted to the target-dir
    assert_exists(&p.root().join(&format!("target-dir/debug/foo{EXE_SUFFIX}")));
    build_dir.assert_build_dir_layout(str![[r#"
[ROOT]/foo/foo/[HASH]/build-dir/.rustc_info.json
[ROOT]/foo/foo/[HASH]/build-dir/CACHEDIR.TAG
[ROOT]/foo/foo/[HASH]/build-dir/debug/.cargo-build-lock
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo.json
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/fingerprint/dep-bin-foo
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/out/foo[..].d
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/.lock

"#]]);

    p.root()
        .join("target-dir")
        .assert_build_dir_layout(str![[r#"
[ROOT]/foo/target-dir/CACHEDIR.TAG
[ROOT]/foo/target-dir/debug/.cargo-lock
[ROOT]/foo/target-dir/debug/.cargo-artifact-lock
[ROOT]/foo/target-dir/debug/foo[EXE]
[ROOT]/foo/target-dir/debug/foo.d

"#]]);
}

/// Verify that the {workspace-path-hash} does not changes if cargo is run from inside of
/// a symlinked directory.
/// The test approach is to build a project twice from the non-symlinked directory and a symlinked
/// directory and then compare the build-dir paths.
#[cargo_test]
fn template_workspace_path_hash_should_handle_symlink() {
    #[cfg(unix)]
    use std::os::unix::fs::symlink;
    #[cfg(windows)]
    use std::os::windows::fs::symlink_dir as symlink;

    let p = project()
        .file("src/lib.rs", "")
        .file(
            "Cargo.toml",
            r#"
             [package]
             name = "foo"
             version = "1.0.0"
             authors = []
             edition = "2015"
             "#,
        )
        .file(
            ".cargo/config.toml",
            r#"
             [build]
             build-dir = "foo/{workspace-path-hash}/build-dir"
             "#,
        )
        .build();

    // Build from the non-symlinked directory
    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking check")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .run();

    // Parse and verify the hash dir created from the non-symlinked dir
    let foo_dir = p.root().join("foo");
    assert_exists(&foo_dir);
    let original_hash_dir = parse_workspace_manifest_path_hash(&foo_dir);

    original_hash_dir.assert_build_dir_layout(str![[r#"
[ROOT]/foo/foo/[HASH]/build-dir/.rustc_info.json
[ROOT]/foo/foo/[HASH]/build-dir/CACHEDIR.TAG
[ROOT]/foo/foo/[HASH]/build-dir/debug/.cargo-build-lock
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/fingerprint/dep-lib-foo
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/fingerprint/lib-foo
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/fingerprint/lib-foo.json
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/out/foo-[HASH].d
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/out/libfoo-[HASH].rmeta
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/.lock

"#]]);

    p.root().join("target").assert_build_dir_layout(str![[r#"
[ROOT]/foo/target/CACHEDIR.TAG
[ROOT]/foo/target/debug/.cargo-lock

"#]]);

    // Create a symlink of the project root.
    let mut symlinked_dir = p.root().clone();
    symlinked_dir.pop();
    symlinked_dir = symlinked_dir.join("symlink-dir");
    symlink(p.root(), &symlinked_dir).unwrap();

    // Remove the foo dir (which contains the build-dir) before we rebuild from a symlinked dir.
    foo_dir.rm_rf();

    // Run cargo from the symlinked dir
    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking check")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .enable_mac_dsym()
        .cwd(&symlinked_dir)
        .run();

    // Parse and verify the hash created from the symlinked dir
    assert_exists(&foo_dir);
    let symlink_hash_dir = parse_workspace_manifest_path_hash(&foo_dir);

    symlink_hash_dir.assert_build_dir_layout(str![[r#"
[ROOT]/foo/foo/[HASH]/build-dir/.rustc_info.json
[ROOT]/foo/foo/[HASH]/build-dir/CACHEDIR.TAG
[ROOT]/foo/foo/[HASH]/build-dir/debug/.cargo-build-lock
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/fingerprint/dep-lib-foo
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/fingerprint/lib-foo
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/fingerprint/lib-foo.json
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/out/foo-[HASH].d
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/out/libfoo-[HASH].rmeta
[ROOT]/foo/foo/[HASH]/build-dir/debug/build/foo/[HASH]/.lock

"#]]);

    p.root().join("target").assert_build_dir_layout(str![[r#"
[ROOT]/foo/target/CACHEDIR.TAG
[ROOT]/foo/target/debug/.cargo-lock

"#]]);

    // Verify the hash dir created from the symlinked and non-symlinked dirs are the same.
    assert_eq!(original_hash_dir, symlink_hash_dir);
}

#[cargo_test]
fn template_should_handle_reject_unmatched_brackets() {
    let p = project()
        .file("src/lib.rs", "")
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            build-dir = "foo/{bar"
            "#,
        )
        .build();

    p.cargo("-Zbuild-dir-new-layout -Zfine-grain-locking build")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] unexpected opening bracket `{` in build.build-dir path `foo/{bar`

"#]])
        .run();

    let p = project()
        .file("src/lib.rs", "")
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            build-dir = "foo/}bar"
            "#,
        )
        .build();

    p.cargo("build")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] unexpected closing bracket `}` in build.build-dir path `foo/}bar`

"#]])
        .run();
}

#[cargo_test]
fn artifact_deps() {
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
                [package]
                name = "foo"
                version = "0.0.0"
                edition = "2015"
                authors = []
                resolver = "2"

                [dependencies]
                bar = { path = "bar/", artifact = ["bin:bar"] }
            "#,
        )
        .file(
            "src/main.rs",
            r#"
            fn main() {
                 println!("CARGO_BIN_DIR_BAR={}", env!("CARGO_BIN_DIR_BAR"));
                 println!("CARGO_BIN_FILE_BAR_bar={}", env!("CARGO_BIN_FILE_BAR_bar"));
            }
            "#,
        )
        .file(
            "bar/Cargo.toml",
            r#"
                [package]
                name = "bar"
                version = "0.1.0"
                edition = "2015"
                authors = []

                [[bin]]
                name = "bar"
            "#,
        )
        .file("bar/src/main.rs", "fn main() {}")
        .build();

    p.cargo("run -Zbuild-dir-new-layout -Z bindeps")
        .masquerade_as_nightly_cargo(&["bindeps", "build-dir-new-layout"])
        .enable_mac_dsym()
        .with_stderr_data(str![[r#"
[LOCKING] 1 package to latest compatible version
[COMPILING] bar v0.1.0 ([ROOT]/foo/bar)
[COMPILING] foo v0.0.0 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[RUNNING] `target-dir/debug/foo[EXE]`

"#]])
        .with_stdout_data(str![[r#"
CARGO_BIN_DIR_BAR=[ROOT]/foo/build-dir/debug/build/bar/[HASH]/artifact/bin
CARGO_BIN_FILE_BAR_bar=[ROOT]/foo/build-dir/debug/build/bar/[HASH]/artifact/bin/bar[..][EXE]

"#]])
        .run();

    p.root().join("build-dir").assert_build_dir_layout(str![[r#"
[ROOT]/foo/build-dir/.rustc_info.json
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/debug/.cargo-build-lock
[ROOT]/foo/build-dir/debug/build/bar/[HASH]/fingerprint/bin-bar
[ROOT]/foo/build-dir/debug/build/bar/[HASH]/fingerprint/bin-bar.json
[ROOT]/foo/build-dir/debug/build/bar/[HASH]/fingerprint/dep-bin-bar
[ROOT]/foo/build-dir/debug/build/bar/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-bin-foo
[ROOT]/foo/build-dir/debug/build/bar/[HASH]/artifact/bin/bar[..][EXE]
[ROOT]/foo/build-dir/debug/build/bar/[HASH]/artifact/bin/bar[..].d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..].d

"#]]);

    p.root()
        .join("target-dir")
        .assert_build_dir_layout(str![[r#"
[ROOT]/foo/target-dir/CACHEDIR.TAG
[ROOT]/foo/target-dir/debug/.cargo-lock
[ROOT]/foo/target-dir/debug/.cargo-artifact-lock
[ROOT]/foo/target-dir/debug/foo[EXE]
[ROOT]/foo/target-dir/debug/foo.d

"#]]);
}

/// __CARGO_DEFAULT_LIB_METADATA is internal but used by rustc bootstrap and Miri
/// Regression test for https://github.com/rust-lang/cargo/issues/16854
#[cargo_test]
fn should_work_with_cargo_default_lib_metadata() {
    let p = project()
        .file("src/main.rs", r#"fn main() { println!("Hello, World!") }"#)
        .file("build.rs", r#"fn main() { }"#)
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            target-dir = "target-dir"
            build-dir = "build-dir"
            "#,
        )
        .build();

    p.cargo("-Zbuild-dir-new-layout build")
        .masquerade_as_nightly_cargo(&["new build-dir layout"])
        .env("__CARGO_DEFAULT_LIB_METADATA", "true")
        .enable_mac_dsym()
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    // NOTE: build_script_build[EXE] does not contain a hash in the filename
    p.root().join("build-dir").assert_build_dir_layout(str![[r#"
[ROOT]/foo/build-dir/.rustc_info.json
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/debug/.cargo-build-lock
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/bin-foo.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-bin-foo
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..][EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/foo[..].d
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/run-build-script-build-script-build
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/run-build-script-build-script-build.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/run/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/run/root-output
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/run/stderr
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/run/stdout
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/build-script-build-script-build
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/build-script-build-script-build.json
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/dep-build-script-build-script-build
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/fingerprint/invoked.timestamp
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/build_script_build[EXE]
[ROOT]/foo/build-dir/debug/build/foo/[HASH]/out/build_script_build.d

"#]]);
}

#[cargo_test]
fn shared_registry_cache_keeps_workspace_artifacts_private() {
    Package::new("shared-registry", "1.0.0")
        .file(
            "build.rs",
            r#"
            fn main() {
                let output = std::path::PathBuf::from(
                    std::env::var_os("OUT_DIR").expect("build script output directory"),
                );
                std::fs::write(
                    output.join("generated.rs"),
                    "pub const VALUE: &str = \"registry\";",
                )
                .expect("write generated registry source");
                println!("cargo:rerun-if-changed=build.rs");
            }
            "#,
        )
        .file(
            "src/lib.rs",
            r#"
            include!(concat!(env!("OUT_DIR"), "/generated.rs"));
            pub fn value() -> &'static str { VALUE }
            "#,
        )
        .publish();
    Package::new("local-dependency", "0.1.0")
        .file(
            "src/lib.rs",
            "pub fn value() -> &'static str { \"published\" }",
        )
        .publish();
    Package::new("registry-parent", "1.0.0")
        .dep("local-dependency", "0.1.0")
        .file(
            "src/lib.rs",
            "pub fn value() -> &'static str { local_dependency::value() }",
        )
        .publish();

    let create_project = |worktree: &str, local_value: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "shared-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                shared-registry = "1.0.0"
                registry-parent = "1.0.0"
                local-dependency = "0.1.0"

                [patch.crates-io]
                local-dependency = { path = "local" }
                "#,
            )
            .file(
                "src/main.rs",
                r#"
                fn main() {
                    println!(
                        "{}:{}:{}",
                        shared_registry::value(),
                        local_dependency::value(),
                        registry_parent::value(),
                    );
                }
                "#,
            )
            .file(
                "local/Cargo.toml",
                r#"
                [package]
                name = "local-dependency"
                version = "0.1.0"
                edition = "2021"
                "#,
            )
            .file(
                "local/src/lib.rs",
                &format!("pub fn value() -> &'static str {{ \"{local_value}\" }}"),
            )
            .build()
    };
    let left = create_project("left-worktree", "left");
    let right = create_project("right-worktree", "right");
    let shared_build_dir = paths::root().join("shared-registry-build-dir");

    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared_build_dir)
        .with_stderr_contains("[COMPILING] shared-registry v1.0.0")
        .with_stderr_contains("[COMPILING] registry-parent v1.0.0")
        .with_stderr_contains("[COMPILING] local-dependency v0.1.0 ([..])")
        .with_stdout_data(str![[r#"
registry:left:left

"#]])
        .run();

    right
        .cargo("run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_UNSTABLE_OHM_SHARED_REGISTRY_CACHE", "true")
        .env("CARGO_BUILD_BUILD_DIR", &shared_build_dir)
        .with_stderr_contains("[COMPILING] registry-parent v1.0.0")
        .with_stderr_contains("[COMPILING] local-dependency v0.1.0 ([..])")
        .with_stderr_does_not_contain("[COMPILING] shared-registry v1.0.0")
        .with_stdout_data(str![[r#"
registry:right:right

"#]])
        .run();

    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared_build_dir)
        .with_stderr_does_not_contain("[COMPILING] shared-registry v1.0.0")
        .with_stderr_does_not_contain("[COMPILING] registry-parent v1.0.0")
        .with_stderr_does_not_contain("[COMPILING] local-dependency v0.1.0 ([..])")
        .with_stdout_data(str![[r#"
registry:left:left

"#]])
        .run();

    let incremental = shared_build_dir.join("debug/incremental");
    assert_eq!(
        std::fs::read_dir(&incremental)
            .expect("read private workspace incremental directories")
            .count(),
        2,
        "each worktree must retain a separate incremental directory",
    );
}

#[cargo_test]
fn shared_registry_cache_rejects_global_compiler_wrappers() {
    Package::new("wrapped-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 19 }")
        .publish();

    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "wrapper-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                wrapped-registry = "1.0.0"
                "#,
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", wrapped_registry::value()); }",
            )
            .build()
    };
    let left = create_project("wrapper-left");
    let right = create_project("wrapper-right");
    let shared_build_dir = paths::root().join("wrapper-shared-build-dir");

    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared_build_dir)
        .with_stderr_contains("[COMPILING] wrapped-registry v1.0.0")
        .with_stdout_data("19\n")
        .run();

    right
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared_build_dir)
        .env("RUSTC_WRAPPER", tools::echo_wrapper())
        .with_stderr_contains("[COMPILING] wrapped-registry v1.0.0")
        .with_stderr_contains("WRAPPER CALLED: rustc --crate-name wrapped_registry[..]")
        .with_stdout_data("19\n")
        .run();

    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared_build_dir)
        .with_stderr_does_not_contain("[COMPILING] wrapped-registry v1.0.0")
        .with_stdout_data("19\n")
        .run();
}

#[cargo_test]
fn shared_registry_cache_keys_build_script_tool_context() {
    Package::new("tool-sensitive-registry", "1.0.0")
        .file(
            "build.rs",
            r#"
            fn main() {
                let output = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
                let rustdoc = std::env::var("RUSTDOC").unwrap();
                std::fs::write(
                    output.join("generated.rs"),
                    format!("pub const TOOL: &str = {rustdoc:?};"),
                )
                .unwrap();
                println!("cargo:rerun-if-changed=build.rs");
            }
            "#,
        )
        .file(
            "src/lib.rs",
            "include!(concat!(env!(\"OUT_DIR\"), \"/generated.rs\"));",
        )
        .publish();

    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "tool-context-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                tool-sensitive-registry = "1.0.0"
                "#,
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", tool_sensitive_registry::TOOL); }",
            )
            .build()
    };
    let left = create_project("tool-context-left");
    let right = create_project("tool-context-right");
    let shared_build_dir = paths::root().join("tool-context-shared-build-dir");

    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared_build_dir)
        .env("RUSTDOC", "left-rustdoc")
        .with_stdout_data("left-rustdoc\n")
        .run();

    right
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared_build_dir)
        .env("RUSTDOC", "right-rustdoc")
        .with_stderr_contains("[COMPILING] tool-sensitive-registry v1.0.0")
        .with_stdout_data("right-rustdoc\n")
        .run();

    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared_build_dir)
        .env("RUSTDOC", "left-rustdoc")
        .with_stderr_does_not_contain("[COMPILING] tool-sensitive-registry v1.0.0")
        .with_stdout_data("left-rustdoc\n")
        .run();
}

#[cargo_test(nightly, reason = "rustdoc mergeable crate info is unstable")]
fn shared_registry_cache_keeps_rustdoc_merge_state_private() {
    let create_project = |worktree: &str, package: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                &format!(
                    r#"
                    [package]
                    name = "{package}"
                    version = "0.1.0"
                    edition = "2021"
                    "#,
                ),
            )
            .file("src/lib.rs", "pub fn documented() {}")
            .build()
    };
    let left = create_project("rustdoc-left", "left-doc");
    let right = create_project("rustdoc-right", "right-doc");
    let shared_build_dir = paths::root().join("rustdoc-shared-build-dir");

    left.cargo("-Zohm-shared-registry-cache -Zrustdoc-mergeable-info doc --no-deps")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache", "rustdoc-mergeable-info"])
        .env("CARGO_BUILD_BUILD_DIR", &shared_build_dir)
        .run();
    right
        .cargo("-Zohm-shared-registry-cache -Zrustdoc-mergeable-info doc --no-deps")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache", "rustdoc-mergeable-info"])
        .env("CARGO_BUILD_BUILD_DIR", &shared_build_dir)
        .run();

    assert!(left.root().join("target/doc/left_doc/index.html").is_file());
    assert!(
        right
            .root()
            .join("target/doc/right_doc/index.html")
            .is_file()
    );
    assert!(!right.root().join("target/doc/left_doc/index.html").exists());
    assert_eq!(
        std::fs::read_dir(&shared_build_dir)
            .expect("read shared rustdoc build directory")
            .filter_map(Result::ok)
            .filter(|entry| {
                entry
                    .file_name()
                    .to_string_lossy()
                    .starts_with(".rustdoc_fingerprint-")
            })
            .count(),
        2,
        "each worktree must retain a separate rustdoc merge fingerprint",
    );
}

#[cargo_test]
fn shared_registry_cache_keeps_test_temporary_directories_private() {
    let create_project = |worktree: &str, value: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "temporary-cache-app"
                version = "0.1.0"
                edition = "2021"
                "#,
            )
            .file("src/lib.rs", "")
            .file(
                "tests/private.rs",
                &format!(
                    r#"
                    #[test]
                    fn temporary_directory_is_private() {{
                        let marker = std::path::Path::new(env!("CARGO_TARGET_TMPDIR"))
                            .join("workspace-marker");
                        assert!(!marker.exists(), "another worktree already created this marker");
                        std::fs::write(marker, "{value}").unwrap();
                    }}
                    "#,
                ),
            )
            .build()
    };
    let left = create_project("temporary-left", "left");
    let right = create_project("temporary-right", "right");
    let shared_build_dir = paths::root().join("temporary-shared-build-dir");

    left.cargo("-Zohm-shared-registry-cache test --test private")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared_build_dir)
        .run();
    right
        .cargo("-Zohm-shared-registry-cache test --test private")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared_build_dir)
        .run();

    let mut contents = std::fs::read_dir(shared_build_dir.join("tmp"))
        .expect("read private test temporary directories")
        .filter_map(Result::ok)
        .map(|entry| {
            std::fs::read_to_string(entry.path().join("workspace-marker"))
                .expect("read private workspace marker")
        })
        .collect::<Vec<_>>();
    contents.sort_unstable();
    assert_eq!(contents, ["left", "right"]);
}

#[cargo_test]
fn shared_registry_cache_plain_clean_preserves_other_workspaces_and_registries() {
    Package::new("clean-shared-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 7 }")
        .publish();

    let create_project = |worktree: &str, value: u32| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "shared-clean-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                clean-shared-registry = "1.0.0"

                [profile.alternate]
                inherits = "dev"
                "#,
            )
            .file(
                "src/main.rs",
                &format!(
                    "fn main() {{ println!(\"{{}}:{value}\", clean_shared_registry::value()); }}"
                ),
            )
            .build()
    };
    let left = create_project("clean-worktree-left", 1);
    let right = create_project("clean-worktree-right", 2);
    let shared = paths::root().join("clean-shared-build-directory");
    let target = rustc_host();

    for project in [&left, &right] {
        project
            .cargo("-Zohm-shared-registry-cache build")
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .run();
        project
            .cargo("-Zohm-shared-registry-cache build --target")
            .arg(&target)
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .run();
        project
            .cargo("-Zohm-shared-registry-cache build --profile alternate")
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .run();
    }

    left.cargo("-Zohm-shared-registry-cache clean")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .run();

    assert!(!left.root().join("target").exists());
    assert!(
        right
            .root()
            .join(format!("target/debug/shared-clean-app{EXE_SUFFIX}"))
            .is_file()
    );
    assert!(
        right
            .root()
            .join(format!("target/alternate/shared-clean-app{EXE_SUFFIX}"))
            .is_file()
    );
    assert!(shared.join("debug/build/registries").is_dir());
    assert!(shared.join("alternate/build/registries").is_dir());
    assert!(shared.join(&target).join("debug/build/registries").is_dir());
    assert!(
        right
            .root()
            .join(format!(
                "target/{target}/debug/shared-clean-app{EXE_SUFFIX}"
            ))
            .is_file()
    );

    right
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[COMPILING] [..]")
        .with_stdout_data("7:2\n")
        .run();
    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] shared-clean-app v0.1.0 ([..])")
        .with_stderr_does_not_contain("[COMPILING] clean-shared-registry v1.0.0")
        .with_stdout_data("7:1\n")
        .run();
}

#[cargo_test]
fn shared_registry_cache_package_clean_only_removes_current_workspace() {
    Package::new("package-clean-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 11 }")
        .publish();

    let create_project = |worktree: &str, value: u32| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "package-clean-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                package-clean-registry = "1.0.0"
                package-clean-local = { path = "local" }
                "#,
            )
            .file(
                "src/main.rs",
                r#"
                fn main() {
                    println!(
                        "{}:{}",
                        package_clean_registry::value(),
                        package_clean_local::value()
                    );
                }
                "#,
            )
            .file(
                "local/Cargo.toml",
                r#"
                [package]
                name = "package-clean-local"
                version = "0.1.0"
                edition = "2021"
                "#,
            )
            .file(
                "local/src/lib.rs",
                &format!("pub fn value() -> u32 {{ {value} }}"),
            )
            .build()
    };
    let left = create_project("package-clean-left", 1);
    let right = create_project("package-clean-right", 2);
    let shared = paths::root().join("package-clean-shared-build-directory");

    for project in [&left, &right] {
        project
            .cargo("-Zohm-shared-registry-cache run")
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .run();
    }

    left.cargo("-Zohm-shared-registry-cache clean -p package-clean-local")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .run();

    right
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[COMPILING] [..]")
        .with_stdout_data("11:2\n")
        .run();
    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] package-clean-local v0.1.0 ([..])")
        .with_stderr_does_not_contain("[COMPILING] package-clean-registry v1.0.0")
        .with_stdout_data("11:1\n")
        .run();

    left.cargo("-Zohm-shared-registry-cache clean -p package-clean-registry")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains(
            "[WARNING] preserving shared registry artifacts for `package-clean-registry` [..]",
        )
        .run();
    right
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[COMPILING] [..]")
        .with_stdout_data("11:2\n")
        .run();
}

#[cargo_test]
fn shared_registry_cache_keys_inherited_rustc_bootstrap() {
    Package::new("bootstrap-sensitive-registry", "1.0.0")
        .file(
            "src/lib.rs",
            "#![feature(never_type)]\npub fn value() -> u32 { 23 }\n",
        )
        .publish();

    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "bootstrap-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                bootstrap-sensitive-registry = "1.0.0"
                "#,
            )
            .file("src/lib.rs", "pub use bootstrap_sensitive_registry::value;")
            .build()
    };
    let left = create_project("bootstrap-worktree-left");
    let right = create_project("bootstrap-worktree-right");
    let shared = paths::root().join("bootstrap-shared-build-directory");

    left.cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("RUSTC_BOOTSTRAP", "1")
        .run();

    right
        .cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("RUSTC_BOOTSTRAP", "-1")
        .with_status(101)
        .with_stderr_contains(
            "error[E0554]: `#![feature]` may not be used on the [..] release channel",
        )
        .run();

    left.cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("RUSTC_BOOTSTRAP", "1")
        .with_stderr_does_not_contain("[COMPILING] [..]")
        .run();
}

#[cfg(unix)]
#[cargo_test]
fn shared_registry_cache_keys_effective_host_runner() {
    Package::new("runner-sensitive-registry", "1.0.0")
        .file(
            "build.rs",
            r#"
            fn main() {
                let output = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
                let runner = std::env::var("OHM_SHARED_HOST_RUNNER").unwrap();
                std::fs::write(
                    output.join("generated.rs"),
                    format!("pub const RUNNER: &str = {runner:?};"),
                )
                .unwrap();
                println!("cargo:rerun-if-changed=build.rs");
            }
            "#,
        )
        .file(
            "src/lib.rs",
            "include!(concat!(env!(\"OUT_DIR\"), \"/generated.rs\"));",
        )
        .publish();

    let create_project = |worktree: &str, runner: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "runner-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                runner-sensitive-registry = "1.0.0"
                "#,
            )
            .file(
                ".cargo/config.toml",
                &format!(
                    r#"
                    target-applies-to-host = false

                    [host]
                    runner = ["sh", "-c", "OHM_SHARED_HOST_RUNNER={runner} \"$@\"", "ohm-host-runner"]
                    "#,
                ),
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", runner_sensitive_registry::RUNNER); }",
            )
            .build()
    };
    let left = create_project("host-runner-left", "left");
    let right = create_project("host-runner-right", "right");
    let shared = paths::root().join("host-runner-shared-build-directory");
    let flags = [
        "ohm-shared-registry-cache",
        "target-applies-to-host",
        "host-config",
    ];
    let command = "-Zohm-shared-registry-cache -Ztarget-applies-to-host -Zhost-config run";

    left.cargo(command)
        .masquerade_as_nightly_cargo(&flags)
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stdout_data("left\n")
        .run();
    right
        .cargo(command)
        .masquerade_as_nightly_cargo(&flags)
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] runner-sensitive-registry v1.0.0")
        .with_stdout_data("right\n")
        .run();
    left.cargo(command)
        .masquerade_as_nightly_cargo(&flags)
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[COMPILING] runner-sensitive-registry v1.0.0")
        .with_stdout_data("left\n")
        .run();
}

#[cargo_test]
fn shared_registry_cache_clean_rejects_overlapping_target_and_build_directories() {
    let project = project_in("unsafe-shared-clean")
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "unsafe-shared-clean"
            version = "0.1.0"
            edition = "2021"
            "#,
        )
        .file("src/lib.rs", "pub fn value() {}")
        .build();

    project
        .cargo("-Zohm-shared-registry-cache clean")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .with_status(101)
        .with_stderr_contains(
            "[ERROR] cannot safely clean overlapping target and shared registry [..]",
        )
        .run();
}

fn parse_workspace_manifest_path_hash(hash_dir: &PathBuf) -> PathBuf {
    // Since the hash will change between test runs simply find the first directories and assume
    // that is the hash dir. The format is a 2 char directory followed by the remaining hash in the
    // inner directory (ie. `34/f9d02eb8411c05`)
    let mut dirs = std::fs::read_dir(hash_dir).unwrap().into_iter();
    let outer_hash_dir = dirs.next().unwrap().unwrap();
    // Validate there are no other directories in `hash_dir`
    assert!(
        dirs.next().is_none(),
        "Found multiple dir entries in {hash_dir:?}"
    );
    // Validate the outer hash dir hash is a directory and has the correct hash length
    assert!(
        outer_hash_dir.path().is_dir(),
        "{outer_hash_dir:?} was not a directory"
    );
    assert_eq!(
        outer_hash_dir.path().file_name().unwrap().len(),
        2,
        "Path {:?} should have been 2 chars",
        outer_hash_dir.path().file_name()
    );

    let mut dirs = std::fs::read_dir(outer_hash_dir.path())
        .unwrap()
        .into_iter();
    let inner_hash_dir = dirs.next().unwrap().unwrap();
    // Validate there are no other directories in first hash dir
    assert!(
        dirs.next().is_none(),
        "Found multiple dir entries in {outer_hash_dir:?}"
    );
    // Validate the outer hash dir hash is a directory and has the correct hash length
    assert!(
        inner_hash_dir.path().is_dir(),
        "{inner_hash_dir:?} was not a directory"
    );
    assert_eq!(
        inner_hash_dir.path().file_name().unwrap().len(),
        14,
        "Path {:?} should have been 2 chars",
        inner_hash_dir.path().file_name()
    );
    return inner_hash_dir.path();
}

#[track_caller]
fn assert_exists(path: &PathBuf) {
    assert!(
        path.exists(),
        "Expected `{}` to exist but was not found.",
        path.display()
    );
}

#[track_caller]
fn assert_not_exists(path: &PathBuf) {
    assert!(
        !path.exists(),
        "Expected `{}` to NOT exist but was found.",
        path.display()
    );
}

#[track_caller]
fn assert_exists_patterns_with_base_dir(base: &PathBuf, patterns: &[&str]) {
    let root = base.to_str().unwrap();
    let p: Vec<_> = patterns.iter().map(|p| format!("{root}/{p}")).collect();
    let p: Vec<&str> = p.iter().map(|v| v.as_str()).collect();
    assert_exists_patterns(&p);
}

#[track_caller]
fn assert_exists_patterns(patterns: &[&str]) {
    for p in patterns {
        assert_exists_pattern(p);
    }
}

#[track_caller]
fn assert_exists_pattern(pattern: &str) {
    use glob::glob;

    let mut z = glob(pattern).unwrap();

    assert!(
        z.next().is_some(),
        "Expected `{pattern}` to match existing file but was not found.",
    )
}
