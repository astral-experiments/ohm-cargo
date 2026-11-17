//! Tests for creating an Ohm worktree with private, seeded build state.

use std::fs;
use std::path::{Path, PathBuf};

use crate::prelude::*;
use cargo_test_support::{Execs, Project, git, paths, str};

fn seeded_cargo(project: &Project, command: &str) -> Execs {
    // Packaged Ohm exercises bare commands; other test builds opt into its defaults.
    let command = if cfg!(feature = "ohm-defaults") {
        command.to_owned()
    } else {
        format!("-Zohm-defaults {command}")
    };
    let mut cargo = crate::build_dir::shared_registry_cargo(project, &command);
    cargo
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("CARGO_BUILD_BUILD_DIR", paths::root().join("shared-build"))
        .env("CARGO_INCREMENTAL", "1")
        .env_remove(cargo::CARGO_INHERITED_OHM_DEFAULTS_ENV)
        .env_remove(cargo::CARGO_INHERITED_OHM_WORKTREE_SEEDS_ENV)
        .env_remove("CARGO_TARGET_DIR");
    cargo
}

fn workspace_caches() -> Vec<PathBuf> {
    fs::read_dir(paths::root().join("shared-build/debug/build/workspaces"))
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .filter(|path| path.is_dir())
        .collect()
}

fn binary(workspace: &Path) -> PathBuf {
    workspace
        .join("target/debug")
        .join(format!("foo{}", std::env::consts::EXE_SUFFIX))
}

#[cfg(unix)]
#[cargo_test(nightly, reason = "worktree seed preparation uses checksum freshness")]
fn seed_markers_replace_symlinks() {
    let donor = git::new("donor", |p| {
        p.file("src/lib.rs", "pub fn value() {}")
            .file(
                "build.rs",
                r#"fn main() { println!("cargo:rerun-if-changed=input"); }"#,
            )
            .file("input", "first")
    });
    let build = || {
        seeded_cargo(
            &donor,
            "-Zohm-shared-registry-cache -Zohm-worktree-seeds=yes build --lib",
        )
        .run();
    };
    build();

    let namespace = workspace_caches().pop().unwrap();
    let markers: Vec<_> = walkdir::WalkDir::new(&namespace)
        .into_iter()
        .map(Result::unwrap)
        .filter(|entry| {
            let name = entry.file_name();
            name == ".ohm-worktree-result-v1"
                || name.as_encoded_bytes().starts_with(b".ohm-worktree-seed-v")
        })
        .map(|entry| entry.into_path())
        .collect();
    assert_eq!(markers.len(), 2);
    let sentinel = paths::root().join("sentinel");
    fs::write(&sentinel, "original").unwrap();
    let mut contents = Vec::new();
    for marker in &markers {
        contents.push(fs::read(marker).unwrap());
        fs::remove_file(marker).unwrap();
        std::os::unix::fs::symlink(&sentinel, marker).unwrap();
    }
    donor.change_file("input", "second");
    build();

    assert_eq!(fs::read(&sentinel).unwrap(), b"original");
    for (marker, expected) in markers.iter().zip(contents) {
        assert!(marker.symlink_metadata().unwrap().is_file());
        assert_eq!(fs::read(marker).unwrap(), expected);
    }
}

#[cargo_test]
fn creates_a_worktree_without_a_previous_build() {
    let donor = git::new("donor", |p| {
        p.file("src/main.rs", "fn main() { println!(\"hello\"); }")
    });
    let destination = paths::root().join("seeded");
    let donor_repo = git2::Repository::open(donor.root()).unwrap();
    let original_head = donor_repo.head().unwrap().target();

    donor
        .cargo("-Zohm-defaults worktree add")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .arg(&destination)
        .run();

    let seeded_repo = git2::Repository::open(&destination).unwrap();
    assert_eq!(seeded_repo.head().unwrap().target(), original_head);
    assert!(!seeded_repo.head_detached().unwrap());
    assert_eq!(seeded_repo.head().unwrap().shorthand().unwrap(), "seeded");
    assert_eq!(
        fs::read_to_string(destination.join("src/main.rs")).unwrap(),
        donor.read_file("src/main.rs")
    );
    assert_eq!(donor_repo.head().unwrap().target(), original_head);
    assert!(destination.join(".git").is_file());
}

