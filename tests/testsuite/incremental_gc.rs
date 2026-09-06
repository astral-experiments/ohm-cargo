//! Eviction of tracked, workspace-private incremental build configurations.

#![cfg(any(target_os = "linux", target_os = "macos"))]

use std::fs;
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use crate::prelude::*;
use cargo_test_support::{Execs, Project, paths, project};
use serde_json::Value;

const RECORD: &str = ".ohm-incremental-gc.json";
const FLAGS: &str = "-Zfine-grain-locking -Zohm-shared-registry-cache -Zohm-incremental-gc";

fn fixture() -> Project {
    project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "foo"
                version = "0.1.0"
                edition = "2021"

                [features]
                recent = []
                reused = []

                [profile.release]
                incremental = true
            "#,
        )
        .file(
            "src/main.rs",
            r#"
                fn main() {
                    println!("{}", if cfg!(feature = "recent") {
                        "recent"
                    } else if cfg!(feature = "reused") {
                        "reused"
                    } else {
                        "default"
                    });
                }
            "#,
        )
        .build()
}

fn shared_build() -> PathBuf {
    paths::root().join("shared-build")
}

fn cargo(p: &Project, command: &str) -> Execs {
    let mut cargo = crate::build_dir::shared_registry_cargo(p, &format!("{FLAGS} {command}"));
    cargo
        .masquerade_as_nightly_cargo(&[
            "fine-grain-locking",
            "ohm-shared-registry-cache",
            "ohm-incremental-gc",
        ])
        // The test harness disables incremental compilation by default.
        .env("CARGO_INCREMENTAL", "1")
        .env("CARGO_TARGET_DIR", p.build_dir())
        .env("CARGO_BUILD_BUILD_DIR", shared_build());
    cargo
}

fn managed_root(profile: &str) -> PathBuf {
    let namespaces = fs::read_dir(shared_build().join(profile).join("incremental"))
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .collect::<Vec<_>>();
    assert_eq!(namespaces.len(), 1, "one workspace namespace");
    namespaces[0].join("ohm-gc-v1")
}

fn units(profile: &str) -> Vec<PathBuf> {
    let mut units = fs::read_dir(managed_root(profile))
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .collect::<Vec<_>>();
    units.sort();
    units
}

fn record(unit: &Path) -> Value {
    serde_json::from_slice(&fs::read(unit.join(RECORD)).unwrap()).unwrap()
}

fn age(unit: &Path) {
    let timestamp = (SystemTime::now() - Duration::from_secs(60 * 24 * 60 * 60))
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs();
    let mut record = record(unit);
    record["last_used"] = timestamp.into();
    fs::write(unit.join(RECORD), serde_json::to_vec(&record).unwrap()).unwrap();
}

