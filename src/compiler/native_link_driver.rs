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

pub(super) fn install(rustc: &mut ProcessBuilder, cache: &RelinkCachePaths) {
    // A target may live on another volume. Only use a symlink naming this exact
    // Cargo executable inside the unit's own directory. Decline existing foreign entries.
    let driver = match driver_alias(cache) {
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

fn driver_alias(cache: &RelinkCachePaths) -> io::Result<std::path::PathBuf> {
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
    let alias = dir.join("ohm-link-cc");
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
