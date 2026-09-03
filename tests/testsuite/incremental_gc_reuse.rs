//! Configuration and worktree reuse with incremental-cache tracking enabled.

#![cfg(any(target_os = "linux", target_os = "macos"))]

use std::fs;
use std::path::{Path, PathBuf};

use crate::prelude::*;
use cargo_test_support::{Execs, Project, git, paths, project};
use serde_json::Value;

const MARKER: &str = ".ohm-incremental-gc.json";
const FLAGS: &str = "-Zfine-grain-locking -Zohm-shared-registry-cache";

fn cargo(project: &Project, command: &str) -> Execs {
    untracked_cargo(project, &format!("-Zohm-incremental-gc {command}"))
}

fn untracked_cargo(project: &Project, command: &str) -> Execs {
    let mut cargo = crate::build_dir::shared_registry_cargo(project, &format!("{FLAGS} {command}"));
    cargo
        .masquerade_as_nightly_cargo(&[
            "fine-grain-locking",
            "ohm-shared-registry-cache",
            "ohm-incremental-gc",
        ])
        .env("CARGO_INCREMENTAL", "1")
        .env("CARGO_TARGET_DIR", project.build_dir())
        .env("CARGO_BUILD_BUILD_DIR", paths::root().join("shared-build"));
    cargo
}

fn markers() -> Vec<PathBuf> {
    let mut markers = walkdir::WalkDir::new(paths::root().join("shared-build/debug/incremental"))
        .into_iter()
        .map(Result::unwrap)
        .filter(|entry| entry.file_name() == MARKER)
        .map(|entry| entry.into_path())
        .collect::<Vec<_>>();
    markers.sort();
    markers
}

fn age(marker: &Path) {
    let mut record: Value = serde_json::from_slice(&fs::read(marker).unwrap()).unwrap();
    record["last_used"] = 1.into();
    fs::write(marker, serde_json::to_vec(&record).unwrap()).unwrap();
}

#[cargo_test]
fn enabling_and_disabling_tracking_preserves_fresh_artifacts() {
    let project = project()
        .file("src/main.rs", "fn main() { println!(\"unchanged\"); }")
        .build();
    untracked_cargo(&project, "build").run();
    assert!(markers().is_empty());
    let binary = fs::read(project.bin("foo")).unwrap();

    cargo(&project, "build -v")
        .with_stderr_contains("[FRESH] foo [..]")
        .with_stderr_does_not_contain("[COMPILING] foo [..]")
        .run();
    let tracked = markers();
    assert_eq!(tracked.len(), 1);
    assert!(
        !walkdir::WalkDir::new(tracked[0].parent().unwrap())
            .into_iter()
            .map(Result::unwrap)
            .any(|entry| entry.file_name() == "dep-graph.bin"),
        "opting in does not eagerly duplicate the existing incremental cache"
    );
    untracked_cargo(&project, "build -v")
        .with_stderr_contains("[FRESH] foo [..]")
        .with_stderr_does_not_contain("[COMPILING] foo [..]")
        .run();
    assert_eq!(fs::read(project.bin("foo")).unwrap(), binary);

    project.change_file("src/main.rs", "fn main() { println!(\"edited\"); }");
    cargo(&project, "build").run();
    assert!(
        walkdir::WalkDir::new(tracked[0].parent().unwrap())
            .into_iter()
            .map(Result::unwrap)
            .any(|entry| entry.file_name() == "dep-graph.bin")
    );
    project
        .process(project.bin("foo"))
        .with_stdout_data("edited\n")
        .run();
}

#[cargo_test(
    nightly,
    reason = "assert-incr-state proves that rustc loads the previous cache"
)]
fn diagnostic_flags_do_not_split_the_existing_incremental_identity() {
    let project = project()
        .file("src/lib.rs", "pub fn value() -> u32 { 42 }")
        .build();
    cargo(&project, "build")
        .env("RUSTFLAGS", "-Zmacro-backtrace=no")
        .run();
    let original = markers();
    assert_eq!(original.len(), 1);

    // Cargo's output unit id includes RUSTFLAGS, but rustc's incremental crate
    // identity does not. These options are also excluded from rustc's incremental
    // dependency hash, so the second compilation must load the previous cache.
    cargo(&project, "build")
        .env(
            "RUSTFLAGS",
            "-Zmacro-backtrace=yes -Zassert-incr-state=loaded",
        )
        .run();
    assert_eq!(markers(), original);
    let rustc_crates = fs::read_dir(original[0].parent().unwrap())
        .unwrap()
        .map(Result::unwrap)
        .filter(|entry| entry.file_type().unwrap().is_dir())
        .count();
    assert_eq!(rustc_crates, 1);

    cargo(&project, "build -v")
        .env("RUSTFLAGS", "-Zmacro-backtrace=no")
        .with_stderr_contains("[FRESH] foo [..]")
        .with_stderr_does_not_contain("[COMPILING] foo [..]")
        .run();
}