#[cargo_test]
fn existing_branches_can_be_selected_by_basename_or_operand() {
    let (donor, repo) = git::new_repo("donor", |p| p.file("src/lib.rs", "pub fn original() {}"));
    let original = repo.head().unwrap().peel_to_commit().unwrap();
    repo.branch("existing", &original, false).unwrap();
    repo.branch("charlie/explicit", &original, false).unwrap();
    donor.change_file("src/lib.rs", "pub fn newer() {}");
    git::add(&repo);
    let donor_head = git::commit(&repo);
    assert_ne!(donor_head, original.id());

    for (directory, branch, operand) in [
        ("existing", "existing", None),
        (
            "different-name",
            "charlie/explicit",
            Some("charlie/explicit"),
        ),
    ] {
        let destination = paths::root().join(directory);
        let mut command = donor.cargo("-Zohm-defaults worktree add");
        command
            .masquerade_as_nightly_cargo(&["ohm-defaults"])
            .arg(&destination);
        if let Some(operand) = operand {
            command.arg(operand);
        }
        command.run();

        let recipient = git2::Repository::open(&destination).unwrap();
        assert!(!recipient.head_detached().unwrap());
        assert_eq!(recipient.head().unwrap().shorthand().unwrap(), branch);
        assert_eq!(recipient.head().unwrap().target(), Some(original.id()));
    }
    assert_eq!(repo.head().unwrap().target(), Some(donor_head));
}

#[cargo_test]
fn detach_options_create_detached_worktrees() {
    let (donor, repo) = git::new_repo("donor", |p| p.file("src/lib.rs", ""));
    let original_head = repo.head().unwrap().target();

    for (flag, directory) in [("--detach", "detached-long"), ("-d", "detached-short")] {
        let destination = paths::root().join(directory);
        donor
            .cargo("-Zohm-defaults worktree add")
            .masquerade_as_nightly_cargo(&["ohm-defaults"])
            .arg(flag)
            .arg(&destination)
            .run();

        let recipient = git2::Repository::open(&destination).unwrap();
        assert!(recipient.head_detached().unwrap());
        assert_eq!(recipient.head().unwrap().target(), original_head);
    }
}

#[cargo_test]
fn branch_and_detach_conflict_before_creating_a_worktree() {
    let (donor, repo) = git::new_repo("donor", |p| p.file("src/lib.rs", ""));

    for (flag, directory) in [("-b", "conflict-short"), ("--branch", "conflict-long")] {
        let destination = paths::root().join(directory);
        donor
            .cargo("-Zohm-defaults worktree add")
            .masquerade_as_nightly_cargo(&["ohm-defaults"])
            .arg(flag)
            .arg("charlie/conflicting")
            .arg("--detach")
            .arg(&destination)
            .with_status(1)
            .with_stderr_contains("[ERROR] the argument [..] cannot be used with [..]")
            .run();

        assert!(!destination.exists());
        assert_eq!(repo.worktrees().unwrap().len(), 0);
        assert!(
            repo.find_branch("charlie/conflicting", git2::BranchType::Local)
                .is_err()
        );
    }
}

#[cargo_test]
fn git_failure_preserves_an_existing_destination() {
    let donor = git::new("donor", |p| p.file("src/lib.rs", "pub fn value() {}"));
    let destination = paths::root().join("occupied");
    fs::create_dir_all(&destination).unwrap();
    fs::write(destination.join("keep.txt"), "unrelated work").unwrap();
    let donor_repo = git2::Repository::open(donor.root()).unwrap();
    let original_head = donor_repo.head().unwrap().target();

    donor
        .cargo("-Zohm-defaults worktree add -b charlie/seeded")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .arg(&destination)
        .with_status(101)
        .with_stderr_contains("[ERROR] worktree destination already exists: [ROOT]/occupied")
        .run();

    assert_eq!(
        fs::read_to_string(destination.join("keep.txt")).unwrap(),
        "unrelated work"
    );
    assert!(!destination.join(".git").exists());
    assert_eq!(donor_repo.head().unwrap().target(), original_head);
    assert_eq!(donor_repo.worktrees().unwrap().len(), 0);
}

#[cargo_test]
fn destination_target_must_be_independent_of_the_donor() {
    let donor = git::new("donor", |p| p.file("src/lib.rs", "pub fn value() {}"));
    let destination = paths::root().join("seeded");

    donor
        .cargo("-Zohm-defaults worktree add -b charlie/seeded")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .arg(&destination)
        .arg("--target-dir")
        .arg(donor.build_dir())
        .with_status(101)
        .with_stderr_contains(
            "[ERROR] destination target directory overlaps source storage: [ROOT]/donor",
        )
        .run();

    assert!(!destination.exists());
    assert_eq!(
        git2::Repository::open(donor.root())
            .unwrap()
            .worktrees()
            .unwrap()
            .len(),
        0
    );
}

