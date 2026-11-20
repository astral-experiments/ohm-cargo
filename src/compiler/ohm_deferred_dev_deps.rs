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
    /// Jobs behind deferred edges with effects on the test beyond a Rust extern.
    pub(crate) retained: Vec<Unit>,
    pub(super) skipped_artifacts: Vec<PathBuf>,
    pub(super) inputs: Option<u64>,
    pub(crate) retry: Arc<AtomicBool>,
}

/// Monitor the skipped files themselves when a registry build script adds
/// system native search paths. A linker script or a hard link can refer to
/// one of these files without any Rust use of its crate.
pub(super) struct ArtifactWatch {
    #[cfg(target_os = "linux")]
    fd: std::os::fd::OwnedFd,
}

impl ArtifactWatch {
    #[cfg(target_os = "linux")]
    pub(super) fn start(paths: &[PathBuf]) -> Option<Self> {
        use rustix::fs::inotify::{self, CreateFlags, WatchFlags};
        if paths.is_empty() {
            return None;
        }
        let fd = inotify::init(CreateFlags::NONBLOCK | CreateFlags::CLOEXEC).ok()?;
        for path in paths {
            if !path.symlink_metadata().ok()?.is_file() {
                return None;
            }
            let flags = WatchFlags::OPEN
                | WatchFlags::MODIFY
                | WatchFlags::ATTRIB
                | WatchFlags::DELETE_SELF
                | WatchFlags::MOVE_SELF;
            inotify::add_watch(&fd, path, flags).ok()?;
        }
        Some(Self { fd })
    }

    #[cfg(target_os = "linux")]
    pub(super) fn untouched(&self) -> bool {
        // Require an empty queue. An open through an alias, a change to an
        // inode, a dropped watch, an overflow or a read error forces a retry.
        rustix::io::read(&self.fd, &mut [0u8; 64][..]) == Err(rustix::io::Errno::AGAIN)
    }

    #[cfg(not(target_os = "linux"))]
    pub(super) fn start(_paths: &[PathBuf]) -> Option<Self> {
        None
    }

    #[cfg(not(target_os = "linux"))]
    pub(super) fn untouched(&self) -> bool {
        false
    }
}

impl State {
    pub(crate) fn retry_requested(&self) -> bool {
        self.retry.load(Ordering::Relaxed)
    }
}

#[derive(Debug, thiserror::Error)]
#[error("retrying with the complete development dependency graph")]
pub(crate) struct Retry;

/// Identify each script's output directory before its job runs. `plan` retains
/// all scripts, so every directory admitted here is still produced by
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
        && runner.bcx.gctx.cli_unstable().collect_relink_cache()
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

/// Called after Cargo verifies the local sources, outputs and configuration
/// of a test that is stale solely due to a dependency.
pub(super) fn reuse(runner: &mut BuildRunner<'_, '_>, unit: &Unit) -> bool {
    if !supported(runner, unit) {
        return false;
    }
    let proof = || {
        let outputs = runner.outputs(unit).ok()?;
        let path = &outputs
            .iter()
            .find(|o| o.flavor == super::FileFlavor::Normal)?
            .path;
        super::RelinkCachePaths::new(path.clone()).unused_proof()
    };
    let Some((names, Some(inputs))) = proof() else {
        return false;
    };
    !plan(runner, unit, Some(&names), Some(inputs)).is_empty()
}

