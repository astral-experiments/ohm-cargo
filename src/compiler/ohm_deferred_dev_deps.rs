//! Targeted tests validate the dependencies their executable actually uses.
//! Resolution and compiler identities retain the complete graph; only scheduling
//! omits previously unused pure-Rust dev dependencies. Fresh proof is mandatory
//! before accepting any output, and an inconclusive attempt retries once normally.

use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

use super::custom_build::BuildOutput;
use super::{BuildRunner, CompileKind, CompileMode, Unit, UnitHash};
use crate::util::data_structures::{HashMap, HashSet};
use crate::util::interning::InternedString;
use crate::workspace::dependency::DepKind;

#[derive(Default)]
pub(crate) struct State {
    pub(crate) disabled: bool,
    /// Only direct edges from the selected root; retained transitive edges still build.
    pub(crate) dependencies: HashSet<Unit>,
    pub(crate) retry: Arc<AtomicBool>,
}

impl State {
    pub(crate) fn retry_requested(&self) -> bool {
        self.retry.load(Ordering::Relaxed)
    }
}

#[derive(Debug, thiserror::Error)]
#[error("retrying with the complete development dependency graph")]
pub(crate) struct Retry;

/// Identify each script's output directory before its job runs. `plan` rejects
/// removing any script, so every directory admitted here is still produced by
/// the ordinary dependency graph before the test compiler starts.
pub(crate) fn native_output_dirs(runner: &BuildRunner<'_, '_>) -> HashMap<UnitHash, PathBuf> {
    runner
        .bcx
        .unit_graph
        .keys()
        .filter(|unit| unit.mode.is_run_custom_build())
        .map(|unit| {
            let path = if runner.bcx.gctx.cli_unstable().build_dir_new_layout {
                runner.files().out_dir_new_layout(unit)
            } else {
                runner.files().build_script_out_dir(unit)
            };
            (runner.get_run_build_script_metadata(unit), path)
        })
        .collect()
}

/// Admit only Linux native search directories containing self-contained native
/// archives, ELF objects, or bounded auxiliary source/header trees owned by a
/// retained script. Reject aliases and inputs that can load another artifact.
pub(crate) fn native_search_paths_supported(output: &BuildOutput, out_dir: &Path) -> bool {
    let supported = || -> Option<()> {
        if !cfg!(target_os = "linux")
            || fs::symlink_metadata(out_dir).ok()?.file_type().is_symlink()
        {
            return None;
        }
        let out_dir = out_dir.canonicalize().ok()?;
        let mut search_dirs = Vec::new();
        for path in &output.library_paths {
            let path = Path::new(path.as_ref().to_str()?.strip_prefix("native=")?);
            let path = path.canonicalize().ok()?;
            if !path.starts_with(&out_dir) {
                return None;
            }
            let mut auxiliary_bytes = 0;
            for (index, entry) in walkdir::WalkDir::new(&path)
                .min_depth(1)
                .into_iter()
                .enumerate()
            {
                let entry = entry.ok()?;
                if index >= 4096 || entry.depth() > 8 {
                    return None;
                }
                if entry.file_type().is_dir() {
                    continue;
                }
                if !entry.file_type().is_file() {
                    return None;
                }
                #[cfg(target_os = "linux")]
                if std::os::unix::fs::MetadataExt::nlink(&entry.metadata().ok()?) != 1 {
                    return None;
                }
                let mut file = fs::File::open(entry.path()).ok()?;
                match entry
                    .path()
                    .extension()
                    .and_then(|extension| extension.to_str())
                {
                    Some("a") => {
                        let mut header = [0; 8];
                        file.read_exact(&mut header).ok()?;
                        if &header != b"!<arch>\n" {
                            return None;
                        }
                    }
                    Some("o") | None => {
                        // Compiler feature probes may omit the .o suffix. Only
                        // ELF relocatable objects are self-contained inputs.
                        let mut header = [0; 18];
                        file.read_exact(&mut header).ok()?;
                        if &header[..4] != b"\x7fELF"
                            || !matches!((header[5], &header[16..18]), (1, [1, 0]) | (2, [0, 1]))
                        {
                            return None;
                        }
                    }
                    Some("c" | "h" | "inc" | "in") => {
                        let mut text = String::new();
                        file.take(8 * 1024 * 1024 - auxiliary_bytes + 1)
                            .read_to_string(&mut text)
                            .ok()?;
                        auxiliary_bytes += text.len() as u64;
                        if auxiliary_bytes > 8 * 1024 * 1024
                            || !native_auxiliary_text_supported(&text)
                        {
                            return None;
                        }
                    }
                    _ => return None,
                }
            }
            search_dirs.push(path);
        }
        for library in &output.library_links {
            let name = library.strip_prefix("static=")?;
            if name.is_empty()
                || !name
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || matches!(c, b'_' | b'-'))
                || !search_dirs
                    .iter()
                    .any(|dir| dir.join(format!("lib{name}.a")).is_file())
            {
                return None;
            }
        }
        Some(())
    };
    supported().is_some()
}

