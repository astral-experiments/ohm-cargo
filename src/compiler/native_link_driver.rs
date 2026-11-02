//! Select Cargo's native-link driver only for a supported, ordinary host binary.

use std::ffi::OsString;
use std::fs;
use std::io;
use std::os::unix::fs::{DirBuilderExt, MetadataExt, symlink};
use std::sync::atomic::{AtomicBool, Ordering};

use super::{BuildRunner, CompileKind, RelinkCachePaths, Unit};
use cargo_util::ProcessBuilder;

// Cargo is also a library. Only the binary that dispatches our alias can serve as a driver.
static CARGO_CLI: AtomicBool = AtomicBool::new(false);

/// Dispatch a driver invocation or enable driver selection in the real Cargo CLI.
pub fn enter_cli() -> Option<i32> {
    let status = super::native_link::run_if_driver();
    if status.is_none() {
        CARGO_CLI.store(true, Ordering::Relaxed);
    }
    status
}

#[cfg(target_os = "macos")]
pub(super) fn supported(build_runner: &BuildRunner<'_, '_>, unit: &Unit) -> bool {
    let bcx = build_runner.bcx;
    let host = "aarch64-apple-darwin";
    let gctx = bcx.gctx;
    let rustc = bcx.rustc();
    if !CARGO_CLI.load(Ordering::Relaxed)
        || !gctx.cli_unstable().ohm_defaults()
        || bcx.host_triple().as_str() != host
        || matches!(unit.kind, CompileKind::Target(t) if t.rustc_target().as_str() != host)
        || bcx.build_config.primary_unit_rustc.is_some()
        || rustc.wrapper.is_some()
        || rustc.workspace_wrapper.is_some()
        || build_runner.compilation.host_linker().is_some()
        || build_runner.compilation.target_linker(unit.kind).is_some()
        || !unit.profile.rustflags.is_empty()
        || bcx
            .extra_args_for(unit)
            .is_some_and(|args| !args.is_empty())
        || super::unit_rustflags_without_ohm_defaults(
            gctx,
            build_runner.rustflags_for_cache_admission(unit),
        )
        .iter()
        .any(|flag| flag != super::OHM_EARLY_METADATA_RUSTFLAG)
    {
        return false;
    }
    true
}

#[cfg(target_os = "macos")]
pub(super) fn install(rustc: &mut ProcessBuilder, cache: &RelinkCachePaths) {
    // A target may live on another volume. Only use a symlink naming this exact
    // Cargo executable inside the unit's own directory. Decline existing foreign entries.
    let driver = match driver_alias(cache, "ohm-link-cc") {
        Ok(p) => p,
        Err(e) => {
            tracing::debug!("native driver alias unavailable: {e}");
            return;
        }
    };
    let mut linker = OsString::from("linker=");
    linker.push(driver);
    rustc.arg("-C").arg(linker);
}

pub(super) fn declared_driver(
    build_runner: &BuildRunner<'_, '_>,
    unit: &Unit,
) -> Option<std::path::PathBuf> {
    let bcx = build_runner.bcx;
    let host = bcx.host_triple().as_str();
    if !CARGO_CLI.load(Ordering::Relaxed)
        || !bcx.gctx.cli_unstable().ohm_defaults()
        || !matches!(host, "x86_64-unknown-linux-gnu" | "aarch64-apple-darwin")
        || !unit.target.is_bin()
        || unit.target.for_host()
        || matches!(unit.kind, CompileKind::Target(t) if t.rustc_target().as_str() != host)
        || bcx.build_config.primary_unit_rustc.is_some()
        || bcx.rustc().wrapper.is_some()
        || bcx.rustc().workspace_wrapper.is_some()
        || !unit.profile.rustflags.is_empty()
        || bcx
            .extra_args_for(unit)
            .is_some_and(|args| !args.is_empty())
        || super::unit_rustflags_without_ohm_defaults(
            bcx.gctx,
            build_runner.rustflags_for_cache_admission(unit),
        )
        .iter()
        .any(|flag| flag != super::OHM_EARLY_METADATA_RUSTFLAG)
    {
        return None;
    }
    let linker = build_runner
        .compilation
        .target_linker(unit.kind)
        .unwrap_or(std::path::Path::new("cc"));
    // rustc selects different flavors for raw linkers and Zig. Only wrap C drivers.
    let name = linker.file_name()?.to_str()?;
    if name == "ld"
        || name.contains("ld.")
        || name.ends_with("-ld")
        || name.contains("lld")
        || name.contains("zig")
    {
        return None;
    }
    Some(linker.to_owned())
}

