use std::collections::BTreeSet;
use std::hash::{Hash, Hasher};
use std::path::PathBuf;

use cargo_util::paths;
use rustc_hash::FxHashMap as HashMap;

use crate::ops::lockfile;
use crate::resolver::Resolve;
use crate::util::{CargoResult, ConfigValue, Rustc, StableHasher};
use crate::workspace::Workspace;

const CACHE_FILE_NAME: &str = ".cargo-resolve-cache-v1";

/// Returns whether an earlier complete workspace resolution has identical inputs.
pub(super) fn cached_workspace_resolve_is_fresh(
    workspace: &Workspace<'_>,
    previous: &Resolve,
    rustc: &Rustc,
    lockfile_contents: &str,
) -> bool {
    let Ok(cached_fingerprint) = paths::read_regular_bounded(&cache_path(workspace), 64) else {
        return false;
    };

    workspace_resolve_fingerprint(workspace, previous, rustc, lockfile_contents).is_ok_and(
        |fingerprint| cached_fingerprint.trim_ascii() == format!("{fingerprint:016x}").as_bytes(),
    )
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
            paths::create_dir_all_excluded_from_backups_atomic(parent)?;
        }

        paths::write_atomic_no_follow(cache_path, format!("{fingerprint:016x}"))?;
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
            let inputs = workspace
                .root_maybe()
                .document()
                .map(|document| {
                    let contents = before_trailing_profiles(contents, document).unwrap_or(contents);
                    before_trailing_workspace_lints(contents, document).unwrap_or(contents)
                })
                .unwrap_or(contents);
            inputs.as_bytes().hash(&mut hasher);
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
        .filter(|(key, _)| environment_affects_workspace_resolution(key))
        .collect();
    environment.sort_unstable_by_key(|(key, _)| *key);
    environment.len().hash(&mut hasher);
    for (key, value) in environment {
        key.hash(&mut hasher);
        value.hash(&mut hasher);
    }

    Ok(Hasher::finish(&hasher))
}

/// Profiles are applied to the resolved packages. Ignore a trailing profile section only
/// when the parsed header belongs to the root table and the entire suffix contains profiles.
fn before_trailing_profiles<'a>(
    contents: &'a str,
    document: &toml::Spanned<toml::de::DeTable<'_>>,
) -> Option<&'a str> {
    let (key, _) = document.get_ref().get_key_value("profile")?;
    let start = key.span().start.checked_sub(1)?;
    let (before, table) = trailing_table(contents, start, "[profile.")?;
    (table.len() == 1 && table.contains_key("profile")).then_some(before)
}

/// Rust and Clippy lint settings affect compiler invocations after dependency resolution.
fn before_trailing_workspace_lints<'a>(
    contents: &'a str,
    document: &toml::Spanned<toml::de::DeTable<'_>>,
) -> Option<&'a str> {
    let workspace = document.get_ref().get("workspace")?.get_ref().as_table()?;
    let (key, _) = workspace.get_key_value("lints")?;
    let start = key.span().start.checked_sub("[workspace.".len())?;
    let (before, table) = trailing_table(contents, start, "[workspace.lints.")?;
    let workspace = table.get("workspace")?.get_ref().as_table()?;
    let lints = workspace.get("lints")?.get_ref().as_table()?;
    (table.len() == 1
        && workspace.len() == 1
        && lints
            .keys()
            .all(|tool| matches!(tool.get_ref().as_ref(), "rust" | "clippy")))
    .then_some(before)
}

/// Parses a complete manifest suffix beginning with the expected unindented table header.
fn trailing_table<'a>(
    contents: &'a str,
    start: usize,
    header: &str,
) -> Option<(&'a str, toml::de::DeTable<'a>)> {
    let (before, suffix) = contents.split_at_checked(start)?;
    if !(before.is_empty() || before.ends_with('\n')) || !suffix.starts_with(header) {
        return None;
    }
    Some((before, toml::de::DeTable::parse(suffix).ok()?.into_inner()))
}

