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
[RUNNING] `rustc --crate-name test --edition=2015 src/lib.rs [..]--crate-type lib --emit=[..]link[..] -C opt-level=1[..] -C debug-assertions=on[..] -C metadata=[..] -C rpath --out-dir [..]`
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
[RUNNING] `rustc --crate-name test --edition=2015 src/lib.rs [..]--crate-type lib --emit=[..]link[..]-C debuginfo=2 [..] -C metadata=[..] --out-dir [..]`
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
[RUNNING] `rustc --crate-name test --edition=2015 src/lib.rs [..]--crate-type lib --emit=[..]link[..]-C debuginfo=1 [..]-C metadata=[..] --out-dir [..]`
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
        --emit=[..]link[..] \
        -C opt-level={level}[..]\
        -C debuginfo=2 [..]\
        -C debug-assertions=on[..] \
        -C metadata=[..] \
        --out-dir [..]`
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

                [lints.cargo]
                default = "allow"
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

                [lints.cargo]
                default = "allow"
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
        --emit=[..]link[..] \
        -C prefer-dynamic \
        -C opt-level=1[..]\
        -C debuginfo=2 [..]\
        -C metadata=[..] \
        --out-dir [ROOT]/foo/target/release/build/foo/[HASH]/out[..]`
[COMPILING] test v0.0.0 ([ROOT]/foo)
[RUNNING] `rustc --crate-name test --edition=2015 src/lib.rs [..]--crate-type lib \
        --emit=[..]link[..] \
        -C opt-level=1[..]\
        -C debuginfo=2 [..]\
        -C metadata=[..] \
        --out-dir [..] \
        --extern foo=[ROOT]/foo/target/release/build/foo/[HASH]/out/\
                     {prefix}foo[..]{suffix} \
        --extern foo=[ROOT]/foo/target/release/build/foo/[HASH]/out/libfoo.rlib[..]`
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
[EXECUTABLE] `[ROOT]/foo/target/debug/build/foo/[HASH]/out/foo-[HASH][EXE]`
[EXECUTABLE] `[ROOT]/foo/target/debug/build/foo/[HASH]/out/foo-[HASH][EXE]`
[EXECUTABLE] `[ROOT]/foo/target/debug/build/foo/[HASH]/out/t1-[HASH][EXE]`

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
[RUNNING] `rustc [..] -C strip=symbols[..]`
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
[RUNNING] `rustc [..] -C strip=unknown[..]`
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
[RUNNING] `rustc [..] -C strip=symbols[..]`
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
fn ohm_proc_macro_helpers() {
    Package::new("leaf", "1.0.0")
        .file("src/lib.rs", "pub struct Number(pub u8);")
        .publish();
    Package::new("helper", "1.0.0")
        .dep("leaf", "1")
        .file("src/lib.rs", "extern crate leaf; pub use leaf::Number;")
        .publish();
    let manifest = r#"
        [package]
        name = "foo"
        version = "0.1.0"
        edition = "2024"

        [dependencies]
        macros = { path = "macros" }
        helper = "1"

        [profile.custom]
        inherits = "dev"

        [profile.dev]
        opt-level = 1
        lto = "off"
    "#;
    let p = project()
        .file("Cargo.toml", manifest)
        .file("src/lib.rs", "const _: [(); 42] = [(); macros::number!()];")
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
                local = { path = "../local" }
                leaf = "1"

                [build-dependencies]
                local = { path = "../local" }
                leaf = "1"
            "#,
        )
        .file(
            "macros/src/lib.rs",
            r#"
                use proc_macro::TokenStream;

                #[proc_macro]
                pub fn number(_: TokenStream) -> TokenStream {
                    let number: leaf::Number = local::number();
                    number.0.to_string().parse().unwrap()
                }
            "#,
        )
        .file(
            "macros/build.rs",
            "fn main() { let _: leaf::Number = local::number(); }",
        )
        .file(
            "local/Cargo.toml",
            r#"
                [package]
                name = "local"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                helper = "1"
            "#,
        )
        .file(
            "local/src/lib.rs",
            "pub fn number() -> helper::Number { helper::Number(42) }",
        )
        .build();

    let check = |defaults: &str, profile: &str, settings: &str, expected: &[&str]| {
        p.change_file("Cargo.toml", &format!("{manifest}\n{settings}"));
        let graph = p
            .cargo(&format!(
                "build --profile {profile} --unit-graph -Zunstable-options -Zohm-defaults={defaults}"
            ))
            .masquerade_as_nightly_cargo(&["unit-graph", "ohm-defaults"])
            .run_json();
        let units = graph["units"].as_array().unwrap();
        let mut marked = Vec::new();
        for unit in units {
            if let Some(flags) = unit["profile"]["rustflags"].as_array() {
                assert_eq!(
                    flags,
                    &["-Zllvm-module-flag=ohm.proc-macro-helper:u32:1:max"]
                );
                assert_eq!(unit["profile"]["codegen_units"], 2);
                assert_eq!(unit["profile"]["opt_level"], "0");
                marked.push(unit["target"]["name"].as_str().unwrap());
            }
        }
        marked.sort();
        if rustc_host() == "x86_64-unknown-linux-gnu" {
            assert_eq!(marked, expected, "{graph}");
            if expected.contains(&"helper") {
                // The target library and the macro's build script each use
                // their ordinary copy of helper.
                let plain = units.iter().filter(|u| {
                    u["target"]["name"] == "helper" && u["profile"]["rustflags"].is_null()
                });
                assert_eq!(plain.count(), 2, "{graph}");
            }
        } else {
            assert!(marked.is_empty(), "{graph}");
        }
    };
    check("yes", "dev", "", &["helper", "leaf"]);
    check("yes", "custom", "", &["helper", "leaf"]);
    check(
        "yes",
        "dev",
        "[profile.dev.package.leaf]\ndebug = 1",
        &["helper"],
    );
    check(
        "yes",
        "dev",
        "[profile.dev.build-override]\nopt-level = 0",
        &[],
    );
    check("yes", "dev", "codegen-units = 8", &[]);
    check(
        "yes",
        "dev",
        "[profile.dev.package.'*']\nopt-level = 1",
        &[],
    );
    check("yes", "release", "", &[]);
    check("no", "dev", "", &[]);

    p.cargo("build -v -Zohm-defaults=yes")
        .with_stderr_contains("[..]--crate-name macros [..]-C lto=off [..]")
        .with_stderr_contains("[..]--crate-name helper [..]-C lto=off [..]")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .run();
    p.cargo("build -Zohm-defaults=yes")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .with_stderr_does_not_contain("[COMPILING] [..]")
        .run();

    // Both host subtrees have an unmarked path library and an overridden
    // registry library in common. Each must see its own copy of leaf through
    // both the direct dependency and local -> helper -> leaf.
    check(
        "yes",
        "dev",
        "[profile.dev.package.helper]\nopt-level = 0",
        &["leaf"],
    );
    p.cargo("build -Zohm-defaults=yes")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .run();
}

