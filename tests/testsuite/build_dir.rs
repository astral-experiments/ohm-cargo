//! Tests for `build.build-dir` config property.
//!
//! The testing strategy for build-dir functionality is primarily checking if directories / files
//! are in the expected locations.
//! The rational is that other tests will verify each individual feature, while the tests in this
//! file verify the files saved to disk are in the correct locations according to the `build-dir`
//! configuration.
//!
//! Tests check if directories match some "layout" by using [`CargoPathExt::assert_build_dir_layout`]
//!
//! Note: This file is mirrored by build_dir_fine_grain_locking.rs and build_dir_legacy.rs which contain
//! the same tests with `enabled and the old build-dir layout respectively.
//! New tests should be added to all when applicable.

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Output, Stdio};
use std::sync::mpsc;
use std::thread;

use crate::prelude::*;
use crate::utils::tools;
use cargo::util::short_hash;
use cargo_test_support::registry::{Package, RegistryBuilder};
use cargo_test_support::{
    execs, is_coarse_mtime, paths, prelude::*, project, project_in, rustc_host, sleep_ms,
    slow_cpu_multiplier, str, target_spec_json,
};
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

    p.cargo("-Zbuild-dir-new-layout build")
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

#[cfg(unix)]
#[cargo_test]
fn fine_grain_locking_scales_beyond_the_soft_descriptor_limit() {
    let mut manifest = String::from(
        "[package]\nname = \"descriptor-budget\"\nversion = \"0.1.0\"\nedition = \"2021\"\n\n[dependencies]\n",
    );
    let mut project = project().file("src/lib.rs", "pub fn value() -> u32 { 1 }");

    for index in 0..72 {
        let dependency = format!("dependency-{index}");
        manifest.push_str(&format!(
            "{dependency} = {{ path = \"crates/{dependency}\" }}\n"
        ));
        project = project
            .file(
                &format!("crates/{dependency}/Cargo.toml"),
                &format!(
                    "[package]\nname = \"{dependency}\"\nversion = \"0.1.0\"\nedition = \"2021\"\n",
                ),
            )
            .file(
                &format!("crates/{dependency}/src/lib.rs"),
                "pub fn value() -> u32 { 1 }",
            );
    }
    let project = project.file("Cargo.toml", &manifest).build();

    project
        .process("sh")
        .arg("-c")
        .arg("ulimit -Sn 64 && exec \"$CARGO_TEST_BINARY\" -Zbuild-dir-new-layout -Zfine-grain-locking build -j 1")
        .env("CARGO_TEST_BINARY", crate::utils::cargo_exe())
        .masquerade_as_nightly_cargo(&["build-dir-new-layout", "fine-grain-locking"])
        .run();
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

    p.cargo("-Zbuild-dir-new-layout build --release")
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

        p.cargo("-Zbuild-dir-new-layout build")
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

    p.cargo("-Zbuild-dir-new-layout build")
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

"#]]);
}

