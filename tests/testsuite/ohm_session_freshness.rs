//! Per-unit freshness must retain ordinary check behavior across session requests.

#![cfg(unix)]

use std::fs;
use std::path::PathBuf;

use crate::ohm_session::{Session, assert_reused, change, fixture};
use crate::prelude::*;
use cargo_test_support::Project;
use serde_json::Value;

fn start(project: &Project) -> Session<'_> {
    Session::start_with_env(
        project,
        &["--message-format=json"],
        &[(
            "CARGO_LOG",
            "cargo::core::compiler::fingerprint::session=trace".into(),
        )],
    )
}

fn messages(response: &Value) -> Vec<Value> {
    response["stdout"]
        .as_str()
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect()
}

fn artifact(response: &Value, target: &str) -> Value {
    let mut artifacts = messages(response).into_iter().filter(|message| {
        message["reason"] == "compiler-artifact" && message["target"]["name"] == target
    });
    let artifact = artifacts
        .next()
        .unwrap_or_else(|| panic!("missing {target} artifact: {response}"));
    assert!(
        artifacts.next().is_none(),
        "duplicate {target} artifact: {response}"
    );
    artifact
}

fn assert_fresh(response: &Value, target: &str, fresh: bool) {
    assert_eq!(artifact(response, target)["fresh"], fresh, "{response}");
}

fn metadata_output(response: &Value, target: &str) -> PathBuf {
    artifact(response, target)["filenames"]
        .as_array()
        .unwrap()
        .iter()
        .map(|filename| PathBuf::from(filename.as_str().unwrap()))
        .find(|path| {
            path.extension()
                .is_some_and(|extension| extension == "rmeta")
        })
        .unwrap_or_else(|| panic!("missing {target} metadata output: {response}"))
}

fn warm(session: &Session<'_>, prepared: &Value, targets: &[&str]) -> Value {
    // The first fresh request can populate entries after an earlier compilation.
    assert_reused(&session.check(true), prepared);
    let response = session.check(true);
    assert_reused(&response, prepared);
    for target in targets {
        assert_fresh(&response, target, true);
        assert!(metadata_output(&response, target).is_file(), "{response}");
    }
    assert!(
        response["stderr"]
            .as_str()
            .unwrap()
            .contains("session freshness hit"),
        "the unchanged request did not reuse per-unit freshness: {response}"
    );
    response
}

fn diagnostics(response: &Value, level: &str) -> Vec<Value> {
    messages(response)
        .into_iter()
        .filter(|message| {
            message["reason"] == "compiler-message" && message["message"]["level"] == level
        })
        .map(|message| message["message"].clone())
        .collect()
}

#[cargo_test]
fn warm_freshness_rechecks_transitive_included_inputs_and_recovers() {
    let p = fixture();
    p.change_file(
        "Cargo.toml",
        &p.read_file("Cargo.toml")
            .replace("members = [\"dep\"]", "members = [\"dep\", \"leaf\"]"),
    );
    p.change_file(
        "dep/Cargo.toml",
        &format!(
            "{}\n[dependencies]\nleaf = {{ path = \"../leaf\" }}\n",
            p.read_file("dep/Cargo.toml")
        ),
    );
    p.change_file("dep/src/lib.rs", "pub use leaf::value;");
    p.change_file(
        "leaf/Cargo.toml",
        "[package]\nname = \"leaf\"\nversion = \"0.1.0\"\nedition = \"2021\"\n",
    );
    p.change_file("leaf/src/lib.rs", "include!(\"../input with spaces.rs\");");
    p.change_file("leaf/input with spaces.rs", "pub fn value() -> u32 { 1 }");
    p.cargo("generate-lockfile --offline").run();

    let session = start(&p);
    let prepared = session.check(true);
    warm(&session, &prepared, &["app", "dep", "leaf"]);

    // The root source does not change. A public type change must propagate
    // through both dependency versions and fail at the root's call site.
    change(
        &p,
        "leaf/input with spaces.rs",
        "pub fn value() -> i32 { 1 }",
    );
    let broken = session.check(false);
    assert_reused(&broken, &prepared);
    assert_fresh(&broken, "leaf", false);
    assert_fresh(&broken, "dep", false);
    assert!(
        diagnostics(&broken, "error")
            .iter()
            .any(|message| message["message"] == "mismatched types"),
        "{broken}"
    );
    let repeated = session.check(false);
    assert_reused(&repeated, &prepared);
    assert!(
        diagnostics(&repeated, "error")
            .iter()
            .any(|message| message["message"] == "mismatched types"),
        "{repeated}"
    );

    change(
        &p,
        "leaf/input with spaces.rs",
        "pub fn value() -> u32 { 2 }",
    );
    let fixed = session.check(true);
    assert_reused(&fixed, &prepared);
    assert_fresh(&fixed, "app", false);
    assert!(diagnostics(&fixed, "error").is_empty(), "{fixed}");
    warm(&session, &prepared, &["app", "dep", "leaf"]);

    fs::remove_file(p.root().join("leaf/input with spaces.rs")).unwrap();
    let missing = session.check(false);
    assert_reused(&missing, &prepared);
    assert!(
        missing["stdout"]
            .as_str()
            .unwrap()
            .contains("input with spaces.rs"),
        "{missing}"
    );
    assert!(!diagnostics(&missing, "error").is_empty(), "{missing}");
    change(
        &p,
        "leaf/input with spaces.rs",
        "pub fn value() -> u32 { 3 }",
    );
    let restored = session.check(true);
    assert_reused(&restored, &prepared);
    assert_fresh(&restored, "leaf", false);
    assert_fresh(&restored, "app", false);
    warm(&session, &prepared, &["app", "dep", "leaf"]);
}

