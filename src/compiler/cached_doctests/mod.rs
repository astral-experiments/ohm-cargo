//! Build mergeable inline examples as one fingerprinted Cargo doctest unit.
mod generate;

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use cargo_util::{ProcessBuilder, paths};

use super::{BuildContext, BuildRunner, RelinkCachePaths, Unit, Work, fingerprint};
use crate::util::{CargoResult, add_path_args, path_args};
use crate::workspace::{Edition, profiles::PanicStrategy};

/// Rustdoc handles requests whose arguments can change which snippets get compiled.
pub(super) fn enabled(bcx: &BuildContext<'_, '_>, unit: &Unit) -> bool {
    bcx.build_config.cached_doctests
        && unit.mode.is_doc_test()
        && unit.kind.is_host()
        && unit.target.edition() == Edition::Edition2024
        && !unit.target.proc_macro()
        && unit.rustdocflags.is_empty()
}

/// Encoded dependencies of the crate under rustdoc's cfgs, separate from the
/// dependencies rustc reports for the extracted examples themselves.
pub(super) fn extraction_dep_info(dir: &Path) -> PathBuf {
    dir.join("dep-doctest-extraction")
}

/// Prepares both compiler commands with the dependencies of the doctest unit.
/// Build-script output is added by the job once those dependencies have finished.
pub(super) fn prepare(br: &BuildRunner<'_, '_>, unit: &Unit, force: bool) -> CargoResult<Work> {
    let bcx = br.bcx;
    let dir = br.files().fingerprint_dir(unit);
    let binary = br.outputs(unit)?[0].path.clone();
    let mut rustdoc = br.compilation.rustdoc_process(unit, None)?;
    let mut rustc = br.compilation.rustc_process(
        unit,
        br.is_primary_package(unit),
        bcx.ws.is_member(&unit.pkg),
    )?;
    let (_, cwd) = path_args(bcx.ws, unit);
    for cmd in [&mut rustdoc, &mut rustc] {
        cmd.cwd(&cwd).inherit_jobserver(&br.jobserver);
        super::build_deps_args(cmd, br, unit)?;
        cmd.args(&super::features_args(unit))
            .args(&super::check_cfg_args(unit));
        cmd.args(&super::lto_args(br, unit));
        unit.kind.add_target_arg(cmd);
        if let Some(linker) = br.compilation.target_linker(unit.kind) {
            let mut flag = OsString::from("linker=");
            flag.push(linker);
            cmd.arg("-C").arg(flag);
        }
        if unit.profile.panic != PanicStrategy::Unwind {
            cmd.arg("-C").arg(format!("panic={}", unit.profile.panic));
        }
        if super::unit_uses_checksum_freshness(br, unit) {
            cmd.arg("-Zchecksum-hash-algorithm=blake3");
        }
    }
    add_path_args(bcx.ws, unit, &mut rustdoc);
    rustdoc.arg("--crate-name").arg(unit.target.crate_name());
    rustdoc.args(unit.pkg.manifest().lint_rustflags());
    rustdoc.args(&["-Zunstable-options", "--cfg", "doctest"]);
    let source = dir.join("doctests.rs");
    let compiled_deps = dir.join("doctests.d");
    let extracted_deps = dir.join("extraction.d");
    rustc.args(&[
        "--edition=2024",
        "--crate-name",
        "rust_out",
        "-Ccodegen-units=1",
    ]);
    let unstable = bcx.gctx.cli_unstable();
    let check_links = (unstable.ohm_defaults() || unstable.relink_only())
        && bcx
            .rustc()
            .supports_relink_input_checks(bcx.gctx, bcx.ws.is_member(&unit.pkg));
    if check_links {
        rustc.arg("-Zohm-check-relink-inputs");
    }
    let linked = dir.join(format!("doctest-link{}", std::env::consts::EXE_SUFFIX));
    let cache = (check_links
        && unstable.collect_relink_cache()
        && fingerprint::unit_can_use_relink_only(br, unit)
        && bcx.rustc().wrapper.is_none()
        && bcx.rustc().workspace_wrapper.is_none()
        && bcx.build_config.primary_unit_rustc.is_none())
    .then(|| RelinkCachePaths::new(linked.clone()));
    if let Some(cache) = &cache {
        cache.preserve_codegen(&mut rustc);
    }
    let relinkable = super::relinkable_dependencies(br, unit);
    let mut emit = OsString::from("--emit=link,dep-info=");
    emit.push(&compiled_deps);
    rustc.arg(emit).arg(&source).arg("-o").arg(&linked);

    let scripts = br.find_build_script_metadatas(unit);
    let build_scripts = br.build_scripts.get(unit).cloned();
    let target = unit.target.clone();
    let mode = unit.mode;
    let outputs = Arc::clone(&br.build_script_outputs);
    let pkg_root = unit.pkg.root().to_owned();
    let build_root = br.files().build_root(unit);
    let env_config = Arc::clone(bcx.gctx.env_config()?);
    let local = unit.is_local();
    let compiled_info = fingerprint::dep_info_loc(br, unit);
    let extracted_info = extraction_dep_info(&dir);
    let fingerprint = Arc::clone(&br.fingerprints[unit]);

    Ok(Work::new(move |state| {
        {
            let outputs = outputs.lock().unwrap();
            for cmd in [&mut rustdoc, &mut rustc] {
                super::add_custom_flags(cmd, &outputs, scripts.clone())?;
                for meta in scripts.iter().flatten() {
                    if let Some(output) = outputs.get(*meta) {
                        for (kind, arg) in &output.linker_args {
                            if kind.applies_to(&target, mode) {
                                cmd.arg("-C").arg(format!("link-arg={arg}"));
                            }
                        }
                    }
                }
                if let Some(scripts) = &build_scripts {
                    for (_, key) in &scripts.to_link {
                        if let Some(output) = outputs.get(*key) {
                            for path in &output.library_paths {
                                cmd.arg("-L").arg(path.as_ref());
                            }
                        }
                    }
                }
            }
        }
        let started = paths::set_invocation_time(&dir)?;
        let translate =
            |raw: &Path, encoded: &Path, cmd: &ProcessBuilder, timestamp| -> CargoResult<()> {
                fingerprint::translate_dep_info(
                    raw,
                    encoded,
                    &cwd,
                    &pkg_root,
                    &build_root,
                    cmd,
                    local,
                    &env_config,
                    None,
                )?;
                paths::set_file_time_no_err(encoded, timestamp);
                Ok(())
            };
        let staging = tempfile::tempdir_in(binary.parent().unwrap())?;
        let staged_binary = staging.path().join("doctest");
        let publish = || -> CargoResult<()> {
            paths::link_or_copy(&linked, &staged_binary)?;
            std::fs::rename(&staged_binary, &binary)?;
            Ok(())
        };
        // The final link can read native archives outside Cargo's dependency
        // graph. Reuse the extraction and object files when Cargo has
        // validated both sets of Rust inputs, but let the linker resolve them.
        let inputs_unchanged = !force
            && !fingerprint.observes_foreign_span()
            && (fingerprint.can_reuse_doctest_codegen()
                || (cache.is_some()
                    && fingerprint::can_relink_due_to_early_cutoff(&fingerprint, &relinkable)));
        if !(inputs_unchanged && source.is_file()) {
            let mut extract = rustdoc.clone();
            extract.arg("--output-format=doctest");
            state.running(&extract);
            let generated = extract
                .exec_with_output()
                .ok()
                .filter(|output| output.stderr.is_empty())
                .and_then(|output| generate::harness(&output.stdout));

            // The extraction JSON has no dep-info. A dependency-only rustdoc
            // invocation also sees cfg(doctest) modules, includes and tracked env.
            let mut emit = OsString::from("--emit=dep-info=");
            emit.push(&extracted_deps);
            rustdoc.arg(emit).arg("-o").arg(dir.join("doc"));
            state.running(&rustdoc);
            if rustdoc.exec_with_output().is_ok() {
                translate(&extracted_deps, &extracted_info, &rustdoc, started)?;
                paths::write_if_changed(&source, generated.unwrap_or_default())?;
            } else {
                // Never admit an executable whose extraction inputs are unknown.
                if extracted_info.exists() {
                    paths::remove_file(&extracted_info)?;
                }
                paths::write_if_changed(&source, "")?;
            }
        }
        if source.metadata()?.len() != 0 {
            if let Some(cache) = &cache {
                if inputs_unchanged && cache.is_valid() {
                    let mut link = rustc.clone();
                    assert!(link.replace_arg(&source, &cache.rlink));
                    link.arg("-Zlink-only");
                    state.running(&link);
                    // The public executable can still be running in another
                    // Cargo process. Give the linker a new private inode.
                    paths::remove_file(&linked)?;
                    if link.exec_with_output().is_ok() {
                        publish()?;
                        cache.refresh_executable()?;
                        return Ok(());
                    }
                }
                cache.invalidate()?;
                cache.clear_codegen_temps()?;
            }
            if linked.exists() {
                paths::remove_file(&linked)?;
            }
            let compile_started = paths::set_invocation_time(&dir)?;
            state.running(&rustc);
            if rustc.exec_with_output().is_ok() {
                translate(&compiled_deps, &compiled_info, &rustc, compile_started)?;
                publish()?;
                if let Some(cache) = &cache {
                    cache.initialize(None)?;
                }
                return Ok(());
            }
        }
        // A snippet that cannot be merged may still pass on its own.
        // Let rustdoc diagnose it and retry extraction if the inputs change.
        if let Some(cache) = &cache {
            cache.invalidate()?;
        }
        if extracted_info.is_file() {
            std::fs::copy(&extracted_info, &compiled_info)?;
        }
        // An empty output routes execution back to rustdoc, including when
        // the previous build of this unit produced a runnable executable.
        paths::write(&staged_binary, [])?;
        std::fs::rename(staged_binary, binary)?;
        Ok(())
    }))
}