#[cargo_test]
fn should_respect_env_var() {
    let p = project()
        .file("src/main.rs", r#"fn main() { println!("Hello, World!") }"#)
        .build();

    p.cargo("-Zbuild-dir-new-layout build")
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

    p.cargo("-Zbuild-dir-new-layout test")
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

    p.cargo("-Zbuild-dir-new-layout build --examples")
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

    p.cargo("-Zbuild-dir-new-layout build --bench=foo")
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

    p.cargo("-Zbuild-dir-new-layout doc")
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

#[cargo_test(nightly, reason = "--output-format is unstable")]
fn cargo_doc_json_should_output_to_target_dir() {
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

    p.cargo("-Zbuild-dir-new-layout -Zunstable-options doc --no-deps --output-format json")
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

    p.cargo("-Zbuild-dir-new-layout package")
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

    p.cargo("-Zbuild-dir-new-layout publish")
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

    p.cargo("-Zbuild-dir-new-layout build")
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

    p.cargo("-Zbuild-dir-new-layout clean")
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

    p.cargo("-Zbuild-dir-new-layout build")
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
[ROOT]/foo/build-dir/debug/build/bar/[HASH]/fingerprint/ohm-message-provenance-lib-bar

"#]]);

    p.cargo("-Zbuild-dir-new-layout clean -p bar")
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

    p.cargo("-Zbuild-dir-new-layout build --timings")
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

    p.cargo("-Zbuild-dir-new-layout build")
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

    p.cargo("-Zbuild-dir-new-layout build")
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

    p.cargo("-Zbuild-dir-new-layout build")
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

    p.cargo("-Zbuild-dir-new-layout build")
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

    p.cargo("-Zbuild-dir-new-layout build")
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

    p.cargo("-Zbuild-dir-new-layout build")
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
    p.cargo("-Zbuild-dir-new-layout check")
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
    p.cargo("-Zbuild-dir-new-layout check")
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

    p.cargo("-Zbuild-dir-new-layout build")
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
[LOCKING] 1 package to highest compatible version
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

/// Verify multiple dylibs are properly added to the search path.
/// Regression test for https://github.com/rust-lang/rust/issues/158526
#[cargo_test]
fn dylib_deps_output_overwrite() {
    let p = project()
        .file(
            ".cargo/config.toml",
            r#"
            [build]
            target-dir = "target-dir"
            build-dir = "build-dir"
            rustflags = ["-C", "prefer-dynamic"]
            "#,
        )
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "main"
                version = "0.0.0"
                edition = "2021"
                authors = []
                resolver = "2"

                [dependencies]
                bar = { path = "bar" }
                baz = { path = "baz" }
            "#,
        )
        .file(
            "src/main.rs",
            r#"
                use bar::bar_value;
                use baz::baz_value;

                fn main() {
                    println!("sum = {}", bar_value() + baz_value());
                }
            "#,
        )
        .file(
            "tests/use_both_dylibs.rs",
            r#"
                use bar::bar_value;
                use baz::baz_value;

                #[test]
                fn uses_both_dylibs() {
                    assert_eq!(bar_value() + baz_value(), 300);
                }
            "#,
        )
        .file(
            "bar/Cargo.toml",
            r#"
                [package]
                name = "bar"
                version = "0.1.0"
                edition = "2021"
                authors = []

                [lib]
                crate-type = ["dylib"]
            "#,
        )
        .file("bar/src/lib.rs", r#"pub fn bar_value() -> i32 { 100 }"#)
        .file(
            "baz/Cargo.toml",
            r#"
                [package]
                name = "baz"
                version = "0.1.0"
                edition = "2021"
                authors = []

                [lib]
                crate-type = ["dylib"]
            "#,
        )
        .file("baz/src/lib.rs", r#"pub fn baz_value() -> i32 { 200 }"#)
        .build();

    p.cargo("test -Zbuild-dir-new-layout")
        .masquerade_as_nightly_cargo(&["build-dir-new-layout"])
        .env("__CARGO_DEFAULT_LIB_METADATA", "1")
        .enable_mac_dsym()
        .with_stderr_data(
            str![[r#"
[LOCKING] 2 packages to highest compatible versions
[COMPILING] bar v0.1.0 ([ROOT]/foo/bar)
[COMPILING] baz v0.1.0 ([ROOT]/foo/baz)
[COMPILING] main v0.0.0 ([ROOT]/foo)
[FINISHED] `test` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[RUNNING] unittests src/main.rs (build-dir/debug/build/main/[HASH]/out/[..])
[RUNNING] tests/use_both_dylibs.rs (build-dir/debug/build/main/[HASH]/out/[..])

"#]]
            .unordered(),
        )
        .run();

    // Check that the dylibs are uplifted
    assert_exists_patterns_with_base_dir(
        &p.root().join("target-dir/debug"),
        &[
            &format!("{DLL_PREFIX}bar{DLL_SUFFIX}"),
            &format!("{DLL_PREFIX}baz{DLL_SUFFIX}"),
        ],
    );

    // Check the correctly-named (hashed) dylibs exist in per-unit out/ dirs.
    assert_exists_pattern(
        &p.root()
            .join(format!(
                "build-dir/debug/build/bar/*/out/{DLL_PREFIX}bar-*{DLL_SUFFIX}"
            ))
            .to_string_lossy(),
    );
    assert_exists_pattern(
        &p.root()
            .join(format!(
                "build-dir/debug/build/baz/*/out/{DLL_PREFIX}baz-*{DLL_SUFFIX}"
            ))
            .to_string_lossy(),
    );
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
fn new_layout_opt_out_nightly() {
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

    p.cargo("build")
        .env("__CARGO_TEMPORARY_BUILD_DIR_NEW_LAYOUT_OPT_OUT", "1")
        .masquerade_as_nightly_cargo(&["new build-dir layout enabled by default on nightly"])
        .enable_mac_dsym()
        .run();

    assert_not_exists(&p.root().join("target"));

    p.root().join("build-dir").assert_build_dir_layout(str![[r#"
[ROOT]/foo/build-dir/.rustc_info.json
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/debug/.cargo-build-lock
[ROOT]/foo/build-dir/debug/.fingerprint/foo-[HASH]/bin-foo
[ROOT]/foo/build-dir/debug/.fingerprint/foo-[HASH]/bin-foo.json
[ROOT]/foo/build-dir/debug/.fingerprint/foo-[HASH]/dep-bin-foo
[ROOT]/foo/build-dir/debug/.fingerprint/foo-[HASH]/invoked.timestamp
[ROOT]/foo/build-dir/debug/deps/foo[..][EXE]
[ROOT]/foo/build-dir/debug/deps/foo[..].d

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
fn new_layout_opt_out_stable() {
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

    p.cargo("build")
        .env("__CARGO_TEMPORARY_BUILD_DIR_NEW_LAYOUT_OPT_OUT", "1")
        .enable_mac_dsym()
        .run();

    assert_not_exists(&p.root().join("target"));

    p.root().join("build-dir").assert_build_dir_layout(str![[r#"
[ROOT]/foo/build-dir/.rustc_info.json
[ROOT]/foo/build-dir/CACHEDIR.TAG
[ROOT]/foo/build-dir/debug/.cargo-build-lock
[ROOT]/foo/build-dir/debug/.fingerprint/foo-[HASH]/bin-foo
[ROOT]/foo/build-dir/debug/.fingerprint/foo-[HASH]/bin-foo.json
[ROOT]/foo/build-dir/debug/.fingerprint/foo-[HASH]/dep-bin-foo
[ROOT]/foo/build-dir/debug/.fingerprint/foo-[HASH]/invoked.timestamp
[ROOT]/foo/build-dir/debug/deps/foo[..][EXE]
[ROOT]/foo/build-dir/debug/deps/foo[..].d

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

fn selected_compiler_supports_ohm_defaults() -> bool {
    static SUPPORTED: std::sync::OnceLock<bool> = std::sync::OnceLock::new();

    *SUPPORTED.get_or_init(|| {
        cargo_test_support::process("rustc")
            .arg("-Zpublic-api-hash")
            .arg("-Zcache-proc-macros")
            .arg("--print=sysroot")
            .exec_with_output()
            .is_ok()
    })
}

pub(super) fn shared_registry_cargo(
    project: &cargo_test_support::Project,
    command: &str,
) -> cargo_test_support::Execs {
    let mut cargo = project.cargo(command);

    #[cfg(unix)]
    if !selected_compiler_supports_ohm_defaults() {
        let path = std::env::join_paths([
            std::path::PathBuf::from(paths::sysroot()).join("bin"),
            std::path::PathBuf::from("/usr/bin"),
            std::path::PathBuf::from("/bin"),
        ])
        .expect("construct trusted stock-toolchain executable search path");
        cargo.env("PATH", path);
    }

    cargo
}

trait SharedRegistryProjectExt {
    fn shared_registry_cargo(&self, command: &str) -> cargo_test_support::Execs;
}

impl SharedRegistryProjectExt for cargo_test_support::Project {
    fn shared_registry_cargo(&self, command: &str) -> cargo_test_support::Execs {
        shared_registry_cargo(self, command)
    }
}

#[cargo_test]
fn shared_registry_cache_coalesces_concurrent_builds() {
    concurrent_shared_registry_misses("build", "env!(\"CARGO_PKG_VERSION\")", 1);
}

#[cargo_test]
fn shared_registry_cache_coalesces_concurrent_checks() {
    concurrent_shared_registry_misses("check", "env!(\"CARGO_PKG_VERSION\")", 1);
}

#[cargo_test]
fn shared_registry_cache_concurrent_misses_preserve_forced_rebuilds() {
    concurrent_shared_registry_misses(
        "fix --allow-no-vcs -p coalesced-registry --lib",
        "env!(\"CARGO_PKG_VERSION\")",
        2,
    );
}

#[cargo_test]
fn shared_registry_cache_concurrent_misses_preserve_environment_inputs() {
    concurrent_shared_registry_misses("build", "env!(\"OHM_COALESCING_INPUT\")", 2);
}

#[cargo_test]
fn shared_registry_cache_failed_producer_releases_waiters() {
    concurrent_shared_registry_misses_with_interruption(
        "check",
        "compile_error!(\"shared registry producer failure\")",
        2,
        SharedRegistryInterruption::CompilationFailure,
    );
}

#[cargo_test]
fn shared_registry_cache_cancelled_waiter_does_not_block_recovery() {
    concurrent_shared_registry_misses_with_interruption(
        "build",
        "env!(\"CARGO_PKG_VERSION\")",
        1,
        SharedRegistryInterruption::CancelledWaiter,
    );
}

#[derive(Clone, Copy, PartialEq)]
enum SharedRegistryInterruption {
    None,
    CompilationFailure,
    CancelledWaiter,
}

fn concurrent_shared_registry_misses(command: &str, value: &str, expected_compilations: usize) {
    concurrent_shared_registry_misses_with_interruption(
        command,
        value,
        expected_compilations,
        SharedRegistryInterruption::None,
    );
}

/// Hold the unit lock until both invocations reach compilation or report a lock wait.
/// Accept unit and profile lock waits, including lease reservation before scheduling.
fn concurrent_shared_registry_misses_with_interruption(
    command: &str,
    value: &str,
    expected_compilations: usize,
    interruption: SharedRegistryInterruption,
) {
    Package::new("coalesced-registry", "1.0.0")
        .file(
            "src/lib.rs",
            &format!(
                r#"
                #[deprecated(note = "coalesced registry warning")]
                fn old() {{}}

                pub fn value() -> &'static str {{
                    old();
                    {value}
                }}
                "#,
            ),
        )
        .publish();

    let projects = ["coalescing-left", "coalescing-right"].map(|directory| {
        project_in(directory)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "coalesced-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                coalesced-registry = "1.0.0"
                "#,
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", coalesced_registry::value()); }",
            )
            .build()
    });
    let shared = paths::root().join("coalescing-shared-build-directory");
    let command = format!("-Zohm-shared-registry-cache {command} -vv --message-format=json");
    let cargo = |project: &cargo_test_support::Project, input: &str| {
        let mut cargo = project.shared_registry_cargo(&command);
        cargo
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .env("OHM_COALESCING_INPUT", input);
        cargo
    };

    // Discover the unit's lock without introducing a rustc wrapper, which would disable
    // authenticated registry sharing. Retain the lock inode while making the unit stale.
    let expected_status = if interruption == SharedRegistryInterruption::CompilationFailure {
        101
    } else {
        0
    };
    let producer_failure = r#"[..]"message":"shared registry producer failure"[..]"#;
    let mut discovery = cargo(&projects[0], "left");
    discovery.with_status(expected_status);
    if interruption == SharedRegistryInterruption::CompilationFailure {
        discovery.with_stdout_contains(producer_failure);
    }
    discovery.run();
    let unit_lock = walkdir::WalkDir::new(shared.join("debug/build/registries"))
        .into_iter()
        .map(Result::unwrap)
        .find(|entry| entry.file_name() == ".lock")
        .expect("the shared registry unit should have a lock")
        .into_path();
    let unit = unit_lock.parent().unwrap();
    let fingerprint = unit.join("fingerprint/lib-coalesced_registry");
    std::fs::remove_dir_all(unit.join("out")).unwrap();
    if command.contains(" check ") && fingerprint.exists() {
        // Cover a completely missing fingerprint as well as an existing stale fingerprint.
        std::fs::remove_file(&fingerprint).unwrap();
    }
    let original_fingerprint = std::fs::read(&fingerprint).ok();
    let lock = std::fs::File::open(&unit_lock).unwrap();
    lock.lock_shared().unwrap();

    let (ready, queued) = mpsc::channel();
    let mut children = Vec::new();
    for (index, (project, input)) in projects.iter().zip(["left", "right"]).enumerate() {
        children.push(spawn_shared_registry_cargo(
            cargo(project, input).build_command(),
            index,
            &["coalesced-registry"],
            ready.clone(),
        ));
    }
    wait_for_shared_registry_barriers(&queued, &mut children);
    let queued_fingerprint = std::fs::read(&fingerprint).ok();
    if interruption == SharedRegistryInterruption::CancelledWaiter {
        // The held unit lock prevents either invocation from starting a compiler.
        let mut child = children.pop().unwrap();
        kill_shared_registry_cargo(&mut child.process);
        assert!(!child.process.wait().unwrap().success());
        child.stdout.join().unwrap();
        child.stderr.join().unwrap();
    }
    drop(lock);

    let surviving_children = children.len();
    let mut compilations = 0;
    let mut fresh_artifacts = 0;
    for output in finish_shared_registry_cargos(children) {
        let mut expected = execs();
        expected.with_status(expected_status);
        if interruption == SharedRegistryInterruption::CompilationFailure {
            expected.with_stdout_contains(producer_failure);
        }
        expected.run_output(&output);
        compilations += String::from_utf8_lossy(&output.stderr)
            .lines()
            .filter(|line| {
                line.contains("Running") && line.contains("--crate-name coalesced_registry")
            })
            .count();
        let messages = String::from_utf8_lossy(&output.stdout)
            .lines()
            .map(|line| serde_json::from_str::<serde_json::Value>(line).unwrap())
            .collect::<Vec<_>>();
        let expected_diagnostic = if interruption == SharedRegistryInterruption::CompilationFailure
        {
            "shared registry producer failure"
        } else {
            "coalesced registry warning"
        };
        assert!(messages.iter().any(|message| {
            message["reason"] == "compiler-message"
                && message["message"]["message"]
                    .as_str()
                    .is_some_and(|message| message.contains(expected_diagnostic))
        }));
        fresh_artifacts += messages
            .iter()
            .filter(|message| {
                message["reason"] == "compiler-artifact"
                    && message["target"]["name"] == "coalesced_registry"
                    && message["fresh"] == true
            })
            .count();
    }
    assert_eq!(queued_fingerprint, original_fingerprint);
    assert_eq!(compilations, expected_compilations);
    assert_eq!(fresh_artifacts, surviving_children - expected_compilations);

    if interruption == SharedRegistryInterruption::CompilationFailure {
        assert!(std::fs::read(&fingerprint).unwrap_or_default().is_empty());
        cargo(&projects[0], "left")
            .with_status(101)
            .with_stdout_contains(producer_failure)
            .with_stderr_contains("[RUNNING] `[..]--crate-name coalesced_registry[..]`")
            .run();
    }
    if interruption == SharedRegistryInterruption::CancelledWaiter {
        cargo(&projects[1], "right")
            .with_stderr_does_not_contain("[RUNNING] `[..]--crate-name coalesced_registry[..]`")
            .run();
    }

    if command.contains(" build ") && interruption != SharedRegistryInterruption::CompilationFailure
    {
        for (project, input) in projects.iter().zip(["left", "right"]) {
            let expected = if value.contains("OHM_COALESCING_INPUT") {
                input
            } else {
                "1.0.0"
            };
            project
                .process(project.bin("coalesced-app"))
                .with_stdout_data(format!("{expected}\n"))
                .run();
        }
    }
}

struct SharedRegistryChild {
    process: Child,
    stdout: thread::JoinHandle<Vec<u8>>,
    stderr: thread::JoinHandle<Vec<u8>>,
}

fn spawn_shared_registry_cargo(
    mut command: Command,
    index: usize,
    packages: &[&str],
    ready: mpsc::Sender<usize>,
) -> SharedRegistryChild {
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0);
    }
    let mut child = command
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let mut stdout = child.stdout.take().unwrap();
    let stdout = thread::spawn(move || {
        let mut output = Vec::new();
        stdout.read_to_end(&mut output).unwrap();
        output
    });
    let stderr = child.stderr.take().unwrap();
    let packages = packages
        .iter()
        .map(|package| {
            (
                format!("{package} v1.0.0"),
                format!("Blocking waiting for file lock on {package} ("),
            )
        })
        .collect::<Vec<_>>();
    let reader = thread::spawn(move || {
        let mut output = String::new();
        for line in BufReader::new(stderr).lines() {
            let line = line.unwrap();
            if packages.iter().any(|(package, lock)| {
                (line.contains(package)
                    && (line.contains("Compiling") || line.contains("Checking")))
                    || line.contains(lock)
            }) || line.contains("Blocking waiting for file lock on build directory")
            {
                let _ = ready.send(index);
            }
            output.push_str(&line);
            output.push('\n');
        }
        output.into_bytes()
    });
    SharedRegistryChild {
        process: child,
        stdout,
        stderr: reader,
    }
}

/// The child must not have been reaped: its PID keeps the owned group ID reserved.
fn kill_shared_registry_cargo(child: &mut Child) {
    #[cfg(unix)]
    {
        // SAFETY: Each child starts its own process group. Kill only that owned group,
        // including compilers that may still hold inherited locks after Cargo exits.
        unsafe { libc::kill(-(child.id() as i32), libc::SIGKILL) };
    }
    let _ = child.kill();
    let _ = child.wait();
}

fn wait_for_shared_registry_barriers(
    queued: &mpsc::Receiver<usize>,
    children: &mut [SharedRegistryChild],
) {
    let mut arrived = vec![false; children.len()];
    let deadline = std::time::Instant::now() + slow_cpu_multiplier(30);
    while !arrived.iter().all(|arrived| *arrived) {
        let remaining = deadline.saturating_duration_since(std::time::Instant::now());
        match queued.recv_timeout(remaining) {
            Ok(index) => arrived[index] = true,
            Err(error) => {
                for child in children {
                    kill_shared_registry_cargo(&mut child.process);
                }
                panic!("both Cargo processes must reach a build lock before release: {error}");
            }
        }
    }
}

fn finish_shared_registry_cargos(mut children: Vec<SharedRegistryChild>) -> Vec<Output> {
    let deadline = std::time::Instant::now() + slow_cpu_multiplier(60);
    let mut completed = vec![false; children.len()];
    let timed_out = loop {
        for (child, completed) in children.iter_mut().zip(&mut completed) {
            // Do not reap the group leader while descendants can still own its pipes.
            // Keeping its PID reserved makes timeout cleanup safe after Cargo exits.
            if !*completed && child.stdout.is_finished() && child.stderr.is_finished() {
                *completed = child.process.try_wait().unwrap().is_some();
            }
        }
        if completed.iter().all(|completed| *completed) {
            break false;
        }
        if std::time::Instant::now() >= deadline {
            for (child, completed) in children.iter_mut().zip(&completed) {
                if !*completed {
                    kill_shared_registry_cargo(&mut child.process);
                }
            }
            break true;
        }
        sleep_ms(10);
    };
    let outputs = children
        .into_iter()
        .map(|mut child| Output {
            status: child.process.wait().unwrap(),
            stdout: child.stdout.join().unwrap(),
            stderr: child.stderr.join().unwrap(),
        })
        .collect::<Vec<_>>();
    assert!(
        !timed_out,
        "concurrent Cargo processes deadlocked: {outputs:#?}"
    );
    outputs
}

#[cargo_test]
fn shared_registry_cache_concurrent_independent_leaves_build() {
    concurrent_shared_registry_independent_leaves("build", false);
}

#[cargo_test]
fn shared_registry_cache_concurrent_independent_leaves_check() {
    concurrent_shared_registry_independent_leaves("check", false);
}

#[cargo_test]
fn shared_registry_cache_concurrent_independent_generations() {
    concurrent_shared_registry_independent_leaves("build", true);
}

fn concurrent_shared_registry_independent_leaves(command: &str, different_inputs: bool) {
    for name in ["locking-a", "locking-b"] {
        Package::new(name, "1.0.0")
            .file(
                "src/lib.rs",
                "pub const VALUE: &str = env!(\"OHM_LOCKING_INPUT\");",
            )
            .publish();
    }
    let projects = ["a", "b"].map(|first| {
        project_in(&format!("locking-{first}"))
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "locking-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                locking-a = "1.0.0"
                locking-b = "1.0.0"
                priority = { path = "priority" }
                "#,
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}/{}/{}\", locking_a::VALUE, locking_b::VALUE, priority::VALUE); }",
            )
            .file(
                "priority/Cargo.toml",
                &format!(
                    "[package]\nname = \"priority\"\nversion = \"0.1.0\"\nedition = \"2021\"\n\n[dependencies]\nlocking-{first} = \"1.0.0\"\n",
                ),
            )
            .file(
                "priority/src/lib.rs",
                &format!("pub use locking_{first}::VALUE;"),
            )
            .build()
    });
    let shared = paths::root().join("independent-leaves-shared-build-directory");
    let command = format!("-Zohm-shared-registry-cache {command} -j 1 -vv --message-format=json");
    let cargo = |project: &cargo_test_support::Project, input: &str| {
        let mut cargo = project.shared_registry_cargo(&command);
        cargo
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .env("OHM_LOCKING_INPUT", input);
        cargo
    };
    cargo(&projects[0], "left").run();

    let profile = std::fs::File::open(shared.join("debug/.cargo-build-lock")).unwrap();
    profile.lock_shared().unwrap();
    let unit_paths = walkdir::WalkDir::new(shared.join("debug/build/registries"))
        .into_iter()
        .map(Result::unwrap)
        .filter(|entry| entry.file_name() == ".lock")
        .map(|entry| entry.into_path())
        .collect::<Vec<_>>();
    assert_eq!(unit_paths.len(), 2);
    let unit_locks = unit_paths
        .iter()
        .map(|path| {
            let unit = path.parent().unwrap();
            std::fs::remove_dir_all(unit.join("out")).unwrap();
            let lock = std::fs::File::open(path).unwrap();
            lock.lock_shared().unwrap();
            lock
        })
        .collect::<Vec<_>>();

    // The extra private consumer gives opposite leaves strictly higher scheduling
    // priority. The old protocol lets each Cargo retain one completed leaf and then
    // wait forever for an exclusive lock on the other's leaf. Readiness accepts
    // either unit or profile lock waits, including leases reserved before scheduling.
    let inputs = ["left", if different_inputs { "right" } else { "left" }];
    let (ready, queued) = mpsc::channel();
    let mut children = Vec::new();
    for (index, project) in projects.iter().enumerate() {
        children.push(spawn_shared_registry_cargo(
            cargo(project, inputs[index]).build_command(),
            index,
            &["locking-a", "locking-b"],
            ready.clone(),
        ));
    }
    wait_for_shared_registry_barriers(&queued, &mut children);
    drop(profile);
    drop(unit_locks);

    let outputs = finish_shared_registry_cargos(children);
    for output in &outputs {
        execs().run_output(output);
    }
    for name in ["locking_a", "locking_b"] {
        let compilations = outputs
            .iter()
            .map(|output| {
                String::from_utf8_lossy(&output.stderr)
                    .lines()
                    .filter(|line| {
                        line.contains("Running") && line.contains(&format!("--crate-name {name} "))
                    })
                    .count()
            })
            .sum::<usize>();
        assert_eq!(compilations, if different_inputs { 2 } else { 1 });
    }
    if command.contains(" build ") {
        for (project, input) in projects.iter().zip(inputs) {
            project
                .process(project.bin("locking-app"))
                .with_stdout_data(format!("{input}/{input}/{input}\n"))
                .run();
        }
    }
    if !different_inputs {
        // Private edits must keep working while another invocation pins the shared
        // profile for reading. Taking an exclusive lock unconditionally would hang.
        let reader = std::fs::File::open(shared.join("debug/.cargo-build-lock")).unwrap();
        reader.lock_shared().unwrap();
        if is_coarse_mtime() {
            sleep_ms(1000);
        }
        let mut children = Vec::new();
        for (index, project) in projects.iter().enumerate() {
            project.change_file(
                "src/main.rs",
                "// private workspace edit\nfn main() { println!(\"{}/{}/{}\", locking_a::VALUE, locking_b::VALUE, priority::VALUE); }",
            );
            children.push(spawn_shared_registry_cargo(
                cargo(project, "left").build_command(),
                index,
                &["locking-a"],
                ready.clone(),
            ));
        }
        for output in finish_shared_registry_cargos(children) {
            execs()
                .with_stderr_contains("[RUNNING] `[..]--crate-name locking_app[..]`")
                .with_stderr_does_not_contain("[RUNNING] `[..]--crate-name locking_a [..]`")
                .with_stderr_does_not_contain("[RUNNING] `[..]--crate-name locking_b [..]`")
                .run_output(&output);
        }
        drop(reader);
    }
}

#[cargo_test]
fn shared_registry_cache_unrelated_cold_writer_overlaps_private_compilation() {
    shared_registry_writer_overlaps_private_compilation(false);
}

#[cargo_test]
fn shared_registry_cache_unrelated_stale_writer_overlaps_private_compilation() {
    shared_registry_writer_overlaps_private_compilation(true);
}

fn shared_registry_writer_overlaps_private_compilation(stale: bool) {
    Package::new("overlap-common", "1.0.0")
        .file("src/lib.rs", "pub const VALUE: &str = \"common\";")
        .publish();
    Package::new("overlap-changing", "1.0.0")
        .file(
            "src/lib.rs",
            "pub const VALUE: &str = env!(\"OHM_OVERLAP_INPUT\");",
        )
        .publish();

    let source = |tag: &str, writer: bool| {
        let value = if writer {
            "overlap_changing::VALUE"
        } else {
            "\"private\""
        };
        format!(
            "locking_gate::hold!({tag});\nfn main() {{ println!(\"{{}}/{{}}\", overlap_common::VALUE, {value}); }}",
        )
    };
    for first in [0, 1] {
        let projects = [false, true].map(|writer| {
            let extra = if writer { "overlap-changing = \"1.0.0\"\n" } else { "" };
            project_in(&format!("overlap-{first}-{writer}"))
                .file(
                    "Cargo.toml",
                    &format!(
                        "[package]\nname = \"overlap-app\"\nversion = \"0.1.0\"\nedition = \"2021\"\n\n[dependencies]\noverlap-common = \"1.0.0\"\nlocking-gate = {{ path = \"gate\" }}\n{extra}",
                    ),
                )
                .file("src/main.rs", &source("skip", writer))
                .file(
                    "gate/Cargo.toml",
                    "[package]\nname = \"locking-gate\"\nversion = \"0.1.0\"\nedition = \"2021\"\n\n[lib]\nproc-macro = true\n",
                )
                .file(
                    "gate/src/lib.rs",
                    r#"
                    extern crate proc_macro;
                    use std::io::{Read, Write};
                    use std::net::TcpStream;

                    #[proc_macro]
                    pub fn hold(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
                        let tag = input.to_string();
                        if tag != "skip" {
                            let mut stream = TcpStream::connect(
                                std::env::var("OHM_OVERLAP_GATE").unwrap()
                            ).unwrap();
                            writeln!(stream, "{} {}", tag, std::process::id()).unwrap();
                            stream.read_exact(&mut [0]).unwrap();
                        }
                        proc_macro::TokenStream::new()
                    }
                    "#,
                )
                .build()
        });
        let shared = paths::root().join(format!("overlap-shared-{first}"));
        let cargo = |project: &cargo_test_support::Project, input: &str| {
            let mut cargo = project.shared_registry_cargo(
                "-Zohm-shared-registry-cache build -j 1 -vv --message-format=json",
            );
            cargo
                .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
                .env("CARGO_BUILD_BUILD_DIR", &shared)
                .env("OHM_OVERLAP_INPUT", input);
            cargo
        };
        cargo(&projects[0], "before").run();
        if stale {
            cargo(&projects[1], "before").run();
        }
        let registries = shared.join("debug/build/registries");
        let fingerprint = walkdir::WalkDir::new(&registries)
            .into_iter()
            .map(Result::unwrap)
            .find(|entry| entry.file_name() == "lib-overlap_common")
            .expect("the common dependency must be shared")
            .into_path();
        let common_lock = fingerprint
            .parent()
            .unwrap()
            .parent()
            .unwrap()
            .join(".lock");
        let common_fingerprint = std::fs::read(&fingerprint).unwrap();
        assert!(!common_fingerprint.is_empty());

        if is_coarse_mtime() {
            sleep_ms(1000);
        }
        projects[0].change_file("src/main.rs", &source("consumer", false));
        projects[1].change_file("src/main.rs", &source("writer", true));
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let (ready, _queued) = mpsc::channel();
        let mut children = Vec::new();
        let mut gates = Vec::new();
        for index in [first, 1 - first] {
            let mut command = cargo(&projects[index], "after");
            command.env(
                "OHM_OVERLAP_GATE",
                listener.local_addr().unwrap().to_string(),
            );
            children.push(spawn_shared_registry_cargo(
                command.build_command(),
                index,
                &["overlap-common", "overlap-changing"],
                ready.clone(),
            ));
            match wait_for_private_compilation_gate(&listener) {
                Ok(gate) => gates.push(gate),
                Err(error) => {
                    // Unblock compiler descendants even when only Cargo can be killed.
                    // Also reject connections racing with cleanup through the listener.
                    drop(gates);
                    drop(listener);
                    for child in &mut children {
                        kill_shared_registry_cargo(&mut child.process);
                    }
                    let stderr = children
                        .into_iter()
                        .map(|child| {
                            String::from_utf8_lossy(&child.stderr.join().unwrap()).into_owned()
                        })
                        .collect::<Vec<_>>();
                    panic!("private compilations did not overlap: {error}; {stderr:#?}");
                }
            }
        }

        // Both real rustc processes remain in their private proc-macro invocation.
        // The extra unit has finished writing, but the common dependency is still
        // pinned while either compiler can consume it. Do not release either gate
        // until both have arrived: a whole-invocation profile writer cannot pass.
        let common_is_pinned = std::fs::File::open(&common_lock)
            .map(|lock| matches!(lock.try_lock(), Err(std::fs::TryLockError::WouldBlock)));
        let unchanged = std::fs::read(&fingerprint);
        let releases = gates
            .iter_mut()
            .map(|(_, _, stream)| stream.write_all(&[1]))
            .collect::<Vec<_>>();
        let outputs = finish_shared_registry_cargos(children);
        for output in &outputs {
            execs().run_output(output);
        }
        for release in releases {
            release.unwrap();
        }
        assert_ne!(
            gates[0].1, gates[1].1,
            "two separate compiler processes must overlap"
        );
        let expected = if first == 0 {
            ["consumer", "writer"]
        } else {
            ["writer", "consumer"]
        };
        assert_eq!([gates[0].0.as_str(), gates[1].0.as_str()], expected);
        assert!(
            common_is_pinned.unwrap(),
            "consumers must retain their common dependency lease"
        );
        assert_eq!(unchanged.unwrap(), common_fingerprint);

        let mut shared_writes = 0;
        for output in &outputs {
            assert!(
                !String::from_utf8_lossy(&output.stderr).lines().any(|line| {
                    line.contains("Running") && line.contains("--crate-name overlap_common ")
                })
            );
            for line in String::from_utf8_lossy(&output.stdout).lines() {
                let message: serde_json::Value = serde_json::from_str(line).unwrap();
                if message["reason"] == "compiler-artifact"
                    && message["target"]["name"] == "overlap_changing"
                    && message["fresh"] == false
                {
                    let filenames = message["filenames"].as_array().unwrap();
                    assert!(!filenames.is_empty());
                    assert!(
                        filenames.iter().all(|filename| {
                            std::path::Path::new(filename.as_str().unwrap())
                                .starts_with(&registries)
                        }),
                        "the writer must publish into the shared registry cache"
                    );
                    shared_writes += 1;
                }
            }
        }
        assert_eq!(shared_writes, 1);
        for (project, expected) in projects.iter().zip(["common/private\n", "common/after\n"]) {
            project
                .process(project.bin("overlap-app"))
                .with_stdout_data(expected)
                .run();
        }
    }
}

fn wait_for_private_compilation_gate(
    listener: &TcpListener,
) -> std::io::Result<(String, u32, TcpStream)> {
    let deadline = std::time::Instant::now() + slow_cpu_multiplier(30);
    loop {
        match listener.accept() {
            Ok((mut stream, _)) => {
                stream.set_nonblocking(false)?;
                stream.set_read_timeout(Some(slow_cpu_multiplier(5)))?;
                let mut message = String::new();
                BufReader::new(&mut stream).read_line(&mut message)?;
                let mut parts = message.split_whitespace();
                let tag = parts
                    .next()
                    .ok_or(std::io::ErrorKind::InvalidData)?
                    .to_owned();
                let pid = parts
                    .next()
                    .and_then(|pid| pid.parse().ok())
                    .ok_or(std::io::ErrorKind::InvalidData)?;
                if parts.next().is_some() {
                    return Err(std::io::ErrorKind::InvalidData.into());
                }
                return Ok((tag, pid, stream));
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {}
            Err(error) => return Err(error),
        }
        if std::time::Instant::now() >= deadline {
            return Err(std::io::ErrorKind::TimedOut.into());
        }
        sleep_ms(10);
    }
}

#[cfg(unix)]
#[cargo_test]
fn shared_registry_cache_rejects_unit_lock_aliases() {
    Package::new("lock-alias", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 7 }")
        .publish();
    let project = project()
        .file("Cargo.toml", "[package]\nname = \"lock-alias-app\"\nversion = \"0.1.0\"\nedition = \"2021\"\n\n[dependencies]\nlock-alias = \"1.0.0\"\n")
        .file("src/main.rs", "fn main() { assert_eq!(lock_alias::value(), 7); }")
        .build();
    let cargo = |shared: &std::path::Path| {
        let mut cargo = project.shared_registry_cargo("-Zohm-shared-registry-cache build");
        cargo
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_BUILD_BUILD_DIR", shared);
        cargo
    };
    let original = paths::root().join("original-lock-alias-cache");
    cargo(&original).run();
    let original_registries = original.join("debug/build/registries");
    for internal in [false, true] {
        let shared = paths::root().join(format!("aliased-lock-cache-{internal}"));
        cargo(&shared).run();
        let registries = shared.join("debug/build/registries");
        if internal {
            let unit_lock = walkdir::WalkDir::new(&registries)
                .into_iter()
                .map(Result::unwrap)
                .find(|entry| entry.file_name() == ".lock")
                .unwrap()
                .into_path();
            std::fs::remove_dir_all(unit_lock.parent().unwrap().join("out")).unwrap();
            std::fs::remove_file(&unit_lock).unwrap();
            std::os::unix::fs::symlink(shared.join("debug/.cargo-build-lock"), unit_lock).unwrap();
        } else {
            std::fs::remove_dir_all(&registries).unwrap();
            std::os::unix::fs::symlink(&original_registries, &registries).unwrap();
        }
        let (ready, _queued) = mpsc::channel();
        let child =
            spawn_shared_registry_cargo(cargo(&shared).build_command(), 0, &["lock-alias"], ready);
        for output in finish_shared_registry_cargos(vec![child]) {
            execs()
                .with_status(101)
                .with_stderr_contains(
                    "[..]shared registry unit lock escapes its locked build profile[..]",
                )
                .run_output(&output);
        }
    }
}

#[cargo_test]
fn shared_registry_cache_avoids_hashing_immutable_public_apis() {
    if !selected_compiler_supports_ohm_defaults() {
        return;
    }

    Package::new("immutable-hash-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 1 }")
        .publish();
    Package::new("mixed-artifact-hash-registry", "1.0.0")
        .file(
            "Cargo.toml",
            "[package]\nname = \"mixed-artifact-hash-registry\"\nversion = \"1.0.0\"\nedition = \"2021\"\n\n[lib]\ncrate-type = [\"rlib\", \"cdylib\"]\n",
        )
        .file("src/lib.rs", "pub fn value() -> u32 { 5 }")
        .publish();
    Package::new("hash-proc-macro", "1.0.0")
        .proc_macro(true)
        .file(
            "src/lib.rs",
            "extern crate proc_macro; #[proc_macro_attribute] pub fn unchanged(_: proc_macro::TokenStream, item: proc_macro::TokenStream) -> proc_macro::TokenStream { item }",
        )
        .publish();
    Package::new("mutable-registry-input", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 2 }")
        .publish();
    Package::new("patched-hash-registry", "1.0.0")
        .dep("mutable-registry-input", "1.0.0")
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { mutable_registry_input::value() }",
        )
        .publish();

    let project = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "hash-policy-app"
            version = "0.1.0"
            edition = "2021"

            [dependencies]
            hash-proc-macro = "1.0.0"
            immutable-hash-registry = "1.0.0"
            mixed-artifact-hash-registry = "1.0.0"
            patched-hash-registry = "1.0.0"
            mutable-workspace-library = { path = "local" }

            [patch.crates-io]
            mutable-registry-input = { path = "patched" }
            "#,
        )
        .file(
            "src/lib.rs",
            "#[hash_proc_macro::unchanged] pub fn value() -> u32 { immutable_hash_registry::value() + mixed_artifact_hash_registry::value() + patched_hash_registry::value() + mutable_workspace_library::value() }",
        )
        .file(
            "local/Cargo.toml",
            "[package]\nname = \"mutable-workspace-library\"\nversion = \"1.0.0\"\nedition = \"2021\"\n",
        )
        .file("local/src/lib.rs", "pub fn value() -> u32 { 3 }")
        .file(
            "patched/Cargo.toml",
            "[package]\nname = \"mutable-registry-input\"\nversion = \"1.0.0\"\nedition = \"2021\"\n",
        )
        .file("patched/src/lib.rs", "pub fn value() -> u32 { 4 }")
        .build();
    let shared_build = paths::root()
        .join("target")
        .join("immutable-hash-shared-build");

    project
        .cargo("-Zohm-shared-registry-cache check -v")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-shared-registry-cache"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .env("CARGO_BUILD_BUILD_DIR", &shared_build)
        .with_stderr_line_without(
            &[
                "[RUNNING] `rustc",
                "--crate-name immutable_hash_registry",
                "-Zpublic-api-hash=no",
            ],
            &[],
        )
        .with_stderr_line_without(
            &["[RUNNING] `rustc", "--crate-name patched_hash_registry"],
            &["-Zpublic-api-hash=no"],
        )
        .with_stderr_line_without(
            &[
                "[RUNNING] `rustc",
                "--crate-name mixed_artifact_hash_registry",
            ],
            &["-Zpublic-api-hash=no"],
        )
        .with_stderr_line_without(
            &["[RUNNING] `rustc", "--crate-name hash_proc_macro"],
            &["-Zpublic-api-hash=no"],
        )
        .with_stderr_line_without(
            &["[RUNNING] `rustc", "--crate-name mutable_workspace_library"],
            &["-Zpublic-api-hash=no"],
        )
        .run();

    project
        .cargo("-Zohm-shared-registry-cache build -v")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-shared-registry-cache"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .env(
            "CARGO_BUILD_BUILD_DIR",
            paths::root().join("immutable-hash-build-mode"),
        )
        .with_stderr_line_without(
            &[
                "[RUNNING] `rustc",
                "--crate-name immutable_hash_registry",
                "-Zpublic-api-hash=no",
            ],
            &[],
        )
        .with_stderr_line_without(
            &["[RUNNING] `rustc", "--crate-name patched_hash_registry"],
            &["-Zpublic-api-hash=no"],
        )
        .with_stderr_line_without(
            &[
                "[RUNNING] `rustc",
                "--crate-name mixed_artifact_hash_registry",
            ],
            &["-Zpublic-api-hash=no"],
        )
        .run();

    project
        .cargo("-Zohm-shared-registry-cache check -v")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-shared-registry-cache"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .env("RUSTFLAGS", "-Zpublic-api-hash=yes")
        .env(
            "CARGO_BUILD_BUILD_DIR",
            paths::root().join("immutable-hash-explicit-override"),
        )
        .with_stderr_line_without(
            &[
                "[RUNNING] `rustc",
                "--crate-name immutable_hash_registry",
                "-Zpublic-api-hash=yes",
            ],
            &["-Zpublic-api-hash=no"],
        )
        .run();

    project
        .cargo("-Zohm-shared-registry-cache check -v")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-shared-registry-cache"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .env("RUSTFLAGS", "-Zpublic_api_hash=yes")
        .env(
            "CARGO_BUILD_BUILD_DIR",
            paths::root().join("immutable-hash-underscore-override"),
        )
        .with_stderr_line_without(
            &[
                "[RUNNING] `rustc",
                "--crate-name immutable_hash_registry",
                "-Zpublic_api_hash=yes",
            ],
            &["-Zpublic-api-hash=no"],
        )
        .run();

    project
        .cargo("-Zohm-defaults=no -Zohm-shared-registry-cache check -v")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-shared-registry-cache"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .env("CARGO_BUILD_BUILD_DIR", &shared_build)
        .with_stderr_line_without(
            &["[RUNNING] `rustc", "--crate-name immutable_hash_registry"],
            &["-Zpublic-api-hash"],
        )
        .run();

    assert_eq!(
        std::fs::read_dir(shared_build.join("debug/build/registries"))
            .expect("read compiler-policy namespaces")
            .count(),
        2,
        "default and opted-out hash policies must never share registry artifacts"
    );
}

#[cargo_test]
fn shared_registry_cache_automatically_shares_explicit_build_directories() {
    if !selected_compiler_supports_ohm_defaults() {
        return;
    }

    Package::new("automatic-shared-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 17 }")
        .publish();

    let create_project = |worktree: &str, value: u32| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "automatic-shared-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                automatic-shared-registry = "1.0.0"
                "#,
            )
            .file(
                "src/main.rs",
                &format!(
                    "fn main() {{ println!(\"{{}}:{value}\", automatic_shared_registry::value()); }}"
                ),
            )
            .build()
    };
    let left = create_project("automatic-shared-worktree-left", 1);
    let right = create_project("automatic-shared-worktree-right", 2);
    let shared = paths::root().join("automatic-shared-build-directory");

    left.cargo("run")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] automatic-shared-registry v1.0.0")
        .with_stdout_data("17:1\n")
        .run();
    right
        .cargo("run")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[COMPILING] automatic-shared-registry v1.0.0")
        .with_stdout_data("17:2\n")
        .run();

    assert!(shared.join(".ohm-shared-registry-cache-v1").is_file());
    assert!(shared.join("debug/build/registries").is_dir());
    assert_eq!(
        std::fs::read_dir(shared.join("debug/incremental"))
            .expect("read workspace-private incremental directories")
            .count(),
        2,
    );

    right
        .cargo("check -v")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[FRESH] automatic-shared-registry v1.0.0")
        .with_stderr_does_not_contain("[CHECKING] automatic-shared-registry v1.0.0")
        .run();
}

#[cargo_test]
fn shared_registry_cache_preserves_cross_workspace_reuse_and_private_early_cutoff() {
    if !selected_compiler_supports_ohm_defaults() {
        return;
    }

    Package::new("cutoff-shared-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 10 }")
        .publish();

    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "cutoff-shared-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                cutoff-shared-registry = "1.0.0"
                cutoff-middle = { path = "middle" }
                "#,
            )
            .file(
                "src/lib.rs",
                "pub fn value() -> u32 { cutoff_shared_registry::value() + cutoff_middle::value() }",
            )
            .file(
                "middle/Cargo.toml",
                r#"
                [package]
                name = "cutoff-middle"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                cutoff-private = { path = "../private" }
                "#,
            )
            .file(
                "middle/src/lib.rs",
                "pub fn value() -> u32 { cutoff_private::value() }",
            )
            .file(
                "private/Cargo.toml",
                r#"
                [package]
                name = "cutoff-private"
                version = "0.1.0"
                edition = "2021"
                "#,
            )
            .file("private/src/lib.rs", "pub fn value() -> u32 { 1 }")
            .build()
    };

    let left = create_project("shared-cutoff-left");
    let right = create_project("shared-cutoff-right");
    let shared = paths::root().join("cross-workspace-early-cutoff-build-directory");

    left.cargo("-Zohm-shared-registry-cache -Zohm-defaults check")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-shared-registry-cache"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[CHECKING] cutoff-shared-registry v1.0.0")
        .run();

    let workspace_root = shared.join("debug/build/workspaces");
    let left_namespaces = std::fs::read_dir(&workspace_root)
        .expect("left workspace namespace should exist")
        .map(|entry| {
            entry
                .expect("workspace namespace should be readable")
                .file_name()
        })
        .collect::<Vec<_>>();
    let left_workspace_lock_path = workspace_root
        .join(
            left_namespaces
                .first()
                .expect("left workspace namespace should have been created"),
        )
        .join(".cargo-workspace-lock");
    let left_workspace_lock = std::fs::File::options()
        .read(true)
        .write(true)
        .open(&left_workspace_lock_path)
        .expect("left workspace lock should be readable and writable");
    left_workspace_lock
        .lock()
        .expect("left workspace lock should be acquired exclusively");
    let competing_left_workspace_lock = std::fs::File::options()
        .read(true)
        .write(true)
        .open(&left_workspace_lock_path)
        .expect("competing workspace lock should open independently");
    assert!(matches!(
        competing_left_workspace_lock.try_lock(),
        Err(std::fs::TryLockError::WouldBlock)
    ));

    right
        .cargo("-Zohm-shared-registry-cache -Zohm-defaults check")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-shared-registry-cache"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[CHECKING] cutoff-shared-registry v1.0.0")
        .run();
    drop(left_workspace_lock);

    let right_namespace = std::fs::read_dir(&workspace_root)
        .expect("right workspace namespace should exist")
        .filter_map(Result::ok)
        .find(|entry| !left_namespaces.contains(&entry.file_name()))
        .expect("the second workspace should have its own namespace")
        .path();
    assert!(right_namespace.join(".cargo-workspace-lock").is_file());

    let metadata = walkdir::WalkDir::new(&right_namespace)
        .into_iter()
        .filter_map(Result::ok)
        .map(|entry| entry.into_path())
        .find(|path| {
            path.extension().and_then(|extension| extension.to_str()) == Some("rmeta")
                && path
                    .file_name()
                    .and_then(|name| name.to_str())
                    .is_some_and(|name| name.starts_with("libcutoff_private-"))
        })
        .expect("workspace-private dependency metadata should exist");
    let initial_modified = filetime::FileTime::from_last_modification_time(
        &std::fs::metadata(&metadata).expect("dependency metadata should be readable"),
    );

    if is_coarse_mtime() {
        sleep_ms(1000);
    }
    right.change_file("private/src/lib.rs", "pub fn value() -> u32 { 2 }");
    right
        .cargo("-Zohm-shared-registry-cache -Zohm-defaults check -v")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-shared-registry-cache"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_line_without(
            &["[RUNNING] `rustc", "--crate-name cutoff_private"],
            &[
                "--crate-name cutoff_middle",
                "--crate-name cutoff_shared_app",
                "--crate-name cutoff_shared_registry",
            ],
        )
        .with_stderr_contains("[FRESH] cutoff-shared-registry v1.0.0")
        .with_stderr_does_not_contain("[RUNNING] `rustc [..]--crate-name cutoff_middle[..]")
        .with_stderr_does_not_contain("[RUNNING] `rustc [..]--crate-name cutoff_shared_app[..]")
        .with_stderr_does_not_contain(
            "[RUNNING] `rustc [..]--crate-name cutoff_shared_registry[..]",
        )
        .run();

    let rebuilt_modified = filetime::FileTime::from_last_modification_time(
        &std::fs::metadata(metadata).expect("rebuilt dependency metadata should be readable"),
    );
    assert_eq!(rebuilt_modified, initial_modified);
}

