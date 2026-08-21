use std::collections::BTreeSet;
use std::hash::{Hash, Hasher};
use std::path::PathBuf;

use cargo_util::paths;
use rustc_hash::FxHashMap as HashMap;

use crate::core::{Resolve, Workspace};
use crate::ops::lockfile;
use crate::util::{CargoResult, ConfigValue, Rustc, StableHasher};

const CACHE_FILE_NAME: &str = ".cargo-resolve-cache-v1";

/// Returns whether an earlier complete workspace resolution has identical inputs.
pub(super) fn cached_workspace_resolve_is_fresh(
    workspace: &Workspace<'_>,
    previous: &Resolve,
    rustc: &Rustc,
    lockfile_contents: &str,
) -> bool {
    let Ok(cached_fingerprint) = paths::read(&cache_path(workspace)) else {
        return false;
    };

    workspace_resolve_fingerprint(workspace, previous, rustc, lockfile_contents)
        .is_ok_and(|fingerprint| cached_fingerprint.trim() == format!("{fingerprint:016x}"))
}

/// Records the inputs that produced a complete workspace resolution.
pub(super) fn mark_workspace_resolve_fresh(
    workspace: &Workspace<'_>,
    resolve: &Resolve,
    rustc: &Rustc,
) -> CargoResult<()> {
    lockfile::with_pkg_lockfile(workspace, |lockfile_contents, _path| {
        if !lockfile::lockfile_matches_resolve(lockfile_contents, resolve) {
            return Ok(());
        }

        let fingerprint =
            workspace_resolve_fingerprint(workspace, resolve, rustc, lockfile_contents)?;
        let cache_path = cache_path(workspace);
        if let Some(parent) = cache_path.parent() {
            paths::create_dir_all(parent)?;
        }

        paths::write_atomic(cache_path, format!("{fingerprint:016x}"))?;
        Ok(())
    })?;
    Ok(())
}

fn cache_path(workspace: &Workspace<'_>) -> PathBuf {
    workspace
        .target_dir()
        .as_path_unlocked()
        .join(CACHE_FILE_NAME)
}

fn workspace_resolve_fingerprint(
    workspace: &Workspace<'_>,
    previous: &Resolve,
    rustc: &Rustc,
    lockfile_contents: &str,
) -> CargoResult<u64> {
    let mut hasher = StableHasher::new();
    env!("CARGO_PKG_VERSION").hash(&mut hasher);
    option_env!("CARGO_COMMIT_HASH").hash(&mut hasher);
    rustc.version.hash(&mut hasher);
    rustc.commit_hash.hash(&mut hasher);
    rustc.host.hash(&mut hasher);
    format!("{:?}", workspace.gctx().cli_unstable()).hash(&mut hasher);
    workspace.resolve_honors_rust_version().hash(&mut hasher);
    format!("{:?}", workspace.resolve_feature_unification()).hash(&mut hasher);
    format!("{:?}", workspace.resolve_publish_time()).hash(&mut hasher);

    let mut manifests = BTreeSet::new();
    manifests.insert(workspace.root_manifest().to_path_buf());
    manifests.extend(
        workspace
            .members()
            .map(|package| package.manifest_path().to_path_buf()),
    );
    manifests.extend(previous.iter().filter_map(|package_id| {
        let path = package_id.source_id().local_path()?;
        Some(if path.is_file() {
            path
        } else {
            path.join("Cargo.toml")
        })
    }));

    manifests.len().hash(&mut hasher);
    for manifest in manifests {
        manifest.hash(&mut hasher);

        if manifest == workspace.root_manifest() {
            let Some(contents) = workspace.root_maybe().contents() else {
                anyhow::bail!(
                    "workspace manifest `{}` has no in-memory contents",
                    manifest.display()
                );
            };
            contents.as_bytes().hash(&mut hasher);
        } else {
            let package = workspace.load(&manifest)?;
            let Some(contents) = package.manifest().contents() else {
                anyhow::bail!(
                    "package manifest `{}` has no in-memory contents",
                    manifest.display()
                );
            };
            contents.as_bytes().hash(&mut hasher);
        }
    }

    let lockfile = workspace.lock_root().as_path_unlocked().join("Cargo.lock");
    lockfile.hash(&mut hasher);
    lockfile_contents.as_bytes().hash(&mut hasher);

    hash_config_table(workspace.gctx().values()?, &mut hasher);

    let mut environment: Vec<_> = workspace
        .gctx()
        .env()
        .filter(|(key, _)| key.starts_with("CARGO_") || key.starts_with("RUST"))
        .collect();
    environment.sort_unstable_by_key(|(key, _)| *key);
    environment.len().hash(&mut hasher);
    for (key, value) in environment {
        key.hash(&mut hasher);
        value.hash(&mut hasher);
    }

    Ok(Hasher::finish(&hasher))
}

fn hash_config_table(values: &HashMap<String, ConfigValue>, hasher: &mut StableHasher) {
    let mut entries: Vec<_> = values.iter().collect();
    entries.sort_unstable_by_key(|(key, _)| *key);
    entries.len().hash(hasher);
    for (key, value) in entries {
        key.hash(hasher);
        hash_config_value(value, hasher);
    }
}

fn hash_config_value(value: &ConfigValue, hasher: &mut StableHasher) {
    value.definition().to_string().hash(hasher);

    match value {
        ConfigValue::Integer(value, _) => {
            0_u8.hash(hasher);
            value.hash(hasher);
        }
        ConfigValue::String(value, _) => {
            1_u8.hash(hasher);
            value.hash(hasher);
        }
        ConfigValue::List(values, _) => {
            2_u8.hash(hasher);
            values.len().hash(hasher);
            for value in values {
                hash_config_value(value, hasher);
            }
        }
        ConfigValue::Table(values, _) => {
            3_u8.hash(hasher);
            hash_config_table(values, hasher);
        }
        ConfigValue::Boolean(value, _) => {
            4_u8.hash(hasher);
            value.hash(hasher);
        }
    }
}
