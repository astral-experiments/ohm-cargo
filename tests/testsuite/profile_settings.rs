//! Tests for profiles.

use std::env;

use crate::prelude::*;
use cargo_test_support::registry::Package;
use cargo_test_support::{project, rustc_host, str};

#[cargo_test]
fn profile_overrides() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]

                name = "test"
                version = "0.0.0"
                edition = "2015"
                authors = []

                [profile.dev]
                opt-level = 1
                debug = false
                rpath = true
            "#,
        )
        .file("src/lib.rs", "")
        .build();
    p.cargo("build -v").with_stderr_data(str![[r#"
[COMPILING] test v0.0.0 ([ROOT]/foo)
[RUNNING] `rustc --crate-name test --edition=2015 src/lib.rs [..]--crate-type lib --emit=[..]link[..] -C opt-level=1[..] -C debug-assertions=on[..] -C metadata=[..] -C rpath --out-dir [ROOT]/foo/target/debug/deps [..] -L dependency=[ROOT]/foo/target/debug/deps`
[FINISHED] `dev` profile [optimized] target(s) in [ELAPSED]s

"#]]).run();
}

#[cargo_test]
fn opt_level_override_0() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]

                name = "test"
                version = "0.0.0"
                edition = "2015"
                authors = []

                [profile.dev]
                opt-level = 0
            "#,
        )
        .file("src/lib.rs", "")
        .build();
    p.cargo("build -v").with_stderr_data(str![[r#"
[COMPILING] test v0.0.0 ([ROOT]/foo)
[RUNNING] `rustc --crate-name test --edition=2015 src/lib.rs [..]--crate-type lib --emit=[..]link[..]-C debuginfo=2 [..] -C metadata=[..] --out-dir [ROOT]/foo/target/debug/deps -L dependency=[ROOT]/foo/target/debug/deps`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]).run();
}

#[cargo_test]
fn debug_override_1() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "test"
                version = "0.0.0"
                edition = "2015"
                authors = []

                [profile.dev]
                debug = 1
            "#,
        )
        .file("src/lib.rs", "")
        .build();
    p.cargo("build -v").with_stderr_data(str![[r#"
[COMPILING] test v0.0.0 ([ROOT]/foo)
[RUNNING] `rustc --crate-name test --edition=2015 src/lib.rs [..]--crate-type lib --emit=[..]link[..]-C debuginfo=1 [..]-C metadata=[..] --out-dir [ROOT]/foo/target/debug/deps -L dependency=[ROOT]/foo/target/debug/deps`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]).run();
}

fn check_opt_level_override(profile_level: &str, rustc_level: &str) {
    let p = project()
        .file(
            "Cargo.toml",
            &format!(
                r#"
                    [package]

                    name = "test"
                    version = "0.0.0"
                    edition = "2015"
                    authors = []

                    [profile.dev]
                    opt-level = {level}
                "#,
                level = profile_level
            ),
        )
        .file("src/lib.rs", "")
        .build();
    p.cargo("build -v")
        .with_stderr_data(&format!(
            "\
[COMPILING] test v0.0.0 ([ROOT]/foo)
[RUNNING] `rustc --crate-name test --edition=2015 src/lib.rs [..]--crate-type lib \
        --emit=[..]link \
        -C opt-level={level}[..]\
        -C debuginfo=2 [..]\
        -C debug-assertions=on[..] \
        -C metadata=[..] \
        --out-dir [..] \
        -L dependency=[ROOT]/foo/target/debug/deps`
[FINISHED] `dev` profile [..]+ debuginfo] target(s) in [ELAPSED]s
",
            level = rustc_level
        ))
        .run();
}

#[cargo_test]
fn opt_level_overrides() {
    for &(profile_level, rustc_level) in &[
        ("1", "1"),
        ("2", "2"),
        ("3", "3"),
        ("\"s\"", "s"),
        ("\"z\"", "z"),
    ] {
        check_opt_level_override(profile_level, rustc_level)
    }
}