#[cargo_test]
fn shared_registry_cache_allows_nested_builds_with_distinct_target_directories() {
    Package::new("nested-common", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 7 }")
        .publish();
    Package::new("nested-helper-only", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 11 }")
        .publish();
    let project = project()
        .file(
            "Cargo.toml",
            r#"
            [workspace]
            members = ["outer", "helper"]
            resolver = "2"
            "#,
        )
        .file(
            "outer/Cargo.toml",
            r#"
            [package]
            name = "nested-outer"
            version = "0.1.0"
            edition = "2021"

            [dependencies]
            nested-common = "1.0.0"

            [build-dependencies]
            nested-common = "1.0.0"
            "#,
        )
        .file("outer/src/lib.rs", "pub use nested_common::value;")
        .file(
            "outer/build.rs",
            r#"
            use std::env;
            use std::ffi::OsStr;
            use std::path::PathBuf;
            use std::process::{Command, Output};

            fn run_nested(target: &OsStr, mode: &str) -> Output {
                let mut command = Command::new(env::var_os("CARGO").expect("Cargo executable"));
                command.env("__CARGO_OHM_DEFAULTS", "no");
                match mode {
                    "shared" => { command.arg("-Zohm-shared-registry-cache"); }
                    "defaults" => {
                        command.env("__CARGO_OHM_DEFAULTS", env::var_os("OHM_TEST_COMPILER_DEFAULTS").unwrap());
                    }
                    "disabled" => {
                        command.arg("-Zohm-defaults=no").env("__CARGO_OHM_DEFAULTS", "yes");
                    }
                    _ => unreachable!(),
                }
                command
                    .args(["check", "-p", "nested-helper", "--target-dir"])
                    .arg(target)
                    // Keep the initial configured target valid too: an invalid CLI
                    // target must still be caught when applied after workspace creation.
                    .env("CARGO_TARGET_DIR", env::var_os("OHM_NESTED_TARGET_DIRECTORY").unwrap());
                command.output().expect("nested Cargo should start")
            }

            fn main() {
                assert_eq!(nested_common::value(), 7);
                let shared = env::var_os("CARGO_BUILD_BUILD_DIR")
                    .expect("nested Cargo must inherit the shared build directory");
                assert_eq!(
                    Some(shared.clone()),
                    env::var_os("OHM_EXPECTED_SHARED_BUILD_DIRECTORY")
                );
                let parent_target = env::var_os("OHM_PARENT_TARGET_DIRECTORY").unwrap();
                assert_eq!(env::var_os("CARGO_TARGET_DIR"), Some(parent_target.clone()));
                let assert_rejected = |output: Output| {
                    assert_eq!(output.status.code(), Some(101), "{output:?}");
                    assert!(
                        String::from_utf8_lossy(&output.stderr).contains(
                            "nested Cargo requires a target directory separate from its parent's build and target directories"
                        ),
                        "{output:?}"
                    );
                };

                // Read-only commands can use the inherited parent target. Cleaning
                // that same target must fail before it can remove in-use artifacts.
                let mut metadata = Command::new(env::var_os("CARGO").unwrap());
                metadata.args(["metadata", "--no-deps", "--format-version", "1"]);
                let output = metadata.output().expect("nested metadata should start");
                assert!(output.status.success(), "nested metadata failed: {output:?}");
                assert!(String::from_utf8_lossy(&output.stdout).contains("\"workspace_members\""));
                let mut clean = Command::new(env::var_os("CARGO").unwrap());
                clean.arg("clean");
                assert_rejected(clean.output().expect("nested clean should start"));

                // Cleaning an ancestor would also remove the active parent roots,
                // even though it does not equal either root. Keep this target inside
                // the disposable fixture and check both roots survive unchanged.
                let sentinels = [
                    PathBuf::from(shared.clone()).join("parent-build-sentinel"),
                    PathBuf::from(parent_target.clone()).join("parent-target-sentinel"),
                ];
                let contents = b"active parent artifacts must survive nested clean";
                for sentinel in &sentinels {
                    std::fs::write(sentinel, contents).unwrap();
                }
                let mut clean = Command::new(env::var_os("CARGO").unwrap());
                clean.args(["clean", "--target-dir"])
                    .arg(env::var_os("OHM_NESTED_ANCESTOR_TARGET").unwrap());
                let output = clean.output().expect("nested ancestor clean should start");
                for sentinel in &sentinels {
                    assert_eq!(
                        std::fs::read(sentinel).expect("nested clean must preserve the parent's files"),
                        contents,
                    );
                }
                assert_eq!(output.status.code(), Some(101), "{output:?}");
                assert!(
                    String::from_utf8_lossy(&output.stderr).contains(
                        "nested Cargo cannot clean a directory containing its parent"
                    ),
                    "{output:?}"
                );

                let mut invalid = vec![shared, parent_target.clone()];
                if let Some(alias) = env::var_os("OHM_SHARED_BUILD_ALIAS") {
                    invalid.push(alias);
                }
                for target in invalid {
                    assert_rejected(run_nested(&target, "shared"));
                }
                let private_target = env::var_os("OHM_NESTED_TARGET_DIRECTORY").unwrap();
                let descendant_target = PathBuf::from(parent_target).join("helpers");
                for target in [private_target, descendant_target.clone().into_os_string()] {
                    let output = run_nested(&target, "shared");
                    assert!(output.status.success(), "nested Cargo failed: {output:?}");
                }
                let out_target = PathBuf::from(env::var_os("OUT_DIR").unwrap()).join("nested-cargo-target");
                std::fs::write(
                    env::var_os("OHM_NESTED_OUT_TARGET_FILE").unwrap(),
                    out_target.to_str().unwrap(),
                ).unwrap();
                for mode in ["defaults", "disabled"] {
                    for target in [&descendant_target, &out_target] {
                        let output = run_nested(target.as_os_str(), mode);
                        assert!(output.status.success(), "nested Cargo ({mode}) failed: {output:?}");
                    }
                }
            }
            "#,
        )
        .file(
            "helper/Cargo.toml",
            r#"
            [package]
            name = "nested-helper"
            version = "0.1.0"
            edition = "2021"

            [dependencies]
            nested-common = "1.0.0"
            nested-helper-only = "1.0.0"
            "#,
        )
        .file(
            "helper/src/lib.rs",
            "pub fn value() -> u32 { nested_common::value() + nested_helper_only::value() }",
        )
        .build();
    let shared = paths::root().join("nested-workspace-shared-build-directory");
    let parent_target = project.root().join("parent-target");
    let nested_target = project.root().join("nested-target");
    let descendant_target = parent_target.join("helpers");
    let out_target_file = paths::root().join("nested-out-target");

    let mut cargo =
        project.shared_registry_cargo("-Zohm-shared-registry-cache check -p nested-outer");
    cargo
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache", "ohm-defaults"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("CARGO_TARGET_DIR", &parent_target)
        .env("OHM_PARENT_TARGET_DIRECTORY", &parent_target)
        .env("OHM_EXPECTED_SHARED_BUILD_DIRECTORY", &shared)
        .env("OHM_NESTED_TARGET_DIRECTORY", &nested_target)
        .env("OHM_NESTED_OUT_TARGET_FILE", &out_target_file)
        .env("OHM_NESTED_ANCESTOR_TARGET", paths::root())
        .env(
            "OHM_TEST_COMPILER_DEFAULTS",
            if selected_compiler_supports_ohm_defaults() {
                "yes"
            } else {
                "no"
            },
        );
    #[cfg(unix)]
    {
        let alias = project.root().join("shared-build-alias");
        std::os::unix::fs::symlink(&shared, &alias).unwrap();
        cargo.env("OHM_SHARED_BUILD_ALIAS", alias);
    }
    // Bound the complete process tree, including nested Cargo and its compilers.
    // Command::output inside build.rs drains both child pipes while they run.
    let (ready, _queued) = mpsc::channel();
    let child = spawn_shared_registry_cargo(cargo.build_command(), 0, &["nested-common"], ready);
    for output in finish_shared_registry_cargos(vec![child]) {
        execs().run_output(&output);
    }
    let out_target = PathBuf::from(std::fs::read_to_string(out_target_file).unwrap());

    assert!(parent_target.is_dir());
    assert!(nested_target.is_dir());
    let namespaces = std::fs::read_dir(shared.join("debug/build/workspaces"))
        .expect("the outer workspace should have a private namespace")
        .map(|entry| entry.expect("workspace namespace should be readable"))
        .collect::<Vec<_>>();
    // The parent still holds its shared-cache lock while build.rs waits for the
    // nested Cargo. The nested invocation must use its private target directory
    // for both its workspace and registry artifacts, while preserving the visible
    // CARGO_BUILD_BUILD_DIR environment inherited by the build script.
    assert_eq!(namespaces.len(), 1);
    for namespace in namespaces {
        assert!(namespace.path().join(".cargo-workspace-lock").is_file());
    }
    for fingerprint in ["lib-nested_helper", "lib-nested_helper_only"] {
        for target in [&nested_target, &descendant_target, &out_target] {
            assert!(
                walkdir::WalkDir::new(target)
                    .into_iter()
                    .map(Result::unwrap)
                    .any(|entry| entry.file_name() == fingerprint)
            );
        }
        assert!(
            !walkdir::WalkDir::new(shared.join("debug/build"))
                .into_iter()
                // OUT_DIR belongs to the parent's private workspace namespace; a
                // nested target below it does not publish into shared registry units.
                .filter_entry(|entry| !entry.path().starts_with(&out_target))
                .map(Result::unwrap)
                .any(|entry| entry.file_name() == fingerprint)
        );
    }
}

