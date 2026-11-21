//! Build mergeable inline examples as one fingerprinted Cargo doctest unit.
mod generate;

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use cargo_util::{ProcessBuilder, paths};

use super::{
    BuildContext, BuildRunner, FingerprintMethod, JobState, RelinkCachePaths, Unit, Work,
    fingerprint,
};
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
    // Regenerate drivers that relaunch examples through their original path.
    dir.join("dep-doctest-extraction-v11")
}

/// Prepares both compiler commands with the dependencies of the doctest unit.
/// Must run after the build scripts have completed and the runtime environment is collected.
pub(super) fn prepare(br: &BuildRunner<'_, '_>, unit: &Unit, force: bool) -> CargoResult<Work> {
    let bcx = br.bcx;
    let dir = br.files().fingerprint_dir(unit);
    let binary = br.outputs(unit)?[0].path.clone();
    let scripts = br.find_build_script_metadatas(unit);
    let mut unstable_opts = false;
    let args = br.doctest_args(unit, scripts.as_deref(), &mut unstable_opts)?;
    let env = super::artifact::get_env(br, unit, br.unit_deps(unit))?;
    let mut rustdoc = br.compilation.rustdoc_process(unit, scripts.as_ref())?;
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
        .cached_doctest_process(&compiler, unit, scripts.as_ref())?;
    if bcx.gctx.extra_verbose() {
        rustc.display_env_vars();
    }
    let (_, cwd) = path_args(bcx.ws, unit);
    for cmd in [&mut rustdoc, &mut rustc] {
        cmd.cwd(&cwd).inherit_jobserver(&br.jobserver);
        for (key, value) in &env {
            cmd.env(key, value);
        }
        for path in &br.compilation.native_dirs {
            cmd.arg("-L").arg(path);
        }
        cmd.args(&args);
        if unstable_opts {
            cmd.arg("-Zunstable-options");
        }
        unit.kind.add_target_arg(cmd);
        if let Some(linker) = br.compilation.target_linker(unit.kind) {
            let mut flag = OsString::from("linker=");
            flag.push(linker);
            cmd.arg("-C").arg(flag);
        }
        if unit.profile.panic != PanicStrategy::Unwind {
            cmd.arg("-C").arg(format!("panic={}", unit.profile.panic));
        }
        if super::unit_fingerprint_method(br, unit)? == FingerprintMethod::Content {
            cmd.arg("-Zchecksum-hash-algorithm=blake3");
        }
    }
    add_path_args(bcx.ws, unit, &mut rustdoc);
    rustdoc.arg("--crate-name").arg(unit.target.crate_name());
    rustdoc.args(unit.pkg.manifest().lint_rustflags());
    rustdoc.args(&["-Zunstable-options", "--cfg", "doctest"]);
    let source = dir.join("doctest_bundle_2024.rs");
    let compiled_deps = dir.join("doctests.d");
    let extracted_deps = dir.join("extraction.d");
    let driver_source = dir.join("doctest-driver.rs");
    let examples_lib = dir.join("lib__ohm_doctest_examples.rlib");
    rustc.args(&["--edition=2024", "-Ccodegen-units=1"]);
    let mut examples = rustc.clone();
    let mut emit = OsString::from("--emit=link,dep-info=");
    emit.push(&compiled_deps);
    examples.arg("--crate-type=rlib");
    examples.arg(emit).arg(&source).arg("-o").arg(&examples_lib);

    // The driver sees the doctest unit's direct dependencies through the examples rlib.
    // The per-unit layout normally omits their directories from rustc's transitive search path.
    if bcx.gctx.cli_unstable().build_dir_new_layout {
        let directories: std::collections::BTreeSet<_> = br
            .unit_deps(unit)
            .iter()
            .filter(|dep| dep.unit.target.is_linkable() && !dep.unit.artifact.is_true())
            .map(|dep| br.files().deps_dir(&dep.unit))
            .collect();
        for directory in directories {
            let mut search = OsString::from("dependency=");
            search.push(directory);
            rustc.arg("-L").arg(search);
        }
    }
    let mut examples_extern = OsString::from("__ohm_doctest_examples=");
    examples_extern.push(&examples_lib);
    rustc
        .arg("--crate-name=__ohm_doctest_driver")
        .arg("--extern")
        .arg(examples_extern);
    rustc.arg("--check-cfg=cfg(ohm_borrowed_libtest)");
    let version = &bcx.rustc().version;
    if (version.major, version.minor) >= (1, 100) {
        rustc.arg("--cfg=ohm_borrowed_libtest");
    }
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

    // Workspace selection can change these paths without changing the unit or its
    // dependencies. The generated sources and objects belong to this search path.
    let search_hash = crate::util::hash_u64((
        &br.compilation.native_dirs,
        rustdoc.get_env(paths::dylib_path_envvar()),
    ))
    .to_le_bytes();
    let search_stamp = dir.join("doctest-search-path");
    let target = unit.target.clone();
    let pkg_root = unit.pkg.root().to_owned();
    let build_root = br.files().build_root(unit);
    let env_config = Arc::clone(bcx.gctx.env_config()?);
    let local = unit.is_local();
    let compiled_info = fingerprint::dep_info_loc(br, unit);
    let extracted_info = extraction_dep_info(&dir);
    let fingerprint = Arc::clone(&br.fingerprints[unit]);

    Ok(Work::new(move |state| {
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
                    false,
                )?;
                paths::set_file_time_no_err(encoded, timestamp);
                Ok(())
            };
        let staging = tempfile::tempdir_in(binary.parent().unwrap())?;
        let staged_binary = staging.path().join("doctest");
        // The final link can read native archives outside Cargo's dependency
        // graph. Reuse the extraction and object files when Cargo has
        // validated both sets of Rust inputs, but let the linker resolve them.
        let inputs_unchanged = !force
            && std::fs::read(&search_stamp).is_ok_and(|recorded| recorded == search_hash)
            && source.is_file()
            && driver_source.is_file()
            && examples_lib.is_file()
            && !fingerprint.observes_foreign_span()
            && (fingerprint.can_reuse_doctest_codegen()
                || (cache.is_some()
                    && fingerprint::can_relink_due_to_early_cutoff(&fingerprint, &relinkable)));
        if !inputs_unchanged {
            if search_stamp.exists() {
                paths::remove_file(&search_stamp)?;
            }
            let mut extract = rustdoc.clone();
            // Make rustdoc's implicit allow(unused) explicit during extraction. An
            // item with its own doc(test(attr(allow(unused)))) then has a second
            // attribute, so we can distinguish its separate bundle in the JSON.
            extract.args(&[
                "--output-format=doctest",
                "-Zcrate-attr=doc(test(attr(allow(unused))))",
            ]);
            state.running(&extract);
            let generated = extract
                .exec_with_output()
                .ok()
                .filter(|output| output.stderr.is_empty())
                .and_then(|output| generate::harness(&output.stdout, &target.crate_name()));

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
            paths::link_or_copy(&linked, &staged_binary)?;
        } else {
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
        }
        std::fs::rename(staged_binary, binary)?;
        if !inputs_unchanged {
            paths::write(&search_stamp, search_hash)?;
        }
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
    let extern_paths_hash = cache.and_then(|_| super::relink_extern_paths_hash(command));
    if let Some(cache) = cache {
        if reuse && cache.is_valid(extern_paths_hash) {
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
        cache.initialize(extern_paths_hash, None)?;
    }
    Ok(CompileStatus::Compiled)
}
