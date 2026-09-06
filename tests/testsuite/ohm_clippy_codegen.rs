//! Cargo routing tests; the paired Clippy driver tests cover actual lint execution.

use std::path::PathBuf;
use std::{env, fs};

use crate::prelude::*;
use cargo_test_support::registry::Package;
use cargo_test_support::{Execs, Project, basic_manifest, paths, project};

fn mock_toolchain() -> PathBuf {
    let helper = project()
        .at("clippy-codegen-tools")
        .file("Cargo.toml", &basic_manifest("clippy-codegen-tools", "0.1.0"))
        .file(
            "src/main.rs",
            r#"
                use std::{env, fs::OpenOptions, io::Write, process::{Command, exit}};

                fn main() {
                    let exe = env::current_exe().unwrap();
                    let name = exe.file_stem().unwrap().to_str().unwrap();
                    let mut args = env::args().skip(1).collect::<Vec<_>>();
                    if name == "cargo-reinvoke" {
                        assert_eq!(env::var("__CARGO_OHM_CLIPPY_CODEGEN").unwrap(), "yes");
                        let mut cargo = Command::new(env::var_os("CARGO").unwrap());
                        if env::var_os("OHM_CHILD_DISABLE").is_some() {
                            cargo.arg("-Zohm-clippy-codegen=no");
                        }
                        exit(cargo.args(["test", "--lib"]).status().unwrap().code().unwrap());
                    }
                    if args == ["--print", "sysroot"] {
                        println!("{}", exe.parent().unwrap().parent().unwrap().display());
                        return;
                    }
                    let clippy = name == "clippy-driver";
                    if clippy && args == ["--ohm-clippy-codegen-version"] {
                        println!("{}", env::var("OHM_TEST_CAPABILITY").unwrap_or("ohm-clippy-codegen-v1".into()));
                        return;
                    }
                    if clippy {
                        let wrapper = args.remove(0);
                        if wrapper == "--rustc" && env::var_os("OHM_TEST_MISMATCH").is_some() {
                            println!("different compiler");
                            return;
                        }
                    }
                    if let Some(crate_name) = args.windows(2).find(|args| args[0] == "--crate-name").map(|args| &args[1]) {
                        if crate_name != "___" {
                            let lint_args = if clippy {
                                assert_eq!(env::var("CLIPPY_CODEGEN").unwrap(), "1");
                                env::var("CLIPPY_ARGS").unwrap()
                            } else { String::new() };
                            let mut log = OpenOptions::new().append(true).create(true).open(env::var_os("OHM_TEST_LOG").unwrap()).unwrap();
                            let line = format!("{crate_name}|{clippy}|{lint_args}\n");
                            log.write_all(line.as_bytes()).unwrap();
                            if clippy {
                                args.extend(lint_args.split("__CLIPPY_HACKERY__").filter(|arg| !arg.is_empty()).map(str::to_owned));
                            }
                        }
                    }
                    exit(Command::new(env::var_os("OHM_TEST_REAL_RUSTC").unwrap()).args(args).status().unwrap().code().unwrap());
                }
            "#,
        )
        .build();
    helper
        .cargo("-Zohm-defaults=no build")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .run();
    let bin = paths::root().join("mock-toolchain/bin");
    fs::create_dir_all(&bin).unwrap();
    for name in ["rustc", "clippy-driver", "cargo-reinvoke"] {
        fs::copy(
            helper.bin("clippy-codegen-tools"),
            bin.join(name).with_extension(env::consts::EXE_EXTENSION),
        )
        .unwrap();
    }
    bin
}

fn cargo(p: &Project, bin: &std::path::Path, command: &str) -> Execs {
    let mut cargo = p.cargo(&format!("-Zohm-defaults=no {command}"));
    cargo
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-clippy-codegen"])
        .env(
            "RUSTC",
            bin.join("rustc").with_extension(env::consts::EXE_EXTENSION),
        )
        .env(
            "OHM_TEST_REAL_RUSTC",
            PathBuf::from(paths::sysroot())
                .join("bin/rustc")
                .with_extension(env::consts::EXE_EXTENSION),
        )
        .env("OHM_TEST_LOG", paths::root().join("compiler.log"))
        .env_remove("RUSTC_WRAPPER")
        .env_remove("RUSTC_WORKSPACE_WRAPPER")
        .env_remove("CARGO_OHM_CLIPPY_ARGS")
        .env_remove(cargo::CARGO_INHERITED_OHM_CLIPPY_CODEGEN_ENV);
    cargo
}