#[cargo_test]
fn evicts_stale_variants_but_preserves_recent_and_freshly_reused_variants() {
    let p = fixture();
    cargo(&p, "build").run();
    let stale = units("debug").pop().unwrap();
    assert_eq!(record(&stale)["version"], 2);
    assert_eq!(
        record(&stale)["unit"],
        stale.file_name().unwrap().to_str().unwrap()
    );
    assert!(
        walkdir::WalkDir::new(&stale)
            .into_iter()
            .map(Result::unwrap)
            .any(|entry| entry.file_name() == "dep-graph.bin"),
        "the tracked unit must own real rustc incremental data"
    );

    cargo(&p, "build --features recent").run();
    let recent = units("debug")
        .into_iter()
        .find(|unit| unit != &stale)
        .unwrap();
    cargo(&p, "build --features reused").run();
    let reused = units("debug")
        .into_iter()
        .find(|unit| unit != &stale && unit != &recent)
        .unwrap();
    assert_eq!(units("debug").len(), 3);

    age(&stale);
    age(&reused);
    let old_timestamp = record(&reused)["last_used"].as_u64().unwrap();
    cargo(&p, "build --features reused -v")
        .with_stderr_contains("[FRESH] foo v0.1.0 ([..])")
        .with_stderr_does_not_contain("[COMPILING] foo [..]")
        .run();
    assert!(record(&reused)["last_used"].as_u64().unwrap() > old_timestamp);

    let binary = fs::read(p.bin("foo")).unwrap();
    let records = [&stale, &recent, &reused].map(|unit| fs::read(unit.join(RECORD)).unwrap());
    cargo(&p, "clean incremental --max-age 30days --dry-run").run();
    assert_eq!(units("debug").len(), 3);
    assert_eq!(
        [&stale, &recent, &reused].map(|unit| fs::read(unit.join(RECORD)).unwrap()),
        records,
        "dry-run must not mutate tracking records"
    );

    cargo(&p, "clean incremental --max-age 30days").run();
    assert!(!stale.exists());
    assert!(recent.is_dir());
    assert!(reused.is_dir());
    assert_eq!(fs::read(p.bin("foo")).unwrap(), binary);
    cargo(&p, "build --features reused -v")
        .with_stderr_contains("[FRESH] foo v0.1.0 ([..])")
        .run();

    // Revisit an evicted configuration after a source edit: rustc reconstructs
    // the cache and still produces the expected executable.
    p.change_file("src/main.rs", "fn main() { println!(\"rebuilt\"); }");
    cargo(&p, "build")
        .with_stderr_contains("[COMPILING] foo v0.1.0 ([..])")
        .run();
    assert!(stale.join(RECORD).is_file());
    p.process(p.bin("foo")).with_stdout_data("rebuilt\n").run();

    cargo(&p, "clean -p foo").run();
    assert!(!stale.exists());
    assert!(!recent.exists());
    assert!(!reused.exists());
}

#[cargo_test]
fn tracking_and_cleaning_require_opt_in() {
    let p = fixture();
    crate::build_dir::shared_registry_cargo(&p, "-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache"])
        .env("CARGO_INCREMENTAL", "1")
        .env("CARGO_TARGET_DIR", p.build_dir())
        .env("CARGO_BUILD_BUILD_DIR", shared_build())
        .run();
    assert!(!managed_root("debug").exists());
    assert!(
        walkdir::WalkDir::new(shared_build().join("debug/incremental"))
            .into_iter()
            .map(Result::unwrap)
            .any(|entry| entry.file_name() == "dep-graph.bin")
    );

    p.cargo("clean incremental --max-age 30days")
        .env("CARGO_BUILD_BUILD_DIR", shared_build())
        .with_status(101)
        .with_stderr_contains("[..]ohm-incremental-gc[..]")
        .run();
}

#[cargo_test]
fn skips_active_profiles_and_cleans_other_profiles() {
    let p = fixture();
    cargo(&p, "build").run();
    cargo(&p, "build --release").run();
    let debug = units("debug").pop().unwrap();
    let release = units("release").pop().unwrap();
    age(&debug);
    age(&release);

    let active = fs::File::open(shared_build().join("debug/.cargo-build-lock")).unwrap();
    active.lock_shared().unwrap();
    cargo(&p, "clean incremental --max-age 30days").run();
    assert!(
        debug.is_dir(),
        "a live build holds the profile's shared lock"
    );
    assert!(
        !release.exists(),
        "an idle profile can be evicted independently"
    );

    drop(active);
    cargo(&p, "clean incremental --max-age 30days").run();
    assert!(!debug.exists());
    assert!(p.bin("foo").is_file());
    assert!(p.release_bin("foo").is_file());
}

