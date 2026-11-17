//! Externally published directory artifacts must outlive their private target's expiry.

#![cfg(any(target_os = "linux", target_os = "macos"))]

use std::fs;
use std::time::{Duration, SystemTime};

use crate::prelude::*;
use crate::utils::cargo_process;
use cargo_test_support::{Execs, Project, basic_manifest, paths, project};

fn shared_cargo(project: &Project, command: &str) -> Execs {
    let mut command = crate::build_dir::shared_registry_cargo(
        project,
        &format!("-Zohm-defaults=no -Zohm-shared-registry-cache {command}"),
    );
    command
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-shared-registry-cache", "artifact-dir"])
        .env("CARGO_BUILD_BUILD_DIR", paths::root().join("shared-build"));
    command
}

#[cargo_test]
fn idle_target_cleanup_preserves_external_directory_exports_and_legacy_pins() {
    let wrapper = project()
        .at("directory-output-wrapper")
        .file("Cargo.toml", &basic_manifest("directory-output-wrapper", "0.1.0"))
        .file(
            "src/main.rs",
            r#"
                fn main() {
                    let mut args = std::env::args_os().skip(1);
                    let rustc = args.next().unwrap();
                    let args: Vec<_> = args.collect();
                    let status = std::process::Command::new(rustc).args(&args).status().unwrap();
                    if status.success() && args.windows(2).any(|a| a[0] == "--crate-name" && a[1] == "exported") {
                        let out = args.windows(2).find(|a| a[0] == "--out-dir").unwrap();
                        let binary = std::fs::read_dir(&out[1]).unwrap().map(|entry| entry.unwrap().path())
                            .find(|path| path.extension().is_none() && path.is_file()).unwrap();
                        std::fs::remove_file(&binary).unwrap();
                        std::fs::create_dir(&binary).unwrap();
                        std::fs::write(binary.join("symbols"), b"published symbols").unwrap();
                    }
                    std::process::exit(status.code().unwrap_or(1));
                }
            "#,
        )
        .build();
    wrapper.cargo("build").run();
    let project = project()
        .at("exported")
        .file("Cargo.toml", &basic_manifest("exported", "0.1.0"))
        .file("src/main.rs", "fn main() {}")
        .build();
    let published = paths::root().join("published");
    shared_cargo(&project, "-Zunstable-options build --artifact-dir")
        .arg(&published)
        .env(
            "RUSTC_WORKSPACE_WRAPPER",
            wrapper.bin("directory-output-wrapper"),
        )
        .run();
    let target = project.root().join("target");
    let export = published.join("exported");
    assert!(export.is_symlink());
    let backing = export.canonicalize().unwrap();
    let context = backing
        .ancestors()
        .find(|path| path.join(".ohm-private-context-export-v1").is_file())
        .unwrap();
    let marker = context.join(".ohm-private-context-export-v1");
    assert!(!context.join(".ohm-private-context-v1").exists());
    assert!(
        marker.is_file(),
        "unmarked compiler contexts also need an export pin"
    );
    for legacy in [false, true] {
        if legacy {
            fs::rename(&marker, context.join(".ohm-private-context-keep-v1")).unwrap();
        }
        let disposable = target.join("unused");
        fs::write(&disposable, b"private").unwrap();
        fs::File::open(target.join(".ohm-target-last-use-v1"))
            .unwrap()
            .set_modified(SystemTime::now() - Duration::from_secs(7200))
            .unwrap();
        for dry_run in [true, false] {
            cargo_process(if dry_run { "gc --dry-run" } else { "gc" })
                .cwd(paths::root())
                .env_remove("CARGO_BUILD_BUILD_DIR")
                .run();
            assert_eq!(
                fs::read(export.join("symbols")).unwrap(),
                b"published symbols"
            );
            assert_eq!(disposable.exists(), dry_run);
        }
    }
    assert!(!target.join("debug/exported").exists());
}

#[cargo_test]
fn obsolete_context_cleanup_preserves_nested_projects() {
    let outer = project().file("src/main.rs", "fn main() {}").build();
    shared_cargo(&outer, "build").run();
    let target = outer.root().join("target");
    let namespace = fs::read_dir(target.join("debug/build/workspaces"))
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path();
    let rustup = paths::root().join("rustup");
    let installation = rustup.join("installation");
    fs::create_dir_all(installation.join("bin")).unwrap();
    fs::write(installation.join("bin/rustc"), b"installed compiler").unwrap();
    fs::write(installation.join(".ohm-version"), b"ohm-1.98.1-2\n").unwrap();
    let toolchains = rustup.join("toolchains");
    fs::create_dir(&toolchains).unwrap();
    std::os::unix::fs::symlink(&installation, toolchains.join("ohm")).unwrap();
    let contexts = ["v2-0000000000000001", "v2-0000000000000002"].map(|id| {
        let context = namespace.join(id);
        fs::create_dir(&context).unwrap();
        let mut proof = format!("{id}\nohm-1.98.1-1\n").into_bytes();
        proof.extend(cargo_util::paths::path2bytes(&toolchains.canonicalize().unwrap()).unwrap());
        fs::write(context.join(".ohm-private-context-v1"), proof).unwrap();
        fs::write(context.join("private"), b"private state").unwrap();
        context
    });
    let nested = project()
        .at(contexts[0].join("nested-project"))
        .file(
            "Cargo.toml",
            &format!("{}\n[workspace]\n", basic_manifest("nested", "0.1.0")),
        )
        .file("src/main.rs", "fn main() {}")
        .build();
    shared_cargo(&nested, "build").run();
    let gc = |dry_run| {
        let mut command = cargo_process(if dry_run { "gc --dry-run" } else { "gc" });
        command
            .cwd(paths::root())
            .env_remove("CARGO_BUILD_BUILD_DIR")
            .env("RUSTUP_HOME", &rustup)
            .env(
                "RUSTC",
                std::path::Path::new(&paths::sysroot()).join("bin/rustc"),
            );
        command
    };
    for dry_run in [true, false] {
        gc(dry_run)
            .with_stderr_contains(
                "[SKIPPING] [..] (contains an independently owned directory at [..])",
            )
            .run();
        assert!(nested.root().join("src/main.rs").is_file());
        assert!(nested.root().join("target/debug/nested").is_file());
        assert!(
            contexts[0].join("private").is_file(),
            "a skipped context stays intact"
        );
        assert_eq!(contexts[1].exists(), dry_run);
    }
    fs::remove_dir_all(nested.root()).unwrap();
    gc(false).run();
    assert!(
        !contexts[0].exists(),
        "the original proof allows cleanup after foreign data is removed"
    );
}
