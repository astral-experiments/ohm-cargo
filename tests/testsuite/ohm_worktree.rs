//! Tests for creating an Ohm worktree with private, seeded build state.

use std::fs;
use std::path::{Path, PathBuf};

use crate::prelude::*;
use cargo_test_support::{Execs, Project, git, paths, project, str};

fn seeded_cargo(project: &Project, command: &str) -> Execs {
    // Packaged Ohm exercises bare commands; other test builds opt into its defaults.
    let command = if cfg!(feature = "ohm-defaults") {
        command.to_owned()
    } else {
        format!("-Zohm-defaults {command}")
    };
    let mut cargo = crate::build_dir::shared_registry_cargo(project, &command);
    cargo
        .masquerade_as_nightly_cargo(&["ohm-defaults", "ohm-clippy-seed-isolation"])
        .env("CARGO_BUILD_BUILD_DIR", paths::root().join("shared-build"))
        .env("CARGO_INCREMENTAL", "1")
        .env_remove(cargo::CARGO_INHERITED_OHM_DEFAULTS_ENV)
        .env_remove(cargo::CARGO_INHERITED_OHM_WORKTREE_SEEDS_ENV)
        .env_remove(cargo::CARGO_INHERITED_OHM_CLIPPY_SEED_ISOLATION_ENV)
        .env_remove("CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION")
        .env_remove("CARGO_EXPERIMENTAL_CLIPPY_SEED_ISOLATION")
        .env_remove("CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST")
        .env_remove("CARGO_TARGET_DIR");
    cargo
}

#[cargo_test]
fn coverage_uses_source_paths_from_the_checkout() {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
            cargo-features = ["profile-rustflags"]
            [package]
            name = "coverage-paths"
            version = "0.1.0"
            edition = "2021"
            [profile.covered]
            inherits = "dev"
            rustflags = ["@coverage.rsp"]
        "#,
        )
        .file("coverage.rsp", "-Cinstrument-coverage\n")
        .file("src/lib.rs", "pub fn covered() -> u8 { 1 }")
        .build();
    for (profile, flags, remapped) in [
        ("dev", "-Cinstrument-coverage", false),
        ("dev", "--codegen instrument_coverage=yes", false),
        (
            "dev",
            "-Cinstrument-coverage -C instrument-coverage=no",
            true,
        ),
        ("covered", "", false),
    ] {
        let mut check = p.cargo("-Zohm-defaults=no -Zohm-worktree-seeds check -v");
        check
            .arg("--profile")
            .arg(profile)
            .masquerade_as_nightly_cargo(&[
                "ohm-defaults",
                "ohm-worktree-seeds",
                "profile-rustflags",
            ])
            .env("RUSTC_BOOTSTRAP", "1")
            .env("RUSTFLAGS", flags);
        if remapped {
            check.with_stderr_contains("[..]-Zremap-cwd-prefix=[..]");
        } else {
            check.with_stderr_does_not_contain("[..]-Zremap-cwd-prefix=[..]");
        }
        check.run();
    }
}

/// Reuse-specific assertions require a clone-capable test filesystem.
/// The import policy test below also verifies normal builds when cloning is unavailable.
pub(super) fn seed_was_imported(output: &cargo_test_support::RawOutput) -> bool {
    let probe = tempfile::tempdir_in(paths::root().join("shared-build")).unwrap();
    let source = probe.path().join("source");
    fs::write(&source, [0x42; 4096]).unwrap();
    let supported = paths::clone_file(&source, &probe.path().join("destination"));
    probe.close().unwrap();
    let stderr = std::str::from_utf8(&output.stderr).unwrap();
    if stderr.contains("without copy-on-write support") {
        assert!(
            !supported,
            "Cargo skipped a clone-capable filesystem: {stderr}"
        );
        assert!(
            stderr.contains("no compatible build snapshot seeded"),
            "{stderr}"
        );
        assert!(!stderr.contains("Seeded"), "{stderr}");
        eprintln!("skipping reuse assertions: test filesystem does not support cloning");
        false
    } else {
        assert!(
            supported,
            "Cargo seeded without independent clone support: {stderr}"
        );
        assert!(stderr.contains("Seeded"), "{stderr}");
        assert!(!stderr.contains(", 0 reflinked files)"), "{stderr}");
        true
    }
}

fn workspace_caches() -> Vec<PathBuf> {
    fs::read_dir(paths::root())
        .unwrap()
        .map(|entry| entry.unwrap().path().join("target/debug/build/workspaces"))
        .filter_map(|path| fs::read_dir(path).ok())
        .flatten()
        .map(|entry| entry.unwrap().path())
        .filter(|path| path.is_dir())
        .collect()
}