#[cargo_test]
fn leaves_malformed_untracked_and_unknown_version_caches_untouched() {
    let p = fixture();
    cargo(&p, "build").run();
    let malformed = units("debug").pop().unwrap();
    age(&malformed);
    let old_record = record(&malformed);
    fs::write(malformed.join(RECORD), b"not json").unwrap();

    let untracked = managed_root("debug").join("foo-0000000000000000");
    fs::create_dir(&untracked).unwrap();
    fs::write(untracked.join("important"), b"untracked").unwrap();

    let future = managed_root("debug").join("foo-1111111111111111");
    fs::create_dir(&future).unwrap();
    let mut future_record = old_record.clone();
    future_record["version"] = 3.into();
    future_record["unit"] = future.file_name().unwrap().to_str().unwrap().into();
    fs::write(
        future.join(RECORD),
        serde_json::to_vec(&future_record).unwrap(),
    )
    .unwrap();

    let mismatched = managed_root("debug").join("foo-2222222222222222");
    fs::create_dir(&mismatched).unwrap();
    fs::write(
        mismatched.join(RECORD),
        serde_json::to_vec(&old_record).unwrap(),
    )
    .unwrap();

    cargo(&p, "clean incremental --max-age 30days").run();
    assert_eq!(fs::read(malformed.join(RECORD)).unwrap(), b"not json");
    assert_eq!(fs::read(untracked.join("important")).unwrap(), b"untracked");
    assert_eq!(record(&future), future_record);
    assert_eq!(record(&mismatched), old_record);
}

#[cfg(unix)]
#[cargo_test]
fn does_not_follow_symlinked_units_or_records() {
    let p = fixture();
    cargo(&p, "build").run();
    let unit = units("debug").pop().unwrap();
    age(&unit);
    let original_record = fs::read(unit.join(RECORD)).unwrap();

    let outside = paths::root().join("outside-incremental");
    fs::rename(&unit, &outside).unwrap();
    p.symlink(&outside, &unit);
    cargo(&p, "clean incremental --max-age 30days").run();
    assert!(unit.is_symlink());
    assert_eq!(fs::read(outside.join(RECORD)).unwrap(), original_record);

    fs::remove_file(&unit).unwrap();
    fs::rename(&outside, &unit).unwrap();
    let outside_record = paths::root().join("outside-record.json");
    fs::rename(unit.join(RECORD), &outside_record).unwrap();
    p.symlink(&outside_record, unit.join(RECORD));
    cargo(&p, "clean incremental --max-age 30days").run();
    assert!(unit.join(RECORD).is_symlink());
    assert_eq!(fs::read(outside_record).unwrap(), original_record);
}

#[cargo_test]
fn cleaning_one_workspace_preserves_another_workspace_in_the_same_build_root() {
    let first = fixture();
    cargo(&first, "build").run();
    let first_unit = units("debug").pop().unwrap();

    // Reuse the crate name and shared root, but keep this workspace's mutable
    // incremental state and final artifacts in their own namespaces.
    let other = project()
        .at("other")
        .file(
            "src/main.rs",
            "fn main() { println!(\"other workspace\"); }",
        )
        .build();
    cargo(&other, "build").run();
    let all_units = walkdir::WalkDir::new(shared_build().join("debug/incremental"))
        .into_iter()
        .map(Result::unwrap)
        .filter(|entry| entry.file_name() == RECORD)
        .map(|entry| entry.path().parent().unwrap().to_path_buf())
        .collect::<Vec<_>>();
    assert_eq!(all_units.len(), 2);
    let other_unit = all_units
        .into_iter()
        .find(|unit| unit != &first_unit)
        .unwrap();
    assert_ne!(first_unit.parent(), other_unit.parent());
    age(&first_unit);
    age(&other_unit);
    let other_record = fs::read(other_unit.join(RECORD)).unwrap();
    let other_binary = fs::read(other.bin("foo")).unwrap();

    cargo(&first, "clean incremental --max-age 30days").run();
    assert!(!first_unit.exists());
    assert_eq!(fs::read(other_unit.join(RECORD)).unwrap(), other_record);
    assert_eq!(fs::read(other.bin("foo")).unwrap(), other_binary);

    cargo(&other, "build -v")
        .with_stderr_contains("[FRESH] foo [..]")
        .with_stderr_does_not_contain("[COMPILING] foo [..]")
        .run();
    other
        .process(other.bin("foo"))
        .with_stdout_data("other workspace\n")
        .run();
}

