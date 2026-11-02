//! dep-info files for external build system integration.
//! See [`output_depinfo`] for more.

use crate::util::data_structures::{HashMap, HashSet};
use cargo_util::paths::normalize_path;
use std::path::{Path, PathBuf};

use super::{BuildRunner, FileFlavor, Unit, fingerprint};
use crate::util::{CargoResult, internal};
use cargo_util::paths;
use tracing::debug;

/// Makes paths relative to the configured base and escapes spaces in Make rules.
fn render_filename(path: &Path, basedir: Option<&Path>) -> CargoResult<PathBuf> {
    let normalized;
    let path = if let Some(basedir) = basedir {
        normalized = normalize_path(path);
        normalized.strip_prefix(basedir).unwrap_or(path)
    } else {
        path
    };
    let bytes = paths::path2bytes(path)?;
    if !bytes.contains(&b' ') {
        return Ok(path.to_owned());
    }
    let mut escaped = Vec::with_capacity(bytes.len());
    for &byte in bytes {
        if byte == b' ' {
            escaped.push(b'\\');
        }
        escaped.push(byte);
    }
    paths::bytes2path(&escaped)
}

/// Compares the prerequisites of a native depfile when the UTF-8 parser cannot read it.
fn same_native_prerequisites(previous: &[u8], prerequisites: &[u8]) -> bool {
    // Spaces in the target are escaped, so the first ": " or ":\n" ends the target.
    std::str::from_utf8(previous).is_err()
        && previous
            .windows(2)
            .position(|pair| matches!(pair, b": " | b":\n"))
            .is_some_and(|end| &previous[end..] == prerequisites)
}

/// Collects all dependencies of the `unit` for the output dep info file.
///
/// Dependencies will be stored in `deps`, including:
///
/// * dependencies from [fingerprint dep-info]
/// * paths from `rerun-if-changed` build script instruction
/// * ...and traverse transitive dependencies recursively
///
/// [fingerprint dep-info]: super::fingerprint#fingerprint-dep-info-files
fn add_deps_for_unit(
    deps: &mut Vec<PathBuf>,
    build_runner: &BuildRunner<'_, '_>,
    unit: &Unit,
    visited: &mut HashSet<Unit>,
    dep_info_cache: &mut Option<HashMap<Unit, Vec<PathBuf>>>,
) -> CargoResult<()> {
    if !visited.insert(unit.clone()) {
        return Ok(());
    }

    // units representing the execution of a build script don't actually
    // generate a dep info file, so we just keep on going below
    if !unit.mode.is_run_custom_build() {
        if let Some(paths) = dep_info_cache.as_ref().and_then(|cache| cache.get(unit)) {
            deps.extend(paths.iter().cloned());
        } else {
            // Add dependencies from rustc dep-info output (stored in fingerprint directory)
            let dep_info_loc = fingerprint::dep_info_loc(build_runner, unit);
            if let Some(paths) = fingerprint::dep_info_paths(
                unit.pkg.root(),
                &build_runner.files().build_root(unit),
                &dep_info_loc,
            ) {
                if let Some(cache) = dep_info_cache.as_mut() {
                    let paths: Vec<_> = paths.collect();
                    deps.extend(paths.iter().cloned());
                    cache.insert(unit.clone(), paths);
                } else {
                    deps.extend(paths);
                }
            } else {
                debug!(
                    "can't find dep_info for {:?} {}",
                    unit.pkg.package_id(),
                    unit.target
                );
                return Err(internal("dep_info missing"));
            }
        }
    }

    // Add rerun-if-changed dependencies
    if let Some(metadata_vec) = build_runner.find_build_script_metadatas(unit) {
        for metadata in metadata_vec {
            if let Some(output) = build_runner
                .build_script_outputs
                .lock()
                .unwrap()
                .get(metadata)
            {
                for path in &output.rerun_if_changed {
                    let package_root = unit.pkg.root();

                    let path = if path.as_os_str().is_empty() {
                        // Joining with an empty path causes Rust to add a trailing path separator.
                        // On Windows, this would add an invalid trailing backslash to the .d file.
                        package_root.to_path_buf()
                    } else {
                        // The paths we have saved from the unit are of arbitrary relativeness and
                        // may be relative to the crate root of the dependency.
                        package_root.join(path)
                    };

                    deps.push(path);
                }
            }
        }
    }

    // Recursively traverse all transitive dependencies
    for dep in build_runner.unit_deps(unit) {
        if dep.unit.is_local() {
            add_deps_for_unit(deps, build_runner, &dep.unit, visited, dep_info_cache)?;
        }
    }
    Ok(())
}