#[cargo_test(nightly, reason = "Ohm defaults require the Ohm compiler")]
fn ohm_prefers_helper_versions_used_by_workspace_macros() {
    cargo_test_support::registry::alt_init();
    for (macro_name, version) in [
        ("older", "1.0.0"),
        ("newer", "2.0.0"),
        ("future", "3.1.0-beta"),
    ] {
        Package::new("helper", version).publish();
        Package::new(macro_name, "1.0.0")
            .proc_macro(true)
            .dep("helper", version)
            .publish();
    }
    Package::new("helper", "4.0.0").alternative(true).publish();
    Package::new("unrelated", "1.0.0")
        .registry_dep("helper", "4")
        .alternative(true)
        .publish();
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [workspace]
                members = ["macros"]
                [package]
                name = "app"
                version = "0.1.0"
                edition = "2024"
                [dependencies]
                older = "1"
                newer = "1"
                future = "1"
                macros = { path = "macros" }
                [profile.dev]
                opt-level = 1
                lto = "off"
            "#,
        )
        .file("src/lib.rs", "")
        .file("macros/src/lib.rs", "")
        .build();
    let mut hashes = Vec::new();
    for (requirement, preferred) in [
        ("1", &["1.0.0"][..]),
        ("2", &["2.0.0"]),
        ("3.1.0-beta", &["3.1.0-beta"]),
        // A broad requirement can also select a compatible prerelease.
        (">=1, <4", &["1.0.0", "2.0.0", "3.1.0-beta"]),
    ] {
        p.change_file(
            "macros/Cargo.toml",
            &format!(
                r#"
                    [package]
                    name = "macros"
                    version = "0.1.0"
                    edition = "2024"
                    [lib]
                    proc-macro = true
                    [dependencies]
                    renamed = {{ package = "helper", version = "{requirement}" }}
                    unrelated = {{ registry = "alternative", version = "1" }}
                "#
            ),
        );
        let graph = p
            .cargo("build --unit-graph -Zunstable-options -Zohm-defaults=yes")
            .masquerade_as_nightly_cargo(&["unit-graph", "ohm-defaults"])
            .run_json();
        let helpers: Vec<_> = graph["units"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|unit| unit["target"]["name"] == "helper")
            .collect();
        // The workspace and registry macros continue to share a single helper
        // per version, even when the workspace changes its preference.
        assert_eq!(helpers.len(), 4, "{graph}");
        if rustc_host() == "x86_64-unknown-linux-gnu" {
            for unit in helpers {
                let id = unit["pkg_id"].as_str().unwrap();
                let (_, version) = id.rsplit_once('@').unwrap();
                // Version 4 belongs to the other registry and is always marked.
                let optimize = preferred.contains(&version) || version == "4.0.0";
                assert_eq!(
                    unit["profile"]["codegen_units"],
                    if optimize { 2 } else { 1 }
                );
                let flag = if optimize {
                    "-Zllvm-module-flag=ohm.proc-macro-helper:u32:1:max"
                } else {
                    "-Zllvm-module-flag=ohm.proc-macro-helper:u32:0:max"
                };
                assert_eq!(unit["profile"]["rustflags"].as_array().unwrap(), &[flag]);
            }

            // The dependency tree of older stays the same as the workspace
            // changes its preference. Its helper's flag goes from 1 to 0,
            // then stays at 0, then goes back to 1.
            let output = p
                .cargo("build -v -p older -Zohm-defaults=yes")
                .masquerade_as_nightly_cargo(&["ohm-defaults"])
                .run();
            let stderr = String::from_utf8(output.stderr).unwrap();
            if matches!(requirement, "1" | "2") {
                let cmd = stderr
                    .lines()
                    .find(|l| l.contains("--crate-name older "))
                    .unwrap();
                let value = |key: &str| {
                    cmd.split_whitespace()
                        .find_map(|arg| arg.strip_prefix(key))
                        .unwrap()
                        .to_string()
                };
                hashes.push((value("metadata="), value("extra-filename=")));
            } else {
                assert!(!stderr.contains("--crate-name "), "{stderr}");
            }
        }
    }
    if rustc_host() == "x86_64-unknown-linux-gnu" {
        assert_eq!(hashes[0].0, hashes[1].0);
        assert_ne!(hashes[0].1, hashes[1].1);
    }
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

            [lints.cargo]
            default = "allow"
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();
    p.cargo("check -v")
        .with_stderr_data(str![[r#"
[WARNING] ignoring `hint-mostly-unused` profile option
  --> Cargo.toml:11:13
   |
10 |             [profile.dev.package.bar]
   |                                  ---
11 |             hint-mostly-unused = true
   |             ^^^^^^^^^^^^^^^^^^^^^^^^^
   |
   = [HELP] pass `-Zprofile-hint-mostly-unused` to enable it
[WARNING] workspace (manifest) generated 1 warning
[UPDATING] `dummy-registry` index
[LOCKING] 1 package to highest compatible version
[DOWNLOADING] crates ...
[DOWNLOADED] bar v1.0.0 (registry `dummy-registry`)
[CHECKING] bar v1.0.0
[RUNNING] `rustc --crate-name bar [..]`
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .with_stderr_does_not_contain("-Zhint-mostly-unused")
        .run();
}

#[cargo_test]
fn profile_hint_mostly_unused_warns_with_mixed_profiles() {
    let normal_only = str![[r#"
[WARNING] ignoring `hint-mostly-unused` profile option
  --> Cargo.toml:14:21
   |
13 |                     [profile.dev]
   |                              ---
14 |                     hint-mostly-unused = true
   |                     ^^^^^^^^^^^^^^^^^^^^^^^^^
   |
   = [HELP] pass `-Zprofile-hint-mostly-unused` to enable it
[WARNING] workspace (manifest) generated 1 warning
[LOCKING] 1 package to highest compatible version
[COMPILING] bar v0.0.1 ([ROOT]/foo/bar)
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]];
    let build_only = str![[r#"
[WARNING] ignoring `hint-mostly-unused` profile option
  --> Cargo.toml:17:21
   |
16 |                     [profile.dev.build-override]
   |                                  --------------
17 |                     hint-mostly-unused = true
   |                     ^^^^^^^^^^^^^^^^^^^^^^^^^
   |
   = [HELP] pass `-Zprofile-hint-mostly-unused` to enable it
[WARNING] workspace (manifest) generated 1 warning
[LOCKING] 1 package to highest compatible version
[COMPILING] bar v0.0.1 ([ROOT]/foo/bar)
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]];
    let both = str![[r#"
[WARNING] ignoring `hint-mostly-unused` profile option
  --> Cargo.toml:14:21
   |
13 |                     [profile.dev]
   |                              ---
14 |                     hint-mostly-unused = true
   |                     ^^^^^^^^^^^^^^^^^^^^^^^^^
   |
   = [HELP] pass `-Zprofile-hint-mostly-unused` to enable it
[WARNING] ignoring `hint-mostly-unused` profile option
  --> Cargo.toml:17:21
   |
16 |                     [profile.dev.build-override]
   |                                  --------------
17 |                     hint-mostly-unused = true
   |                     ^^^^^^^^^^^^^^^^^^^^^^^^^
   |
   = [HELP] pass `-Zprofile-hint-mostly-unused` to enable it
[WARNING] workspace (manifest) generated 2 warnings
[LOCKING] 1 package to highest compatible version
[COMPILING] bar v0.0.1 ([ROOT]/foo/bar)
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]];
    for (normal_hint, build_hint, expected) in [
        (true, false, normal_only),
        (false, true, build_only),
        (true, true, both),
    ] {
        let p = project()
            .file(
                "Cargo.toml",
                &format!(
                    r#"
                    [package]
                    name = "foo"
                    version = "0.0.1"
                    edition = "2015"

                    [dependencies]
                    bar = {{ path = "bar" }}

                    [build-dependencies]
                    bar = {{ path = "bar" }}

                    [profile.dev]
                    hint-mostly-unused = {normal_hint}

                    [profile.dev.build-override]
                    hint-mostly-unused = {build_hint}

                    [profile.dev.package.foo]
                    hint-mostly-unused = false
                    "#,
                ),
            )
            .file("src/main.rs", "extern crate bar; fn main() {}")
            .file("build.rs", "extern crate bar; fn main() {}")
            .file(
                "bar/Cargo.toml",
                r#"
                [package]
                name = "bar"
                version = "0.0.1"
                edition = "2015"
                "#,
            )
            .file("bar/src/lib.rs", "")
            .build();

        p.cargo("check").with_stderr_data(expected).run();
    }
}

#[cargo_test]
fn profile_hint_mostly_unused_from_config_warn_without_gate() {
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

            [lints.cargo]
            default = "allow"
            "#,
        )
        .file(
            ".cargo/config.toml",
            r#"
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
[WARNING] ignoring `hint-mostly-unused` in `profile.dev.package.bar` (defined in [ROOT]/foo/.cargo/config.toml), pass `-Zprofile-hint-mostly-unused` to enable it
[CHECKING] bar v1.0.0
[RUNNING] `rustc --crate-name bar [..]`
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .with_stderr_does_not_contain("-Zhint-mostly-unused")
        .run();
}

#[cargo_test]
fn profile_hint_mostly_unused_from_config_only_profile_warn_without_gate() {
    let p = project()
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
            ".cargo/config.toml",
            r#"
            [profile.custom]
            inherits = "dev"
            hint-mostly-unused = true

            # Never loaded, since nothing requests it, so it must not break the build.
            [profile.broken]
            opt-level = "zzz"
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();
    p.cargo("fetch").with_stderr_data(str![""]).run();
    p.cargo("check --profile custom -v")
        .with_stderr_data(str![[r#"
[WARNING] ignoring `hint-mostly-unused` in `profile.custom` (defined in [ROOT]/foo/.cargo/config.toml), pass `-Zprofile-hint-mostly-unused` to enable it
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..]`
[FINISHED] `custom` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .with_stderr_does_not_contain("-Zhint-mostly-unused")
        .run();
}

#[cargo_test]
fn profile_hint_mostly_unused_from_env_and_config_warn_without_gate() {
    let p = project()
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
            ".cargo/config.toml",
            r#"
            [profile.dev.build-override]
            hint-mostly-unused = true
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .file("build.rs", "fn main() {}")
        .build();
    p.cargo("check")
        .env("CARGO_PROFILE_DEV_HINT_MOSTLY_UNUSED", "true")
        .with_stderr_data(str![[r#"
[WARNING] ignoring `hint-mostly-unused` in `profile.dev` (defined in environment variable `CARGO_PROFILE_DEV_HINT_MOSTLY_UNUSED`), pass `-Zprofile-hint-mostly-unused` to enable it
[WARNING] ignoring `hint-mostly-unused` in `profile.dev.build-override` (defined in [ROOT]/foo/.cargo/config.toml), pass `-Zprofile-hint-mostly-unused` to enable it
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn profile_hint_mostly_unused_in_unselected_profile_warn_without_gate() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "foo"
            version = "0.0.1"
            edition = "2015"

            [profile.release]
            hint-mostly-unused = true
            "#,
        )
        .file(
            ".cargo/config.toml",
            r#"
            [profile.bench]
            hint-mostly-unused = true
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();
    p.cargo("check")
        .with_stderr_data(str![[r#"
[WARNING] ignoring `hint-mostly-unused` profile option
 --> Cargo.toml:8:13
  |
7 |             [profile.release]
  |                      -------
8 |             hint-mostly-unused = true
  |             ^^^^^^^^^^^^^^^^^^^^^^^^^
  |
  = [HELP] pass `-Zprofile-hint-mostly-unused` to enable it
[WARNING] workspace (manifest) generated 1 warning
[WARNING] ignoring `hint-mostly-unused` in `profile.bench` (defined in [ROOT]/foo/.cargo/config.toml), pass `-Zprofile-hint-mostly-unused` to enable it
[CHECKING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
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

            [lints.cargo]
            default = "allow"
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();
    p.cargo("check -v")
        .arg("-Zprofile-hint-mostly-unused")
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

#[cargo_test(nightly, reason = "Ohm defaults require the Ohm compiler")]
fn ohm_inlines_workspace_build_helpers() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "app"
                version = "0.1.0"
                edition = "2024"
                [workspace]
                members = ["generator", "util"]
                [profile.dev]
                opt-level = 1
                [build-dependencies]
                genlib = { package = "generator", path = "generator" }
            "#,
        )
        .file(
            "build.rs",
            r#"fn main() { println!("cargo:rustc-env=VALUE={}", genlib::value()); }"#,
        )
        .file(
            "src/lib.rs",
            r#"const _: () = assert!(env!("VALUE").len() == 2);"#,
        )
        .file(
            "generator/Cargo.toml",
            r#"
                [package]
                name = "generator"
                version = "0.1.0"
                edition = "2024"
                [dependencies]
                util = { path = "../util" }
            "#,
        )
        .file(
            "generator/src/lib.rs",
            "pub fn value() -> u32 { util::number() }",
        )
        .file(
            "util/Cargo.toml",
            "[package]\nname='util'\nversion='0.1.0'\nedition='2024'",
        )
        .file("util/src/lib.rs", "pub fn number() -> u32 { 42 }")
        .build();
    let run = |command: &str, options: &str| {
        let output = p
            .cargo(&format!("{command} -v -p app -Zohm-defaults=yes {options}"))
            .masquerade_as_nightly_cargo(&["ohm-defaults"])
            .run();
        String::from_utf8(output.stderr).unwrap()
    };
    let initial = run("check", "");
    if rustc_host() != "x86_64-unknown-linux-gnu" {
        assert!(!initial.contains("ohm.build-script-helper"), "{initial}");
        return;
    }
    let command = |stderr: &str| {
        stderr
            .lines()
            .find(|l| l.contains("--crate-name generator "))
            .unwrap()
            .to_owned()
    };
    let tuned = command(&initial);
    assert_eq!(
        initial.matches("ohm.build-script-helper").count(),
        1,
        "{initial}"
    );
    assert!(
        tuned.contains("-Zllvm-module-flag=ohm.build-script-helper:u32:1:max"),
        "{tuned}"
    );
    assert!(tuned.contains("-Ccodegen-units=1"), "{tuned}");
    assert!(!run("build", "").contains("--crate-name generator "));

    // An explicit level 0 has the same profile and symbol metadata, but
    // disables the extra passes. Both versions should survive in the cache.
    let options = "--config profile.dev.package.generator.opt-level=0";
    let plain = command(&run("check", options));
    assert!(!plain.contains("ohm.build-script-helper"), "{plain}");
    let value = |cmd: &str, key: &str| {
        cmd.split_whitespace()
            .find_map(|arg| arg.strip_prefix(key))
            .unwrap()
            .to_owned()
    };
    assert_eq!(value(&tuned, "metadata="), value(&plain, "metadata="));
    assert_ne!(
        value(&tuned, "extra-filename="),
        value(&plain, "extra-filename=")
    );
    for opts in ["", options] {
        assert!(!run("build", opts).contains("--crate-name generator "));
    }

    let override_flags = p
        .cargo("check -v -p app -Zohm-defaults=yes")
        .env("RUSTFLAGS", "-Ccodegen-units=4")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .run();
    let explicit = command(&String::from_utf8(override_flags.stderr).unwrap());
    assert!(!explicit.contains("ohm.build-script-helper"), "{explicit}");
    assert!(explicit.contains("-Ccodegen-units=4"), "{explicit}");

    // A dynamic library may not have a hashed output filename.
    let generator = p.read_file("generator/Cargo.toml");
    p.change_file(
        "generator/Cargo.toml",
        &format!("{generator}\n[lib]\ncrate-type = ['rlib', 'cdylib']"),
    );
    let shared = command(&run("check", ""));
    assert!(!shared.contains("ohm.build-script-helper"), "{shared}");
    p.change_file("generator/Cargo.toml", &generator);

    // A dev dependency need not be active to change the helper's role.
    let manifest = p.read_file("Cargo.toml");
    p.change_file(
        "Cargo.toml",
        &format!(
            "{manifest}\n[dev-dependencies]\ngenlib = {{ package='generator', path='generator' }}"
        ),
    );
    p.change_file(
        "generator/src/lib.rs",
        "pub fn value() -> u32 { util::number() + 1 }",
    );
    let mixed = command(&run("check", ""));
    assert!(!mixed.contains("ohm.build-script-helper"), "{mixed}");
}

#[cargo_test(nightly, reason = "Ohm defaults require the Ohm compiler")]
fn ohm_inlines_a_registry_build_helper_published_with_its_consumer() {
    let metadata = |name, version, repo| {
        format!(
            r#"
            [package]
            name = "{name}"
            version = "{version}"
            repository = "https://example.com/{repo}"
            edition = "2024"
            "#
        )
    };
    for (name, version, repo) in [
        ("tables", "1.0.0", "data"),
        ("common", "1.0.0", "other"),
        ("older", "0.9.0", "data"),
    ] {
        Package::new(name, version)
            .file("Cargo.toml", &metadata(name, version, repo))
            .file("src/lib.rs", "pub fn value() -> u32 { 14 }")
            .publish();
    }
    Package::new("data", "1.0.0")
        .build_dep("tables", "1")
        .build_dep("common", "1")
        .build_dep("older", "0.9")
        .file(
            "Cargo.toml",
            &(metadata("data", "1.0.0", "data")
                + "\n[build-dependencies]\ntables = '1'\ncommon = '1'\nolder = '0.9'\n"),
        )
        .file("src/lib.rs", "")
        .file(
            "build.rs",
            "fn main() { assert_eq!(tables::value() + common::value() + older::value(), 42); }",
        )
        .publish();
    let app = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "app"
            version = "0.1.0"
            edition = "2024"
            [profile.dev]
            opt-level = 1
            [dependencies]
            data = "1"
            tables = { version = "1", optional = true }
            "#,
        )
        .file("src/lib.rs", "")
        .build();
    let run = |args: &str| {
        let result = app
            .cargo(&format!("{args} -v -Zohm-defaults=yes"))
            .masquerade_as_nightly_cargo(&["ohm-defaults"])
            .run();
        String::from_utf8(result.stderr).unwrap()
    };
    let first = run("check");
    let marker = "ohm.build-script-helper";
    if rustc_host() != "x86_64-unknown-linux-gnu" {
        assert!(!first.contains(marker), "{first}");
        return;
    }
    assert_eq!(first.matches(marker).count(), 1, "{first}");
    assert!(
        first
            .lines()
            .any(|line| line.contains("--crate-name tables ") && line.contains(marker)),
        "{first}"
    );
    assert!(!run("build").contains("--crate-name tables "));
    // An unrelated consumer must get a separate, unmarked copy.
    let shared = run("check --features tables");
    assert!(shared.contains("--crate-name tables "), "{shared}");
    assert!(!shared.contains(marker), "{shared}");
    assert!(!run("check").contains("--crate-name tables "));
}