#[cargo_test]
fn top_level_overrides_deps() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]

                name = "test"
                version = "0.0.0"
                edition = "2015"
                authors = []

                [profile.release]
                opt-level = 1
                debug = true

                [dependencies.foo]
                path = "foo"
            "#,
        )
        .file("src/lib.rs", "")
        .file(
            "foo/Cargo.toml",
            r#"
                [package]

                name = "foo"
                version = "0.0.0"
                edition = "2015"
                authors = []

                [profile.release]
                opt-level = 0
                debug = false

                [lib]
                name = "foo"
                crate-type = ["dylib", "rlib"]
            "#,
        )
        .file("foo/src/lib.rs", "")
        .build();
    p.cargo("build -v --release")
        .with_stderr_data(&format!(
            "\
[LOCKING] 1 package to highest compatible version
[COMPILING] foo v0.0.0 ([ROOT]/foo/foo)
[RUNNING] `rustc --crate-name foo --edition=2015 foo/src/lib.rs [..]\
        --crate-type dylib --crate-type rlib \
        --emit=[..]link \
        -C prefer-dynamic \
        -C opt-level=1[..]\
        -C debuginfo=2 [..]\
        -C metadata=[..] \
        --out-dir [ROOT]/foo/target/release/deps \
        -L dependency=[ROOT]/foo/target/release/deps`
[COMPILING] test v0.0.0 ([ROOT]/foo)
[RUNNING] `rustc --crate-name test --edition=2015 src/lib.rs [..]--crate-type lib \
        --emit=[..]link \
        -C opt-level=1[..]\
        -C debuginfo=2 [..]\
        -C metadata=[..] \
        --out-dir [..] \
        -L dependency=[ROOT]/foo/target/release/deps \
        --extern foo=[ROOT]/foo/target/release/deps/\
                     {prefix}foo[..]{suffix} \
        --extern foo=[ROOT]/foo/target/release/deps/libfoo.rlib`
[FINISHED] `release` profile [optimized + debuginfo] target(s) in [ELAPSED]s
",
            prefix = env::consts::DLL_PREFIX,
            suffix = env::consts::DLL_SUFFIX
        ))
        .run();
}