#[cargo_test]
fn warm_freshness_rechecks_outputs_short_hashes_and_dep_info() {
    let p = fixture();
    let session = start(&p);
    let prepared = session.check(true);
    let ready = warm(&session, &prepared, &["app", "dep"]);
    let dependency_output = metadata_output(&ready, "dep");

    // An existing root output becoming older than its dependency is a dirty
    // unit, even when the source and dep-info files remain unchanged.
    filetime::set_file_mtime(
        &metadata_output(&ready, "app"),
        filetime::FileTime::from_unix_time(1, 0),
    )
    .unwrap();
    let outdated = session.check(true);
    assert_reused(&outdated, &prepared);
    assert_fresh(&outdated, "dep", true);
    assert_fresh(&outdated, "app", false);
    warm(&session, &prepared, &["app", "dep"]);

    let hash = p
        .glob("target/debug/.fingerprint/dep-*/lib-dep")
        .next()
        .unwrap()
        .unwrap();
    let original = fs::read(&hash).unwrap();
    let modified = filetime::FileTime::from_last_modification_time(&fs::metadata(&hash).unwrap());
    // An empty short hash is Cargo's interrupted-build marker. Preserve its
    // mtime so the retained unit must observe the changed file contents.
    fs::write(&hash, []).unwrap();
    filetime::set_file_mtime(&hash, modified).unwrap();
    let interrupted = session.check(true);
    assert_reused(&interrupted, &prepared);
    assert_fresh(&interrupted, "dep", false);
    // Ordinary Cargo also keeps the root fresh: the interrupted-build marker
    // changes the dependency's admission, not its computed hash or source inputs.
    assert_fresh(&interrupted, "app", true);
    assert_eq!(fs::read(&hash).unwrap(), original);
    warm(&session, &prepared, &["app", "dep"]);

    let dep_info = p
        .glob("target/debug/.fingerprint/dep-*/dep-lib-dep")
        .next()
        .unwrap()
        .unwrap();
    fs::write(&dep_info, []).unwrap();
    let invalid = session.check(true);
    assert_reused(&invalid, &prepared);
    assert_fresh(&invalid, "dep", false);
    assert_fresh(&invalid, "app", false);
    assert!(!fs::read(&dep_info).unwrap().is_empty());
    warm(&session, &prepared, &["app", "dep"]);

    fs::remove_file(&dependency_output).unwrap();
    let missing = session.check(true);
    assert_reused(&missing, &prepared);
    assert_fresh(&missing, "dep", false);
    assert_fresh(&missing, "app", false);
    assert!(dependency_output.is_file());
}

#[cargo_test]
fn warm_freshness_replays_current_diagnostics_and_json_artifacts() {
    let p = fixture();
    p.change_file(
        "src/lib.rs",
        "pub fn answer() -> u32 { let original_warning = 1; dep::value() }",
    );
    let session = start(&p);
    let prepared = session.check(true);
    let previous_warnings = diagnostics(&prepared, "warning");
    assert!(!previous_warnings.is_empty(), "{prepared}");
    let fresh = warm(&session, &prepared, &["app", "dep"]);
    assert_eq!(diagnostics(&fresh, "warning"), previous_warnings);

    change(
        &p,
        "src/lib.rs",
        "pub fn answer() -> u32 { let replacement_warning = 2; dep::value() }",
    );
    let changed = session.check(true);
    assert_reused(&changed, &prepared);
    assert_fresh(&changed, "app", false);
    let warnings = diagnostics(&changed, "warning");
    assert_ne!(warnings, previous_warnings);
    assert!(
        changed["stdout"]
            .as_str()
            .unwrap()
            .contains("replacement_warning"),
        "{changed}"
    );
    assert!(
        !changed["stdout"]
            .as_str()
            .unwrap()
            .contains("original_warning"),
        "{changed}"
    );
    let fresh = warm(&session, &prepared, &["app", "dep"]);
    assert_eq!(diagnostics(&fresh, "warning"), warnings);
    assert_eq!(
        metadata_output(&fresh, "app"),
        metadata_output(&changed, "app")
    );
}