#[cargo_test(
    nightly,
    reason = "worktree seeds use checksum freshness and cwd remapping"
)]
fn worktree_seeding_can_be_disabled() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file("src/lib.rs", "pub fn value() -> u32 { 1 }")
    });

    seeded_cargo(&donor, "-Zohm-worktree-seeds=no build").run();
    seeded_cargo(&donor, "worktree add")
        .arg(paths::root().join("unprepared"))
        .with_stderr_contains("[CREATED] [ROOT]/unprepared (no compatible build snapshot seeded)")
        .run();
    assert_eq!(workspace_caches().len(), 1);

    // Establish a compatible donor before checking that both overrides prevent copying it.
    seeded_cargo(&donor, "build").run();
    seeded_cargo(&donor, "worktree add")
        .arg(paths::root().join("prepared"))
        .with_stderr_contains("[..]Seeded [..] files [..]")
        .run();
    assert_eq!(workspace_caches().len(), 2);

    for (directory, command, environment) in [
        (
            "disabled-flag",
            "-Zohm-worktree-seeds=no worktree add",
            false,
        ),
        ("disabled-env", "worktree add", true),
    ] {
        let mut cargo = seeded_cargo(&donor, command);
        if environment {
            cargo.env("CARGO_UNSTABLE_OHM_WORKTREE_SEEDS", "false");
        }
        cargo
            .arg(paths::root().join(directory))
            .with_stderr_contains("[CREATED] [ROOT]/[..] (no compatible build snapshot seeded)")
            .run();
        assert_eq!(workspace_caches().len(), 2);
    }
}

#[cargo_test(
    nightly,
    reason = "worktree seeds use checksum freshness and cwd remapping"
)]
fn worktree_seeding_can_override_disabled_ohm_defaults() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file("src/lib.rs", "pub fn value() -> u32 { 1 }")
    });
    // Keep the shared layout enabled explicitly so only preparation differs.
    let without_defaults = "-Zohm-defaults=no -Zohm-shared-registry-cache";
    seeded_cargo(&donor, &format!("{without_defaults} build")).run();
    seeded_cargo(&donor, "worktree add")
        .arg(paths::root().join("unprepared"))
        .with_stderr_contains("[CREATED] [ROOT]/unprepared (no compatible build snapshot seeded)")
        .run();
    assert_eq!(workspace_caches().len(), 1);

    let enabled = format!("{without_defaults} -Zohm-worktree-seeds=yes build -v");
    seeded_cargo(&donor, &enabled).run();
    let destination = paths::root().join("seeded");
    // The worktree command itself requires Ohm defaults; subsequent builds do not.
    seeded_cargo(&donor, "worktree add")
        .arg(&destination)
        .with_stderr_contains("[..]Seeded [..] files [..]")
        .run();
    assert_eq!(workspace_caches().len(), 2);
    seeded_cargo(&donor, &enabled)
        .cwd(&destination)
        .with_stderr_contains("[FRESH] foo v0.0.1 ([ROOT]/seeded)")
        .with_stderr_does_not_contain("[COMPILING] foo v0.0.1 ([ROOT]/seeded)")
        .run();
}

#[cargo_test(
    nightly,
    reason = "worktree seeds use checksum freshness and cwd remapping"
)]
fn seeds_an_unchanged_build_and_keeps_the_worktrees_independent() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file("src/lib.rs", "pub fn value() -> &'static str { \"donor\" }")
            .file(
                "src/main.rs",
                "extern crate foo; fn main() { println!(\"{}\", foo::value()); }",
            )
    });
    let destination = paths::root().join("seeded");
    seeded_cargo(&donor, "build -v").run();

    let caches = workspace_caches();
    assert_eq!(caches.len(), 1);
    let donor_cache = &caches[0];
    let artifact = walkdir::WalkDir::new(donor_cache)
        .into_iter()
        .map(Result::unwrap)
        .map(|entry| entry.into_path())
        .find(|path| {
            path.extension()
                .is_some_and(|extension| extension == "rlib")
        })
        .expect("the donor library should have been compiled");
    let original_artifact = fs::read(&artifact).unwrap();

    seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .run();

    let caches = workspace_caches();
    assert_eq!(caches.len(), 2);
    let seeded_cache = caches.iter().find(|path| *path != donor_cache).unwrap();
    let seeded_artifact = seeded_cache.join(artifact.strip_prefix(donor_cache).unwrap());
    assert_eq!(fs::read(&seeded_artifact).unwrap(), original_artifact);
    assert!(
        !same_file::is_same_file(&artifact, &seeded_artifact).unwrap(),
        "seeding must not hard-link mutable files between worktrees"
    );
    let seeded_incremental = paths::root()
        .join("shared-build/debug/incremental")
        .join(seeded_cache.file_name().unwrap());
    assert!(
        walkdir::WalkDir::new(&seeded_incremental)
            .into_iter()
            .map(Result::unwrap)
            .any(|entry| entry.file_name() == "query-cache.bin"),
        "seeding should retain finalized incremental sessions"
    );

    seeded_cargo(&donor, "build -v")
        .cwd(&destination)
        .with_stderr_contains("[FRESH] foo v0.0.1 ([ROOT]/seeded)")
        .with_stderr_does_not_contain("[COMPILING] foo v0.0.1 ([ROOT]/seeded)")
        .run();
    assert_eq!(
        fs::read(binary(&destination)).unwrap(),
        fs::read(donor.bin("foo")).unwrap()
    );

    fs::write(
        destination.join("src/lib.rs"),
        "pub fn value() -> &'static str { \"child\" }",
    )
    .unwrap();
    destination.join("src/lib.rs").move_into_the_past();
    seeded_cargo(&donor, "build -v")
        .cwd(&destination)
        .with_stderr_contains("[COMPILING] foo v0.0.1 ([ROOT]/seeded)")
        .run();
    donor
        .process(binary(&destination))
        .with_stdout_data("child\n")
        .run();

    seeded_cargo(&donor, "build -v")
        .with_stderr_contains("[FRESH] foo v0.0.1 ([ROOT]/donor)")
        .with_stderr_does_not_contain("[COMPILING] foo v0.0.1 ([ROOT]/donor)")
        .run();
    donor
        .process(donor.bin("foo"))
        .with_stdout_data("donor\n")
        .run();
    assert_eq!(fs::read(&artifact).unwrap(), original_artifact);
}