pub(super) fn declarations<'a>(
    linker: &std::path::Path,
    scripts: impl Iterator<Item = Option<(&'a std::path::Path, &'a super::custom_build::BuildOutput)>>,
) -> Option<(std::path::PathBuf, String)> {
    let mut files = std::collections::BTreeSet::new();
    let mut archives = std::collections::BTreeSet::new();
    for script in scripts {
        let (root, output) = script?;
        if !output.linker_args.is_empty() {
            return None;
        }
        for name in &output.library_links {
            let name = name.strip_prefix("static=")?;
            if !name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._+-".contains(&b))
            {
                return None;
            }
            archives.insert(format!("lib{name}.a"));
        }
        for input in &output.rerun_if_changed {
            let path = root.join(input);
            if !path.is_file() || files.len() >= 1024 {
                return None;
            }
            files.insert(path);
        }
    }
    if archives.is_empty()
        || !archives.iter().all(|name| {
            files
                .iter()
                .any(|p| p.file_name() == Some(std::ffi::OsStr::new(name)))
        })
    {
        return None;
    }
    Some((linker.to_owned(), serde_json::to_string(&files).ok()?))
}

pub(super) fn install_declared(
    rustc: &mut ProcessBuilder,
    cache: &RelinkCachePaths,
    (driver, files): &(std::path::PathBuf, String),
) {
    let Ok(alias) = driver_alias(cache, "ohm-declared-cc") else {
        return;
    };
    let mut arg = OsString::from("linker=");
    arg.push(alias);
    rustc.arg("-C").arg(arg);
    rustc.env(super::native_link::declared::DRIVER, driver);
    rustc.env(super::native_link::declared::WATCHED, files);
}

fn driver_alias(cache: &RelinkCachePaths, name: &str) -> io::Result<std::path::PathBuf> {
    let dir = &cache.objects;
    match fs::DirBuilder::new().mode(0o700).create(dir) {
        Ok(()) => {}
        Err(err) if err.kind() == io::ErrorKind::AlreadyExists => {}
        Err(err) => return Err(err),
    }
    let uid = unsafe { libc::geteuid() };
    let meta = fs::symlink_metadata(dir)?;
    let current = fs::canonicalize(std::env::current_exe()?)?;
    let exe = fs::metadata(&current)?;
    if !meta.is_dir()
        || meta.uid() != uid
        || meta.mode() & 0o022 != 0
        || !exe.is_file()
        || (exe.uid() != uid && exe.uid() != 0)
        || exe.mode() & 0o022 != 0
        || fs::canonicalize(dir)? != *dir
        || !dir.ancestors().chain(current.ancestors().skip(1)).all(|p| {
            fs::symlink_metadata(p).is_ok_and(|m| {
                m.is_dir()
                    && (m.uid() == uid || m.uid() == 0)
                    && (m.mode() & 0o022 == 0 || m.mode() & 0o1000 != 0)
            })
        })
    {
        return Err(io::Error::other("untrusted driver path"));
    }
    let alias = dir.join(name);
    match symlink(&current, &alias) {
        Ok(()) => {}
        Err(err) if err.kind() == io::ErrorKind::AlreadyExists => {}
        Err(err) => return Err(err),
    }
    if fs::read_link(&alias)? != current {
        return Err(io::Error::other("unexpected driver alias"));
    }
    Ok(alias)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::compiler::custom_build::BuildOutput;
    use std::path::Path;

    #[test]
    fn native_driver_requires_an_archive_declaration_and_keeps_private_inputs() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        let linker = Path::new("cc");
        fs::write(root.join("libengine.a"), b"!<arch>\n").unwrap();
        fs::write(root.join("mode"), b"first").unwrap();
        let mut script = BuildOutput {
            library_links: vec!["static=engine".into()],
            rerun_if_changed: vec!["mode".into()],
            ..BuildOutput::default()
        };
        assert!(declarations(linker, [Some((root, &script))].into_iter()).is_none());
        script.rerun_if_changed.push("libengine.a".into());
        let (_, json) = declarations(linker, [Some((root, &script))].into_iter()).unwrap();
        let files: Vec<std::path::PathBuf> = serde_json::from_str(&json).unwrap();
        assert_eq!(files, [root.join("libengine.a"), root.join("mode")]);
    }
}
