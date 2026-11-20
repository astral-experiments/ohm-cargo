use crate::prelude::*;
#[cfg(all(target_os = "linux", target_arch = "x86_64", target_env = "gnu"))]
use cargo_test_support::str;
use cargo_test_support::{Execs, Project, basic_manifest, paths, project};
use std::path::{Path, PathBuf};
use std::{env, fs};

#[cfg(all(
    target_os = "linux",
    target_arch = "x86_64",
    target_env = "gnu",
    feature = "ohm-defaults"
))]
#[cargo_test(requires = "cc", requires = "ar")]
fn binary_with_unused_library_keeps_its_link_until_an_input_changes() {
    // Exercise the native dependency file alongside the real compiler's usage report.
    if !Path::new(&paths::sysroot())
        .join("lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd")
        .is_file()
    {
        return;
    }
    let p = project()
        .file(
            "Cargo.toml",
            "[package]\nname=\"app\"\nversion=\"0.1.0\"\nedition=\"2024\"\n",
        )
        .file("src/lib.rs", "pub struct Original;")
        .file(
            "src/main.rs",
            r#"fn main() { let warning = 1; println!("17"); }"#,
        )
        .file("vendor/answer.c", "int answer(void) { return 17; }")
        .build();
    let archive = || {
        p.process("cc")
            .args(&["-c", "vendor/answer.c", "-o", "vendor/answer.o"])
            .run();
        p.process("ar")
            .args(&["crs", "vendor/libanswer.a", "vendor/answer.o"])
            .run();
    };
    let build = || {
        let mut cmd = p.cargo("-Zohm-defaults build -v");
        cmd.masquerade_as_nightly_cargo(&["ohm-defaults"])
            .env_remove("LIBRARY_PATH")
            .env("CARGO_LOG", "cargo::compiler::ohm_independent_binary=info");
        cmd
    };
    build().run();
    for edit in ["pub struct First;", "pub struct Second;"] {
        p.change_file("src/lib.rs", edit);
        build()
            .with_stderr_contains("[..]reusing binary with unused library[..]")
            .with_stderr_contains("[..]unused variable: `warning`[..]")
            .run();
        p.process(p.bin("app")).with_stdout_contains("17").run();
    }
    build().with_stderr_contains("[FRESH] app[..]").run();

    // LIBRARY_PATH can expose multilib directories, thin archives and
    // dangling symlinks. Relink when only the Rust library changed.
    let native_build = || {
        let mut cmd = build();
        cmd.env("LIBRARY_PATH", p.root().join("vendor"))
            .with_stderr_does_not_contain("[..]reusing binary with unused library[..]");
        cmd
    };
    p.change_file(
        "src/main.rs",
        r#"
            #[link(name="answer", kind="static", modifiers="-bundle")]
            unsafe extern "C" { fn answer() -> i32; }
            fn main() { println!("{}", unsafe { answer() }); }
        "#,
    );
    archive();
    native_build().run();
    p.change_file("src/lib.rs", "pub struct Native;");
    native_build().run();
    p.process(p.bin("app")).with_stdout_contains("17").run();
    p.change_file("vendor/libanswer.a", "invalid archive");
    p.change_file("src/lib.rs", "pub struct Third;");
    native_build()
        .with_status(101)
        .with_stderr_contains("[..]linking with [..] failed[..]")
        .run();
    fs::remove_file(p.root().join("vendor/libanswer.a")).unwrap();
    p.change_file("vendor/answer.c", "int answer(void) { return 29; }");
    archive();
    p.change_file("src/lib.rs", "pub fn value() -> i32 { 31 }");
    native_build().run();
    p.process(p.bin("app")).with_stdout_contains("29").run();
    p.change_file(
        "src/main.rs",
        "fn main() { println!(\"{}\", app::value()); }",
    );
    build().run();
    p.process(p.bin("app")).with_stdout_contains("31").run();
    p.change_file("src/lib.rs", "pub fn value() -> i32 { 37 }");
    build().run();
    p.process(p.bin("app")).with_stdout_contains("37").run();

    // Respect cc shims that do not understand dependency reporting.
    use std::os::unix::fs::PermissionsExt;
    let bin = p.root().join("driver");
    fs::create_dir(&bin).unwrap();
    fs::write(
        bin.join("cc"),
        "#!/bin/sh\ncase \"$*\" in *--dependency-file=*) exit 1;; esac\nexec /usr/bin/cc \"$@\"\n",
    )
    .unwrap();
    fs::set_permissions(bin.join("cc"), fs::Permissions::from_mode(0o755)).unwrap();
    let path = env::var_os("PATH").unwrap();
    let path = env::join_paths(std::iter::once(bin).chain(env::split_paths(&path))).unwrap();
    p.change_file("src/main.rs", "fn main() { println!(\"shim\"); }");
    build().env("PATH", path).run();
    p.process(p.bin("app")).with_stdout_contains("shim").run();
}