fn incremental_for(namespace: &Path) -> PathBuf {
    namespace
        .ancestors()
        .nth(3)
        .unwrap()
        .join("incremental")
        .join(namespace.file_name().unwrap())
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
    let result = walkdir::WalkDir::new(&namespace)
        .into_iter()
        .map(Result::unwrap)
        .find(|entry| entry.file_name() == ".ohm-worktree-result-v1")
        .unwrap()
        .into_path();
    let sentinel = paths::root().join("sentinel");
    fs::write(&sentinel, "original").unwrap();
    let markers = [namespace.join(".ohm-worktree-seed-v7"), result];
    let contents = markers.each_ref().map(|p| fs::read(p).unwrap());
    for marker in &markers {
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

#[cargo_test(
    nightly,
    reason = "worktree imports require cloning even with explicit preparation or isolation"
)]
fn worktree_import_requires_cloning() {
    for isolation in ["false", "true"] {
        let donor = git::new(&format!("donor-{isolation}"), |p| {
            p.file(".gitignore", "/target\n/Cargo.lock\n")
                .file("src/lib.rs", "pub fn value() -> u32 { 1 }")
        });
        seeded_cargo(&donor, "-Zohm-worktree-seeds=yes build").run();
        let before = workspace_caches().len();
        let destination = paths::root().join(format!("seeded-{isolation}"));
        let output = seeded_cargo(&donor, "worktree add")
            .env("CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION", isolation)
            .arg(&destination)
            .run();
        let cloned = seed_was_imported(&output);
        assert_eq!(workspace_caches().len(), before + usize::from(cloned));
        assert!(git2::Repository::open(&destination).unwrap().is_worktree());
        assert!(
            !walkdir::WalkDir::new(paths::root())
                .into_iter()
                .map(Result::unwrap)
                .any(|entry| entry.file_type().is_dir()
                    && entry
                        .file_name()
                        .to_string_lossy()
                        .starts_with(".ohm-worktree-seed-"))
        );
        let mut build = seeded_cargo(&donor, "build -v");
        build.cwd(&destination);
        if cloned {
            build
                .with_stderr_contains("[FRESH] foo [..]")
                .with_stderr_does_not_contain("[COMPILING] foo [..]");
        } else {
            build.with_stderr_contains("[COMPILING] foo [..]");
        }
        build.run();
        seeded_cargo(&donor, "build -v")
            .with_stderr_contains("[FRESH] foo [..]")
            .with_stderr_does_not_contain("[COMPILING] foo [..]")
            .run();
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
fn loads_registry_configuration_from_the_selected_revision() {
    let manifest = r#"
        [package]
        name = "app"
        version = "0.1.0"
        edition = "2024"

        [dependencies]
        dep = { path = "dep", version = "0.1.0", registry = "selected" }
    "#;
    let (donor, repo) = git::new_repo("donor", |p| {
        p.file("Cargo.toml", manifest)
            .file("src/lib.rs", "")
            .file(
                "dep/Cargo.toml",
                &cargo_test_support::basic_manifest("dep", "0.1.0"),
            )
            .file("dep/src/lib.rs", "")
            .file(
                ".cargo/config.toml",
                r#"[registries.selected]
index = "sparse+https://selected.invalid/index/"
"#,
            )
    });
    let selected = repo.head().unwrap().target().unwrap();
    fs::write(
        donor.root().join("Cargo.toml"),
        cargo_test_support::basic_manifest("app", "0.1.0"),
    )
    .unwrap();
    fs::remove_file(donor.root().join(".cargo/config.toml")).unwrap();
    git::add(&repo);
    git::commit(&repo);

    let child = paths::root().join("child");
    seeded_cargo(&donor, "worktree add --detach")
        .arg(&child)
        .arg(selected.to_string())
        .run();
    donor.cargo("check --offline").cwd(child).run();
}

#[cargo_test]
fn discovers_worktree_configuration_from_the_calling_member() {
    let (donor, _) = git::new_repo("donor", |p| {
        p.file("Cargo.toml", "[workspace]\nmembers = ['app', 'dep']\nresolver = '3'\n")
            .file("app/Cargo.toml", &format!(
                "{}\n[dependencies]\ndep = {{ path = '../dep', version = '0.1.0', registry = 'local' }}\n",
                cargo_test_support::basic_manifest("app", "0.1.0")
            ))
            .file("app/src/lib.rs", "")
            .file("app/.cargo/config.toml", "[registries.local]\nindex = 'sparse+https://local.invalid/'\n")
            .file("dep/Cargo.toml", &cargo_test_support::basic_manifest("dep", "0.1.0"))
            .file("dep/src/lib.rs", "")
    });
    let child = paths::root().join("child");
    seeded_cargo(&donor, "worktree add --detach")
        .cwd(donor.root().join("app"))
        .arg(&child)
        .run();
    donor.cargo("check --offline").cwd(child.join("app")).run();
}

#[cfg(unix)]
#[cargo_test]
fn keeps_the_package_root_of_a_symlinked_manifest() {
    let (donor, repo) = git::new_repo("donor", |p| p.file("src/lib.rs", ""));
    let root = donor.root();
    fs::create_dir(root.join("templates")).unwrap();
    fs::rename(root.join("Cargo.toml"), root.join("templates/package.toml")).unwrap();
    std::os::unix::fs::symlink("templates/package.toml", root.join("Cargo.toml")).unwrap();
    git::add(&repo);
    git::commit(&repo);

    let child = paths::root().join("child");
    donor
        .cargo("-Zohm-defaults worktree add --detach")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .arg(&child)
        .run();
    donor.cargo("check").cwd(child).run();
}

#[cfg(unix)]
#[cargo_test]
fn follows_package_directories_in_the_selected_commit() {
    let (donor, repo) = git::new_repo("donor", |p| {
        p.no_manifest()
            .file(
                "first/Cargo.toml",
                &cargo_test_support::basic_manifest("app", "1.0.0"),
            )
            .file("first/src/lib.rs", "")
    });
    let root = donor.root();
    let current = root.join("current");
    std::os::unix::fs::symlink("first", &current).unwrap();
    git::add(&repo);
    let first = git::commit(&repo);
    fs::rename(root.join("first"), root.join("second")).unwrap();
    fs::remove_file(&current).unwrap();
    std::os::unix::fs::symlink("second", &current).unwrap();
    git::add(&repo);
    git::commit(&repo);

    let child = paths::root().join("child");
    donor
        .cargo("-Zohm-defaults worktree add --detach --manifest-path")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .arg(current.join("Cargo.toml"))
        .arg(&child)
        .arg(first.to_string())
        .run();
    donor
        .cargo("check --manifest-path")
        .arg(child.join("current/Cargo.toml"))
        .run();
}

#[cfg(unix)]
#[cargo_test]
fn maps_a_donor_only_directory_alias_into_the_worktree() {
    let donor = git::new("donor", |p| p.file("src/lib.rs", ""));
    let local = donor.root().join("local");
    fs::create_dir(&local).unwrap();
    std::os::unix::fs::symlink("..", local.join("package")).unwrap();

    donor
        .cargo("-Zohm-defaults worktree add --detach --manifest-path")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .arg(local.join("package/Cargo.toml"))
        .arg(paths::root().join("child"))
        .run();
}

#[cfg(unix)]
#[cargo_test]
fn rejects_a_package_directory_pointing_back_to_the_donor() {
    let (donor, repo) = git::new_repo("donor", |p| p.file("src/lib.rs", ""));
    let alias = donor.root().join("current");
    std::os::unix::fs::symlink(donor.root(), &alias).unwrap();
    git::add(&repo);
    git::commit(&repo);

    donor
        .cargo("-Zohm-defaults worktree add --detach --manifest-path")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .arg(alias.join("Cargo.toml"))
        .arg(paths::root().join("child"))
        .with_status(101)
        .with_stderr_contains("[..]outside the new worktree[..]")
        .run();
    assert!(!donor.root().join("target").exists());
}

#[cargo_test]
fn discovers_a_nested_package_in_a_sha256_repository() {
    let root = paths::root().join("donor");
    let donor = project()
        .at(root.join("nested"))
        .file("src/lib.rs", "pub fn from_donor() {}")
        .build();
    donor
        .process("git")
        .cwd(&root)
        .args(&["init", "--object-format=sha256"])
        .run();
    donor.process("git").args(&["add", "."]).run();
    donor
        .process("git")
        .args(&[
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "initial",
        ])
        .run();
    let destination = paths::root().join("child");
    donor
        .cargo("-Zohm-defaults worktree add --detach")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .env("GIT_CEILING_DIRECTORIES", &root)
        .arg(&destination)
        .run();
    assert_eq!(
        fs::read(destination.join("nested/src/lib.rs")).unwrap(),
        fs::read(donor.root().join("src/lib.rs")).unwrap()
    );
}

#[cargo_test]
fn worktree_add_uses_the_repository_discovered_from_the_package() {
    let enclosing = git::new("outer", |p| {
        p.no_manifest()
            .file(".gitignore", "/selected/\n")
            .file(
                "package/Cargo.toml",
                &cargo_test_support::basic_manifest("enclosing", "1.0.0"),
            )
            .file("package/src/lib.rs", "")
    });
    let (donor, repo) = git::new_repo("outer/selected", |p| {
        p.no_manifest()
            .file(
                "package/Cargo.toml",
                &cargo_test_support::basic_manifest("selected", "1.0.0"),
            )
            .file("package/src/lib.rs", "")
    });
    let expected_head = repo.head().unwrap().target();
    drop(repo);
    let package = donor.root().join("package");
    fs::rename(donor.root().join(".git"), package.join(".git")).unwrap();
    donor
        .process("git")
        .cwd(&package)
        .args(&["config", "core.worktree", "../.."])
        .run();

    let child = paths::root().join("child");
    enclosing
        .cargo("-Zohm-defaults worktree add --detach --manifest-path")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .arg(package.join("Cargo.toml"))
        .arg(&child)
        .run();
    assert_eq!(
        git2::Repository::open(&child)
            .unwrap()
            .head()
            .unwrap()
            .target(),
        expected_head
    );
}

#[cargo_test]
fn worktree_uses_manifest_repository_with_foreign_git_environment() {
    let (donor, donor_repo) = git::new_repo("donor", |p| p.file("src/lib.rs", "pub fn donor() {}"));
    let (foreign, foreign_repo) =
        git::new_repo("foreign", |p| p.file("src/lib.rs", "pub fn foreign() {}"));
    let destination = paths::root().join("recipient");
    let foreign_git = foreign_repo.path();

    foreign
        .cargo("-Zohm-defaults worktree add --detach")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .arg("--manifest-path")
        .arg(donor.root().join("Cargo.toml"))
        .arg(&destination)
        .env("GIT_DIR", foreign_git)
        .env("GIT_WORK_TREE", foreign.root())
        .env("GIT_COMMON_DIR", foreign_git)
        .env("GIT_INDEX_FILE", foreign_git.join("index"))
        .env("GIT_OBJECT_DIRECTORY", foreign_git.join("objects"))
        .env(
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            foreign_git.join("objects"),
        )
        .run();

    let recipient = git2::Repository::open(destination).unwrap();
    assert_eq!(
        recipient.head().unwrap().target(),
        donor_repo.head().unwrap().target()
    );
    assert_eq!(foreign_repo.worktrees().unwrap().len(), 0);
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
#[cfg(unix)]
fn missing_parent_components_do_not_hide_overlapping_storage() {
    let donor = git::new("donor", |p| p.file("src/lib.rs", "pub fn value() {}"));
    let alias = paths::root().join("alias");
    std::os::unix::fs::symlink(donor.root(), &alias).unwrap();
    let nested = alias.join("missing/../nested");
    let separate = paths::root().join("separate");

    for (dest, target, error) in [
        (
            &nested,
            &separate,
            "the new worktree must be outside the source worktree",
        ),
        (
            &separate,
            &nested,
            "destination target directory overlaps source storage",
        ),
    ] {
        donor
            .cargo("-Zohm-defaults worktree add --detach")
            .masquerade_as_nightly_cargo(&["ohm-defaults"])
            .arg("--target-dir")
            .arg(target)
            .arg(dest)
            .with_status(101)
            .with_stderr_contains(format!("[ERROR] {error}[..]"))
            .run();
        assert_eq!(
            git2::Repository::open(donor.root())
                .unwrap()
                .worktrees()
                .unwrap()
                .len(),
            0
        );
    }
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
    let output = seeded_cargo(&donor, "worktree add")
        .arg(paths::root().join("prepared"))
        .run();
    let expected_caches = 1 + usize::from(seed_was_imported(&output));
    assert_eq!(workspace_caches().len(), expected_caches);

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
        assert_eq!(workspace_caches().len(), expected_caches);
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
    let output = seeded_cargo(&donor, "worktree add").arg(&destination).run();
    if !seed_was_imported(&output) {
        return;
    }
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

    let output = seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .run();
    if !seed_was_imported(&output) {
        return;
    }

    let caches = workspace_caches();
    assert_eq!(caches.len(), 2);
    let seeded_cache = caches.iter().find(|path| *path != donor_cache).unwrap();
    let seeded_artifact = seeded_cache.join(artifact.strip_prefix(donor_cache).unwrap());
    assert_eq!(fs::read(&seeded_artifact).unwrap(), original_artifact);
    assert!(
        !same_file::is_same_file(&artifact, &seeded_artifact).unwrap(),
        "seeding must not hard-link mutable files between worktrees"
    );
    let seeded_incremental = incremental_for(seeded_cache);
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
    requires = "clippy-driver",
    reason = "normal Ohm defaults require clone-capable snapshot storage"
)]
fn bundled_clippy_isolation_defaults_follow_actual_snapshot_cloning() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file("src/lib.rs", "pub fn value() -> u32 { 42 }")
    });
    let clippy = PathBuf::from(paths::sysroot())
        .join("bin/clippy-driver")
        .with_extension(std::env::consts::EXE_EXTENSION);
    seeded_cargo(&donor, "build").run();
    let donor_cache = workspace_caches().pop().unwrap();
    // Ask the snapshot importer independently whether this test filesystem clones.
    // The same test exercises automatic admission on APFS/Btrfs and rejection on ext4.
    let output = seeded_cargo(&donor, "worktree add -b charlie/probe")
        .arg(paths::root().join("probe"))
        .run();
    let cloned = seed_was_imported(&output);
    seeded_cargo(&donor, "check --lib")
        .env("RUSTC_WORKSPACE_WRAPPER", &clippy)
        .run();
    assert_eq!(donor_cache.join(".ohm-clippy-v1").is_dir(), cloned);
    assert_eq!(
        donor_cache.join(".ohm-worktree-seed-deny-v7").is_file(),
        !cloned,
    );
    seeded_cargo(&donor, "check --lib -v")
        .env("RUSTC_WORKSPACE_WRAPPER", &clippy)
        .with_stderr_contains("[FRESH] foo v0.0.1 ([ROOT]/donor)")
        .run();
    assert!(
        !walkdir::WalkDir::new(paths::root())
            .into_iter()
            .map(Result::unwrap)
            .any(|entry| entry
                .file_name()
                .to_string_lossy()
                .starts_with(".ohm-clone-probe-"))
    );
}

