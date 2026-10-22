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
use cargo_test_support::{
    Execs, Project, basic_manifest, git, paths, project, slow_cpu_multiplier, str,
};

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

fn add_ohm_worktree(project: &Project, name: &str) -> PathBuf {
    let path = paths::root().join(name);
    cargo(
        project,
        "-Zohm-defaults=yes -Zohm-worktree-seeds=no worktree add --detach",
    )
    .arg(&path)
    .run();
    path
}

fn marked_private_context(worktree: &Path, id: u64, release: &str) -> PathBuf {
    marked_private_context_at(worktree, &worktree.join("target"), id, release)
}

fn marked_private_context_at(worktree: &Path, target: &Path, id: u64, release: &str) -> PathBuf {
    fs::create_dir_all(target).unwrap();
    let namespace = cargo::util::short_hash(&(
        "ohm-shared-workspace-v3",
        worktree.canonicalize().unwrap(),
        target.canonicalize().unwrap(),
    ));
    let context = format!("v2-{id:016x}");
    let path = target
        .join("debug/build/workspaces")
        .join(namespace)
        .join(&context);
    fs::create_dir_all(&path).unwrap();
    fs::File::options()
        .write(true)
        .create(true)
        .truncate(false)
        .open(target.join("debug/.cargo-build-lock"))
        .unwrap();
    let mut proof = format!("{context}\n{release}\n").into_bytes();
    let toolchains = moving_ohm("ohm-1.98.1-2")
        .join("toolchains")
        .canonicalize()
        .unwrap();
    proof.extend_from_slice(cargo_util::paths::path2bytes(&toolchains).unwrap());
    fs::write(path.join(".ohm-private-context-v1"), proof).unwrap();
    path
}

fn current_ohm_rustc() -> PathBuf {
    use std::os::unix::fs::PermissionsExt as _;

    let compiler = paths::root().join("current-ohm-rustc");
    fs::write(
        &compiler,
        format!(
            "#!/bin/sh\ncat <<'VERSION'\nrustc 1.98.1-dev (ohm-1.98.1-2)\nbinary: rustc\ncommit-hash: unknown\nhost: {}\nrelease: 1.98.1-dev\nLLVM version: 22.1.8\nVERSION\n",
            cargo_test_support::rustc_host()
        ),
    )
    .unwrap();
    fs::set_permissions(&compiler, fs::Permissions::from_mode(0o755)).unwrap();
    compiler
}

fn private_gc(command: &str, compiler: &Path) -> Execs {
    let mut command = gc_outside_workspace(command);
    command
        .env("RUSTC", compiler)
        .env("RUSTUP_HOME", moving_ohm("ohm-1.98.1-2"));
    command
}

fn gc_outside_workspace(command: &str) -> Execs {
    let mut command = cargo_process(command);
    command
        .cwd(paths::root())
        .env_remove("CARGO_BUILD_BUILD_DIR");
    command
}

fn age_target(target: &Path) {
    fs::File::open(target.join(".ohm-target-last-use-v1"))
        .unwrap()
        .set_modified(SystemTime::now() - Duration::from_secs(3601))
        .unwrap();
}