#[cargo_test]
fn shared_registry_cache_isolates_target_directories_and_cleans_only_their_private_artifacts() {
    Package::new("target-isolation-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 7 }")
        .publish();

    let project = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "target-isolation-app"
            version = "0.1.0"
            edition = "2021"

            [dependencies]
            target-isolation-registry = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { target_isolation_registry::value() }",
        )
        .build();
    let shared = paths::root().join("target-isolation-shared-build-directory");
    let left_target = project.root().join("left-target");
    let right_target = project.root().join("right-target");

    project
        .shared_registry_cargo("-Zohm-shared-registry-cache check")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("CARGO_TARGET_DIR", &left_target)
        .with_stderr_contains("[CHECKING] target-isolation-registry v1.0.0")
        .run();

    let workspace_root = shared.join("debug/build/workspaces");
    let left_namespace = std::fs::read_dir(&workspace_root)
        .expect("left target namespace should exist")
        .next()
        .expect("left target should have a private namespace")
        .expect("left target namespace should be readable")
        .path();
    let legacy_namespace = short_hash(
        &project
            .root()
            .canonicalize()
            .expect("workspace root should have a canonical path"),
    );
    assert_ne!(
        left_namespace.file_name().and_then(|name| name.to_str()),
        Some(legacy_namespace.as_str()),
        "older Cargo processes do not participate in the new workspace-lock protocol",
    );

    project
        .shared_registry_cargo("-Zohm-shared-registry-cache check -v")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("CARGO_TARGET_DIR", &right_target)
        .with_stderr_contains("[FRESH] target-isolation-registry v1.0.0")
        .with_stderr_does_not_contain("[CHECKING] target-isolation-registry v1.0.0")
        .with_stderr_contains("[CHECKING] target-isolation-app v0.1.0 ([..])")
        .run();

    let right_namespace = std::fs::read_dir(&workspace_root)
        .expect("both target namespaces should exist")
        .filter_map(Result::ok)
        .find(|entry| entry.path() != left_namespace)
        .expect("the right target should have an independent namespace")
        .path();
    let private_metadata_exists = |namespace: &PathBuf| {
        walkdir::WalkDir::new(namespace)
            .into_iter()
            .filter_map(Result::ok)
            .any(|entry| {
                entry.file_name().to_str().is_some_and(|name| {
                    name.starts_with("libtarget_isolation_app-") && name.ends_with(".rmeta")
                })
            })
    };
    assert!(left_namespace.join(".cargo-workspace-lock").is_file());
    assert!(right_namespace.join(".cargo-workspace-lock").is_file());
    assert!(private_metadata_exists(&left_namespace));
    assert!(private_metadata_exists(&right_namespace));
    let registry = shared.join("debug/build/registries");
    assert!(registry.is_dir());
    assert_eq!(
        std::fs::read_dir(&registry)
            .expect("shared registry compiler contexts should be readable")
            .count(),
        1,
    );

    std::fs::remove_dir_all(&left_target)
        .expect("simulate a target directory removed before Cargo cleans its private artifacts");
    project
        .shared_registry_cargo("clean")
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("CARGO_TARGET_DIR", &left_target)
        .run();

    assert!(!left_namespace.exists());
    assert!(right_target.is_dir());
    assert!(private_metadata_exists(&right_namespace));
    assert!(registry.is_dir());

    project
        .shared_registry_cargo("-Zohm-shared-registry-cache check -v")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("CARGO_TARGET_DIR", &right_target)
        .with_stderr_contains("[FRESH] target-isolation-registry v1.0.0")
        .with_stderr_does_not_contain("[CHECKING] target-isolation-app v0.1.0 ([..])")
        .run();
}

#[cfg(unix)]
#[cargo_test]
fn shared_registry_cache_canonicalizes_symlinked_target_directories() {
    let project = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "symlinked-target-app"
            version = "0.1.0"
            edition = "2021"
            "#,
        )
        .file("src/lib.rs", "pub fn value() -> u32 { 1 }")
        .build();
    let shared = paths::root().join("symlinked-target-shared-build-directory");
    let target = project.root().join("physical-target");
    let alias = project.root().join("target-alias");

    project
        .cargo("-Zohm-shared-registry-cache check")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("CARGO_TARGET_DIR", &target)
        .run();
    std::os::unix::fs::symlink(&target, &alias)
        .expect("target-directory alias should point to the original target");
    project
        .cargo("-Zohm-shared-registry-cache check")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("CARGO_TARGET_DIR", &alias)
        .with_stderr_does_not_contain("[CHECKING] symlinked-target-app v0.1.0 ([..])")
        .run();

    assert_eq!(
        std::fs::read_dir(shared.join("debug/build/workspaces"))
            .expect("canonical target aliases should share one namespace")
            .count(),
        1,
    );
}

#[cargo_test]
fn shared_registry_cache_defaults_preserve_ordinary_layout_without_build_directory() {
    if !selected_compiler_supports_ohm_defaults() {
        return;
    }

    Package::new("ordinary-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 23 }")
        .publish();

    let project = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "ordinary-layout-app"
            version = "0.1.0"
            edition = "2021"

            [dependencies]
            ordinary-registry = "1.0.0"
            "#,
        )
        .file(
            "src/main.rs",
            "fn main() { println!(\"{}\", ordinary_registry::value()); }",
        )
        .build();

    project
        .cargo("run")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .env_remove("CARGO_BUILD_BUILD_DIR")
        .with_stderr_contains("[COMPILING] ordinary-registry v1.0.0")
        .with_stdout_data("23\n")
        .run();

    let target = project.root().join("target");
    assert!(target.join("debug/.fingerprint").is_dir());
    assert!(!target.join(".ohm-shared-registry-cache-v1").exists());
    assert!(!target.join("debug/build/registries").exists());
}

#[cargo_test]
fn shared_registry_cache_defaults_preserve_overlapping_build_directories() {
    if !selected_compiler_supports_ohm_defaults() {
        return;
    }

    Package::new("overlapping-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 31 }")
        .publish();

    let absolute_equal = paths::root().join("overlap-absolute-equal");
    let absolute_child = paths::root().join("overlap-absolute-child");
    let absolute_parent = paths::root().join("overlap-absolute-parent");
    let cases = [
        ("relative-equal", PathBuf::from("target"), None),
        ("relative-child", PathBuf::from("target/cache"), None),
        (
            "workspace-template",
            PathBuf::from("{workspace-root}/target"),
            None,
        ),
        (
            "absolute-equal",
            absolute_equal.clone(),
            Some(absolute_equal),
        ),
        (
            "absolute-child",
            absolute_child.join("cache"),
            Some(absolute_child),
        ),
        (
            "absolute-parent",
            absolute_parent.clone(),
            Some(absolute_parent.join("workspace-output")),
        ),
    ];

    for (name, build_directory, target_directory) in cases {
        let project = project_in(&format!("overlapping-build-directory-{name}"))
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "overlapping-build-directory-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                overlapping-registry = "1.0.0"
                "#,
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", overlapping_registry::value()); }",
            )
            .build();

        let mut build = project.cargo("build");
        build
            .masquerade_as_nightly_cargo(&["ohm-defaults"])
            .env("__CARGO_OHM_DEFAULTS", "yes")
            .env("CARGO_BUILD_BUILD_DIR", &build_directory);
        if let Some(target_directory) = &target_directory {
            build.env("CARGO_TARGET_DIR", target_directory);
        }
        build.run();

        let actual_build_directory = if name == "workspace-template" {
            project.root().join("target")
        } else if build_directory.is_absolute() {
            build_directory.clone()
        } else {
            project.root().join(&build_directory)
        };
        assert!(
            !actual_build_directory
                .join(".ohm-shared-registry-cache-v1")
                .exists(),
            "{name} must retain Cargo's ordinary build layout"
        );

        let mut clean = project.cargo("clean");
        clean
            .masquerade_as_nightly_cargo(&["ohm-defaults"])
            .env("__CARGO_OHM_DEFAULTS", "yes")
            .env("CARGO_BUILD_BUILD_DIR", &build_directory);
        if let Some(target_directory) = &target_directory {
            clean.env("CARGO_TARGET_DIR", target_directory);
        }
        clean.run();
    }
}

#[cargo_test]
fn shared_registry_cache_defaults_respect_aggregate_opt_out() {
    Package::new("opt-out-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 29 }")
        .publish();

    let project = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "opt-out-app"
            version = "0.1.0"
            edition = "2021"

            [dependencies]
            opt-out-registry = "1.0.0"
            "#,
        )
        .file(
            "src/main.rs",
            "fn main() { println!(\"{}\", opt_out_registry::value()); }",
        )
        .build();
    let ordinary = paths::root().join("opted-out-build-directory");

    project
        .shared_registry_cargo("-Zohm-defaults=no run")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .env("CARGO_BUILD_BUILD_DIR", &ordinary)
        .with_stdout_data("29\n")
        .run();

    assert!(ordinary.join("debug/.fingerprint").is_dir());
    assert!(!ordinary.join(".ohm-shared-registry-cache-v1").exists());
    assert!(!ordinary.join("debug/build/registries").exists());

    let explicit = paths::root().join("explicitly-shared-build-directory");
    project
        .shared_registry_cargo("-Zohm-defaults=no -Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-shared-registry-cache"])
        .env("__CARGO_OHM_DEFAULTS", "yes")
        .env("CARGO_BUILD_BUILD_DIR", &explicit)
        .with_stdout_data("29\n")
        .run();

    assert!(explicit.join(".ohm-shared-registry-cache-v1").is_file());
    assert!(explicit.join("debug/build/registries").is_dir());
}

#[cargo_test]
fn shared_registry_cache_separates_procedural_macro_trust_policies() {
    Package::new("policy-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 47 }")
        .publish();

    let create_project = |name: &str| {
        project_in(name)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "policy-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                policy-registry = "1.0.0"
                "#,
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", policy_registry::value()); }",
            )
            .build()
    };
    let audited = create_project("macro-policy-audited");
    let permissive = create_project("macro-policy-all");
    let shared = paths::root().join("macro-policy-shared-build-directory");

    audited
        .shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] policy-registry v1.0.0")
        .with_stdout_data("47\n")
        .run();

    permissive
        .shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST", "all")
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] policy-registry v1.0.0")
        .with_stdout_data("47\n")
        .run();

    permissive
        .shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST", "all")
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[COMPILING] policy-registry v1.0.0")
        .with_stdout_data("47\n")
        .run();

    permissive
        .shared_registry_cargo("-Zohm-shared-registry-cache -Zohm-proc-macro-trust=audited run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache", "ohm-proc-macro-trust"])
        .env("CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST", "all")
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[COMPILING] policy-registry v1.0.0")
        .with_stdout_data("47\n")
        .run();
}

#[cargo_test]
fn shared_registry_cache_separates_native_tool_trust_policies() {
    Package::new("native-policy-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 53 }")
        .publish();

    let create_project = |name: &str| {
        project_in(name)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "native-policy-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                native-policy-registry = "1.0.0"
                "#,
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", native_policy_registry::value()); }",
            )
            .build()
    };
    let strict = create_project("native-policy-strict");
    let build_scripts = create_project("native-policy-build-scripts");
    let all = create_project("native-policy-all");
    let shared = paths::root().join("native-policy-shared-build-directory");

    strict
        .shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] native-policy-registry v1.0.0")
        .with_stdout_data("53\n")
        .run();

    for (project, policy) in [(&build_scripts, "build-scripts"), (&all, "all")] {
        project
            .shared_registry_cargo("-Zohm-shared-registry-cache run")
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST", policy)
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .with_stderr_contains("[COMPILING] native-policy-registry v1.0.0")
            .with_stdout_data("53\n")
            .run();

        project
            .shared_registry_cargo("-Zohm-shared-registry-cache run")
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST", policy)
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .with_stderr_does_not_contain("[COMPILING] native-policy-registry v1.0.0")
            .with_stdout_data("53\n")
            .run();
    }

    all.shared_registry_cargo("-Zohm-shared-registry-cache -Zohm-native-tool-trust=strict run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache", "ohm-native-tool-trust"])
        .env("CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST", "all")
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[COMPILING] native-policy-registry v1.0.0")
        .with_stdout_data("53\n")
        .run();

    all.shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST", "all")
        .env("CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST", "all")
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] native-policy-registry v1.0.0")
        .with_stdout_data("53\n")
        .run();
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

    left.shared_registry_cargo("-Zohm-shared-registry-cache run")
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
        .shared_registry_cargo("run")
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

    left.shared_registry_cargo("-Zohm-shared-registry-cache run")
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
fn shared_registry_cache_keeps_replaced_registry_sources_private() {
    Package::new("replaced-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 41 }")
        .publish();

    let _alternative = RegistryBuilder::new().alternative().build();
    Package::new("replaced-registry", "1.0.0")
        .alternative(true)
        .file("src/lib.rs", "pub fn value() -> u32 { 82 }")
        .publish();

    let manifest = r#"
        [package]
        name = "replacement-cache-app"
        version = "0.1.0"
        edition = "2021"

        [dependencies]
        replaced-registry = "1.0.0"
    "#;
    let source = "fn main() { println!(\"{}\", replaced_registry::value()); }";
    let original = project_in("original-registry-worktree")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .build();
    let replaced = project_in("replaced-registry-worktree")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .file(
            ".cargo/config.toml",
            r#"
                [source.crates-io]
                replace-with = "alternative"
            "#,
        )
        .build();
    let shared = paths::root().join("replacement-shared-build-directory");

    original
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] replaced-registry v1.0.0")
        .with_stdout_data("41\n")
        .run();

    replaced
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] replaced-registry v1.0.0")
        .with_stdout_data("82\n")
        .run();

    original
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[COMPILING] replaced-registry v1.0.0")
        .with_stdout_data("41\n")
        .run();
}

