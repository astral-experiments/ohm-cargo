//! Tests for dep-info files. This includes the dep-info file Cargo creates in
//! the output directory, and the ones stored in the fingerprint.

use std::path::Path;

use crate::prelude::*;
use cargo_test_support::compare::assert_e2e;
use cargo_test_support::paths;
use cargo_test_support::registry::Package;
use cargo_test_support::str;
use cargo_test_support::{assert_deps, assert_deps_contains};
use cargo_test_support::{basic_bin_manifest, basic_manifest, main_file, project, rustc_host};
use filetime::FileTime;

#[cargo_test]
fn build_dep_info() {
    let p = project()
        .file("Cargo.toml", &basic_bin_manifest("foo"))
        .file("src/foo.rs", &main_file(r#""i am foo""#, &[]))
        .build();

    p.cargo("build").run();

    let depinfo_bin_path = &p.bin("foo").with_extension("d");

    assert!(depinfo_bin_path.is_file());

    let depinfo = p.read_file(depinfo_bin_path);

    let bin_path = p.bin("foo");
    let src_path = p.root().join("src").join("foo.rs");
    if !depinfo.lines().any(|line| {
        line.starts_with(&format!("{}:", bin_path.display()))
            && line.contains(src_path.to_str().unwrap())
    }) {
        panic!(
            "Could not find {:?}: {:?} in {:?}",
            bin_path, src_path, depinfo_bin_path
        );
    }
}

#[cargo_test]
fn build_dep_info_lib() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                authors = []

                [[example]]
                name = "ex"
                crate-type = ["lib"]
            "#,
        )
        .file("build.rs", "fn main() {}")
        .file("src/lib.rs", "")
        .file("examples/ex.rs", "")
        .build();

    p.cargo("build --example=ex").run();
    assert!(p.example_lib("ex", "lib").with_extension("d").is_file());
}

#[cargo_test]
fn build_dep_info_rlib() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                authors = []

                [[example]]
                name = "ex"
                crate-type = ["rlib"]
            "#,
        )
        .file("src/lib.rs", "")
        .file("examples/ex.rs", "")
        .build();

    p.cargo("build --example=ex").run();
    assert!(p.example_lib("ex", "rlib").with_extension("d").is_file());
}

#[cargo_test]
fn build_dep_info_dylib() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.0.1"
                authors = []

                [[example]]
                name = "ex"
                crate-type = ["dylib"]
            "#,
        )
        .file("src/lib.rs", "")
        .file("examples/ex.rs", "")
        .build();

    p.cargo("build --example=ex").run();
    assert!(p.example_lib("ex", "dylib").with_extension("d").is_file());
}

#[cargo_test]
fn dep_path_inside_target_has_correct_path() {
    let p = project()
        .file("Cargo.toml", &basic_bin_manifest("a"))
        .file("target/debug/blah", "")
        .file(
            "src/main.rs",
            r#"
                fn main() {
                    let x = include_bytes!(concat!(env!("CARGO_MANIFEST_DIR"), "/target/debug/blah"));
                }
            "#,
        )
        .build();

    p.cargo("build").run();

    let depinfo_path = &p.bin("a").with_extension("d");

    assert!(depinfo_path.is_file(), "{:?}", depinfo_path);

    let depinfo = p.read_file(depinfo_path);

    let bin_path = p.bin("a");
    let target_debug_blah = Path::new("target").join("debug").join("blah");
    if !depinfo.lines().any(|line| {
        line.starts_with(&format!("{}:", bin_path.display()))
            && line.contains(target_debug_blah.to_str().unwrap())
    }) {
        panic!(
            "Could not find {:?}: {:?} in {:?}",
            bin_path, target_debug_blah, depinfo_path
        );
    }
}