#[cargo_test(
    nightly,
    reason = "worktree reuse must distinguish metadata cutoff from unchanged link artifacts"
)]
fn metadata_only_cutoff_does_not_reuse_a_stale_executable() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file(
                "Cargo.toml",
                r#"
                    [package]
                    name = "foo"
                    version = "0.0.1"
                    edition = "2024"

                    [workspace]
                    members = ["a", "b"]

                    [dependencies]
                    b = { path = "b" }
                "#,
            )
            .file("src/main.rs", "fn main() { println!(\"{}\", b::value()); }")
            .file(
                "b/Cargo.toml",
                r#"
                    [package]
                    name = "b"
                    version = "0.0.1"
                    edition = "2024"

                    [dependencies]
                    a = { path = "../a" }
                "#,
            )
            .file(
                "b/src/lib.rs",
                "#[inline(never)] pub fn value() -> u32 { a::value() }",
            )
            .file(
                "a/Cargo.toml",
                r#"
                    [package]
                    name = "a"
                    version = "0.0.1"
                    edition = "2024"
                "#,
            )
            .file(
                "a/src/lib.rs",
                "#[inline(never)] pub fn value() -> u32 { 1 }",
            )
    });
    let destination = paths::root().join("seeded");
    seeded_cargo(&donor, "build").run();
    seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .with_stderr_contains("[..]Seeded [..] files [..]")
        .run();
    assert_eq!(workspace_caches().len(), 2, "the child must receive a seed");

    // A's body changes without changing its API. B can reuse metadata, but
    // the executable must still link the new A through B.
    fs::write(
        destination.join("a/src/lib.rs"),
        "#[inline(never)] pub fn value() -> u32 { 2 }",
    )
    .unwrap();
    destination.join("a/src/lib.rs").move_into_the_past();
    seeded_cargo(&donor, "build -v")
        .cwd(&destination)
        .with_stderr_contains("[RUNNING] `[..]--crate-name a [..]`")
        .with_stderr_does_not_contain("[RUNNING] `[..]--crate-name b [..]`")
        .run();
    donor
        .process(binary(&destination))
        .with_stdout_data("2\n")
        .run();
    donor
        .process(donor.bin("foo"))
        .with_stdout_data("1\n")
        .run();
}

#[cfg(unix)]
#[cargo_test(
    nightly,
    reason = "worktree seeds use checksum freshness and cwd remapping"
)]
fn symlinked_cache_parent_is_rejected_without_writing_through_it() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file("src/main.rs", "fn main() { println!(\"donor\"); }")
    });
    let destination = paths::root().join("seeded");
    seeded_cargo(&donor, "build").run();

    let workspaces = paths::root().join("shared-build/debug/build/workspaces");
    let moved = paths::root().join("moved-workspace-caches");
    fs::rename(&workspaces, &moved).unwrap();
    std::os::unix::fs::symlink(&moved, &workspaces).unwrap();
    let snapshot = || {
        walkdir::WalkDir::new(&moved)
            .into_iter()
            .map(Result::unwrap)
            .map(|entry| {
                let contents = entry
                    .file_type()
                    .is_file()
                    .then(|| fs::read(entry.path()).unwrap());
                (
                    entry.path().strip_prefix(&moved).unwrap().to_owned(),
                    contents,
                )
            })
            .collect::<std::collections::BTreeMap<_, _>>()
    };
    let before = snapshot();

    seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .with_status(101)
        .with_stderr_contains(
            "[ERROR] worktree was created at [ROOT]/seeded, but build-state seeding failed",
        )
        .with_stderr_contains(
            "[..]snapshot path is not a plain directory: [ROOT]/shared-build/debug/build/workspaces",
        )
        .run();

    assert_eq!(snapshot(), before);
    assert!(destination.join(".git").is_file());
    assert!(!destination.join("target").exists());
    fs::remove_file(&workspaces).unwrap();
    fs::rename(&moved, &workspaces).unwrap();
    seeded_cargo(&donor, "build -v")
        .with_stderr_contains("[FRESH] foo v0.0.1 ([ROOT]/donor)")
        .with_stderr_does_not_contain("[COMPILING] foo v0.0.1 ([ROOT]/donor)")
        .run();
    donor
        .process(donor.bin("foo"))
        .with_stdout_data("donor\n")
        .run();
}

