//! dep-info files for external build system integration.
//! See [`output_depinfo`] for more.

use crate::util::data_structures::{IndexMap, IndexSet};
use cargo_util::paths::normalize_path;
use std::cell::OnceCell;
use std::ffi::OsString;
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};

use super::{BuildRunner, FileFlavor, Unit, fingerprint};
use crate::util::{CargoResult, OnceExt, internal};
use cargo_util::paths;
use tracing::debug;

/// Basically just normalizes a given path and converts it to a string.
fn render_filename<P: AsRef<Path>>(path: P, basedir: Option<&str>) -> CargoResult<String> {
    fn wrap_path(path: &Path) -> CargoResult<String> {
        path.to_str()
            .ok_or_else(|| internal(format!("path `{:?}` not utf-8", path)))
            .map(|f| f.replace(" ", "\\ "))
    }

    let path = path.as_ref();
    if let Some(basedir) = basedir {
        let norm_path = normalize_path(path);
        let norm_basedir = normalize_path(basedir.as_ref());
        match norm_path.strip_prefix(norm_basedir) {
            Ok(relpath) => wrap_path(relpath),
            _ => wrap_path(path),
        }
    } else {
        wrap_path(path)
    }
}

/// Looks up the direct prerequisites once per unit, after all compiler jobs finish.
fn unit_paths(
    build_runner: &BuildRunner<'_, '_>,
    unit: &Unit,
    paths: &mut IndexSet<OsString>,
) -> CargoResult<Vec<usize>> {
    let mut deps = Vec::new();
    if !unit.mode.is_run_custom_build() {
        let dep_info_loc = fingerprint::dep_info_loc(build_runner, unit);
        let build_root = build_runner.files().build_root(unit);
        let Some(files) = fingerprint::dep_info_paths(unit.pkg.root(), &build_root, &dep_info_loc)
        else {
            debug!(
                "can't find dep_info for {:?} {}",
                unit.pkg.package_id(),
                unit.target
            );
            return Err(internal("dep_info missing"));
        };
        deps.extend(files.map(|path| paths.insert_full(path.into_os_string()).0));
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

                    deps.push(paths.insert_full(path.into_os_string()).0);
                }
            }
        }
    }

    Ok(deps)
}

/// Records each reachable local unit in the original depth-first order.
fn collect_units(
    build_runner: &BuildRunner<'_, '_>,
    unit: &Unit,
    units: &mut IndexSet<usize>,
    dep_info_cache: &mut IndexMap<Unit, Vec<usize>>,
    paths: &mut IndexSet<OsString>,
) -> CargoResult<()> {
    let index = if let Some(index) = dep_info_cache.get_index_of(unit) {
        index
    } else {
        let deps = unit_paths(build_runner, unit, paths)?;
        dep_info_cache.insert_full(unit.clone(), deps).0
    };
    if !units.insert(index) {
        return Ok(());
    }
    for dep in build_runner.unit_deps(unit) {
        if dep.unit.is_local() {
            collect_units(build_runner, &dep.unit, units, dep_info_cache, paths)?;
        }
    }
    Ok(())
}

/// Saves external `.d` files for the build's uplifted artifacts.
///
/// The prerequisites include rustc inputs and build-script `rerun-if-changed`
/// paths from transitive local dependencies. Registry updates are represented
/// by `Cargo.lock`. Compiler tasks must finish before their dep-info is read.
pub fn output_depinfo(build_runner: &BuildRunner<'_, '_>) -> CargoResult<()> {
    let mut paths = IndexSet::default();
    let mut dep_info_cache = IndexMap::default();
    let mut pending = Vec::new();
    for unit in &build_runner.bcx.roots {
        let outputs = build_runner.outputs(unit)?;
        let destinations: Vec<_> = outputs
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
            .filter_map(|output| output.hardlink.clone())
            .collect();
        if destinations.is_empty() {
            continue;
        }
        let mut units = IndexSet::default();
        let success = collect_units(
            build_runner,
            unit,
            &mut units,
            &mut dep_info_cache,
            &mut paths,
        )
        .is_ok();
        pending.push((destinations, units, success));
    }
    if pending.is_empty() {
        return Ok(());
    }
    let bcx = build_runner.bcx;
    let basedir_string;
    let basedir = match bcx.gctx.build_config()?.dep_info_basedir.clone() {
        Some(value) => {
            basedir_string = value
                .resolve_path(bcx.gctx)
                .as_os_str()
                .to_str()
                .ok_or_else(|| anyhow::format_err!("build.dep-info-basedir path not utf-8"))?
                .to_string();
            Some(basedir_string.as_str())
        }
        None => None,
    };
    // Compare each distinct spelling in one workspace-wide sort. Path equality
    // normalizes some spellings, so give those the same rank while retaining
    // the first original spelling independently for each output.
    let mut sorted: Vec<_> = (0..paths.len()).collect();
    sorted.sort_unstable_by(|&a, &b| Path::new(&paths[a]).cmp(Path::new(&paths[b])));
    let mut ranks = vec![0; paths.len()];
    for (rank, group) in sorted
        .chunk_by(|&a, &b| Path::new(&paths[a]) == Path::new(&paths[b]))
        .enumerate()
    {
        for &id in group {
            ranks[id] = rank;
        }
    }
    let rendered = vec![OnceCell::new(); paths.len()];
    for (outputs, units, success) in pending {
        let mut deps = units
            .into_iter()
            .flat_map(|index| dep_info_cache[index].iter().copied())
            .collect::<Vec<_>>();
        deps.sort_by_key(|&id| ranks[id]);
        deps.dedup_by_key(|id| ranks[*id]);
        let deps = deps
            .into_iter()
            .map(|id| {
                rendered[id]
                    .try_borrow_with(|| render_filename(Path::new(&paths[id]), basedir))
                    .map(String::as_str)
            })
            .collect::<CargoResult<Vec<_>>>()?;
        write_depinfo(&outputs, &deps, basedir, success)?;
    }
    Ok(())
}

fn write_depinfo(
    outputs: &[PathBuf],
    deps: &[&str],
    basedir: Option<&str>,
    success: bool,
) -> CargoResult<()> {
    // Preserve the legacy target selection for crate types sharing a dep-info path.
    let single_output = outputs.len() == 1;
    for link_dst in outputs {
        let output_path = link_dst.with_extension("d");
        if success {
            let target_fn = render_filename(link_dst, basedir)?;

            if single_output {
                let mut contents = Vec::new();
                write!(contents, "{}:", target_fn)?;
                for dep in deps {
                    write!(contents, " {}", dep)?;
                }
                writeln!(contents)?;

                // Preserve the mtime when the complete rendered dep-info is unchanged.
                if paths::read_bytes(&output_path).is_ok_and(|previous| previous == contents) {
                    continue;
                }
                paths::write(output_path, contents)?;
            } else {
                // The dependency-only comparison can retain an earlier output's target.
                if let Ok(previous) = fingerprint::parse_rustc_dep_info(&output_path) {
                    if previous
                        .files
                        .iter()
                        .map(|(path, _checksum)| Path::new(path))
                        .eq(deps.iter().map(Path::new))
                    {
                        continue;
                    }
                }

                let mut outfile = BufWriter::new(paths::create(output_path)?);
                write!(outfile, "{}:", target_fn)?;
                for dep in deps {
                    write!(outfile, " {}", dep)?;
                }
                writeln!(outfile)?;
            }

        // dep-info generation failed, so delete output file. This will
        // usually cause the build system to always rerun the build
        // rule, which is correct if inefficient.
        } else if output_path.exists() {
            paths::remove_file(output_path)?;
        }
    }
    Ok(())
}