#[cargo_test(
    nightly,
    requires = "clippy-driver",
    reason = "worktree seeds use the matching toolchain's Clippy driver and cwd remapping"
)]
fn bundled_clippy_preserves_ordinary_seeds_without_importing_lint_state() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file("clippy.toml", "too-many-arguments-threshold = 2\n")
            .file(
                "src/lib.rs",
                "pub fn sum(left: u8, right: u8) -> u8 { left + right }",
            )
            .file(
                "src/main.rs",
                "extern crate foo; fn main() { println!(\"{}\", foo::sum(1, 2)); }",
            )
    });
    let clippy = PathBuf::from(paths::sysroot())
        .join("bin/clippy-driver")
        .with_extension(std::env::consts::EXE_EXTENSION);
    let destination = paths::root().join("seeded");
    seeded_cargo(&donor, "build").run();
    let donor_cache = workspace_caches().pop().unwrap();
    seeded_cargo(&donor, "check --lib -v")
        .env("CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION", "true")
        .env("RUSTC_WORKSPACE_WRAPPER", &clippy)
        .env(
            "CLIPPY_ARGS",
            "-W__CLIPPY_HACKERY__clippy::too_many_arguments",
        )
        .with_stderr_does_not_contain("[..]this function has too many arguments[..]")
        .run();
    assert!(
        donor_cache
            .join(".ohm-clippy-v1/.ohm-worktree-seed-deny-v7")
            .is_file()
    );
    assert!(!donor_cache.join(".ohm-worktree-seed-deny-v7").exists());
    seeded_cargo(&donor, "build -v")
        .with_stderr_contains("[FRESH] foo v0.0.1 ([ROOT]/donor)")
        .with_stderr_does_not_contain("[COMPILING] foo v0.0.1 ([ROOT]/donor)")
        .run();

    let output = seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .run();
    if !seed_was_imported(&output) {
        return;
    }
    let recipient_cache = workspace_caches()
        .into_iter()
        .find(|cache| *cache != donor_cache)
        .unwrap();
    assert!(!recipient_cache.join(".ohm-clippy-v1").exists());
    let incremental = incremental_for(&recipient_cache);
    assert!(!incremental.join(".ohm-clippy-v1").exists());
    assert!(
        walkdir::WalkDir::new(&incremental)
            .into_iter()
            .map(Result::unwrap)
            .any(|entry| entry.file_name() == "query-cache.bin")
    );

    seeded_cargo(&donor, "build -v")
        .cwd(&destination)
        .with_stderr_contains("[FRESH] foo v0.0.1 ([ROOT]/seeded)")
        .with_stderr_does_not_contain("[COMPILING] foo v0.0.1 ([ROOT]/seeded)")
        .run();
    fs::write(
        destination.join("clippy.toml"),
        "too-many-arguments-threshold = 1\n",
    )
    .unwrap();
    seeded_cargo(&donor, "check --lib -v")
        .cwd(&destination)
        .env("CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION", "true")
        .env("RUSTC_WORKSPACE_WRAPPER", &clippy)
        .env(
            "CLIPPY_ARGS",
            "-W__CLIPPY_HACKERY__clippy::too_many_arguments",
        )
        .with_stderr_contains("[..]this function has too many arguments[..]")
        .run();
    fs::write(
        destination.join("src/lib.rs"),
        "pub fn sum(left: u8, right: u8) -> u8 { left + right + 1 }",
    )
    .unwrap();
    destination.join("src/lib.rs").move_into_the_past();
    seeded_cargo(&donor, "build -v")
        .cwd(&destination)
        .with_stderr_contains("[COMPILING] foo v0.0.1 ([ROOT]/seeded)")
        .run();
    donor
        .process(binary(&destination))
        .with_stdout_data("4\n")
        .run();
    donor
        .process(donor.bin("foo"))
        .with_stdout_data("3\n")
        .run();

    // Turning isolation off must restore the conservative whole-profile policy.
    // Turning it back on cannot erase an intervening opaque compilation's history.
    for isolation in ["false", "true"] {
        seeded_cargo(&donor, "check --lib")
            .env("CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION", isolation)
            .env("RUSTC_WORKSPACE_WRAPPER", &clippy)
            .run();
        assert!(donor_cache.join(".ohm-worktree-seed-deny-v7").is_file());
    }
    seeded_cargo(&donor, "worktree add -b charlie/after-disabled-clippy")
        .arg(paths::root().join("after-disabled-clippy"))
        .with_stderr_contains("[..](no compatible build snapshot seeded)")
        .run();

    let donor_incremental = incremental_for(&donor_cache);
    assert!(donor_incremental.join(".ohm-clippy-v1").is_dir());
    seeded_cargo(&donor, "clean -p foo").run();
    for root in [&donor_cache, &donor_incremental] {
        assert!(
            !walkdir::WalkDir::new(root)
                .into_iter()
                .map(Result::unwrap)
                .any(|entry| {
                    let name = entry.file_name().to_string_lossy();
                    name == "foo" || name.starts_with("foo-")
                })
        );
    }
    assert!(!donor.bin("foo").exists());
    assert!(binary(&destination).is_file());
}

