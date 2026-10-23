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

#[cargo_test(nightly, reason = "unit-graph and Ohm defaults are unstable")]
fn ohm_proc_macro_helper_profiles() {
    let manifest = r#"
        [package]
        name = "app"
        version = "0.1.0"
        edition = "2024"
        [workspace]
        members = ["macros", "nested", "helper", "leaf", "script_helper"]
        resolver = "2"
        [dependencies]
        macros = { path = "macros" }
        [build-dependencies]
        script_helper = { path = "script_helper" }
        [profile.dev]
        opt-level = 2
        [profile.custom]
        inherits = "dev"
        [profile.custom-release]
        inherits = "release"
        opt-level = 2
    "#;
    let p = project()
        .file("Cargo.toml", manifest)
        .file("src/lib.rs", "")
        .file("build.rs", "fn main() {}")
        .file(
            "macros/Cargo.toml",
            r#"
            [package]
            name = "macros"
            version = "0.1.0"
            edition = "2024"
            [lib]
            proc-macro = true
            [dependencies]
            helper = { path = "../helper" }
            nested = { path = "../nested" }
        "#,
        )
        .file("macros/src/lib.rs", "")
        .file(
            "nested/Cargo.toml",
            r#"
            [package]
            name = "nested"
            version = "0.1.0"
            edition = "2024"
            [lib]
            proc-macro = true
            [dependencies]
            leaf = { path = "../leaf" }
        "#,
        )
        .file("nested/src/lib.rs", "")
        .file(
            "helper/Cargo.toml",
            r#"
            [package]
            name = "helper"
            version = "0.1.0"
            edition = "2024"
            [dependencies]
            leaf = { path = "../leaf" }
            [build-dependencies]
            script_helper = { path = "../script_helper" }
        "#,
        )
        .file("helper/src/lib.rs", "")
        .file("helper/src/main.rs", "fn main() {}")
        .file("helper/build.rs", "fn main() {}")
        .file(
            "leaf/Cargo.toml",
            "[package]\nname='leaf'\nversion='0.1.0'\nedition='2024'\n",
        )
        .file("leaf/src/lib.rs", "")
        .file(
            "script_helper/Cargo.toml",
            "[package]\nname='script_helper'\nversion='0.1.0'\nedition='2024'\n",
        )
        .file("script_helper/src/lib.rs", "")
        .build();
    let graph = |args: &str, configs: &[&str], env_opt: Option<&str>| {
        let mut cargo = p.cargo(&format!("build {args} --unit-graph -Zunstable-options"));
        cargo.masquerade_as_nightly_cargo(&["unit-graph", "ohm-defaults", "bindeps"]);
        for config in configs {
            cargo.arg("--config").arg(config);
        }
        if let Some(opt) = env_opt {
            cargo.env("CARGO_PROFILE_DEV_OPT_LEVEL", opt);
        }
        cargo.run_json()
    };
    let check = |args: &str,
                 configs: &[&str],
                 env_opt: Option<&str>,
                 helper: &str,
                 leaf: &str,
                 host: &str| {
        let g = graph(args, configs, env_opt);
        let mut seen = std::collections::BTreeSet::new();
        for u in g["units"].as_array().unwrap() {
            let name = u["target"]["name"].as_str().unwrap();
            if u["mode"] == "run-custom-build" || name == "app" {
                continue;
            }
            let expected = match name {
                "helper" => helper,
                "leaf" => leaf,
                "macros" | "nested" | "script_helper" | "build-script-build" => host,
                _ => panic!("unexpected unit {u}"),
            };
            assert_eq!(u["profile"]["opt_level"].as_str(), Some(expected), "{u}");
            seen.insert(name.to_owned());
        }
        assert!(
            seen.contains("helper")
                && seen.contains("leaf")
                && seen.contains("macros")
                && seen.contains("nested")
                && seen.contains("script_helper")
        );
    };
    check("-p app -Zohm-defaults=yes", &[], None, "2", "2", "0");
    check(
        "-p app --profile test -Zohm-defaults=yes",
        &[],
        None,
        "2",
        "2",
        "0",
    );
    check(
        "-p app --profile custom -Zohm-defaults=yes",
        &[],
        None,
        "2",
        "2",
        "0",
    );
    check("-p app -Zohm-defaults=no", &[], None, "0", "0", "0");
    check(
        "-p app --release -Zohm-defaults=yes",
        &[],
        None,
        "0",
        "0",
        "0",
    );
    check(
        "-p app --profile custom-release -Zohm-defaults=yes",
        &[],
        None,
        "0",
        "0",
        "0",
    );
    check(
        "-p app -Zohm-defaults=yes",
        &["profile.dev.opt-level=1"],
        None,
        "1",
        "1",
        "0",
    );
    check(
        "-p app -Zohm-defaults=yes",
        &["profile.dev.build-override.opt-level=1"],
        None,
        "1",
        "1",
        "1",
    );
    check(
        "-p app -Zohm-defaults=yes",
        &["profile.dev.package.helper.opt-level=0"],
        None,
        "0",
        "2",
        "0",
    );
    check(
        "-p app -Zohm-defaults=yes",
        &["profile.dev.package.leaf.opt-level=0"],
        None,
        "2",
        "0",
        "0",
    );
    check(
        "-p app -Zohm-defaults=yes",
        &[
            "profile.dev.build-override.opt-level=1",
            "profile.dev.package.leaf.opt-level=0",
        ],
        None,
        "1",
        "0",
        "1",
    );
    check(
        &format!("-p app --target {} -Zohm-defaults=yes", rustc_host()),
        &[],
        None,
        "2",
        "2",
        "0",
    );
    // A proc-macro selected as a root already uses the dev profile itself.
    let direct = graph("-p macros -Zohm-defaults=yes", &[], None);
    for u in direct["units"].as_array().unwrap() {
        if u["target"]["name"] == "macros"
            || u["target"]["name"] == "helper"
            || u["target"]["name"] == "leaf"
        {
            assert_eq!(u["profile"]["opt_level"], "2", "{u}");
        }
        if u["target"]["name"] == "nested" {
            assert_eq!(u["profile"]["opt_level"], "0");
        }
    }
    p.change_file("Cargo.toml", &manifest.replace("opt-level = 2", ""));
    check("-p app -Zohm-defaults=yes", &[], None, "0", "0", "0");
    check("-p app -Zohm-defaults=yes", &[], Some("3"), "3", "3", "0");
    // Runtime debug-info matching and final graph sharing must still work.
    p.change_file(
        "Cargo.toml",
        &manifest.replace(
            "macros = { path = \"macros\" }",
            "macros = { path = \"macros\" }\nhelper = { path = \"helper\" }",
        ),
    );
    let shared = graph("-p app -Zohm-defaults=yes", &[], None);
    let helpers: Vec<_> = shared["units"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|u| u["target"]["name"] == "helper")
        .collect();
    assert_eq!(helpers.len(), 1, "{shared}");
    assert_eq!(helpers[0]["profile"]["opt_level"], "2");
    // Artifact binaries and their ordinary library edges keep the old host defaults.
    p.change_file(
        "Cargo.toml",
        &manifest.replace(
            "script_helper = { path = \"script_helper\" }",
            "helper = { path = \"helper\", artifact = \"bin\" }",
        ),
    );
    let artifacts = graph("-p app -Zohm-defaults=yes -Zbindeps", &[], None);
    let mut saw_bin = false;
    for u in artifacts["units"].as_array().unwrap() {
        if u["target"]["kind"] == serde_json::json!(["bin"]) {
            saw_bin = true;
            assert_eq!(u["profile"]["opt_level"], "0", "{u}");
        }
    }
    assert!(saw_bin);
}

