//! Explicit reclamation of Ohm's shared build storage without evicting live state.

#![cfg(any(target_os = "linux", target_os = "macos"))]

use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::os::unix::process::CommandExt as _;
use std::path::{Path, PathBuf};
use std::process::{Child, Stdio};
use std::time::{Duration, Instant, SystemTime};

use crate::prelude::*;
use crate::utils::cargo_process;
use cargo_test_support::registry::Package;
use cargo_test_support::{Execs, Project, git, paths, slow_cpu_multiplier, str};

fn shared_root() -> PathBuf {
    paths::root().join("shared-build")
}

fn cargo(project: &Project, command: &str) -> Execs {
    let mut command = crate::build_dir::shared_registry_cargo(
        project,
        &format!("-Zohm-defaults=no -Zohm-shared-registry-cache {command}"),
    );
    command
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-shared-registry-cache"])
        .env("CARGO_BUILD_BUILD_DIR", shared_root())
        .env("CARGO_INCREMENTAL", "1")
        .env_remove("CARGO_TARGET_DIR");
    command
}

fn donor() -> Project {
    Package::new("gc-dependency", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 42 }")
        .publish();
    git::new("donor", |project| {
        project
            .file(
                "Cargo.toml",
                "[package]\nname = \"foo\"\nversion = \"0.0.1\"\n\n[dependencies]\ngc-dependency = \"1.0.0\"\n",
            )
            .file(".gitignore", "/target\n/Cargo.lock\n")
            .file("src/main.rs", "fn main() { println!(\"hello\"); }")
    })
}

fn add_worktree(project: &Project, name: &str) -> PathBuf {
    let path = paths::root().join(name);
    project
        .process("git")
        .args(&["worktree", "add", "--detach"])
        .arg(&path)
        .run();
    path
}

fn remove_worktree(project: &Project, path: &Path) {
    project
        .process("git")
        .args(&["worktree", "remove", "--force"])
        .arg(path)
        .run();
}

fn collect(project: &Project, dry_run: bool) {
    let mut command = cargo(project, "gc --build-dir");
    command.arg(shared_root()).cwd(paths::root());
    if dry_run {
        command.arg("--dry-run");
    }
    command.run();
}

fn private_artifacts(namespace: &str) -> PathBuf {
    shared_root().join("debug/build/workspaces").join(namespace)
}

/// Finds the one private namespace created in this fixture's target directory.
fn local_private_artifacts(target: &Path) -> PathBuf {
    fs::read_dir(target.join("debug/build/workspaces"))
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .find(|path| path.is_dir())
        .unwrap()
}

/// Models worktree state left in the shared root by Cargo before the layout change.
fn legacy_private_state(target: &Path) -> String {
    let local = local_private_artifacts(target);
    let namespace = local.file_name().unwrap().to_str().unwrap();
    let private = private_artifacts(namespace);
    fs::create_dir_all(&private).unwrap();
    fs::write(private.join("legacy-artifact"), b"old build").unwrap();
    let incremental = shared_root().join("debug/incremental").join(namespace);
    fs::create_dir_all(incremental).unwrap();
    namespace.to_owned()
}

fn json_files(directory: &Path) -> Vec<PathBuf> {
    fs::read_dir(directory)
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .filter(|path| {
            path.extension()
                .is_some_and(|extension| extension == "json")
        })
        .collect()
}

fn tracker() -> rusqlite::Connection {
    rusqlite::Connection::open(shared_root().join(".ohm-gc-v1/cache.sqlite")).unwrap()
}

fn context() -> String {
    tracker()
        .query_row("SELECT context FROM contexts", [], |row| row.get(0))
        .unwrap()
}

fn context_record() -> serde_json::Value {
    let bytes: Vec<u8> = tracker()
        .query_row("SELECT record FROM contexts", [], |row| row.get(0))
        .unwrap();
    serde_json::from_slice(&bytes).unwrap()
}

fn dependency_paths() -> Vec<PathBuf> {
    tracker()
        .prepare("SELECT entry FROM dependencies")
        .unwrap()
        .query_map([], |row| row.get::<_, Vec<u8>>(0))
        .unwrap()
        .map(|row| shared_root().join(cargo_util::paths::bytes2path(&row.unwrap()).unwrap()))
        .collect()
}

