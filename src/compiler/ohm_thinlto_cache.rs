//! Manage optional backend objects separately from Cargo's required build artifacts.

use std::ffi::OsString;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};

use cargo_platform::Cfg;
use cargo_util::ProcessBuilder;

use crate::util::errors::CargoResult;
use crate::workspace::build_cache_gc;

use super::{BuildRunner, CompileMode, Unit};

const MAX_BYTES: u64 = 2 * 1024 * 1024 * 1024;
const MAX_ENTRIES: usize = 100_000;
const MAX_AGE: Duration = Duration::from_secs(30 * 24 * 60 * 60);

pub(super) struct Cache {
    root: PathBuf,
    shared: bool,
}

pub(super) fn configure(runner: &BuildRunner<'_, '_>, unit: &Unit, command: &mut ProcessBuilder) {
    let bcx = runner.bcx;
    if !bcx.gctx.cli_unstable().ohm_thinlto_cache()
        || !matches!(unit.mode, CompileMode::Build | CompileMode::Test)
        || unit.is_std
        || unit.target.for_host()
        || unit.profile.incremental
        || unit.profile.codegen_backend.is_some()
        || bcx.rustc().wrapper.is_some()
        || bcx.rustc().workspace_wrapper.is_some()
        || bcx.build_config.primary_unit_rustc.is_some()
        || !bcx.target_data.cfg(unit.kind).iter().any(
            |cfg| matches!(cfg, Cfg::KeyPair(key, value) if key == "target_os" && value == "linux"),
        )
        || !eligible_args(command.get_args())
        || !bcx.rustc().supports_ohm_thinlto_cache(bcx.gctx)
    {
        return;
    }

    let cache = runner.thinlto_cache.get_or_init(|| {
        if let Some(usage) = &runner.context_use {
            // Reuse the enrolled compiler context and its consumer lease. Rustc's
            // inner keys still distinguish backend options and individual objects.
            return Cache {
                root: bcx
                    .ws
                    .configured_build_dir()
                    .join(build_cache_gc::THINLTO)
                    .join(usage.context())
                    .into_path_unlocked(),
                shared: true,
            };
        }
        // If provenance could not be recorded, keep optional state private too.
        Cache {
            root: bcx
                .ws
                .build_dir()
                .join(build_cache_gc::THINLTO)
                .into_path_unlocked(),
            shared: false,
        }
    });
    let mut option = OsString::from("-Zthinlto-cache=");
    option.push(&cache.root);
    command.arg(option);
}

/// Inspect the final arguments, including profile and `cargo rustc` overrides.
/// Rustc remains responsible for rejecting unsupported backend configurations.
fn eligible_args<'a>(args: impl IntoIterator<Item = &'a OsString>) -> bool {
    let mut lto = None;
    let mut optimized = false;
    let mut single_cgu = false;
    let mut args = args.into_iter();
    while let Some(arg) = args.next() {
        let Some(arg) = arg.to_str() else {
            return false;
        };
        if arg.starts_with('@') {
            return false;
        }
        let (unstable, option) = if matches!(arg, "-C" | "--codegen" | "-Z") {
            (arg == "-Z", args.next().and_then(|arg| arg.to_str()))
        } else if let Some(option) = arg.strip_prefix("-Z") {
            (true, Some(option))
        } else {
            (
                false,
                arg.strip_prefix("-C")
                    .or_else(|| arg.strip_prefix("--codegen=")),
            )
        };
        let Some(option) = option else { continue };
        let (name, value) = option.split_once('=').unwrap_or((option, ""));
        match (unstable, name.replace('_', "-").as_str()) {
            (true, "thinlto-cache" | "thinlto" | "codegen-backend") => return false,
            (false, "incremental" | "linker-plugin-lto") => return false,
            (false, "lto") => lto = Some(value),
            (false, "opt-level") => optimized = value != "0",
            (false, "codegen-units") => single_cgu = value == "1",
            _ => {}
        }
    }
    match lto {
        Some("thin") => true,
        None => optimized && !single_cgu,
        _ => false,
    }
}