#[cargo_test]
fn shared_registry_cache_rejects_global_compiler_wrappers() {
    Package::new("wrapped-registry", "1.0.0")
        .file(
            "build.rs",
            r#"fn main() {
                if std::env::var_os("OHM_PRIVATE_BUILD_SCRIPT_PATH").is_some() {
                    println!("cargo:rustc-env=PATH={}", std::env::var("PATH").unwrap());
                }
            }"#,
        )
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
        .env("OHM_PRIVATE_BUILD_SCRIPT_PATH", "1")
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
fn shared_registry_cache_rejects_hidden_codegen_backends() {
    Package::new("backend-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 37 }")
        .publish();

    let manifest = r#"
        [package]
        name = "backend-cache-app"
        version = "0.1.0"
        edition = "2021"

        [dependencies]
        backend-registry = "1.0.0"
    "#;
    let response = paths::root().join("backend.args");
    std::fs::write(&response, "-Zcodegen-backend=llvm\n")
        .expect("write opaque compiler backend response file");
    let split_response = paths::root().join("split-backend.args");
    std::fs::write(&split_response, "codegen-backend=llvm\n")
        .expect("write split compiler backend response file");
    let flags = [
        format!("@{}", response.display()),
        format!("-Z @{}", split_response.display()),
        "-Zcodegen_backend=llvm".to_owned(),
        "-Zllvm-plugins=".to_owned(),
        "-Zllvm_plugins=".to_owned(),
        "-Z llvm-plugins=".to_owned(),
        "-Zautodiff".to_owned(),
        "-Z autodiff".to_owned(),
        "-Clinker=cc".to_owned(),
        "-C linker=cc".to_owned(),
        "--codegen=linker=cc".to_owned(),
        "--codegen linker=cc".to_owned(),
        "-Zpre-link-args=".to_owned(),
        "-Zpre_link_args=".to_owned(),
        "-Z pre-link-args=".to_owned(),
    ];

    for (index, rustflags) in flags.into_iter().enumerate() {
        let left_name = format!("backend-worktree-{index}-left");
        let right_name = format!("backend-worktree-{index}-right");
        let left = project_in(&left_name)
            .file("Cargo.toml", manifest)
            .file("src/lib.rs", "pub use backend_registry::value;")
            .build();
        let right = project_in(&right_name)
            .file("Cargo.toml", manifest)
            .file("src/lib.rs", "pub use backend_registry::value;")
            .build();
        let shared = paths::root().join(format!("backend-shared-build-directory-{index}"));

        left.cargo("-Zohm-shared-registry-cache build")
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .env("RUSTC_BOOTSTRAP", "1")
            .env("RUSTFLAGS", &rustflags)
            .with_stderr_contains("[COMPILING] backend-registry v1.0.0")
            .run();
        right
            .cargo("-Zohm-shared-registry-cache build")
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .env("RUSTC_BOOTSTRAP", "1")
            .env("RUSTFLAGS", &rustflags)
            .with_stderr_contains("[COMPILING] backend-registry v1.0.0")
            .run();
    }
}

#[cargo_test]
fn shared_registry_cache_keeps_custom_target_codegen_backends_private() {
    let mut target = serde_json::from_str::<serde_json::Value>(target_spec_json())
        .expect("parse known compiler target specification");
    target["default-codegen-backend"] = serde_json::Value::String("llvm".to_owned());
    let target_json = serde_json::to_string(&target).expect("serialize custom target backend");

    Package::new("target-backend-registry", "1.0.0")
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

            pub fn value() -> u32 { 53 }
            "#,
        )
        .file("cwd-backend-target.json", &target_json)
        .publish();

    let directory = paths::root().join("custom-backend-targets");
    std::fs::create_dir_all(&directory).expect("create isolated custom target directory");
    let target_path = directory.join("ohm-backend-target.json");
    std::fs::write(&target_path, &target_json)
        .expect("write isolated custom target backend specification");

    let manifest = r#"
        [package]
        name = "target-backend-cache-app"
        version = "0.1.0"
        edition = "2021"

        [dependencies]
        target-backend-registry = "1.0.0"
    "#;
    let source = r#"
        #![allow(internal_features)]
        #![feature(no_core, lang_items, auto_traits)]
        #![no_core]

        extern crate target_backend_registry;

        #[lang = "freeze"]
        unsafe auto trait Freeze {}

        pub fn value() -> u32 { target_backend_registry::value() }
    "#;

    for (index, (target, search_path)) in [
        (target_path.display().to_string(), None),
        ("ohm-backend-target".to_owned(), Some(directory.as_path())),
        ("cwd-backend-target".to_owned(), None),
    ]
    .into_iter()
    .enumerate()
    {
        let left = project_in(&format!("target-backend-{index}-left"))
            .file("Cargo.toml", manifest)
            .file("src/lib.rs", source)
            .file("cwd-backend-target.json", &target_json)
            .build();
        let right = project_in(&format!("target-backend-{index}-right"))
            .file("Cargo.toml", manifest)
            .file("src/lib.rs", source)
            .file("cwd-backend-target.json", &target_json)
            .build();
        let shared = paths::root().join(format!("target-backend-shared-{index}"));
        let command =
            format!("-Zohm-shared-registry-cache -Zjson-target-spec build --lib --target {target}");

        for project in [&left, &right] {
            let mut invocation = project.shared_registry_cargo(&command);
            invocation
                .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache", "json-target-spec"])
                .env("CARGO_BUILD_BUILD_DIR", &shared)
                .env("RUSTC_BOOTSTRAP", "1")
                .env("RUSTFLAGS", "-Zunstable-options")
                .with_stderr_contains("[COMPILING] target-backend-registry v1.0.0");
            if let Some(search_path) = search_path {
                invocation.env("RUST_TARGET_PATH", search_path);
            } else {
                invocation.env_remove("RUST_TARGET_PATH");
            }
            invocation.run();
        }
    }

    let left = project_in("builtin-backend-left")
        .file("Cargo.toml", manifest)
        .file("src/lib.rs", source)
        .build();
    let right = project_in("builtin-backend-right")
        .file("Cargo.toml", manifest)
        .file("src/lib.rs", source)
        .build();
    let shared = paths::root().join("builtin-backend-shared");
    let command = format!(
        "-Zohm-shared-registry-cache build --lib --target {}",
        rustc_host()
    );

    left.shared_registry_cargo(&command)
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("RUSTC_BOOTSTRAP", "1")
        .with_stderr_contains("[COMPILING] target-backend-registry v1.0.0")
        .run();
    right
        .shared_registry_cargo(&command)
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("RUSTC_BOOTSTRAP", "1")
        .with_stderr_does_not_contain("[COMPILING] target-backend-registry v1.0.0")
        .run();
}

#[cfg(unix)]
#[cargo_test]
fn shared_registry_cache_rejects_ambient_direct_compiler_shims() {
    Package::new("shimmed-registry", "1.0.0")
        .file(
            "src/lib.rs",
            r#"
                #[cfg(ohm_changed_direct_compiler)]
                compile_error!("the shared compiler shim changed behavior");

                pub fn value() -> u32 { 19 }
            "#,
        )
        .publish();

    let manifest = r#"
        [package]
        name = "compiler-shim-cache-app"
        version = "0.1.0"
        edition = "2021"

        [dependencies]
        shimmed-registry = "1.0.0"
    "#;
    let source = "fn main() { println!(\"{}\", shimmed_registry::value()); }";
    let left = project_in("compiler-shim-left")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .executable(
            "rustc-shim",
            r#"#!/bin/sh
if [ "$OHM_DRIVER_MODE" = "deny" ]; then
    previous=
    for argument in "$@"; do
        if [ "$previous" = "--crate-name" ] && [ "$argument" = "shimmed_registry" ]; then
            exec rustc "$@" --cfg ohm_changed_direct_compiler
        fi
        previous="$argument"
    done
fi
exec rustc "$@"
"#,
        )
        .executable(
            "rustc",
            r#"#!/bin/sh
if [ "$OHM_DRIVER_MODE" = "deny" ]; then
    previous=
    for argument in "$@"; do
        if [ "$previous" = "--crate-name" ] && [ "$argument" = "shimmed_registry" ]; then
            exec "$OHM_GENUINE_RUSTC" "$@" --cfg ohm_changed_direct_compiler
        fi
        previous="$argument"
    done
fi
exec "$OHM_GENUINE_RUSTC" "$@"
"#,
        )
        .build();
    let right = project_in("compiler-shim-right")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .build();
    let shared = paths::root().join("compiler-shim-shared-build-directory");
    let compiler = left.root().join("rustc-shim");

    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("RUSTC", &compiler)
        .env("OHM_DRIVER_MODE", "allow")
        .with_stderr_contains("[COMPILING] shimmed-registry v1.0.0")
        .with_stdout_data("19\n")
        .run();

    right
        .cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("RUSTC", &compiler)
        .env("OHM_DRIVER_MODE", "deny")
        .with_status(101)
        .with_stderr_contains("[COMPILING] shimmed-registry v1.0.0")
        .with_stderr_contains("[ERROR] the shared compiler shim changed behavior")
        .run();

    let inherited_path = std::env::var_os("PATH").expect("available executable search path");
    let configured_path = std::env::join_paths(
        std::iter::once(left.root()).chain(std::env::split_paths(&inherited_path)),
    )
    .expect("prepend the opaque compiler to the configured child executable path");
    let configuration = format!(
        "[env]\nPATH = {{ value = {:?}, force = true }}\n",
        configured_path.to_string_lossy()
    );
    let configured_left = project_in("configured-compiler-shim-left")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .file(".cargo/config.toml", &configuration)
        .build();
    let configured_right = project_in("configured-compiler-shim-right")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .file(".cargo/config.toml", &configuration)
        .build();
    let configured_shared = paths::root().join("configured-compiler-shim-shared-build-directory");
    let genuine_compiler = PathBuf::from(paths::sysroot()).join("bin/rustc");

    configured_left
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &configured_shared)
        .env("RUSTC", "rustc")
        .env("OHM_GENUINE_RUSTC", &genuine_compiler)
        .env("OHM_DRIVER_MODE", "allow")
        .with_stderr_contains("[COMPILING] shimmed-registry v1.0.0")
        .with_stdout_data("19\n")
        .run();
    configured_right
        .cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &configured_shared)
        .env("RUSTC", "rustc")
        .env("OHM_GENUINE_RUSTC", &genuine_compiler)
        .env("OHM_DRIVER_MODE", "deny")
        .with_status(101)
        .with_stderr_contains("[COMPILING] shimmed-registry v1.0.0")
        .with_stderr_contains("[ERROR] the shared compiler shim changed behavior")
        .run();
}

#[cargo_test]
fn shared_registry_cache_shares_authenticated_mirror_macro_closures() {
    let _registry = RegistryBuilder::new().http_index().build();
    let _other_registry = RegistryBuilder::new().alternative().http_index().build();
    let mut helper = Package::new("mirror-macro-helper", "1.0.0");
    helper.file("src/lib.rs", "pub fn value() -> u32 { 23 }");
    let mut macro_package = Package::new("mirror-macro", "1.0.0");
    macro_package
        .proc_macro(true)
        .dep("mirror-macro-helper", "1.0.0")
        .file(
            "src/lib.rs",
            r#"
            extern crate mirror_macro_helper;
            extern crate proc_macro;

            #[proc_macro]
            pub fn value(_: proc_macro::TokenStream) -> proc_macro::TokenStream {
                format!("{}u32", mirror_macro_helper::value()).parse().unwrap()
            }
            "#,
        );
    let mut consumer = Package::new("mirror-consumer", "1.0.0");
    consumer.dep("mirror-macro", "1.0.0").file(
        "src/lib.rs",
        "extern crate mirror_macro; pub fn value() -> u32 { mirror_macro::value!() }",
    );
    for package in [&mut helper, &mut macro_package, &mut consumer] {
        let checksum = package.publish();
        assert_eq!(package.alternative(true).publish(), checksum);
    }

    let create_project = |name: &str, mirror: &str| {
        project_in(name)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "mirror-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                mirror-consumer = "1.0.0"
                "#,
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", mirror_consumer::value()); }",
            )
            .file(
                ".cargo/config.toml",
                &format!("[source.crates-io]\nreplace-with = {mirror:?}\n"),
            )
            .build()
    };
    let shared = paths::root().join("mirror-macro-shared-build-directory");
    for policy in ["audited", "all"] {
        for mirror in ["dummy-registry", "alternative"] {
            for side in ["left", "right"] {
                let project = create_project(&format!("{policy}-{mirror}-{side}"), mirror);
                let mut cargo = project.shared_registry_cargo("-Zohm-shared-registry-cache run");
                cargo
                    .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
                    .env("CARGO_BUILD_BUILD_DIR", &shared)
                    .env("CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST", policy)
                    .with_stdout_data("23\n");
                for package in ["mirror-macro", "mirror-consumer"] {
                    let compiling = format!("[COMPILING] {package} v1.0.0");
                    if side == "left" || policy == "audited" {
                        cargo.with_stderr_contains(&compiling);
                    } else {
                        cargo.with_stderr_does_not_contain(&compiling);
                    }
                }
                // Identical archives from distinct mirrors still have distinct artifact keys.
                if side == "left" {
                    cargo.with_stderr_contains("[COMPILING] mirror-macro-helper v1.0.0");
                } else {
                    cargo.with_stderr_does_not_contain("[COMPILING] mirror-macro-helper v1.0.0");
                }
                cargo.run();
            }
        }
    }

    let project = create_project("mirror-build-to-check", "dummy-registry");
    project
        .shared_registry_cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST", "all")
        .with_stderr_does_not_contain("[COMPILING] mirror-consumer v1.0.0")
        .run();
    project
        .shared_registry_cargo("-Zohm-shared-registry-cache -Zohm-reuse-built-deps check -v")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache", "ohm-reuse-built-deps"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST", "all")
        .with_stderr_contains("[FRESH] mirror-consumer v1.0.0")
        .with_stderr_does_not_contain("[CHECKING] mirror-consumer v1.0.0")
        .run();
}

#[cargo_test]
fn shared_registry_cache_rejects_untrusted_procedural_macro_closures() {
    Package::new("ambient-registry-macro", "1.0.0")
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
                if std::env::var("OHM_SHARED_MACRO_MODE").as_deref() == Ok("deny") {
                    "compile_error!(\"the shared procedural macro observed changed environment\");"
                        .parse()
                        .unwrap()
                } else if std::env::var("OHM_SHARED_MACRO_STATE")
                    .ok()
                    .and_then(|path| std::fs::read_to_string(path).ok())
                    .as_deref()
                    == Some("deny")
                {
                    "compile_error!(\"the shared procedural macro observed changed file\");"
                        .parse()
                        .unwrap()
                } else {
                    input
                }
            }
            "#,
        )
        .publish();
    Package::new("macro-expanded-registry", "1.0.0")
        .dep("ambient-registry-macro", "1.0.0")
        .file(
            "src/lib.rs",
            r#"
            extern crate ambient_registry_macro;

            #[ambient_registry_macro::gate]
            pub fn value() -> u32 { 31 }
            "#,
        )
        .publish();

    let manifest = r#"
        [package]
        name = "shared-macro-cache-app"
        version = "0.1.0"
        edition = "2021"

        [dependencies]
        macro-expanded-registry = "1.0.0"
    "#;
    let source = "fn main() { println!(\"{}\", macro_expanded_registry::value()); }";
    let left = project_in("ambient-macro-left")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .build();
    let right = project_in("ambient-macro-right")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .build();
    let changed_file = project_in("ambient-macro-file")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .build();
    let shared = paths::root().join("ambient-macro-shared-build-directory");
    let state = paths::root().join("ambient-macro-state");
    std::fs::write(&state, "allow").expect("write procedural macro external state");

    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("OHM_SHARED_MACRO_MODE", "allow")
        .env("OHM_SHARED_MACRO_STATE", &state)
        .with_stdout_data("31\n")
        .run();
    right
        .cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("OHM_SHARED_MACRO_MODE", "deny")
        .env("OHM_SHARED_MACRO_STATE", &state)
        .with_status(101)
        .with_stderr_contains("[COMPILING] macro-expanded-registry v1.0.0")
        .with_stderr_contains("[ERROR] the shared procedural macro observed changed environment")
        .run();

    std::fs::write(&state, "deny").expect("change procedural macro external state");
    changed_file
        .cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("OHM_SHARED_MACRO_MODE", "allow")
        .env("OHM_SHARED_MACRO_STATE", &state)
        .with_status(101)
        .with_stderr_contains("[COMPILING] macro-expanded-registry v1.0.0")
        .with_stderr_contains("[ERROR] the shared procedural macro observed changed file")
        .run();
}

#[cfg(unix)]
#[cargo_test]
fn shared_registry_cache_rejects_ambient_rustdoc_wrappers() {
    Package::new("rustdoc-wrapper-registry", "1.0.0")
        .file(
            "build.rs",
            r#"
            fn main() {
                let rustdoc = std::env::var_os("RUSTDOC").unwrap();
                let output = std::process::Command::new(rustdoc).output().unwrap();
                assert!(output.status.success());
                let mode = String::from_utf8(output.stdout).unwrap();
                let directory = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
                std::fs::write(
                    directory.join("generated.rs"),
                    format!("pub const VALUE: &str = {:?};", mode.trim()),
                ).unwrap();
                println!("cargo:rerun-if-changed=build.rs");
            }
            "#,
        )
        .file(
            "src/lib.rs",
            "include!(concat!(env!(\"OUT_DIR\"), \"/generated.rs\"));",
        )
        .publish();

    let manifest = r#"
        [package]
        name = "rustdoc-wrapper-cache-app"
        version = "0.1.0"
        edition = "2021"

        [dependencies]
        rustdoc-wrapper-registry = "1.0.0"
    "#;
    let source = "fn main() { println!(\"{}\", rustdoc_wrapper_registry::VALUE); }";
    let left = project_in("rustdoc-wrapper-left")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .executable(
            "rustdoc-wrapper",
            "#!/bin/sh\nprintf '%s\\n' \"$OHM_RUSTDOC_MODE\"\n",
        )
        .executable(
            "rustdoc",
            "#!/bin/sh\nprintf '%s\\n' \"$OHM_RUSTDOC_MODE\"\n",
        )
        .build();
    let right = project_in("rustdoc-wrapper-right")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .build();
    let shared = paths::root().join("rustdoc-wrapper-shared-build-directory");
    let rustdoc = left.root().join("rustdoc-wrapper");

    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("RUSTDOC", &rustdoc)
        .env("OHM_RUSTDOC_MODE", "left")
        .with_stdout_data("left\n")
        .run();
    right
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("RUSTDOC", &rustdoc)
        .env("OHM_RUSTDOC_MODE", "right")
        .with_stderr_contains("[COMPILING] rustdoc-wrapper-registry v1.0.0")
        .with_stdout_data("right\n")
        .run();

    let inherited_path = std::env::var_os("PATH").expect("available executable search path");
    let intercepted_path = std::env::join_paths(
        std::iter::once(left.root()).chain(std::env::split_paths(&inherited_path)),
    )
    .expect("prepend the isolated fake rustdoc without changing its pathname");
    let intercepted_build = paths::root().join("rustdoc-bare-path-shared-build-directory");

    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &intercepted_build)
        .env("PATH", &intercepted_path)
        .env("RUSTDOC", "rustdoc")
        .env("OHM_RUSTDOC_MODE", "left")
        .with_stderr_contains("[COMPILING] rustdoc-wrapper-registry v1.0.0")
        .with_stdout_data("left\n")
        .run();
    right
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &intercepted_build)
        .env("PATH", &intercepted_path)
        .env("RUSTDOC", "rustdoc")
        .env("OHM_RUSTDOC_MODE", "right")
        .with_stderr_contains("[COMPILING] rustdoc-wrapper-registry v1.0.0")
        .with_stdout_data("right\n")
        .run();

    let configuration = format!(
        "[env]\nPATH = {{ value = {:?}, force = true }}\n",
        intercepted_path.to_string_lossy()
    );
    let configured_left = project_in("rustdoc-configured-path-left")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .file(".cargo/config.toml", &configuration)
        .build();
    let configured_right = project_in("rustdoc-configured-path-right")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .file(".cargo/config.toml", &configuration)
        .build();
    let configured_shared = paths::root().join("rustdoc-configured-path-shared-build-directory");

    configured_left
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &configured_shared)
        .env("RUSTDOC", "rustdoc")
        .env("OHM_RUSTDOC_MODE", "left")
        .with_stderr_contains("[COMPILING] rustdoc-wrapper-registry v1.0.0")
        .with_stdout_data("left\n")
        .run();
    configured_right
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &configured_shared)
        .env("RUSTDOC", "rustdoc")
        .env("OHM_RUSTDOC_MODE", "right")
        .with_stderr_contains("[COMPILING] rustdoc-wrapper-registry v1.0.0")
        .with_stdout_data("right\n")
        .run();
}