fn timestamp(time: SystemTime) -> i64 {
    time.duration_since(SystemTime::UNIX_EPOCH)
        .unwrap()
        .as_nanos()
        .try_into()
        .unwrap()
}

fn thinlto_object(context: &str) -> PathBuf {
    let directory = shared_root()
        .join(".ohm-thinlto-cache")
        .join(context)
        .join("0".repeat(32));
    fs::create_dir_all(&directory).unwrap();
    let object = directory.join("1".repeat(32) + ".cache");
    fs::write(&object, b"backend").unwrap();
    object
}

#[cargo_test]
fn thinlto_gc_reports_objects_without_invalidating_warm_builds() {
    let project = donor();
    cargo(&project, "build").run();
    let object = thinlto_object(&context());
    fs::File::open(&object)
        .unwrap()
        .set_modified(SystemTime::now() - Duration::from_secs(3601))
        .unwrap();
    cargo(&project, "gc --dry-run")
        .with_stderr_data(str![[r#"
Would remove ThinLTO objects for context [..] (unused for at least 1 hour)
[SUMMARY] 1 file, [FILE_SIZE]B total
[WARNING] no files deleted due to --dry-run

"#]])
        .run();
    assert!(object.exists());
    cargo(&project, "gc")
        .with_stderr_data(str![[r#"
[REMOVING] ThinLTO objects for context [..] (unused for at least 1 hour)
[REMOVED] 1 file, [FILE_SIZE]B total

"#]])
        .run();
    assert!(!object.exists());
    cargo(&project, "run -v")
        .with_stderr_does_not_contain("[COMPILING] [..]")
        .with_stdout_data("hello\n")
        .run();
}

#[cfg(target_os = "linux")]
#[cargo_test]
fn thinlto_compiler_uses_the_registered_context_and_waits_for_manual_gc() {
    use std::os::unix::fs::PermissionsExt as _;

    let project = donor();
    let compiler = project.root().join("thinlto-rustc");
    // Exercise Cargo's cache wiring with stock and older Ohm compilers too.
    // The compiler-side cache format and hit behavior have their own rustc tests.
    fs::write(&compiler, r#"#!/bin/bash
args=()
cache=
compile=false
for arg in "$@"; do
    case "$arg" in
        -Zthinlto-cache=*) cache="${arg#*=}" ;;
        --emit=*) compile=true; args+=("$arg") ;;
        *) args+=("$arg") ;;
    esac
done
"$OHM_TEST_REAL_RUSTC" "${args[@]}" || exit $?
if $compile && [ -n "$cache" ]; then
    mkdir -p "$cache/00000000000000000000000000000000"
    printf backend > "$cache/00000000000000000000000000000000/11111111111111111111111111111111.cache"
fi
"#).unwrap();
    fs::set_permissions(&compiler, fs::Permissions::from_mode(0o755)).unwrap();
    let build = || {
        let mut command = cargo(&project, "-Zohm-thinlto-cache=yes build --release -v");
        command
            .env("RUSTC", &compiler)
            .env(
                "OHM_TEST_REAL_RUSTC",
                Path::new(&paths::sysroot()).join("bin/rustc"),
            )
            .env("CARGO_INCREMENTAL", "0");
        command
    };
    build().run();
    let cache = shared_root().join(".ohm-thinlto-cache").join(context());
    let object = cache.join("0".repeat(32)).join("1".repeat(32) + ".cache");
    assert_eq!(fs::read(&object).unwrap(), b"backend");
    fs::File::open(&object)
        .unwrap()
        .set_modified(SystemTime::now() - Duration::from_secs(31 * 24 * 3600))
        .unwrap();
    build()
        .with_stderr_does_not_contain("[COMPILING] [..]")
        .run();
    assert!(object.exists(), "warm builds do not prune the shared cache");
    cargo(&project, "clean").run();
    assert!(
        object.exists(),
        "cargo clean preserves shared ThinLTO state"
    );
    collect(&project, false);
    assert!(!object.exists());
}

#[cargo_test]
fn empty_gc_uses_cargo_clean_summaries() {
    cargo_process("gc --dry-run")
        .with_stdout_data("")
        .with_stderr_data(str![[r#"
[SUMMARY] 0 files
[WARNING] no files deleted due to --dry-run

"#]])
        .run();
    cargo_process("gc")
        .with_stdout_data("")
        .with_stderr_data(str![[r#"
[REMOVED] 0 files

"#]])
        .run();
}

#[cargo_test]
fn discovers_legacy_caches_without_writing_during_preview() {
    let root = paths::home().join(".cache/ohm-build/old-project");
    let context = root.join("debug/build/registries/0123456789abcdef-all");
    fs::create_dir_all(&context).unwrap();
    fs::write(root.join(".ohm-shared-registry-cache-v1"), b"").unwrap();
    fs::write(root.join("debug/.cargo-build-lock"), b"").unwrap();
    fs::write(context.join("artifact"), [0; 1024]).unwrap();
    let registry = paths::cargo_home().join(".ohm-build-roots-v1");
    cargo_process("gc --dry-run")
        .with_stderr_contains("Would remove legacy context [..] (no usage records)")
        .with_stderr_contains("[SUMMARY] 1 file, [FILE_SIZE]B total")
        .with_stderr_contains("[WARNING] no files deleted due to --dry-run")
        .run();
    assert!(!root.join(".ohm-gc-v1").exists());
    assert!(!registry.exists());
    assert!(context.join("artifact").is_file());
    cargo_process("gc")
        .with_stderr_contains("[REMOVING] legacy context [..] (no usage records)")
        .with_stderr_contains("[REMOVED] 1 file, [FILE_SIZE]B total")
        .run();
    assert!(!context.exists());
    assert_eq!(json_files(&registry).len(), 1);
}

#[cargo_test]
fn legacy_registry_cleanup_preserves_current_dependencies_and_warm_builds() {
    let project = donor();
    cargo(&project, "build").run();
    let legacy = shared_root().join("debug/build/registries/0000000000000000");
    fs::create_dir(&legacy).unwrap();
    fs::write(legacy.join("artifact"), b"old dependency").unwrap();
    collect(&project, false);
    assert!(!legacy.exists());
    cargo(&project, "run -v")
        .with_stderr_does_not_contain("[COMPILING] [..]")
        .with_stdout_data("hello\n")
        .run();
}

#[cargo_test]
fn dependency_gc_preserves_reused_transitive_dependencies_and_rebuilds_evicted_variants() {
    Package::new("gc-leaf", "1.0.0")
        .file("src/lib.rs", "pub fn value() -> u32 { 42 }")
        .publish();
    Package::new("gc-dependency", "1.0.0")
        .dep("gc-leaf", "1.0.0")
        .feature("extra", &[])
        .file("src/lib.rs", "pub fn value() -> u32 { gc_leaf::value() }")
        .publish();
    let project = cargo_test_support::project()
        .file("Cargo.toml", "[package]\nname = \"foo\"\nversion = \"0.0.1\"\n[dependencies]\ngc-dependency = { version = \"1.0.0\", features = [\"extra\"] }\n")
        .file("src/main.rs", "fn main() { println!(\"{}\", gc_dependency::value()); }")
        .build();
    cargo(&project, "build").run();
    let old_paths = dependency_paths();
    assert_eq!(old_paths.len(), 2, "record the transitive dependency too");
    tracker()
        .execute("UPDATE dependencies SET last_used = 0", [])
        .unwrap();

    project.change_file("Cargo.toml", "[package]\nname = \"foo\"\nversion = \"0.0.1\"\n[dependencies]\ngc-dependency = \"1.0.0\"\n");
    cargo(&project, "build").run();
    assert_eq!(dependency_paths().len(), 3);
    cargo(&project, "gc --dry-run")
        .with_stderr_contains(
            "Would remove dependency [..]/gc-dependency/[..] (unused for at least 1 hour)",
        )
        .with_stderr_does_not_contain("Would remove dependency [..]/gc-leaf/[..]")
        .run();
    assert!(old_paths.iter().all(|path| path.is_dir()));
    collect(&project, false);
    let old = old_paths
        .iter()
        .find(|path| path.parent().unwrap().ends_with("gc-dependency"))
        .unwrap();
    let leaf = old_paths
        .iter()
        .find(|path| path.parent().unwrap().ends_with("gc-leaf"))
        .unwrap();
    assert!(!old.exists());
    assert!(leaf.is_dir());
    cargo(&project, "run")
        .with_stderr_does_not_contain("[COMPILING] [..]")
        .with_stdout_data("42\n")
        .run();
    cargo(&project, "build --features gc-dependency/extra")
        .with_stderr_contains("[COMPILING] gc-dependency v1.0.0")
        .with_stderr_does_not_contain("[COMPILING] gc-leaf [..]")
        .run();
    assert!(old.is_dir());
    assert_eq!(
        dependency_paths().len(),
        3,
        "each compiled variant has one row"
    );
    collect(&project, false);
    assert!(
        old.is_dir(),
        "reusing an evicted variant refreshes its usage"
    );
}

#[cargo_test]
fn checking_reused_build_artifacts_refreshes_their_dependency_usage() {
    let project = donor();
    // A concrete loader search path permits authenticated build-to-check reuse.
    cargo(&project, "-Zohm-reuse-built-deps build")
        .masquerade_as_nightly_cargo(&[
            "ohm-defaults",
            "ohm-shared-registry-cache",
            "ohm-reuse-built-deps",
        ])
        .env(cargo_util::paths::dylib_path_envvar(), project.root())
        .run();
    assert_eq!(dependency_paths().len(), 1);
    tracker()
        .execute("UPDATE dependencies SET last_used = 0", [])
        .unwrap();
    let started = SystemTime::now();
    cargo(&project, "-Zohm-reuse-built-deps check -v")
        .masquerade_as_nightly_cargo(&[
            "ohm-defaults",
            "ohm-shared-registry-cache",
            "ohm-reuse-built-deps",
        ])
        .env(cargo_util::paths::dylib_path_envvar(), project.root())
        .with_stderr_contains("[FRESH] gc-dependency v1.0.0")
        .with_stderr_does_not_contain("[CHECKING] gc-dependency [..]")
        .run();
    let used: i64 = tracker()
        .query_row("SELECT min(last_used) FROM dependencies", [], |row| {
            row.get(0)
        })
        .unwrap();
    assert!(used >= timestamp(started));
    cargo(&project, "gc --dry-run")
        .with_stderr_contains("[SUMMARY] 0 files")
        .run();
}

#[cargo_test]
fn upgrades_retire_fresh_contexts_without_removing_installed_compilers() {
    use std::os::unix::fs::PermissionsExt as _;

    let project = donor();
    cargo(&project, "build").run();
    let mut record = context_record();
    record["ohm_version"] = "ohm-1.98.1-1".into();
    tracker()
        .execute(
            "UPDATE contexts SET record = ?1",
            [serde_json::to_vec(&record).unwrap()],
        )
        .unwrap();
    let registry = shared_root()
        .join("debug/build/registries")
        .join(record["context"].as_str().unwrap());
    let thinlto = thinlto_object(record["context"].as_str().unwrap());
    let private = local_private_artifacts(&project.root().join("target"));
    let compiler = paths::root().join("upgraded-rustc");
    fs::write(&compiler, "#!/bin/sh\ncat <<'VERSION'\nrustc 1.98.1-dev (ohm-1.98.1-2)\nbinary: rustc\ncommit-hash: unknown\nhost: x86_64-unknown-linux-gnu\nrelease: 1.98.1-dev\nLLVM version: 22.1.8\nVERSION\n").unwrap();
    fs::set_permissions(&compiler, fs::Permissions::from_mode(0o755)).unwrap();
    cargo(&project, "gc --dry-run")
        .env("RUSTC", &compiler)
        .with_stderr_contains(
            "Would remove context [..] (from ohm-1.98.1-1; current is ohm-1.98.1-2)",
        )
        .run();
    assert!(registry.is_dir());
    cargo(&project, "gc").env("RUSTC", &compiler).run();
    assert!(!registry.exists());
    assert!(!thinlto.exists());
    assert!(private.is_dir());
    for file in ["compiler", "driver"] {
        assert!(Path::new(record[file]["path"].as_str().unwrap()).is_file());
    }
}

#[cargo_test]
fn preview_and_cleanup_report_the_same_payload_sizes_and_respect_quiet() {
    let project = donor();
    cargo(&project, "build").run();
    let database = shared_root().join(".ohm-gc-v1/cache.sqlite");
    let registry = shared_root().join("debug/build/registries").join(context());
    // Use known payload lengths so the summary can be checked without redactions.
    fs::remove_dir_all(&registry).unwrap();
    fs::create_dir_all(registry.join("nested/empty")).unwrap();
    fs::write(registry.join("first"), [0; 1024]).unwrap();
    fs::write(registry.join("nested/second"), [0; 512]).unwrap();
    fs::write(registry.join("empty-file"), b"").unwrap();
    tracker()
        .execute("UPDATE contexts SET last_used = 0", [])
        .unwrap();
    let before = fs::read(&database).unwrap();
    let preview = cargo(&project, "gc --dry-run --color never")
        .cwd(paths::root())
        .with_stdout_data("")
        .with_stderr_data(str![[r#"
Would remove context [..] (unused for at least 1 hour)
[SUMMARY] [FILE_NUM] files, [FILE_SIZE]B total
[WARNING] no files deleted due to --dry-run

"#]])
        .run();
    assert!(
        std::str::from_utf8(&preview.stderr)
            .unwrap()
            .contains("Summary 3 files, 1.5KiB total")
    );
    assert_eq!(fs::read(&database).unwrap(), before);
    assert_eq!(fs::read(registry.join("first")).unwrap().len(), 1024);
    cargo(&project, "gc --dry-run --quiet")
        .with_stdout_data("")
        .with_stderr_data("")
        .run();
    let collected = cargo(&project, "gc --color never")
        .with_stdout_data("")
        .with_stderr_data(str![[r#"
[REMOVING] context [..] (unused for at least 1 hour)
[REMOVED] [FILE_NUM] files, [FILE_SIZE]B total

"#]])
        .run();
    assert!(
        std::str::from_utf8(&collected.stderr)
            .unwrap()
            .contains("Removed 3 files, 1.5KiB total")
    );
    assert!(!registry.exists());
}

#[cargo_test]
fn fresh_builds_preserve_ownership_records_and_in_tree_targets() {
    let project = donor();
    let worktree = add_worktree(&project, "fresh-worktree");
    cargo(&project, "build").cwd(&worktree).run();
    assert!(worktree.join("target/debug/foo").is_file());
    assert!(!shared_root().join("debug/foo").exists());

    let metadata = shared_root().join(".ohm-gc-v1");
    assert!(
        !metadata.join("workspaces").exists(),
        "new private state needs no global ownership record"
    );
    assert!(local_private_artifacts(&worktree.join("target")).is_dir());
    assert!(!shared_root().join("debug/build/workspaces").exists());
    assert!(!shared_root().join("debug/incremental").exists());
    let provenance = context_record();
    let records = json_files(&paths::home().join(".cargo/.ohm-build-roots-v1"));
    assert_eq!(records.len(), 1);
    let old_mtime = filetime::FileTime::from_unix_time(946_684_800, 0);
    let before = records
        .into_iter()
        .map(|path| {
            let contents = fs::read(&path).unwrap();
            filetime::set_file_mtime(&path, old_mtime).unwrap();
            (path, contents)
        })
        .collect::<Vec<_>>();
    tracker()
        .execute_batch("UPDATE contexts SET last_used = 0; UPDATE dependencies SET last_used = 0;")
        .unwrap();
    let started = timestamp(SystemTime::now());
    cargo(&project, "build -v")
        .cwd(&worktree)
        .with_stderr_contains("[FRESH] foo v0.0.1 [..]")
        .with_stderr_does_not_contain("[COMPILING] [..]")
        .run();
    for table in ["contexts", "dependencies"] {
        let used: i64 = tracker()
            .query_row(&format!("SELECT min(last_used) FROM {table}"), [], |row| {
                row.get(0)
            })
            .unwrap();
        assert!(used >= started);
    }
    assert_eq!(context_record(), provenance, "provenance remains immutable");
    assert!(!metadata.join("contexts").exists());
    assert!(!metadata.join("dependencies").exists());
    assert!(!metadata.join("last-used").exists());
    for (path, contents) in before {
        assert_eq!(fs::read(&path).unwrap(), contents);
        assert_eq!(
            filetime::FileTime::from_last_modification_time(&fs::metadata(&path).unwrap()),
            old_mtime
        );
    }
}

#[cargo_test]
fn idle_context_is_collected_globally_and_rebuilds_on_demand() {
    let project = donor();
    cargo(&project, "build").run();
    let context = context();
    let registry = shared_root().join("debug/build/registries").join(&context);
    let private = local_private_artifacts(&project.root().join("target")).join(&context);
    assert!(registry.is_dir());
    assert!(private.is_dir());
    tracker()
        .execute("UPDATE contexts SET last_used = 0", [])
        .unwrap();
    collect(&project, true);
    assert!(registry.is_dir());
    assert!(private.is_dir());
    cargo(&project, "gc")
        .cwd(paths::root())
        .with_stderr_contains("[REMOVING] context [..] (unused for at least 1 hour)")
        .run();
    assert!(!registry.exists());
    assert!(
        private.is_dir(),
        "global GC preserves worktree-private state"
    );
    assert_eq!(
        tracker()
            .query_row("SELECT count(*) FROM contexts", [], |row| row
                .get::<_, usize>(0))
            .unwrap(),
        0
    );
    assert!(dependency_paths().is_empty());
    assert!(project.root().join("target/debug/foo").is_file());
    cargo(&project, "build")
        .with_stderr_contains("[COMPILING] gc-dependency v1.0.0")
        .run();
    assert!(registry.is_dir());
    assert!(private.is_dir());
    collect(&project, false);
    assert!(registry.is_dir());
}

#[cargo_test]
fn removed_worktrees_retire_legacy_state_without_touching_external_targets() {
    let project = donor();
    cargo(&project, "build").run();
    let retained_dependencies = walkdir::WalkDir::new(shared_root().join("debug/build"))
        .into_iter()
        .map(Result::unwrap)
        .filter(|entry| {
            entry.file_type().is_file()
                && entry
                    .file_name()
                    .to_string_lossy()
                    .starts_with("libgc_dependency-")
                && entry
                    .path()
                    .extension()
                    .is_some_and(|extension| extension == "rlib")
        })
        .map(|entry| entry.into_path())
        .collect::<Vec<_>>();
    assert!(!retained_dependencies.is_empty());
    let worktree = add_worktree(&project, "removed.worktree-δ");
    let external_target = paths::root().join("external-target");
    cargo(&project, "build")
        .cwd(&worktree)
        .env("CARGO_TARGET_DIR", &external_target)
        .run();
    let namespace = legacy_private_state(&external_target);
    let private = private_artifacts(&namespace);
    let incremental = shared_root().join("debug/incremental").join(&namespace);
    assert!(private.is_dir());
    assert!(incremental.is_dir());
    assert!(!worktree.join("target").exists());

    remove_worktree(&project, &worktree);
    cargo(&project, "gc --dry-run")
        .cwd(paths::root())
        .with_stderr_contains(
            "Would remove legacy workspace [..] (private state now lives in target)",
        )
        .run();
    assert!(private.is_dir(), "dry run preserves artifacts");
    assert!(!shared_root().join(".ohm-gc-v1/candidates.json").exists());
    cargo(&project, "gc")
        .cwd(paths::root())
        .env_remove("CARGO_BUILD_BUILD_DIR")
        .run();
    assert!(!private.exists());
    assert!(!incremental.exists());
    assert!(external_target.join("debug/foo").is_file());
    for dependency in retained_dependencies {
        assert!(
            dependency.is_file(),
            "live dependency {}",
            dependency.display()
        );
    }
    cargo(&project, "run -v")
        .with_stderr_does_not_contain("[COMPILING] [..]")
        .with_stdout_data("hello\n")
        .run();
}

#[cargo_test]
fn removing_a_worktree_removes_its_private_state_without_gc() {
    let project = donor();
    let worktree = add_worktree(&project, "local-only");
    cargo(&project, "build").cwd(&worktree).run();
    let private = local_private_artifacts(&worktree.join("target"));
    assert!(worktree.join("target/debug/incremental").is_dir());
    let registries = shared_root().join("debug/build/registries");
    assert!(registries.is_dir());
    remove_worktree(&project, &worktree);
    assert!(!private.exists());
    assert!(!shared_root().join("debug/build/workspaces").exists());
    assert!(!shared_root().join(".ohm-gc-v1/workspaces").exists());
    collect(&project, false);
    assert!(registries.is_dir());
}

#[cargo_test]
fn legacy_private_state_is_disposable_even_for_live_or_moved_worktrees() {
    let project = donor();
    let moved = add_worktree(&project, "before-move");
    let missing = add_worktree(&project, "registered-missing");
    let mut legacy = Vec::new();
    for worktree in [&moved, &missing] {
        cargo(&project, "build").cwd(worktree).run();
        legacy.push(legacy_private_state(&worktree.join("target")));
    }
    let destination = paths::root().join("after-move");
    let unavailable = paths::root().join("temporarily-unavailable");
    project
        .process("git")
        .args(&["worktree", "move"])
        .arg(&moved)
        .arg(&destination)
        .run();
    fs::rename(&missing, &unavailable).unwrap();

    collect(&project, false);
    for namespace in legacy {
        assert!(!private_artifacts(&namespace).exists());
    }
    for worktree in [destination, unavailable] {
        assert!(local_private_artifacts(&worktree.join("target")).is_dir());
        assert!(worktree.join("target/debug/foo").is_file());
    }
}

#[cargo_test]
fn busy_consumers_and_profiles_postpone_retirement() {
    let project = donor();
    let worktree = add_worktree(&project, "busy");
    cargo(&project, "build").cwd(&worktree).run();
    let private = private_artifacts(&legacy_private_state(&worktree.join("target")));
    remove_worktree(&project, &worktree);

    for path in [".ohm-gc-v1/consumers.lock", "debug/.cargo-build-lock"] {
        let lock = fs::File::open(shared_root().join(path)).unwrap();
        lock.lock_shared().unwrap();
        collect(&project, false);
        assert!(private.is_dir(), "collection must skip a held {path}");
        drop(lock);
    }
    collect(&project, false);
    assert!(!private.exists());
}

#[cargo_test]
fn builds_leave_retired_state_until_explicit_gc() {
    let project = donor();
    cargo(&project, "build").run();
    let worktree = add_worktree(&project, "retired");
    cargo(&project, "build").cwd(&worktree).run();
    let private = private_artifacts(&legacy_private_state(&worktree.join("target")));
    let payload = private.join("large-fixture");
    fs::create_dir(&payload).unwrap();
    for index in 0..300 {
        fs::write(payload.join(index.to_string()), b"fixture").unwrap();
    }
    remove_worktree(&project, &worktree);

    // Exercise packaged defaults when the selected compiler supports them; this
    // suite also runs with stock stable Rust, which rejects Ohm's compiler flags.
    let command = if crate::build_dir::selected_compiler_supports_ohm_defaults() {
        "-Zohm-defaults=yes build"
    } else {
        "build"
    };
    cargo(&project, command).run();
    assert!(private.is_dir());
    let registry = paths::home().join(".cargo/.ohm-build-roots-v1");
    assert!(
        fs::read_dir(&registry).unwrap().all(|entry| {
            entry
                .unwrap()
                .path()
                .extension()
                .is_some_and(|extension| extension == "json")
        }),
        "builds only register roots, without scheduling markers or locks"
    );

    // An explicit invocation drains more than one deletion chunk.
    collect(&project, false);
    assert!(!private.exists());
    let trash = shared_root().join("debug/.ohm-gc-trash-v1");
    if trash.exists() {
        assert!(fs::read_dir(trash).unwrap().all(|entry| {
            !entry
                .unwrap()
                .file_name()
                .to_string_lossy()
                .starts_with("entry-")
        }));
    }
}

#[cargo_test(
    nightly,
    reason = "worktree seeding requires checksum freshness and cwd remapping"
)]
fn seed_only_recipients_keep_all_private_state_in_their_target() {
    let project = donor();
    cargo(&project, "-Zohm-worktree-seeds=yes build").run();
    let worktree = paths::root().join("seed-only");
    let output = cargo(&project, "-Zohm-defaults=yes worktree add")
        .arg(&worktree)
        .run();
    let private = worktree.join("target/debug/build/workspaces");
    let stderr = std::str::from_utf8(&output.stderr).unwrap();
    if stderr.contains("Seeded ") {
        assert!(local_private_artifacts(&worktree.join("target")).is_dir());
    } else {
        assert!(
            stderr.contains("no compatible build snapshot seeded"),
            "{stderr}"
        );
        assert!(
            fs::read_dir(&private)
                .map(|mut entries| entries.next().is_none())
                .unwrap_or(true)
        );
    }
    assert!(!worktree.join("target/debug/foo").exists());
    assert!(!shared_root().join(".ohm-gc-v1/workspaces").exists());
    remove_worktree(&project, &worktree);
    assert!(
        !private.exists(),
        "removing a worktree also removes its unbuilt seed"
    );
    collect(&project, false);
}

/// Keeps the process group owned until all test children have released their lease.
struct RunningCargo(Child);

impl Drop for RunningCargo {
    fn drop(&mut self) {
        // SAFETY: The child starts a new process group and has not been reaped.
        unsafe { libc::kill(-(self.0.id() as i32), libc::SIGKILL) };
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn accept_child(listener: &TcpListener) -> TcpStream {
    listener.set_nonblocking(true).unwrap();
    let deadline = Instant::now() + slow_cpu_multiplier(60);
    loop {
        match listener.accept() {
            Ok((stream, _)) => return stream,
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                assert!(
                    Instant::now() < deadline,
                    "test child did not reach its barrier"
                );
                std::thread::sleep(Duration::from_millis(10));
            }
            Err(error) => panic!("accepting test child: {error}"),
        }
    }
}

#[cargo_test]
fn running_test_retains_lease_after_its_cargo_parent_exits() {
    let project = donor();
    project.change_file(
        "tests/lease.rs",
        r#"
        #[test]
        fn retained_artifacts() {
            use std::io::{Read, Write};
            let mut stream = std::net::TcpStream::connect(
                std::env::var("OHM_GC_TEST_LISTENER").unwrap()
            ).unwrap();
            stream.write_all(b"ready").unwrap();
            stream.read_exact(&mut [0]).unwrap();
        }
        "#,
    );
    let repo = git2::Repository::open(project.root()).unwrap();
    git::add(&repo);
    git::commit(&repo);
    let worktree = add_worktree(&project, "running-test");
    cargo(&project, "test --test lease --no-run")
        .cwd(&worktree)
        .run();
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let mut command = cargo(&project, "test --test lease");
    let mut process = command
        .cwd(&worktree)
        .env(
            "OHM_GC_TEST_LISTENER",
            listener.local_addr().unwrap().to_string(),
        )
        .build_command();
    let mut running = RunningCargo(
        process
            .process_group(0)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap(),
    );
    let mut stream = accept_child(&listener);
    stream
        .set_read_timeout(Some(slow_cpu_multiplier(30)))
        .unwrap();
    stream.read_exact(&mut [0; 5]).unwrap();
    let private = local_private_artifacts(&worktree.join("target"));
    let registry = shared_root().join("debug/build/registries").join(context());
    tracker()
        .execute("UPDATE contexts SET last_used = 0", [])
        .unwrap();

    // Kill Cargo alone: its test retains both the global and the private lease.
    running.0.kill().unwrap();
    let local_lock = fs::File::open(worktree.join("target/.ohm-build-lock")).unwrap();
    assert!(matches!(
        local_lock.try_lock(),
        Err(fs::TryLockError::WouldBlock)
    ));
    remove_worktree(&project, &worktree);
    assert!(!private.exists());
    collect(&project, false);
    assert!(registry.is_dir());
    stream.write_all(&[1]).unwrap();
    drop(stream);

    let lock = fs::File::open(shared_root().join(".ohm-gc-v1/consumers.lock")).unwrap();
    let deadline = Instant::now() + slow_cpu_multiplier(30);
    loop {
        match lock.try_lock() {
            Ok(()) => break,
            Err(fs::TryLockError::WouldBlock) => {
                assert!(
                    Instant::now() < deadline,
                    "test child retained its lease after exit"
                );
                std::thread::sleep(Duration::from_millis(10));
            }
            Err(error) => panic!("checking test child lease: {error}"),
        }
    }
    drop(lock);
    collect(&project, false);
    assert!(!registry.exists());
}
