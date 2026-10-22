//! Root registration and explicit collection of Ohm shared build caches.

use std::fs::{self, File, OpenOptions};
use std::io::Read as _;
use std::path::{Path, PathBuf};

use anyhow::{Context as _, ensure};

use super::build_cache_gc;
use crate::compiler::Layout;
use crate::util::{CargoResult, GlobalContext, HumanBytes};

const ROOTS: &str = ".ohm-build-roots-v1";

/// Registers a canonical root once, so later invocations can maintain old roots.
pub(crate) fn register_root(gctx: &GlobalContext, root: &Path) -> CargoResult<()> {
    build_cache_gc::metadata_dir(root, false)?;
    let directory = gctx.home().as_path_unlocked().join(ROOTS);
    match fs::create_dir(&directory) {
        Ok(()) => {}
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            fs::create_dir_all(&directory)?
        }
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

/// Collects registered and discoverable legacy roots without loading a workspace.
pub fn collect(gctx: &GlobalContext, root: Option<&Path>, dry_run: bool) -> CargoResult<()> {
    ensure!(
        cfg!(any(target_os = "linux", target_os = "macos")),
        "Ohm build-cache cleanup requires Linux or macOS file locks"
    );
    let directory = gctx.home().as_path_unlocked().join(ROOTS);
    let roots = match root {
        Some(root) => vec![gctx.cwd().join(root).canonicalize()?],
        None => {
            let mut roots = registered_roots(&directory)?;
            if let Some(build) = &gctx.build_config()?.build_dir
                && !build.raw_value().contains("{workspace-")
                && let Some(path) = gctx.build_dir(&gctx.cwd().join("Cargo.toml"))?
            {
                discover_roots(path.as_path_unlocked(), 0, &mut roots)?;
            }
            let mut caches = Vec::new();
            if let Some(home) = gctx.get_env_os("HOME") {
                caches.push(Path::new(home).join(".cache"));
                #[cfg(target_os = "macos")]
                caches.push(Path::new(home).join("Library/Caches"));
            }
            if let Some(cache) = gctx.get_env_os("XDG_CACHE_HOME")
                && Path::new(cache).is_absolute()
            {
                caches.push(PathBuf::from(cache));
            }
            for cache in caches {
                discover_roots(&cache, 4, &mut roots)?;
            }
            roots.sort();
            roots.dedup();
            roots
        }
    };
    let current_ohm = if roots.is_empty() {
        None
    } else {
        gctx.load_global_rustc(None).ok().and_then(|rustc| {
            build_cache_gc::ohm_version(&rustc.verbose_version).map(str::to_owned)
        })
    };
    let mut counts = build_cache_gc::FileCounts::default();
    let mut errors = Vec::new();
    let explicit_root = root.is_some();
    for root in roots {
        gctx.shell()
            .verbose(|shell| shell.status("Checking", root.display()))?;
        // A registered path can be reused for something else, especially under /tmp.
        if !explicit_root
            && fs::symlink_metadata(root.join(Layout::SHARED_REGISTRY_CACHE_MARKER))
                .is_err_and(|error| error.kind() == std::io::ErrorKind::NotFound)
        {
            gctx.shell().status(
                "Skipping",
                format!("{} (shared cache marker is missing)", root.display()),
            )?;
            continue;
        }
        let mut summary = build_cache_gc::Summary::default();
        let result = collect_root(&root, dry_run, current_ohm.as_deref(), &mut summary);
        if let Err(error) = result {
            errors.push(format!("{} ({error:#})", root.display()));
        } else if !dry_run && let Err(error) = register_root(gctx, &root) {
            errors.push(format!("failed to register {} ({error:#})", root.display()));
        }
        counts.include(&summary.counts);
        errors.extend(summary.errors);
        for detail in &summary.details {
            gctx.shell()
                .status(if dry_run { "Would remove" } else { "Removing" }, detail)?;
        }
        for detail in &summary.skipped {
            gctx.shell().status("Skipping", detail)?;
        }
        if summary.busy && summary.skipped.is_empty() {
            gctx.shell()
                .status("Skipping", format!("{} (cache is in use)", root.display()))?;
        }
        gctx.shell().verbose(|shell| {
            for path in &summary.blocking_locks {
                shell.status("Busy lock", path.display())?;
            }
            Ok(())
        })?;
    }
    let file_count = match (counts.files, counts.directories) {
        (0, 1) => "1 directory".to_owned(),
        (0, 2..) => format!("{} directories", counts.directories),
        (1, _) => "1 file".to_owned(),
        (files, _) => format!("{files} files"),
    };
    let byte_count = if counts.bytes == 0 {
        String::new()
    } else {
        format!(", {:.1} total", HumanBytes(counts.bytes))
    };
    gctx.shell().status(
        if dry_run { "Summary" } else { "Removed" },
        format!("{file_count}{byte_count}"),
    )?;
    if dry_run {
        gctx.shell().warn("no files deleted due to --dry-run")?;
    }
    ensure!(
        errors.is_empty(),
        "could not clean the following paths:\n  {}",
        errors.join("\n  ")
    );
    Ok(())
}

/// Finds marked roots near cache-directory tops without traversing artifact trees.
/// Symlinks and inaccessible directories never expand discovery's reach.
fn discover_roots(path: &Path, depth: usize, roots: &mut Vec<PathBuf>) -> CargoResult<()> {
    if !fs::symlink_metadata(path).is_ok_and(|metadata| metadata.is_dir()) {
        return Ok(());
    }
    if fs::symlink_metadata(path.join(Layout::SHARED_REGISTRY_CACHE_MARKER))
        .is_ok_and(|metadata| metadata.is_file())
    {
        roots.push(path.canonicalize()?);
    }
    if depth == 0 || path.join(".cargo-build-lock").exists() {
        return Ok(());
    }
    let Ok(entries) = fs::read_dir(path) else {
        return Ok(());
    };
    for entry in entries {
        let Ok(entry) = entry else { continue };
        if entry.file_type().is_ok_and(|kind| kind.is_dir())
            && !matches!(
                entry.file_name().to_str(),
                Some(".git" | "registry" | "node_modules")
            )
        {
            discover_roots(&entry.path(), depth - 1, roots)?;
        }
    }
    Ok(())
}

/// Drains productive batches, releasing build locks between them.
fn collect_root(
    root: &Path,
    dry_run: bool,
    current_ohm: Option<&str>,
    total: &mut build_cache_gc::Summary,
) -> CargoResult<()> {
    let mut state = build_cache_gc::CollectionState::default();
    if dry_run {
        return build_cache_gc::collect(root, true, current_ohm, &mut state, total);
    }
    loop {
        let mut summary = build_cache_gc::Summary::default();
        let result = build_cache_gc::collect(root, false, current_ohm, &mut state, &mut summary);
        let progress = summary.retired > 0 || summary.deleted_entries > 0 || summary.advanced;
        total.retired += summary.retired;
        total.deleted_entries += summary.deleted_entries;
        total.counts.include(&summary.counts);
        total.errors.extend(summary.errors);
        total.blocking_locks.extend(summary.blocking_locks);
        total.retained = summary.retained;
        total.busy = summary.busy;
        total.pending = summary.pending;
        for detail in summary.skipped {
            if !total.skipped.contains(&detail) {
                total.skipped.push(detail);
            }
        }
        for detail in summary.details {
            if total.details.len() < 32 && !total.details.contains(&detail) {
                total.details.push(detail);
            }
        }
        result?;
        if !progress || !total.pending {
            return Ok(());
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
    fn discovery_finds_nested_marked_roots_without_entering_profiles_or_symlinks() -> CargoResult<()>
    {
        let directory = tempfile::tempdir()?;
        let outer = directory.path().join("ohm-build");
        let nested = outer.join("project");
        let profile = nested.join("debug");
        let payload = profile.join("payload");
        let unmarked = directory.path().join("unmarked");
        for path in [&outer, &nested, &payload, &unmarked] {
            fs::create_dir_all(path)?;
            if path != &unmarked {
                File::create(path.join(Layout::SHARED_REGISTRY_CACHE_MARKER))?;
            }
        }
        File::create(profile.join(".cargo-build-lock"))?;
        let external = tempfile::tempdir()?;
        File::create(external.path().join(Layout::SHARED_REGISTRY_CACHE_MARKER))?;
        symlink(external.path(), directory.path().join("alias"))?;
        let mut roots = Vec::new();
        discover_roots(directory.path(), 4, &mut roots)?;
        roots.sort();
        assert_eq!(roots, [outer.canonicalize()?, nested.canonicalize()?]);
        Ok(())
    }

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
