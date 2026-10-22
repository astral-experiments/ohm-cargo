//! Exact dependency-search arguments from the production unit traversal.

use crate::prelude::*;
use cargo::GlobalContext;
use cargo::compiler::{
    BuildRunner, CompileKind, CompileMode, CompileTarget, Lto, Unit, UnitIndex, UnitInterner,
    UserIntent, lib_search_paths,
};
use cargo::ops::{CompileOptions, create_bcx};
use cargo::util::cache_lock::CacheLockMode;
use cargo::workspace::Workspace;
use cargo::workspace::profiles::Profile;
use cargo_test_support::{paths, project, rustc_host};
use cargo_util_terminal::Shell;
use std::cmp::Ordering;
use std::collections::hash_map::DefaultHasher;
use std::ffi::OsString;
use std::hash::{Hash, Hasher};
use std::path::PathBuf;

fn copy_unit(interner: &UnitInterner, unit: &Unit, profile: Profile, dep_hash: u64) -> Unit {
    interner.intern(
        &unit.pkg,
        &unit.target,
        profile,
        unit.kind,
        unit.mode,
        unit.features.clone(),
        unit.rustflags.clone(),
        unit.rustdocflags.clone(),
        unit.links_overrides.clone(),
        unit.is_std,
        dep_hash,
        unit.artifact,
        unit.artifact_target_for_features,
        unit.skip_non_compile_time_dep,
    )
}

fn with_graph(
    new_layout: bool,
    explicit_target: bool,
    duplicate_leaf: bool,
    check: impl FnOnce(&BuildRunner<'_, '_>, &Unit, Option<&Unit>, &UnitInterner),
) {
    let p = project()
        .file(
            "Cargo.toml",
            r#"
            [package]
            name = "app"
            version = "0.1.0"
            edition = "2021"

            [dependencies]
            a = { path = "a" }
            b = { path = "b" }
            derive = { path = "derive" }

            [build-dependencies]
            build-only = { path = "build-only" }

            [workspace]
            resolver = "2"
            "#,
        )
        .file("src/lib.rs", "")
        .file("build.rs", "fn main() {}")
        .file(
            "a/Cargo.toml",
            "[package]\nname = 'a'\nversion = '0.1.0'\n[dependencies]\nshared = { path = '../shared' }\n",
        )
        .file("a/src/lib.rs", "")
        .file(
            "b/Cargo.toml",
            "[package]\nname = 'b'\nversion = '0.1.0'\n[dependencies]\nshared = { path = '../shared' }\n",
        )
        .file("b/src/lib.rs", "")
        .file(
            "derive/Cargo.toml",
            "[package]\nname = 'derive'\nversion = '0.1.0'\n[lib]\nproc-macro = true\n[dependencies]\nmacro-only = { path = '../macro-only' }\n",
        )
        .file("derive/src/lib.rs", "")
        .file(
            "shared/Cargo.toml",
            "[package]\nname = 'shared'\nversion = '0.1.0'\n",
        )
        .file("shared/src/lib.rs", "")
        .file(
            "macro-only/Cargo.toml",
            "[package]\nname = 'macro-only'\nversion = '0.1.0'\n",
        )
        .file("macro-only/src/lib.rs", "")
        .file(
            "build-only/Cargo.toml",
            "[package]\nname = 'build-only'\nversion = '0.1.0'\n",
        )
        .file("build-only/src/lib.rs", "")
        .build();

    let mut gctx = GlobalContext::new(Shell::new(), p.root(), paths::cargo_home());
    gctx.nightly_features_allowed = true;
    let mut unstable = vec!["ohm-defaults=no".to_owned()];
    if new_layout {
        unstable.push("build-dir-new-layout".to_owned());
    }
    gctx.configure(0, false, None, false, false, true, &None, &unstable, &[])
        .unwrap();
    let ws = Workspace::new(&p.root().join("Cargo.toml"), &gctx).unwrap();
    let mut options = CompileOptions::new(&gctx, UserIntent::Build).unwrap();
    if explicit_target {
        options.build_config.requested_kinds = vec![CompileKind::Target(
            CompileTarget::new(rustc_host(), false).unwrap(),
        )];
    }
    let interner = UnitInterner::new();
    let mut bcx = create_bcx(&ws, &options, &interner, None).unwrap();
    let root = bcx
        .roots
        .iter()
        .find(|unit| unit.pkg.name().as_str() == "app" && unit.target.is_lib())
        .unwrap()
        .clone();
    assert_eq!(!root.kind.is_host(), explicit_target);

    let alias = duplicate_leaf.then(|| {
        let shared = bcx
            .unit_graph
            .keys()
            .find(|unit| unit.pkg.name().as_str() == "shared")
            .unwrap()
            .clone();
        assert!(bcx.unit_graph[&shared].is_empty());
        // Two interned units can have different graph identities but the same
        // directory. Keep this case explicit: search paths are a multiset.
        let alias = copy_unit(
            &interner,
            &shared,
            shared.profile.clone(),
            shared.dep_hash.wrapping_add(1),
        );
        assert_ne!(alias, shared);
        assert_ne!(alias.cmp(&shared), Ordering::Equal);
        let mut edge = bcx
            .unit_graph
            .values()
            .flatten()
            .find(|dep| dep.unit == shared)
            .unwrap()
            .clone();
        edge.unit = alias.clone();
        let index = UnitIndex(bcx.unit_to_index.len() as u64);
        assert!(bcx.unit_to_index.insert(alias.clone(), index).is_none());
        assert!(bcx.unit_graph.insert(alias.clone(), Vec::new()).is_none());
        bcx.unit_graph.get_mut(&root).unwrap().push(edge);
        alias
    });

    let _lock = gctx
        .acquire_package_cache_lock(CacheLockMode::Shared)
        .unwrap();
    let mut runner = BuildRunner::new(&bcx).unwrap();
    // These fixtures use the default dev profile without LTO. Initialize the
    // same metadata prerequisite as BuildRunner::dry_run without consuming it.
    runner.lto = bcx
        .unit_graph
        .keys()
        .map(|unit| {
            assert_eq!(
                unit.profile.lto,
                cargo::workspace::profiles::Lto::Bool(false)
            );
            (unit.clone(), Lto::OnlyObject)
        })
        .collect();
    runner.prepare_units().unwrap();
    check(&runner, &root, alias.as_ref(), &interner);
}