/// Save a `.d` dep-info file for the given unit. This is the third kind of
/// dep-info mentioned in [`fingerprint`] module.
///
/// Argument `unit` is expected to be the root unit, which will be uplifted.
///
/// Cargo emits its own dep-info files in the output directory. This is
/// only done for every "uplifted" artifact. These are intended to be used
/// with external build systems so that they can detect if Cargo needs to be
/// re-executed.
///
/// It includes all the entries from the `rustc` dep-info file, and extends it
/// with any `rerun-if-changed` entries from build scripts. It also includes
/// sources from any path dependencies. Registry dependencies are not included
/// under the assumption that changes to them can be detected via changes to
/// `Cargo.lock`.
///
/// Share `dep_info_cache` only across roots of the same completed build.
///
/// [`fingerprint`]: super::fingerprint#dep-info-files
pub fn output_depinfo(
    build_runner: &BuildRunner<'_, '_>,
    unit: &Unit,
    dep_info_cache: &mut Option<HashMap<Unit, Vec<PathBuf>>>,
) -> CargoResult<()> {
    let outputs = build_runner.outputs(unit)?;
    let mut outputs = outputs
        .iter()
        .filter(|output| {
            !matches!(
                output.flavor,
                FileFlavor::DebugInfo
                    | FileFlavor::Auxiliary
                    | FileFlavor::Sbom
                    | FileFlavor::Unremap
            )
        })
        .filter_map(|output| output.hardlink.as_ref())
        .peekable();
    if outputs.peek().is_none() {
        return Ok(());
    }

    let bcx = build_runner.bcx;
    let mut deps = Vec::new();
    let mut visited = HashSet::default();
    let success =
        add_deps_for_unit(&mut deps, build_runner, unit, &mut visited, dep_info_cache).is_ok();
    // A stable sort preserves the first spelling of equivalent paths.
    deps.sort();
    deps.dedup();
    let basedir = bcx
        .gctx
        .build_config()?
        .dep_info_basedir
        .as_ref()
        .map(|value| normalize_path(&value.resolve_path(bcx.gctx)));
    let deps = deps
        .iter()
        .map(|f| render_filename(f, basedir.as_deref()))
        .collect::<CargoResult<Vec<_>>>()?;

    // Preserve the legacy target selection for crate types sharing a dep-info path.
    let single_output = outputs.clone().nth(1).is_none();
    for link_dst in outputs {
        let output_path = link_dst.with_extension("d");
        if success {
            let target = render_filename(link_dst, basedir.as_deref())?;
            let mut contents = paths::path2bytes(&target)?.to_vec();
            let target_len = contents.len();
            contents.push(b':');
            for dep in &deps {
                contents.push(b' ');
                contents.extend_from_slice(paths::path2bytes(dep)?);
            }
            contents.push(b'\n');

            if single_output {
                // Preserve the mtime when the complete rendered dep-info is unchanged.
                if paths::read_bytes(&output_path).is_ok_and(|previous| previous == contents) {
                    continue;
                }
            } else if let Ok(previous) = fingerprint::parse_rustc_dep_info(&output_path) {
                // The dependency-only comparison can retain an earlier output's target.
                if previous
                    .files
                    .iter()
                    .map(|(path, _checksum)| path)
                    .eq(&deps)
                {
                    continue;
                }
            } else if paths::read_bytes(&output_path)
                .is_ok_and(|previous| same_native_prerequisites(&previous, &contents[target_len..]))
            {
                continue;
            }
            paths::write(output_path, contents)?;

        // dep-info generation failed, so delete output file. This will
        // usually cause the build system to always rerun the build
        // rule, which is correct if inefficient.
        } else if output_path.exists() {
            paths::remove_file(output_path)?;
        }
    }
    Ok(())
}
