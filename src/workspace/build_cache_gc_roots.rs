//! Root registration and explicit collection of Ohm shared build caches.

use std::fs::{self, File, OpenOptions};
use std::io::Read as _;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use anyhow::{Context as _, ensure};

use super::build_cache_gc;
use crate::util::{CargoResult, GlobalContext};

const ROOTS: &str = ".ohm-build-roots-v1";

/// Registers a canonical root once, so later invocations can maintain old roots.
pub(crate) fn register_root(gctx: &GlobalContext, root: &Path) -> CargoResult<()> {
    build_cache_gc::metadata_dir(root, false)?;
    let directory = gctx.home().as_path_unlocked().join(ROOTS);
    match fs::create_dir(&directory) {
        Ok(()) => {}
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
        Err(error) => return Err(error.into()),
    }
    validate_directory(&directory)?;
    let path = directory.join(format!("{}.json", crate::util::short_hash(&root)));
    match fs::symlink_metadata(&path) {
        Ok(metadata) => {
            ensure!(metadata.is_file(), "invalid build-root record");
            return Ok(());
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => return Err(error.into()),
    }
    let mut temporary = tempfile::NamedTempFile::new_in(&directory)?;
    serde_json::to_writer(&mut temporary, root)?;
    match temporary.persist_noclobber(&path) {
        Ok(_) => Ok(()),
        Err(error) if error.error.kind() == std::io::ErrorKind::AlreadyExists => {
            ensure!(
                fs::symlink_metadata(&path)?.is_file(),
                "invalid build-root record"
            );
            Ok(())
        }
        Err(error) => Err(error.error.into()),
    }
}

/// Opens a stable root record without following directory or file symlinks.
fn open_regular(path: &Path) -> CargoResult<File> {
    let directory = path
        .parent()
        .context("build-cache metadata has no parent")?;
    let before = validate_directory(directory)?;
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt as _;
        options.custom_flags(libc::O_NOFOLLOW);
    }
    let file = options.open(path)?;
    let opened = file.metadata()?;
    let named = fs::symlink_metadata(path)?;
    ensure!(
        opened.is_file() && named.is_file(),
        "invalid build-cache metadata file"
    );
    let after = validate_directory(directory)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt as _;
        ensure!(
            (opened.dev(), opened.ino()) == (named.dev(), named.ino())
                && (before.dev(), before.ino()) == (after.dev(), after.ino()),
            "build-cache metadata changed while opening it"
        );
    }
    #[cfg(not(unix))]
    let _ = (before, after);
    Ok(file)
}

fn validate_directory(directory: &Path) -> CargoResult<fs::Metadata> {
    let metadata = fs::symlink_metadata(directory)?;
    ensure!(metadata.is_dir(), "invalid build-root registry");
    Ok(metadata)
}

/// Collects registered roots, or one explicit root, without loading a workspace.
pub fn collect(gctx: &GlobalContext, root: Option<&Path>, dry_run: bool) -> CargoResult<()> {
    ensure!(
        cfg!(any(target_os = "linux", target_os = "macos")),
        "Ohm build-cache cleanup requires Linux or macOS file locks"
    );
    let directory = gctx.home().as_path_unlocked().join(ROOTS);
    let roots = match root {
        Some(root) => vec![gctx.cwd().join(root).canonicalize()?],
        None => registered_roots(&directory)?,
    };
    for root in roots {
        let summary = collect_root(&root, dry_run)
            .with_context(|| format!("failed to inspect {}", root.display()))?;
        for detail in &summary.details {
            gctx.shell().status("Cache", detail)?;
        }
        gctx.shell().status(
            if dry_run { "Would clean" } else { "Cleaned" },
            format!(
                "{} namespaces in {} ({} files removed{})",
                summary.retired,
                root.display(),
                summary.deleted_files,
                if summary.busy {
                    "; active consumers, skipped"
                } else if summary.pending {
                    "; retirement pending; run cargo gc again"
                } else {
                    ""
                }
            ),
        )?;
    }
    Ok(())
}

/// Drains productive batches while yielding to new builds and bounding I/O.
fn collect_root(root: &Path, dry_run: bool) -> CargoResult<build_cache_gc::Summary> {
    let started = Instant::now();
    let mut total = build_cache_gc::Summary::default();
    loop {
        let summary = build_cache_gc::collect(root, dry_run)?;
        let progress = summary.retired > 0 || summary.deleted_files > 0;
        total.retired += summary.retired;
        total.deleted_files += summary.deleted_files;
        total.retained = summary.retained;
        total.busy = summary.busy;
        total.pending = summary.pending;
        for detail in summary.details {
            if total.details.len() < 32 && !total.details.contains(&detail) {
                total.details.push(detail);
            }
        }
        if dry_run
            || !progress
            || total.busy
            || !total.pending
            || started.elapsed() >= Duration::from_secs(10)
        {
            return Ok(total);
        }
    }
}

fn registered_roots(directory: &Path) -> CargoResult<Vec<PathBuf>> {
    if !directory.try_exists()? {
        return Ok(Vec::new());
    }
    validate_directory(directory)?;
    let mut roots = Vec::new();
    for entry in fs::read_dir(directory)? {
        let entry = entry?;
        if !entry.file_type()?.is_file()
            || entry
                .path()
                .extension()
                .is_none_or(|extension| extension != "json")
        {
            continue;
        }
        let Ok(file) = open_regular(&entry.path()) else {
            continue;
        };
        let Ok(root) = serde_json::from_reader::<_, PathBuf>(file.take(64 * 1024)) else {
            continue;
        };
        if root.is_absolute()
            && entry.file_name() == format!("{}.json", crate::util::short_hash(&root)).as_str()
            && root.try_exists().unwrap_or(false)
        {
            roots.push(root);
        }
    }
    roots.sort();
    roots.dedup();
    Ok(roots)
}

#[cfg(all(test, any(target_os = "linux", target_os = "macos")))]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;

    #[test]
    fn rejects_symlinked_registry_and_records() -> CargoResult<()> {
        let directory = tempfile::tempdir()?;
        let external = tempfile::tempdir()?;
        let record = external.path().join("record");
        fs::write(&record, b"unchanged")?;
        let link = directory.path().join("record.json");
        symlink(&record, &link)?;
        assert!(open_regular(&link).is_err());
        symlink(external.path(), directory.path().join("registry"))?;
        assert!(open_regular(&directory.path().join("registry/record")).is_err());
        assert_eq!(fs::read(record)?, b"unchanged");
        Ok(())
    }
}