/// Excludes execution and presentation settings that cannot affect dependency resolution.
fn environment_affects_workspace_resolution(name: &str) -> bool {
    (name.starts_with("CARGO_") || name.starts_with("RUST"))
        && !matches!(
            name,
            "RUST_MIN_STACK"
                | "CARGO_BUILD_JOBS"
                | "CARGO_TERM_COLOR"
                | "CARGO_TERM_VERBOSE"
                | "CARGO_TERM_QUIET"
        )
        && !name.starts_with("CARGO_TERM_PROGRESS_")
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

#[cfg(test)]
mod tests {
    use super::{
        before_trailing_profiles, before_trailing_workspace_lints,
        environment_affects_workspace_resolution,
    };

    #[test]
    fn trailing_workspace_lints_preserve_dependency_and_cargo_settings() {
        let prefix = "[workspace]\nmembers = ['member']\n";
        let rust = "[workspace.lints.rust]\nunused_variables = 'deny'\n";
        for (suffix, expected) in [
            (rust.to_owned(), Some(prefix)),
            (
                format!("{rust}[workspace.lints.clippy]\npedantic = 'allow'\n"),
                Some(prefix),
            ),
            (format!("{rust}[workspace.dependencies]\ndep = '1'\n"), None),
            (
                format!("{rust}[workspace.lints.cargo]\nunused_features = 'warn'\n"),
                None,
            ),
            (
                format!("{rust}[patch.crates-io]\ndep = {{ path = 'local' }}\n"),
                None,
            ),
        ] {
            let contents = format!("{prefix}{suffix}");
            let document = toml::de::DeTable::parse(&contents).unwrap();
            assert_eq!(
                before_trailing_workspace_lints(&contents, &document),
                expected
            );
        }
    }

    #[test]
    fn trailing_profile_tables_preserve_the_other_manifest_inputs() {
        let prefix = "[package]\ndescription = '''\n[profile.example]\n'''\n";
        let profile = "[profile.dev]\nopt-level = 1\n";
        for (contents, expected) in [
            (format!("{prefix}{profile}"), Some(prefix)),
            (prefix.to_owned(), None),
            (
                format!("{prefix}{profile}[dependencies]\ndep = '1'\n"),
                None,
            ),
            (format!("{prefix}['profile'.dev]\nopt-level = 1\n"), None),
        ] {
            let document = toml::de::DeTable::parse(&contents).unwrap();
            assert_eq!(before_trailing_profiles(&contents, &document), expected);
        }
    }

    #[test]
    fn execution_only_environment_does_not_affect_workspace_resolution() {
        for name in [
            "RUST_MIN_STACK",
            "CARGO_BUILD_JOBS",
            "CARGO_TERM_COLOR",
            "CARGO_TERM_VERBOSE",
            "CARGO_TERM_QUIET",
            "CARGO_TERM_PROGRESS_WHEN",
            "CARGO_TERM_PROGRESS_WIDTH",
        ] {
            assert!(
                !environment_affects_workspace_resolution(name),
                "execution-only setting {name} should not invalidate the resolver"
            );
        }
    }

    #[test]
    fn resolution_relevant_environment_remains_in_workspace_fingerprint() {
        for name in [
            "CARGO_BUILD_TARGET",
            "CARGO_BUILD_RUSTFLAGS",
            "CARGO_REGISTRIES_CRATES_IO_PROTOCOL",
            "CARGO_REGISTRY_DEFAULT",
            "CARGO_TARGET_AARCH64_APPLE_DARWIN_RUSTFLAGS",
            "CARGO_UNSTABLE_BUILD_STD",
            "CARGO_EXPERIMENTAL_RESOLVE_CACHE",
            "RUSTFLAGS",
            "RUSTC",
            "RUSTC_WRAPPER",
            "RUSTC_WORKSPACE_WRAPPER",
            "RUSTUP_TOOLCHAIN",
        ] {
            assert!(
                environment_affects_workspace_resolution(name),
                "potential resolver input {name} must stay in the fingerprint"
            );
        }
    }
}