#[cargo_test]
fn build_check_and_test_refresh_their_own_configurations() {
    let project = project()
        .file("src/lib.rs", "pub fn value() -> u32 { 42 }")
        .build();
    cargo(&project, "build").run();
    let build = markers();
    assert_eq!(build.len(), 1);
    cargo(&project, "check").run();
    let check = markers()
        .into_iter()
        .filter(|marker| !build.contains(marker))
        .collect::<Vec<_>>();
    assert_eq!(check.len(), 1);
    cargo(&project, "test --no-run").run();
    let test = markers()
        .into_iter()
        .filter(|marker| !build.contains(marker) && !check.contains(marker))
        .collect::<Vec<_>>();
    assert!(!test.is_empty());

    for marker in markers() {
        age(&marker);
    }
    cargo(&project, "check -v")
        .with_stderr_contains("[FRESH] foo [..]")
        .with_stderr_does_not_contain("[CHECKING] foo [..]")
        .run();
    cargo(&project, "clean incremental --max-age 30days").run();
    assert!(check.iter().all(|marker| marker.is_file()));
    assert!(build.iter().chain(&test).all(|marker| !marker.exists()));

    // Expiry does not turn any of the completed build modes into a dirty unit.
    cargo(&project, "build -v")
        .with_stderr_contains("[FRESH] foo [..]")
        .with_stderr_does_not_contain("[COMPILING] foo [..]")
        .run();
    cargo(&project, "test --no-run -v")
        .with_stderr_contains("[FRESH] foo [..]")
        .with_stderr_does_not_contain("[COMPILING] foo [..]")
        .run();
}

#[cargo_test(
    nightly,
    reason = "worktree seeds use checksum freshness and cwd remapping"
)]
fn tracked_worktree_seeds_remain_private_and_reusable() {
    let donor = git::new("donor", |project| {
        project
            .file(".gitignore", "/target\n/Cargo.lock\n")
            .file("src/main.rs", "fn main() { println!(\"donor\"); }")
    });
    let destination = paths::root().join("seeded");
    let seeded_cargo = |command: &str| {
        let mut command = cargo(&donor, &format!("-Zohm-defaults {command}"));
        command
            .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-incremental-gc"])
            .env_remove("CARGO_TARGET_DIR")
            .env_remove(cargo::CARGO_INHERITED_OHM_DEFAULTS_ENV)
            .env_remove(cargo::CARGO_INHERITED_OHM_WORKTREE_SEEDS_ENV)
            .env_remove("CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST");
        command
    };
    seeded_cargo("build").run();
    let donor_marker = markers().pop().unwrap();
    let donor_record = fs::read(&donor_marker).unwrap();
    let donor_binary = fs::read(donor.bin("foo")).unwrap();
    let donor_incremental = donor_marker
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .parent()
        .unwrap();
    let donor_trash = donor_incremental.join("ohm-gc-trash-v1");
    fs::create_dir(&donor_trash).unwrap();
    fs::write(donor_trash.join("retired-payload"), b"partly deleted cache").unwrap();
    seeded_cargo("worktree add -b charlie/seeded")
        .arg(&destination)
        .run();
    let recipient_marker = markers()
        .into_iter()
        .find(|marker| *marker != donor_marker)
        .unwrap();
    assert_eq!(fs::read(&recipient_marker).unwrap(), donor_record);
    assert!(!same_file::is_same_file(&donor_marker, &recipient_marker).unwrap());
    let recipient_incremental = recipient_marker
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .parent()
        .unwrap();
    assert!(
        !recipient_incremental.join("ohm-gc-trash-v1").exists(),
        "worktree seeding must not copy retired incremental data"
    );
    assert_eq!(
        fs::read(donor_trash.join("retired-payload")).unwrap(),
        b"partly deleted cache"
    );
    assert!(
        walkdir::WalkDir::new(recipient_marker.parent().unwrap())
            .into_iter()
            .map(Result::unwrap)
            .any(|entry| entry.file_name() == "query-cache.bin")
    );
    seeded_cargo("build -v")
        .cwd(&destination)
        .with_stderr_contains("[FRESH] foo [..]")
        .with_stderr_does_not_contain("[COMPILING] foo [..]")
        .run();
    fs::write(
        destination.join("src/main.rs"),
        "fn main() { println!(\"recipient\"); }",
    )
    .unwrap();
    seeded_cargo("build -v")
        .cwd(&destination)
        .with_stderr_contains("[COMPILING] foo [..]")
        .run();
    let recipient_binary = destination
        .join("target/debug")
        .join(format!("foo{}", std::env::consts::EXE_SUFFIX));
    donor
        .process(&recipient_binary)
        .with_stdout_data("recipient\n")
        .run();
    assert_eq!(fs::read(donor.bin("foo")).unwrap(), donor_binary);
    assert_eq!(fs::read(&donor_marker).unwrap(), donor_record);

    age(&donor_marker);
    age(&recipient_marker);
    let aged_donor = fs::read(&donor_marker).unwrap();
    seeded_cargo("clean incremental --max-age 30days")
        .cwd(&destination)
        .run();
    assert!(!recipient_marker.exists());
    assert_eq!(fs::read(&donor_marker).unwrap(), aged_donor);
    assert_eq!(fs::read(donor.bin("foo")).unwrap(), donor_binary);
    seeded_cargo("build -v")
        .cwd(&destination)
        .with_stderr_contains("[FRESH] foo [..]")
        .with_stderr_does_not_contain("[COMPILING] foo [..]")
        .run();
    donor
        .process(&recipient_binary)
        .with_stdout_data("recipient\n")
        .run();
}