#[cargo_test(
    nightly,
    requires = "clippy-driver",
    reason = "Clippy isolation overrides must survive external cargo commands"
)]
#[cfg(unix)]
fn clippy_isolation_overrides_are_inherited_and_child_flags_take_precedence() {
    use std::os::unix::fs::PermissionsExt;

    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file(
                ".cargo/config.toml",
                "[unstable]\nohm-clippy-seed-isolation = true\n",
            )
            .file("src/lib.rs", "pub fn value() {}")
    });
    let tools = paths::root().join("tools");
    fs::create_dir(&tools).unwrap();
    let external = tools.join("cargo-isolation-reinvoke");
    fs::write(
        &external,
        r#"#!/bin/sh
if [ "$OHM_TEST_CHILD_OVERRIDE" = "1" ]; then
    exec "$CARGO" -Zohm-clippy-seed-isolation=yes check --lib
fi
exec "$CARGO" check --lib
"#,
    )
    .unwrap();
    fs::set_permissions(&external, fs::Permissions::from_mode(0o755)).unwrap();
    let mut search_path = vec![tools];
    search_path.extend(std::env::split_paths(&std::env::var_os("PATH").unwrap()));
    let clippy = PathBuf::from(paths::sysroot()).join("bin/clippy-driver");
    seeded_cargo(&donor, "build").run();
    let namespace = workspace_caches().pop().unwrap();
    for child_override in ["0", "1"] {
        seeded_cargo(&donor, "-Zohm-clippy-seed-isolation=no isolation-reinvoke")
            .env("PATH", std::env::join_paths(&search_path).unwrap())
            .env("RUSTC_WORKSPACE_WRAPPER", &clippy)
            .env("OHM_TEST_CHILD_OVERRIDE", child_override)
            .run();
        assert!(namespace.join(".ohm-worktree-seed-deny-v7").is_file());
        assert_eq!(
            namespace.join(".ohm-clippy-v1").is_dir(),
            child_override == "1"
        );
    }
}

