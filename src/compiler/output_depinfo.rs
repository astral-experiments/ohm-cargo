//! dep-info files for external build system integration.
//! See [`output_depinfo`] for more.

use crate::util::data_structures::{HashMap, HashSet};
use cargo_util::paths::normalize_path;
use std::path::{Path, PathBuf};

use super::{BuildRunner, FileFlavor, Unit, fingerprint};
use crate::util::{CargoResult, internal};
use cargo_util::paths;
use tracing::debug;

/// Makes a path relative to the configured base and quotes it for its part of a Make rule.
fn render_filename(
    path: &Path,
    basedir: Option<&Path>,
    extra_separator: Option<u8>,
) -> CargoResult<PathBuf> {
    let normalized;
    let path = if let Some(basedir) = basedir {
        normalized = normalize_path(path);
        normalized.strip_prefix(basedir).unwrap_or(path)
    } else {
        path
    };
    let bytes = paths::path2bytes(path)?;
    let prerequisite = extra_separator == Some(b'|');
    let needs_backslash = |byte| {
        matches!(byte, b' ' | b'\t' | b'#')
            || (cfg!(unix) && byte == b':')
            || Some(byte) == extra_separator
    };
    if !bytes
        .iter()
        .any(|&byte| byte == b'$' || needs_backslash(byte) || (prerequisite && byte == b';'))
    {
        return Ok(path.to_owned());
    }
    let mut escaped = Vec::with_capacity(bytes.len());
    let mut backslashes = 0;
    for &byte in bytes {
        if prerequisite && byte == b';' {
            // Make unquotes a recipe separator twice, consuming 4N+3 backslashes.
            escaped.extend(std::iter::repeat_n(b'\\', 3 * (backslashes + 1)));
        } else if needs_backslash(byte) {
            // Make consumes pairs of backslashes before a quoted separator.
            escaped.extend(std::iter::repeat_n(b'\\', backslashes + 1));
        } else if byte == b'$' {
            escaped.push(b'$');
        }
        escaped.push(byte);
        backslashes = if byte == b'\\' { backslashes + 1 } else { 0 };
    }
    paths::bytes2path(&escaped)
}

/// Splits a Cargo-written rule before the separator, preserving its exact native bytes.
fn rule_parts(rule: &[u8]) -> Option<(&[u8], &[u8])> {
    // A space in a target is escaped, so the first ": " or ":\n" ends the target.
    rule.windows(2)
        .position(|pair| matches!(pair, b": " | b":\n"))
        .map(|end| rule.split_at(end))
}

/// Compares all rendered prerequisites, including an order-only recheck rule.
fn same_literal_prerequisites(previous: &[u8], prerequisites: &[u8]) -> bool {
    rule_parts(previous).is_some_and(|(_, deps)| deps == prerequisites)
}