/// A verbatim native library name can select a header or source file too. Do
/// not admit renamed archives or text that can load files as a linker script.
/// Require both literal and escaped string interpretations to be safe;
/// malformed text conservatively retains the full graph.
fn native_auxiliary_text_supported(text: &str) -> bool {
    if text.starts_with("!<arch>\n")
        || text.starts_with("!<thin>\n")
        || text
            .chars()
            .any(|c| c.is_control() && !c.is_ascii_whitespace())
    {
        return false;
    }
    for escapes in [false, true] {
        let mut text = text;
        let mut file_command = false;
        loop {
            text = text.trim_start();
            if text.is_empty() {
                break;
            }
            if let Some(comment) = text.strip_prefix("/*") {
                let Some((_, rest)) = comment.split_once("*/") else {
                    return false;
                };
                text = rest;
                continue;
            }
            if text.starts_with('#') {
                text = text.split_once(['\r', '\n']).map_or("", |(_, rest)| rest);
                continue;
            }
            if text.starts_with('(') && file_command {
                return false;
            }
            file_command = false;
            let mut quoted = String::new();
            let (word, rest) = if text.starts_with('"') {
                let mut chars = text.char_indices().skip(1);
                let end = loop {
                    let Some((index, c)) = chars.next() else {
                        return false;
                    };
                    if escapes && c == '\\' {
                        let Some((_, c)) = chars.next() else {
                            return false;
                        };
                        quoted.push(c);
                    } else if c == '"' {
                        break index + 1;
                    } else {
                        quoted.push(c);
                    }
                };
                (quoted.as_str(), &text[end..])
            } else {
                let length = text
                    .bytes()
                    .take_while(|c| c.is_ascii_alphanumeric() || *c == b'_')
                    .count();
                if length == 0 {
                    text = &text[text.chars().next().unwrap().len_utf8()..];
                    continue;
                }
                text.split_at(length)
            };
            if word == "INCLUDE" {
                return false;
            }
            file_command = matches!(
                word,
                "INPUT" | "GROUP" | "AS_NEEDED" | "SEARCH_DIR" | "STARTUP"
            );
            text = rest;
        }
    }
    true
}