#[cargo_test]
fn inherited_tracking_setting_allows_nested_private_builds() {
    let p = project()
        .file("src/main.rs", "fn main() {}")
        .file(
            "build.rs",
            r#"
                use std::{env, process::Command};

                fn main() {
                    assert_eq!(
                        env::var("CARGO_UNSTABLE_OHM_INCREMENTAL_GC").unwrap(),
                        "true"
                    );
                    let target = env::var_os("OHM_NESTED_TARGET").unwrap();
                    let output = Command::new(env::var_os("CARGO").unwrap())
                        .args([
                            "-Zohm-shared-registry-cache", "build",
                            "--manifest-path", "helper/Cargo.toml",
                            "--target-dir",
                        ])
                        .arg(&target)
                        .env("CARGO_TARGET_DIR", &target)
                        .output()
                        .unwrap();
                    assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stderr));
                }
            "#,
        )
        .file(
            "helper/Cargo.toml",
            r#"
                [package]
                name = "nested-helper"
                version = "0.1.0"
                edition = "2021"
                [workspace]
            "#,
        )
        .file("helper/src/lib.rs", "pub fn value() -> u32 { 7 }")
        .build();
    let nested_target = p.root().join("nested-target");
    crate::build_dir::shared_registry_cargo(&p, "-Zohm-shared-registry-cache build")
        .masquerade_as_nightly_cargo(&["ohm-shared-registry-cache", "ohm-incremental-gc"])
        .env("CARGO_UNSTABLE_OHM_INCREMENTAL_GC", "true")
        .env("CARGO_INCREMENTAL", "1")
        .env("CARGO_TARGET_DIR", p.build_dir())
        .env("CARGO_BUILD_BUILD_DIR", shared_build())
        .env("OHM_NESTED_TARGET", &nested_target)
        .run();

    assert!(!units("debug").is_empty(), "the outer build is tracked");
    let nested_files = walkdir::WalkDir::new(nested_target.join("debug/incremental"))
        .into_iter()
        .map(Result::unwrap)
        .collect::<Vec<_>>();
    assert!(
        nested_files
            .iter()
            .any(|entry| entry.file_name() == "dep-graph.bin")
    );
    assert!(nested_files.iter().all(|entry| entry.file_name() != RECORD));
    assert!(
        nested_files
            .iter()
            .all(|entry| entry.file_name() != "ohm-gc-v1")
    );
    assert!(units("debug").iter().all(|unit| {
        !unit
            .file_name()
            .unwrap()
            .to_str()
            .unwrap()
            .starts_with("nested_helper-")
    }));
}

#[cargo_test]
fn interrupted_trash_deletion_cannot_expose_partial_sessions_to_rustc() {
    let p = fixture();
    let source = "fn warn() { let unused = 1; }\nfn main() { warn(); println!(\"first\"); }\n";
    p.change_file("src/main.rs", source);
    cargo(&p, "build")
        .with_stderr_contains("[WARNING] unused variable: `unused`")
        .run();
    let unit = units("debug").pop().unwrap();
    let trash = managed_root("debug").with_file_name("ohm-gc-trash-v1");
    fs::create_dir(&trash).unwrap();
    let retired = trash.join(unit.file_name().unwrap());
    fs::rename(&unit, &retired).unwrap();

    // Recreate interruption after the atomic retirement and deletion of just the
    // query cache. Reusing this finalized session would panic while replaying
    // the cached unused-variable diagnostic from its surviving dep-graph.
    let query_cache = walkdir::WalkDir::new(&retired)
        .into_iter()
        .map(Result::unwrap)
        .find(|entry| entry.file_name() == "query-cache.bin")
        .unwrap();
    fs::remove_file(query_cache.path()).unwrap();
    assert!(
        walkdir::WalkDir::new(&retired)
            .into_iter()
            .map(Result::unwrap)
            .any(|entry| entry.file_name() == "dep-graph.bin")
    );
    cargo(&p, "build -v")
        .with_stderr_contains("[FRESH] foo [..]")
        .run();
    assert!(unit.join(RECORD).is_file());
    p.change_file("src/main.rs", &source.replace("first", "second"));
    cargo(&p, "build")
        .with_stderr_contains("[WARNING] unused variable: `unused`")
        .run();
    p.process(p.bin("foo")).with_stdout_data("second\n").run();

    // The previous trash marker is recent, but retirement is unconditional.
    // A dry run must also handle a new eligible unit with the same name as the
    // trash entry that it would remove first.
    age(&unit);
    cargo(&p, "clean incremental --max-age 30days --dry-run")
        .with_stderr_contains("[..]1 configurations eligible, 1 trash entries eligible[..]")
        .run();
    assert!(retired.join(RECORD).is_file());
    assert!(unit.join(RECORD).is_file());
    cargo(&p, "clean incremental --max-age 30days").run();
    assert!(!retired.exists());
    assert!(!unit.exists());

    // Package-scoped cleaning also removes retired configurations.
    cargo(&p, "build").run();
    fs::rename(&unit, &retired).unwrap();
    cargo(&p, "clean -p foo").run();
    assert!(!retired.exists());
}