#[cfg(unix)]
#[cargo_test]
fn shared_registry_cache_rejects_rustup_proxy_toolchain_changes() {
    Package::new("rustup-dispatch-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 47 }")
        .publish();

    let create_project = |name: &str| {
        project_in(name)
            .file(
                "Cargo.toml",
                r#"
                    [package]
                    name = "rustup-dispatch-app"
                    version = "0.1.0"
                    edition = "2021"

                    [dependencies]
                    rustup-dispatch-registry = "1.0.0"
                "#,
            )
            .file("src/lib.rs", "pub use rustup_dispatch_registry::value;")
            .build()
    };
    let left = create_project("rustup-dispatch-left");
    let right = create_project("rustup-dispatch-right");
    let shared = paths::root().join("rustup-dispatch-shared-build-directory");
    let genuine_compiler = PathBuf::from(paths::sysroot()).join("bin/rustc");

    for (project, toolchain) in [(&left, "stable"), (&right, "nightly")] {
        project
            .cargo("-Zohm-shared-registry-cache build")
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .env("RUSTC", &genuine_compiler)
            .env("RUSTDOC", "rustdoc")
            .env("RUSTUP_TOOLCHAIN", toolchain)
            .with_stderr_contains("[COMPILING] rustup-dispatch-registry v1.0.0")
            .run();
    }
}

#[cfg(windows)]
#[cargo_test]
fn shared_registry_cache_rejects_windows_configuration_environment_aliases() {
    Package::new("windows-environment-alias-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 61 }")
        .publish();

    let inherited_path = std::env::var("PATH").expect("available Windows executable search path");
    let configuration = format!("[env]\nPath = {{ value = {inherited_path:?}, force = true }}\n");
    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "windows-environment-alias-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                windows-environment-alias-registry = "1.0.0"
                "#,
            )
            .file(".cargo/config.toml", &configuration)
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", windows_environment_alias_registry::value()); }",
            )
            .build()
    };
    let left = create_project("windows-environment-alias-left");
    let right = create_project("windows-environment-alias-right");
    let shared = paths::root().join("windows-environment-alias-shared-build-directory");

    for project in [&left, &right] {
        project
            .cargo("-Zohm-shared-registry-cache run")
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .with_stderr_contains("[COMPILING] windows-environment-alias-registry v1.0.0")
            .with_stdout_data("61\n")
            .run();
    }
}

#[cfg(unix)]
#[cargo_test]
fn shared_registry_cache_isolates_only_opaque_native_tool_closures() {
    native_tool_closure_sharing(false);
}

#[cfg(unix)]
#[cargo_test]
fn shared_registry_cache_shares_authenticated_mirror_native_tool_closures() {
    native_tool_closure_sharing(true);
}

/// Exercise strict and permissive sharing with file-backed or HTTP registry replacements.
#[cfg(unix)]
fn native_tool_closure_sharing(http_mirror: bool) {
    let _registry = http_mirror.then(|| RegistryBuilder::new().http_index().build());
    Package::new("cmake", "1.0.0")
        .file(
            "src/lib.rs",
            r#"
            pub fn selected_value() -> String {
                let output = std::process::Command::new("cmake")
                    .output()
                    .expect("run workspace-private native tool");
                assert!(output.status.success());
                String::from_utf8(output.stdout).expect("decode native tool output")
            }
            "#,
        )
        .publish();
    Package::new("unrelated-pure-registry", "1.0.0")
        .file(
            "src/lib.rs",
            "pub fn value() -> &'static str { \"shared\" }",
        )
        .publish();
    for helper in ["cc", "pkg-config", "openssl-src"] {
        Package::new(helper, "1.0.0")
            .file(
                "src/lib.rs",
                "pub fn value() -> &'static str { \"helper\" }",
            )
            .publish();
    }
    Package::new("indirect-native-registry", "1.0.0")
        .build_dep("cmake", "1.0.0")
        .file(
            "build.rs",
            r#"
            fn main() {
                let output = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
                std::fs::write(
                    output.join("generated.rs"),
                    format!("pub const VALUE: &str = {:?};", cmake::selected_value()),
                )
                .unwrap();
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
    Package::new("direct-native-registry", "1.0.0")
        .file(
            "build.rs",
            r#"
            fn main() {
                let selected = std::process::Command::new("cmake").output().unwrap();
                assert!(selected.status.success());
                let output = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
                std::fs::write(
                    output.join("generated.rs"),
                    format!(
                        "pub const VALUE: &str = {:?};",
                        String::from_utf8(selected.stdout).unwrap(),
                    ),
                )
                .unwrap();
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
    Package::new("native-parent-registry", "1.0.0")
        .dep("indirect-native-registry", "1.0.0")
        .file(
            "src/lib.rs",
            "pub fn value() -> &'static str { indirect_native_registry::value() }",
        )
        .publish();

    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "native-tool-closure-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                unrelated-pure-registry = "1.0.0"
                indirect-native-registry = "1.0.0"
                direct-native-registry = "1.0.0"
                native-parent-registry = "1.0.0"
                cc = "1.0.0"
                pkg-config = "1.0.0"
                openssl-src = "1.0.0"
                "#,
            )
            .file(
                "src/main.rs",
                r#"
                fn main() {
                    println!(
                        "{}:{}:{}:{}",
                        unrelated_pure_registry::value(),
                        indirect_native_registry::value(),
                        direct_native_registry::value(),
                        native_parent_registry::value(),
                    );
                }
                "#,
            )
            .build()
    };
    let left = create_project("native-tool-closure-left");
    let right = create_project("native-tool-closure-right");
    let wrapper = project_in("native-tool-closure-wrapper")
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "native-tool-closure-wrapper"
            version = "0.1.0"
            edition = "2021"
            "#,
        )
        .file("src/lib.rs", "")
        .executable(
            "cmake",
            "#!/bin/sh\nprintf '%s' \"$OHM_NATIVE_TOOL_MODE\"\n",
        )
        .executable("nvcc", "#!/bin/sh\nexit 0\n")
        .executable("pkg-config", "#!/bin/sh\nexit 0\n")
        .executable("make", "#!/bin/sh\nexit 0\n")
        .build();
    let inherited_path = std::env::var_os("PATH").expect("native tool executable search path");
    let executable_path = std::env::join_paths(
        std::iter::once(wrapper.root())
            .chain(std::iter::once(
                std::path::PathBuf::from(paths::sysroot()).join("bin"),
            ))
            .chain([
                std::path::PathBuf::from("/usr/bin"),
                std::path::PathBuf::from("/bin"),
            ])
            .chain(std::env::split_paths(&inherited_path)),
    )
    .expect("construct native tool wrapper executable search path");
    let shared = paths::root().join("native-tool-closure-shared-build-directory");

    left.shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("PATH", &executable_path)
        .env("OHM_NATIVE_TOOL_MODE", "left")
        .with_stderr_contains("[COMPILING] unrelated-pure-registry v1.0.0")
        .with_stderr_contains("[COMPILING] cmake v1.0.0")
        .with_stderr_contains("[COMPILING] cc v1.0.0")
        .with_stderr_contains("[COMPILING] pkg-config v1.0.0")
        .with_stderr_contains("[COMPILING] openssl-src v1.0.0")
        .with_stderr_contains("[COMPILING] indirect-native-registry v1.0.0")
        .with_stderr_contains("[COMPILING] direct-native-registry v1.0.0")
        .with_stderr_contains("[COMPILING] native-parent-registry v1.0.0")
        .with_stdout_data("shared:left:left:left\n")
        .run();

    right
        .shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("PATH", &executable_path)
        .env("OHM_NATIVE_TOOL_MODE", "right")
        .with_stderr_does_not_contain("[COMPILING] unrelated-pure-registry v1.0.0")
        .with_stderr_contains("[COMPILING] cmake v1.0.0")
        .with_stderr_contains("[COMPILING] cc v1.0.0")
        .with_stderr_contains("[COMPILING] pkg-config v1.0.0")
        .with_stderr_contains("[COMPILING] openssl-src v1.0.0")
        .with_stderr_contains("[COMPILING] indirect-native-registry v1.0.0")
        .with_stderr_contains("[COMPILING] direct-native-registry v1.0.0")
        .with_stderr_contains("[COMPILING] native-parent-registry v1.0.0")
        .with_stdout_data("shared:right:right:right\n")
        .run();

    // File-backed replacements stay private. Authenticated HTTP mirrors can share build
    // scripts, and `all` additionally shares opaque native helpers and their consumers.
    for (policy, prefix) in [("build-scripts", "scripts"), ("all", "all")] {
        for side in ["left", "right"] {
            let project = create_project(&format!("native-tool-closure-{prefix}-{side}"));
            let selected = format!("{prefix}-{side}");
            let shared_scripts = http_mirror && side == "right";
            let shared_helpers = shared_scripts && policy == "all";
            let direct = if shared_scripts {
                format!("{prefix}-left")
            } else {
                selected.clone()
            };
            let indirect = if shared_helpers {
                format!("{prefix}-left")
            } else {
                selected.clone()
            };
            let expected = format!("shared:{indirect}:{direct}:{indirect}\n");
            let mut cargo = project.shared_registry_cargo("-Zohm-shared-registry-cache run");
            cargo
                .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
                .env("CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST", policy)
                .env("CARGO_BUILD_BUILD_DIR", &shared)
                .env("PATH", &executable_path)
                .env("OHM_NATIVE_TOOL_MODE", &selected)
                .with_stdout_data(&expected);
            for (package, reused) in [
                ("cmake", shared_helpers),
                ("cc", shared_helpers),
                ("pkg-config", shared_helpers),
                ("openssl-src", shared_helpers),
                ("indirect-native-registry", shared_helpers),
                ("direct-native-registry", shared_scripts),
                ("native-parent-registry", shared_helpers),
            ] {
                let compiling = format!("[COMPILING] {package} v1.0.0");
                if reused {
                    cargo.with_stderr_does_not_contain(&compiling);
                } else {
                    cargo.with_stderr_contains(&compiling);
                }
            }
            if side == "left" {
                cargo.with_stderr_contains("[COMPILING] unrelated-pure-registry v1.0.0");
            } else {
                cargo.with_stderr_does_not_contain("[COMPILING] unrelated-pure-registry v1.0.0");
            }
            cargo.run();
        }
    }

    assert!(shared.join("debug/build/registries").is_dir());
    assert!(shared.join("debug/build/workspaces").is_dir());
}

#[cfg(unix)]
#[cargo_test]
fn shared_registry_cache_rejects_ambient_native_compiler_wrappers() {
    Package::new("native-wrapper-registry", "1.0.0")
        .file(
            "build.rs",
            r#"
            fn main() {
                let output = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
                let object = output.join("native.o");
                let library = output.join("libohm_wrapped_native.a");
                let target = std::env::var("TARGET").unwrap().replace(['-', '.'], "_");
                let compiler = std::env::var_os("CC")
                    .or_else(|| std::env::var_os(format!("CC_{target}")))
                    .unwrap_or_else(|| "cc".into());
                assert!(
                    std::process::Command::new(compiler)
                        .args(["-c", "native.c", "-o"])
                        .arg(&object)
                        .status()
                        .unwrap()
                        .success()
                );
                assert!(
                    std::process::Command::new("ar")
                        .arg("crs")
                        .arg(&library)
                        .arg(&object)
                        .status()
                        .unwrap()
                        .success()
                );
                println!("cargo:rustc-link-search=native={}", output.display());
                println!("cargo:rustc-link-lib=static=ohm_wrapped_native");
                println!("cargo:rerun-if-changed=native.c");
                println!("cargo:rerun-if-env-changed=CC");
            }
            "#,
        )
        .file(
            "native.c",
            "unsigned int ohm_wrapped_native_value(void) { return OHM_WRAPPED_VALUE; }",
        )
        .file(
            "src/lib.rs",
            r#"
            extern "C" { fn ohm_wrapped_native_value() -> u32; }
            pub fn value() -> u32 { unsafe { ohm_wrapped_native_value() } }
            "#,
        )
        .publish();

    let manifest = r#"
        [package]
        name = "native-wrapper-cache-app"
        version = "0.1.0"
        edition = "2021"

        [dependencies]
        native-wrapper-registry = "1.0.0"
    "#;
    let source = "fn main() { println!(\"{}\", native_wrapper_registry::value()); }";
    let left = project_in("native-wrapper-left")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .executable(
            "native-wrapper",
            "#!/bin/sh\nexec /usr/bin/cc -DOHM_WRAPPED_VALUE=\"$OHM_NATIVE_MODE\" \"$@\"\n",
        )
        .executable(
            "cc",
            "#!/bin/sh\nexec /usr/bin/cc -DOHM_WRAPPED_VALUE=\"$OHM_NATIVE_MODE\" \"$@\"\n",
        )
        .build();
    let right = project_in("native-wrapper-right")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .build();
    let target_left = project_in("native-wrapper-target-left")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .build();
    let target_right = project_in("native-wrapper-target-right")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .build();
    let shared = paths::root().join("native-wrapper-shared-build-directory");
    let compiler = left.root().join("native-wrapper");

    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("CC", &compiler)
        .env("OHM_NATIVE_MODE", "11")
        .with_stdout_data("11\n")
        .run();
    right
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("CC", &compiler)
        .env("OHM_NATIVE_MODE", "29")
        .with_stderr_contains("[COMPILING] native-wrapper-registry v1.0.0")
        .with_stdout_data("29\n")
        .run();

    let target_compiler = format!("CC_{}", rustc_host().replace(['-', '.'], "_"));
    target_left
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env(&target_compiler, &compiler)
        .env("OHM_NATIVE_MODE", "41")
        .with_stdout_data("41\n")
        .run();
    target_right
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env(&target_compiler, &compiler)
        .env("OHM_NATIVE_MODE", "53")
        .with_stderr_contains("[COMPILING] native-wrapper-registry v1.0.0")
        .with_stdout_data("53\n")
        .run();

    let inherited_path = std::env::var_os("PATH").expect("available executable search path");
    let intercepted_path = std::env::join_paths(
        std::iter::once(left.root()).chain(std::env::split_paths(&inherited_path)),
    )
    .expect("prepend the implicitly selected native compiler");
    let implicit_left = project_in("implicit-native-wrapper-left")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .build();
    let implicit_right = project_in("implicit-native-wrapper-right")
        .file("Cargo.toml", manifest)
        .file("src/main.rs", source)
        .build();
    let implicit_shared = paths::root().join("implicit-native-wrapper-shared-build-directory");

    implicit_left
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &implicit_shared)
        .env("PATH", &intercepted_path)
        .env("OHM_NATIVE_MODE", "67")
        .with_stderr_contains("[COMPILING] native-wrapper-registry v1.0.0")
        .with_stdout_data("67\n")
        .run();
    implicit_right
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &implicit_shared)
        .env("PATH", &intercepted_path)
        .env("OHM_NATIVE_MODE", "83")
        .with_stderr_contains("[COMPILING] native-wrapper-registry v1.0.0")
        .with_stdout_data("83\n")
        .run();
}

#[cfg(unix)]
#[cargo_test]
fn shared_registry_cache_rejects_ambient_external_build_tool_wrappers() {
    Package::new("external-build-tool-registry", "1.0.0")
        .file(
            "build.rs",
            r#"fn main() {
                let name = std::env::var("OHM_NATIVE_BUILD_TOOL").unwrap();
                let executable = std::env::var_os(&name).unwrap();
                let mut command = if name.contains("CROSS_COMPILE") {
                    std::process::Command::new(format!("{}gcc", executable.to_string_lossy()))
                } else if name.contains("CMAKE_TOOLCHAIN_FILE") {
                    let mut command = std::process::Command::new("/bin/sh");
                    command.arg(executable);
                    command
                } else {
                    std::process::Command::new(executable)
                };
                let status = command.status().unwrap();
                assert!(status.success(), "the shared native build tool changed behavior");
            }"#,
        )
        .file("src/lib.rs", "pub fn value() -> u32 { 73 }")
        .publish();

    let manifest = r#"
        [package]
        name = "external-build-tool-cache-app"
        version = "0.1.0"
        edition = "2021"

        [dependencies]
        external-build-tool-registry = "1.0.0"
    "#;
    let source = "pub fn value() -> u32 { external_build_tool_registry::value() }";
    let wrapper_source = "#!/bin/sh\nif [ \"$OHM_NATIVE_TOOL_MODE\" = deny ]; then\n    echo 'the shared native build tool changed behavior' >&2\n    exit 1\nfi\n";
    let wrapper_project = project_in("external-build-tool-wrapper")
        .file("Cargo.toml", manifest)
        .file("src/lib.rs", source)
        .executable("opaque-native-tool", wrapper_source)
        .executable("opaque-native-cross-gcc", wrapper_source)
        .build();
    let wrapper = wrapper_project.root().join("opaque-native-tool");
    let target = rustc_host().replace(['-', '.'], "_");
    let names = [
        "RANLIB".to_owned(),
        "NVCC".to_owned(),
        "CMAKE".to_owned(),
        "EMCMAKE".to_owned(),
        "EMMAKE".to_owned(),
        "PKG_CONFIG".to_owned(),
        "PERL".to_owned(),
        "OPENSSL_SRC_PERL".to_owned(),
        "HOST_RANLIB".to_owned(),
        "TARGET_RANLIB".to_owned(),
        format!("RANLIB_{target}"),
        "CROSS_COMPILE".to_owned(),
        "HOST_CROSS_COMPILE".to_owned(),
        "CMAKE_TOOLCHAIN_FILE".to_owned(),
        format!("CMAKE_TOOLCHAIN_FILE_{target}"),
    ];

    for (index, name) in names.into_iter().enumerate() {
        let left = project_in(&format!("external-build-tool-{index}-left"))
            .file("Cargo.toml", manifest)
            .file("src/lib.rs", source)
            .build();
        let right = project_in(&format!("external-build-tool-{index}-right"))
            .file("Cargo.toml", manifest)
            .file("src/lib.rs", source)
            .build();
        let shared = paths::root().join(format!("external-build-tool-{index}-shared"));
        let executable = if name.contains("CROSS_COMPILE") {
            wrapper_project.root().join("opaque-native-cross-")
        } else {
            wrapper.clone()
        };

        left.cargo("-Zohm-shared-registry-cache build")
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .env(&name, &executable)
            .env("OHM_NATIVE_BUILD_TOOL", &name)
            .env("OHM_NATIVE_TOOL_MODE", "allow")
            .run();
        right
            .cargo("-Zohm-shared-registry-cache build")
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .env(&name, &executable)
            .env("OHM_NATIVE_BUILD_TOOL", &name)
            .env("OHM_NATIVE_TOOL_MODE", "deny")
            .with_status(101)
            .with_stderr_contains("[COMPILING] external-build-tool-registry v1.0.0")
            .with_stderr_contains("[..]the shared native build tool changed behavior[..]")
            .run();
    }
}