/// Record proof even when opted out, without altering rustc's tracked inputs.
/// Unsupported commands retain the ordinary build path.
pub(crate) fn supported(runner: &BuildRunner<'_, '_>, unit: &Unit) -> bool {
    runner.bcx.gctx.cli_unstable().ohm_defaults()
        && runner.bcx.gctx.cli_unstable().relink_only()
        && !runner.bcx.gctx.cli_unstable().cargo_lints
        && runner.bcx.roots.len() == 1
        && runner.bcx.roots[0] == *unit
        && unit.mode == CompileMode::Test
        && unit.target.is_lib()
        && !unit.target.proc_macro()
        && runner.bcx.ws.is_member_id(unit.pkg.package_id())
        && runner.bcx.build_config.primary_unit_rustc.is_none()
        && !runner.bcx.build_config.dry_run
        && !runner.bcx.build_config.sbom
        && !runner.bcx.build_config.future_incompat_report
        && unit.kind == CompileKind::Host
        && runner.compilation.target_linker(unit.kind).is_none()
        && !super::has_opaque_integration_linker_flags(runner, unit)
        && runner
            .bcx
            .rustc()
            .supports_transparent_unused_externs(runner.bcx.gctx)
        && matches!(
            runner.lto[unit],
            super::lto::Lto::Off | super::lto::Lto::OnlyObject
        )
}

/// Remove only scheduling edges. The original graph remains authoritative for
/// feature resolution, metadata hashes, rustc arguments, and fingerprints.
pub(crate) fn plan(
    runner: &mut BuildRunner<'_, '_>,
    unit: &Unit,
    previous_unused: Option<&HashSet<InternedString>>,
) -> Vec<InternedString> {
    if runner.deferred_dev_deps.disabled
        || !runner.bcx.gctx.cli_unstable().ohm_defer_dev_deps()
        || !supported(runner, unit)
        || runner.fingerprints.get(unit).is_none_or(|fp| {
            fp.is_early_cutoff_candidate()
                || !matches!(fp.fs_status(), super::fingerprint::FsStatus::StaleItem(_))
        })
    {
        return Vec::new();
    }
    let Some(previous_unused) = previous_unused else {
        return Vec::new();
    };
    let (candidates, _) =
        super::unused_integration_workspace_dependencies(runner, unit, previous_unused);
    let dependencies = runner.unit_deps(unit);
    let deferred = dependencies
        .iter()
        .filter(|dep| {
            candidates.contains(&runner.bcx.unit_to_index[&dep.unit])
                && dep.manifest_deps.0.as_ref().is_some_and(|deps| {
                    !deps.is_empty() && deps.iter().all(|dep| dep.kind() == DepKind::Development)
                })
        })
        .map(|dep| dep.unit.clone())
        .collect::<HashSet<_>>();
    if deferred.is_empty() {
        return Vec::new();
    }

    let closure = |roots: Vec<Unit>| {
        let mut pending = roots;
        let mut visited = HashSet::default();
        while let Some(dep) = pending.pop() {
            if visited.insert(dep.clone()) {
                pending.extend(runner.unit_deps(&dep).iter().map(|dep| dep.unit.clone()));
            }
        }
        visited
    };
    let retained = closure(
        dependencies
            .iter()
            .filter(|dep| !deferred.contains(&dep.unit))
            .map(|dep| dep.unit.clone())
            .collect(),
    );
    let removed = closure(deferred.iter().cloned().collect());
    // Build scripts, proc macros, artifact dependencies and native links can
    // contribute effects beyond a direct --extern. Do not speculate over them.
    if removed.difference(&retained).any(|dep| {
        dep.mode != CompileMode::Build
            || !dep.target.is_lib()
            || dep.target.proc_macro()
            || dep.artifact.is_true()
            || dep.pkg.manifest().links().is_some()
            || runner.find_build_script_units(dep).is_some()
            || super::has_opaque_integration_linker_flags(runner, dep)
            || dep
                .target
                .rustc_crate_types()
                .iter()
                .any(|kind| !matches!(kind, super::CrateType::Lib | super::CrateType::Rlib))
    }) {
        return Vec::new();
    }
    let names = dependencies
        .iter()
        .filter(|dep| deferred.contains(&dep.unit))
        .map(|dep| dep.extern_crate_name)
        .collect::<Vec<_>>();
    tracing::info!(target: "cargo::compiler::ohm_deferred_dev_deps", ?names, "deferring unused dev dependencies");
    runner.deferred_dev_deps.dependencies = deferred;
    names
}
