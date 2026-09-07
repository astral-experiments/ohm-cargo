use crate::prelude::*;
#[cfg(all(target_os = "linux", target_arch = "x86_64", target_env = "gnu"))]
use cargo_test_support::str;
use cargo_test_support::{Execs, Project, basic_manifest, paths, project};
use std::path::{Path, PathBuf};
use std::{env, fs};

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
}