fn library_unit(runner: &BuildRunner<'_, '_>, name: &str) -> Unit {
    let units: Vec<_> = runner
        .bcx
        .unit_graph
        .keys()
        .filter(|unit| unit.pkg.name().as_str() == name && unit.target.is_lib())
        .cloned()
        .collect();
    assert_eq!(units.len(), 1, "expected exactly one {name} library unit");
    units.into_iter().next().unwrap()
}

fn dependency_args(paths: impl IntoIterator<Item = PathBuf>) -> Vec<OsString> {
    paths
        .into_iter()
        .flat_map(|path| {
            let mut value = OsString::from("dependency=");
            value.push(path);
            [OsString::from("-L"), value]
        })
        .collect()
}

fn root_dependency_paths(runner: &BuildRunner<'_, '_>) -> Vec<PathBuf> {
    // The shared leaf occurs once despite the diamond. Neither a custom-build
    // unit nor its dependencies nor the proc macro's private dependency occurs.
    let mut paths: Vec<_> = ["a", "b", "derive", "shared"]
        .into_iter()
        .map(|name| runner.files().deps_dir(&library_unit(runner, name)))
        .collect();
    paths.sort_unstable();
    paths
}

#[cargo_test]
fn new_layout_sorts_paths_and_respects_traversal_boundaries() {
    with_graph(true, false, false, |runner, root, _, _| {
        let expected = dependency_args(root_dependency_paths(runner));
        assert_eq!(lib_search_paths(runner, root).unwrap(), expected);

        let shared = library_unit(runner, "shared");
        for name in ["a", "b"] {
            assert_eq!(
                lib_search_paths(runner, &library_unit(runner, name)).unwrap(),
                dependency_args([runner.files().deps_dir(&shared)])
            );
        }

        let derive = library_unit(runner, "derive");
        let macro_only = library_unit(runner, "macro-only");
        assert_eq!(
            lib_search_paths(runner, &derive).unwrap(),
            dependency_args([runner.files().deps_dir(&macro_only)])
        );
        let build = runner
            .bcx
            .unit_graph
            .keys()
            .find(|unit| unit.target.is_custom_build() && unit.mode == CompileMode::Build)
            .unwrap();
        let build_only = library_unit(runner, "build-only");
        assert_eq!(
            lib_search_paths(runner, build).unwrap(),
            dependency_args([runner.files().deps_dir(&build_only)])
        );
    });
}