/// Detects a rendered prerequisite that a GCC depfile reader can interpret as a different file.
fn ambiguous_gcc_prerequisite(path: &[u8]) -> bool {
    path.ends_with(br"\:")
        || path.iter().enumerate().any(|(i, &byte)| match byte {
            b'\t' | b'|' | b';' => true,
            b'#' | b':' => path[..i].ends_with(br"\\"),
            b'$' => path[..i].ends_with(br"\"),
            // Ninja 1.11 splits these unquoted bytes between filenames.
            byte if byte.is_ascii_control() || br#""&'*<>?^`"#.contains(&byte) => {
                !path[..i].ends_with(br"\")
            }
            _ => false,
        })
}

/// Checks the target spelling before retaining a sibling crate type's percent-containing target.
fn shared_target_spelling_matches(depfile: &Path, target: &Path) -> bool {
    let Ok(previous) = paths::read_bytes(depfile) else {
        return false;
    };
    let Some((previous_target, _)) = rule_parts(&previous) else {
        return false;
    };
    paths::bytes2path(previous_target)
        .is_ok_and(|previous| previous.with_extension("d") == target.with_extension("d"))
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
    let config = bcx.gctx.build_config()?;
    let target_separator = config
        .dep_info_escape_percent
        .unwrap_or(false)
        .then_some(b'%');
    let basedir = config
        .dep_info_basedir
        .as_ref()
        .map(|value| normalize_path(&value.resolve_path(bcx.gctx)));
    let deps = deps
        .iter()
        .map(|f| render_filename(f, basedir.as_deref(), Some(b'|')))
        .collect::<CargoResult<Vec<_>>>()?;

    // Preserve the legacy target selection for crate types sharing a dep-info path.
    let single_output = outputs.clone().nth(1).is_none();
    for link_dst in outputs {
        let output_path = link_dst.with_extension("d");
        if success {
            let target = render_filename(link_dst, basedir.as_deref(), target_separator)?;
            let mut contents = paths::path2bytes(&target)?.to_vec();
            let target_len = contents.len();
            contents.push(b':');
            let mut recheck_gcc = false;
            let mut recheck_make = false;
            let mut saw_equals = false;
            for dep in &deps {
                let mut bytes = paths::path2bytes(dep)?;
                if bytes.ends_with(br"\") {
                    // A trailing backslash can quote the next word or the newline.
                    recheck_make = true;
                    continue;
                }
                recheck_gcc |= ambiguous_gcc_prerequisite(bytes);
                let first = contents.len() == target_len + 1;
                contents.push(b' ');
                if !saw_equals && let Some(equal) = bytes.iter().position(|&b| b == b'=') {
                    saw_equals = true;
                    if first {
                        // The empty automatic variable prevents a target-specific assignment.
                        // GCC-style depfile readers skip both characters.
                        contents.extend_from_slice(b"$< ");
                    }
                    // Make unquotes preceding backslashes only up to the first equals sign.
                    let (prefix, rest) = bytes.split_at(equal);
                    let slashes = prefix.iter().rev().take_while(|&&b| b == b'\\').count();
                    contents.extend_from_slice(prefix);
                    contents.extend(std::iter::repeat_n(b'\\', slashes));
                    recheck_gcc |= slashes != 0;
                    bytes = rest;
                }
                contents.extend_from_slice(bytes);
            }
            if recheck_gcc || recheck_make {
                // Make ignores the age of an order-only prerequisite. Use an ordinary
                // prerequisite when Make also needs to recheck the build.
                let marker = if cfg!(unix) {
                    PathBuf::from("/dev/null/ohm-ambiguous-gcc-path")
                } else {
                    output_path.join("ohm-ambiguous-gcc-path")
                };
                let prerequisite = render_filename(&marker, None, Some(b'|'))?;
                let marker_target = render_filename(&marker, None, Some(b'%'))?;
                contents.extend_from_slice(if recheck_make { b" " } else { b" | " });
                contents.extend_from_slice(paths::path2bytes(&prerequisite)?);
                contents.push(b'\n');
                contents.extend_from_slice(paths::path2bytes(&marker_target)?);
                contents.push(b':');
            }
            contents.push(b'\n');

            if single_output {
                // Preserve the mtime when the complete rendered dep-info is unchanged.
                if paths::read_bytes(&output_path).is_ok_and(|previous| previous == contents) {
                    continue;
                }
            } else if (!contents[..target_len].contains(&b'%')
                || shared_target_spelling_matches(&output_path, &target))
                && (paths::read_bytes(&output_path).is_ok_and(|previous| {
                    same_literal_prerequisites(&previous, &contents[target_len..])
                }) || (!(recheck_gcc || recheck_make || saw_equals)
                    && fingerprint::parse_rustc_dep_info(&output_path).is_ok_and(|previous| {
                        previous
                            .files
                            .iter()
                            .map(|(path, _checksum)| path)
                            .eq(&deps)
                    })))
            {
                // A shared depfile can retain an earlier output's target.
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