#[cargo_test]
fn profile_in_non_root_manifest_triggers_a_warning() {
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

                [profile.dev]
                debug = false
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .file(
            "bar/Cargo.toml",
            r#"
                [package]
                name = "bar"
                version = "0.1.0"
                edition = "2015"
                authors = []
                workspace = ".."

                [profile.dev]
                opt-level = 1
            "#,
        )
        .file("bar/src/main.rs", "fn main() {}")
        .build();

    p.cargo("build -v")
        .cwd("bar")
        .with_stderr_data(str![[r#"
[WARNING] profiles for the non root package will be ignored, specify profiles at the workspace root:
package:   [ROOT]/foo/bar/Cargo.toml
workspace: [ROOT]/foo/Cargo.toml
[COMPILING] bar v0.1.0 ([ROOT]/foo/bar)
[RUNNING] `rustc [..]`
[FINISHED] `dev` profile [unoptimized] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn profile_in_virtual_manifest_works() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [workspace]
                members = ["bar"]

                [profile.dev]
                opt-level = 1
                debug = false
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .file(
            "bar/Cargo.toml",
            r#"
                [package]
                name = "bar"
                version = "0.1.0"
                edition = "2015"
                authors = []
                workspace = ".."
            "#,
        )
        .file("bar/src/main.rs", "fn main() {}")
        .build();

    p.cargo("build -v")
        .cwd("bar")
        .with_stderr_data(str![[r#"
[COMPILING] bar v0.1.0 ([ROOT]/foo/bar)
[RUNNING] `rustc [..]`
[FINISHED] `dev` profile [optimized] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn profile_lto_string_bool_dev() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"

                [profile.dev]
                lto = "true"
            "#,
        )
        .file("src/lib.rs", "")
        .build();

    p.cargo("build")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to parse manifest at `[ROOT]/foo/Cargo.toml`

Caused by:
  `lto` setting of string `"true"` for `dev` profile is not a valid setting, must be a boolean (`true`/`false`) or a string (`"thin"`/`"fat"`/`"off"`) or omitted.

"#]])
        .run();
}

#[cargo_test]
fn profile_panic_test_bench() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"

                [profile.test]
                panic = "abort"

                [profile.bench]
                panic = "abort"
            "#,
        )
        .file("src/lib.rs", "")
        .build();

    p.cargo("build")
        .with_stderr_data(str![[r#"
[WARNING] Cargo.toml: `panic` setting is ignored for `bench` profile
[WARNING] Cargo.toml: `panic` setting is ignored for `test` profile
[WARNING] `foo` (manifest) generated 2 warnings
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn profile_doc_deprecated() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"

                [profile.doc]
                opt-level = 0
            "#,
        )
        .file("src/lib.rs", "")
        .build();

    p.cargo("build")
        .with_stderr_data(str![[r#"
[WARNING] Cargo.toml: profile `doc` is deprecated and has no effect
...
"#]])
        .run();
}

#[cargo_test]
fn panic_unwind_does_not_build_twice() {
    // Check for a bug where `lib` was built twice, once with panic set and
    // once without. Since "unwind" is the default, they are the same and
    // should only be built once.
    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "foo"
            version = "0.1.0"
            edition = "2015"

            [profile.dev]
            panic = "unwind"
            "#,
        )
        .file("src/lib.rs", "")
        .file("src/main.rs", "fn main() {}")
        .file("tests/t1.rs", "")
        .build();

    p.cargo("test -v --tests --no-run")
        .with_stderr_data(
            str![[r#"
[COMPILING] foo v0.1.0 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo --edition=2015 src/lib.rs [..]--crate-type lib [..]`
[RUNNING] `rustc --crate-name foo --edition=2015 src/lib.rs [..] --test [..]`
[RUNNING] `rustc --crate-name foo --edition=2015 src/main.rs [..]--crate-type bin [..]`
[RUNNING] `rustc --crate-name foo --edition=2015 src/main.rs [..] --test [..]`
[RUNNING] `rustc --crate-name t1 --edition=2015 tests/t1.rs [..]`
[FINISHED] `test` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[EXECUTABLE] `[ROOT]/foo/target/debug/deps/foo-[HASH][EXE]`
[EXECUTABLE] `[ROOT]/foo/target/debug/deps/foo-[HASH][EXE]`
[EXECUTABLE] `[ROOT]/foo/target/debug/deps/t1-[HASH][EXE]`

"#]]
            .unordered(),
        )
        .run();
}

#[cargo_test]
fn debug_0_report() {
    // The finished line handles 0 correctly.
    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "foo"
            version = "0.1.0"
            edition = "2015"

            [profile.dev]
            debug = 0
            "#,
        )
        .file("src/lib.rs", "")
        .build();

    p.cargo("build -v")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.1.0 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo --edition=2015 src/lib.rs [..]`
[FINISHED] `dev` profile [unoptimized] target(s) in [ELAPSED]s

"#]])
        .with_stderr_does_not_contain("-C debuginfo")
        .run();
}

#[cargo_test]
fn thin_lto_works() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "top"
                version = "0.5.0"
                edition = "2015"
                authors = []

                [profile.release]
                lto = 'thin'
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("build --release -v")
        .with_stderr_data(str![[r#"
[COMPILING] top v0.5.0 ([ROOT]/foo)
[RUNNING] `rustc [..] -C lto=thin [..]`
[FINISHED] `release` profile [optimized] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn strip_works() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2015"

                [profile.release]
                strip = 'symbols'
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("build --release -v")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.1.0 ([ROOT]/foo)
[RUNNING] `rustc [..] -C strip=symbols [..]`
[FINISHED] `release` profile [optimized] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn strip_passes_unknown_option_to_rustc() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2015"

                [profile.release]
                strip = 'unknown'
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("build --release -v")
        .with_status(101)
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.1.0 ([ROOT]/foo)
[RUNNING] `rustc [..] -C strip=unknown [..]`
[ERROR] incorrect value `unknown` for [..] `strip` [..] was expected
...
"#]])
        .run();
}

#[cargo_test]
fn strip_accepts_true_to_strip_symbols() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2015"

                [profile.release]
                strip = true
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("build --release -v")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.1.0 ([ROOT]/foo)
[RUNNING] `rustc [..] -C strip=symbols [..]`
[FINISHED] `release` profile [optimized] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn strip_accepts_false_to_disable_strip() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2015"

                [profile.release]
                strip = false
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("build --release -v")
        .with_stderr_does_not_contain("[RUNNING] `rustc [..] -C strip[..]`")
        .run();
}

#[cargo_test]
fn strip_debuginfo_in_release() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2015"
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("build --release -v")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.1.0 ([ROOT]/foo)
[RUNNING] `rustc [..] -C strip=debuginfo[..]`
[FINISHED] `release` profile [optimized] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("build --release -v --target")
        .arg(rustc_host())
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.1.0 ([ROOT]/foo)
[RUNNING] `rustc [..] -C strip=debuginfo[..]`
[FINISHED] `release` profile [optimized] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn strip_debuginfo_without_debug() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2015"
                
                [profile.dev]
                debug = 0
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("build -v")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.1.0 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..] -C strip=debuginfo[..]`
[FINISHED] `dev` profile [unoptimized] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn do_not_strip_debuginfo_with_requested_debug() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2015"

                [dependencies]
                bar = { path = "bar" }

                [profile.release.package.bar]
                debug = 1
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .file(
            "bar/Cargo.toml",
            r#"
                [package]
                name = "bar"
                version = "0.1.0"
                edition = "2015"
        "#,
        )
        .file("bar/src/lib.rs", "")
        .build();

    p.cargo("build --release -v")
        .with_stderr_does_not_contain("[RUNNING] `rustc [..] -C strip=debuginfo[..]`")
        .run();
}

#[cargo_test]
fn rustflags_works() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
            cargo-features = ["profile-rustflags"]

            [profile.dev]
            rustflags = ["-C", "link-dead-code=yes"]

            [package]
            name = "foo"
            version = "0.0.1"
            edition = "2015"
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("build -v")
        .masquerade_as_nightly_cargo(&["profile-rustflags"])
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..] -C link-dead-code=yes [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn rustflags_works_with_env() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
            cargo-features = ["profile-rustflags"]

            [package]
            name = "foo"
            version = "0.0.1"
            edition = "2015"
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("build -v")
        .env("CARGO_PROFILE_DEV_RUSTFLAGS", "-C link-dead-code=yes")
        .masquerade_as_nightly_cargo(&["profile-rustflags"])
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..] -C link-dead-code=yes [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn rustflags_requires_cargo_feature() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [profile.dev]
                rustflags = ["-C", "link-dead-code=yes"]

                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("build -v")
        .masquerade_as_nightly_cargo(&["profile-rustflags"])
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to parse manifest at `[ROOT]/foo/Cargo.toml`

Caused by:
  feature `profile-rustflags` is required

  The package requires the Cargo feature called `profile-rustflags`, but that feature is not stabilized in this version of Cargo (1.[..]).
  Consider adding `cargo-features = ["profile-rustflags"]` to the top of Cargo.toml (above the [package] table) to tell Cargo you are opting in to use this unstable feature.
  See https://doc.rust-lang.org/nightly/cargo/reference/unstable.html#profile-rustflags-option for more information about the status of this feature.

"#]])
        .run();

    Package::new("bar", "1.0.0").publish();
    p.change_file(
        "Cargo.toml",
        r#"
            [package]
            name = "foo"
            version = "0.0.1"
            edition = "2015"

            [dependencies]
            bar = "1.0"

            [profile.dev.package.bar]
            rustflags = ["-C", "link-dead-code=yes"]
        "#,
    );
    p.cargo("check")
        .masquerade_as_nightly_cargo(&["profile-rustflags"])
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] failed to parse manifest at `[ROOT]/foo/Cargo.toml`

Caused by:
  feature `profile-rustflags` is required

  The package requires the Cargo feature called `profile-rustflags`, but that feature is not stabilized in this version of Cargo (1.[..]).
  Consider adding `cargo-features = ["profile-rustflags"]` to the top of Cargo.toml (above the [package] table) to tell Cargo you are opting in to use this unstable feature.
  See https://doc.rust-lang.org/nightly/cargo/reference/unstable.html#profile-rustflags-option for more information about the status of this feature.

"#]])
        .run();
}

#[cargo_test]
fn debug_options_valid() {
    let build = |option| {
        let p = project()
            .file(
                "Cargo.toml",
                &format!(
                    r#"
                    [package]
                    name = "foo"
                    authors = []
                    version = "0.0.0"
                    edition = "2015"

                    [profile.dev]
                    debug = "{option}"
                "#
                ),
            )
            .file("src/main.rs", "fn main() {}")
            .build();

        p.cargo("build -v")
    };

    for (option, cli) in [
        ("line-directives-only", "line-directives-only"),
        ("line-tables-only", "line-tables-only"),
        ("limited", "1"),
        ("full", "2"),
    ] {
        build(option)
            .with_stderr_data(&format!(
                "\
...
[RUNNING] `rustc [..]-C debuginfo={cli} [..]`
...
"
            ))
            .run();
    }
    build("none")
        .with_stderr_does_not_contain("[..]-C debuginfo[..]")
        .run();
}

#[cargo_test(nightly, reason = "Ohm defaults require the Ohm compiler")]
fn ohm_default_debuginfo() {
    Package::new("bar", "1.0.0").publish();
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2024"
                [dependencies]
                bar = "1"
                [profile.custom]
                inherits = "dev"
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    for defaults in ["yes", "no"] {
        for profile in ["dev", "test", "custom", "release"] {
            let graph = p
                .cargo(&format!(
                    "build --profile {profile} --unit-graph -Zunstable-options -Zohm-defaults={defaults}"
                ))
                .masquerade_as_nightly_cargo(&["unit-graph", "ohm-defaults"])
                .run_json();
            let expected = match (profile, defaults) {
                ("release", _) => serde_json::json!(0),
                (_, "yes") => serde_json::json!("line-tables-only"),
                _ => serde_json::json!(2),
            };
            let units = graph["units"].as_array().unwrap();
            assert_eq!(units.len(), 2);
            for unit in units {
                assert_eq!(unit["profile"]["debuginfo"], expected, "{unit}");
            }
        }
    }
}

#[cargo_test(nightly, reason = "Ohm defaults require the Ohm compiler")]
fn ohm_proc_macro_optimization() {
    Package::new("parser", "1.0.0")
        .file(
            "src/lib.rs",
            r#"
            pub fn debug_settings() -> bool {
                cfg!(debug_assertions) && std::panic::catch_unwind(|| {
                    std::hint::black_box(u8::MAX) + std::hint::black_box(1)
                }).is_err()
            }
        "#,
        )
        .publish();
    Package::new("derive", "1.0.0")
        .edition("2021")
        .proc_macro(true)
        .dep("parser", "1")
        .file(
            "src/lib.rs",
            r#"
            extern crate proc_macro;
            #[proc_macro]
            pub fn debug_settings(_: proc_macro::TokenStream) -> proc_macro::TokenStream {
                (cfg!(debug_assertions) && parser::debug_settings()).to_string().parse().unwrap()
            }
        "#,
        )
        .publish();
    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "app"
            version = "1.0.0"
            edition = "2024"

            [dependencies]
            derive = "1"
            parser = "1"

            [build-dependencies]
            parser = "1"

            [profile.dev-no-lto]
            inherits = "dev"
            lto = "off"
        "#,
        )
        .file(
            "src/main.rs",
            "fn main() { assert!(derive::debug_settings!()); }",
        )
        .file("build.rs", "fn main() {}")
        .build();

    for (defaults, flags, macro_level, macro_lto, parser_levels) in [
        ("yes", "", "1", "off", vec!["0", "1"]),
        ("yes", "--profile dev-no-lto", "1", "off", vec!["0", "1"]),
        ("no", "", "0", "false", vec!["0"]),
        (
            "yes",
            "--config profile.dev.build-override.opt-level=0",
            "0",
            "false",
            vec!["0"],
        ),
        (
            "yes",
            "--config profile.dev.opt-level=0",
            "0",
            "false",
            vec!["0"],
        ),
        (
            "yes",
            "--config profile.dev.build-override.opt-level=1",
            "1",
            "false",
            vec!["0", "1"],
        ),
        (
            "yes",
            "--config profile.dev.lto=false",
            "0",
            "false",
            vec!["0"],
        ),
        (
            "yes",
            "--config profile.dev.package.derive.opt-level=2",
            "2",
            "false",
            vec!["0", "1"],
        ),
        ("yes", "--release", "0", "false", vec!["0", "3"]),
    ] {
        let graph = p
            .cargo(&format!(
                "build --unit-graph -Zunstable-options -Zohm-defaults={defaults} {flags}"
            ))
            .masquerade_as_nightly_cargo(&["unit-graph", "ohm-defaults"])
            .run_json();
        let units = graph["units"].as_array().unwrap();
        let levels = |target: &str| {
            let mut found: Vec<_> = units
                .iter()
                .filter(|u| u["target"]["name"] == target)
                .map(|u| u["profile"]["opt_level"].as_str().unwrap())
                .collect();
            found.sort_unstable();
            found.dedup();
            found
        };
        for unit in units.iter().filter(|u| u["target"]["name"] == "derive") {
            assert_eq!(unit["profile"]["lto"], macro_lto);
        }
        assert_eq!(levels("derive"), [macro_level]);
        assert_eq!(levels("parser"), parser_levels);
        assert_eq!(
            levels("app"),
            [if flags == "--release" { "3" } else { "0" }]
        );
    }

    p.cargo("run -v -Zohm-defaults=yes")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .with_stderr_contains("[..]--crate-name parser [..]-C opt-level=1 [..]-C lto=off [..]")
        .run();
}

#[cargo_test(nightly, reason = "Ohm defaults require the Ohm compiler")]
fn ohm_native_build_dependency_optimization() {
    let script = r#"fn main() {
        println!("cargo:rustc-env=NATIVE_OPT={}", std::env::var("OPT_LEVEL").unwrap());
    }"#;
    let library = r#"pub const OPT: &str = env!("NATIVE_OPT");"#;
    for name in ["shared", "hostonly", "targetonly", "macrodep"] {
        Package::new(name, "1.0.0")
            .links(name)
            .feature("extra", &[])
            .file("Cargo.toml", &format!(
                "[package]\nname = '{name}'\nversion = '1.0.0'\nedition = '2024'\nlinks = '{name}'\n[features]\nextra = []"
            ))
            .file("build.rs", script)
            .file("src/lib.rs", library)
            .publish();
    }
    Package::new("bridge", "1.0.0")
        .edition("2024")
        .dep("shared", "1")
        .dep("hostonly", "1")
        .file(
            "src/lib.rs",
            "pub const OPT: (&str, &str) = (shared::OPT, hostonly::OPT);",
        )
        .publish();
    Package::new("use-native", "1.0.0")
        .edition("2024")
        .proc_macro(true)
        .dep("macrodep", "1")
        .file("src/lib.rs", r#"
            use proc_macro::TokenStream;
            #[proc_macro]
            pub fn level(_: TokenStream) -> TokenStream { format!("{:?}", macrodep::OPT).parse().unwrap() }
        "#)
        .publish();
    let p = project()
        .file(
            "Cargo.toml",
            r#"
        [package]
        name = "app"
        version = "1.0.0"
        edition = "2024"
        [dependencies]
        shared = "1"
        targetonly = "1"
        macrodep = "1"
        use-native = "1"
        [build-dependencies]
        bridge = "1"
        local = { path = "local" }
        [features]
        extra = ["shared/extra"]
        [profile.child]
        inherits = "dev"
    "#,
        )
        .file(
            "local/Cargo.toml",
            r#"
        [package]
        name = "local"
        version = "1.0.0"
        edition = "2024"
        links = "local"
    "#,
        )
        .file("local/build.rs", script)
        .file("local/src/lib.rs", library)
        .file(
            "build.rs",
            r#"fn main() { assert_eq!(bridge::OPT, ("1", "1")); assert_eq!(local::OPT, "0"); }"#,
        )
        .file(
            "src/main.rs",
            r#"fn main() {
                assert_eq!(shared::OPT, "1");
                assert_eq!(targetonly::OPT, "0");
                assert_eq!((use_native::level!(), macrodep::OPT), ("1", "0"));
            }"#,
        )
        .build();

    for (command, defaults, config, shared, hostonly, targetonly) in [
        ("build", "yes", "", vec!["1"], "1", "0"),
        ("check", "yes", "", vec!["1"], "1", "0"),
        (
            "build --features extra",
            "yes",
            "",
            vec!["0", "1"],
            "1",
            "0",
        ),
        ("build --profile child", "yes", "", vec!["1"], "1", "0"),
        ("build", "no", "", vec!["0"], "0", "0"),
        ("build --release", "yes", "", vec!["0", "3"], "0", "3"),
        (
            "build",
            "yes",
            "profile.dev.opt-level=0",
            vec!["0"],
            "0",
            "0",
        ),
        (
            "build --profile child",
            "yes",
            "profile.dev.opt-level=0",
            vec!["0"],
            "0",
            "0",
        ),
        (
            "build",
            "yes",
            "profile.dev.build-override.opt-level=0",
            vec!["0"],
            "0",
            "0",
        ),
        (
            "build",
            "yes",
            "profile.dev.package.shared.opt-level=0",
            vec!["0"],
            "1",
            "0",
        ),
        (
            "build",
            "yes",
            "profile.dev.package.shared.opt-level=2",
            vec!["2"],
            "1",
            "0",
        ),
        (
            "build",
            "yes",
            r#"profile.dev.package."*".opt-level=2"#,
            vec!["2"],
            "2",
            "2",
        ),
        (
            "build --target wasm32-unknown-unknown",
            "yes",
            "",
            vec!["0", "1"],
            "1",
            "0",
        ),
    ] {
        let mut cargo = p.cargo(&format!(
            "{command} --unit-graph -Zunstable-options -Zohm-defaults={defaults}"
        ));
        cargo.masquerade_as_nightly_cargo(&["unit-graph", "ohm-defaults"]);
        if !config.is_empty() {
            cargo.arg("--config").arg(config);
        }
        let graph = cargo.run_json();
        let units = graph["units"].as_array().unwrap();
        let native_runs = |name: &str| {
            let pkg = &units
                .iter()
                .find(|unit| unit["target"]["name"] == name)
                .unwrap()["pkg_id"];
            let mut runs: Vec<_> = units
                .iter()
                .filter(|unit| &unit["pkg_id"] == pkg && unit["mode"] == "run-custom-build")
                .map(|unit| unit["profile"]["opt_level"].as_str().unwrap())
                .collect();
            runs.sort_unstable();
            runs
        };
        assert_eq!(
            native_runs("shared"),
            shared,
            "{command} {defaults} {config}"
        );
        assert_eq!(native_runs("hostonly"), [hostonly]);
        assert_eq!(native_runs("targetonly"), [targetonly]);
        if command == "build" && defaults == "yes" && config.is_empty() {
            // The proc macro's dependency was already optimized. Its final-target copy stays at zero.
            assert_eq!(native_runs("macrodep"), ["0", "1"]);
        }
    }
    p.cargo("run -Zohm-defaults=yes")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .run();
}

#[cargo_test(nightly, reason = "Ohm defaults require the Ohm compiler")]
fn ohm_default_debuginfo_respects_overrides() {
    Package::new("bar", "1.0.0").publish();
    let manifest = r#"
        [package]
        name = "foo"
        version = "0.1.0"
        edition = "2024"
        [dependencies]
        bar = "1"
    "#;
    let p = project()
        .file("Cargo.toml", manifest)
        .file("src/main.rs", "fn main() {}")
        .build();
    let check = |env_debug: Option<&str>, workspace_debug, dependency_debug| {
        let mut cargo = p.cargo("build --unit-graph -Zunstable-options -Zohm-defaults=yes");
        cargo.masquerade_as_nightly_cargo(&["unit-graph", "ohm-defaults"]);
        if let Some(debug) = env_debug {
            cargo.env("CARGO_PROFILE_DEV_DEBUG", debug);
        }
        let graph = cargo.run_json();
        let units = graph["units"].as_array().unwrap();
        assert_eq!(units.len(), 2);
        for unit in units {
            let expected = if unit["target"]["name"] == "foo" {
                &workspace_debug
            } else {
                &dependency_debug
            };
            assert_eq!(&unit["profile"]["debuginfo"], expected, "{unit}");
        }
    };

    p.change_file(
        "Cargo.toml",
        &format!("{manifest}\n[profile.dev]\ndebug = true"),
    );
    check(None, serde_json::json!(2), serde_json::json!(2));

    p.change_file(".cargo/config.toml", "[profile.dev]\ndebug = 1");
    check(None, serde_json::json!(1), serde_json::json!(1));
    check(Some("0"), serde_json::json!(0), serde_json::json!(0));
    check(Some("2"), serde_json::json!(2), serde_json::json!(2));

    p.change_file(".cargo/config.toml", "");
    p.change_file(
        "Cargo.toml",
        &format!("{manifest}\n[profile.dev.package.'*']\ndebug = false"),
    );
    check(
        None,
        serde_json::json!("line-tables-only"),
        serde_json::json!(0),
    );
}

#[cfg(all(target_arch = "x86_64", target_os = "linux", target_env = "gnu"))]
#[cargo_test(nightly, reason = "Ohm defaults require the Ohm compiler")]
fn ohm_native_dev_line_tables() {
    let p = project().file("src/lib.rs", "pub fn answer() {}").build();
    for (defaults, profile, debug, split, target, expected) in [
        (
            "yes",
            "dev",
            "line-tables-only",
            None,
            None,
            Some("unpacked"),
        ),
        (
            "yes",
            "test",
            "line-tables-only",
            None,
            None,
            Some("unpacked"),
        ),
        (
            "yes",
            "dev",
            "line-tables-only",
            Some("off"),
            None,
            Some("off"),
        ),
        ("yes", "dev", "full", None, None, None),
        ("yes", "release", "line-tables-only", None, None, None),
        ("no", "dev", "line-tables-only", None, None, None),
        (
            "yes",
            "dev",
            "line-tables-only",
            None,
            Some("x86_64-pc-windows-msvc"),
            None,
        ),
    ] {
        let mut cmd = p.cargo(&format!(
            "build --profile {profile} --unit-graph -Zunstable-options -Zohm-defaults={defaults}"
        ));
        cmd.masquerade_as_nightly_cargo(&["unit-graph", "ohm-defaults"])
            .env("CARGO_PROFILE_DEV_DEBUG", debug)
            .env("CARGO_PROFILE_RELEASE_DEBUG", debug);
        if let Some(split) = split {
            cmd.env("CARGO_PROFILE_DEV_SPLIT_DEBUGINFO", split);
        }
        if let Some(target) = target {
            cmd.arg("--target").arg(target);
        }
        let graph = cmd.run_json();
        assert_eq!(
            graph["units"][0]["profile"]["split_debuginfo"],
            serde_json::json!(expected)
        );
    }
    p.change_file("src/main.rs", "fn main() {}");
    let graph = p
        .cargo("test --no-run --unit-graph -Zunstable-options -Zohm-defaults=yes")
        .masquerade_as_nightly_cargo(&["unit-graph", "ohm-defaults"])
        .run_json();
    let mut library = false;
    let mut harness = false;
    for unit in graph["units"].as_array().unwrap() {
        let rlib = unit["mode"] == "build" && unit["target"]["kind"] == serde_json::json!(["lib"]);
        library |= rlib;
        harness |= unit["mode"] == "test";
        assert_eq!(
            unit["profile"]["split_debuginfo"],
            serde_json::json!(rlib.then_some("unpacked"))
        );
    }
    assert!(library && harness);
}

#[cargo_test]
fn profile_hint_mostly_unused_warn_without_gate() {
    Package::new("bar", "1.0.0").publish();
    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "foo"
            version = "0.0.1"
            edition = "2015"

            [dependencies]
            bar = "1.0"

            [profile.dev.package.bar]
            hint-mostly-unused = true
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();
    p.cargo("check -v")
        .with_stderr_data(str![[r#"
[UPDATING] `dummy-registry` index
[LOCKING] 1 package to highest compatible version
[DOWNLOADING] crates ...
[DOWNLOADED] bar v1.0.0 (registry `dummy-registry`)
[WARNING] bar@1.0.0: ignoring 'hint-mostly-unused' profile option, pass `-Zprofile-hint-mostly-unused` to enable it
[CHECKING] bar v1.0.0
[RUNNING] `rustc --crate-name bar [..]`
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .with_stderr_does_not_contain("-Zhint-mostly-unused")
        .run();
}

#[cargo_test(nightly, reason = "-Zhint-mostly-unused is unstable")]
fn profile_hint_mostly_unused_nightly() {
    Package::new("bar", "1.0.0").publish();
    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "foo"
            version = "0.0.1"
            edition = "2015"

            [dependencies]
            bar = "1.0"

            [profile.dev.package.bar]
            hint-mostly-unused = true
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();
    p.cargo("check -Zprofile-hint-mostly-unused -v")
        .masquerade_as_nightly_cargo(&["profile-hint-mostly-unused"])
        .with_stderr_data(str![[r#"
[UPDATING] `dummy-registry` index
[LOCKING] 1 package to highest compatible version
[DOWNLOADING] crates ...
[DOWNLOADED] bar v1.0.0 (registry `dummy-registry`)
[CHECKING] bar v1.0.0
[RUNNING] `rustc --crate-name bar [..] -Zhint-mostly-unused [..]`
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .with_stderr_does_not_contain(
            "[RUNNING] `rustc --crate-name foo [..] -Zhint-mostly-unused [..]",
        )
        .run();
}
