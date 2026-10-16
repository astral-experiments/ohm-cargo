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
use cargo_test_support::registry::Package;
use cargo_test_support::{Execs, Project, git, paths, slow_cpu_multiplier};

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

fn namespace(worktree: &Path) -> String {
    let worktree = worktree.canonicalize().unwrap();
    let record = json_files(&shared_root().join(".ohm-gc-v1/workspaces"))
        .into_iter()
        .find(|path| {
            let value: serde_json::Value =
                serde_json::from_slice(&fs::read(path).unwrap()).unwrap();
            value["workspace_root"].as_str() == worktree.to_str()
        })
        .expect("linked worktree is registered");
    record.file_stem().unwrap().to_str().unwrap().to_owned()
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

/// Models retained data from the old layout, then lets a warm build enroll its ownership.
fn enroll_legacy_private_state(project: &Project, worktree: &Path, target: &Path) {
    let local = local_private_artifacts(target);
    let namespace = local.file_name().unwrap().to_str().unwrap();
    let private = private_artifacts(namespace);
    fs::create_dir_all(&private).unwrap();
    fs::write(private.join("legacy-artifact"), b"old build").unwrap();
    let incremental = shared_root().join("debug/incremental").join(namespace);
    fs::create_dir_all(incremental).unwrap();
    cargo(project, "build")
        .cwd(worktree)
        .env("CARGO_TARGET_DIR", target)
        .run();
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
    let mut records = json_files(&metadata.join("contexts"));
    records.extend(json_files(
        &paths::home().join(".cargo/.ohm-build-roots-v1"),
    ));
    assert!(
        records.len() >= 2,
        "only context and shared root need registration"
    );
    let old_mtime = filetime::FileTime::from_unix_time(946_684_800, 0);
    let before = records
        .into_iter()
        .map(|path| {
            let contents = fs::read(&path).unwrap();
            filetime::set_file_mtime(&path, old_mtime).unwrap();
            (path, contents)
        })
        .collect::<Vec<_>>();

    let usage = fs::read_dir(metadata.join("last-used"))
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .collect::<Vec<_>>();
    assert!(!usage.is_empty());
    for path in &usage {
        filetime::set_file_mtime(path, old_mtime).unwrap();
    }
    let started = SystemTime::now();
    cargo(&project, "build -v")
        .cwd(&worktree)
        .with_stderr_contains("[FRESH] foo v0.0.1 [..]")
        .with_stderr_does_not_contain("[COMPILING] [..]")
        .run();
    for path in usage {
        assert!(fs::metadata(path).unwrap().modified().unwrap() >= started);
    }
    for (path, contents) in before {
        assert_eq!(fs::read(&path).unwrap(), contents, "{}", path.display());
        assert_eq!(
            filetime::FileTime::from_last_modification_time(&fs::metadata(&path).unwrap()),
            old_mtime,
            "fresh builds must not rewrite {}",
            path.display()
        );
    }
}

#[cargo_test]
fn idle_context_is_collected_globally_and_rebuilds_on_demand() {
    let project = donor();
    cargo(&project, "build").run();
    let metadata = shared_root().join(".ohm-gc-v1");
    let records = json_files(&metadata.join("contexts"));
    assert_eq!(records.len(), 1);
    let context = records[0].file_stem().unwrap();
    let registry = shared_root().join("debug/build/registries").join(context);
    let private = local_private_artifacts(&project.root().join("target")).join(context);
    let usage = metadata.join("last-used").join(context);
    assert!(registry.is_dir());
    assert!(private.is_dir());
    filetime::set_file_mtime(&usage, filetime::FileTime::from_unix_time(946_684_800, 0)).unwrap();
    collect(&project, true);
    assert!(registry.is_dir());
    assert!(private.is_dir());
    cargo(&project, "gc")
        .cwd(paths::root())
        .with_stderr_contains(
            "[..]Cache retiring contexts/[..]: context unused for at least one hour",
        )
        .run();
    assert!(!registry.exists());
    assert!(
        private.is_dir(),
        "global GC preserves worktree-private state"
    );
    assert!(!records[0].exists());
    assert!(!usage.exists());
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
    enroll_legacy_private_state(&project, &worktree, &external_target);
    let namespace = namespace(&worktree);
    let private = private_artifacts(&namespace);
    let incremental = shared_root().join("debug/incremental").join(&namespace);
    assert!(private.is_dir());
    assert!(incremental.is_dir());
    assert!(!worktree.join("target").exists());

    remove_worktree(&project, &worktree);
    let record = shared_root()
        .join(".ohm-gc-v1/workspaces")
        .join(format!("{namespace}.json"));
    let before = fs::read(&record).unwrap();
    cargo(&project, "gc --dry-run")
        .cwd(paths::root())
        .with_stderr_contains("[..]Cache would retire workspaces/[..]")
        .run();
    assert!(private.is_dir(), "dry run preserves artifacts");
    assert_eq!(fs::read(&record).unwrap(), before);
    assert!(!shared_root().join(".ohm-gc-v1/candidates.json").exists());
    cargo(&project, "gc")
        .cwd(paths::root())
        .env_remove("CARGO_BUILD_BUILD_DIR")
        .run();
    assert!(!private.exists());
    assert!(!incremental.exists());
    assert!(!record.exists());
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
fn moved_and_registered_missing_worktrees_are_preserved() {
    let project = donor();
    let moved = add_worktree(&project, "before-move");
    let missing = add_worktree(&project, "registered-missing");
    for worktree in [&moved, &missing] {
        cargo(&project, "build").cwd(worktree).run();
        enroll_legacy_private_state(&project, worktree, &worktree.join("target"));
    }
    let retained = [namespace(&moved), namespace(&missing)];
    project
        .process("git")
        .args(&["worktree", "move"])
        .arg(&moved)
        .arg(paths::root().join("after-move"))
        .run();
    fs::rename(&missing, paths::root().join("temporarily-unavailable")).unwrap();

    collect(&project, false);
    for namespace in retained {
        assert!(private_artifacts(&namespace).is_dir());
    }
}

#[cargo_test]
fn busy_consumers_and_profiles_postpone_retirement() {
    let project = donor();
    let worktree = add_worktree(&project, "busy");
    cargo(&project, "build").cwd(&worktree).run();
    enroll_legacy_private_state(&project, &worktree, &worktree.join("target"));
    let private = private_artifacts(&namespace(&worktree));
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
    enroll_legacy_private_state(&project, &worktree, &worktree.join("target"));
    let private = private_artifacts(&namespace(&worktree));
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
    let context = json_files(&shared_root().join(".ohm-gc-v1/contexts"))[0].clone();
    let context = context.file_stem().unwrap();
    let registry = shared_root().join("debug/build/registries").join(context);
    let usage = shared_root().join(".ohm-gc-v1/last-used").join(context);
    filetime::set_file_mtime(usage, filetime::FileTime::from_unix_time(946_684_800, 0)).unwrap();

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