#[cargo_test(
    nightly,
    requires = "clippy-driver",
    reason = "forced Clippy isolation must not bypass compiler trust"
)]
#[cfg(unix)]
fn forced_clippy_isolation_preserves_compiler_trust_rejections() {
    use std::os::unix::fs::PermissionsExt;

    let passthrough = paths::root().join("global-wrapper");
    fs::write(&passthrough, "#!/bin/sh\nexec \"$@\"\n").unwrap();
    fs::set_permissions(&passthrough, fs::Permissions::from_mode(0o755)).unwrap();
    let clippy = PathBuf::from(paths::sysroot()).join("bin/clippy-driver");
    let mut previous = Vec::new();
    for case in ["wrapper", "logger"] {
        let donor = git::new(case, |p| {
            p.file(".gitignore", "/target\n/Cargo.lock\n")
                .file("src/lib.rs", "pub fn value() {}")
        });
        seeded_cargo(&donor, "build").run();
        let namespace = workspace_caches()
            .into_iter()
            .find(|path| !previous.contains(path))
            .unwrap();
        let mut command = seeded_cargo(&donor, "-Zohm-clippy-seed-isolation=yes check --lib");
        command.env("RUSTC_WORKSPACE_WRAPPER", &clippy);
        if case == "wrapper" {
            command.env("RUSTC_WRAPPER", &passthrough);
        } else {
            command.env("RUSTC_LOG", "warn");
        }
        command.run();
        assert!(!namespace.join(".ohm-clippy-v1").exists());
        assert!(namespace.join(".ohm-worktree-seed-deny-v7").is_file());
        previous.push(namespace);
    }
}