#[cargo_test]
fn new_layout_preserves_duplicate_paths_for_distinct_units() {
    with_graph(true, false, true, |runner, root, alias, _| {
        let alias = alias.unwrap();
        let shared = runner
            .bcx
            .unit_graph
            .keys()
            .find(|unit| unit.pkg.name().as_str() == "shared" && *unit != alias)
            .unwrap();
        let shared_path = runner.files().deps_dir(shared);
        assert_eq!(runner.files().deps_dir(alias), shared_path);
        let mut paths: Vec<_> = ["a", "b", "derive"]
            .into_iter()
            .map(|name| runner.files().deps_dir(&library_unit(runner, name)))
            .chain([shared_path.clone(), shared_path])
            .collect();
        paths.sort_unstable();
        assert_eq!(
            lib_search_paths(runner, root).unwrap(),
            dependency_args(paths)
        );
    });
}

#[cargo_test]
fn explicit_target_appends_host_path_after_sorted_dependencies() {
    with_graph(true, true, false, |runner, root, _, _| {
        let mut expected = dependency_args(root_dependency_paths(runner));
        expected.extend(dependency_args([runner.files().host_deps(root)]));
        assert_eq!(lib_search_paths(runner, root).unwrap(), expected);
    });
}

#[cargo_test]
fn old_layout_keeps_its_single_directory_and_host_append() {
    for explicit_target in [false, true] {
        with_graph(false, explicit_target, false, |runner, root, _, _| {
            let mut expected = dependency_args([runner.files().deps_dir(root)]);
            if explicit_target {
                expected.extend(dependency_args([runner.files().host_deps(root)]));
            }
            assert_eq!(lib_search_paths(runner, root).unwrap(), expected);
        });
    }
}

#[cargo_test]
fn graph_units_share_the_interner_identity_used_by_hashing() {
    with_graph(true, false, false, |runner, root, _, interner| {
        let hash = |unit: &Unit| {
            let mut hasher = DefaultHasher::new();
            unit.hash(&mut hasher);
            hasher.finish()
        };
        for left in runner.bcx.unit_graph.keys() {
            for right in runner.bcx.unit_graph.keys() {
                assert_eq!(left.cmp(right) == Ordering::Equal, left == right);
                if left == right {
                    assert_eq!(hash(left), hash(right));
                }
            }
        }
        let copy = copy_unit(interner, root, root.profile.clone(), root.dep_hash);
        assert_eq!(copy, *root);
        assert_eq!(copy.cmp(root), Ordering::Equal);
        assert_eq!(hash(&copy), hash(root));

        // Profile names are not part of interning equality. Canonicalization
        // happens before the graph is handed to the search-path traversal.
        let mut profile = root.profile.clone();
        profile.name = "another-name".into();
        assert_eq!(copy_unit(interner, root, profile, root.dep_hash), *root);

        // This equivalence is deliberately scoped to one build's interner.
        // Separate build attempts must not mix their Units into one graph.
        let other = UnitInterner::new();
        let independent = copy_unit(&other, root, root.profile.clone(), root.dep_hash);
        assert_ne!(independent, *root);
        assert_eq!(independent.cmp(root), Ordering::Equal);
    });
}