#[cargo_test]
fn trash_recovery_preserves_unknown_data_and_removes_only_empty_unmarked_entries() {
    let p = fixture();
    cargo(&p, "build").run();
    let unit = units("debug").pop().unwrap();
    age(&unit);
    let trash = managed_root("debug").with_file_name("ohm-gc-trash-v1");
    fs::create_dir(&trash).unwrap();

    let collision = trash.join(unit.file_name().unwrap());
    fs::create_dir(&collision).unwrap();
    fs::write(collision.join("important"), "unrecognized payload").unwrap();
    cargo(&p, "clean incremental --max-age 30days").run();
    assert!(unit.join(RECORD).is_file());
    assert_eq!(
        fs::read_to_string(collision.join("important")).unwrap(),
        "unrecognized payload"
    );

    let unknown = trash.join("foo-0000000000000000");
    fs::rename(collision, &unknown).unwrap();
    let empty = trash.join("foo-1111111111111111");
    fs::create_dir(&empty).unwrap();
    let alias = trash.join("foo-2222222222222222");
    p.symlink(&unknown, &alias);

    cargo(&p, "clean incremental --max-age 30days --dry-run").run();
    assert!(empty.is_dir());
    cargo(&p, "clean incremental --max-age 30days").run();
    assert!(!unit.exists());
    assert!(!empty.exists());
    assert!(alias.is_symlink());
    assert_eq!(
        fs::read_to_string(unknown.join("important")).unwrap(),
        "unrecognized payload"
    );
}

#[cargo_test]
fn unicode_target_names_can_be_tracked_and_expired() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
                [package]
                name = "unicode-target"
                version = "0.1.0"
                edition = "2021"

                [[bin]]
                name = "café"
                path = "src/main.rs"
            "#,
        )
        .file("src/main.rs", "fn main() { println!(\"unicode\"); }")
        .build();
    cargo(&p, "build").run();
    let unit = units("debug").pop().unwrap();
    assert!(
        unit.file_name()
            .unwrap()
            .to_str()
            .unwrap()
            .starts_with("café-")
    );
    age(&unit);
    cargo(&p, "clean incremental --max-age 30days").run();
    assert!(!unit.exists());
    p.process(p.bin("café")).with_stdout_data("unicode\n").run();
    cargo(&p, "build -v")
        .with_stderr_contains("[FRESH] unicode-target [..]")
        .run();
}

