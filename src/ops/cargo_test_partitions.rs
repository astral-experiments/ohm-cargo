use std::collections::BTreeMap;
use std::path::{Component, PathBuf};

use anyhow::{Context as _, bail};
use serde::Deserialize;

use crate::compiler::{CompileMode, Unit, UnitInterner};
use crate::ops::{CompileFilter, CompileOptions, FilterRule, LibRule, Packages};
use crate::util::CargoResult;
use crate::util::restricted_names::is_glob_pattern;
use crate::workspace::{PackageId, Workspace};

/// A manifest-declared integration-test root, selected independently of its artifact identity.
#[derive(Clone, Debug)]
pub struct TestPartition {
    package: PackageId,
    target: String,
    group: String,
    relative_path: PathBuf,
    source: PathBuf,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Declaration {
    path: PathBuf,
    prefixes: Vec<String>,
}

/// Selects a declared partition only for a single, exact integration-test invocation.
pub fn configure_test_partition(
    ws: &Workspace<'_>,
    options: &mut CompileOptions,
    test_args: &[&str],
    no_run: bool,
) -> CargoResult<()> {
    let unstable = ws.gctx().cli_unstable();
    if !unstable.ohm_test_partitions {
        return Ok(());
    }
    if unstable.ohm_focused_tests {
        bail!("cannot combine `-Zohm-test-partitions` with `-Zohm-focused-tests`");
    }
    let [test_name, "--exact"] = test_args else {
        return Ok(());
    };
    if no_run
        || options.target_rustc_args.is_some()
        || options.build_config.requested_kinds.len() != 1
        || options.build_config.unit_graph
        || !matches!(&options.spec, Packages::Packages(packages) if packages.len() == 1)
    {
        return Ok(());
    }
    let CompileFilter::Only {
        all_targets: false,
        lib: LibRule::False,
        bins: FilterRule::Just(bins),
        examples: FilterRule::Just(examples),
        tests: FilterRule::Just(tests),
        benches: FilterRule::Just(benches),
    } = &options.filter
    else {
        return Ok(());
    };
    let [target_name] = tests.as_slice() else {
        return Ok(());
    };
    if !bins.is_empty()
        || !examples.is_empty()
        || !benches.is_empty()
        || is_glob_pattern(target_name)
    {
        return Ok(());
    }
    let packages = options.spec.get_packages(ws)?;
    let [package] = packages.as_slice() else {
        return Ok(());
    };
    let Some(target) = package
        .targets()
        .iter()
        .find(|target| target.is_test() && target.name() == target_name && target.harness())
    else {
        return Ok(());
    };
    let Some(partitions) = package
        .manifest()
        .custom_metadata()
        .and_then(|metadata| metadata.get("ohm"))
        .and_then(|metadata| metadata.get("test-partitions"))
    else {
        return Ok(());
    };
    let partitions = partitions
        .as_table()
        .context("package.metadata.ohm.test-partitions must be a table")?;
    let Some(declarations) = partitions.get(target_name) else {
        return Ok(());
    };
    let declarations: BTreeMap<String, Declaration> =
        declarations.clone().try_into().with_context(|| {
            format!("invalid test partitions for integration target `{target_name}`")
        })?;
    if declarations.len() > 8 {
        bail!("integration target `{target_name}` declares more than 8 test partitions");
    }
    let mut prefixes: Vec<String> = Vec::new();
    let mut selected = None;
    for (group, declaration) in declarations {
        if group.trim().is_empty() {
            bail!("test partition group names must not be empty");
        }
        if declaration.path.as_os_str().is_empty()
            || !declaration
                .path
                .components()
                .all(|part| matches!(part, Component::Normal(_)))
        {
            bail!("test partition `{group}` requires a package-relative path without `.` or `..`");
        }
        let relative_path: PathBuf = declaration.path.components().collect();
        let source = package.root().join(&relative_path);
        if !source.is_file() {
            bail!(
                "test partition `{group}` source `{}` is not a file",
                source.display()
            );
        }
        if package
            .targets()
            .iter()
            .any(|target| target.src_path().path() == Some(source.as_path()))
        {
            bail!(
                "test partition `{group}` source is already a Cargo target; place partition roots in a nested directory"
            );
        }
        if declaration.prefixes.is_empty() {
            bail!("test partition `{group}` requires at least one module prefix");
        }
        let mut matches = false;
        for prefix in declaration.prefixes {
            if prefix.split("::").any(|part| {
                part.is_empty() || part.chars().any(|ch| ch.is_whitespace() || ch == ':')
            }) {
                bail!("invalid module prefix `{prefix}` in test partition `{group}`");
            }
            if let Some(previous) = prefixes.iter().find(|previous| {
                *previous == &prefix
                    || contains_test(previous, &prefix)
                    || contains_test(&prefix, previous)
            }) {
                bail!("overlapping test partition prefixes `{previous}` and `{prefix}`");
            }
            matches |= contains_test(&prefix, test_name);
            prefixes.push(prefix);
        }
        if matches {
            selected = Some(TestPartition {
                package: package.package_id(),
                target: target.name().to_owned(),
                group,
                relative_path,
                source,
            });
        }
    }
    options.test_partition = selected;
    Ok(())
}

fn contains_test(prefix: &str, name: &str) -> bool {
    name.strip_prefix(prefix)
        .is_some_and(|suffix| suffix.starts_with("::"))
}

impl TestPartition {
    pub(crate) fn apply(&self, roots: &mut [Unit], interner: &UnitInterner) {
        let [unit] = roots else { return };
        if unit.pkg.package_id() != self.package
            || unit.target.name() != self.target
            || unit.mode != CompileMode::Test
            || has_coverage_flags(unit)
        {
            return;
        }
        let mut target = unit.target.clone();
        target.set_src_path(self.source.clone().into());
        target.set_ohm_test_partition(self.group.clone(), self.relative_path.clone());
        *unit = interner.intern(
            &unit.pkg,
            &target,
            unit.profile.clone(),
            unit.kind,
            unit.mode,
            unit.features.clone(),
            unit.rustflags.clone(),
            unit.rustdocflags.clone(),
            unit.links_overrides.clone(),
            unit.is_std,
            unit.dep_hash,
            unit.artifact,
            unit.artifact_target_for_features,
            unit.skip_non_compile_time_dep,
        );
    }
}

fn has_coverage_flags(unit: &Unit) -> bool {
    let mut args = unit
        .pkg
        .manifest()
        .lint_rustflags()
        .iter()
        .map(String::as_str)
        .chain(unit.profile.rustflags.iter().map(|arg| arg.as_str()))
        .chain(unit.rustflags.iter().map(String::as_str));
    while let Some(argument) = args.next() {
        if argument.starts_with('@') {
            return true;
        }
        let option = if matches!(argument, "-C" | "--codegen" | "-Z") {
            args.next()
        } else {
            argument
                .strip_prefix("-C")
                .or_else(|| argument.strip_prefix("--codegen="))
                .or_else(|| argument.strip_prefix("-Z"))
        };
        if option.is_some_and(|option| option.split('=').next() == Some("instrument-coverage")) {
            return true;
        }
    }
    false
}