/// Remove only scheduling edges. The original graph remains authoritative for
/// feature resolution, metadata hashes, rustc arguments, and fingerprints.
pub(crate) fn plan(
    runner: &mut BuildRunner<'_, '_>,
    unit: &Unit,
    previous_unused: Option<&HashSet<InternedString>>,
    expected: Option<u64>,
) -> Vec<InternedString> {
    if runner.deferred_dev_deps.disabled
        || !runner.bcx.gctx.cli_unstable().ohm_defer_dev_deps()
        || !supported(runner, unit)
        || runner.fingerprints.get(unit).is_none_or(|fp| {
            fp.is_early_cutoff_candidate()
                || (expected.is_none()
                    && !matches!(fp.fs_status(), super::fingerprint::FsStatus::StaleItem(_)))
        })
    {
        return Vec::new();
    }
    let Some(previous_unused) = previous_unused else {
        return Vec::new();
    };
    let candidates =
        super::unused_integration_workspace_dependencies(runner, unit, previous_unused);
    let dependencies = runner.unit_deps(unit);
    let mut deferred = dependencies
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
    let mut retained = closure(
        dependencies
            .iter()
            .filter(|dep| !deferred.contains(&dep.unit))
            .map(|dep| dep.unit.clone())
            .collect(),
    );
    let removed = closure(deferred.iter().cloned().collect());
    // Schedule the units with effects beyond an ordinary --extern as
    // additional dependencies of the test, with all their inputs.
    let mut extra: Vec<_> = removed
        .difference(&retained)
        .filter(|dep| {
            dep.mode != CompileMode::Build
                || !dep.target.is_lib()
                || dep.target.proc_macro()
                || dep.artifact.is_true()
                || dep.pkg.manifest().links().is_some()
                || super::has_opaque_integration_linker_flags(runner, dep)
                || dep
                    .target
                    .rustc_crate_types()
                    .iter()
                    .any(|kind| !matches!(kind, super::CrateType::Lib | super::CrateType::Rlib))
        })
        .cloned()
        .collect();
    retained.extend(closure(extra.clone()));
    if !extra.is_empty() {
        // Keep fresh side dependencies in the ordinary queue as well.
        // Watching these files could cause spurious retries when another
        // compiler reads shared artifacts whose producers have no new work.
        let fresh: Vec<_> = removed
            .difference(&retained)
            .filter(|dep| {
                runner.fingerprints.get(*dep).is_some_and(|fp| {
                    matches!(
                        fp.fs_status(),
                        super::fingerprint::FsStatus::UpToDate { .. }
                    )
                })
            })
            .cloned()
            .collect();
        retained.extend(closure(fresh.clone()));
        extra.extend(fresh);
    }
    deferred.retain(|dep| !retained.contains(dep));
    if deferred.is_empty() {
        return Vec::new();
    }
    let snapshot = || {
        let mut units = Vec::new();
        for dep in retained.iter() {
            units.push(super::fingerprint::deferred_input(runner, dep, false)?);
        }
        for dep in removed.difference(&retained) {
            units.push(super::fingerprint::deferred_input(runner, dep, true)?);
        }
        units.sort_unstable();
        Some(crate::util::hash_u64(units))
    };
    let inputs = snapshot();
    if expected.is_some() && inputs != expected {
        return Vec::new();
    }
    let mut skipped_artifacts = Vec::new();
    for dep in removed.difference(&retained) {
        let Ok(outputs) = runner.outputs(dep) else {
            return Vec::new();
        };
        let mut has_rlib = false;
        for output in outputs.iter() {
            let extension = output.path.extension().and_then(|s| s.to_str());
            if matches!(extension, Some("rlib" | "rmeta")) {
                has_rlib |= extension == Some("rlib");
                skipped_artifacts.push(output.path.clone());
            }
        }
        if !has_rlib {
            return Vec::new();
        }
    }
    let names = dependencies
        .iter()
        .filter(|dep| deferred.contains(&dep.unit))
        .map(|dep| dep.extern_crate_name)
        .collect::<Vec<_>>();
    tracing::info!(target: "cargo::compiler::ohm_deferred_dev_deps", ?names, "deferring unused dev dependencies");
    if expected.is_none() {
        runner.deferred_dev_deps.inputs = inputs;
    }
    runner.deferred_dev_deps.dependencies = deferred;
    runner.deferred_dev_deps.retained = extra;
    runner.deferred_dev_deps.skipped_artifacts = skipped_artifacts;
    names
}

#[cfg(all(target_os = "linux", test))]
#[test]
fn detects_a_native_input_opened_through_an_alias() {
    let dir = tempfile::tempdir().unwrap();
    let archive = dir.path().join("libhelper.rlib");
    let native = dir.path().join("libhelper.a");
    fs::write(&archive, b"!<arch>\n").unwrap();
    fs::hard_link(&archive, &native).unwrap();
    let watch = ArtifactWatch::start(&[archive]).unwrap();
    assert!(watch.untouched());
    fs::File::open(native).unwrap();
    assert!(!watch.untouched());
}
