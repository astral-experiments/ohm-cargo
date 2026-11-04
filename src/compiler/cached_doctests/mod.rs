//! Build mergeable inline examples as one fingerprinted Cargo doctest unit.
mod generate;

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use cargo_util::{ProcessBuilder, paths};

use super::{BuildContext, BuildRunner, JobState, RelinkCachePaths, Unit, Work, fingerprint};
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
        && super::compilation::host_tests_run_directly(bcx)
        && super::build_runner::uses_toolchain_rustdoc(bcx)
}

/// Encoded dependencies of the crate under rustdoc's cfgs, separate from the
/// dependencies rustc reports for the extracted examples themselves.
pub(super) fn extraction_dep_info(dir: &Path) -> PathBuf {
    // Recompile cached snippets that could resolve an undefined name to the generated dispatcher.
    dir.join("dep-doctest-extraction-v5")
}

/// Prepares both compiler commands with the dependencies of the doctest unit.
/// Build-script output is added by the job once those dependencies have finished.
pub(super) fn prepare(br: &BuildRunner<'_, '_>, unit: &Unit, force: bool) -> CargoResult<Work> {
    let bcx = br.bcx;
    let dir = br.files().fingerprint_dir(unit);
    let binary = br.outputs(unit)?[0].path.clone();
    let mut rustdoc = br.compilation.rustdoc_process(unit, None)?;
    // Rustdoc compiles examples with the sysroot compiler, independently of Cargo's wrappers.
    let compiler = bcx
        .target_data
        .info(unit.kind)
        .sysroot
        .join("bin")
        .join("rustc")
        .with_extension(std::env::consts::EXE_EXTENSION);
    let mut rustc = br
        .compilation
        .configure_rustc_process(unit, ProcessBuilder::new(compiler))?;
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
    let driver_source = dir.join("doctest-driver.rs");
    let examples_lib = dir.join("lib__ohm_doctest_examples.rlib");
    rustc.args(&["--edition=2024", "-Ccodegen-units=1"]);
    let mut examples = rustc.clone();
    let mut emit = OsString::from("--emit=link,dep-info=");
    emit.push(&compiled_deps);
    examples.args(&["--crate-type=rlib", "--crate-name", "rust_out"]);
    examples.arg(emit).arg(&source).arg("-o").arg(&examples_lib);

    let mut examples_extern = OsString::from("__ohm_doctest_examples=");
    examples_extern.push(&examples_lib);
    rustc
        .arg("--crate-name=__ohm_doctest_driver")
        .arg("--extern")
        .arg(examples_extern);
    let unstable = bcx.gctx.cli_unstable();
    let check_links = (unstable.ohm_defaults() || unstable.relink_only())
        && bcx
            .rustc()
            .supports_relink_input_checks(bcx.gctx, bcx.ws.is_member(&unit.pkg));
    if check_links {
        rustc.arg("-Zohm-check-relink-inputs");
        examples.arg("-Zohm-check-relink-inputs");
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
    let examples_cache = cache
        .as_ref()
        .map(|_| RelinkCachePaths::new(examples_lib.clone()));
    if let Some(cache) = &examples_cache {
        cache.preserve_codegen(&mut examples);
    }
    let relinkable = super::relinkable_dependencies(br, unit);
    rustc.arg(&driver_source).arg("-o").arg(&linked);

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
            for cmd in [&mut rustdoc, &mut examples, &mut rustc] {
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
                    false,
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
            && source.is_file()
            && driver_source.is_file()
            && examples_lib.is_file()
            && !fingerprint.observes_foreign_span()
            && (fingerprint.can_reuse_doctest_codegen()
                || (cache.is_some()
                    && fingerprint::can_relink_due_to_early_cutoff(&fingerprint, &relinkable)));
        if !inputs_unchanged {
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
                let generated = generated.unwrap_or_default();
                paths::write_if_changed(&driver_source, generated.driver)?;
                paths::write_if_changed(&source, generated.examples)?;
            } else {
                // Never admit an executable whose extraction inputs are unknown.
                if extracted_info.exists() {
                    paths::remove_file(&extracted_info)?;
                }
                paths::write_if_changed(&source, "")?;
            }
        }
        let mut runnable = source.metadata()?.len() != 0;
        if runnable {
            // An inline #[link] can bundle a native archive into the example library.
            // Reassemble the library before linking the driver so both see current inputs.
            let compile_started = paths::set_invocation_time(&dir)?;
            match compile(
                state,
                &examples,
                &source,
                &examples_lib,
                examples_cache.as_ref(),
                inputs_unchanged,
            )? {
                CompileStatus::Compiled => {
                    translate(&compiled_deps, &compiled_info, &examples, compile_started)?
                }
                CompileStatus::Relinked => {}
                CompileStatus::Failed => {
                    // Keep using rustdoc until a change triggers a fresh extraction.
                    paths::write_if_changed(&source, "")?;
                    runnable = false;
                }
            }
        }
        if runnable
            && !matches!(
                compile(
                    state,
                    &rustc,
                    &driver_source,
                    &linked,
                    cache.as_ref(),
                    inputs_unchanged
                )?,
                CompileStatus::Failed
            )
        {
            publish()?;
            return Ok(());
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

enum CompileStatus {
    Compiled,
    Relinked,
    Failed,
}

/// Builds a doctest artifact, reusing validated Rust objects while resolving native inputs afresh.
fn compile(
    state: &JobState<'_, '_>,
    command: &ProcessBuilder,
    source: &Path,
    output: &Path,
    cache: Option<&RelinkCachePaths>,
    reuse: bool,
) -> CargoResult<CompileStatus> {
    if let Some(cache) = cache {
        if reuse && cache.is_valid() {
            let mut link = command.clone();
            assert!(link.replace_arg(source, &cache.rlink));
            link.arg("-Zlink-only");
            state.running(&link);
            // Give the linker a new inode if an earlier doctest is still running.
            paths::remove_file(output)?;
            if link.exec_with_output().is_ok() {
                cache.refresh_executable()?;
                return Ok(CompileStatus::Relinked);
            }
        }
        cache.invalidate()?;
        cache.clear_codegen_temps()?;
    }
    if output.exists() {
        paths::remove_file(output)?;
    }
    state.running(command);
    if command.exec_with_output().is_err() {
        return Ok(CompileStatus::Failed);
    }
    if let Some(cache) = cache {
        cache.initialize(None)?;
    }
    Ok(CompileStatus::Compiled)
}