#[cargo_test(
    nightly,
    reason = "worktree seeds use checksum freshness and cwd remapping"
)]
fn dirty_donor_does_not_override_the_requested_commit() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file("src/main.rs", "fn main() { println!(\"committed\"); }")
    });
    let destination = paths::root().join("seeded");
    donor.change_file("src/main.rs", "fn main() { println!(\"dirty\"); }");
    seeded_cargo(&donor, "build").run();

    seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .arg("HEAD")
        .run();
    // A copied mtime fingerprint would incorrectly accept the donor's binary here.
    destination.join("src/main.rs").move_into_the_past();
    seeded_cargo(&donor, "build -v")
        .cwd(&destination)
        .with_stderr_contains("[COMPILING] foo v0.0.1 ([ROOT]/seeded)")
        .run();
    donor
        .process(binary(&destination))
        .with_stdout_data("committed\n")
        .run();
    donor
        .process(donor.bin("foo"))
        .with_stdout_data("dirty\n")
        .run();
    assert_eq!(
        donor.read_file("src/main.rs"),
        "fn main() { println!(\"dirty\"); }"
    );
}

#[cargo_test(
    nightly,
    reason = "worktree seeds use checksum freshness and cwd remapping"
)]
fn sibling_source_file_is_revalidated_in_the_requested_commit() {
    let (donor, repo) = git::new_repo("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file(
                "Cargo.toml",
                r#"
                    [workspace]
                    members = ["app"]
                    resolver = "3"
                "#,
            )
            .file(
                "app/Cargo.toml",
                r#"
                    [package]
                    name = "foo"
                    version = "0.0.1"
                    edition = "2024"
                "#,
            )
            .file(
                "app/src/main.rs",
                "fn main() { println!(\"{}\", include_str!(\"../../shared.txt\")); }",
            )
            .file("shared.txt", "donor")
    });
    let original = repo.revparse_single("HEAD").unwrap();
    seeded_cargo(&donor, "build").run();

    donor.change_file("shared.txt", "child");
    git::add(&repo);
    let requested = git::commit(&repo);
    repo.reset(&original, git2::ResetType::Hard, None).unwrap();
    assert_eq!(donor.read_file("shared.txt"), "donor");

    let destination = paths::root().join("seeded");
    seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .arg(requested.to_string())
        .run();
    assert_eq!(workspace_caches().len(), 2, "the child must receive a seed");
    destination.join("shared.txt").move_into_the_past();
    destination.join("app/src/main.rs").move_into_the_past();
    seeded_cargo(&donor, "build -v").cwd(&destination).run();
    donor
        .process(binary(&destination))
        .with_stdout_data("child\n")
        .run();
    donor
        .process(donor.bin("foo"))
        .with_stdout_data("donor\n")
        .run();
}

#[cfg(unix)]
#[cargo_test(
    nightly,
    reason = "worktree seeds use checksum freshness and cwd remapping"
)]
fn retargeted_source_symlinks_are_revalidated_in_the_new_worktree() {
    let (donor, repo) = git::new_repo("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", include_str!(\"data.txt\")); }",
            )
            .file("a.txt", "donor")
            .file("b.txt", "child")
    });
    let link = donor.root().join("src/data.txt");
    std::os::unix::fs::symlink("../a.txt", &link).unwrap();
    git::add(&repo);
    git::commit(&repo);
    let original = repo.revparse_single("HEAD").unwrap();
    seeded_cargo(&donor, "build").run();

    fs::remove_file(&link).unwrap();
    std::os::unix::fs::symlink("../b.txt", &link).unwrap();
    git::add(&repo);
    let requested = git::commit(&repo);
    repo.reset(&original, git2::ResetType::Hard, None).unwrap();

    let destination = paths::root().join("seeded");
    seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .arg(requested.to_string())
        .run();
    assert_eq!(workspace_caches().len(), 2, "the child must receive a seed");
    destination.join("b.txt").move_into_the_past();
    destination.join("src/main.rs").move_into_the_past();
    seeded_cargo(&donor, "build -v").cwd(&destination).run();
    donor
        .process(binary(&destination))
        .with_stdout_data("child\n")
        .run();
    donor
        .process(donor.bin("foo"))
        .with_stdout_data("donor\n")
        .run();
}