#[cargo_test(
    nightly,
    requires = "clippy-driver",
    reason = "opaque wrappers must keep their conservative worktree policy"
)]
#[cfg(unix)]
fn clippy_wrapper_scripts_still_deny_the_whole_seed() {
    use std::os::unix::fs::PermissionsExt;

    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file("src/lib.rs", "pub fn value() {}")
    });
    let wrapper = paths::root().join("clippy-wrapper");
    let clippy = PathBuf::from(paths::sysroot()).join("bin/clippy-driver");
    fs::write(
        &wrapper,
        format!("#!/bin/sh\nexec '{}' \"$@\"\n", clippy.display()),
    )
    .unwrap();
    fs::set_permissions(&wrapper, fs::Permissions::from_mode(0o755)).unwrap();
    seeded_cargo(&donor, "build").run();
    seeded_cargo(&donor, "check --lib")
        .env("CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION", "true")
        .env("RUSTC_WORKSPACE_WRAPPER", wrapper)
        .run();
    let cache = workspace_caches().pop().unwrap();
    assert!(cache.join(".ohm-worktree-seed-deny-v7").is_file());
    seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(paths::root().join("seeded"))
        .with_stderr_contains("[..](no compatible build snapshot seeded)")
        .run();
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
    let output = seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .run();
    if !seed_was_imported(&output) {
        return;
    }
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

    let workspaces = donor.root().join("target/debug/build/workspaces");
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
            "[..]snapshot path is not a plain directory: [ROOT]/donor/target/debug/build/workspaces",
        )
        .run();

    assert_eq!(snapshot(), before);
    assert!(destination.join(".git").is_file());
    assert!(!destination.join("target/debug").exists());
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

    let output = seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .arg("HEAD")
        .run();
    if !seed_was_imported(&output) {
        return;
    }
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
    let output = seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .arg(requested.to_string())
        .run();
    if !seed_was_imported(&output) {
        return;
    }
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
    let output = seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .arg(requested.to_string())
        .run();
    if !seed_was_imported(&output) {
        return;
    }
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
    let output = seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .run();
    if !seed_was_imported(&output) {
        return;
    }
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
        // Trusting macros must not admit unsupported Cargo-generated paths.
        .env("CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST", "all")
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
    let output = seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .run();
    if !seed_was_imported(&output) {
        return;
    }
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
    let output = seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .run();
    if !seed_was_imported(&output) {
        return;
    }

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
    let output = seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .run();
    if !seed_was_imported(&output) {
        return;
    }
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
    let output = seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .run();
    if !seed_was_imported(&output) {
        return;
    }
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
    let output = seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .arg(&destination)
        .run();
    if !seed_was_imported(&output) {
        return;
    }
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