#[cfg(unix)]
#[cargo_test]
fn shared_registry_cache_keys_path_selected_native_compilers() {
    Package::new("path-sensitive-native-registry", "1.0.0")
        .file(
            "build.rs",
            r#"
            fn main() {
                let output = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
                let object = output.join("native.o");
                let library = output.join("libohm_path_native.a");
                let compiled = std::process::Command::new("cc")
                    .arg("-c")
                    .arg("native.c")
                    .arg("-o")
                    .arg(&object)
                    .status()
                    .unwrap();
                assert!(compiled.success(), "compile PATH-selected native source");
                let archived = std::process::Command::new("ar")
                    .arg("crs")
                    .arg(&library)
                    .arg(&object)
                    .status()
                    .unwrap();
                assert!(archived.success(), "archive PATH-selected native source");
                println!("cargo:rustc-link-search=native={}", output.display());
                println!("cargo:rustc-link-lib=static=ohm_path_native");
                println!("cargo:rerun-if-changed=native.c");
            }
            "#,
        )
        .file(
            "native.c",
            "unsigned int ohm_path_native_value(void) { return OHM_PATH_VALUE; }",
        )
        .file(
            "src/lib.rs",
            r#"
            extern "C" {
                fn ohm_path_native_value() -> u32;
            }

            pub fn value() -> u32 {
                unsafe { ohm_path_native_value() }
            }
            "#,
        )
        .publish();

    let create_project = |worktree: &str, value: u32| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "path-sensitive-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                path-sensitive-native-registry = "1.0.0"
                "#,
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", path_sensitive_native_registry::value()); }",
            )
            .executable(
                "native-tools/cc",
                &format!(
                    r#"#!/bin/sh
case "$*" in
    *native.c*) exec /usr/bin/cc -DOHM_PATH_VALUE={value} "$@" ;;
    *) exec /usr/bin/cc "$@" ;;
esac
"#,
                ),
            )
            .build()
    };
    let left = create_project("native-path-left", 11);
    let right = create_project("native-path-right", 29);
    let shared = paths::root().join("native-path-shared-build-directory");
    let inherited_path = std::env::var_os("PATH").expect("native compiler executable search path");
    let left_path = std::env::join_paths(
        std::iter::once(left.root().join("native-tools"))
            .chain(std::env::split_paths(&inherited_path)),
    )
    .expect("left native compiler executable search path");
    let right_path = std::env::join_paths(
        std::iter::once(right.root().join("native-tools"))
            .chain(std::env::split_paths(&inherited_path)),
    )
    .expect("right native compiler executable search path");

    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("PATH", &left_path)
        .with_stdout_data("11\n")
        .run();
    right
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("PATH", &right_path)
        .with_stderr_contains("[COMPILING] path-sensitive-native-registry v1.0.0")
        .with_stdout_data("29\n")
        .run();
    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("PATH", &left_path)
        .with_stderr_does_not_contain("[COMPILING] path-sensitive-native-registry v1.0.0")
        .with_stdout_data("11\n")
        .run();
}

#[cargo_test]
fn shared_registry_cache_rejects_injected_dynamic_loaders() {
    Package::new("injected-loader-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 13 }")
        .publish();

    let injection = if cfg!(target_os = "macos") {
        "LD_PRELOAD"
    } else {
        "DYLD_INSERT_LIBRARIES"
    };
    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "loader-injection-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                injected-loader-registry = "1.0.0"
                "#,
            )
            .file(
                ".cargo/config.toml",
                &format!(
                    "[env]\n{injection} = {{ value = \"untrusted-injected-loader\", force = true }}\n"
                ),
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", injected_loader_registry::value()); }",
            )
            .build()
    };
    let left = create_project("loader-injection-left");
    let right = create_project("loader-injection-right");
    let shared = paths::root().join("loader-injection-shared-build-directory");

    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] injected-loader-registry v1.0.0")
        .with_stdout_data("13\n")
        .run();
    right
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] injected-loader-registry v1.0.0")
        .with_stdout_data("13\n")
        .run();
    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[COMPILING] injected-loader-registry v1.0.0")
        .with_stdout_data("13\n")
        .run();
}

#[cargo_test]
fn shared_registry_cache_rejects_alternate_drivers_in_stable_loader_search_paths() {
    Package::new("loader-shadow-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 23 }")
        .publish();

    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "loader-shadow-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                loader-shadow-registry = "1.0.0"
                "#,
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", loader_shadow_registry::value()); }",
            )
            .build()
    };
    let left = create_project("loader-shadow-left");
    let right = create_project("loader-shadow-right");
    let shared = paths::root().join("loader-shadow-shared-build-directory");
    let search = paths::root().join("loader-shadow-search-directory");
    std::fs::create_dir_all(&search).expect("create an initially empty loader search directory");
    let loader = if cfg!(target_os = "macos") {
        "LD_LIBRARY_PATH"
    } else {
        "DYLD_LIBRARY_PATH"
    };

    left.shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env(loader, &search)
        .with_stderr_contains("[COMPILING] loader-shadow-registry v1.0.0")
        .with_stdout_data("23\n")
        .run();
    right
        .shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env(loader, &search)
        .with_stderr_does_not_contain("[COMPILING] loader-shadow-registry v1.0.0")
        .with_stdout_data("23\n")
        .run();

    let alternate = search.join(selected_runtime_compiler_driver_filename());
    std::fs::write(
        &alternate,
        "isolated same-basename compiler-driver stand-in",
    )
    .expect("introduce an alternate compiler driver without changing the search path");

    right
        .shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env(loader, &search)
        .with_stderr_contains("[COMPILING] loader-shadow-registry v1.0.0")
        .with_stdout_data("23\n")
        .run();

    std::fs::remove_file(alternate).expect("remove only the isolated alternate driver");
    left.shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env(loader, &search)
        .with_stderr_does_not_contain("[COMPILING] loader-shadow-registry v1.0.0")
        .with_stdout_data("23\n")
        .run();
}

fn selected_runtime_compiler_driver_filename() -> std::ffi::OsString {
    let sysroot = std::process::Command::new("rustc")
        .args(["--print", "sysroot"])
        .output()
        .expect("query the selected compiler's runtime sysroot");
    assert!(
        sysroot.status.success(),
        "the compiler sysroot must be available"
    );
    let sysroot = String::from_utf8(sysroot.stdout).expect("UTF-8 compiler sysroot");
    let runtime =
        std::path::Path::new(sysroot.trim()).join(if cfg!(windows) { "bin" } else { "lib" });
    let prefix = format!("{DLL_PREFIX}rustc_driver-");

    std::fs::read_dir(runtime)
        .expect("read the selected compiler's runtime directory")
        .filter_map(Result::ok)
        .map(|entry| entry.file_name())
        .find(|filename| {
            filename.to_str().is_some_and(|filename| {
                filename.starts_with(&prefix) && filename.ends_with(DLL_SUFFIX)
            })
        })
        .expect("locate the actual dynamically loaded compiler driver")
}

#[cargo_test]
fn shared_registry_cache_rejects_drivers_in_generated_host_dependency_directories() {
    Package::new("generated-host-driver-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 37 }")
        .publish();

    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "generated-host-driver-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                generated-host-driver-registry = "1.0.0"
                "#,
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", generated_host_driver_registry::value()); }",
            )
            .build()
    };
    let left = create_project("generated-host-driver-left");
    let right = create_project("generated-host-driver-right");
    let shared = paths::root().join("generated-host-driver-shared-build-directory");

    left.shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] generated-host-driver-registry v1.0.0")
        .with_stdout_data("37\n")
        .run();
    right
        .shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[COMPILING] generated-host-driver-registry v1.0.0")
        .with_stdout_data("37\n")
        .run();

    let generated = walkdir::WalkDir::new(shared.join("debug/build/registries"))
        .into_iter()
        .filter_map(Result::ok)
        .find(|entry| {
            entry.file_type().is_dir()
                && entry.file_name() == "out"
                && entry.path().ancestors().any(|ancestor| {
                    ancestor.file_name().is_some_and(|name| {
                        name == std::ffi::OsStr::new("generated-host-driver-registry")
                    })
                })
        })
        .expect("locate the generated registry dependency directory")
        .into_path();
    let alternate = generated.join(selected_runtime_compiler_driver_filename());
    std::fs::write(&alternate, "isolated generated-directory compiler driver")
        .expect("introduce a same-basename driver into Cargo's generated loader path");

    right
        .shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] generated-host-driver-registry v1.0.0")
        .with_stdout_data("37\n")
        .run();
}

#[cfg(target_os = "macos")]
#[cargo_test]
fn shared_registry_cache_uses_inherited_platform_loader_paths_over_forced_configuration() {
    Package::new("configured-loader-driver-registry", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 43 }")
        .publish();

    let inherited = paths::root().join("configured-loader-inherited-search");
    let configured = paths::root().join("configured-loader-ignored-search");
    std::fs::create_dir_all(&inherited).expect("create inherited loader search directory");
    std::fs::create_dir_all(&configured).expect("create ignored configured search directory");
    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "configured-loader-driver-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                configured-loader-driver-registry = "1.0.0"
                "#,
            )
            .file(
                ".cargo/config.toml",
                &format!(
                    "[env]\nDYLD_FALLBACK_LIBRARY_PATH = {{ value = {:?}, force = true }}\n",
                    configured.display().to_string()
                ),
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", configured_loader_driver_registry::value()); }",
            )
            .build()
    };
    let left = create_project("configured-loader-left");
    let right = create_project("configured-loader-right");
    let shared = paths::root().join("configured-loader-shared-build-directory");

    left.shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("DYLD_FALLBACK_LIBRARY_PATH", &inherited)
        .with_stderr_contains("[COMPILING] configured-loader-driver-registry v1.0.0")
        .with_stdout_data("43\n")
        .run();
    right
        .shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("DYLD_FALLBACK_LIBRARY_PATH", &inherited)
        .with_stderr_does_not_contain("[COMPILING] configured-loader-driver-registry v1.0.0")
        .with_stdout_data("43\n")
        .run();

    std::fs::write(
        inherited.join(selected_runtime_compiler_driver_filename()),
        "same-basename driver hidden from forced Cargo configuration",
    )
    .expect("shadow the actual inherited compiler driver");
    right
        .shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("DYLD_FALLBACK_LIBRARY_PATH", &inherited)
        .with_stderr_contains("[COMPILING] configured-loader-driver-registry v1.0.0")
        .with_stdout_data("43\n")
        .run();
}

#[cargo_test]
fn shared_registry_cache_rejects_build_script_compiler_injection() {
    let loader_override = if cfg!(target_os = "macos") {
        "LD_PRELOAD"
    } else {
        "DYLD_INSERT_LIBRARIES"
    };
    Package::new("script-injected-registry", "1.0.0")
        .file(
            "build.rs",
            &format!(
                "fn main() {{ println!(\"cargo:rustc-env={loader_override}=opaque-loader\"); }}"
            ),
        )
        .file("src/lib.rs", "pub fn value() -> u32 { 13 }")
        .publish();

    let project = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "script-injection-cache-app"
            version = "0.1.0"
            edition = "2021"

            [dependencies]
            script-injected-registry = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { script_injected_registry::value() }",
        )
        .build();

    project
        .shared_registry_cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .with_status(101)
        .with_stderr_contains("[ERROR] cannot share registry package [..]")
        .with_stderr_contains(&format!(
            "[..]compiler environment variable `{loader_override}`[..]"
        ))
        .run();
}

#[cargo_test]
fn shared_registry_cache_rejects_build_script_compiler_search_path_overrides() {
    Package::new("script-loader-search-registry", "1.0.0")
        .file(
            "build.rs",
            r#"fn main() {
                let name = std::env::var("OHM_SCRIPT_LOADER_VARIABLE").unwrap();
                let value = std::env::var("OHM_SCRIPT_LOADER_VALUE").unwrap();
                println!("cargo:rerun-if-env-changed=OHM_SCRIPT_LOADER_VARIABLE");
                println!("cargo:rerun-if-env-changed=OHM_SCRIPT_LOADER_VALUE");
                println!("cargo:rustc-env={name}={value}");
            }"#,
        )
        .file("src/lib.rs", "pub fn value() -> u32 { 31 }")
        .publish();

    let project = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "script-loader-search-cache-app"
            version = "0.1.0"
            edition = "2021"

            [dependencies]
            script-loader-search-registry = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { script_loader_search_registry::value() }",
        )
        .build();

    for (name, value) in [
        ("DYLD_LIBRARY_PATH", "/opaque/dynamic-libraries"),
        ("DYLD_FALLBACK_LIBRARY_PATH", "/opaque/dynamic-libraries"),
        ("LD_LIBRARY_PATH", "/opaque/dynamic-libraries"),
        ("PATH", "/opaque/compiler-tools"),
        ("DYLD_LIBRARY_PATH", ""),
        ("PATH", ""),
        ("RUSTC_LOG", "warn"),
        ("RUSTC_LOG_OUTPUT_TARGET", "/opaque/compiler-log"),
    ] {
        project
            .shared_registry_cargo("-Zohm-shared-registry-cache build")
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("OHM_SCRIPT_LOADER_VARIABLE", name)
            .env("OHM_SCRIPT_LOADER_VALUE", value)
            .with_status(101)
            .with_stderr_contains("[ERROR] cannot share registry package [..]")
            .with_stderr_contains(&format!("[..]compiler environment variable `{name}`[..]"))
            .run();
    }
}

#[cargo_test]
#[cfg(unix)]
fn shared_registry_cache_accepts_standard_pthread_linker_arguments() {
    Package::new("pthread-native-registry", "1.0.0")
        .links("pthread_native")
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "pthread-native-registry"
            version = "1.0.0"
            edition = "2021"
            links = "pthread_native"
            "#,
        )
        .file(
            "build.rs",
            r#"fn main() {
                println!("cargo:rustc-link-arg=-pthread");
                println!("cargo:rerun-if-changed=build.rs");
            }"#,
        )
        .file("src/lib.rs", "pub fn value() -> u32 { 73 }")
        .publish();

    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "pthread-native-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                pthread-native-registry = "1.0.0"
                "#,
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", pthread_native_registry::value()); }",
            )
            .build()
    };
    let left = create_project("pthread-native-left");
    let right = create_project("pthread-native-right");
    let shared = paths::root().join("pthread-native-shared-build-directory");

    left.shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] pthread-native-registry v1.0.0")
        .with_stdout_data("73\n")
        .run();
    right
        .shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[COMPILING] pthread-native-registry v1.0.0")
        .with_stdout_data("73\n")
        .run();

    assert!(shared.join("debug/build/registries").is_dir());
}

#[cargo_test]
fn shared_registry_cache_rejects_build_script_opaque_linker_arguments() {
    Package::new("script-linker-registry", "1.0.0")
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "script-linker-registry"
            version = "1.0.0"
            edition = "2021"

            [lib]
            crate-type = ["rlib", "cdylib"]
            "#,
        )
        .file(
            "build.rs",
            r#"fn main() {
                let form = std::env::var("OHM_SCRIPT_LINKER_FORM").unwrap();
                println!("cargo:rerun-if-env-changed=OHM_SCRIPT_LINKER_FORM");
                match form.as_str() {
                    "argument" => println!(
                        "cargo:rustc-link-arg=-fuse-ld=/opaque/compiler-linker-wrapper"
                    ),
                    "pthread-prefix" => println!(
                        "cargo:rustc-link-arg=-pthread=/opaque/compiler-linker-wrapper"
                    ),
                    "pthread-combined" => println!(
                        "cargo:rustc-link-arg=-pthread,-fuse-ld=/opaque/compiler-linker-wrapper"
                    ),
                    "library" => println!("cargo:rustc-link-lib=link-arg=--opaque-linker"),
                    "modifier" => println!(
                        "cargo:rustc-link-lib=link-arg:+verbatim=--opaque-linker"
                    ),
                    "flags" => println!("cargo:rustc-flags=-llink-arg=--opaque-linker"),
                    _ => {}
                }
            }"#,
        )
        .file("src/lib.rs", "pub fn value() -> u32 { 59 }")
        .publish();

    let project = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "script-linker-cache-app"
            version = "0.1.0"
            edition = "2021"

            [dependencies]
            script-linker-registry = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { script_linker_registry::value() }",
        )
        .build();

    for form in [
        "argument",
        "pthread-prefix",
        "pthread-combined",
        "library",
        "modifier",
        "flags",
    ] {
        project
            .shared_registry_cargo("-Zohm-shared-registry-cache build")
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("RUSTC_BOOTSTRAP", "1")
            .env("RUSTFLAGS", "-Zunstable-options")
            .env("OHM_SCRIPT_LINKER_FORM", form)
            .with_status(101)
            .with_stderr_contains("[ERROR] cannot share registry package [..]")
            .with_stderr_contains("[..]opaque compiler linker arguments[..]")
            .run();
    }
}