#[cargo_test]
fn workspace_codegen_is_opt_in_separate_and_inherited_by_external_commands() {
    let bin = mock_toolchain();
    Package::new("dep", "1.0.0").publish();
    let p = project()
        .file("Cargo.toml", "[package]\nname='foo'\nversion='0.1.0'\nedition='2021'\n[dependencies]\ndep='1.0.0'")
        .file(".cargo/config.toml", "[env]\nCLIPPY_CODEGEN={value='0',force=true}\nCLIPPY_ARGS={value='--cfg__CLIPPY_HACKERY__clippy',force=true}\n")
        .file("build.rs", "fn main() { if std::env::var(\"__CARGO_OHM_CLIPPY_CODEGEN\").as_deref() == Ok(\"yes\") { assert!(std::env::var_os(\"RUSTC_WORKSPACE_WRAPPER\").is_none()); } }")
        .file("src/lib.rs", "#[cfg(clippy)] compile_error!(\"clippy cfg changed the program\");\n#[test] fn works() { let _ = (option_env!(\"CLIPPY_CODEGEN\"), option_env!(\"CLIPPY_ARGS\"), option_env!(\"CLIPPY_CODEGEN_CONFIG\")); assert_eq!(2 + 2, 4); }")
        .build();
    let log = paths::root().join("compiler.log");
    cargo(&p, &bin, "test --lib").run();
    let ordinary = fs::read_to_string(&log).unwrap();
    assert!(ordinary.contains("foo|false|"), "{ordinary}");
    assert!(ordinary.contains("dep|false|"), "{ordinary}");

    fs::write(&log, "").unwrap();
    cargo(&p, &bin, "-Zohm-clippy-codegen test --lib")
        .env("CARGO_OHM_CLIPPY_ARGS", "-W clippy::pedantic")
        .run();
    let opted_in = fs::read_to_string(&log).unwrap();
    assert!(opted_in.contains("foo|true|-W__CLIPPY_HACKERY__clippy::pedantic"));
    assert!(
        !opted_in.contains("dep|"),
        "unchanged registry dependency was rebuilt: {opted_in}"
    );

    // Config discovery must invalidate even when the previous build had no file.
    for contents in [Some("disallowed-names = ['bad']\n"), None] {
        match contents {
            Some(contents) => p.change_file("clippy.toml", contents),
            None => fs::remove_file(p.root().join("clippy.toml")).unwrap(),
        }
        fs::write(&log, "").unwrap();
        cargo(&p, &bin, "-Zohm-clippy-codegen test --lib")
            .env("CARGO_OHM_CLIPPY_ARGS", "-W clippy::pedantic")
            .run();
        assert!(fs::read_to_string(&log).unwrap().contains("foo|true|"));
    }
    fs::write(&log, "").unwrap();
    cargo(&p, &bin, "-Zohm-clippy-codegen test --lib")
        .env("CARGO_OHM_CLIPPY_ARGS", "-W clippy::pedantic")
        .run();
    assert!(fs::read_to_string(&log).unwrap().is_empty());

    let mut search_path = vec![bin.clone()];
    search_path.extend(env::split_paths(&env::var_os("PATH").unwrap()));
    fs::write(&log, "").unwrap();
    cargo(&p, &bin, "-Zohm-clippy-codegen reinvoke")
        .env("PATH", env::join_paths(&search_path).unwrap())
        .env("CARGO_OHM_CLIPPY_ARGS", "-D warnings")
        .run();
    assert!(
        fs::read_to_string(&log)
            .unwrap()
            .contains("foo|true|-D__CLIPPY_HACKERY__warnings")
    );

    fs::write(&log, "").unwrap();
    cargo(&p, &bin, "-Zohm-clippy-codegen reinvoke")
        .env("PATH", env::join_paths(&search_path).unwrap())
        .env("OHM_CHILD_DISABLE", "1")
        .run();
    assert!(!fs::read_to_string(&log).unwrap().contains("|true|"));
}