#[cargo_test(
    nightly,
    reason = "worktree seeds use checksum freshness and cwd remapping"
)]
fn cargo_manifest_environment_is_revalidated_without_a_build_script() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n").file(
            "src/main.rs",
            r#"
                fn main() {
                    println!("directory={}", env!("CARGO_MANIFEST_DIR"));
                    println!("manifest={}", env!("CARGO_MANIFEST_PATH"));
                }
            "#,
        )
    });
    let destination = paths::root().join("seeded");
    seeded_cargo(&donor, "build").run();
    seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .run();
    assert_eq!(workspace_caches().len(), 2, "the child must receive a seed");
    seeded_cargo(&donor, "build -v").cwd(&destination).run();
    donor
        .process(binary(&destination))
        .with_stdout_data(str![[r#"
directory=[ROOT]/seeded
manifest=[ROOT]/seeded/Cargo.toml

"#]])
        .run();
    seeded_cargo(&donor, "build -v")
        .cwd(&destination)
        .with_stderr_contains("[FRESH] foo v0.0.1 ([ROOT]/seeded)")
        .with_stderr_does_not_contain("[COMPILING] foo v0.0.1 ([ROOT]/seeded)")
        .run();
}

#[cargo_test(
    nightly,
    reason = "worktree seeds use checksum freshness and cwd remapping"
)]
fn integration_tests_execute_the_recipient_binary() {
    let (donor, repo) = git::new_repo("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file("src/main.rs", "fn main() { println!(\"donor\"); }")
            .file("expected-output.txt", "donor\n")
            .file(
                "tests/binary.rs",
                r#"
                    #[test]
                    fn runs_the_worktrees_binary() {
                        let output = std::process::Command::new(env!("CARGO_BIN_EXE_foo"))
                            .output()
                            .unwrap();
                        assert!(output.status.success());
                        // Cargo runs tests in the current package directory. Read this
                        // at runtime so changing the expected value cannot itself make
                        // a transplanted test executable stale.
                        let expected = std::fs::read_to_string("expected-output.txt").unwrap();
                        assert_eq!(String::from_utf8(output.stdout).unwrap(), expected);
                    }
                "#,
            )
    });
    let original = repo.revparse_single("HEAD").unwrap();
    seeded_cargo(&donor, "test").run();

    donor.change_file("src/main.rs", "fn main() { println!(\"child\"); }");
    donor.change_file("expected-output.txt", "child\n");
    git::add(&repo);
    let requested = git::commit(&repo);
    repo.reset(&original, git2::ResetType::Hard, None).unwrap();

    let destination = paths::root().join("seeded");
    seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .arg(requested.to_string())
        .with_stderr_contains("[..](no compatible build snapshot seeded)")
        .with_stderr_contains("[..]1 unprepared or unsupported build profiles")
        .run();
    assert_eq!(
        workspace_caches().len(),
        1,
        "the unsafe profile must be skipped"
    );
    seeded_cargo(&donor, "test").cwd(&destination).run();
    seeded_cargo(&donor, "test").run();
}