#[cargo_test]
fn fresh_builds_preserve_recent_records_and_upgrade_legacy_records_once() {
    use std::os::unix::fs::MetadataExt;

    let p = fixture();
    cargo(&p, "build").run();
    let unit = units("debug").pop().unwrap();
    let marker = unit.join(RECORD);
    let original = fs::read(&marker).unwrap();
    let original_inode = fs::metadata(&marker).unwrap().ino();
    cargo(&p, "build -v")
        .with_stderr_contains("[FRESH] foo [..]")
        .run();
    assert_eq!(fs::read(&marker).unwrap(), original);
    assert_eq!(fs::metadata(&marker).unwrap().ino(), original_inode);

    // Upgrade version 1 even when its timestamp is within the refresh window.
    // This ensures only records written with throttling use its expiry grace.
    let mut legacy = record(&unit);
    legacy["version"] = 1.into();
    fs::write(&marker, serde_json::to_vec(&legacy).unwrap()).unwrap();
    cargo(&p, "build -v")
        .with_stderr_contains("[FRESH] foo [..]")
        .run();
    assert_eq!(record(&unit)["version"], 2);
    let upgraded = fs::read(&marker).unwrap();
    let upgraded_inode = fs::metadata(&marker).unwrap().ino();
    assert_ne!(upgraded_inode, original_inode);
    cargo(&p, "build -v")
        .with_stderr_contains("[FRESH] foo [..]")
        .run();
    assert_eq!(fs::read(&marker).unwrap(), upgraded);
    assert_eq!(fs::metadata(&marker).unwrap().ino(), upgraded_inode);
}

#[cargo_test(
    nightly,
    requires = "clippy-driver",
    reason = "isolated bundled Clippy caches must retain cleanup eligibility"
)]
fn isolated_clippy_caches_can_expire_and_be_cleaned_by_package() {
    let p = fixture();
    cargo(&p, "build").run();
    let ordinary = units("debug").pop().unwrap();
    let binary = fs::read(p.bin("foo")).unwrap();
    let driver = PathBuf::from(paths::sysroot()).join("bin/clippy-driver");
    cargo(&p, "check")
        .env("CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION", "true")
        .env("RUSTC_WORKSPACE_WRAPPER", &driver)
        .run();
    let managed = managed_root("debug");
    let isolated = managed.parent().unwrap().join(".ohm-clippy-v1/ohm-gc-v1");
    let clippy = fs::read_dir(&isolated)
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path();
    assert!(clippy.join(RECORD).is_file());
    age(&clippy);
    cargo(&p, "clean incremental --max-age 30days --dry-run")
        .with_stderr_contains("[..]1 configurations eligible[..]")
        .run();
    assert!(clippy.is_dir());
    cargo(&p, "clean incremental --max-age 30days").run();
    assert!(!clippy.exists());
    assert!(ordinary.is_dir());
    assert_eq!(fs::read(p.bin("foo")).unwrap(), binary);
    cargo(&p, "build -v")
        .with_stderr_contains("[FRESH] foo [..]")
        .run();

    cargo(&p, "check --features recent")
        .env("CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION", "true")
        .env("RUSTC_WORKSPACE_WRAPPER", &driver)
        .run();
    let current = fs::read_dir(&isolated)
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path();
    assert!(current.join(RECORD).is_file());
    let namespace = managed.parent().unwrap().file_name().unwrap();
    let private = shared_build()
        .join("debug/build/workspaces")
        .join(namespace);
    assert!(
        walkdir::WalkDir::new(private.join(".ohm-clippy-v1"))
            .into_iter()
            .map(Result::unwrap)
            .any(|entry| entry.file_name() == "foo")
    );
    cargo(&p, "clean -p foo").run();
    assert!(!ordinary.exists());
    assert!(!current.exists());
    assert!(
        !walkdir::WalkDir::new(&private)
            .into_iter()
            .map(Result::unwrap)
            .any(|entry| entry.file_name() == "foo")
    );
    cargo(&p, "check -v")
        .env("CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION", "true")
        .env("RUSTC_WORKSPACE_WRAPPER", &driver)
        .with_stderr_contains("[CHECKING] foo [..]")
        .run();
}