fn moving_ohm(release: &str) -> PathBuf {
    let rustup = paths::root().join(format!("rustup-{release}"));
    if !rustup.exists() {
        let sysroot = rustup.join("installation");
        fs::create_dir_all(sysroot.join("bin")).unwrap();
        fs::write(sysroot.join("bin/rustc"), b"installed compiler").unwrap();
        fs::write(sysroot.join(".ohm-version"), format!("{release}\n")).unwrap();
        fs::create_dir(rustup.join("toolchains")).unwrap();
        std::os::unix::fs::symlink(sysroot, rustup.join("toolchains/ohm")).unwrap();
    }
    rustup
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
fn gc_finishes_healthy_roots_before_reporting_errors() {
    let cache = paths::home().join(".cache");
    let stale = cache.join("a-reused");
    let newer = cache.join("b-newer");
    let healthy = cache.join("c-healthy");
    for root in [&stale, &newer, &healthy] {
        fs::create_dir_all(root).unwrap();
        fs::write(root.join(".ohm-shared-registry-cache-v1"), b"").unwrap();
    }
    cargo_process("gc --build-dir").arg(&stale).run();
    fs::remove_file(stale.join(".ohm-shared-registry-cache-v1")).unwrap();
    fs::write(stale.join("unrelated"), b"keep").unwrap();
    fs::create_dir(newer.join(".ohm-gc-v1")).unwrap();
    rusqlite::Connection::open(newer.join(".ohm-gc-v1/cache.sqlite"))
        .unwrap()
        .execute_batch("PRAGMA user_version = 999")
        .unwrap();
    let context = healthy.join("debug/build/registries/0123456789abcdef");
    fs::create_dir_all(&context).unwrap();
    fs::write(healthy.join("debug/.cargo-build-lock"), b"").unwrap();
    fs::write(context.join("artifact"), b"cached").unwrap();

    for (command, summary) in [("gc --dry-run", "[SUMMARY]"), ("gc", "[REMOVED]")] {
        cargo_process(command)
            .with_status(101)
            .with_stderr_contains("[SKIPPING] [..]/a-reused (shared cache marker is missing)")
            .with_stderr_contains(format!("{summary} 1 file, [FILE_SIZE]B total"))
            .with_stderr_contains("  [..]/b-newer (unsupported build-cache database version 999)")
            .run();
        assert_eq!(context.exists(), command == "gc --dry-run");
        assert_eq!(fs::read(stale.join("unrelated")).unwrap(), b"keep");
    }
    cargo_process("gc --quiet --build-dir")
        .arg(stale)
        .with_status(101)
        .with_stderr_contains("  [..]/a-reused (not an owned shared registry cache)")
        .run();
}

#[cargo_test]
fn gc_discovers_roots_when_the_root_registry_is_invalid() {
    let registry = paths::cargo_home().join(".ohm-build-roots-v1");
    fs::create_dir_all(paths::cargo_home()).unwrap();
    fs::write(&registry, b"unrelated").unwrap();
    let root = paths::home().join(".cache/ohm-build");
    let context = root.join(".ohm-thinlto-cache").join("a".repeat(32));
    fs::create_dir_all(&context).unwrap();
    fs::write(root.join(".ohm-shared-registry-cache-v1"), b"").unwrap();
    fs::write(context.join("artifact"), b"cached").unwrap();

    cargo_process("gc --dry-run --build-dir")
        .arg(&root)
        .with_stderr_contains("[SUMMARY] 1 file, [FILE_SIZE]B total")
        .run();
    cargo_process("gc")
        .with_status(101)
        .with_stderr_contains("[REMOVED] 1 file, [FILE_SIZE]B total")
        .with_stderr_contains(
            "  failed to read [..]/.ohm-build-roots-v1 (invalid build-root registry)",
        )
        .run();
    assert!(!context.exists());
    assert_eq!(fs::read(registry).unwrap(), b"unrelated");
}

/// Restore the same inode on failure, even if GC has moved it into its trash.
fn restrict_permissions(path: &Path, mode: u32) -> impl Drop {
    use std::os::unix::fs::PermissionsExt as _;

    struct Restore(fs::File, fs::Permissions);
    impl Drop for Restore {
        fn drop(&mut self) {
            self.0.set_permissions(self.1.clone()).unwrap();
        }
    }

    let file = fs::File::open(path).unwrap();
    let previous = file.metadata().unwrap().permissions();
    file.set_permissions(fs::Permissions::from_mode(mode))
        .unwrap();
    Restore(file, previous)
}

#[cargo_test]
fn gc_reports_inaccessible_paths_and_cleans_their_siblings() {
    let root = shared_root();
    let registry = root.join("debug/build/registries/0123456789abcdef");
    let workspace = root.join("debug/build/workspaces/0123456789abcdef");
    let blocked = workspace.join("unreadable");
    fs::create_dir_all(&registry).unwrap();
    fs::create_dir_all(&blocked).unwrap();
    fs::write(root.join(".ohm-shared-registry-cache-v1"), b"").unwrap();
    fs::write(root.join("debug/.cargo-build-lock"), b"").unwrap();
    fs::write(registry.join("blocked-rename"), b"a").unwrap();
    fs::write(blocked.join("blocked-read"), b"b").unwrap();
    fs::write(workspace.join("writable"), b"c").unwrap();
    let registries = registry.parent().unwrap();
    let blocked_mode = restrict_permissions(&blocked, 0o000);
    if fs::read_dir(&blocked).is_ok() {
        // Privileged test runners can bypass the permissions this test exercises.
        return;
    }
    let registries_mode = restrict_permissions(registries, 0o555);

    let preview = cargo_process("gc --color never --dry-run --build-dir")
        .arg(&root)
        .with_status(101)
        .with_stderr_contains("[ERROR] could not clean the following paths:")
        .run();
    let stderr = String::from_utf8(preview.stderr).unwrap();
    assert!(stderr.contains("Summary 2 files, 2B total"), "{stderr}");
    assert!(
        stderr.contains(&format!("{} (Permission denied", blocked.display())),
        "{stderr}"
    );
    let result = cargo_process("gc --color never --build-dir")
        .arg(&root)
        .with_status(101)
        .with_stderr_contains("[ERROR] could not clean the following paths:")
        .run();
    let stderr = String::from_utf8(result.stderr).unwrap();
    assert!(stderr.contains("Removed 1 file, 1B total"), "{stderr}");
    assert!(
        stderr.contains(&format!("{} (Permission denied", registry.display())),
        "{stderr}"
    );
    assert!(
        stderr.contains("/payload/unreadable (Permission denied"),
        "{stderr}"
    );
    assert!(registry.join("blocked-rename").is_file());
    let trash = root.join("debug/.ohm-gc-trash-v1");
    let payload = fs::read_dir(trash)
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path()
        .join("payload");
    assert!(!payload.join("writable").exists());
    drop((registries_mode, blocked_mode));
    let retry = cargo_process("gc --color never --build-dir")
        .arg(root)
        .run();
    let stderr = String::from_utf8(retry.stderr).unwrap();
    assert!(stderr.contains("Removed 2 files, 2B total"), "{stderr}");
    assert!(!payload.exists());
    assert!(!registry.exists());
}

#[cargo_test]
fn inaccessible_context_lock_preserves_only_its_context() {
    let root = shared_root();
    let registries = root.join("debug/build/registries");
    let blocked = "v2-0000000000000001";
    let peer = "v2-0000000000000002";
    for context in [blocked, peer] {
        fs::create_dir_all(registries.join(context)).unwrap();
        fs::write(registries.join(context).join("artifact"), b"x").unwrap();
    }
    fs::write(root.join(".ohm-shared-registry-cache-v1"), b"").unwrap();
    fs::write(root.join("debug/.cargo-build-lock"), b"").unwrap();
    let metadata = root.join(".ohm-gc-v1");
    fs::create_dir(&metadata).unwrap();
    let lock = metadata.join(format!("context-{blocked}.lock"));
    fs::write(&lock, b"").unwrap();
    let _mode = restrict_permissions(&lock, 0o000);
    if fs::File::open(&lock).is_ok() {
        return;
    }
    for (command, summary) in [("gc --dry-run", "Summary"), ("gc", "Removed")] {
        let result = cargo_process(command)
            .args(&["--color", "never"])
            .arg("--build-dir")
            .arg(&root)
            .with_status(101)
            .with_stderr_contains("[ERROR] could not clean the following paths:")
            .run();
        let stderr = String::from_utf8(result.stderr).unwrap();
        assert!(
            stderr.contains(&format!("{summary} 1 file, 1B total")),
            "{stderr}"
        );
        assert!(
            stderr.contains(&format!("{} (Permission denied", lock.display())),
            "{stderr}"
        );
        assert!(!stderr.contains("(in use)"), "{stderr}");
        assert!(registries.join(blocked).join("artifact").is_file());
        assert_eq!(registries.join(peer).exists(), command == "gc --dry-run");
    }
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
fn gc_explains_skipped_paths_and_cleans_unrelated_artifacts() {
    let project = donor();
    cargo(&project, "build").run();
    let registry = shared_root().join("debug/build/registries").join(context());
    let outside = paths::root().join("outside-cache");
    fs::rename(&registry, &outside).unwrap();
    fs::write(outside.join("preserved"), b"untouched").unwrap();
    std::os::unix::fs::symlink(&outside, &registry).unwrap();
    tracker()
        .execute("UPDATE contexts SET last_used = 0", [])
        .unwrap();

    // More blocked contexts than fit in one batch must not starve later work.
    let mut record = context_record();
    let mut skipped = vec![registry.clone()];
    for index in 0..9 {
        let name = format!("v2-{index:016x}");
        record["context"] = name.clone().into();
        tracker()
            .execute(
                "INSERT INTO contexts (context, record, last_used) VALUES (?1, ?2, 0)",
                rusqlite::params![name, serde_json::to_vec(&record).unwrap()],
            )
            .unwrap();
        let path = registry.parent().unwrap().join(name);
        std::os::unix::fs::symlink(&outside, &path).unwrap();
        skipped.push(path);
    }
    let unused = registry.parent().unwrap().join("v2-ffffffffffffffff");
    fs::create_dir(&unused).unwrap();
    fs::write(unused.join("artifact"), b"unused").unwrap();
    for dry_run in [true, false] {
        let command = if dry_run {
            "gc --dry-run --color never --build-dir"
        } else {
            "gc --color never --build-dir"
        };
        let output = cargo(&project, command).arg(shared_root()).run();
        let stderr = String::from_utf8(output.stderr).unwrap();
        for path in &skipped {
            assert!(
                stderr.contains(&format!(
                    "Skipping {} (not a regular file or directory)",
                    path.display()
                )),
                "{stderr}"
            );
            assert!(path.is_symlink());
        }
        assert!(!stderr.contains("is incomplete"), "{stderr}");
        assert!(!stderr.contains("again to continue"), "{stderr}");
        assert_eq!(unused.exists(), dry_run);
        assert_eq!(fs::read(outside.join("preserved")).unwrap(), b"untouched");
    }
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
    let compiler = current_ohm_rustc();
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
fn gc_discovers_private_contexts_outside_worktrees_and_respects_explicit_roots() {
    let project = donor();
    let worktree = add_ohm_worktree(&project, "managed");
    let obsolete = marked_private_context(&worktree, 1, "ohm-1.98.1-1");
    fs::write(obsolete.join("artifact"), [0; 1024]).unwrap();
    let kept = marked_private_context(&worktree, 2, "ohm-1.98.1-1");
    fs::write(kept.join(".ohm-private-context-keep-v1"), b"").unwrap();
    let current = marked_private_context(&worktree, 3, "ohm-1.98.1-2");
    let newer = marked_private_context(&worktree, 4, "ohm-1.98.1-3");
    let unknown = marked_private_context(&worktree, 5, "unrecognized compiler");
    let unmarked = marked_private_context(&worktree, 6, "ohm-1.98.1-1");
    fs::remove_file(unmarked.join(".ohm-private-context-v1")).unwrap();

    let symbols = marked_private_context(&worktree, 7, "ohm-1.98.1-1");
    let symbol_payload = symbols.join("tool.dSYM");
    fs::create_dir(&symbol_payload).unwrap();
    fs::write(symbol_payload.join("symbols"), b"keep symbols").unwrap();
    let examples = worktree.join("target/debug/examples");
    fs::create_dir_all(&examples).unwrap();
    std::os::unix::fs::symlink(&symbol_payload, examples.join("tool.dSYM")).unwrap();

    let manual = add_worktree(&project, "manual");
    let unmanaged = marked_private_context(&manual, 8, "ohm-1.98.1-1");
    let retained = [
        &kept, &current, &newer, &unknown, &unmarked, &symbols, &unmanaged,
    ];
    for path in retained {
        fs::write(path.join("preserved"), b"keep").unwrap();
    }
    let final_output = worktree.join("target/debug/foo");
    let incremental = worktree.join("target/debug/incremental/session/state");
    fs::write(&final_output, b"keep executable").unwrap();
    fs::create_dir_all(incremental.parent().unwrap()).unwrap();
    fs::write(&incremental, b"keep incremental").unwrap();

    // Resolving the current compiler must also work with no registered shared roots.
    assert!(!shared_root().exists());
    let compiler = current_ohm_rustc();
    let alias_version = moving_ohm("ohm-1.98.1-2").join("installation/.ohm-version");
    fs::write(&alias_version, b"ohm-1.98.1-1\n").unwrap();
    private_gc("gc --dry-run", &compiler)
        .with_stderr_contains("[SUMMARY] 0 files")
        .run();
    fs::write(&alias_version, b"ohm-1.98.1-2\n").unwrap();
    private_gc("gc --dry-run", &compiler)
        .env("RUSTUP_HOME", moving_ohm("ohm-1.98.1-3"))
        .with_stderr_contains("[SUMMARY] 0 files")
        .run();
    let preview = private_gc("gc --dry-run --color never", &compiler).run();
    let stderr = String::from_utf8(preview.stderr).unwrap();
    assert!(
        stderr.contains("Would remove private context v2-0000000000000001"),
        "{stderr}"
    );
    assert!(stderr.contains(&worktree.display().to_string()), "{stderr}");
    assert!(stderr.contains("Summary 1 file, 1.0KiB total"), "{stderr}");
    assert!(obsolete.join("artifact").is_file());

    fs::create_dir_all(shared_root()).unwrap();
    fs::write(shared_root().join(".ohm-shared-registry-cache-v1"), b"").unwrap();
    private_gc("gc --build-dir", &compiler)
        .arg(shared_root())
        .with_stderr_contains("[REMOVED] 0 files")
        .run();
    assert!(
        obsolete.exists(),
        "--build-dir only cleans the selected shared root"
    );

    let result = private_gc("gc --color never", &compiler).run();
    let stderr = String::from_utf8(result.stderr).unwrap();
    assert!(stderr.contains("Removed 1 file, 1.0KiB total"), "{stderr}");
    assert!(!obsolete.exists());
    for path in retained {
        assert_eq!(fs::read(path.join("preserved")).unwrap(), b"keep");
    }
    assert_eq!(fs::read(&final_output).unwrap(), b"keep executable");
    assert_eq!(fs::read(&incremental).unwrap(), b"keep incremental");
    assert_eq!(
        fs::read(examples.join("tool.dSYM/symbols")).unwrap(),
        b"keep symbols"
    );
}

#[cargo_test]
fn gc_skips_busy_private_targets_and_cleans_other_worktrees() {
    let project = donor();
    let busy = add_ohm_worktree(&project, "busy-private");
    let free = add_ohm_worktree(&project, "free-private");
    let busy_context = marked_private_context(&busy, 1, "ohm-1.98.1-1");
    let free_context = marked_private_context(&free, 2, "ohm-1.98.1-1");
    fs::write(busy_context.join("artifact"), b"busy").unwrap();
    fs::write(free_context.join("artifact"), b"free").unwrap();
    let lock_path = busy.join("target/.ohm-build-lock");
    let lock = fs::File::open(&lock_path).unwrap();
    lock.lock_shared().unwrap();
    let compiler = current_ohm_rustc();
    for dry_run in [true, false] {
        let command = if dry_run {
            "gc -v --dry-run --color never"
        } else {
            "gc -v --color never"
        };
        let result = private_gc(command, &compiler).run();
        let stderr = String::from_utf8(result.stderr).unwrap();
        assert!(stderr.contains("target directory is in use"), "{stderr}");
        assert!(
            stderr.contains(&format!("Busy lock {}", lock_path.display())),
            "{stderr}"
        );
        assert!(stderr.contains("1 file, 4B total"), "{stderr}");
        assert!(busy_context.exists());
        assert_eq!(free_context.exists(), dry_run);
    }
    drop(lock);
    private_gc("gc", &compiler)
        .with_stderr_contains("[REMOVED] 1 file, [FILE_SIZE]B total")
        .run();
    assert!(!busy_context.exists());
}

#[cargo_test]
fn build_and_check_enroll_primary_and_existing_worktrees_for_gc() {
    let project = donor();
    let existing = add_worktree(&project, "existing");
    cargo(&project, "build").run();
    cargo(&project, "check").cwd(&existing).run();
    let primary_context = marked_private_context(&project.root(), 1, "ohm-1.98.1-1");
    let linked_context = marked_private_context(&existing, 2, "ohm-1.98.1-1");
    for path in [&primary_context, &linked_context] {
        fs::write(path.join("artifact"), b"old private state").unwrap();
    }
    private_gc("gc", &current_ohm_rustc()).run();
    assert!(!primary_context.exists());
    assert!(!linked_context.exists());
    assert!(project.root().join("target/debug/foo").is_file());
}

#[cargo_test]
fn gc_resumes_private_cleanup_in_a_target_selected_by_two_non_git_projects() {
    let target = paths::root().join("external-target");
    let mut contexts = Vec::new();
    for (index, name) in ["first", "second"].into_iter().enumerate() {
        let project = project()
            .at(name)
            .file("Cargo.toml", &basic_manifest(name, "0.1.0"))
            .file("src/lib.rs", "")
            .build();
        assert!(!project.root().join(".git").exists());
        cargo(&project, "check --target-dir").arg(&target).run();
        let path =
            marked_private_context_at(&project.root(), &target, index as u64, "ohm-1.98.1-1");
        fs::write(path.join("artifact"), b"data").unwrap();
        contexts.push(path);
    }
    // A previous GC detached the first directory and was interrupted before unlinking it.
    let namespace = contexts[0]
        .parent()
        .unwrap()
        .file_name()
        .unwrap()
        .to_str()
        .unwrap();
    let stage = target.join(format!(".ohm-worktree-gc-trash-v1-{namespace}/entry-first"));
    fs::create_dir_all(&stage).unwrap();
    fs::write(stage.join("owner"), b"ohm-build-gc-v1\n").unwrap();
    fs::rename(&contexts[0], stage.join("payload")).unwrap();
    let compiler = current_ohm_rustc();
    for dry_run in [true, false] {
        let result = private_gc(if dry_run { "gc --dry-run" } else { "gc" }, &compiler).run();
        let stderr = String::from_utf8(result.stderr).unwrap();
        assert!(stderr.contains("2 files, 8B total"), "{stderr}");
        assert_eq!(stage.exists(), dry_run);
        assert_eq!(contexts[1].exists(), dry_run);
    }
}

#[cargo_test]
fn gc_cleans_idle_targets_on_the_current_release_and_rebuilds_on_demand() {
    use std::os::unix::fs::MetadataExt as _;

    let project = donor();
    let warm = add_worktree(&project, "warm-target");
    let busy = add_worktree(&project, "busy-target");
    cargo(&project, "build").run();
    cargo(&project, "doc --no-deps").run();
    for worktree in [&warm, &busy] {
        cargo(&project, "build").cwd(worktree).run();
    }
    let target = project.root().join("target");
    let binary = target.join("debug/foo");
    let docs = target.join("doc/foo/index.html");
    let incremental = target.join("debug/incremental/unused-session/state");
    let unmarked = target.join("debug/build/unmarked/artifact");
    for path in [&incremental, &unmarked] {
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, [0; 1024]).unwrap();
    }
    assert!(binary.is_file());
    assert!(docs.is_file());
    let kept = [
        target.clone(),
        target.join("CACHEDIR.TAG"),
        target.join(".ohm-build-lock"),
        target.join(".ohm-target-last-use-v1"),
    ]
    .map(|path| {
        let inode = fs::symlink_metadata(&path).unwrap().ino();
        (path, inode)
    });
    age_target(&target);
    age_target(&busy.join("target"));
    let busy_lock = fs::File::open(busy.join("target/.ohm-build-lock")).unwrap();
    busy_lock.lock_shared().unwrap();

    gc_outside_workspace("gc --build-dir")
        .arg(shared_root())
        .run();
    assert!(
        binary.is_file(),
        "an explicit shared root excludes private targets"
    );

    let preview = gc_outside_workspace("gc --dry-run --color never").run();
    let preview = String::from_utf8(preview.stderr).unwrap();
    assert!(
        preview.contains(&format!(
            "Would remove workspace target {} (unused for at least 1 hour)",
            target.display()
        )),
        "{preview}"
    );
    assert!(preview.contains("target directory is in use"), "{preview}");
    let expected_counts = preview
        .lines()
        .find_map(|line| line.trim_start().strip_prefix("Summary "))
        .unwrap();
    assert!(expected_counts.contains("files,"), "{preview}");
    for path in [&binary, &docs, &incremental, &unmarked] {
        assert!(path.exists(), "dry run changed {}", path.display());
    }

    let collected = gc_outside_workspace("gc --color never").run();
    let collected = String::from_utf8(collected.stderr).unwrap();
    assert!(
        collected.contains(&format!("Removed {expected_counts}")),
        "{collected}"
    );
    for path in [&binary, &docs, &incremental, &unmarked] {
        assert!(!path.exists(), "idle target retained {}", path.display());
    }
    for (path, inode) in kept {
        assert_eq!(fs::symlink_metadata(&path).unwrap().ino(), inode);
    }
    assert!(warm.join("target/debug/foo").is_file());
    assert!(busy.join("target/debug/foo").is_file());
    drop(busy_lock);

    // An enrolled target can also be used by Cargo versions without the Ohm root lease.
    for name in [".cargo-lock", ".cargo-build-lock", ".cargo-artifact-lock"] {
        let path = busy.join("target/debug").join(name);
        let lock = fs::File::options()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(&path)
            .unwrap();
        lock.lock().unwrap();
        let output = gc_outside_workspace("gc -v --color never").run();
        let stderr = String::from_utf8(output.stderr).unwrap();
        assert!(
            stderr.contains(&format!("Busy lock {}", path.display())),
            "{stderr}"
        );
        assert!(busy.join("target/debug/foo").is_file());
    }

    cargo(&project, "run")
        .with_stderr_contains("[COMPILING] foo [..]")
        .with_stdout_data("hello\n")
        .run();
    assert!(binary.is_file());
    assert!(target.join("debug/incremental").is_dir());
    gc_outside_workspace("gc").run();
    assert!(binary.is_file(), "the rebuilt target is warm again");
    assert!(!busy.join("target/debug/foo").exists());
}

#[cargo_test]
fn gc_protects_targets_while_a_build_resolves_its_context() {
    let project = donor();
    cargo(&project, "build").run();
    let wrapper = cargo_test_support::project()
        .at("gc-resolution-wrapper")
        .file(
            "Cargo.toml",
            &basic_manifest("gc-resolution-wrapper", "0.1.0"),
        )
        .file(
            "src/main.rs",
            r#"
                use std::io::{Read, Write};

                fn main() {
                    let mut args = std::env::args_os().skip(1);
                    let rustc = args.next().unwrap();
                    let args: Vec<_> = args.collect();
                    if args.iter().any(|arg| arg == "--print=cfg")
                        && std::fs::File::options().write(true).create_new(true)
                            .open(std::env::var_os("OHM_GC_TEST_BARRIER").unwrap()).is_ok()
                    {
                        let mut stream = std::net::TcpStream::connect(
                            std::env::var("OHM_GC_TEST_LISTENER").unwrap()
                        ).unwrap();
                        stream.write_all(b"ready").unwrap();
                        stream.read_exact(&mut [0]).unwrap();
                    }
                    let status = std::process::Command::new(rustc).args(args).status().unwrap();
                    std::process::exit(status.code().unwrap_or(1));
                }
            "#,
        )
        .build();
    wrapper.cargo("build").run();
    let target = project.root().join("target");
    let binary = target.join("debug/foo");
    age_target(&target);
    let started = SystemTime::now();
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let mut command = cargo(&project, "build");
    let mut process = command
        .env(
            "RUSTC_WORKSPACE_WRAPPER",
            wrapper.bin("gc-resolution-wrapper"),
        )
        .env("CARGO_CACHE_RUSTC_INFO", "0")
        .env(
            "OHM_GC_TEST_BARRIER",
            paths::root().join("resolution-started"),
        )
        .env(
            "OHM_GC_TEST_LISTENER",
            listener.local_addr().unwrap().to_string(),
        )
        .build_command();
    let mut running = RunningCargo(
        process
            .process_group(0)
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap(),
    );
    let mut stream = accept_child(&listener);
    stream
        .set_read_timeout(Some(slow_cpu_multiplier(30)))
        .unwrap();
    stream.read_exact(&mut [0; 5]).unwrap();
    assert!(
        fs::metadata(target.join(".ohm-target-last-use-v1"))
            .unwrap()
            .modified()
            .unwrap()
            >= started
    );

    // Even resolution that lasts over an hour retains the same target lease.
    age_target(&target);
    for command in ["gc --dry-run", "gc"] {
        let output = gc_outside_workspace(command).run();
        let stderr = String::from_utf8(output.stderr).unwrap();
        assert!(stderr.contains("target directory is in use"), "{stderr}");
        assert!(binary.is_file());
    }
    stream.write_all(&[1]).unwrap();
    let status = running.0.wait().unwrap();
    let mut stderr = String::new();
    running
        .0
        .stderr
        .take()
        .unwrap()
        .read_to_string(&mut stderr)
        .unwrap();
    assert!(status.success(), "{stderr}");
    let lock = fs::File::open(target.join(".ohm-build-lock")).unwrap();
    lock.try_lock().unwrap();
}

#[cargo_test]
fn gc_accepts_legacy_default_targets_but_preserves_ambiguous_external_directories() {
    let project = donor();
    cargo(&project, "build").run();
    let target = project.root().join("target");
    let external = paths::root().join("pre-existing-output");
    fs::create_dir(&external).unwrap();
    fs::write(external.join("unrelated"), b"preserve existing data").unwrap();
    cargo(&project, "build --target-dir").arg(&external).run();
    let external_tag = external.join("CACHEDIR.TAG");
    if external_tag.exists() {
        fs::remove_file(external_tag).unwrap();
    }
    age_target(&target);
    age_target(&external);

    // A malformed tag is not equivalent to an older conventional target with no tag.
    fs::write(target.join("CACHEDIR.TAG"), b"not a cache tag").unwrap();
    gc_outside_workspace("gc")
        .with_stderr_contains("[SKIPPING] [..] (could not verify a dedicated Cargo target)")
        .with_stderr_contains("[REMOVED] 0 files")
        .run();
    assert!(target.join("debug/foo").is_file());
    fs::remove_file(target.join("CACHEDIR.TAG")).unwrap();

    let outside = paths::root().join("outside-artifact");
    fs::write(&outside, b"preserve symlink target").unwrap();
    let linked = target.join("linked-artifact");
    let dangling = target.join("dangling-artifact");
    std::os::unix::fs::symlink(&outside, &linked).unwrap();
    std::os::unix::fs::symlink(paths::root().join("missing-artifact"), &dangling).unwrap();
    for dry_run in [true, false] {
        let command = if dry_run {
            "gc --dry-run --color never"
        } else {
            "gc --color never"
        };
        let output = gc_outside_workspace(command).run();
        let stderr = String::from_utf8(output.stderr).unwrap();
        assert!(
            stderr.contains(&format!(
                "workspace target {} (unused for at least 1 hour)",
                target.display()
            )),
            "{stderr}"
        );
        assert!(
            stderr.contains(&format!(
                "Skipping {} (could not verify a dedicated Cargo target)",
                external.display()
            )),
            "{stderr}"
        );
        assert_eq!(target.join("debug/foo").exists(), dry_run);
        assert_eq!(linked.is_symlink(), dry_run);
        assert_eq!(dangling.is_symlink(), dry_run);
        assert_eq!(fs::read(&outside).unwrap(), b"preserve symlink target");
        assert_eq!(
            fs::read(external.join("unrelated")).unwrap(),
            b"preserve existing data"
        );
        assert!(external.join("debug/foo").is_file());
    }
}

#[cargo_test]
fn gc_uses_shared_target_activity_and_preserves_colocated_shared_caches() {
    let target = paths::root().join("shared-target");
    let projects = ["first", "second"].map(|name| {
        let project = project()
            .at(name)
            .file("Cargo.toml", &basic_manifest(name, "0.1.0"))
            .file("src/lib.rs", "pub fn value() -> u8 { 1 }")
            .build();
        cargo(&project, "check --target-dir").arg(&target).run();
        project
    });
    for project in &projects {
        age_target(&target);
        let started = SystemTime::now();
        cargo(project, "check --target-dir")
            .arg(&target)
            .with_stderr_does_not_contain("[CHECKING] [..]")
            .run();
        let used = fs::metadata(target.join(".ohm-target-last-use-v1"))
            .unwrap()
            .modified()
            .unwrap();
        assert!(used >= started, "a warm check refreshes the shared target");
        gc_outside_workspace("gc --dry-run")
            .with_stderr_does_not_contain("Would remove workspace target [..]")
            .run();
    }

    let registry = target.join("debug/build/registries/v2-0000000000000001/artifact");
    let thinlto = target.join(".ohm-thinlto-cache/v2-0000000000000001/backend.cache");
    fs::write(target.join(".ohm-shared-registry-cache-v1"), b"").unwrap();
    for path in [&registry, &thinlto] {
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, b"shared cache").unwrap();
    }
    let private = target.join("debug/build/workspaces");
    assert!(private.is_dir());
    age_target(&target);
    gc_outside_workspace("gc --dry-run")
        .with_stderr_contains("Would remove workspace target [..] (unused for at least 1 hour)")
        .run();
    assert!(private.is_dir());
    gc_outside_workspace("gc")
        .with_stderr_contains("[REMOVING] workspace target [..] (unused for at least 1 hour)")
        .run();
    assert!(!private.exists());
    for path in [&registry, &thinlto] {
        assert_eq!(fs::read(path).unwrap(), b"shared cache");
    }
    assert!(target.join(".ohm-shared-registry-cache-v1").is_file());
    assert!(target.join(".ohm-target-last-use-v1").is_file());
    assert!(target.join(".ohm-build-lock").is_file());
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
        let lock = fs::OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(shared_root().join(path))
            .unwrap();
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
    cargo(&project, "gc --build-dir")
        .arg(shared_root())
        .with_stderr_does_not_contain("[WARNING] cleanup [..]")
        .run();
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

    // A long-running program protects its context, not unrelated legacy state.
    let unused = shared_root().join("debug/build/registries/0123456789abcdef");
    fs::create_dir_all(&unused).unwrap();
    fs::write(unused.join("old-artifact"), b"unused").unwrap();
    let output = cargo(&project, "gc --dry-run --build-dir")
        .arg(shared_root())
        .run();
    let stderr = String::from_utf8(output.stderr).unwrap();
    assert!(stderr.contains("Skipping context v2-"), "{stderr}");
    assert!(stderr.contains("Summary 1 file, 6B total"), "{stderr}");
    assert!(!stderr.contains("Busy lock"), "{stderr}");
    assert!(unused.exists());
    let context_lock = shared_root()
        .canonicalize()
        .unwrap()
        .join(format!(".ohm-gc-v1/context-{}.lock", context()));
    let output = cargo(&project, "gc -v --build-dir")
        .arg(shared_root())
        .run();
    let stderr = String::from_utf8(output.stderr).unwrap();
    assert!(
        stderr.contains(&format!("Busy lock {}", context_lock.display())),
        "{stderr}"
    );
    assert!(!unused.exists());
    assert!(registry.is_dir());

    // Kill Cargo alone: its test retains both the context and the private lease.
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

    let lock = fs::File::open(context_lock).unwrap();
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