fn local_proc_macro_project(macro_body: &str) -> Project {
    git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file(
                "Cargo.toml",
                r#"
                    [package]
                    name = "foo"
                    version = "0.0.1"
                    edition = "2024"

                    [workspace]
                    members = ["path-macro", "macro-helper"]

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

                    [dependencies]
                    macro-helper = { path = "../macro-helper" }
                "#,
            )
            .file(
                "path-macro/src/lib.rs",
                &format!(
                    r#"
                    extern crate proc_macro;

                    #[proc_macro]
                    pub fn value(_: proc_macro::TokenStream) -> proc_macro::TokenStream {{
                        {macro_body}
                    }}
                "#
                ),
            )
            .file(
                "macro-helper/Cargo.toml",
                r#"
                    [package]
                    name = "macro-helper"
                    version = "0.0.1"
                    edition = "2024"
                "#,
            )
            .file("macro-helper/src/lib.rs", "pub fn value() -> u32 { 1 }")
            .file(
                "src/main.rs",
                "fn main() { println!(\"{}\", path_macro::value!()); }",
            )
    })
}

const AMBIENT_PROC_MACRO_BODY: &str = r#"
    // Unlike env!, this runtime read does not appear in rustc's dep-info.
    let directory = std::env::var("CARGO_MANIFEST_DIR").unwrap();
    format!("{directory:?}").parse().unwrap()
"#;