#[cfg(unix)]
#[cargo_test]
fn native_workspace_path_in_external_dep_info() {
    use std::ffi::OsStr;
    use std::os::unix::ffi::OsStrExt;

    let p = project().file("src/main.rs", "fn main() {}").build();
    let native = p.root().with_file_name(OsStr::from_bytes(b"native-\xff"));
    if let Err(error) = std::fs::rename(p.root(), &native) {
        // Some filesystems reject non-Unicode names before Cargo can use the workspace.
        assert_eq!(error.raw_os_error(), Some(libc::EILSEQ), "{error}");
        return;
    }
    let target = paths::root().join("target");
    p.cargo("build")
        .cwd(&native)
        .env("CARGO_TARGET_DIR", &target)
        .run();

    let depfile = target.join("debug/foo.d");
    assert!(
        std::fs::read(&depfile)
            .unwrap()
            .ends_with(b"/native-\xff/src/main.rs\n")
    );

    p.cargo("build")
        .arg("--config")
        .arg("build.dep-info-basedir=\".\"")
        .cwd(&native)
        .env("CARGO_TARGET_DIR", &target)
        .run();
    assert!(
        std::fs::read(&depfile)
            .unwrap()
            .ends_with(b": src/main.rs\n")
    );
}

#[cargo_test]
fn no_rewrite_if_no_change() {
    let p = project()
        .file(
            "src/lib.rs",
            "mod first; mod second; const _: &str = include_str!(\"data with spaces.txt\");",
        )
        .file("src/first.rs", "")
        .file("src/second.rs", "")
        .file("src/data with spaces.txt", "data")
        .build();

    p.cargo("build").run();
    let dep_info = p.root().join("target/debug/libfoo.d");
    let preserved_mtime = FileTime::from_unix_time(1, 0);
    filetime::set_file_mtime(&dep_info, preserved_mtime).unwrap();
    p.cargo("build").run();
    assert_eq!(
        FileTime::from_last_modification_time(&dep_info.metadata().unwrap()),
        preserved_mtime,
    );

    p.change_file(
        "src/lib.rs",
        "mod third; mod second; const _: &str = include_str!(\"data with spaces.txt\");",
    );
    p.change_file("src/third.rs", "");
    p.cargo("build").run();
    let updated_contents = p.read_file(&dep_info);
    assert!(updated_contents.contains("third.rs"));
    assert!(!updated_contents.contains("first.rs"));
    assert_ne!(
        FileTime::from_last_modification_time(&dep_info.metadata().unwrap()),
        preserved_mtime,
    );

    filetime::set_file_mtime(&dep_info, preserved_mtime).unwrap();
    p.cargo("build").run();
    assert_eq!(p.read_file(&dep_info), updated_contents);
    assert_eq!(
        FileTime::from_last_modification_time(&dep_info.metadata().unwrap()),
        preserved_mtime,
    );
}

#[cargo_test]
fn multiple_crate_types_preserve_dep_info_target() {
    let p = project()
        .file(
            "Cargo.toml",
            &format!(
                "{}\n[lib]\ncrate-type = [\"rlib\", \"cdylib\"]\n",
                basic_manifest("foo", "0.0.1")
            ),
        )
        .file("src/lib.rs", "")
        .build();

    // Relative paths keep the single dependency unescaped even if the test root has spaces.
    let expected = format!(
        "{}: {}\n",
        Path::new("target")
            .join("debug")
            .join("libfoo.rlib")
            .display(),
        Path::new("src").join("lib.rs").display(),
    );
    p.cargo("build")
        .env("CARGO_BUILD_DEP_INFO_BASEDIR", p.root())
        .run();
    assert_eq!(p.read_file("target/debug/libfoo.d"), expected);

    p.cargo("build")
        .env("CARGO_BUILD_DEP_INFO_BASEDIR", p.root())
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
    assert_eq!(p.read_file("target/debug/libfoo.d"), expected);
}