#[cargo_test(
    nightly,
    reason = "worktree seeds use checksum freshness and cwd remapping"
)]
fn path_sensitive_code_and_build_scripts_use_the_new_worktree() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file(
                "build.rs",
                r#"
                    fn main() {
                        let output = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
                        std::fs::write(
                            output.join("manifest.txt"),
                            std::env::var("CARGO_MANIFEST_DIR").unwrap(),
                        ).unwrap();
                        println!("cargo:rerun-if-changed=build.rs");
                    }
                "#,
            )
            .file(
                "src/main.rs",
                r#"
                    fn main() {
                        println!("manifest={}", env!("CARGO_MANIFEST_DIR"));
                        println!("build={}", include_str!(concat!(env!("OUT_DIR"), "/manifest.txt")));
                        println!("value={}", env!("WORKTREE_SEED_VALUE"));
                    }
                "#,
            )
    });
    let destination = paths::root().join("seeded");
    seeded_cargo(&donor, "build")
        .env("WORKTREE_SEED_VALUE", "shared")
        .run();
    seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .run();
    seeded_cargo(&donor, "build -v")
        .cwd(&destination)
        .env("WORKTREE_SEED_VALUE", "shared")
        .run();
    donor
        .process(binary(&destination))
        .with_stdout_data(str![[r#"
manifest=[ROOT]/seeded
build=[ROOT]/seeded
value=shared

"#]])
        .run();
}

#[cargo_test(
    nightly,
    reason = "worktree seeds compare regenerated build-script results by contents"
)]
fn identical_build_script_results_preserve_seeded_compilations() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n/script-ran\n")
            .file(
                "build.rs",
                r#"
                    fn main() {
                        std::fs::write("script-ran", std::env::var("CARGO_MANIFEST_DIR").unwrap()).unwrap();
                        let output = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
                        std::fs::write(output.join("unchanged.txt"), "same bytes").unwrap();
                        println!("cargo:rerun-if-changed=build.rs");
                        println!("cargo:rustc-env=GENERATED_VALUE=shared");
                    }
                "#,
            )
            .file("src/lib.rs", "pub fn value() -> &'static str { env!(\"GENERATED_VALUE\") }")
            .file("src/main.rs", "extern crate foo; fn main() { println!(\"{}\", foo::value()); }")
    });
    let destination = paths::root().join("seeded");
    seeded_cargo(&donor, "build").run();
    seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .with_stderr_contains("[..]Seeded [..] files [..]")
        .run();

    seeded_cargo(&donor, "build -v")
        .cwd(&destination)
        .with_stderr_does_not_contain("[RUNNING] `[..]--crate-name foo [..]`")
        .run();
    assert_eq!(
        fs::read_to_string(destination.join("script-ran")).unwrap(),
        destination.to_str().unwrap()
    );
    donor
        .process(binary(&destination))
        .with_stdout_data("shared\n")
        .run();

    // The newly written stdout timestamp must not make the next build stale.
    seeded_cargo(&donor, "build -v")
        .cwd(&destination)
        .with_stderr_does_not_contain("[RUNNING]")
        .run();
    donor
        .process(donor.bin("foo"))
        .with_stdout_data("shared\n")
        .run();
}

#[cargo_test(
    nightly,
    reason = "worktree seeds compare regenerated build-script results by contents"
)]
fn changed_build_script_results_invalidate_seeded_compilations() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file("value.txt", "donor")
            .file(
                "build.rs",
                r#"
                    fn main() {
                        println!("cargo:rerun-if-changed=value.txt");
                        println!("cargo:rustc-env=GENERATED_VALUE={}", std::fs::read_to_string("value.txt").unwrap());
                    }
                "#,
            )
            .file("src/main.rs", "fn main() { println!(\"{}\", env!(\"GENERATED_VALUE\")); }")
    });
    let destination = paths::root().join("seeded");
    seeded_cargo(&donor, "build").run();
    seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .with_stderr_contains("[..]Seeded [..] files [..]")
        .run();
    fs::write(destination.join("value.txt"), "child").unwrap();
    destination.join("value.txt").move_into_the_past();

    seeded_cargo(&donor, "build -v").cwd(&destination).run();
    donor
        .process(binary(&destination))
        .with_stdout_data("child\n")
        .run();
    donor
        .process(donor.bin("foo"))
        .with_stdout_data("donor\n")
        .run();
}

#[cargo_test(
    nightly,
    reason = "worktree seeds revalidate consumed source after build scripts finish"
)]
fn source_rewritten_by_a_build_script_is_checked_after_execution() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file("src/generated.rs", "1")
            .file(
                "build.rs",
                r#"
                    fn main() {
                        // Identical script stdout/output-directory contents do not certify
                        // files the script writes elsewhere in the package.
                        std::fs::write("src/generated.rs", std::env::var("GENERATED_VALUE").unwrap()).unwrap();
                        std::fs::OpenOptions::new().write(true).open("src/generated.rs").unwrap()
                            .set_modified(std::time::UNIX_EPOCH + std::time::Duration::from_secs(86400)).unwrap();
                        println!("cargo:rerun-if-changed=build.rs");
                    }
                "#,
            )
            .file("src/main.rs", "fn main() { println!(\"{}\", include!(\"generated.rs\")); }")
    });
    let destination = paths::root().join("seeded");
    seeded_cargo(&donor, "build")
        .env("GENERATED_VALUE", "1")
        .run();
    seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .with_stderr_contains("[..]Seeded [..] files [..]")
        .run();
    seeded_cargo(&donor, "build -v")
        .cwd(&destination)
        .env("GENERATED_VALUE", "2")
        .run();
    donor
        .process(binary(&destination))
        .with_stdout_data("2\n")
        .run();
    donor
        .process(donor.bin("foo"))
        .with_stdout_data("1\n")
        .run();
}