#[cargo_test(
    nightly,
    reason = "worktree seeds use checksum freshness and cwd remapping"
)]
fn local_proc_macros_use_the_new_worktrees_environment() {
    let donor = local_proc_macro_project(AMBIENT_PROC_MACRO_BODY);
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
        .with_stderr_contains("[..](no compatible build snapshot seeded)")
        .run();
    assert_eq!(workspace_caches().len(), 1);
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
    reason = "worktree seeds can explicitly trust local procedural macro history"
)]
fn local_proc_macro_trust_is_selected_when_adding_a_worktree() {
    let donor = local_proc_macro_project(AMBIENT_PROC_MACRO_BODY);
    let destination = paths::root().join("seeded");

    // Preparation and subsequent builds need no opt-in: admission happens at add.
    seeded_cargo(&donor, "build").run();
    let output = seeded_cargo(&donor, "worktree add")
        .env("CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST", "all")
        .arg(&destination)
        .run();
    if !seed_was_imported(&output) {
        return;
    }
    assert_eq!(workspace_caches().len(), 2);
    seeded_cargo(&donor, "build -v")
        .cwd(&destination)
        .with_stderr_contains("[FRESH] foo v0.0.1 ([ROOT]/seeded)")
        .with_stderr_does_not_contain("[RUNNING]")
        .run();
    // This deliberately demonstrates why the opt-in is unsafe: the macro's
    // untracked environment read retains the donor's value.
    donor
        .process(binary(&destination))
        .with_stdout_data(str![[r#"
[ROOT]/donor

"#]])
        .run();

    seeded_cargo(&donor, "worktree add")
        .cwd(&destination)
        .arg(paths::root().join("strict"))
        .with_stderr_contains("[..](no compatible build snapshot seeded)")
        .run();
    assert_eq!(workspace_caches().len(), 2);

    // Removing the macro from the current graph must not erase opaque history
    // retained in old artifacts and incremental sessions.
    fs::write(
        destination.join("Cargo.toml"),
        "[package]\nname = \"foo\"\nversion = \"0.0.1\"\nedition = \"2024\"\n[workspace]\n",
    )
    .unwrap();
    fs::write(
        destination.join("src/main.rs"),
        "fn main() { println!(\"no macro\"); }",
    )
    .unwrap();
    seeded_cargo(&donor, "build").cwd(&destination).run();
    let recipient_repo = git2::Repository::open(&destination).unwrap();
    git::add(&recipient_repo);
    git::commit(&recipient_repo);
    seeded_cargo(&donor, "worktree add")
        .cwd(&destination)
        .arg(paths::root().join("strict-after-removal"))
        .with_stderr_contains("[..](no compatible build snapshot seeded)")
        .run();
    assert_eq!(workspace_caches().len(), 2);
}

#[cargo_test(
    nightly,
    reason = "trusted local macro seeds still revalidate tracked inputs"
)]
fn trusted_local_proc_macro_seeds_rebuild_changed_inputs() {
    let donor =
        local_proc_macro_project(r#"format!("{}u32", macro_helper::value()).parse().unwrap()"#);
    let destination = paths::root().join("seeded");
    seeded_cargo(&donor, "build").run();
    let output = seeded_cargo(&donor, "worktree add")
        .env("CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST", "all")
        .arg(&destination)
        .run();
    if !seed_was_imported(&output) {
        return;
    }
    seeded_cargo(&donor, "build -v")
        .cwd(&destination)
        .with_stderr_does_not_contain("[RUNNING]")
        .run();

    let changed_macro = donor
        .read_file("path-macro/src/lib.rs")
        .replace("macro_helper::value()", "macro_helper::value() + 1");
    for (path, contents, expected) in [
        (
            "src/main.rs",
            "fn main() { println!(\"source {}\", path_macro::value!()); }",
            "source 1\n",
        ),
        (
            "path-macro/src/lib.rs",
            changed_macro.as_str(),
            "source 2\n",
        ),
        (
            "macro-helper/src/lib.rs",
            "pub fn value() -> u32 { 41 }",
            "source 42\n",
        ),
    ] {
        let source = destination.join(path);
        fs::write(&source, contents).unwrap();
        source.move_into_the_past();
        seeded_cargo(&donor, "build -v")
            .cwd(&destination)
            .with_stderr_contains("[COMPILING] foo v0.0.1 ([ROOT]/seeded)")
            .run();
        donor
            .process(binary(&destination))
            .with_stdout_data(expected)
            .run();
    }
    donor
        .process(donor.bin("foo"))
        .with_stdout_data("1\n")
        .run();
}

#[cargo_test(
    nightly,
    reason = "trusting a local macro import does not change build-script invalidation"
)]
fn trusted_local_proc_macro_imports_preserve_build_script_invalidation() {
    let donor =
        local_proc_macro_project(r#"format!("{}u32", macro_helper::value()).parse().unwrap()"#);
    donor.change_file(".gitignore", "/target\n/Cargo.lock\n/script-ran\n");
    donor.change_file(
        "build.rs",
        r#"
            fn main() {
                std::fs::write("script-ran", std::env::var("SCRIPT_TRIGGER").unwrap()).unwrap();
                println!("cargo:rerun-if-env-changed=SCRIPT_TRIGGER");
            }
        "#,
    );
    let repo = git2::Repository::open(donor.root()).unwrap();
    git::add(&repo);
    git::commit(&repo);
    seeded_cargo(&donor, "build")
        .env("SCRIPT_TRIGGER", "first")
        .run();

    // Merely preparing a snapshot must preserve ordinary donor invalidation.
    // COMPILING alone would also be printed if Cargo subsequently skipped rustc.
    seeded_cargo(&donor, "build -v")
        .env("SCRIPT_TRIGGER", "second")
        .with_stderr_contains("[RUNNING] `[..]--crate-name foo [..]`")
        .run();
    assert_eq!(donor.read_file("script-ran"), "second");

    let destination = paths::root().join("seeded");
    let output = seeded_cargo(&donor, "worktree add")
        .env("CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST", "all")
        .arg(&destination)
        .run();
    if !seed_was_imported(&output) {
        return;
    }
    seeded_cargo(&donor, "build -v")
        .cwd(&destination)
        .env("SCRIPT_TRIGGER", "second")
        .with_stderr_contains("[RUNNING] `[..]--crate-name foo [..]`")
        .run();
    assert_eq!(
        fs::read_to_string(destination.join("script-ran")).unwrap(),
        "second"
    );
    donor
        .process(binary(&destination))
        .with_stdout_data("1\n")
        .run();
}

#[cargo_test(
    nightly,
    reason = "new worktree trust policies must not reinterpret old snapshot markers"
)]
fn local_proc_macro_trust_does_not_admit_legacy_snapshots() {
    let donor = git::new("donor", |p| {
        p.file(".gitignore", "/target\n/Cargo.lock\n")
            .file("src/lib.rs", "pub fn value() -> u32 { 1 }")
    });
    seeded_cargo(&donor, "build").run();
    let namespace = workspace_caches().pop().unwrap();
    fs::rename(
        namespace.join(".ohm-worktree-seed-v7"),
        namespace.join(".ohm-worktree-seed-v5"),
    )
    .unwrap();
    fs::write(
        namespace.join(".ohm-worktree-seed-deny-v5"),
        "untrusted compile-time inputs\n",
    )
    .unwrap();

    seeded_cargo(&donor, "worktree add")
        .env("CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST", "all")
        .arg(paths::root().join("legacy"))
        .with_stderr_contains("[..](no compatible build snapshot seeded)")
        .run();
    assert_eq!(workspace_caches().len(), 1);
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
    let output = seeded_cargo(&donor, "worktree add -b charlie/seeded")
        .env("CARGO_TARGET_DIR", &donor_target)
        .arg(&destination)
        .arg("--target-dir")
        .arg(&seeded_target)
        .run();
    if !seed_was_imported(&output) {
        return;
    }

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