// Exercise Cargo's routing and fingerprinting without requiring Wild in the
// test compiler. The devbox smoke test separately exercises the real linker.
fn mock_toolchain() -> PathBuf {
    let helper = project()
        .at("linker-tools")
        .file("Cargo.toml", &basic_manifest("linker-tools", "0.1.0"))
        .file("src/main.rs", r#"
            use std::{env, fs::OpenOptions, io::Write, process::{Command, exit}};
            fn main() {
                let mut args: Vec<String> = env::args().skip(1).collect();
                if let Some(name) = args.windows(2).find(|a| a[0] == "--crate-name").map(|a| a[1].clone()) {
                    if name != "___" {
                        let mut log = OpenOptions::new().create(true).append(true).open(env::var_os("OHM_LINKER_LOG").unwrap()).unwrap();
                        writeln!(log, "{name} {}", args.join(" ")).unwrap();
                    }
                }
                args.retain(|arg| !arg.starts_with("-Clinker-features=") && !arg.starts_with("-Clink-self-contained=") && !arg.starts_with("-Clink-arg=-B") && arg != "-Clink-arg=-fuse-ld=bfd");
                let output = Command::new(env::var_os("OHM_REAL_RUSTC").unwrap()).args(&args).output().unwrap();
                let mut stdout = String::from_utf8_lossy(&output.stdout).into_owned();
                if args.iter().any(|arg| arg == "--print=sysroot") {
                    stdout = stdout.lines().map(|line| if line == env::var("OHM_REAL_SYSROOT").unwrap() { env::var("OHM_MOCK_SYSROOT").unwrap() } else { line.to_owned() }).collect::<Vec<_>>().join("\n") + "\n";
                }
                print!("{stdout}");
                eprint!("{}", String::from_utf8_lossy(&output.stderr));
                exit(output.status.code().unwrap());
            }
        "#)
        .build();
    helper
        .cargo("-Zohm-defaults=no build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .run();
    helper.bin("linker-tools")
}

fn cargo(p: &Project, rustc: &Path, command: &str) -> Execs {
    let mut exec = p.cargo(&format!("-Zohm-defaults=no {command}"));
    exec.masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-linker", "profile-rustflags"])
        .env("RUSTC", rustc)
        .env(
            "OHM_REAL_RUSTC",
            Path::new(&paths::sysroot())
                .join("bin/rustc")
                .with_extension(env::consts::EXE_EXTENSION),
        )
        .env("OHM_REAL_SYSROOT", paths::sysroot())
        .env("OHM_MOCK_SYSROOT", paths::root().join("sysroot"))
        .env("OHM_LINKER_LOG", paths::root().join("linker.log"));
    exec
}

#[cargo_test]
#[cfg(all(target_os = "linux", target_arch = "x86_64", target_env = "gnu"))]
fn selection_invalidates_artifacts_and_respects_overrides() {
    let rustc = mock_toolchain();
    let linker =
        paths::root().join("sysroot/lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd");
    fs::create_dir_all(linker.parent().unwrap()).unwrap();
    fs::write(&linker, "fixture").unwrap();
    let p = project()
        .file("src/main.rs", "fn main() {}")
        .file("build.rs", "fn main() {}")
        .build();
    let log = paths::root().join("linker.log");
    cargo(&p, &rustc, "build").run();
    assert!(!fs::read_to_string(&log).unwrap().contains("wild-ld"));
    for mode in ["wild", "lld"] {
        fs::write(&log, "").unwrap();
        cargo(&p, &rustc, &format!("-Zohm-linker={mode} build")).run();
        let output = fs::read_to_string(&log).unwrap();
        if mode == "wild" {
            assert!(output.contains("foo "), "{output}");
        }
        assert_eq!(output.contains("wild-ld"), mode == "wild", "{output}");
        fs::write(&log, "").unwrap();
        cargo(&p, &rustc, &format!("-Zohm-linker={mode} build")).run();
        assert!(fs::read_to_string(&log).unwrap().is_empty());
    }
    // A previous Wild artifact may be reused when switching back; it must not
    // be rebuilt with LLD's flags.
    fs::write(&log, "").unwrap();
    cargo(&p, &rustc, "-Zohm-linker=wild build").run();
    let output = fs::read_to_string(&log).unwrap();
    assert!(output.is_empty() || output.contains("wild-ld"), "{output}");

    fs::remove_file(&linker).unwrap();
    // An explicit linker works even if this toolchain has no bundled Wild.
    p.change_file(".cargo/config.toml", "[target.'cfg(unix)']\nlinker='cc'\n");
    fs::write(&log, "").unwrap();
    cargo(&p, &rustc, "-Zohm-linker=wild build").run();
    let output = fs::read_to_string(&log).unwrap();
    assert!(output.contains("linker=cc"));
    assert!(!output.contains("wild-ld"));
    p.change_file(".cargo/config.toml", "");
    fs::write(&log, "").unwrap();
    cargo(&p, &rustc, "-Zohm-linker=wild build")
        .env("CARGO_ENCODED_RUSTFLAGS", "-C\x1flinker=cc")
        .run();
    assert!(!fs::read_to_string(&log).unwrap().contains("wild-ld"));
    // Profile and cargo-rustc flags arrive after target discovery.
    p.change_file(
        ".cargo/config.toml",
        "[profile.dev]\nrustflags=['-Clinker=cc']\n",
    );
    cargo(&p, &rustc, "-Zprofile-rustflags -Zohm-linker=wild build").run();
    p.change_file(".cargo/config.toml", "");
    fs::remove_file(p.root().join("build.rs")).unwrap();
    cargo(&p, &rustc, "-Zohm-linker=wild rustc -- -Clinker=cc").run();
    cargo(&p, &rustc, "-Zohm-linker=wild build")
        .with_status(101)
        .with_stderr_data(str![[r#"
[ERROR] bundled Wild linker not found at `[ROOT]/sysroot/lib/rustlib/[HOST_TARGET]/bin/wild-ld/ld.bfd`; install an Ohm toolchain that includes Wild or use `-Zohm-linker=lld`

"#]])
        .run();
}

#[cargo_test]
#[cfg(not(all(target_os = "linux", target_arch = "x86_64", target_env = "gnu")))]
fn unsupported_host_keeps_default_linker() {
    let rustc = mock_toolchain();
    let p = project().file("src/main.rs", "fn main() {}").build();
    cargo(&p, &rustc, "-Zohm-linker=wild build").run();
    let log = fs::read_to_string(paths::root().join("linker.log")).unwrap();
    assert!(!log.contains("wild-ld"));
    assert!(!log.contains("linker-features"));
}

#[cargo_test(
    nightly,
    reason = "automatic defaults require the packaged Ohm compiler"
)]
#[cfg(all(target_os = "linux", target_arch = "x86_64", target_env = "gnu"))]
fn ohm_defaults_select_wild_and_allow_lld() {
    let rustc = mock_toolchain();
    let linker =
        paths::root().join("sysroot/lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd");
    fs::create_dir_all(linker.parent().unwrap()).unwrap();
    fs::write(&linker, "fixture").unwrap();
    let p = project()
        .file("src/main.rs", "fn main() {}")
        .file("build.rs", "fn main() {}")
        .build();
    let log = paths::root().join("linker.log");
    cargo(&p, &rustc, "-Zohm-defaults=yes build").run();
    let output = fs::read_to_string(&log).unwrap();
    for name in ["foo", "build_script_build"] {
        assert!(
            output
                .lines()
                .any(|line| line.starts_with(name) && line.contains("wild-ld")),
            "{output}"
        );
    }
    fs::write(&log, "").unwrap();
    cargo(&p, &rustc, "-Zohm-defaults=yes build").run();
    assert!(fs::read_to_string(&log).unwrap().is_empty());

    cargo(&p, &rustc, "-Zohm-defaults=yes -Zohm-linker=lld build").run();
    let output = fs::read_to_string(&log).unwrap();
    assert!(output.contains("foo "), "{output}");
    assert!(!output.contains("wild-ld"), "{output}");
    fs::write(&log, "").unwrap();
    cargo(&p, &rustc, "build").run();
    let output = fs::read_to_string(&log).unwrap();
    assert!(output.contains("foo "), "{output}");
    assert!(!output.contains("wild-ld"), "{output}");
    // Older compiler sysroots retain their linker under automatic defaults.
    fs::remove_file(linker).unwrap();
    p.change_file("src/main.rs", "fn main() { println!(\"older sysroot\"); }");
    fs::write(&log, "").unwrap();
    cargo(&p, &rustc, "-Zohm-defaults=yes build").run();
    let output = fs::read_to_string(&log).unwrap();
    assert!(output.contains("foo "), "{output}");
    assert!(!output.contains("wild-ld"), "{output}");
}

#[cfg(all(
    target_os = "linux",
    target_arch = "x86_64",
    target_env = "gnu",
    feature = "ohm-defaults"
))]
#[cargo_test(requires = "cc")]
fn independent_integration_test_revalidates_library_and_script_inputs() {
    if !Path::new(&paths::sysroot())
        .join("lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd")
        .is_file()
    {
        return;
    }
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "app"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                api = { path = "api" }

                [workspace]
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .file("api/Cargo.toml", &basic_manifest("api", "0.1.0"))
        .file("api/src/lib.rs", "pub trait Answer {}")
        .file("trigger", "a")
        .file(
            "build.rs",
            r#"fn main() {
                println!("cargo:rerun-if-changed=trigger");
                let text = std::fs::read_to_string("trigger").unwrap();
                println!("cargo:rustc-env=APP_MARKER={}", text.trim());
            }"#,
        )
        .file(
            "tests/cli.rs",
            r#"#[test] fn cli() { let warning = 1; assert_eq!(env!("APP_MARKER"), "a"); }"#,
        )
        .build();
    let test = || {
        let mut cmd = p.cargo("-Zohm-defaults test --test cli");
        cmd.masquerade_as_nightly_cargo(&["ohm-defaults"])
            .env_remove("LIBRARY_PATH")
            .env("CARGO_LOG", "cargo::compiler::ohm_independent_binary=info")
            .env("CARGO_BUILD_BUILD_DIR", p.root().join("shared"));
        cmd
    };
    let reused = "[..]reusing independent integration test[..]";
    let has_impl = "pub trait Answer {} impl Answer for u8 {}";
    test().run();
    p.change_file("api/src/lib.rs", has_impl);
    test()
        .with_stderr_contains(reused)
        .with_stderr_contains("[..]unused variable: `warning`[..]")
        .run();
    p.change_file("trigger", "a ");
    test().with_stderr_contains(reused).run();
    p.change_file("trigger", "b");
    test()
        .with_stderr_does_not_contain(reused)
        .with_status(101)
        .with_stdout_contains("[..]left: \"b\"[..]")
        .run();
    p.change_file(
        "tests/cli.rs",
        "#[test] fn cli() { fn require<T: api::Answer>() {} require::<u8>(); }",
    );
    test().with_stderr_does_not_contain(reused).run();
    p.change_file("api/src/lib.rs", "pub trait Answer {}");
    test()
        .with_stderr_does_not_contain(reused)
        .with_status(101)
        .with_stderr_contains("[..]the trait bound [..] is not satisfied[..]")
        .run();
    p.change_file("tests/cli.rs", "#[test] fn cli() {}");
    test().run();
    p.change_file(
        "build.rs",
        r#"fn main() { println!("cargo:rustc-link-arg-tests=-lmissing_integration_lib"); }"#,
    );
    test()
        .with_stderr_does_not_contain(reused)
        .with_status(101)
        .with_stderr_contains("[..]linking with [..] failed[..]")
        .run();
}