#[cargo_test]
fn shared_registry_cache_validates_configured_build_script_overrides() {
    Package::new("configured-override-registry", "1.0.0")
        .links("configured_native")
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "configured-override-registry"
                version = "1.0.0"
                edition = "2021"
                links = "configured_native"
            "#,
        )
        .file("build.rs", "this overridden build script is never compiled")
        .file("src/lib.rs", "pub fn value() -> u32 { 67 }")
        .publish();

    let manifest = r#"
        [package]
        name = "configured-override-cache-app"
        version = "0.1.0"
        edition = "2021"

        [dependencies]
        configured-override-registry = "1.0.0"
    "#;
    let source = "fn main() { println!(\"{}\", configured_override_registry::value()); }";
    let safe_configuration = format!(
        "[target.{}.configured_native]\nrustc-env = {{ SAFE_GENERATED_VALUE = \"67\" }}\n",
        rustc_host()
    );
    let left = project_in("configured-override-safe-left")
        .file("Cargo.toml", manifest)
        .file(".cargo/config.toml", &safe_configuration)
        .file("src/main.rs", source)
        .build();
    let right = project_in("configured-override-safe-right")
        .file("Cargo.toml", manifest)
        .file(".cargo/config.toml", &safe_configuration)
        .file("src/main.rs", source)
        .build();
    let shared = paths::root().join("configured-override-safe-shared-build-directory");

    left.shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] configured-override-registry v1.0.0")
        .with_stdout_data("67\n")
        .run();
    right
        .shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[COMPILING] configured-override-registry v1.0.0")
        .with_stdout_data("67\n")
        .run();

    for (index, (configuration, expected)) in [
        (
            r#"rustc-env = { LD_LIBRARY_PATH = "/opaque/compiler-driver" }"#,
            "compiler environment variable `LD_LIBRARY_PATH`",
        ),
        (
            r#"rustc-env = { RUSTC_OVERRIDE_VERSION_STRING = "1.99.0" }"#,
            "compiler environment variable `RUSTC_OVERRIDE_VERSION_STRING`",
        ),
        (
            r#"rustc-link-arg = ["-fuse-ld=/opaque/compiler-linker"]"#,
            "opaque compiler linker arguments",
        ),
        (
            r#"rustc-link-lib = ["link-arg=--opaque-linker"]"#,
            "opaque compiler linker arguments",
        ),
        (
            r#"rustc-link-lib = ["link-arg:+verbatim=--opaque-linker"]"#,
            "opaque compiler linker arguments",
        ),
        (
            r#"rustc-flags = "-llink-arg=--opaque-linker""#,
            "opaque compiler linker arguments",
        ),
    ]
    .into_iter()
    .enumerate()
    {
        let configuration = format!(
            "[target.{}.configured_native]\n{configuration}\n",
            rustc_host()
        );
        let project = project_in(&format!("configured-override-unsafe-{index}"))
            .file("Cargo.toml", manifest)
            .file(".cargo/config.toml", &configuration)
            .file("src/main.rs", source)
            .build();

        project
            .shared_registry_cargo("-Zohm-shared-registry-cache build")
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("RUSTC_BOOTSTRAP", "1")
            .env("RUSTFLAGS", "-Zunstable-options")
            .with_status(101)
            .with_stderr_contains("[ERROR] cannot share registry package [..]")
            .with_stderr_contains(&format!("[..]{expected}[..]"))
            .run();
    }
}

#[cargo_test]
fn shared_registry_cache_rejects_build_script_native_compiler_driver_shadows() {
    Package::new("script-native-driver-registry", "1.0.0")
        .file(
            "build.rs",
            r#"fn main() {
                let directory = std::path::PathBuf::from(
                    std::env::var_os("OUT_DIR").expect("build-script output directory"),
                );
                let driver = std::env::var_os("OHM_EXPECTED_COMPILER_DRIVER")
                    .expect("selected runtime compiler driver filename");
                std::fs::write(directory.join(driver), "isolated alternate compiler driver")
                    .expect("write same-basename build-script compiler driver");
                println!("cargo:rustc-link-search=native={}", directory.display());
            }"#,
        )
        .file("src/lib.rs", "pub fn value() -> u32 { 47 }")
        .publish();

    let project = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "script-native-driver-cache-app"
            version = "0.1.0"
            edition = "2021"

            [dependencies]
            script-native-driver-registry = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { script_native_driver_registry::value() }",
        )
        .build();

    project
        .shared_registry_cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env(
            "OHM_EXPECTED_COMPILER_DRIVER",
            selected_runtime_compiler_driver_filename(),
        )
        .with_status(101)
        .with_stderr_contains("[ERROR] cannot share registry package [..]")
        .with_stderr_contains(
            "[..]build-script library search path[..]alternate compiler driver[..]",
        )
        .run();
}

#[cargo_test]
fn shared_registry_cache_rejects_build_script_compiler_version_overrides() {
    Package::new("script-version-registry", "1.0.0")
        .file(
            "build.rs",
            r#"fn main() {
                println!("cargo:rustc-env=RUSTC_OVERRIDE_VERSION_STRING=1.99.0");
            }"#,
        )
        .file("src/lib.rs", "pub fn value() -> u32 { 17 }")
        .publish();

    let project = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "script-version-cache-app"
            version = "0.1.0"
            edition = "2021"

            [dependencies]
            script-version-registry = "1.0.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { script_version_registry::value() }",
        )
        .build();

    project
        .shared_registry_cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .with_status(101)
        .with_stderr_contains("[ERROR] cannot share registry package [..]")
        .with_stderr_contains(
            "[..]compiler environment variable `RUSTC_OVERRIDE_VERSION_STRING`[..]",
        )
        .run();
}

#[cargo_test]
fn shared_registry_cache_rejects_invalid_lock_ownership_markers() {
    let project = project()
        .file(
            "Cargo.toml",
            "[package]\nname = \"marker-app\"\nversion = \"0.1.0\"\n",
        )
        .file("src/lib.rs", "")
        .build();
    let shared = paths::root().join("invalid-marker-shared-build-directory");
    std::fs::create_dir_all(shared.join(".ohm-shared-registry-cache-v1"))
        .expect("create invalid directory ownership marker");

    project
        .cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_status(101)
        .with_stderr_contains(
            "[ERROR] shared registry cache ownership marker is not a regular file: [..]",
        )
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
            .shared_registry_cargo("-Zohm-shared-registry-cache build")
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .run();
        project
            .shared_registry_cargo("-Zohm-shared-registry-cache build --target")
            .arg(&target)
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .run();
        project
            .shared_registry_cargo("-Zohm-shared-registry-cache build --profile alternate")
            .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
            .env("CARGO_BUILD_BUILD_DIR", &shared)
            .run();
    }

    assert!(shared.join(".ohm-shared-registry-cache-v1").is_file());
    left.shared_registry_cargo("clean")
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
        .shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[COMPILING] [..]")
        .with_stdout_data("7:2\n")
        .run();
    left.shared_registry_cargo("-Zohm-shared-registry-cache run")
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

    left.cargo("clean -p package-clean-local")
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_status(101)
        .with_stderr_contains(
            "[ERROR] cleaning a package in a shared registry build directory requires [..]",
        )
        .run();

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

#[cargo_test]
fn shared_registry_cache_keys_overridden_compiler_versions() {
    Package::new("compiler-version-registry", "1.0.0")
        .file(
            "src/lib.rs",
            r#"
            #![feature(cfg_version)]

            #[cfg(not(version("1.80")))]
            compile_error!("the shared compiler version changed");

            pub fn value() -> u32 { 31 }
            "#,
        )
        .publish();

    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "compiler-version-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                compiler-version-registry = "1.0.0"
                "#,
            )
            .file("src/lib.rs", "pub use compiler_version_registry::value;")
            .build()
    };
    let left = create_project("compiler-version-worktree-left");
    let right = create_project("compiler-version-worktree-right");
    let shared = paths::root().join("compiler-version-shared-build-directory");

    left.cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTC_OVERRIDE_VERSION_STRING", "1.99.0")
        .run();
    right
        .cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTC_OVERRIDE_VERSION_STRING", "1.50.0")
        .with_status(101)
        .with_stderr_contains("[COMPILING] compiler-version-registry v1.0.0")
        .with_stderr_contains("[ERROR] the shared compiler version changed")
        .run();
    left.cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("RUSTC_BOOTSTRAP", "1")
        .env("RUSTC_OVERRIDE_VERSION_STRING", "1.99.0")
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

#[cfg(unix)]
#[cargo_test]
fn shared_registry_cache_rejects_ambient_host_runner_wrappers() {
    Package::new("ambient-runner-registry", "1.0.0")
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

    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "ambient-runner-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                ambient-runner-registry = "1.0.0"
                "#,
            )
            .file(
                ".cargo/config.toml",
                r#"
                target-applies-to-host = false

                [host]
                runner = [
                    "sh",
                    "-c",
                    "OHM_SHARED_HOST_RUNNER=$OHM_RUNNER_MODE \"$@\"",
                    "ohm-host-runner",
                ]
                "#,
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", ambient_runner_registry::RUNNER); }",
            )
            .build()
    };
    let left = create_project("ambient-host-runner-left");
    let right = create_project("ambient-host-runner-right");
    let shared = paths::root().join("ambient-host-runner-shared-build-directory");
    let flags = [
        "ohm-shared-registry-cache",
        "target-applies-to-host",
        "host-config",
    ];
    let command = "-Zohm-shared-registry-cache -Ztarget-applies-to-host -Zhost-config run";

    left.cargo(command)
        .masquerade_as_nightly_cargo(&flags)
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("OHM_RUNNER_MODE", "left")
        .with_stdout_data("left\n")
        .run();
    right
        .cargo(command)
        .masquerade_as_nightly_cargo(&flags)
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("OHM_RUNNER_MODE", "right")
        .with_stderr_contains("[COMPILING] ambient-runner-registry v1.0.0")
        .with_stdout_data("right\n")
        .run();
    left.cargo(command)
        .masquerade_as_nightly_cargo(&flags)
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("OHM_RUNNER_MODE", "left")
        .with_stderr_does_not_contain("[COMPILING] ambient-runner-registry v1.0.0")
        .with_stdout_data("left\n")
        .run();
}

#[cfg(unix)]
#[cargo_test]
fn shared_registry_cache_rejects_ambient_configured_linker_wrappers() {
    Package::new("ambient-linker-registry", "1.0.0")
        .file("build.rs", "fn main() {}")
        .file("src/lib.rs", "pub fn value() -> u32 { 17 }")
        .publish();

    let linker = paths::root()
        .join("ambient-linker-left")
        .join("foo")
        .join("linker-wrapper");
    let config = format!("[target.'cfg(unix)']\nlinker = {linker:?}\n");
    let manifest = r#"
        [package]
        name = "ambient-linker-cache-app"
        version = "0.1.0"
        edition = "2021"

        [dependencies]
        ambient-linker-registry = "1.0.0"
    "#;
    let source = "fn main() { println!(\"{}\", ambient_linker_registry::value()); }";
    let left = project_in("ambient-linker-left")
        .file("Cargo.toml", manifest)
        .file(".cargo/config.toml", &config)
        .file("src/main.rs", source)
        .executable(
            "linker-wrapper",
            r#"#!/bin/sh
if [ "$OHM_LINKER_MODE" = "deny" ]; then
    for argument in "$@"; do
        case "$argument" in
            *ambient-linker-registry*)
                echo 'the ambient linker rejected the registry helper' >&2
                exit 86
                ;;
        esac
    done
fi
exec /usr/bin/cc "$@"
"#,
        )
        .build();
    let right = project_in("ambient-linker-right")
        .file("Cargo.toml", manifest)
        .file(".cargo/config.toml", &config)
        .file("src/main.rs", source)
        .build();
    let shared = paths::root().join("ambient-linker-shared-build-directory");

    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("OHM_LINKER_MODE", "allow")
        .with_stdout_data("17\n")
        .run();
    right
        .cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("OHM_LINKER_MODE", "deny")
        .with_status(101)
        .with_stderr_contains("[COMPILING] ambient-linker-registry v1.0.0")
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

#[cargo_test]
fn shared_registry_cache_preserves_very_verbose_dependency_warnings() {
    Package::new("warning-sensitive-registry", "1.0.0")
        .file(
            "src/lib.rs",
            "pub fn value() -> u32 { let overlooked_warning = 1; 31 }",
        )
        .publish();

    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "warning-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                warning-sensitive-registry = "1.0.0"
                "#,
            )
            .file("src/lib.rs", "pub use warning_sensitive_registry::value;")
            .build()
    };
    let left = create_project("warning-worktree-left");
    let right = create_project("warning-worktree-right");
    let shared = paths::root().join("warning-shared-build-directory");

    left.cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[WARNING] unused variable: `overlooked_warning`")
        .run();
    right
        .cargo("-Zohm-shared-registry-cache build -vv")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_contains("[COMPILING] warning-sensitive-registry v1.0.0")
        .with_stderr_contains("[WARNING] unused variable: `overlooked_warning`")
        .run();
    left.cargo("-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[COMPILING] warning-sensitive-registry v1.0.0")
        .run();
}

#[cargo_test]
fn shared_registry_cache_keys_apple_deployment_targets() {
    Package::new("deployment-sensitive-registry", "1.0.0")
        .file(
            "build.rs",
            r#"
            fn main() {
                let deployment = std::env::var("MACOSX_DEPLOYMENT_TARGET")
                    .expect("inherited Apple deployment target");
                println!("cargo:rustc-env=OBSERVED_APPLE_DEPLOYMENT={deployment}");
                println!("cargo:rerun-if-changed=build.rs");
            }
            "#,
        )
        .file(
            "src/lib.rs",
            "pub const VALUE: &str = env!(\"OBSERVED_APPLE_DEPLOYMENT\");",
        )
        .publish();

    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "deployment-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                deployment-sensitive-registry = "1.0.0"
                "#,
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", deployment_sensitive_registry::VALUE); }",
            )
            .build()
    };
    let left = create_project("deployment-worktree-left");
    let right = create_project("deployment-worktree-right");
    let shared = paths::root().join("deployment-shared-build-directory");

    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("MACOSX_DEPLOYMENT_TARGET", "11.0")
        .with_stdout_data("11.0\n")
        .run();
    right
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("MACOSX_DEPLOYMENT_TARGET", "12.0")
        .with_stderr_contains("[COMPILING] deployment-sensitive-registry v1.0.0")
        .with_stdout_data("12.0\n")
        .run();
    left.cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("MACOSX_DEPLOYMENT_TARGET", "11.0")
        .with_stderr_does_not_contain("[COMPILING] deployment-sensitive-registry v1.0.0")
        .with_stdout_data("11.0\n")
        .run();
}

#[cargo_test]
fn shared_registry_cache_keys_native_sdk_and_dynamic_library_environment() {
    Package::new("native-environment-registry", "1.0.0")
        .file(
            "build.rs",
            r#"
            fn main() {
                let sdk = std::env::var("SDKROOT").expect("inherited SDK root");
                let loader = std::env::var("DYLD_LIBRARY_PATH")
                    .expect("inherited dynamic library search path");
                println!("cargo:rustc-env=OBSERVED_NATIVE_SDK={sdk}");
                println!("cargo:rustc-env=OBSERVED_NATIVE_LOADER={loader}");
                println!("cargo:rerun-if-changed=build.rs");
            }
            "#,
        )
        .file(
            "src/lib.rs",
            r#"
            pub const SDK: &str = env!("OBSERVED_NATIVE_SDK");
            pub const LOADER: &str = env!("OBSERVED_NATIVE_LOADER");
            "#,
        )
        .publish();

    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "native-environment-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                native-environment-registry = "1.0.0"
                "#,
            )
            .file(
                "src/main.rs",
                r#"
                fn main() {
                    println!(
                        "{}:{}",
                        native_environment_registry::SDK,
                        native_environment_registry::LOADER,
                    );
                }
                "#,
            )
            .build()
    };
    let original = create_project("native-environment-original");
    let changed_sdk = create_project("native-environment-sdk");
    let changed_loader = create_project("native-environment-loader");
    let shared = paths::root().join("native-environment-shared-build-directory");

    original
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("SDKROOT", "original-sdk")
        .env("DYLD_LIBRARY_PATH", "original-libraries")
        .with_stdout_data("original-sdk:original-libraries\n")
        .run();
    changed_sdk
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("SDKROOT", "changed-sdk")
        .env("DYLD_LIBRARY_PATH", "original-libraries")
        .with_stderr_contains("[COMPILING] native-environment-registry v1.0.0")
        .with_stdout_data("changed-sdk:original-libraries\n")
        .run();
    changed_loader
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("SDKROOT", "original-sdk")
        .env("DYLD_LIBRARY_PATH", "changed-libraries")
        .with_stderr_contains("[COMPILING] native-environment-registry v1.0.0")
        .with_stdout_data("original-sdk:changed-libraries\n")
        .run();
    original
        .cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .env("SDKROOT", "original-sdk")
        .env("DYLD_LIBRARY_PATH", "original-libraries")
        .with_stderr_does_not_contain("[COMPILING] native-environment-registry v1.0.0")
        .with_stdout_data("original-sdk:original-libraries\n")
        .run();
}

#[cargo_test]
fn shared_registry_cache_loads_native_libraries_from_shared_output() {
    Package::new("dynamic-native-registry", "1.0.0")
        .file(
            "build.rs",
            r##"
            fn main() {
                let output = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
                let source = output.join("native.rs");
                std::fs::write(
                    &source,
                    "#[no_mangle] pub extern \"C\" fn shared_registry_native_value() -> u32 { 37 }",
                )
                .unwrap();
                let library = output.join(format!(
                    "{}shared_registry_native{}",
                    std::env::consts::DLL_PREFIX,
                    std::env::consts::DLL_SUFFIX,
                ));
                let mut compiler = std::process::Command::new(std::env::var_os("RUSTC").unwrap());
                compiler
                    .arg("--crate-type=cdylib")
                    .arg("--edition=2021")
                    .arg("-o")
                    .arg(&library)
                    .arg(&source);
                let library_name = library.file_name().unwrap().to_string_lossy();
                if cfg!(target_os = "macos") {
                    compiler.arg("-C").arg(format!(
                        "link-arg=-Wl,-install_name,@rpath/{library_name}"
                    ));
                } else if cfg!(target_os = "linux") {
                    compiler
                        .arg("-C")
                        .arg(format!("link-arg=-Wl,-soname,{library_name}"));
                }
                let status = compiler.status().unwrap();
                assert!(status.success(), "compile the shared native dependency");
                println!("cargo:rustc-link-search=native={}", output.display());
                println!("cargo:rustc-link-lib=dylib=shared_registry_native");
                println!("cargo:rerun-if-changed=build.rs");
            }
            "##,
        )
        .file(
            "src/lib.rs",
            r#"
            extern "C" {
                fn shared_registry_native_value() -> u32;
            }

            pub fn value() -> u32 {
                unsafe { shared_registry_native_value() }
            }
            "#,
        )
        .publish();

    let create_project = |worktree: &str| {
        project_in(worktree)
            .file(
                "Cargo.toml",
                r#"
                [package]
                name = "dynamic-native-cache-app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                dynamic-native-registry = "1.0.0"
                "#,
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", dynamic_native_registry::value()); }",
            )
            .build()
    };
    let left = create_project("dynamic-native-worktree-left");
    let right = create_project("dynamic-native-worktree-right");
    let shared = paths::root().join("dynamic-native-shared-build-directory");

    left.shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stdout_data("37\n")
        .run();
    right
        .shared_registry_cargo("-Zohm-shared-registry-cache run")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", &shared)
        .with_stderr_does_not_contain("[COMPILING] dynamic-native-registry v1.0.0")
        .with_stdout_data("37\n")
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