#[cargo_test]
fn shared_dependencies_are_refreshed_after_rebuild() {
    let p = project()
        .file("src/lib.rs", "mod first;")
        .file("src/main.rs", "extern crate foo; fn main() {}")
        .file("src/first.rs", "")
        .file("src/second.rs", "")
        .build();

    let dep_info_paths = [
        p.root().join("target/debug/libfoo.d"),
        p.bin("foo").with_extension("d"),
    ];
    for (module, previous) in [("first", "second"), ("second", "first")] {
        p.root().move_into_the_past();
        p.change_file("src/lib.rs", &format!("mod {module};"));
        p.cargo("build").run();
        for path in &dep_info_paths {
            let contents = p.read_file(path);
            assert!(contents.contains(&format!("{module}.rs")), "{contents}");
            assert!(!contents.contains(&format!("{previous}.rs")), "{contents}");
        }
    }
}

#[cargo_test(nightly, reason = "-Z binary-dep-depinfo is unstable")]
fn relative_depinfo_paths_ws() {
    // Test relative dep-info paths in a workspace with --target with
    // proc-macros and other dependency kinds.
    Package::new("regdep", "0.1.0")
        .file("src/lib.rs", "pub fn f() {}")
        .publish();
    Package::new("pmdep", "0.1.0")
        .file("src/lib.rs", "pub fn f() {}")
        .publish();
    Package::new("bdep", "0.1.0")
        .file("src/lib.rs", "pub fn f() {}")
        .publish();

    let p = project()
        /*********** Workspace ***********/
        .file(
            "Cargo.toml",
            r#"
            [workspace]
            members = ["foo"]
            "#,
        )
        /*********** Main Project ***********/
        .file(
            "foo/Cargo.toml",
            r#"
            [package]
            name = "foo"
            version = "0.1.0"
            edition = "2018"

            [dependencies]
            pm = {path = "../pm"}
            bar = {path = "../bar"}
            regdep = "0.1"

            [build-dependencies]
            bdep = "0.1"
            bar = {path = "../bar"}
            "#,
        )
        .file(
            "foo/src/main.rs",
            r#"
            pm::noop!{}

            fn main() {
                bar::f();
                regdep::f();
            }
            "#,
        )
        .file("foo/build.rs", "fn main() { bdep::f(); }")
        /*********** Proc Macro ***********/
        .file(
            "pm/Cargo.toml",
            r#"
            [package]
            name = "pm"
            version = "0.1.0"
            edition = "2018"

            [lib]
            proc-macro = true

            [dependencies]
            pmdep = "0.1"
            "#,
        )
        .file(
            "pm/src/lib.rs",
            r#"
            extern crate proc_macro;
            use proc_macro::TokenStream;

            #[proc_macro]
            pub fn noop(_item: TokenStream) -> TokenStream {
                pmdep::f();
                "".parse().unwrap()
            }
            "#,
        )
        /*********** Path Dependency `bar` ***********/
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("bar/src/lib.rs", "pub fn f() {}")
        .build();

    let host = rustc_host();
    p.cargo("build -Z binary-dep-depinfo --target")
        .arg(&host)
        .masquerade_as_nightly_cargo(&["binary-dep-depinfo"])
        .with_stderr_data(str![[r#"
...
[COMPILING] foo v0.1.0 ([ROOT]/foo/foo)
...
"#]])
        .run();

    assert_deps_contains(
        &p,
        "target/debug/.fingerprint/pm-*/dep-lib-pm",
        &[(0, "src/lib.rs"), (1, "debug/deps/libpmdep-*.rlib")],
    );

    assert_deps_contains(
        &p,
        &format!("target/{}/debug/.fingerprint/foo-*/dep-bin-foo", host),
        &[
            (0, "src/main.rs"),
            (
                1,
                &format!(
                    "debug/deps/{}pm-*.{}",
                    paths::get_lib_prefix("proc-macro"),
                    paths::get_lib_extension("proc-macro")
                ),
            ),
            (1, &format!("{}/debug/deps/libbar-*.rlib", host)),
            (1, &format!("{}/debug/deps/libregdep-*.rlib", host)),
        ],
    );

    assert_deps_contains(
        &p,
        "target/debug/.fingerprint/foo-*/dep-build-script-build-script-build",
        &[(0, "build.rs"), (1, "debug/deps/libbdep-*.rlib")],
    );

    // Make sure it stays fresh.
    p.cargo("build -Z binary-dep-depinfo --target")
        .arg(&host)
        .masquerade_as_nightly_cargo(&["binary-dep-depinfo"])
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test(nightly, reason = "-Z binary-dep-depinfo is unstable")]
fn relative_depinfo_paths_no_ws() {
    // Test relative dep-info paths without a workspace with proc-macros and
    // other dependency kinds.
    Package::new("regdep", "0.1.0")
        .file("src/lib.rs", "pub fn f() {}")
        .publish();
    Package::new("pmdep", "0.1.0")
        .file("src/lib.rs", "pub fn f() {}")
        .publish();
    Package::new("bdep", "0.1.0")
        .file("src/lib.rs", "pub fn f() {}")
        .publish();

    let p = project()
        /*********** Main Project ***********/
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "foo"
            version = "0.1.0"
            edition = "2018"

            [dependencies]
            pm = {path = "pm"}
            bar = {path = "bar"}
            regdep = "0.1"

            [build-dependencies]
            bdep = "0.1"
            bar = {path = "bar"}
            "#,
        )
        .file(
            "src/main.rs",
            r#"
            pm::noop!{}

            fn main() {
                bar::f();
                regdep::f();
            }
            "#,
        )
        .file("build.rs", "fn main() { bdep::f(); }")
        /*********** Proc Macro ***********/
        .file(
            "pm/Cargo.toml",
            r#"
            [package]
            name = "pm"
            version = "0.1.0"
            edition = "2018"

            [lib]
            proc-macro = true

            [dependencies]
            pmdep = "0.1"
            "#,
        )
        .file(
            "pm/src/lib.rs",
            r#"
            extern crate proc_macro;
            use proc_macro::TokenStream;

            #[proc_macro]
            pub fn noop(_item: TokenStream) -> TokenStream {
                pmdep::f();
                "".parse().unwrap()
            }
            "#,
        )
        /*********** Path Dependency `bar` ***********/
        .file("bar/Cargo.toml", &basic_manifest("bar", "0.1.0"))
        .file("bar/src/lib.rs", "pub fn f() {}")
        .build();

    p.cargo("build -Z binary-dep-depinfo")
        .masquerade_as_nightly_cargo(&["binary-dep-depinfo"])
        .with_stderr_data(str![[r#"
...
[COMPILING] foo v0.1.0 ([ROOT]/foo)
...
"#]])
        .run();

    assert_deps_contains(
        &p,
        "target/debug/.fingerprint/pm-*/dep-lib-pm",
        &[(0, "src/lib.rs"), (1, "debug/deps/libpmdep-*.rlib")],
    );

    assert_deps_contains(
        &p,
        "target/debug/.fingerprint/foo-*/dep-bin-foo",
        &[
            (0, "src/main.rs"),
            (
                1,
                &format!(
                    "debug/deps/{}pm-*.{}",
                    paths::get_lib_prefix("proc-macro"),
                    paths::get_lib_extension("proc-macro")
                ),
            ),
            (1, "debug/deps/libbar-*.rlib"),
            (1, "debug/deps/libregdep-*.rlib"),
        ],
    );

    assert_deps_contains(
        &p,
        "target/debug/.fingerprint/foo-*/dep-build-script-build-script-build",
        &[(0, "build.rs"), (1, "debug/deps/libbdep-*.rlib")],
    );

    // Make sure it stays fresh.
    p.cargo("build -Z binary-dep-depinfo")
        .masquerade_as_nightly_cargo(&["binary-dep-depinfo"])
        .with_stderr_data(str![[r#"
[FINISHED] `dev` profile [unoptimized + debuginfo] target(s) in [ELAPSED]s

"#]])
        .run();
}

#[cargo_test]
fn reg_dep_source_not_tracked() {
    // Make sure source files in dep-info file are not tracked for registry dependencies.
    Package::new("regdep", "0.1.0")
        .file("src/lib.rs", "pub fn f() {}")
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "foo"
            version = "0.1.0"

            [dependencies]
            regdep = "0.1"
            "#,
        )
        .file("src/lib.rs", "pub fn f() { regdep::f(); }")
        .build();

    p.cargo("check").run();

    assert_deps(
        &p,
        "target/debug/.fingerprint/regdep-*/dep-lib-regdep",
        |info_path, entries| {
            for (kind, path) in entries {
                if *kind == 1 {
                    panic!(
                        "Did not expect package root relative path type: {:?} in {:?}",
                        path, info_path
                    );
                }
            }
        },
    );
}

#[cargo_test(nightly, reason = "-Z binary-dep-depinfo is unstable")]
fn canonical_path() {
    if !cargo_test_support::symlink_supported() {
        return;
    }
    Package::new("regdep", "0.1.0")
        .file("src/lib.rs", "pub fn f() {}")
        .publish();

    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "foo"
            version = "0.1.0"

            [dependencies]
            regdep = "0.1"
            "#,
        )
        .file("src/lib.rs", "pub fn f() { regdep::f(); }")
        .build();

    let real = p.root().join("real_target");
    real.mkdir_p();
    p.symlink(real, "target");

    p.cargo("check -Z binary-dep-depinfo")
        .masquerade_as_nightly_cargo(&["binary-dep-depinfo"])
        .run();

    assert_deps_contains(
        &p,
        "target/debug/.fingerprint/foo-*/dep-lib-foo",
        &[(0, "src/lib.rs"), (1, "debug/deps/libregdep-*.rmeta")],
    );
}

#[cargo_test]
fn non_local_build_script() {
    // Non-local build script information is not included.
    Package::new("bar", "1.0.0")
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

                [dependencies]
                bar = "1.0"
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .build();

    p.cargo("build").run();
    let contents = p.read_file("target/debug/foo.d");
    assert_e2e().eq(
        &contents,
        str![[r#"
[ROOT]/foo/target/debug/foo[EXE]: [ROOT]/foo/src/main.rs

"#]],
    );
}

#[cargo_test]
fn no_trailing_separator_after_package_root_build_script() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "foo"
            version = "0.0.1"
            authors = []
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .file(
            "build.rs",
            r#"
            fn main() {
                println!("cargo::rerun-if-changed=");
            }
            "#,
        )
        .build();

    p.cargo("build").run();
    let contents = p.read_file("target/debug/foo.d");

    assert_e2e().eq(
        &contents,
        str![[r#"
[ROOT]/foo/target/debug/foo[EXE]: [ROOT]/foo [ROOT]/foo/build.rs [ROOT]/foo/src/main.rs

"#]],
    );
}

#[cargo_test(nightly, reason = "proc_macro::tracked::path is unstable")]
fn no_trailing_separator_after_package_root_proc_macro() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "foo"
            version = "0.0.1"
            authors = []
            edition = "2018"

            [dependencies]
            pm = { path = "pm" }
            "#,
        )
        .file(
            "src/main.rs",
            "
            pm::noop!{}
            fn main() {}
            ",
        )
        .file(
            "pm/Cargo.toml",
            r#"
            [package]
            name = "pm"
            version = "0.1.0"
            edition = "2018"

            [lib]
            proc-macro = true
            "#,
        )
        .file(
            "pm/src/lib.rs",
            r#"
            #![feature(proc_macro_tracked_path)]
            extern crate proc_macro;
            use proc_macro::TokenStream;

            #[proc_macro]
            pub fn noop(_item: TokenStream) -> TokenStream {
                proc_macro::tracked::path(
                    std::env::current_dir().unwrap().to_str().unwrap()
                );
                "".parse().unwrap()
            }
            "#,
        )
        .build();

    p.cargo("build").run();
    let contents = p.read_file("target/debug/foo.d");

    assert_e2e().eq(
        &contents,
        str![[r#"
[ROOT]/foo/target/debug/foo[EXE]: [ROOT]/foo [ROOT]/foo/pm/src/lib.rs [ROOT]/foo/src/main.rs

"#]],
    );
}