#[cfg(all(
    target_os = "linux",
    target_arch = "x86_64",
    target_env = "gnu",
    feature = "ohm-defaults"
))]
#[cargo_test(requires = "cc")]
fn independent_integration_test_rechecks_script_inputs_read_by_local_macro() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "app"
                version = "0.1.0"
                edition = "2024"

                [dependencies]
                api = { path = "api" }
                probe = { path = "probe" }

                [workspace]
            "#,
        )
        .file("src/main.rs", "fn main() {}")
        .file("api/Cargo.toml", &basic_manifest("api", "0.1.0"))
        .file("api/src/lib.rs", "")
        .file(
            "probe/Cargo.toml",
            r#"
                [package]
                name = "probe"
                version = "0.1.0"
                edition = "2024"

                [lib]
                proc-macro = true
            "#,
        )
        .file(
            "probe/src/lib.rs",
            r#"#[proc_macro]
            pub fn value(_: proc_macro::TokenStream) -> proc_macro::TokenStream {
                std::fs::read_to_string("input").unwrap().parse().unwrap()
            }"#,
        )
        .file("input", "1")
        .file(
            "build.rs",
            r#"fn main() { println!("cargo:rerun-if-changed=input"); }"#,
        )
        .file(
            "tests/cli.rs",
            r#"#[test] fn cli() {
                assert_eq!(probe::value!().to_string(), std::fs::read_to_string("input").unwrap());
            }"#,
        )
        .build();
    let test = || {
        p.cargo("-Zohm-defaults test --test cli")
            .masquerade_as_nightly_cargo(&["ohm-defaults"])
            .env_remove("LIBRARY_PATH")
            .env("CARGO_BUILD_BUILD_DIR", p.root().join("shared"))
            .run();
    };
    test();
    p.change_file("input", "22");
    test();
}