#[cargo_test]
fn lint_arguments_honor_config_environment_precedence_and_external_commands() {
    let bin = mock_toolchain();
    let p = project()
        .file("src/lib.rs", "pub fn example() { let unused = 1; }")
        .build();
    let mut search_path = vec![bin.clone()];
    search_path.extend(env::split_paths(&env::var_os("PATH").unwrap()));
    let search_path = env::join_paths(&search_path).unwrap();

    for command in [
        "-Zohm-clippy-codegen test --lib",
        "-Zohm-clippy-codegen reinvoke",
    ] {
        p.change_file(
            ".cargo/config.toml",
            "[env]\nCARGO_OHM_CLIPPY_ARGS = '-Dwarnings'\n",
        );
        cargo(&p, &bin, command)
            .env("PATH", &search_path)
            .with_status(101)
            .with_stderr_contains("[ERROR] unused variable: `unused`")
            .run();

        cargo(&p, &bin, command)
            .env("PATH", &search_path)
            .env("CARGO_OHM_CLIPPY_ARGS", "-Awarnings")
            .run();

        p.change_file(
            ".cargo/config.toml",
            "[env]\nCARGO_OHM_CLIPPY_ARGS = { value = '-Dwarnings', force = true }\n",
        );
        cargo(&p, &bin, command)
            .env("PATH", &search_path)
            .env("CARGO_OHM_CLIPPY_ARGS", "-Awarnings")
            .with_status(101)
            .with_stderr_contains("[ERROR] unused variable: `unused`")
            .run();
    }
}

#[cargo_test]
fn rejects_conflicting_wrappers_unsupported_drivers_and_non_lint_arguments() {
    let bin = mock_toolchain();
    let p = project().file("src/lib.rs", "").build();
    for wrapper in ["RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"] {
        cargo(&p, &bin, "-Zohm-clippy-codegen build")
            .env(wrapper, "another-wrapper")
            .with_status(101)
            .with_stderr_contains("[ERROR] -Zohm-clippy-codegen cannot be combined with a rustc wrapper or workspace wrapper")
            .run();
    }
    cargo(&p, &bin, "-Zohm-clippy-codegen build")
        .env("OHM_TEST_CAPABILITY", "unsupported")
        .env("CARGO_CACHE_RUSTC_INFO", "0")
        .with_status(101)
        .with_stderr_contains("[ERROR] [..] does not support -Zohm-clippy-codegen")
        .run();
    cargo(&p, &bin, "-Zohm-clippy-codegen build")
        .env("OHM_TEST_MISMATCH", "1")
        .env("CARGO_CACHE_RUSTC_INFO", "0")
        .with_status(101)
        .with_stderr_contains(
            "[ERROR] -Zohm-clippy-codegen requires Clippy and rustc from the same compiler build",
        )
        .run();
    cargo(&p, &bin, "-Zohm-clippy-codegen build")
        .env("CARGO_OHM_CLIPPY_ARGS", "--cfg clippy")
        .with_status(101)
        .with_stderr_contains("[ERROR] CARGO_OHM_CLIPPY_ARGS accepts only lint levels [..]")
        .run();
    cargo(&p, &bin, "-Zohm-clippy-codegen build")
        .env(
            "CARGO_OHM_CLIPPY_ARGS",
            "-Wfoo__CLIPPY_HACKERY__--cfg__CLIPPY_HACKERY__clippy",
        )
        .with_status(101)
        .with_stderr_contains("[ERROR] CARGO_OHM_CLIPPY_ARGS contains an invalid lint name [..]")
        .run();
    p.change_file(
        "build.rs",
        "fn main() { println!(\"cargo:rustc-env=CLIPPY_CODEGEN=0\"); }",
    );
    cargo(&p, &bin, "-Zohm-clippy-codegen build")
        .with_status(101)
        .with_stderr_contains("[ERROR] -Zohm-clippy-codegen does not support build-script overrides of CLIPPY_CODEGEN")
        .run();
}