#[cargo_test(nightly, reason = "unit-graph and Ohm defaults are unstable")]
fn ohm_proc_macro_helper_build_script_origins() {
    let p = project()
        .file("Cargo.toml", r#"
            [package]
            name = "app"
            version = "0.1.0"
            edition = "2024"
            [workspace]
            members = ["macros", "helper", "leaf"]
            resolver = "2"
            [dependencies]
            macros = { path = "macros" }
            [build-dependencies]
            helper = { path = "helper" }
            [profile.dev]
            opt-level = 2
            [profile.dev.package.helper]
            opt-level = 0
        "#)
        .file("src/main.rs", "macros::value!(); fn main() { assert_eq!(MACRO_LEVEL, \"2\"); }")
        .file("build.rs", "fn main() { assert_eq!(helper::leaf_level(), \"0\"); assert_eq!(helper::own_level(), \"0\"); }")
        .file("macros/Cargo.toml", r#"
            [package]
            name = "macros"
            version = "0.1.0"
            edition = "2024"
            [lib]
            proc-macro = true
            [dependencies]
            helper = { path = "../helper" }
        "#)
        .file("macros/src/lib.rs", r#"
            extern crate proc_macro;
            #[proc_macro]
            pub fn value(_: proc_macro::TokenStream) -> proc_macro::TokenStream {
                assert_eq!(helper::own_level(), "0");
                format!("pub const MACRO_LEVEL: &str = {:?};", helper::leaf_level()).parse().unwrap()
            }
        "#)
        .file("helper/Cargo.toml", r#"
            [package]
            name = "helper"
            version = "0.1.0"
            edition = "2024"
            [dependencies]
            leaf = { path = "../leaf" }
        "#)
        .file("helper/src/lib.rs", "pub fn leaf_level() -> &'static str { env!(\"LEAF_LEVEL\") } pub fn own_level() -> &'static str { env!(\"OWN_LEVEL\") }")
        .file("helper/build.rs", r#"
            fn main() {
                println!("cargo:rustc-env=LEAF_LEVEL={}", std::env::var("DEP_LEAF_LINK_LEVEL").unwrap());
                println!("cargo:rustc-env=OWN_LEVEL={}", std::env::var("OPT_LEVEL").unwrap());
            }
        "#)
        .file("leaf/Cargo.toml", "[package]\nname='leaf'\nversion='0.1.0'\nedition='2024'\nlinks='leaf_link'\n")
        .file("leaf/src/lib.rs", "")
        .file("leaf/build.rs", "fn main() { println!(\"cargo:level={}\", std::env::var(\"OPT_LEVEL\").unwrap()); }")
        .build();
    let graph = |args: &str| {
        p.cargo(&format!(
            "build {args} --unit-graph -Zunstable-options -Zohm-defaults=yes"
        ))
        .masquerade_as_nightly_cargo(&["unit-graph", "ohm-defaults"])
        .run_json()
    };
    let check = |g: &serde_json::Value, variants: usize| {
        let units = g["units"].as_array().unwrap();
        let helpers: Vec<_> = units
            .iter()
            .filter(|u| u["target"]["name"] == "helper")
            .collect();
        assert_eq!(helpers.len(), variants, "{g}");
        let helper_id = &helpers[0]["pkg_id"];
        let compiled_scripts: Vec<_> = units
            .iter()
            .filter(|u| {
                &u["pkg_id"] == helper_id
                    && u["target"]["kind"] == serde_json::json!(["custom-build"])
                    && u["mode"] != "run-custom-build"
            })
            .collect();
        assert_eq!(compiled_scripts.len(), 1, "{g}");
        assert_eq!(compiled_scripts[0]["profile"]["opt_level"], "0");
        for helper in helpers {
            assert_eq!(helper["profile"]["opt_level"], "0");
            let deps: Vec<_> = helper["dependencies"]
                .as_array()
                .unwrap()
                .iter()
                .map(|d| &units[d["index"].as_u64().unwrap() as usize])
                .collect();
            let leaf = deps.iter().find(|u| u["target"]["name"] == "leaf").unwrap();
            let run = deps
                .iter()
                .find(|u| u["mode"] == "run-custom-build")
                .unwrap();
            assert_eq!(run["profile"]["opt_level"], helper["profile"]["opt_level"]);
            let leaf_runs: Vec<_> = run["dependencies"]
                .as_array()
                .unwrap()
                .iter()
                .map(|d| &units[d["index"].as_u64().unwrap() as usize])
                .filter(|u| u["mode"] == "run-custom-build")
                .collect();
            assert_eq!(leaf_runs.len(), 1, "{run}");
            assert_eq!(
                leaf_runs[0]["profile"]["opt_level"],
                leaf["profile"]["opt_level"]
            );
        }
    };
    check(&graph("-p app"), 2);
    let first = graph("-p app -p macros");
    let reverse = graph("-p macros -p app");
    check(&first, 2);
    check(&reverse, 2);
    let signatures = |g: &serde_json::Value| {
        let mut rows: Vec<_> = g["units"]
            .as_array()
            .unwrap()
            .iter()
            .map(|u| {
                let mut row = u.clone();
                row.as_object_mut().unwrap().remove("dependencies");
                row.to_string()
            })
            .collect();
        rows.sort();
        rows
    };
    assert_eq!(signatures(&first), signatures(&reverse));
    // A leaf override makes both complete closures equal, so the final pass shares them.
    check(
        &graph("-p app --config profile.dev.package.leaf.opt-level=0"),
        1,
    );
    // This executes both build-script metadata branches and the proc macro.
    p.cargo("run -p app -Zohm-defaults=yes")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .run();
}