impl Drop for Cache {
    fn drop(&mut self) {
        if self.shared {
            // Shared objects are collected only by `cargo gc`.
            return;
        }
        // Run once after the graph finishes, including failed builds. Concurrent
        // writers publish atomically; an evicted object is just a compiler miss.
        if let Err(error) = prune(&self.root, MAX_BYTES, MAX_ENTRIES, MAX_AGE) {
            tracing::debug!(
                "unable to prune ThinLTO cache {}: {error}",
                self.root.display()
            );
        }
    }
}

fn is_key(name: &str) -> bool {
    name.len() == 32 && name.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn prune(root: &Path, max_bytes: u64, max_entries: usize, max_age: Duration) -> CargoResult<()> {
    // Do not create a directory for builds whose backend never used the cache.
    if !root
        .symlink_metadata()
        .is_ok_and(|metadata| metadata.is_dir())
    {
        return Ok(());
    }
    let Some(_lock) = build_cache_gc::try_lock(&root.join(".prune-lock"), true)? else {
        return Ok(());
    };

    let now = SystemTime::now();
    let expired = |modified| now.duration_since(modified).is_ok_and(|age| age > max_age);
    let mut entries = Vec::new();
    let mut directories = Vec::new();
    let mut bytes = 0u64;
    for namespace in fs::read_dir(root)? {
        let namespace = namespace?;
        if !namespace.file_type()?.is_dir() || !namespace.file_name().to_str().is_some_and(is_key) {
            continue;
        }
        let directory = namespace.path();
        for entry in fs::read_dir(&directory)? {
            let entry = entry?;
            let name = entry.file_name();
            let Some(name) = name.to_str() else { continue };
            let kind = entry.file_type()?;
            if kind.is_dir() && name.starts_with("ohm-thinlto-") {
                if entry.metadata()?.modified().is_ok_and(expired) {
                    let _ = fs::remove_dir_all(entry.path());
                }
            } else if kind.is_file() && name.strip_suffix(".cache").is_some_and(is_key) {
                let metadata = entry.metadata()?;
                bytes = bytes.saturating_add(metadata.len());
                entries.push((metadata.modified()?, entry.path(), metadata.len()));
            }
        }
        directories.push(directory);
    }

    // Successful hits refresh mtime in rustc, so hot objects survive pruning.
    entries.sort_unstable();
    let mut count = entries.len();
    for (modified, path, size) in entries {
        if bytes <= max_bytes && count <= max_entries && !expired(modified) {
            break;
        }
        if fs::remove_file(path).is_ok() {
            bytes = bytes.saturating_sub(size);
            count -= 1;
        }
    }
    for directory in directories {
        let _ = fs::remove_dir(directory);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::workspace::features::CliUnstable;

    #[test]
    fn defaults_and_opt_out() {
        for defaults in [false, true] {
            for override_ in [None, Some(false), Some(true)] {
                let options = CliUnstable {
                    ohm_defaults: Some(defaults),
                    ohm_thinlto_cache: override_,
                    ..CliUnstable::default()
                };
                assert_eq!(options.ohm_thinlto_cache(), override_.unwrap_or(defaults));
            }
        }
        let mut options = CliUnstable {
            ohm_defaults: Some(true),
            ..CliUnstable::default()
        };
        options
            .parse(&["ohm-thinlto-cache=no".into()], true)
            .unwrap();
        assert!(!options.ohm_thinlto_cache());
        options
            .parse(&["ohm-thinlto-cache=yes".into()], true)
            .unwrap();
        assert!(options.ohm_thinlto_cache());
    }

    #[test]
    fn final_lto_arguments_and_explicit_cache_override() {
        for (args, expected) in [
            ("-C lto=thin", true),
            ("-Clto=thin -Ccodegen-units=1", true),
            ("-Copt-level=3", true),
            ("-Copt-level=3 -Clto=no", false),
            ("-Copt-level=3 -Ccodegen-units=1", false),
            ("-Clto=thin -Clto=fat", false),
            ("-Clto=thin --codegen lto=off", false),
            ("--codegen=lto=thin", true),
            ("-Copt-level=0", false),
            ("-Clto=thin -Cincremental=inc", false),
            ("-Clto=thin -Clinker-plugin-lto", false),
            ("-Clto=thin -Zthinlto-cache=mine", false),
            ("-Clto=thin -Z thinlto_cache=mine", false),
            ("-Clto=thin @arguments", false),
        ] {
            let args = args
                .split_whitespace()
                .map(OsString::from)
                .collect::<Vec<_>>();
            assert_eq!(eligible_args(&args), expected, "{args:?}");
        }
    }

    fn entry(root: &Path, key: u32, size: usize, age: Duration) -> PathBuf {
        let directory = root.join(format!("{:032x}", key % 2));
        fs::create_dir_all(&directory).unwrap();
        let path = directory.join(format!("{key:032x}.cache"));
        fs::write(&path, vec![0; size]).unwrap();
        fs::File::open(&path)
            .unwrap()
            .set_modified(SystemTime::now() - age)
            .unwrap();
        path
    }

    #[test]
    fn evicts_oldest_across_namespaces_and_expires_unused_entries() {
        let root = tempfile::tempdir().unwrap();
        let expired = entry(root.path(), 0, 1, MAX_AGE + Duration::from_secs(10));
        let oldest = entry(root.path(), 1, 8, Duration::from_secs(20));
        let hot = entry(root.path(), 2, 8, Duration::ZERO);
        prune(root.path(), 8, MAX_ENTRIES, MAX_AGE).unwrap();
        assert!(!expired.exists());
        assert!(!oldest.exists());
        assert!(hot.exists());
        // A count limit also bounds caches made of tiny objects.
        prune(root.path(), MAX_BYTES, 0, MAX_AGE).unwrap();
        assert!(!hot.exists());
    }

    #[test]
    fn pruning_is_nonblocking_and_leaves_unrecognized_files_alone() {
        let root = tempfile::tempdir().unwrap();
        let cached = entry(root.path(), 0, 8, Duration::ZERO);
        let unrelated = cached.parent().unwrap().join("keep.txt");
        fs::write(&unrelated, "unrelated").unwrap();
        let lock = build_cache_gc::try_lock(&root.path().join(".prune-lock"), true)
            .unwrap()
            .unwrap();
        prune(root.path(), 0, 0, MAX_AGE).unwrap();
        assert!(cached.exists());
        drop(lock);
        prune(root.path(), 0, 0, MAX_AGE).unwrap();
        assert!(!cached.exists());
        assert!(unrelated.exists());
    }

    #[test]
    fn shared_cache_waits_for_explicit_gc() {
        let root = tempfile::tempdir().unwrap();
        let cached = entry(root.path(), 0, 8, MAX_AGE + Duration::from_secs(1));
        drop(Cache {
            root: root.path().to_path_buf(),
            shared: true,
        });
        assert!(cached.exists());
        assert!(!root.path().join(".prune-lock").exists());
        drop(Cache {
            root: root.path().to_path_buf(),
            shared: false,
        });
        assert!(!cached.exists());
    }

    #[test]
    #[cfg(unix)]
    fn pruning_does_not_follow_symlinks() {
        let root = tempfile::tempdir().unwrap();
        let other = tempfile::tempdir().unwrap();
        let cached = entry(other.path(), 0, 8, Duration::ZERO);
        std::os::unix::fs::symlink(cached.parent().unwrap(), root.path().join("0".repeat(32)))
            .unwrap();
        prune(root.path(), 0, 0, MAX_AGE).unwrap();
        assert!(cached.exists());
    }
}