#[cargo_test(
    nightly,
    reason = "worktree seeds preserve the actual meaning of observed output paths"
)]
fn embedded_output_directory_is_revalidated_after_relocation() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file(
                "build.rs",
                "fn main() { println!(\"cargo:rerun-if-changed=build.rs\"); }",
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", env!(\"OUT_DIR\")); }",
            )
    });
    let destination = paths::root().join("seeded");
    seeded_cargo(&donor, "build").run();
    let donor_namespace = workspace_caches().pop().unwrap();
    let original = donor.process(donor.bin("foo")).run().stdout;
    seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .with_stderr_contains("[..]Seeded [..] files [..]")
        .run();
    let recipient_namespace = workspace_caches()
        .into_iter()
        .find(|path| *path != donor_namespace)
        .unwrap();
    seeded_cargo(&donor, "build -v").cwd(&destination).run();
    let relocated = donor.process(binary(&destination)).run().stdout;
    assert_ne!(relocated, original);
    assert!(
        Path::new(std::str::from_utf8(&relocated).unwrap().trim())
            .starts_with(&recipient_namespace)
    );
}

#[cargo_test(
    nightly,
    reason = "worktree seeds use checksum freshness and cwd remapping"
)]
fn local_proc_macros_use_the_new_worktrees_environment() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file(
                "Cargo.toml",
                r#"
                    [package]
                    name = "foo"
                    version = "0.0.1"
                    edition = "2024"

                    [workspace]
                    members = ["path-macro"]

                    [dependencies]
                    path-macro = { path = "path-macro" }
                "#,
            )
            .file(
                "path-macro/Cargo.toml",
                r#"
                    [package]
                    name = "path-macro"
                    version = "0.0.1"
                    edition = "2024"

                    [lib]
                    proc-macro = true
                "#,
            )
            .file(
                "path-macro/src/lib.rs",
                r#"
                    extern crate proc_macro;

                    #[proc_macro]
                    pub fn manifest_dir(_: proc_macro::TokenStream) -> proc_macro::TokenStream {
                        // Unlike env!, this runtime read does not appear in rustc's dep-info.
                        let directory = std::env::var("CARGO_MANIFEST_DIR").unwrap();
                        format!("{directory:?}").parse().unwrap()
                    }
                "#,
            )
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", path_macro::manifest_dir!()); }",
            )
    });
    let destination = paths::root().join("seeded");
    seeded_cargo(&donor, "build").run();
    donor
        .process(donor.bin("foo"))
        .with_stdout_data(str![[r#"
[ROOT]/donor

"#]])
        .run();

    seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .run();
    seeded_cargo(&donor, "build").cwd(&destination).run();
    donor
        .process(binary(&destination))
        .with_stdout_data(str![[r#"
[ROOT]/seeded

"#]])
        .run();
}

#[cargo_test(
    nightly,
    reason = "worktree seeds use checksum freshness and cwd remapping"
)]
fn external_targets_stay_independent_and_recheck_changed_environment() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/Cargo.lock\n").file(
            "src/main.rs",
            "fn main() { println!(\"{}\", env!(\"WORKTREE_SEED_VALUE\")); }",
        )
    });
    let destination = paths::root().join("seeded");
    let donor_target = paths::root().join("donor-target");
    let seeded_target = paths::root().join("seeded-target");

    seeded_cargo(&donor, "build")
        .env("CARGO_TARGET_DIR", &donor_target)
        .env("WORKTREE_SEED_VALUE", "donor")
        .run();
    seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .env("CARGO_TARGET_DIR", &donor_target)
        .arg(&destination)
        .arg("--target-dir")
        .arg(&seeded_target)
        .run();

    seeded_cargo(&donor, "build -v")
        .cwd(&destination)
        .env("CARGO_TARGET_DIR", &seeded_target)
        .env("WORKTREE_SEED_VALUE", "donor")
        .with_stderr_contains("[FRESH] foo v0.0.1 ([ROOT]/seeded)")
        .with_stderr_does_not_contain("[COMPILING] foo v0.0.1 ([ROOT]/seeded)")
        .run();
    seeded_cargo(&donor, "build -v")
        .cwd(&destination)
        .env("CARGO_TARGET_DIR", &seeded_target)
        .env("WORKTREE_SEED_VALUE", "child")
        .with_stderr_contains("[COMPILING] foo v0.0.1 ([ROOT]/seeded)")
        .run();
    let executable = format!("debug/foo{}", std::env::consts::EXE_SUFFIX);
    donor
        .process(seeded_target.join(&executable))
        .with_stdout_data("child\n")
        .run();
    donor
        .process(donor_target.join(&executable))
        .with_stdout_data("donor\n")
        .run();
    assert!(!destination.join("target").exists());
}
