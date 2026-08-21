//! Tests for fingerprinting (rebuild detection).

use std::ffi::OsStr;
use std::fs::{self, OpenOptions};
use std::io;
use std::io::prelude::*;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::thread;
use std::time::SystemTime;

use crate::prelude::*;
use cargo_test_support::paths;
use cargo_test_support::registry::Package;
use cargo_test_support::{
    basic_lib_manifest, basic_manifest, is_coarse_mtime, project, rustc_host, rustc_host_env,
    sleep_ms, str,
};
use filetime::FileTime;

use super::death;

#[cargo_test]
fn modifying_and_moving() {
    let p = project()
        .file("src/main.rs", "mod a; fn main() {}")
        .file("src/a.rs", "")
        .build();

    p.cargo("build")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("build")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.root().move_into_the_past();
    p.root().join("target").move_into_the_past();

    p.change_file("src/a.rs", "#[allow(unused)]fn main() {}");
    p.cargo("build -v")
        .with_stderr_data(str![[r#"
[DIRTY] foo v0.0.1 ([ROOT]/foo): the file `src/a.rs` has changed ([TIME_DIFF_AFTER_LAST_BUILD])
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    fs::rename(&p.root().join("src/a.rs"), &p.root().join("src/b.rs")).unwrap();
    p.cargo("build")
        .with_status(101)
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
error[E0583]: file not found for module `a`
...
[ERROR] could not compile `foo` (bin "foo") due to 1 previous error

"#]])
        .run();
}

#[cargo_test]
fn modify_only_some_files() {
    let p = project()
        .file("src/lib.rs", "mod a;")
        .file("src/a.rs", "")
        .file("src/main.rs", "mod b; fn main() {}")
        .file("src/b.rs", "")
        .file("tests/test.rs", "")
        .build();

    p.cargo("build")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("test").run();
    sleep_ms(1000);

    assert!(p.bin("foo").is_file());

    let lib = p.root().join("src/lib.rs");
    p.change_file("src/lib.rs", "invalid rust code");
    p.change_file("src/b.rs", "#[allow(unused)]fn foo() {}");
    lib.move_into_the_past();

    // Make sure the binary is rebuilt, not the lib
    p.cargo("build -v")
        .with_stderr_data(str![[r#"
[DIRTY] foo v0.0.1 ([ROOT]/foo): the file `src/b.rs` has changed ([TIME_DIFF_AFTER_LAST_BUILD])
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    assert!(p.bin("foo").is_file());
}

#[cargo_test]
fn rebuild_sub_package_then_while_package() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                authors = []
                version = "0.0.1"
                edition = "2015"

                [dependencies.a]
                path = "a"
                [dependencies.b]
                path = "b"
            "#,
        )
        .file("src/lib.rs", "extern crate a; extern crate b;")
        .file(
            "a/Cargo.toml",
            r#"
                [package]
                name = "a"
                authors = []
                version = "0.0.1"
                edition = "2015"
                [dependencies.b]
                path = "../b"
            "#,
        )
        .file("a/src/lib.rs", "extern crate b;")
        .file("b/Cargo.toml", &basic_manifest("b", "0.0.1"))
        .file("b/src/lib.rs", "")
        .build();

    p.cargo("build")
        .with_stderr_data(str![[r#"
[LOCKING] 2 packages to latest compatible versions
[COMPILING] b v0.0.1 ([ROOT]/foo/b)
[COMPILING] a v0.0.1 ([ROOT]/foo/a)
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    if is_coarse_mtime() {
        sleep_ms(1000);
    }
    p.change_file("b/src/lib.rs", "pub fn b() {}");

    p.cargo("build -pb -v")
        .with_stderr_data(str![[r#"
[DIRTY] b v0.0.1 ([ROOT]/foo/b): the file `b/src/lib.rs` has changed ([TIME_DIFF_AFTER_LAST_BUILD])
[COMPILING] b v0.0.1 ([ROOT]/foo/b)
[RUNNING] `rustc --crate-name b [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.change_file(
        "src/lib.rs",
        "extern crate a; extern crate b; pub fn toplevel() {}",
    );

    p.cargo("build -v")
        .with_stderr_data(str![[r#"
[FRESH] b v0.0.1 ([ROOT]/foo/b)
[DIRTY] a v0.0.1 ([ROOT]/foo/a): the dependency `b` was rebuilt ([TIME_DIFF_AFTER_LAST_BUILD])
[COMPILING] a v0.0.1 ([ROOT]/foo/a)
[RUNNING] `rustc --crate-name a [..]
[DIRTY] foo v0.0.1 ([ROOT]/foo): the file `src/lib.rs` has changed ([TIME_DIFF_AFTER_LAST_BUILD])
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..] src/lib.rs [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn changing_lib_features_caches_targets() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                authors = []
                version = "0.0.1"
                edition = "2015"

                [features]
                foo = []
            "#,
        )
        .file("src/lib.rs", "")
        .build();

    p.cargo("build")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("build --features foo")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    /* Targets should be cached from the first build */

    p.cargo("build")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("build")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("build --features foo")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn changing_profiles_caches_targets() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                authors = []
                version = "0.0.1"
                edition = "2015"

                [profile.dev]
                panic = "abort"
            "#,
        )
        .file("src/lib.rs", "")
        .build();

    p.cargo("build")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("test")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `test` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[RUNNING] unittests src/lib.rs (target/debug/deps/foo-[HASH][EXE])
[DOCTEST] foo

"#]])
        .run();

    /* Targets should be cached from the first build */

    p.cargo("build")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("test foo")
        .with_stderr_data(str![[r#"
[FINISHED] `test` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[RUNNING] unittests src/lib.rs (target/debug/deps/foo-[HASH][EXE])

"#]])
        .run();
}

#[cargo_test]
fn changing_bin_paths_common_target_features_caches_targets() {
    // Make sure dep_cache crate is built once per feature
    let p = project()
        .no_manifest()
        .file(
            ".cargo/config.toml",
            r#"
                [build]
                target-dir = "./target"
            "#,
        )
        .file(
            "dep_crate/Cargo.toml",
            r#"
                [package]
                name    = "dep_crate"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [features]
                ftest  = []
            "#,
        )
        .file(
            "dep_crate/src/lib.rs",
            r#"
                #[cfg(feature = "ftest")]
                pub fn yo() {
                    println!("ftest on")
                }
                #[cfg(not(feature = "ftest"))]
                pub fn yo() {
                    println!("ftest off")
                }
            "#,
        )
        .file(
            "a/Cargo.toml",
            r#"
                [package]
                name    = "a"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [dependencies]
                dep_crate = {path = "../dep_crate", features = []}
            "#,
        )
        .file("a/src/lib.rs", "")
        .file(
            "a/src/main.rs",
            r#"
                extern crate dep_crate;
                use dep_crate::yo;
                fn main() {
                    yo();
                }
            "#,
        )
        .file(
            "b/Cargo.toml",
            r#"
                [package]
                name    = "b"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [dependencies]
                dep_crate = {path = "../dep_crate", features = ["ftest"]}
            "#,
        )
        .file("b/src/lib.rs", "")
        .file(
            "b/src/main.rs",
            r#"
                extern crate dep_crate;
                use dep_crate::yo;
                fn main() {
                    yo();
                }
            "#,
        )
        .build();

    /* Build and rebuild a/. Ensure dep_crate only builds once */
    p.cargo("run")
        .cwd("a")
        .with_stdout_data(str![[r#"
ftest off

"#]])
        .with_stderr_data(str![[r#"
[LOCKING] 1 package to latest compatible version
[COMPILING] dep_crate v0.0.1 ([ROOT]/foo/dep_crate)
[COMPILING] a v0.0.1 ([ROOT]/foo/a)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[RUNNING] `[ROOT]/foo/./target/debug/a[EXE]`

"#]])
        .run();
    p.cargo("clean -p a").cwd("a").run();
    p.cargo("run")
        .cwd("a")
        .with_stdout_data(str![[r#"
ftest off

"#]])
        .with_stderr_data(str![[r#"
[COMPILING] a v0.0.1 ([ROOT]/foo/a)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[RUNNING] `[ROOT]/foo/./target/debug/a[EXE]`

"#]])
        .run();

    /* Build and rebuild b/. Ensure dep_crate only builds once */
    p.cargo("run")
        .cwd("b")
        .with_stdout_data(str![[r#"
ftest on

"#]])
        .with_stderr_data(str![[r#"
[LOCKING] 1 package to latest compatible version
[COMPILING] dep_crate v0.0.1 ([ROOT]/foo/dep_crate)
[COMPILING] b v0.0.1 ([ROOT]/foo/b)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[RUNNING] `[ROOT]/foo/./target/debug/b[EXE]`

"#]])
        .run();
    p.cargo("clean -p b").cwd("b").run();
    p.cargo("run")
        .cwd("b")
        .with_stdout_data(str![[r#"
ftest on

"#]])
        .with_stderr_data(str![[r#"
[COMPILING] b v0.0.1 ([ROOT]/foo/b)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[RUNNING] `[ROOT]/foo/./target/debug/b[EXE]`

"#]])
        .run();

    /* Build a/ package again. If we cache different feature dep builds correctly,
     * this should not cause a rebuild of dep_crate */
    p.cargo("clean -p a").cwd("a").run();
    p.cargo("run")
        .cwd("a")
        .with_stdout_data(str![[r#"
ftest off

"#]])
        .with_stderr_data(str![[r#"
[COMPILING] a v0.0.1 ([ROOT]/foo/a)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[RUNNING] `[ROOT]/foo/./target/debug/a[EXE]`

"#]])
        .run();

    /* Build b/ package again. If we cache different feature dep builds correctly,
     * this should not cause a rebuild */
    p.cargo("clean -p b").cwd("b").run();
    p.cargo("run")
        .cwd("b")
        .with_stdout_data(str![[r#"
ftest on

"#]])
        .with_stderr_data(str![[r#"
[COMPILING] b v0.0.1 ([ROOT]/foo/b)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[RUNNING] `[ROOT]/foo/./target/debug/b[EXE]`

"#]])
        .run();
}

#[cargo_test]
fn changing_bin_features_caches_targets() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                authors = []
                version = "0.0.1"
                edition = "2015"

                [features]
                foo = []
            "#,
        )
        .file(
            "src/main.rs",
            r#"
                fn main() {
                    let msg = if cfg!(feature = "foo") { "feature on" } else { "feature off" };
                    println!("{}", msg);
                }
            "#,
        )
        .build();

    p.cargo("build")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.rename_run("foo", "off1")
        .with_stdout_data(str![[r#"
feature off

"#]])
        .run();

    p.cargo("build --features foo")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.rename_run("foo", "on1")
        .with_stdout_data(str![[r#"
feature on

"#]])
        .run();

    /* Targets should be cached from the first build */

    let mut e = p.cargo("build -v");

    // MSVC does not include hash in binary filename, so it gets recompiled.
    if cfg!(target_env = "msvc") {
        e.with_stderr_data(str![[r#"
[DIRTY] foo v0.0.1 ([ROOT]/foo): the list of features changed
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]);
    } else {
        e.with_stderr_data(str![[r#"
[FRESH] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]);
    }
    e.run();
    p.rename_run("foo", "off2")
        .with_stdout_data(str![[r#"
feature off

"#]])
        .run();

    let mut e = p.cargo("build --features foo -v");
    if cfg!(target_env = "msvc") {
        e.with_stderr_data(str![[r#"
[DIRTY] foo v0.0.1 ([ROOT]/foo): the list of features changed
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]);
    } else {
        e.with_stderr_data(str![[r#"
[FRESH] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]);
    }
    e.run();
    p.rename_run("foo", "on2")
        .with_stdout_data(str![[r#"
feature on

"#]])
        .run();
}

#[cargo_test]
fn rebuild_tests_if_lib_changes() {
    let p = project()
        .file("src/lib.rs", "pub fn foo() {}")
        .file("tests/foo-test.rs", "extern crate foo;")
        .build();

    p.cargo("build").run();
    p.cargo("test").run();

    sleep_ms(1000);
    p.change_file("src/lib.rs", "");

    p.cargo("build").run();
    p.cargo("test -v --test foo-test")
        .with_stderr_data(str![[r#"
[DIRTY] foo v0.0.1 ([ROOT]/foo): the dependency `foo` was rebuilt ([TIME_DIFF_AFTER_LAST_BUILD])
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo_test [..]`
[FINISHED] `test` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[RUNNING] `[ROOT]/foo/target/debug/deps/foo_test-[HASH][EXE]`

"#]])
        .run();
}

#[cargo_test]
fn no_rebuild_transitive_target_deps() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [dependencies]
                a = { path = "a" }
                [dev-dependencies]
                b = { path = "b" }
            "#,
        )
        .file("src/lib.rs", "")
        .file("tests/foo.rs", "")
        .file(
            "a/Cargo.toml",
            r#"
                [package]
                name = "a"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [target.foo.dependencies]
                c = { path = "../c" }
            "#,
        )
        .file("a/src/lib.rs", "")
        .file(
            "b/Cargo.toml",
            r#"
                [package]
                name = "b"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [dependencies]
                c = { path = "../c" }
            "#,
        )
        .file("b/src/lib.rs", "")
        .file("c/Cargo.toml", &basic_manifest("c", "0.0.1"))
        .file("c/src/lib.rs", "")
        .build();

    p.cargo("build").run();
    p.cargo("test --no-run")
        .with_stderr_data(str![[r#"
[COMPILING] c v0.0.1 ([ROOT]/foo/c)
[COMPILING] b v0.0.1 ([ROOT]/foo/b)
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `test` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[EXECUTABLE] unittests src/lib.rs (target/debug/deps/foo-[HASH][EXE])
[EXECUTABLE] tests/foo.rs (target/debug/deps/foo-[HASH][EXE])

"#]])
        .run();
}

#[cargo_test]
fn rerun_if_changed_in_dep() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [dependencies]
                a = { path = "a" }
            "#,
        )
        .file("src/lib.rs", "")
        .file(
            "a/Cargo.toml",
            r#"
                [package]
                name = "a"
                version = "0.0.1"
                edition = "2015"
                authors = []
                build = "build.rs"
            "#,
        )
        .file(
            "a/build.rs",
            r#"
                fn main() {
                    println!("cargo::rerun-if-changed=build.rs");
                }
            "#,
        )
        .file("a/src/lib.rs", "")
        .build();

    p.cargo("build").run();
    p.cargo("build")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn same_build_dir_cached_packages() {
    let p = project()
        .no_manifest()
        .file(
            "a1/Cargo.toml",
            r#"
                [package]
                name = "a1"
                version = "0.0.1"
                edition = "2015"
                authors = []
                [dependencies]
                b = { path = "../b" }
            "#,
        )
        .file("a1/src/lib.rs", "")
        .file(
            "a2/Cargo.toml",
            r#"
                [package]
                name = "a2"
                version = "0.0.1"
                edition = "2015"
                authors = []
                [dependencies]
                b = { path = "../b" }
            "#,
        )
        .file("a2/src/lib.rs", "")
        .file(
            "b/Cargo.toml",
            r#"
                [package]
                name = "b"
                version = "0.0.1"
                edition = "2015"
                authors = []
                [dependencies]
                c = { path = "../c" }
            "#,
        )
        .file("b/src/lib.rs", "")
        .file(
            "c/Cargo.toml",
            r#"
                [package]
                name = "c"
                version = "0.0.1"
                edition = "2015"
                authors = []
                [dependencies]
                d = { path = "../d" }
            "#,
        )
        .file("c/src/lib.rs", "")
        .file("d/Cargo.toml", &basic_manifest("d", "0.0.1"))
        .file("d/src/lib.rs", "")
        .file(
            ".cargo/config.toml",
            r#"
                [build]
                target-dir = "./target"
            "#,
        )
        .build();

    p.cargo("build")
        .cwd("a1")
        .with_stderr_data(str![[r#"
[LOCKING] 3 packages to latest compatible versions
[COMPILING] d v0.0.1 ([ROOT]/foo/d)
[COMPILING] c v0.0.1 ([ROOT]/foo/c)
[COMPILING] b v0.0.1 ([ROOT]/foo/b)
[COMPILING] a1 v0.0.1 ([ROOT]/foo/a1)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("build")
        .cwd("a2")
        .with_stderr_data(str![[r#"
[LOCKING] 3 packages to latest compatible versions
[COMPILING] a2 v0.0.1 ([ROOT]/foo/a2)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn no_rebuild_if_build_artifacts_move_backwards_in_time() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [dependencies]
                a = { path = "a" }
            "#,
        )
        .file("src/lib.rs", "")
        .file("a/Cargo.toml", &basic_manifest("a", "0.0.1"))
        .file("a/src/lib.rs", "")
        .build();

    p.cargo("build").run();

    p.root().move_into_the_past();

    p.cargo("build")
        .with_stdout_data(str![])
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn rebuild_if_build_artifacts_move_forward_in_time() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [dependencies]
                a = { path = "a" }
            "#,
        )
        .file("src/lib.rs", "")
        .file("a/Cargo.toml", &basic_manifest("a", "0.0.1"))
        .file("a/src/lib.rs", "")
        .build();

    p.cargo("build").run();

    p.root().move_into_the_future();

    p.cargo("build")
        .env("CARGO_LOG", "")
        .with_stdout_data(str![])
        .with_stderr_data(str![[r#"
[COMPILING] a v0.0.1 ([ROOT]/foo/a)
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn rebuild_if_environment_changes() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                description = "old desc"
                version = "0.0.1"
                edition = "2015"
                authors = []
            "#,
        )
        .file(
            "src/main.rs",
            r#"
                fn main() {
                    println!("{}", env!("CARGO_PKG_DESCRIPTION"));
                }
            "#,
        )
        .build();

    p.cargo("run")
        .with_stdout_data(str![[r#"
old desc

"#]])
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[RUNNING] `target/debug/foo[EXE]`

"#]])
        .run();

    p.change_file(
        "Cargo.toml",
        r#"
            [package]
            name = "foo"
            description = "new desc"
            version = "0.0.1"
            edition = "2015"
            authors = []
        "#,
    );

    p.cargo("run -v")
        .with_stdout_data(str![[r#"
new desc

"#]])
        .with_stderr_data(str![[r#"
[DIRTY] foo v0.0.1 ([ROOT]/foo): the environment variable CARGO_PKG_DESCRIPTION changed
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[RUNNING] `target/debug/foo[EXE]`

"#]])
        .run();
}

#[cargo_test]
fn no_rebuild_when_rename_dir() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "bar"
                version = "0.0.1"
                edition = "2015"
                authors = []

                [workspace]

                [dependencies]
                foo = { path = "foo" }
            "#,
        )
        .file("src/_unused.rs", "")
        .file("build.rs", "fn main() {}")
        .file("foo/Cargo.toml", &basic_manifest("foo", "0.0.1"))
        .file("foo/src/lib.rs", "")
        .file("foo/build.rs", "fn main() {}")
        .build();

    // make sure the most recently modified file is `src/lib.rs`, not
    // `Cargo.toml`, to expose a historical bug where we forgot to strip the
    // `Cargo.toml` path from looking for the package root.
    cargo_test_support::sleep_ms(100);
    fs::write(p.root().join("src/lib.rs"), "").unwrap();

    p.cargo("build").run();
    let mut new = p.root();
    new.pop();
    new.push("bar");
    fs::rename(p.root(), &new).unwrap();

    p.cargo("build")
        .cwd(&new)
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn unused_optional_dep() {
    Package::new("registry1", "0.1.0").publish();
    Package::new("registry2", "0.1.0").publish();
    Package::new("registry3", "0.1.0").publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "p"
                authors = []
                version = "0.1.0"
                edition = "2015"

                [dependencies]
                bar = { path = "bar" }
                baz = { path = "baz" }
                registry1 = "*"
            "#,
        )
        .file("src/lib.rs", "")
        .file(
            "bar/Cargo.toml",
            r#"
                [package]
                name = "bar"
                version = "0.1.1"
                edition = "2015"
                authors = []

                [dev-dependencies]
                registry2 = "*"
            "#,
        )
        .file("bar/src/lib.rs", "")
        .file(
            "baz/Cargo.toml",
            r#"
                [package]
                name = "baz"
                version = "0.1.1"
                edition = "2015"
                authors = []

                [dependencies]
                registry3 = { version = "*", optional = true }
            "#,
        )
        .file("baz/src/lib.rs", "")
        .build();

    p.cargo("build").run();
    p.cargo("build")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn path_dev_dep_registry_updates() {
    Package::new("registry1", "0.1.0").publish();
    Package::new("registry2", "0.1.0").publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "p"
                authors = []
                version = "0.1.0"
                edition = "2015"

                [dependencies]
                bar = { path = "bar" }
            "#,
        )
        .file("src/lib.rs", "")
        .file(
            "bar/Cargo.toml",
            r#"
                [package]
                name = "bar"
                version = "0.1.1"
                edition = "2015"
                authors = []

                [dependencies]
                registry1 = "*"

                [dev-dependencies]
                baz = { path = "../baz"}
            "#,
        )
        .file("bar/src/lib.rs", "")
        .file(
            "baz/Cargo.toml",
            r#"
                [package]
                name = "baz"
                version = "0.1.1"
                edition = "2015"
                authors = []

                [dependencies]
                registry2 = "*"
            "#,
        )
        .file("baz/src/lib.rs", "")
        .build();

    p.cargo("build").run();
    p.cargo("build")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn change_panic_mode() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [workspace]
                members = ['bar', 'baz']
                [profile.dev]
                panic = 'abort'
            "#,
        )
        .file("src/lib.rs", "")
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.1.1"))
        .file("bar/src/lib.rs", "")
        .file(
            "baz/Cargo.toml",
            r#"
                [package]
                name = "baz"
                version = "0.1.1"
                edition = "2015"
                authors = []

                [lib]
                proc-macro = true

                [dependencies]
                bar = { path = '../bar' }
            "#,
        )
        .file("baz/src/lib.rs", "extern crate bar;")
        .build();

    p.cargo("build -p bar").run();
    p.cargo("build -p baz").run();
}

#[cargo_test]
fn dont_rebuild_based_on_plugins() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "bar"
                version = "0.1.1"
                edition = "2015"

                [workspace]
                members = ['baz']

                [dependencies]
                proc-macro-thing = { path = 'proc-macro-thing' }
            "#,
        )
        .file("src/lib.rs", "")
        .file(
            "proc-macro-thing/Cargo.toml",
            r#"
                [package]
                name = "proc-macro-thing"
                version = "0.1.1"
                edition = "2015"

                [lib]
                proc-macro = true

                [dependencies]
                qux = { path = '../qux' }
            "#,
        )
        .file("proc-macro-thing/src/lib.rs", "")
        .file(
            "baz/Cargo.toml",
            r#"
                [package]
                name = "baz"
                version = "0.1.1"
                edition = "2015"

                [dependencies]
                qux = { path = '../qux' }
            "#,
        )
        .file("baz/src/main.rs", "fn main() {}")
        .file("qux/Cargo.toml", &basic_manifest("qux", "0.1.1"))
        .file("qux/src/lib.rs", "")
        .build();

    p.cargo("build").run();
    p.cargo("build -p baz").run();
    p.cargo("build")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("build -p bar")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn reuse_workspace_lib() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "bar"
                version = "0.1.1"
                edition = "2015"

                [workspace]

                [dependencies]
                baz = { path = 'baz' }
            "#,
        )
        .file("src/lib.rs", "")
        .file("baz/Cargo.toml", &basic_manifest("baz", "0.1.1"))
        .file("baz/src/lib.rs", "")
        .build();

    p.cargo("build").run();
    p.cargo("test -p baz -v --no-run")
        .with_stderr_data(str![[r#"
[COMPILING] baz v0.1.1 ([ROOT]/foo/baz)
[RUNNING] `rustc --crate-name baz [..]
[FINISHED] `test` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[EXECUTABLE] `[ROOT]/foo/target/debug/deps/baz-[HASH][EXE]`

"#]])
        .run();
}

#[cargo_test]
fn reuse_shared_build_dep() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"

                [dependencies]
                shared = {path = "shared"}

                [workspace]
                members = ["shared", "bar"]
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .file("shared/Cargo.toml", &basic_manifest("shared", "0.0.1"))
        .file("shared/src/lib.rs", "")
        .file(
            "bar/Cargo.toml",
            r#"
                [package]
                name = "bar"
                version = "0.0.1"
                edition = "2015"

                [build-dependencies]
                shared = { path = "../shared" }
            "#,
        )
        .file("bar/src/lib.rs", "")
        .file("bar/build.rs", "fn main() {}")
        .build();

    p.cargo("build --workspace").run();
    // This should not recompile!
    p.cargo("build -p foo -v")
        .with_stderr_data(str![[r#"
[FRESH] shared v0.0.1 ([ROOT]/foo/shared)
[FRESH] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn changing_rustflags_is_cached() {
    let p = project().file("src/lib.rs", "").build();

    // This isn't ever cached, we always have to recompile
    p.cargo("build")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("build -v")
        .env("RUSTFLAGS", "-C linker=cc")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("build -v")
        .with_stderr_data(str![[r#"
[FRESH] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("build -v")
        .env("RUSTFLAGS", "-C linker=cc")
        .with_stderr_data(str![[r#"
[FRESH] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn changing_rustc_extra_flags_is_cached() {
    let p = project().file("src/lib.rs", "").build();

    // This isn't ever cached, we always have to recompile
    p.cargo("rustc")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("rustc -v -- -C linker=cc")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("rustc -v")
        .with_stderr_data(str![[r#"
[FRESH] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("rustc -v -- -C linker=cc")
        .with_stderr_data(str![[r#"
[FRESH] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn update_dependency_mtime_does_not_rebuild() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"

                [dependencies]
                bar = { path = "bar" }
            "#,
        )
        .file("src/lib.rs", "")
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.0.1"))
        .file("bar/src/lib.rs", "")
        .build();

    p.cargo("build -Z mtime-on-use")
        .masquerade_as_nightly_cargo(&["mtime-on-use"])
        .env("RUSTFLAGS", "-C linker=cc")
        .with_stderr_data(str![[r#"
[LOCKING] 1 package to latest compatible version
[COMPILING] bar v0.0.1 ([ROOT]/foo/bar)
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    // This does not make new files, but it does update the mtime of the dependency.
    p.cargo("build -p bar -Z mtime-on-use")
        .masquerade_as_nightly_cargo(&["mtime-on-use"])
        .env("RUSTFLAGS", "-C linker=cc")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    // This should not recompile!
    p.cargo("build -Z mtime-on-use")
        .masquerade_as_nightly_cargo(&["mtime-on-use"])
        .env("RUSTFLAGS", "-C linker=cc")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

fn fingerprint_cleaner(mut dir: PathBuf, timestamp: filetime::FileTime) {
    // Cargo is experimenting with letting outside projects develop some
    // limited forms of GC for target_dir. This is one of the forms.
    // Specifically, Cargo is updating the mtime of a file in
    // target/profile/.fingerprint each time it uses the fingerprint.
    // So a cleaner can remove files associated with a fingerprint
    // if all the files in the fingerprint's folder are older then a time stamp without
    // effecting any builds that happened since that time stamp.
    let mut cleaned = false;
    dir.push(".fingerprint");
    for fingerprint in fs::read_dir(&dir).unwrap() {
        let fingerprint = fingerprint.unwrap();

        let outdated = |f: io::Result<fs::DirEntry>| {
            filetime::FileTime::from_last_modification_time(&f.unwrap().metadata().unwrap())
                <= timestamp
        };
        if fs::read_dir(fingerprint.path()).unwrap().all(outdated) {
            fs::remove_dir_all(fingerprint.path()).unwrap();
            println!("remove: {:?}", fingerprint.path());
            // a real cleaner would remove the big files in deps and build as well
            // but fingerprint is sufficient for our tests
            cleaned = true;
        } else {
        }
    }
    assert!(
        cleaned,
        "called fingerprint_cleaner, but there was nothing to remove"
    );
}

#[cargo_test]
fn fingerprint_cleaner_does_not_rebuild() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"

                [dependencies]
                bar = { path = "bar" }

                [features]
                a = []
            "#,
        )
        .file("src/lib.rs", "")
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.0.1"))
        .file("bar/src/lib.rs", "")
        .build();

    p.cargo("build -Z mtime-on-use")
        .masquerade_as_nightly_cargo(&["mtime-on-use"])
        .run();
    p.cargo("build -Z mtime-on-use --features a")
        .masquerade_as_nightly_cargo(&["mtime-on-use"])
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    if is_coarse_mtime() {
        sleep_ms(1000);
    }
    let timestamp = filetime::FileTime::from_system_time(SystemTime::now());
    if is_coarse_mtime() {
        sleep_ms(1000);
    }
    // This does not make new files, but it does update the mtime.
    p.cargo("build -Z mtime-on-use --features a")
        .masquerade_as_nightly_cargo(&["mtime-on-use"])
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    fingerprint_cleaner(p.target_debug_dir(), timestamp);
    // This should not recompile!
    p.cargo("build -Z mtime-on-use --features a")
        .masquerade_as_nightly_cargo(&["mtime-on-use"])
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    // But this should be cleaned and so need a rebuild
    p.cargo("build -Z mtime-on-use")
        .masquerade_as_nightly_cargo(&["mtime-on-use"])
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn reuse_panic_build_dep_test() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"

                [build-dependencies]
                bar = { path = "bar" }

                [dev-dependencies]
                bar = { path = "bar" }

                [profile.dev]
                panic = "abort"
            "#,
        )
        .file("src/lib.rs", "")
        .file("build.rs", "fn main() {}")
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.0.1"))
        .file("bar/src/lib.rs", "")
        .build();

    // Check that `bar` is not built twice. It is only needed once (without `panic`).
    p.cargo("test --lib --no-run -v")
        .with_stderr_data(str![[r#"
[LOCKING] 1 package to latest compatible version
[COMPILING] bar v0.0.1 ([ROOT]/foo/bar)
[RUNNING] `rustc --crate-name bar [..]
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name build_script_build [..]
[RUNNING] `[ROOT]/foo/target/debug/build/foo-[HASH]/build-script-build`
[RUNNING] `rustc --crate-name foo [..] src/lib.rs [..]--test[..]
[FINISHED] `test` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[EXECUTABLE] `[ROOT]/foo/target/debug/deps/foo-[HASH][EXE]`

"#]])
        .run();
}

#[cargo_test]
fn reuse_panic_pm() {
    // foo(panic) -> bar(panic)
    // somepm(nopanic) -> bar(nopanic)
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"

                [dependencies]
                bar = { path = "bar" }
                somepm = { path = "somepm" }

                [profile.dev]
                panic = "abort"
            "#,
        )
        .file("src/lib.rs", "extern crate bar;")
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.0.1"))
        .file("bar/src/lib.rs", "")
        .file(
            "somepm/Cargo.toml",
            r#"
                [package]
                name = "somepm"
                version = "0.0.1"
                edition = "2015"

                [lib]
                proc-macro = true

                [dependencies]
                bar = { path = "../bar" }
            "#,
        )
        .file("somepm/src/lib.rs", "extern crate bar;")
        .build();

    // bar is built once without panic (for proc-macro) and once with (for the
    // normal dependency).
    p.cargo("build -v")
        .with_stderr_data(
            str![[r#"
[LOCKING] 2 packages to latest compatible versions
[COMPILING] bar v0.0.1 ([ROOT]/foo/bar)
[RUNNING] `rustc --crate-name bar [..] -C panic=abort [..]
[RUNNING] `rustc --crate-name bar [..]
[COMPILING] somepm v0.0.1 ([ROOT]/foo/somepm)
[RUNNING] `rustc --crate-name somepm [..]
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..] -C panic=abort [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]
            .unordered(),
        )
        .run();
}

#[cargo_test]
fn bust_patched_dep() {
    Package::new("registry1", "0.1.0").publish();
    Package::new("registry2", "0.1.0")
        .dep("registry1", "0.1.0")
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                edition = "2015"

                [dependencies]
                registry2 = "0.1.0"

                [patch.crates-io]
                registry1 = { path = "reg1new" }
            "#,
        )
        .file("src/lib.rs", "")
        .file("reg1new/Cargo.toml", &basic_manifest("registry1", "0.1.0"))
        .file("reg1new/src/lib.rs", "")
        .build();

    p.cargo("build").run();
    if is_coarse_mtime() {
        sleep_ms(1000);
    }

    p.change_file("reg1new/src/lib.rs", "// modified");
    if is_coarse_mtime() {
        sleep_ms(1000);
    }

    p.cargo("build -v").with_stderr_data(str![[r#"
[DIRTY] registry1 v0.1.0 ([ROOT]/foo/reg1new): the file `reg1new/src/lib.rs` has changed ([TIME_DIFF_AFTER_LAST_BUILD])
[COMPILING] registry1 v0.1.0 ([ROOT]/foo/reg1new)
[RUNNING] `rustc --crate-name registry1 [..]
[DIRTY] registry2 v0.1.0: the dependency `registry1` was rebuilt
[COMPILING] registry2 v0.1.0
[RUNNING] `rustc --crate-name registry2 [..]
[DIRTY] foo v0.0.1 ([ROOT]/foo): the dependency `registry2` was rebuilt
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]).run();

    p.cargo("build -v")
        .with_stderr_data(str![[r#"
[FRESH] registry1 v0.1.0 ([ROOT]/foo/reg1new)
[FRESH] registry2 v0.1.0
[FRESH] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn rebuild_on_mid_build_file_modification() {
    let server = TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = server.local_addr().unwrap();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [workspace]
                members = ["root", "proc_macro_dep"]
            "#,
        )
        .file(
            "root/Cargo.toml",
            r#"
                [package]
                name = "root"
                version = "0.1.0"
                edition = "2015"
                authors = []

                [dependencies]
                proc_macro_dep = { path = "../proc_macro_dep" }
            "#,
        )
        .file(
            "root/src/lib.rs",
            r#"
                #[macro_use]
                extern crate proc_macro_dep;

                #[derive(Noop)]
                pub struct X;
            "#,
        )
        .file(
            "proc_macro_dep/Cargo.toml",
            r#"
                [package]
                name = "proc_macro_dep"
                version = "0.1.0"
                edition = "2015"
                authors = []

                [lib]
                proc-macro = true
            "#,
        )
        .file(
            "proc_macro_dep/src/lib.rs",
            &format!(
                r#"
                    extern crate proc_macro;

                    use std::io::Read;
                    use std::net::TcpStream;
                    use proc_macro::TokenStream;

                    #[proc_macro_derive(Noop)]
                    pub fn noop(_input: TokenStream) -> TokenStream {{
                        let mut stream = TcpStream::connect("{}").unwrap();
                        let mut v = Vec::new();
                        stream.read_to_end(&mut v).unwrap();
                        "".parse().unwrap()
                    }}
                "#,
                addr
            ),
        )
        .build();
    let root = p.root();

    let t = thread::spawn(move || {
        let socket = server.accept().unwrap().0;
        sleep_ms(1000);
        let mut file = OpenOptions::new()
            .write(true)
            .append(true)
            .open(root.join("root/src/lib.rs"))
            .unwrap();
        writeln!(file, "// modified").expect("Failed to append to root sources");
        drop(file);
        drop(socket);
        drop(server.accept().unwrap());
    });

    p.cargo("build")
        .with_stderr_data(str![[r#"
[COMPILING] proc_macro_dep v0.1.0 ([ROOT]/foo/proc_macro_dep)
[COMPILING] root v0.1.0 ([ROOT]/foo/root)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("build -v").with_stderr_data(str![[r#"
[FRESH] proc_macro_dep v0.1.0 ([ROOT]/foo/proc_macro_dep)
[DIRTY] root v0.1.0 ([ROOT]/foo/root): the file `root/src/lib.rs` has changed ([TIME_DIFF_AFTER_LAST_BUILD])
[COMPILING] root v0.1.0 ([ROOT]/foo/root)
[RUNNING] `rustc --crate-name root [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]).run();

    t.join().ok().unwrap();
}

#[cargo_test]
fn dirty_both_lib_and_test() {
    // This tests that all artifacts that depend on the results of a build
    // script will get rebuilt when the build script reruns, even for separate
    // commands. It does the following:
    //
    // 1. Project "foo" has a build script which will compile a small
    //    staticlib to link against. Normally this would use the `cc` crate,
    //    but here we just use rustc to avoid the `cc` dependency.
    // 2. Build the library.
    // 3. Build the unit test. The staticlib intentionally has a bad value.
    // 4. Rewrite the staticlib with the correct value.
    // 5. Build the library again.
    // 6. Build the unit test. This should recompile.

    let slib = |n| {
        format!(
            r#"
                #[no_mangle]
                pub extern "C" fn doit() -> i32 {{
                    return {};
                }}
            "#,
            n
        )
    };

    let p = project()
        .file(
            "src/lib.rs",
            r#"
                extern "C" {
                    fn doit() -> i32;
                }

                #[test]
                fn t1() {
                    assert_eq!(unsafe { doit() }, 1, "doit assert failure");
                }
            "#,
        )
        .file(
            "build.rs",
            r#"
                use std::env;
                use std::path::PathBuf;
                use std::process::Command;

                fn main() {
                    let rustc = env::var_os("RUSTC").unwrap();
                    let out_dir = PathBuf::from(env::var("OUT_DIR").unwrap());
                    assert!(
                        Command::new(rustc)
                            .args(&[
                                "--crate-type=staticlib",
                                "--out-dir",
                                out_dir.to_str().unwrap(),
                                "slib.rs"
                            ])
                            .status()
                            .unwrap()
                            .success(),
                        "slib build failed"
                    );
                    println!("cargo::rustc-link-lib=slib");
                    println!("cargo::rustc-link-search={}", out_dir.display());
                }
            "#,
        )
        .file("slib.rs", &slib(2))
        .build();

    p.cargo("build").run();

    // 2 != 1
    p.cargo("test --lib")
        .with_status(101)
        .with_stdout_data("...\n[..]doit assert failure[..]\n...")
        .run();

    if is_coarse_mtime() {
        // #5918
        sleep_ms(1000);
    }
    // Fix the mistake.
    p.change_file("slib.rs", &slib(1));

    p.cargo("build").run();
    // This should recompile with the new static lib, and the test should pass.
    p.cargo("test --lib").run();
}

#[cargo_test]
fn script_fails_stay_dirty() {
    // Check if a script is aborted (such as hitting Ctrl-C) that it will re-run.
    // Steps:
    // 1. Build to establish fingerprints.
    // 2. Make a change that triggers the build script to re-run. Abort the
    //    script while it is running.
    // 3. Run the build again and make sure it re-runs the script.
    let p = project()
        .file(
            "build.rs",
            r#"
                mod helper;
                fn main() {
                    println!("cargo::rerun-if-changed=build.rs");
                    helper::doit();
                }
            "#,
        )
        .file("helper.rs", "pub fn doit() {}")
        .file("src/lib.rs", "")
        .build();

    p.cargo("build").run();
    if is_coarse_mtime() {
        sleep_ms(1000);
    }
    p.change_file("helper.rs", r#"pub fn doit() {panic!("Crash!");}"#);
    p.cargo("build")
        .with_stderr_data("...\n[..]Crash![..]\n...")
        .with_status(101)
        .run();
    // There was a bug where this second call would be "fresh".
    p.cargo("build")
        .with_stderr_data("...\n[..]Crash![..]\n...")
        .with_status(101)
        .run();
}

#[cargo_test]
fn simulated_docker_deps_stay_cached() {
    // Test what happens in docker where the nanoseconds are zeroed out.
    Package::new("regdep", "1.0.0").publish();
    Package::new("regdep_old_style", "1.0.0")
        .file("build.rs", "fn main() {}")
        .file("src/lib.rs", "")
        .publish();
    Package::new("regdep_env", "1.0.0")
        .file(
            "build.rs",
            r#"
            fn main() {
                println!("cargo::rerun-if-env-changed=SOMEVAR");
            }
            "#,
        )
        .file("src/lib.rs", "")
        .publish();
    Package::new("regdep_rerun", "1.0.0")
        .file(
            "build.rs",
            r#"
            fn main() {
                println!("cargo::rerun-if-changed=build.rs");
            }
            "#,
        )
        .file("src/lib.rs", "")
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "foo"
            version = "0.1.0"
            edition = "2015"

            [dependencies]
            pathdep = { path = "pathdep" }
            regdep = "1.0"
            regdep_old_style = "1.0"
            regdep_env = "1.0"
            regdep_rerun = "1.0"
            "#,
        )
        .file(
            "src/lib.rs",
            "
            extern crate pathdep;
            extern crate regdep;
            extern crate regdep_old_style;
            extern crate regdep_env;
            extern crate regdep_rerun;
            ",
        )
        .file("build.rs", "fn main() {}")
        .file("pathdep/Cargo.toml", &basic_manifest("pathdep", "1.0.0"))
        .file("pathdep/src/lib.rs", "")
        .build();

    p.cargo("build").run();

    let already_zero = {
        // This happens on HFS with 1-second timestamp resolution,
        // or other filesystems where it just so happens to write exactly on a
        // 1-second boundary.
        let metadata = fs::metadata(p.root().join("src/lib.rs")).unwrap();
        let mtime = FileTime::from_last_modification_time(&metadata);
        mtime.nanoseconds() == 0
    };

    // Recursively remove `nanoseconds` from every path.
    fn zeropath(path: &Path) {
        for entry in walkdir::WalkDir::new(path)
            .into_iter()
            .filter_map(|e| e.ok())
        {
            let metadata = fs::metadata(entry.path()).unwrap();
            let mtime = metadata.modified().unwrap();
            let mtime_duration = mtime.duration_since(SystemTime::UNIX_EPOCH).unwrap();
            let trunc_mtime = FileTime::from_unix_time(mtime_duration.as_secs() as i64, 0);
            let atime = metadata.accessed().unwrap();
            let atime_duration = atime.duration_since(SystemTime::UNIX_EPOCH).unwrap();
            let trunc_atime = FileTime::from_unix_time(atime_duration.as_secs() as i64, 0);
            if let Err(e) = filetime::set_file_times(entry.path(), trunc_atime, trunc_mtime) {
                // Windows doesn't allow changing filetimes on some things
                // (directories, other random things I'm not sure why). Just
                // ignore them.
                if e.kind() == std::io::ErrorKind::PermissionDenied {
                    println!("PermissionDenied filetime on {:?}", entry.path());
                } else {
                    panic!("FileTime error on {:?}: {:?}", entry.path(), e);
                }
            }
        }
    }
    zeropath(&p.root());
    zeropath(&paths::home());

    if already_zero {
        println!("already zero");
        // If it was already truncated, then everything stays fresh.
        p.cargo("build -v")
            .with_stderr_data(
                str![[r#"
[FRESH] pathdep [..]
[FRESH] regdep [..]
[FRESH] regdep_env [..]
[FRESH] regdep_old_style [..]
[FRESH] regdep_rerun [..]
[FRESH] foo [..]
[FINISHED] [..]

"#]]
                .unordered(),
            )
            .run();
    } else {
        println!("not already zero");
        // It is not ideal that `foo` gets recompiled, but that is the current
        // behavior. Currently mtimes are ignored for registry deps.
        //
        // Note that this behavior is due to the fact that `foo` has a build
        // script in "old" mode where it doesn't print `rerun-if-*`. In this
        // mode we use `Precalculated` to fingerprint a path dependency, where
        // `Precalculated` is an opaque string which has the most recent mtime
        // in it. It differs between builds because one has nsec=0 and the other
        // likely has a nonzero nsec. Hence, the rebuild.
        p.cargo("build -v")
            .with_stderr_data(
                str![[r#"
[FRESH] regdep [..]
[FRESH] pathdep [..]
[FRESH] regdep_env [..]
[DIRTY] foo v0.1.0 ([ROOT]/foo): the precalculated components changed
[COMPILING] foo v0.1.0 ([ROOT]/foo)
[FRESH] regdep_rerun [..]
[FRESH] regdep_old_style [..]
[RUNNING] `[ROOT]/foo/target/debug/build/foo-[HASH]/build-script-build`
[RUNNING] `rustc --crate-name foo [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]]
                .unordered(),
            )
            .run();
    }
}

#[cargo_test]
fn metadata_change_invalidates() {
    // (key, value, value-updated, env-var-name)
    let scenarios = [
        (
            "description",
            r#""foo""#,
            r#""foo_updated""#,
            "CARGO_PKG_DESCRIPTION",
        ),
        (
            "homepage",
            r#""foo""#,
            r#""foo_updated""#,
            "CARGO_PKG_HOMEPAGE",
        ),
        (
            "repository",
            r#""foo""#,
            r#""foo_updated""#,
            "CARGO_PKG_REPOSITORY",
        ),
        (
            "license",
            r#""foo""#,
            r#""foo_updated""#,
            "CARGO_PKG_LICENSE",
        ),
        (
            "license-file",
            r#""foo""#,
            r#""foo_updated""#,
            "CARGO_PKG_LICENSE_FILE",
        ),
        (
            "authors",
            r#"["foo"]"#,
            r#"["foo_updated"]"#,
            "CARGO_PKG_AUTHORS",
        ),
        (
            "rust-version",
            r#""1.0.0""#,
            r#""1.0.1""#,
            "CARGO_PKG_RUST_VERSION",
        ),
        ("readme", r#""foo""#, r#""foo_updated""#, "CARGO_PKG_README"),
    ];
    let base_cargo_toml = r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2015"
                "#;

    let p = project().build();
    for (key, value, value_updated, env_var) in scenarios {
        p.change_file("Cargo.toml", base_cargo_toml);
        p.change_file(
            "src/main.rs",
            &format!(
                r#"
            fn main() {{
                let output = env!("{env_var}");
                println!("{{output}}");
            }}
            "#
            ),
        );

        // Compile the first time
        p.cargo("build").run();

        // Update the manifest, rebuild, and verify the build was invalided
        p.change_file("Cargo.toml", &format!("{base_cargo_toml}\n{key} = {value}"));
        p.cargo("build -v")
            .with_stderr_data(format!(
                r#"[DIRTY] foo v0.1.0 ([ROOT]/foo): the environment variable {env_var} changed
[COMPILING] foo v0.1.0 ([ROOT]/foo)
[RUNNING] `rustc [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
"#
            ))
            .run();

        // Remove references to the metadata and rebuild
        p.change_file(
            "src/main.rs",
            r#"
            fn main() {
                println!("foo");
            }
            "#,
        );
        p.cargo("build").run();

        // Update the manifest value and verify the build is NOT invalidated.
        p.change_file(
            "Cargo.toml",
            &format!("{base_cargo_toml}\n{key} = {value_updated}"),
        );

        p.cargo("build -v")
            .with_stderr_data(str![[r#"
[FRESH] foo v0.1.0 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
            .run();
    }
}

#[cargo_test]
fn edition_change_invalidates() {
    const MANIFEST: &str = r#"
        [package]
        name = "foo"
        version = "0.1.0"
    "#;
    let p = project()
        .file("Cargo.toml", MANIFEST)
        .file("src/lib.rs", "")
        .build();
    p.cargo("build").run();
    p.change_file("Cargo.toml", &format!("{}edition = \"2018\"", MANIFEST));
    p.cargo("build")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.1.0 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.change_file(
        "Cargo.toml",
        &format!(
            r#"{}edition = "2018"
            [lib]
            edition = "2015"
            "#,
            MANIFEST
        ),
    );
    p.cargo("build")
        .with_stderr_data(str![[r#"
[WARNING] Cargo.toml: `edition` is set on library `foo` which is deprecated
[WARNING] `foo` (manifest) generated 1 warning
[COMPILING] foo v0.1.0 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("build -v")
        .with_stderr_data(str![[r#"
[WARNING] Cargo.toml: `edition` is set on library `foo` which is deprecated
[WARNING] `foo` (manifest) generated 1 warning
[FRESH] foo v0.1.0 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    assert_eq!(p.glob("target/debug/deps/libfoo-*.rlib").count(), 1);
}

#[cargo_test]
fn rename_with_path_deps() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.5.0"
                edition = "2015"
                authors = []

                [dependencies]
                a = { path = 'a' }
            "#,
        )
        .file("src/lib.rs", "extern crate a; pub fn foo() { a::foo(); }")
        .file(
            "a/Cargo.toml",
            r#"
                [package]
                name = "a"
                version = "0.5.0"
                edition = "2015"
                authors = []

                [dependencies]
                b = { path = 'b' }
            "#,
        )
        .file("a/src/lib.rs", "extern crate b; pub fn foo() { b::foo() }")
        .file(
            "a/b/Cargo.toml",
            r#"
                [package]
                name = "b"
                version = "0.5.0"
                edition = "2015"
                authors = []
            "#,
        )
        .file("a/b/src/lib.rs", "pub fn foo() { }");
    let p = p.build();

    p.cargo("build").run();

    // Now rename the root directory and rerun `cargo run`. Not only should we
    // not build anything but we also shouldn't crash.
    let mut new = p.root();
    new.pop();
    new.push("foo2");

    fs::rename(p.root(), &new).unwrap();

    p.cargo("build")
        .cwd(&new)
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn move_target_directory_with_path_deps() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.5.0"
                edition = "2015"
                authors = []

                [dependencies]
                a = { path = "a" }
            "#,
        )
        .file(
            "a/Cargo.toml",
            r#"
                [package]
                name = "a"
                version = "0.5.0"
                edition = "2015"
                authors = []
            "#,
        )
        .file("src/lib.rs", "extern crate a; pub use a::print_msg;")
        .file(
            "a/build.rs",
            r###"
                use std::env;
                use std::fs;
                use std::path::Path;

                fn main() {
                    println!("cargo::rerun-if-changed=build.rs");
                    let out_dir = env::var("OUT_DIR").unwrap();
                    let dest_path = Path::new(&out_dir).join("hello.rs");
                    fs::write(&dest_path, r#"
                        pub fn message() -> &'static str {
                            "Hello, World!"
                        }
                    "#).unwrap();
                }
            "###,
        )
        .file(
            "a/src/lib.rs",
            r#"
            include!(concat!(env!("OUT_DIR"), "/hello.rs"));
            pub fn print_msg() { message(); }
            "#,
        );
    let p = p.build();

    let mut parent = p.root();
    parent.pop();

    p.cargo("build").run();

    let new_target = p.root().join("target2");
    fs::rename(p.root().join("target"), &new_target).unwrap();

    p.cargo("build")
        .env("CARGO_TARGET_DIR", &new_target)
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn rerun_if_changes() {
    let p = project()
        .file(
            "build.rs",
            r#"
                fn main() {
                    println!("cargo::rerun-if-env-changed=FOO");
                    if std::env::var("FOO").is_ok() {
                        println!("cargo::rerun-if-env-changed=BAR");
                    }
                }
            "#,
        )
        .file("src/lib.rs", "")
        .build();

    p.cargo("build").run();
    p.cargo("build")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("build -v")
        .env("FOO", "1")
        .with_stderr_data(str![[r#"
[DIRTY] foo v0.0.1 ([ROOT]/foo): the env variable FOO changed
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `[ROOT]/foo/target/debug/build/foo-[HASH]/build-script-build`
[RUNNING] `rustc [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("build")
        .env("FOO", "1")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("build -v")
        .env("FOO", "1")
        .env("BAR", "1")
        .with_stderr_data(str![[r#"
[DIRTY] foo v0.0.1 ([ROOT]/foo): the env variable BAR changed
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `[ROOT]/foo/target/debug/build/foo-[HASH]/build-script-build`
[RUNNING] `rustc [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("build")
        .env("FOO", "1")
        .env("BAR", "1")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("build -v")
        .env("BAR", "2")
        .with_stderr_data(str![[r#"
[DIRTY] foo v0.0.1 ([ROOT]/foo): the env variable FOO changed
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `[ROOT]/foo/target/debug/build/foo-[HASH]/build-script-build`
[RUNNING] `rustc [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("build")
        .env("BAR", "2")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn channel_shares_filenames() {
    // Test that different "nightly" releases use the same output filename.

    // Create separate rustc binaries to emulate running different toolchains.
    let nightly1 = format!(
        "\
rustc 1.44.0-nightly (38114ff16 2020-03-21)
binary: rustc
commit-hash: 38114ff16e7856f98b2b4be7ab4cd29b38bed59a
commit-date: 2020-03-21
host: {}
release: 1.44.0-nightly
LLVM version: 9.0
",
        rustc_host()
    );

    let nightly2 = format!(
        "\
rustc 1.44.0-nightly (a5b09d354 2020-03-31)
binary: rustc
commit-hash: a5b09d35473615e7142f5570f5c5fad0caf68bd2
commit-date: 2020-03-31
host: {}
release: 1.44.0-nightly
LLVM version: 9.0
",
        rustc_host()
    );

    let beta1 = format!(
        "\
rustc 1.43.0-beta.3 (4c587bbda 2020-03-25)
binary: rustc
commit-hash: 4c587bbda04ab55aaf56feab11dfdfe387a85d7a
commit-date: 2020-03-25
host: {}
release: 1.43.0-beta.3
LLVM version: 9.0
",
        rustc_host()
    );

    let beta2 = format!(
        "\
rustc 1.42.0-beta.5 (4e1c5f0e9 2020-02-28)
binary: rustc
commit-hash: 4e1c5f0e9769a588b91c977e3d81e140209ef3a2
commit-date: 2020-02-28
host: {}
release: 1.42.0-beta.5
LLVM version: 9.0
",
        rustc_host()
    );

    let stable1 = format!(
        "\
rustc 1.42.0 (b8cedc004 2020-03-09)
binary: rustc
commit-hash: b8cedc00407a4c56a3bda1ed605c6fc166655447
commit-date: 2020-03-09
host: {}
release: 1.42.0
LLVM version: 9.0
",
        rustc_host()
    );

    let stable2 = format!(
        "\
rustc 1.41.1 (f3e1a954d 2020-02-24)
binary: rustc
commit-hash: f3e1a954d2ead4e2fc197c7da7d71e6c61bad196
commit-date: 2020-02-24
host: {}
release: 1.41.1
LLVM version: 9.0
",
        rustc_host()
    );

    let compiler = project()
        .at("compiler")
        .file("Cargo.toml", &basic_manifest("compiler", "0.1.0"))
        .file(
            "src/main.rs",
            r#"
            fn main() {
                if std::env::args_os().any(|a| a == "-vV") {
                    print!("{}", env!("FUNKY_VERSION_TEST"));
                    return;
                }
                let mut cmd = std::process::Command::new("rustc");
                cmd.args(std::env::args_os().skip(1));
                assert!(cmd.status().unwrap().success());
            }
            "#,
        )
        .build();

    let makeit = |version, vv| {
        // Force a rebuild.
        compiler.target_debug_dir().join("deps").rm_rf();
        compiler.cargo("build").env("FUNKY_VERSION_TEST", vv).run();
        fs::rename(compiler.bin("compiler"), compiler.bin(version)).unwrap();
    };
    makeit("nightly1", nightly1);
    makeit("nightly2", nightly2);
    makeit("beta1", beta1);
    makeit("beta2", beta2);
    makeit("stable1", stable1);
    makeit("stable2", stable2);

    // Run `cargo check` with different rustc versions to observe its behavior.
    let p = project().file("src/lib.rs", "").build();

    // Runs `cargo check` and returns the rmeta filename created.
    // Checks that the freshness matches the given value.
    let check = |version, fresh| -> String {
        let output = p
            .cargo("check --message-format=json")
            .env("RUSTC", compiler.bin(version))
            .run();
        // Collect the filenames generated.
        let mut artifacts: Vec<_> = std::str::from_utf8(&output.stdout)
            .unwrap()
            .lines()
            .filter_map(|line| {
                let value: serde_json::Value = serde_json::from_str(line).unwrap();
                if value["reason"].as_str().unwrap() == "compiler-artifact" {
                    assert_eq!(value["fresh"].as_bool().unwrap(), fresh);
                    let filenames = value["filenames"].as_array().unwrap();
                    assert_eq!(filenames.len(), 1);
                    Some(filenames[0].to_string())
                } else {
                    None
                }
            })
            .collect();
        // Should only generate one rmeta file.
        assert_eq!(artifacts.len(), 1);
        artifacts.pop().unwrap()
    };

    let nightly1_name = check("nightly1", false);
    assert_eq!(check("nightly1", true), nightly1_name);
    assert_eq!(check("nightly2", false), nightly1_name); // same as before
    assert_eq!(check("nightly2", true), nightly1_name);
    // Should rebuild going back to nightly1.
    assert_eq!(check("nightly1", false), nightly1_name);

    let beta1_name = check("beta1", false);
    assert_ne!(beta1_name, nightly1_name);
    assert_eq!(check("beta1", true), beta1_name);
    assert_eq!(check("beta2", false), beta1_name); // same as before
    assert_eq!(check("beta2", true), beta1_name);
    // Should rebuild going back to beta1.
    assert_eq!(check("beta1", false), beta1_name);

    let stable1_name = check("stable1", false);
    assert_ne!(stable1_name, nightly1_name);
    assert_ne!(stable1_name, beta1_name);
    let stable2_name = check("stable2", false);
    assert_ne!(stable1_name, stable2_name);
    // Check everything is fresh.
    assert_eq!(check("stable1", true), stable1_name);
    assert_eq!(check("stable2", true), stable2_name);
    assert_eq!(check("beta1", true), beta1_name);
    assert_eq!(check("nightly1", true), nightly1_name);
}

#[cargo_test]
fn linking_interrupted() {
    // Interrupt during the linking phase shouldn't leave test executable as "fresh".

    // This is used to detect when linking starts, then to pause the linker so
    // that the test can kill cargo.
    let link_listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let link_addr = link_listener.local_addr().unwrap();

    // This is used to detect when rustc exits.
    let rustc_listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let rustc_addr = rustc_listener.local_addr().unwrap();

    // Create a linker that we can interrupt.
    let linker = project()
        .at("linker")
        .file("Cargo.toml", &basic_manifest("linker", "1.0.0"))
        .file(
            "src/main.rs",
            &r#"
            fn main() {
                // Figure out the output filename.
                let output = match std::env::args().find(|a| a.starts_with("/OUT:")) {
                    Some(s) => s[5..].to_string(),
                    None => {
                        let mut args = std::env::args();
                        loop {
                            if args.next().unwrap() == "-o" {
                                break;
                            }
                        }
                        args.next().unwrap()
                    }
                };
                std::fs::remove_file(&output).unwrap();
                std::fs::write(&output, "").unwrap();
                // Tell the test that we are ready to be interrupted.
                let mut socket = std::net::TcpStream::connect("__ADDR__").unwrap();
                // Wait for the test to kill us.
                std::thread::sleep(std::time::Duration::new(60, 0));
            }
            "#
            .replace("__ADDR__", &link_addr.to_string()),
        )
        .build();
    linker.cargo("build").run();

    // Create a wrapper around rustc that will tell us when rustc is finished.
    let rustc = project()
        .at("rustc-waiter")
        .file("Cargo.toml", &basic_manifest("rustc-waiter", "1.0.0"))
        .file(
            "src/main.rs",
            &r#"
            fn main() {
                let mut conn = None;
                // Check for a normal build (not -vV or --print).
                if std::env::args().any(|arg| arg == "t1") {
                    // Tell the test that rustc has started.
                    conn = Some(std::net::TcpStream::connect("__ADDR__").unwrap());
                }
                let status = std::process::Command::new("rustc")
                    .args(std::env::args().skip(1))
                    .status()
                    .expect("rustc to run");
                std::process::exit(status.code().unwrap_or(1));
            }
            "#
            .replace("__ADDR__", &rustc_addr.to_string()),
        )
        .build();
    rustc.cargo("build").run();

    // Build it once so that the fingerprint gets saved to disk.
    let p = project()
        .file("src/lib.rs", "")
        .file("tests/t1.rs", "")
        .build();
    p.cargo("test --test t1 --no-run").run();

    // Make a change, start a build, then interrupt it.
    p.change_file("src/lib.rs", "// modified");
    let linker_env = format!("CARGO_TARGET_{}_LINKER", rustc_host_env());
    // NOTE: This assumes that the paths to the linker or rustc are not in the
    // fingerprint. But maybe they should be?
    let mut cmd = p
        .cargo("test --test t1 --no-run")
        .env(&linker_env, linker.bin("linker"))
        .env("RUSTC", rustc.bin("rustc-waiter"))
        .build_command();
    let mut child = cmd
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .env("__CARGO_TEST_SETSID_PLEASE_DONT_USE_ELSEWHERE", "1")
        .spawn()
        .unwrap();
    // Wait for rustc to start.
    let mut rustc_conn = rustc_listener.accept().unwrap().0;
    // Wait for linking to start.
    drop(link_listener.accept().unwrap());

    // Interrupt the child.
    death::ctrl_c(&mut child);
    assert!(!child.wait().unwrap().success());
    // Wait for rustc to exit. If we don't wait, then the command below could
    // start while rustc is still being torn down.
    let mut buf = [0];
    drop(rustc_conn.read_exact(&mut buf));

    // Build again, shouldn't be fresh.
    p.cargo("test --test t1 -v")
        .with_stderr_data(str![[r#"
[DIRTY] foo v0.0.1 ([ROOT]/foo): the config settings changed
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..]
[RUNNING] `rustc --crate-name t1 [..]
[FINISHED] `test` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s
[RUNNING] `[ROOT]/foo/target/debug/deps/t1-[HASH][EXE]`

"#]])
        .run();
}

#[cargo_test]
#[cfg_attr(
    not(all(target_arch = "x86_64", target_os = "windows", target_env = "msvc")),
    ignore
)]
fn lld_is_fresh() {
    // Check for bug when using lld linker that it remains fresh with dylib.
    let p = project()
        .file(
            ".cargo/config.toml",
            r#"
                [target.x86_64-pc-windows-msvc]
                linker = "rust-lld"
            "#,
        )
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2015"

                [lib]
                crate-type = ["dylib"]
            "#,
        )
        .file("src/lib.rs", "")
        .build();

    p.cargo("build").run();
    p.cargo("build -v")
        .with_stderr_data(str![[r#"
[FRESH] foo v0.1.0 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn env_in_code_causes_rebuild() {
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
        .file(
            "src/main.rs",
            r#"
                fn main() {
                    println!("{:?}", option_env!("FOO"));
                    println!("{:?}", option_env!("FOO\nBAR"));
                }
            "#,
        )
        .build();

    p.cargo("build").env_remove("FOO").run();
    p.cargo("build")
        .env_remove("FOO")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("build -v")
        .env("FOO", "bar")
        .with_stderr_data(str![[r#"
[DIRTY] foo v0.1.0 ([ROOT]/foo): the environment variable FOO changed
[COMPILING] foo v0.1.0 ([ROOT]/foo)
[RUNNING] `rustc [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("build")
        .env("FOO", "bar")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("build -v")
        .env("FOO", "baz")
        .with_stderr_data(str![[r#"
[DIRTY] foo v0.1.0 ([ROOT]/foo): the environment variable FOO changed
[COMPILING] foo v0.1.0 ([ROOT]/foo)
[RUNNING] `rustc [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("build")
        .env("FOO", "baz")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("build -v")
        .env_remove("FOO")
        .with_stderr_data(str![[r#"
[DIRTY] foo v0.1.0 ([ROOT]/foo): the environment variable FOO changed
[COMPILING] foo v0.1.0 ([ROOT]/foo)
[RUNNING] `rustc [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.cargo("build")
        .env_remove("FOO")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    let interesting = " #!$\nabc\r\\\t\u{8}\r\n";
    p.cargo("build").env("FOO", interesting).run();
    p.cargo("build")
        .env("FOO", interesting)
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("build").env("FOO\nBAR", interesting).run();
    p.cargo("build")
        .env("FOO\nBAR", interesting)
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn env_build_script_no_rebuild() {
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
        .file(
            "build.rs",
            r#"
                fn main() {
                    println!("cargo::rustc-env=FOO=bar");
                }
            "#,
        )
        .file(
            "src/main.rs",
            r#"
                fn main() {
                    println!("{:?}", env!("FOO"));
                }
            "#,
        )
        .build();

    p.cargo("build").run();
    p.cargo("build")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn cargo_env_changes() {
    // Checks that changes to the env var CARGO in the dep-info file triggers
    // a rebuild.
    let p = project()
        .file("Cargo.toml", &basic_manifest("foo", "1.0.0"))
        .file(
            "src/main.rs",
            r#"
                fn main() {
                    println!("{:?}", env!("CARGO"));
                }
            "#,
        )
        .build();

    let cargo_exe = crate::utils::cargo_exe();
    let other_cargo_path = p.root().join(cargo_exe.file_name().unwrap());
    std::fs::hard_link(&cargo_exe, &other_cargo_path).unwrap();
    let other_cargo = || {
        let mut pb = cargo_test_support::process(&other_cargo_path);
        pb.cwd(p.root());
        cargo_test_support::execs().with_process_builder(pb)
    };

    p.cargo("check").run();
    other_cargo()
        .arg("check")
        .arg("-v")
        .with_stderr_data(str![[r#"
[DIRTY] foo v1.0.0 ([ROOT]/foo): the environment variable CARGO changed
[CHECKING] foo v1.0.0 ([ROOT]/foo)
[RUNNING] `rustc [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    // And just to confirm that without using env! it doesn't rebuild.
    p.change_file("src/main.rs", "fn main() {}");
    p.cargo("check")
        .with_stderr_data(str![[r#"
[CHECKING] foo v1.0.0 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    other_cargo()
        .arg("check")
        .arg("-v")
        .with_stderr_data(str![[r#"
[FRESH] foo v1.0.0 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn changing_linker() {
    // Changing linker should rebuild.
    let p = project().file("src/main.rs", "fn main() {}").build();
    p.cargo("build").run();
    let linker_env = format!("CARGO_TARGET_{}_LINKER", rustc_host_env());
    p.cargo("build --verbose")
        .env(&linker_env, "nonexistent-linker")
        .with_status(101)
        .with_stderr_data(str![[r#"
[DIRTY] foo v0.0.1 ([ROOT]/foo): the config settings changed
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..] -C linker=nonexistent-linker [..]`
[ERROR] linker `nonexistent-linker` not found
...
"#]])
        .run();
}

#[cargo_test]
fn verify_source_before_recompile() {
    Package::new("bar", "0.1.0")
        .file("src/lib.rs", "")
        .publish();
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2015"

                [dependencies]
                bar = "0.1.0"
            "#,
        )
        .file("src/lib.rs", "")
        .build();

    p.cargo("vendor --respect-source-config").run();
    p.change_file(
        ".cargo/config.toml",
        r#"
            [source.crates-io]
            replace-with = 'vendor'

            [source.vendor]
            directory = 'vendor'
        "#,
    );
    // Sanity check: vendoring works correctly.
    p.cargo("check --verbose")
        .with_stderr_data(str![[r#"
[CHECKING] bar v0.1.0
[RUNNING] `rustc --crate-name bar [..] [ROOT]/foo/vendor/bar/src/lib.rs [..]
[CHECKING] foo v0.1.0 ([ROOT]/foo)
[RUNNING] `rustc --crate-name foo [..] src/lib.rs [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    // Now modify vendored crate.
    p.change_file(
        "vendor/bar/src/lib.rs",
        r#"compile_error!("You shall not pass!");"#,
    );
    // Should ignore modified sources without any recompile.
    p.cargo("check --verbose")
        .with_stderr_data(str![[r#"
[FRESH] bar v0.1.0
[FRESH] foo v0.1.0 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    // Add a `RUSTFLAGS` to trigger a recompile.
    //
    // Cargo should refuse to build because of checksum verification failure.
    // Cargo shouldn't recompile dependency `bar`.
    p.cargo("check --verbose")
        .env("RUSTFLAGS", "-W warnings")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] the listed checksum of `[ROOT]/foo/vendor/bar/src/lib.rs` has changed:
expected: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
actual:   66e843918c1d4ea8231af814f9f958958808249d4407de01114acb730ecd9bdf

directory sources are not intended to be edited, if modifications are required then it is recommended that `[patch]` is used with a forked copy of the source

"#]])
        .run();
}

#[cargo_test]
fn skip_mtime_check_in_selected_cargo_home_subdirs() {
    let p = project()
        .at("cargo_home/registry/foo")
        .file("Cargo.toml", &basic_lib_manifest("foo"))
        .file("src/lib.rs", "")
        .build();
    let project_root = p.root();
    let cargo_home = project_root.parent().unwrap().parent().unwrap();
    p.cargo("check -v")
        .env("CARGO_HOME", &cargo_home)
        .with_stderr_data(str![[r#"
[CHECKING] foo v0.5.0 ([ROOT]/cargo_home/registry/foo)
[RUNNING] `rustc --crate-name foo [..] src/lib.rs [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.change_file("src/lib.rs", "illegal syntax");
    p.cargo("check -v")
        .env("CARGO_HOME", &cargo_home)
        .with_stderr_data(str![[r#"
[FRESH] foo v0.5.0 ([ROOT]/cargo_home/registry/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn use_mtime_cache_in_cargo_home() {
    let p = project()
        .at("cargo_home/foo")
        .file("Cargo.toml", &basic_lib_manifest("foo"))
        .file("src/lib.rs", "")
        .build();
    let project_root = p.root();
    let cargo_home = project_root.parent().unwrap();
    p.cargo("check -v")
        .env("CARGO_HOME", &cargo_home)
        .with_stderr_data(str![[r#"
[CHECKING] foo v0.5.0 ([ROOT]/cargo_home/foo)
[RUNNING] `rustc --crate-name foo [..] src/lib.rs [..] src/lib.rs [..]
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.change_file("src/lib.rs", "illegal syntax");
    p.cargo("check -v")
        .env("CARGO_HOME", &cargo_home)
        .with_status(101)
        .with_stderr_data(str![[r#"
[DIRTY] foo v0.5.0 ([ROOT]/cargo_home/foo): the file `src/lib.rs` has changed ([TIME_DIFF_AFTER_LAST_BUILD])
[CHECKING] foo v0.5.0 ([ROOT]/cargo_home/foo)
[RUNNING] `rustc --crate-name foo [..] src/lib.rs [..]
...
[ERROR] could not compile `foo` (lib) due to 1 previous error
...
"#]])
        .run();
}

#[cargo_test]
fn incremental_build_script_execution_got_new_mtime_and_cargo_check() {
    // See https://github.com/rust-lang/cargo/issues/16104
    let p = project()
        .file("src/lib.rs", "")
        .file("touch-me", "")
        .file(
            "build.rs",
            r#"fn main() { println!("cargo::rerun-if-changed=touch-me") }"#,
        )
        .build();

    p.cargo("check")
        .env("CARGO_INCREMENTAL", "1")
        .with_stderr_data(str![[r#"
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    if is_coarse_mtime() {
        sleep_ms(1000);
    }

    p.change_file("touch-me", "oops");

    // The first one is expected to rerun build script
    p.cargo("check -v")
        .env("CARGO_INCREMENTAL", "1")
        .with_stderr_data(str![[r#"
[DIRTY] foo v0.0.1 ([ROOT]/foo): the file `touch-me` has changed ([TIME_DIFF_AFTER_LAST_BUILD])
[COMPILING] foo v0.0.1 ([ROOT]/foo)
[RUNNING] `[ROOT]/foo/target/debug/build/foo-[HASH]/build-script-build`
[RUNNING] `rustc --crate-name foo [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    // subsequent cargo check gets stuck...
    p.cargo("check -v")
        .env("CARGO_INCREMENTAL", "1")
        .with_stderr_data(str![[r#"
[FRESH] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();

    p.cargo("check -v")
        .env("CARGO_INCREMENTAL", "1")
        .with_stderr_data(str![[r#"
[FRESH] foo v0.0.1 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn symlink_to_package() {
    // Illustrates what happens when the path is a symlink, and the symlink
    // target changes.
    if !cargo_test_support::symlink_supported() {
        return;
    }
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                edition = "2015"

                [dependencies]
                bar = { path = "bar" }
            "#,
        )
        .file(
            "src/main.rs",
            r#"
                fn main() {
                    bar::bar();
                }
            "#,
        )
        .file("bar1/Cargo.toml", &basic_manifest("bar", "1.0.0"))
        .file(
            "bar1/src/lib.rs",
            r#"
                pub fn bar() {
                    println!("one");
                }
            "#,
        )
        .file("bar2/Cargo.toml", &basic_manifest("bar", "1.0.0"))
        .file(
            "bar2/src/lib.rs",
            r#"
                pub fn bar() {
                    println!("two");
                }
            "#,
        )
        .symlink_dir("bar1", "bar")
        .build();
    p.cargo("check")
        .with_stderr_data(str![[r#"
[LOCKING] 1 package to latest compatible version
[CHECKING] bar v1.0.0 ([ROOT]/foo/bar)
[CHECKING] foo v0.0.0 ([ROOT]/foo)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    let bar_path = p.root().join("bar");
    cargo_util::paths::remove_file(&bar_path).unwrap();
    p.symlink("bar2", "bar");
    // FIXME: This is not rebuilding when it should.
    p.cargo("check")
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

fn public_api_hash_wrapper() -> PathBuf {
    // The Cargo testsuite's rustc does not know about our fork's
    // `-Zpublic-api-hash`. Strip the flag and attach a deterministic hash to
    // rustc's metadata artifact notification so this test exercises Cargo's
    // transport and scheduling behavior independently.
    let wrapper = project()
        .at("public-api-hash-wrapper")
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "public-api-hash-wrapper"
                version = "0.1.0"
                edition = "2024"
            "#,
        )
        .file(
            "src/main.rs",
            r#"
                use std::env;
                use std::ffi::OsStr;
                use std::fs::OpenOptions;
                use std::io::{self, Write};
                use std::process::{Command, exit};

                fn main() {
                    let mut args = env::args_os().skip(1);
                    let rustc = args.next().expect("rustc path");
                    let args = args.collect::<Vec<_>>();
                    let crate_name = args
                        .windows(2)
                        .find(|args| args[0] == OsStr::new("--crate-name"))
                        .map(|args| &args[1]);
                    if let Some(path) = env::var_os("PUBLIC_API_HASH_WRAPPER_LOG")
                        && let Some(crate_name) = crate_name
                        && crate_name != OsStr::new("___")
                    {
                        let mut log = OpenOptions::new()
                            .create(true)
                            .append(true)
                            .open(path)
                            .expect("wrapper log should open");
                        writeln!(log, "{}", crate_name.to_string_lossy())
                            .expect("wrapper log should be writable");
                    }
                    let public_api_hash = if crate_name.is_some_and(|crate_name| {
                        env::var_os("PUBLIC_API_HASH_WRAPPER_CHANGED_CRATE")
                            .as_deref()
                            == Some(crate_name.as_os_str())
                    }) {
                        "11111111111111111111111111111111"
                    } else {
                        "00000000000000000000000000000000"
                    };
                    let args = args
                        .into_iter()
                        .filter(|arg| {
                            !matches!(
                                arg.to_str(),
                                Some(
                                    "-Zpublic-api-hash"
                                        | "-Zpublic-api-hash=no"
                                        | "-Zcache-proc-macros"
                                        | "-Zcache-proc-macros=no"
                                )
                            )
                        });
                    let output = Command::new(rustc)
                        .args(args)
                        .output()
                        .expect("rustc should run");

                    io::stdout().write_all(&output.stdout).unwrap();
                    let stderr = String::from_utf8(output.stderr).unwrap();
                    for line in stderr.lines() {
                        if line.contains("\"artifact\":")
                            && line.contains(".rmeta")
                            && let Some(prefix) = line.strip_suffix('}')
                        {
                            eprintln!(
                                "{prefix},\"public_api_hash\":{{\"version\":1,\
                                 \"value\":\"{public_api_hash}\"}}}}"
                            );
                        } else {
                            eprintln!("{line}");
                        }
                    }
                    exit(output.status.code().unwrap_or(1));
                }
            "#,
        )
        .build();
    wrapper
        .cargo("-Zohm-defaults=no build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .run();
    wrapper.bin("public-api-hash-wrapper")
}

#[cargo_test]
#[cfg(not(windows))]
fn early_cutoff_skips_dependent_rebuild() {
    let wrapper = public_api_hash_wrapper();

    // Changing a native library rebuilds its Rust wrapper with byte-identical
    // metadata. Intermediate Rust libraries can be reused, but the final
    // binary must still be relinked against the new native implementation.
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "app"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                middle = { path = "middle" }
            "#,
        )
        .file(
            "src/main.rs",
            "fn main() { println!(\"{}\", middle::value()); }",
        )
        .file(
            "middle/Cargo.toml",
            r#"
                [package]
                name = "middle"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                dep = { path = "../dep" }
            "#,
        )
        .file(
            "middle/src/lib.rs",
            "fn unused() {}\npub fn value() -> i32 { dep::value() }",
        )
        .file(
            "dep/Cargo.toml",
            r#"
                [package]
                name = "dep"
                version = "0.1.0"
                edition = "2021"
                build = "build.rs"
            "#,
        )
        .file(
            "dep/build.rs",
            r#"
                use std::env;
                use std::path::PathBuf;
                use std::process::Command;

                fn main() {
                    let out_dir =
                        PathBuf::from(env::var_os("OUT_DIR").expect("OUT_DIR should be set"));
                    let object = out_dir.join("native.o");
                    let archive = out_dir.join("libnative.a");
                    assert!(
                        Command::new("cc")
                            .args(["-c", "native.c", "-o"])
                            .arg(&object)
                            .status()
                            .expect("cc should run")
                            .success()
                    );
                    assert!(
                        Command::new("ar")
                            .arg("rcs")
                            .arg(&archive)
                            .arg(&object)
                            .status()
                            .expect("ar should run")
                            .success()
                    );
                    println!("cargo::rerun-if-changed=native.c");
                    println!("cargo::rustc-link-search=native={}", out_dir.display());
                    println!("cargo::rustc-link-lib=static=native");
                }
            "#,
        )
        .file(
            "dep/src/lib.rs",
            r#"
                unsafe extern "C" {
                    fn native_value() -> i32;
                }

                #[inline(never)]
                pub fn value() -> i32 {
                    // SAFETY: `native_value` is defined by `native.c`, which is
                    // linked by this package's build script.
                    unsafe { native_value() }
                }
            "#,
        )
        .file("dep/native.c", "int native_value(void) { return 1; }")
        .build();

    p.cargo("build")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .run();
    p.process(&p.bin("app"))
        .with_stdout_data(str![[r#"
1

"#]])
        .run();

    sleep_ms(1000);
    p.change_file("dep/native.c", "int native_value(void) { return 2; }");

    // `middle` can be reused, while the final executable must be rebuilt.
    p.cargo("build -v")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .with_stderr_data(str![[r#"
[DIRTY] dep v0.1.0 ([ROOT]/foo/dep): the file `dep/native.c` has changed ([TIME_DIFF_AFTER_LAST_BUILD])
[COMPILING] dep v0.1.0 ([ROOT]/foo/dep)
[RUNNING] `[ROOT]/foo/target/debug/build/dep-[HASH]/build-script-build`
[RUNNING] `[..]/public-api-hash-wrapper[EXE] rustc --crate-name dep [..]`
[DIRTY] middle v0.1.0 ([ROOT]/foo/middle): the dependency `dep` was rebuilt
[COMPILING] middle v0.1.0 ([ROOT]/foo/middle)
[WARNING] function `unused` is never used
 --> middle/src/lib.rs:1:4
  |
1 | fn unused() {}
  |    ^^^^^^
  |
  = [NOTE] `#[warn(dead_code)]` (part of `#[warn(unused)]`) on by default

[WARNING] `middle` (lib) generated 1 warning
[DIRTY] app v0.1.0 ([ROOT]/foo): the dependency `middle` was rebuilt
[COMPILING] app v0.1.0 ([ROOT]/foo)
[RUNNING] `[..]/public-api-hash-wrapper[EXE] rustc --crate-name app [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    p.process(&p.bin("app"))
        .with_stdout_data(str![[r#"
2

"#]])
        .run();

    sleep_ms(1000);
    p.change_file("dep/native.c", "int native_value(void) { return 3; }");

    // Replayed diagnostics must retain their normal policy effects, not merely be displayed.
    p.cargo("build")
        .arg("--config")
        .arg("build.warnings='deny'")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .with_stderr_data(str![[r#"
[COMPILING] dep v0.1.0 ([ROOT]/foo/dep)
[COMPILING] middle v0.1.0 ([ROOT]/foo/middle)
[WARNING] function `unused` is never used
 --> middle/src/lib.rs:1:4
  |
1 | fn unused() {}
  |    ^^^^^^
  |
  = [NOTE] `#[warn(dead_code)]` (part of `#[warn(unused)]`) on by default

[ERROR] `middle` (lib) generated 1 warning
[ERROR] warnings are denied by `build.warnings` configuration

"#]])
        .with_status(101)
        .run();

    sleep_ms(1000);
    p.change_file(
        "dep/src/lib.rs",
        r#"
            unsafe extern "C" {
                fn native_value() -> i32;
            }

            #[inline(never)]
            pub fn value() -> i32 {
                // SAFETY: `native_value` is defined by `native.c`, which is
                // linked by this package's build script.
                let value = unsafe { native_value() };
                value
            }
        "#,
    );
    p.change_file(
        "middle/src/lib.rs",
        "pub fn value() -> i32 { dep::value() + 0 }",
    );

    // The leaf's public API hash is unchanged, but the middle crate also has
    // a local source change and therefore must not be skipped.
    p.cargo("build -v")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .with_stderr_data(str![[r#"
[DIRTY] dep v0.1.0 ([ROOT]/foo/dep): the file `dep/src/lib.rs` has changed ([TIME_DIFF_AFTER_LAST_BUILD])
[COMPILING] dep v0.1.0 ([ROOT]/foo/dep)
[RUNNING] `[..]/public-api-hash-wrapper[EXE] rustc --crate-name dep [..]`
[DIRTY] middle v0.1.0 ([ROOT]/foo/middle): the file `middle/src/lib.rs` has changed ([TIME_DIFF_AFTER_LAST_BUILD])
[COMPILING] middle v0.1.0 ([ROOT]/foo/middle)
[RUNNING] `[..]/public-api-hash-wrapper[EXE] rustc --crate-name middle [..]`
[DIRTY] app v0.1.0 ([ROOT]/foo): the dependency `middle` was rebuilt
[COMPILING] app v0.1.0 ([ROOT]/foo)
[RUNNING] `[..]/public-api-hash-wrapper[EXE] rustc --crate-name app [..]`
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

fn assert_early_cutoff_checks_dependents(
    command: &str,
    rustflags: Option<&str>,
    expected_invocations: &str,
) {
    let wrapper = public_api_hash_wrapper();
    let p = project()
        .at("check-workspace")
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "app"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                middle = { path = "middle" }
            "#,
        )
        .file(
            "src/lib.rs",
            r#"
                pub fn value() -> i32 {
                    middle::value()
                }

                #[test]
                fn value_is_positive() {
                    assert!(value() > 0);
                }
            "#,
        )
        .file(
            "middle/Cargo.toml",
            r#"
                [package]
                name = "middle"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                dep = { path = "../dep" }
            "#,
        )
        .file(
            "middle/src/lib.rs",
            "pub fn value() -> i32 { dep::value() }",
        )
        .file("dep/Cargo.toml", &basic_manifest("dep", "0.1.0"))
        .file("dep/src/lib.rs", "pub fn value() -> i32 { 1 }")
        .build();
    let log = p.root().join("public-api-hash-wrapper.log");

    let mut initial = p.cargo(command);
    if command.contains("ohm-defaults") {
        initial.masquerade_as_nightly_cargo(&["ohm-defaults"]);
    }
    initial
        .env("PUBLIC_API_HASH_WRAPPER_LOG", &log)
        .env("RUSTC_WRAPPER", &wrapper);
    if let Some(rustflags) = rustflags {
        initial.env("RUSTFLAGS", rustflags);
    }
    initial.run();

    fs::write(&log, "").unwrap();
    if is_coarse_mtime() {
        sleep_ms(1000);
    }
    p.change_file("dep/src/lib.rs", "pub fn value() -> i32 { 2 }");
    let mut rebuilt = p.cargo(command);
    if command.contains("ohm-defaults") {
        rebuilt.masquerade_as_nightly_cargo(&["ohm-defaults"]);
    }
    rebuilt
        .env("PUBLIC_API_HASH_WRAPPER_LOG", &log)
        .env("RUSTC_WRAPPER", &wrapper);
    if let Some(rustflags) = rustflags {
        rebuilt.env("RUSTFLAGS", rustflags);
    }
    rebuilt.run();
    assert_eq!(fs::read_to_string(&log).unwrap(), expected_invocations);
}

#[cargo_test]
fn early_cutoff_skips_check_dependents() {
    assert_early_cutoff_checks_dependents("check", Some("-Zpublic-api-hash"), "dep\n");
}

#[cargo_test]
fn early_cutoff_skips_check_test_dependents() {
    // Clippy schedules the same Check units, including test-mode units for
    // local test targets when invoked with `--tests`.
    assert_early_cutoff_checks_dependents("check --tests", Some("-Zpublic-api-hash"), "dep\n");
}

#[cargo_test]
fn ohm_defaults_enable_check_early_cutoff() {
    assert_early_cutoff_checks_dependents("-Zohm-defaults check", None, "dep\n");
}

#[cargo_test]
fn ohm_defaults_respect_public_api_hash_opt_out() {
    assert_early_cutoff_checks_dependents(
        "-Zohm-defaults check",
        Some("-Zpublic-api-hash=no"),
        "dep\nmiddle\napp\n",
    );
}

#[cargo_test]
fn disabled_ohm_defaults_do_not_enable_check_early_cutoff() {
    assert_early_cutoff_checks_dependents("-Zohm-defaults=no check", None, "dep\nmiddle\napp\n");
}

#[cargo_test]
fn disabled_ohm_defaults_preserve_explicit_public_api_hash() {
    assert_early_cutoff_checks_dependents(
        "-Zohm-defaults=no check",
        Some("-Zpublic-api-hash"),
        "dep\n",
    );
}

fn assert_early_cutoff_rechecks_transitive_trait_implementations(
    command: &str,
    rebuild_producer_separately: bool,
) {
    let wrapper = public_api_hash_wrapper();
    let p = project()
        .at("transitive-trait-workspace")
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "app"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                middle = { path = "middle" }
            "#,
        )
        .file(
            "src/lib.rs",
            r#"
                use middle::{Candidate, External};

                trait Local {
                    fn selected(&self) -> usize;
                }

                impl Local for External {
                    fn selected(&self) -> usize {
                        1
                    }
                }

                pub fn selected() -> usize {
                    External.selected()
                }
            "#,
        )
        .file(
            "middle/Cargo.toml",
            r#"
                [package]
                name = "middle"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                helper = { path = "../helper" }
                producer = { path = "../producer" }
            "#,
        )
        .file(
            "middle/src/lib.rs",
            "pub use helper::Candidate;\npub use producer::External;\n",
        )
        .file(
            "producer/Cargo.toml",
            r#"
                [package]
                name = "producer"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                helper = { path = "../helper" }
            "#,
        )
        .file(
            "producer/src/lib.rs",
            r#"
                pub struct External;

                pub type ExistingReference = &'static dyn helper::Candidate;
            "#,
        )
        .file("helper/Cargo.toml", &basic_manifest("helper", "0.1.0"))
        .file(
            "helper/src/lib.rs",
            r#"
                pub trait Candidate {
                    fn selected(&self) -> usize;
                }
            "#,
        )
        .build();

    p.cargo(command)
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .run();

    if is_coarse_mtime() {
        sleep_ms(1000);
    }
    p.change_file(
        "producer/src/lib.rs",
        r#"
            pub struct External;

            pub type ExistingReference = &'static dyn helper::Candidate;

            impl helper::Candidate for External {
                fn selected(&self) -> usize {
                    2
                }
            }
        "#,
    );

    if rebuild_producer_separately {
        // A separate Cargo invocation updates the producer without updating its dependents.
        // During the full build below, the producer is fresh for this invocation even though its
        // metadata differs from what the intermediate crate was originally compiled against.
        p.cargo(&format!("{command} -p producer"))
            .env("RUSTC_WRAPPER", &wrapper)
            .env("RUSTFLAGS", "-Zpublic-api-hash")
            .env("PUBLIC_API_HASH_WRAPPER_CHANGED_CRATE", "producer")
            .run();
    }

    let expected = match (command, rebuild_producer_separately) {
        ("build", true) => str![[r#"
[COMPILING] middle v0.1.0 ([ROOT]/transitive-trait-workspace/middle)
[COMPILING] app v0.1.0 ([ROOT]/transitive-trait-workspace)
error[E0034]: multiple applicable items in scope
...
[ERROR] could not compile `app` (lib) due to 1 previous error

"#]],
        ("build", false) => str![[r#"
[COMPILING] producer v0.1.0 ([ROOT]/transitive-trait-workspace/producer)
[COMPILING] middle v0.1.0 ([ROOT]/transitive-trait-workspace/middle)
[COMPILING] app v0.1.0 ([ROOT]/transitive-trait-workspace)
error[E0034]: multiple applicable items in scope
...
[ERROR] could not compile `app` (lib) due to 1 previous error

"#]],
        ("check", true) => str![[r#"
[CHECKING] middle v0.1.0 ([ROOT]/transitive-trait-workspace/middle)
[CHECKING] app v0.1.0 ([ROOT]/transitive-trait-workspace)
error[E0034]: multiple applicable items in scope
...
[ERROR] could not compile `app` (lib) due to 1 previous error

"#]],
        ("check", false) => str![[r#"
[CHECKING] producer v0.1.0 ([ROOT]/transitive-trait-workspace/producer)
[CHECKING] middle v0.1.0 ([ROOT]/transitive-trait-workspace/middle)
[CHECKING] app v0.1.0 ([ROOT]/transitive-trait-workspace)
error[E0034]: multiple applicable items in scope
...
[ERROR] could not compile `app` (lib) due to 1 previous error

"#]],
        _ => panic!("unsupported command: {command}"),
    };
    p.cargo(command)
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .env("PUBLIC_API_HASH_WRAPPER_CHANGED_CRATE", "producer")
        .with_status(101)
        .with_stderr_data(expected)
        .run();
}

#[cargo_test]
fn early_cutoff_rechecks_transitive_trait_implementations() {
    assert_early_cutoff_rechecks_transitive_trait_implementations("check", false);
}

#[cargo_test]
fn early_cutoff_rechecks_previously_rebuilt_transitive_trait_implementations_in_checks() {
    assert_early_cutoff_rechecks_transitive_trait_implementations("check", true);
}

#[cargo_test]
fn early_cutoff_rechecks_transitive_trait_implementations_in_builds() {
    assert_early_cutoff_rechecks_transitive_trait_implementations("build", false);
}

#[cargo_test]
fn early_cutoff_rechecks_previously_rebuilt_transitive_trait_implementations_in_builds() {
    assert_early_cutoff_rechecks_transitive_trait_implementations("build", true);
}

fn assert_early_cutoff_rechecks_previously_changed_dependency(
    command: &str,
    rebuild_changed_dependency_again: bool,
) {
    let wrapper = public_api_hash_wrapper();
    let p = project()
        .at("previously-changed-dependency")
        .file(
            "Cargo.toml",
            r#"
                [workspace]
                members = ["producer_a", "producer_b", "consumer", "app"]
                resolver = "2"
            "#,
        )
        .file(
            "producer_a/Cargo.toml",
            &basic_manifest("producer_a", "0.1.0"),
        )
        .file(
            "producer_a/src/lib.rs",
            "pub fn value() -> i32 { 1 }\npub fn stable() -> i32 { 10 }\n",
        )
        .file(
            "producer_b/Cargo.toml",
            &basic_manifest("producer_b", "0.1.0"),
        )
        .file("producer_b/src/lib.rs", "pub fn value() -> i32 { 2 }\n")
        .file(
            "consumer/Cargo.toml",
            r#"
                [package]
                name = "consumer"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                producer_a = { path = "../producer_a" }
                producer_b = { path = "../producer_b" }
            "#,
        )
        .file(
            "consumer/src/lib.rs",
            "pub fn value() -> i32 { producer_a::value() + producer_b::value() }\n",
        )
        .file(
            "app/Cargo.toml",
            r#"
                [package]
                name = "app"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                producer_a = { path = "../producer_a" }
            "#,
        )
        .file(
            "app/src/lib.rs",
            "pub fn value() -> i32 { producer_a::stable() }\n",
        )
        .build();

    p.cargo(&format!("{command} -p consumer"))
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .run();

    if is_coarse_mtime() {
        sleep_ms(1000);
    }
    p.change_file(
        "producer_a/src/lib.rs",
        "pub fn value() -> &'static str { \"changed\" }\npub fn stable() -> i32 { 10 }\n",
    );
    p.cargo(&format!("{command} -p app"))
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .env("PUBLIC_API_HASH_WRAPPER_CHANGED_CRATE", "producer_a")
        .run();

    if is_coarse_mtime() {
        sleep_ms(1000);
    }
    if rebuild_changed_dependency_again {
        // Its public API is unchanged in this invocation, but still differs from the metadata
        // recorded when `consumer` was compiled before the previous invocation.
        p.change_file(
            "producer_a/src/lib.rs",
            "pub fn value() -> &'static str { \"changed again\" }\npub fn stable() -> i32 { 10 }\n",
        );
    } else {
        p.change_file("producer_b/src/lib.rs", "pub fn value() -> i32 { 3 }\n");
    }
    p.cargo(&format!("{command} -p consumer"))
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .env("PUBLIC_API_HASH_WRAPPER_CHANGED_CRATE", "producer_a")
        .env("CARGO_BUILD_JOBS", "1")
        .with_status(101)
        .with_stderr_data(str![[r#"
...
error[E0369]: cannot add `i32` to `&str`
...
[ERROR] could not compile `consumer` (lib) due to 1 previous error

"#]])
        .run();
}

#[cargo_test]
fn early_cutoff_rechecks_fresh_dependency_changed_by_previous_build() {
    assert_early_cutoff_rechecks_previously_changed_dependency("build", false);
}

#[cargo_test]
fn early_cutoff_rechecks_unchanged_dependency_changed_by_previous_build() {
    assert_early_cutoff_rechecks_previously_changed_dependency("build", true);
}

#[cargo_test]
fn early_cutoff_rechecks_fresh_dependency_changed_by_previous_check() {
    assert_early_cutoff_rechecks_previously_changed_dependency("check", false);
}

#[cargo_test]
fn early_cutoff_rechecks_unchanged_dependency_changed_by_previous_check() {
    assert_early_cutoff_rechecks_previously_changed_dependency("check", true);
}

fn assert_early_cutoff_rechecks_proc_macro_changed_by_previous_build(command: &str) {
    let wrapper = public_api_hash_wrapper();
    let p = project()
        .at("previously-changed-proc-macro")
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "consumer"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                macro_dep = { path = "macro_dep" }
                producer = { path = "producer" }
            "#,
        )
        .file(
            "src/lib.rs",
            "macro_dep::make_value!();\npub fn value() -> i32 { generated() + producer::value() }\n",
        )
        .file(
            "macro_dep/Cargo.toml",
            r#"
                [package]
                name = "macro_dep"
                version = "0.1.0"
                edition = "2024"

                [lib]
                proc-macro = true
            "#,
        )
        .file(
            "macro_dep/src/lib.rs",
            r#"
                use proc_macro::TokenStream;

                #[proc_macro]
                pub fn make_value(_: TokenStream) -> TokenStream {
                    "pub fn generated() -> i32 { 1 }"
                        .parse()
                        .expect("generated function should parse")
                }
            "#,
        )
        .file("producer/Cargo.toml", &basic_manifest("producer", "0.1.0"))
        .file("producer/src/lib.rs", "pub fn value() -> i32 { 2 }\n")
        .build();

    p.cargo(command)
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .run();

    if is_coarse_mtime() {
        sleep_ms(1000);
    }
    p.change_file(
        "macro_dep/src/lib.rs",
        r#"
            use proc_macro::TokenStream;

            #[proc_macro]
            pub fn make_value(_: TokenStream) -> TokenStream {
                "pub fn generated() -> i32 { \"changed\" }"
                    .parse()
                    .expect("generated function should parse")
            }
        "#,
    );
    p.cargo("build -p macro_dep")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .run();

    if is_coarse_mtime() {
        sleep_ms(1000);
    }
    p.change_file("producer/src/lib.rs", "pub fn value() -> i32 { 3 }\n");
    p.cargo(command)
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .with_status(101)
        .with_stderr_data(str![[r#"
...
error[E0308]: mismatched types
...
[ERROR] could not compile `consumer` (lib) due to 1 previous error

"#]])
        .run();
}

#[cargo_test]
fn early_cutoff_rechecks_proc_macro_changed_by_previous_build() {
    assert_early_cutoff_rechecks_proc_macro_changed_by_previous_build("build");
}

#[cargo_test]
fn early_cutoff_rechecks_proc_macro_changed_by_previous_check() {
    assert_early_cutoff_rechecks_proc_macro_changed_by_previous_build("check");
}

fn find_metadata_output(root: &Path, crate_name: &str) -> PathBuf {
    let prefix = format!("lib{crate_name}-");
    fs::read_dir(root.join("target/debug/deps"))
        .expect("dependency output directory should exist")
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .find(|path| {
            path.extension().and_then(|extension| extension.to_str()) == Some("rmeta")
                && path
                    .file_name()
                    .and_then(|name| name.to_str())
                    .is_some_and(|name| name.starts_with(&prefix))
        })
        .expect("metadata output should exist")
}

fn assert_private_dependency_rebuild_preserves_metadata_generation(command: &str) {
    let wrapper = public_api_hash_wrapper();
    let p = project()
        .at(&format!("private-metadata-generation-{command}"))
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "consumer"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                producer = { path = "producer" }
            "#,
        )
        .file(
            "src/lib.rs",
            "pub fn value() -> i32 { producer::value() }\n",
        )
        .file("producer/Cargo.toml", &basic_manifest("producer", "0.1.0"))
        .file("producer/src/lib.rs", "pub fn value() -> i32 { 1 }\n")
        .build();

    p.cargo(command)
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .run();

    let metadata = find_metadata_output(&p.root(), "producer");
    let initial_mtime = FileTime::from_last_modification_time(
        &fs::metadata(&metadata).expect("producer metadata should be readable"),
    );

    if is_coarse_mtime() {
        sleep_ms(1000);
    }
    p.change_file("producer/src/lib.rs", "pub fn value() -> i32 { 2 }\n");
    p.cargo(&format!("{command} -p producer"))
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .run();

    let rebuilt_mtime = FileTime::from_last_modification_time(
        &fs::metadata(&metadata).expect("rebuilt producer metadata should be readable"),
    );
    assert_eq!(rebuilt_mtime, initial_mtime);

    p.cargo(&format!("{command} -v"))
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .with_stderr_data(str![[r#"
[FRESH] producer v0.1.0 ([ROOT]/private-metadata-generation-[..]/producer)
[FRESH] consumer v0.1.0 ([ROOT]/private-metadata-generation-[..])
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn private_dependency_rebuild_preserves_build_metadata_generation() {
    assert_private_dependency_rebuild_preserves_metadata_generation("build");
}

#[cargo_test]
fn private_dependency_rebuild_preserves_check_metadata_generation() {
    assert_private_dependency_rebuild_preserves_metadata_generation("check");
}

fn assert_private_dependency_rebuild_propagates_link_generation(package: &str) {
    let wrapper = public_api_hash_wrapper();
    let p = project()
        .at(&format!("private-dependency-link-generation-{package}"))
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "app"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                middle = { path = "middle" }
            "#,
        )
        .file(
            "src/main.rs",
            "fn main() { println!(\"{}\", middle::value()); }\n",
        )
        .file(
            "middle/Cargo.toml",
            r#"
                [package]
                name = "middle"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                producer = { path = "../producer" }
            "#,
        )
        .file(
            "middle/src/lib.rs",
            "pub fn value() -> i32 { producer::value() }\n",
        )
        .file(
            "producer/Cargo.toml",
            r#"
                [package]
                name = "producer"
                version = "0.1.0"
                edition = "2024"
                build = "build.rs"
            "#,
        )
        .file(
            "producer/build.rs",
            r#"
                use std::env;
                use std::path::PathBuf;
                use std::process::Command;

                fn main() {
                    let out_dir =
                        PathBuf::from(env::var_os("OUT_DIR").expect("OUT_DIR should be set"));
                    let object = out_dir.join("native.o");
                    let archive = out_dir.join("libnative.a");
                    assert!(
                        Command::new("cc")
                            .args(["-c", "native.c", "-o"])
                            .arg(&object)
                            .status()
                            .expect("cc should run")
                            .success()
                    );
                    assert!(
                        Command::new("ar")
                            .arg("rcs")
                            .arg(&archive)
                            .arg(&object)
                            .status()
                            .expect("ar should run")
                            .success()
                    );
                    println!("cargo::rerun-if-changed=native.c");
                    println!("cargo::rustc-link-search=native={}", out_dir.display());
                    println!("cargo::rustc-link-lib=static=native");
                }
            "#,
        )
        .file(
            "producer/src/lib.rs",
            r#"
                unsafe extern "C" {
                    fn native_value() -> i32;
                }

                #[inline(never)]
                pub fn value() -> i32 {
                    // SAFETY: `native_value` is defined by the static archive
                    // generated by this package's build script.
                    unsafe { native_value() }
                }
            "#,
        )
        .file("producer/native.c", "int native_value(void) { return 1; }")
        .build();

    p.cargo("run --quiet")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .with_stdout_data(str![[r#"
1

"#]])
        .run();

    let metadata = find_metadata_output(&p.root(), "middle");
    let initial_mtime = FileTime::from_last_modification_time(
        &fs::metadata(&metadata).expect("middle metadata should be readable"),
    );

    if is_coarse_mtime() {
        sleep_ms(1000);
    }
    p.change_file("producer/native.c", "int native_value(void) { return 2; }");
    p.cargo(&format!("build -p {package}"))
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .run();

    let rebuilt_mtime = FileTime::from_last_modification_time(
        &fs::metadata(&metadata).expect("skipped middle metadata should be readable"),
    );
    assert_eq!(rebuilt_mtime, initial_mtime);

    // Its effective link generation must make the existing executable stale,
    // even though metadata-only intermediate crates do not recompile.
    p.cargo("run --quiet")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .with_stdout_data(str![[r#"
2

"#]])
        .run();
}

#[cargo_test]
#[cfg(not(windows))]
fn skipped_dependency_preserves_metadata_and_propagates_link_generation() {
    assert_private_dependency_rebuild_propagates_link_generation("middle");
}

#[cargo_test]
#[cfg(not(windows))]
fn separately_rebuilt_dependency_propagates_transitive_link_generation() {
    assert_private_dependency_rebuild_propagates_link_generation("producer");
}

#[cargo_test]
fn unchanged_check_metadata_does_not_fall_behind_rerun_build_script() {
    let wrapper = public_api_hash_wrapper();
    let p = project()
        .at("check-metadata-build-script-generation")
        .file("src/lib.rs", "pub fn value() -> i32 { 1 }\n")
        .file("touch-me", "initial")
        .file(
            "build.rs",
            r#"fn main() { println!("cargo::rerun-if-changed=touch-me") }"#,
        )
        .build();

    p.cargo("check")
        .env("CARGO_INCREMENTAL", "1")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .run();

    if is_coarse_mtime() {
        sleep_ms(1000);
    }
    p.change_file("touch-me", "updated");
    p.cargo("check")
        .env("CARGO_INCREMENTAL", "1")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .run();

    p.cargo("check -v")
        .env("CARGO_INCREMENTAL", "1")
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .with_stderr_data(str![[r#"
[FRESH] foo v0.0.1 ([ROOT]/check-metadata-build-script-generation)
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cfg(not(windows))]
fn relink_only_wrapper() -> PathBuf {
    // The testsuite compiler does not implement the public API hash or
    // separate-link flags used by this prototype. This wrapper attaches a
    // deterministic public hash and emulates rustc's `.rlink` protocol while
    // still running the real compiler for behavioral validation.
    let wrapper = project()
        .at("relink-only-wrapper")
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "relink-only-wrapper"
                version = "0.1.0"
                edition = "2024"
            "#,
        )
        .file(
            "src/main.rs",
            r#"
                use std::env;
                use std::ffi::{OsStr, OsString};
                use std::fs::{self, OpenOptions};
                use std::io::{self, Write};
                use std::path::{Path, PathBuf};
                use std::process::{Command, Output, exit};

                fn has_flag(args: &[OsString], name: &str) -> bool {
                    let combined = format!("-Z{name}");
                    args.iter().any(|arg| arg == OsStr::new(&combined))
                        || args.windows(2).any(|args| {
                            args[0] == OsStr::new("-Z") && args[1] == OsStr::new(name)
                        })
                }

                fn strip_flags(args: &[OsString]) -> Vec<OsString> {
                    let mut stripped = Vec::new();
                    let mut index = 0;
                    while index < args.len() {
                        if matches!(
                            args[index].to_str(),
                            Some("-Zpublic-api-hash" | "-Zcache-proc-macros")
                        ) {
                            index += 1;
                        } else if index + 1 < args.len()
                            && args[index] == OsStr::new("-Z")
                            && matches!(
                                args[index + 1].to_str(),
                                Some("no-link" | "link-only")
                            )
                        {
                            index += 2;
                        } else {
                            stripped.push(args[index].clone());
                            index += 1;
                        }
                    }
                    stripped
                }

                fn crate_name(args: &[OsString]) -> Option<&str> {
                    args.windows(2)
                        .find(|args| args[0] == OsStr::new("--crate-name"))
                        .and_then(|args| args[1].to_str())
                }

                fn log(kind: &str, args: &[OsString]) {
                    let Some(crate_name) = crate_name(args) else {
                        return;
                    };
                    if crate_name == "___" {
                        return;
                    }
                    let path = env::var_os("RELINK_WRAPPER_LOG")
                        .expect("RELINK_WRAPPER_LOG should be set");
                    let mut log = OpenOptions::new()
                        .create(true)
                        .append(true)
                        .open(path)
                        .expect("wrapper log should open");
                    writeln!(log, "{kind}:{crate_name}")
                        .expect("wrapper log should be writable");
                }

                fn run(rustc: &OsStr, args: &[OsString]) -> Output {
                    Command::new(rustc)
                        .args(args)
                        .output()
                        .expect("rustc should run")
                }

                fn emit(output: Output) -> ! {
                    io::stdout().write_all(&output.stdout).unwrap();
                    let stderr = String::from_utf8(output.stderr).unwrap();
                    for line in stderr.lines() {
                        if line.contains("\"artifact\":")
                            && line.contains(".rmeta")
                            && let Some(prefix) = line.strip_suffix('}')
                        {
                            eprintln!(
                                "{prefix},\"public_api_hash\":{{\"version\":1,\
                                 \"value\":\"00000000000000000000000000000000\"}}}}"
                            );
                        } else {
                            eprintln!("{line}");
                        }
                    }
                    exit(output.status.code().unwrap_or(1));
                }

                fn artifact_path(stderr: &[u8]) -> PathBuf {
                    let stderr = String::from_utf8_lossy(stderr);
                    stderr
                        .lines()
                        .filter(|line| !line.contains(".rmeta"))
                        .find_map(|line| {
                            let (_, rest) = line.split_once("\"artifact\":\"")?;
                            let (path, _) = rest.split_once('"')?;
                            Some(PathBuf::from(path))
                        })
                        .expect("rustc should report its executable artifact")
                }

                fn write_args(path: &Path, args: &[OsString]) {
                    let args = args
                        .iter()
                        .map(|arg| arg.to_str().expect("test arguments should be UTF-8"))
                        .collect::<Vec<_>>()
                        .join("\n");
                    fs::write(path, args).expect("saved rustc arguments should be writable");
                }

                fn read_args(path: &Path) -> Vec<OsString> {
                    fs::read_to_string(path)
                        .expect("saved rustc arguments should be readable")
                        .lines()
                        .map(OsString::from)
                        .collect()
                }

                fn main() {
                    let mut wrapper_args = env::args_os().skip(1);
                    let rustc = wrapper_args.next().expect("rustc path");
                    let args = wrapper_args.collect::<Vec<_>>();
                    let stripped = strip_flags(&args);

                    if has_flag(&args, "link-only") {
                        log("link", &args);
                        let rlink = args
                            .iter()
                            .find(|arg| Path::new(arg).extension() == Some(OsStr::new("rlink")))
                            .map(PathBuf::from)
                            .expect("link-only should receive an rlink");
                        let marker = rlink.with_extension("fresh-rlink");
                        if marker.exists() {
                            fs::remove_file(marker).unwrap();
                            exit(0);
                        }
                        let saved_args = read_args(&rlink.with_extension("relink-args"));
                        emit(run(&rustc, &saved_args));
                    }

                    if has_flag(&args, "no-link") {
                        log("codegen", &args);
                        let output = run(&rustc, &stripped);
                        if output.status.success() {
                            let artifact = artifact_path(&output.stderr);
                            let rlink = artifact.with_extension("rlink");
                            fs::write(&rlink, b"test rlink").unwrap();
                            fs::write(artifact.with_extension("fake.rcgu.o"), b"test object")
                                .unwrap();
                            fs::write(rlink.with_extension("fresh-rlink"), b"").unwrap();
                            write_args(&rlink.with_extension("relink-args"), &stripped);
                        }
                        emit(output);
                    }

                    log("compile", &args);
                    emit(run(&rustc, &stripped));
                }
            "#,
        )
        .build();
    wrapper.cargo("build").run();
    wrapper.bin("relink-only-wrapper")
}

#[cargo_test]
#[cfg(not(windows))]
fn relink_only_reuses_root_codegen() {
    let wrapper = relink_only_wrapper();
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "app"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                dep = { path = "dep" }
            "#,
        )
        .file(
            "src/main.rs",
            "fn main() { println!(\"{}\", dep::value()); }",
        )
        .file(
            "dep/Cargo.toml",
            r#"
                [package]
                name = "dep"
                version = "0.1.0"
                edition = "2024"
            "#,
        )
        .file("dep/src/lib.rs", "pub fn value() -> i32 { 1 }")
        .build();
    let log = p.root().join("relink-wrapper.log");

    p.cargo("-Zohm-defaults build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RELINK_WRAPPER_LOG", &log)
        .run();
    assert_eq!(
        fs::read_to_string(&log).unwrap(),
        "compile:dep\ncodegen:app\nlink:app\n"
    );

    fs::write(&log, "").unwrap();
    sleep_ms(1000);
    p.change_file("dep/src/lib.rs", "pub fn value() -> i32 { 2 }");
    p.cargo("-Zohm-defaults build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RELINK_WRAPPER_LOG", &log)
        .run();
    assert_eq!(fs::read_to_string(&log).unwrap(), "compile:dep\nlink:app\n");
    p.process(&p.bin("app"))
        .with_stdout_data(str![[r#"
2

"#]])
        .run();

    // A corrupt sidecar must fail closed and regenerate the codegen cache.
    let manifest = fs::read_dir(p.root().join("target/debug/deps"))
        .unwrap()
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .find(|path| {
            path.file_name()
                .and_then(OsStr::to_str)
                .is_some_and(|name| name.ends_with(".rlink-cache.json"))
        })
        .unwrap();
    fs::write(manifest, "corrupt").unwrap();
    fs::write(&log, "").unwrap();
    sleep_ms(1000);
    p.change_file("dep/src/lib.rs", "pub fn value() -> i32 { 3 }");
    p.cargo("-Zohm-defaults build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RELINK_WRAPPER_LOG", &log)
        .run();
    assert_eq!(
        fs::read_to_string(&log).unwrap(),
        "compile:dep\ncodegen:app\nlink:app\n"
    );
    p.process(&p.bin("app"))
        .with_stdout_data(str![[r#"
3

"#]])
        .run();

    // A local source change is not dependency-only and must regenerate the
    // codegen cache before linking.
    fs::write(&log, "").unwrap();
    sleep_ms(1000);
    p.change_file(
        "src/main.rs",
        "fn main() { println!(\"value={}\", dep::value()); }",
    );
    p.cargo("-Zohm-defaults build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RELINK_WRAPPER_LOG", &log)
        .run();
    assert_eq!(fs::read_to_string(&log).unwrap(), "codegen:app\nlink:app\n");
}

#[cargo_test]
#[cfg(not(windows))]
fn relink_only_reuses_root_codegen_after_separate_transitive_dependency_build() {
    let wrapper = relink_only_wrapper();
    let p = project()
        .at("transitive-relink-only")
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "app"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                middle = { path = "middle" }
            "#,
        )
        .file(
            "src/main.rs",
            "fn main() { println!(\"{}\", middle::value()); }",
        )
        .file(
            "middle/Cargo.toml",
            r#"
                [package]
                name = "middle"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                dep = { path = "../dep" }
            "#,
        )
        .file(
            "middle/src/lib.rs",
            "pub fn value() -> i32 { dep::value() }",
        )
        .file(
            "dep/Cargo.toml",
            r#"
                [package]
                name = "dep"
                version = "0.1.0"
                edition = "2024"
                build = "build.rs"
            "#,
        )
        .file(
            "dep/build.rs",
            r#"
                use std::env;
                use std::path::PathBuf;
                use std::process::Command;

                fn main() {
                    let out_dir = PathBuf::from(env::var_os("OUT_DIR").unwrap());
                    let object = out_dir.join("native.o");
                    let archive = out_dir.join("libnative.a");
                    assert!(
                        Command::new("cc")
                            .args(["-c", "native.c", "-o"])
                            .arg(&object)
                            .status()
                            .unwrap()
                            .success()
                    );
                    assert!(
                        Command::new("ar")
                            .arg("rcs")
                            .arg(&archive)
                            .arg(&object)
                            .status()
                            .unwrap()
                            .success()
                    );
                    println!("cargo::rerun-if-changed=native.c");
                    println!("cargo::rustc-link-search=native={}", out_dir.display());
                    println!("cargo::rustc-link-lib=static=native");
                }
            "#,
        )
        .file(
            "dep/src/lib.rs",
            r#"
                unsafe extern "C" {
                    fn native_value() -> i32;
                }

                pub fn value() -> i32 {
                    // SAFETY: `native_value` is provided by the build-script archive.
                    unsafe { native_value() }
                }
            "#,
        )
        .file("dep/native.c", "int native_value(void) { return 1; }")
        .build();
    let log = p.root().join("relink-wrapper.log");

    p.cargo("-Zrelink-only build")
        .masquerade_as_nightly_cargo(&["relink-only"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RELINK_WRAPPER_LOG", &log)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .run();
    assert_eq!(
        fs::read_to_string(&log).unwrap(),
        "compile:build_script_build\ncompile:dep\ncompile:middle\ncodegen:app\nlink:app\n"
    );

    fs::write(&log, "").unwrap();
    if is_coarse_mtime() {
        sleep_ms(1000);
    }
    p.change_file("dep/native.c", "int native_value(void) { return 2; }");
    p.cargo("-Zrelink-only build -p dep")
        .masquerade_as_nightly_cargo(&["relink-only"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RELINK_WRAPPER_LOG", &log)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .run();
    assert_eq!(fs::read_to_string(&log).unwrap(), "compile:dep\n");

    fs::write(&log, "").unwrap();
    p.cargo("-Zrelink-only build")
        .masquerade_as_nightly_cargo(&["relink-only"])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RELINK_WRAPPER_LOG", &log)
        .env("RUSTFLAGS", "-Zpublic-api-hash")
        .run();
    assert_eq!(fs::read_to_string(&log).unwrap(), "link:app\n");
    p.process(&p.bin("app"))
        .with_stdout_data(str![[r#"
2

"#]])
        .run();
}