#[cargo_test]
fn cleanup_includes_release_9_namespaces_for_only_the_selected_target() {
    let p = fixture();
    cargo(&p, "build").run();
    let original_unit = units("debug").pop().unwrap();
    let namespace = |version: &str, target: &Path| {
        cargo::util::short_hash(&(
            version,
            p.root().canonicalize().unwrap(),
            target.canonicalize().unwrap(),
        ))
    };
    let current = namespace("ohm-shared-workspace-v3", &p.build_dir());
    let legacy = namespace("ohm-shared-workspace-v2", &p.build_dir());
    let profile = shared_build().join("debug");
    let move_to_legacy = |current: &str, legacy: &str| {
        for root in ["build/workspaces", "incremental"] {
            fs::rename(
                profile.join(root).join(current),
                profile.join(root).join(legacy),
            )
            .unwrap();
        }
    };
    // The previous release used the same layout below a workspace-and-target v2 hash.
    move_to_legacy(&current, &legacy);
    let legacy_incremental = profile.join("incremental").join(&legacy);
    let legacy_unit = legacy_incremental
        .join("ohm-gc-v1")
        .join(original_unit.file_name().unwrap());
    age(&legacy_unit);
    cargo(&p, "build --features recent").run();
    let current_incremental = profile.join("incremental").join(&current);
    let current_unit = fs::read_dir(current_incremental.join("ohm-gc-v1"))
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path();

    // Even another v2 namespace for this same workspace belongs to a different target.
    let other_target = paths::root().join("other-target");
    cargo(&p, "build")
        .env("CARGO_TARGET_DIR", &other_target)
        .run();
    let other_current = namespace("ohm-shared-workspace-v3", &other_target);
    let other_legacy = namespace("ohm-shared-workspace-v2", &other_target);
    move_to_legacy(&other_current, &other_legacy);
    let other_incremental = profile.join("incremental").join(&other_legacy);
    let other_unit = fs::read_dir(other_incremental.join("ohm-gc-v1"))
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path();
    age(&other_unit);
    let other_record = fs::read(other_unit.join(RECORD)).unwrap();
    let other_binary = fs::read(other_target.join("debug/foo")).unwrap();

    cargo(&p, "clean incremental --max-age 30days --dry-run")
        .with_stderr_contains("[..]1 configurations eligible[..]")
        .run();
    assert!(legacy_unit.is_dir());
    assert!(current_unit.is_dir());
    let active = fs::File::open(profile.join(".cargo-build-lock")).unwrap();
    active.lock_shared().unwrap();
    cargo(&p, "clean incremental --max-age 30days").run();
    assert!(
        legacy_unit.is_dir(),
        "the old namespace still shares the profile lock"
    );
    drop(active);
    cargo(&p, "clean incremental --max-age 30days").run();
    assert!(!legacy_unit.exists());
    assert!(current_unit.is_dir());
    assert_eq!(fs::read(other_unit.join(RECORD)).unwrap(), other_record);

    // Package cleanup must also find real configurations in both namespace versions.
    let relocated_unit = legacy_incremental
        .join("ohm-gc-v1")
        .join(current_unit.file_name().unwrap());
    fs::rename(&current_unit, &relocated_unit).unwrap();
    cargo(&p, "build --features reused").run();
    let current_unit = fs::read_dir(current_incremental.join("ohm-gc-v1"))
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path();
    cargo(&p, "clean -p foo --dry-run").run();
    assert!(relocated_unit.is_dir());
    assert!(current_unit.is_dir());
    cargo(&p, "clean -p foo").run();
    assert!(!relocated_unit.exists());
    assert!(!current_unit.exists());
    for workspace in [&current, &legacy] {
        assert!(
            !walkdir::WalkDir::new(profile.join("build/workspaces").join(workspace))
                .into_iter()
                .map(Result::unwrap)
                .any(|entry| entry.file_name() == "foo")
        );
    }

    cargo(&p, "clean --dry-run").run();
    assert!(legacy_incremental.is_dir());
    cargo(&p, "clean").run();
    for workspace in [&current, &legacy] {
        assert!(!profile.join("build/workspaces").join(workspace).exists());
        assert!(!profile.join("incremental").join(workspace).exists());
    }
    assert!(profile.join("build/workspaces").join(other_legacy).is_dir());
    assert_eq!(fs::read(other_unit.join(RECORD)).unwrap(), other_record);
    assert_eq!(
        fs::read(other_target.join("debug/foo")).unwrap(),
        other_binary
    );
}
