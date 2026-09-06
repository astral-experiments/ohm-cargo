//! Source cache inputs consumed by retained Cargo preparation.

#![cfg(unix)]

use std::fs;
use std::path::PathBuf;

use crate::prelude::*;
use cargo_test_support::registry::{Package, RegistryBuilder};
use cargo_test_support::{Project, basic_manifest, git, paths};
use serde_json::Value;

use super::ohm_session::{Session, assert_reused, fixture};

fn dependency(p: &Project, declaration: &str) {
    let manifest = fs::read_to_string(p.root().join("Cargo.toml")).unwrap();
    p.change_file(
        "Cargo.toml",
        &manifest.replace("[dependencies]", &format!("[dependencies]\n{declaration}")),
    );
}

fn cached_path(pattern: &str) -> PathBuf {
    let pattern = paths::cargo_home().join(pattern);
    let mut paths = glob::glob(pattern.to_str().unwrap()).unwrap();
    let path = paths.next().unwrap().unwrap();
    assert!(paths.next().is_none(), "ambiguous cache path {pattern:?}");
    path
}

fn assert_reprepared(response: &Value, previous: &Value) {
    assert_eq!(response["reused"], false, "{response}");
    assert!(
        response["preparations"].as_u64().unwrap() > previous["preparations"].as_u64().unwrap(),
        "{response}"
    );
}

#[cargo_test]
fn sparse_registry_cache_and_archive_removal_invalidate_preparation() {
    let _registry = RegistryBuilder::new().http_index().build();
    Package::new("registry_dep", "1.0.0").publish();
    let p = fixture();
    dependency(&p, "registry_dep = \"1\"");
    p.cargo("check -p app --lib").run();
    let session = Session::start(&p, &[]);
    let first = session.check(true);
    assert_reused(&session.check(true), &first);

    let index = cached_path("registry/index/*/.cache/re/gi/registry_dep");
    let bytes = fs::read(&index).unwrap();
    fs::remove_file(&index).unwrap();
    let missing = session.check(false);
    assert_reprepared(&missing, &first);
    p.cargo("check --offline -p app --lib")
        .with_status(101)
        .with_stderr_contains("[ERROR] no matching package named `registry_dep` found")
        .run();
    fs::write(&index, bytes).unwrap();
    let restored = session.check(true);
    assert_reused(&session.check(true), &restored);

    let archive = cached_path("registry/cache/*/registry_dep-1.0.0.crate");
    let bytes = fs::read(&archive).unwrap();
    fs::remove_file(&archive).unwrap();
    let missing = session.check(false);
    assert_reprepared(&missing, &restored);
    p.cargo("check --offline -p app --lib")
        .with_status(101)
        .with_stderr_contains("  attempting to make an HTTP request, but --offline was specified")
        .run();
    fs::write(&archive, bytes).unwrap();
    let restored = session.check(true);
    assert_reused(&session.check(true), &restored);
}

#[cargo_test]
fn sparse_registry_configuration_manifests_and_extraction_markers_are_inputs() {
    let _registry = RegistryBuilder::new().http_index().build();
    Package::new("registry_dep", "1.0.0").publish();
    let p = fixture();
    dependency(&p, "registry_dep = \"1\"");
    p.cargo("check -p app --lib").run();
    let session = Session::start(&p, &[]);
    let first = session.check(true);
    assert_reused(&session.check(true), &first);

    let config = cached_path("registry/index/*/config.json");
    let mut bytes = fs::read(&config).unwrap();
    bytes.push(b'\n');
    fs::write(&config, bytes).unwrap();
    let configured = session.check(true);
    assert_reprepared(&configured, &first);
    assert_reused(&session.check(true), &configured);

    let manifest = cached_path("registry/src/*/registry_dep-1.0.0/Cargo.toml");
    let bytes = fs::read(&manifest).unwrap();
    fs::write(&manifest, "invalid manifest").unwrap();
    let invalid = session.check(false);
    assert_reprepared(&invalid, &configured);
    p.cargo("check --offline -p app --lib")
        .with_status(101)
        .with_stderr_contains("[ERROR] key with no value, expected `=`")
        .run();
    fs::write(&manifest, bytes).unwrap();
    let restored = session.check(true);
    assert_reused(&session.check(true), &restored);

    fs::remove_file(manifest.parent().unwrap().join(".cargo-ok")).unwrap();
    let unpacked = session.check(true);
    assert_reprepared(&unpacked, &restored);
    assert_reused(&session.check(true), &unpacked);
}

