use crate::util::GlobalContext;
use crate::util::errors::CargoResult;
use crate::util::session_inputs::TrackedFs;
use cargo_util::paths;
use std::path::{Path, PathBuf};

/// Finds the root `Cargo.toml`.
pub fn find_root_manifest_for_wd(cwd: &Path) -> CargoResult<PathBuf> {
    find_root_manifest(cwd, TrackedFs::new(None))
}

pub(crate) fn find_root_manifest_for_wd_tracked(
    cwd: &Path,
    gctx: &GlobalContext,
) -> CargoResult<PathBuf> {
    find_root_manifest(cwd, gctx.files())
}

fn find_root_manifest(cwd: &Path, files: TrackedFs<'_>) -> CargoResult<PathBuf> {
    let valid_cargo_toml_file_name = "Cargo.toml";
    let invalid_cargo_toml_file_name = "cargo.toml";
    let mut invalid_cargo_toml_path_exists = false;

    for current in paths::ancestors(cwd, None) {
        let manifest = current.join(valid_cargo_toml_file_name);
        if files.exists(&manifest) {
            return Ok(manifest);
        }
        if files.exists(&current.join(invalid_cargo_toml_file_name)) {
            invalid_cargo_toml_path_exists = true;
        }
    }

    if invalid_cargo_toml_path_exists {
        anyhow::bail!(
            "could not find `{}` in `{}` or any parent directory, but found cargo.toml please try to rename it to Cargo.toml",
            valid_cargo_toml_file_name,
            cwd.display()
        )
    } else {
        anyhow::bail!(
            "could not find `{}` in `{}` or any parent directory",
            valid_cargo_toml_file_name,
            cwd.display()
        )
    }
}

/// Returns the path to the `file` in `pwd`, if it exists.
pub fn find_project_manifest_exact(pwd: &Path, file: &str) -> CargoResult<PathBuf> {
    find_project_manifest(pwd, file, TrackedFs::new(None))
}

pub(crate) fn find_project_manifest_exact_tracked(
    pwd: &Path,
    file: &str,
    gctx: &GlobalContext,
) -> CargoResult<PathBuf> {
    find_project_manifest(pwd, file, gctx.files())
}

fn find_project_manifest(pwd: &Path, file: &str, files: TrackedFs<'_>) -> CargoResult<PathBuf> {
    let manifest = pwd.join(file);

    if files.exists(&manifest) {
        Ok(manifest)
    } else {
        anyhow::bail!("Could not find `{}` in `{}`", file, pwd.display())
    }
}