#[cargo_test]
fn local_registry_reuses_preparation_and_tracks_its_raw_index() {
    Package::new("registry_dep", "1.0.0").local(true).publish();
    let p = fixture();
    dependency(&p, "registry_dep = \"1\"");
    fs::create_dir_all(p.root().join(".cargo")).unwrap();
    p.change_file(
        ".cargo/config.toml",
        &format!(
            "[source.crates-io]\nreplace-with = 'local'\n[source.local]\nlocal-registry = '{}'\n",
            cargo_test_support::registry::registry_path().display()
        ),
    );
    p.cargo("check --offline -p app --lib").run();
    let session = Session::start(&p, &[]);
    let first = session.check(true);
    assert_reused(&session.check(true), &first);

    let index = cargo_test_support::registry::registry_path().join("index/re/gi/registry_dep");
    let bytes = fs::read(&index).unwrap();
    fs::remove_file(&index).unwrap();
    let missing = session.check(false);
    assert_reprepared(&missing, &first);
    p.cargo("check --offline -p app --lib")
        .with_status(101)
        .with_stderr_contains("[ERROR] no matching package named `registry_dep` found")
        .run();
    fs::write(&index, bytes).unwrap();
    let restored = session.check(true);
    assert_reused(&session.check(true), &restored);
}

#[cargo_test]
fn locked_git_sources_track_checkout_head_and_manifests() {
    let git_dep = git::new("git_dep", |project| {
        project
            .file("Cargo.toml", &basic_manifest("git_dep", "1.0.0"))
            .file("src/lib.rs", "pub fn value() {}")
    });
    let p = fixture();
    dependency(&p, &format!("git_dep = {{ git = '{}' }}", git_dep.url()));
    p.cargo("check -p app --lib").run();
    let session = Session::start(&p, &[]);
    let first = session.check(true);
    assert_reused(&session.check(true), &first);

    let manifest = cached_path("git/checkouts/git_dep-*/*/Cargo.toml");
    let bytes = fs::read(&manifest).unwrap();
    fs::write(&manifest, "invalid manifest").unwrap();
    let invalid = session.check(false);
    assert_reprepared(&invalid, &first);
    p.cargo("check --offline -p app --lib")
        .with_status(101)
        .with_stderr_contains("[ERROR] key with no value, expected `=`")
        .run();
    fs::write(&manifest, bytes).unwrap();
    let restored = session.check(true);
    assert_reused(&session.check(true), &restored);

    // Ordinary Cargo repairs a checkout whose HEAD no longer matches Cargo.lock.
    // The retained graph must make that same decision even if manifests match.
    let checkout = manifest.parent().unwrap();
    let repo = git2::Repository::open(checkout).unwrap();
    repo.set_head("refs/heads/nonexistent").unwrap();
    drop(repo);
    let repaired = session.check(true);
    assert_reprepared(&repaired, &restored);
    assert_reused(&session.check(true), &repaired);
}

#[cargo_test]
fn git_worktree_configuration_invalidates_the_checkout_repair_decision() {
    let git_dep = git::new("git_dep", |project| {
        project
            .file("Cargo.toml", &basic_manifest("git_dep", "1.0.0"))
            .file("src/lib.rs", "pub fn value() {}")
    });
    let p = fixture();
    dependency(&p, &format!("git_dep = {{ git = '{}' }}", git_dep.url()));
    p.cargo("check -p app --lib").run();
    let session = Session::start(&p, &[]);
    let first = session.check(true);
    assert_reused(&session.check(true), &first);

    let manifest = cached_path("git/checkouts/git_dep-*/*/Cargo.toml");
    let checkout = manifest.parent().unwrap();
    let other_worktree = paths::root().join("other-worktree");
    fs::create_dir(&other_worktree).unwrap();
    let invalidate_checkout = || {
        // HEAD stays at the locked revision, but Cargo must now look for its
        // completion marker under the worktree selected by Git's configuration.
        let repo = git2::Repository::open(checkout).unwrap();
        repo.config()
            .unwrap()
            .set_str("core.worktree", other_worktree.to_str().unwrap())
            .unwrap();
        fs::write(
            checkout.join("src/lib.rs"),
            "compile_error!(\"checkout was not repaired\");",
        )
        .unwrap();
        p.cargo("clean").run();
    };
    invalidate_checkout();
    p.cargo("check --offline -p app --lib").run();
    invalidate_checkout();
    let repaired = session.check(true);
    assert_reprepared(&repaired, &first);
    assert_reused(&session.check(true), &repaired);
}
