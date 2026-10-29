//! Root registration and explicit collection of Ohm shared build caches.

use std::fmt;
use std::fs::{self, File};
use std::io::Read as _;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant, SystemTime};

use anyhow::{Context as _, ensure};
use cargo_util_terminal::Verbosity;

use super::build_cache_gc;
use crate::compiler::Layout;
use crate::util::{CargoResult, GlobalContext, HumanBytes, Progress, ProgressStyle};

const ROOTS: &str = ".ohm-build-roots-v1";

/// A cutoff that never advances during collection, even when a later batch starts.
pub(crate) struct GcAge {
    cutoff: Option<SystemTime>,
    max_age: Duration,
    started: Option<Instant>,
    label: String,
}

impl GcAge {
    pub(crate) fn new(now: SystemTime, max_age: Duration) -> Self {
        use jiff::fmt::friendly::{Designator, Spacing, SpanPrinter};

        let started = Instant::now();
        let printer = SpanPrinter::new()
            .designator(Designator::Verbose)
            .spacing(Spacing::BetweenUnitsAndDesignators);
        let units = jiff::SpanRound::new()
            .largest(jiff::Unit::Week)
            .days_are_24_hours();
        let label = jiff::Span::try_from(max_age)
            .and_then(|span| span.round(units))
            .map(|span| printer.span_to_string(&span))
            .unwrap_or_else(|_| printer.unsigned_duration_to_string(&max_age));
        let cutoff = now.checked_sub(max_age);
        Self {
            cutoff,
            max_age,
            started: cutoff.map(|_| started),
            label,
        }
    }

    /// Recheck under the lease. After a clock change, a build made since GC
    /// started must still fall after the cutoff in the new clock epoch.
    pub(crate) fn recheck(&mut self) {
        if let Some(started) = self.started {
            self.recheck_at(SystemTime::now(), started.elapsed());
        }
    }

    fn recheck_at(&mut self, now: SystemTime, elapsed: Duration) {
        let start = now.checked_sub(elapsed);
        self.cutoff = self
            .cutoff
            .min(start.and_then(|time| time.checked_sub(self.max_age)));
    }

    /// Tests that supply their own wall time can freeze it between collection batches.
    #[cfg(test)]
    pub(crate) fn simulated(now: SystemTime, max_age: Duration) -> Self {
        Self {
            started: None,
            ..Self::new(now, max_age)
        }
    }

    pub(crate) fn cutoff(&self) -> Option<SystemTime> {
        self.cutoff
    }

    pub(crate) fn expired(&self, last_used: SystemTime) -> bool {
        self.cutoff.is_some_and(|cutoff| last_used <= cutoff)
    }
}

impl fmt::Display for GcAge {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.label)
    }
}

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
pub(crate) fn open_regular(path: &Path) -> CargoResult<File> {
    let directory = path
        .parent()
        .context("build-cache metadata has no parent")?;
    let before = validate_directory(directory)?;
    let file = cargo_util::paths::open_regular(path)?;
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
pub fn collect(
    gctx: &GlobalContext,
    root: Option<&Path>,
    dry_run: bool,
    max_age: Duration,
) -> CargoResult<()> {
    let mut age = GcAge::new(SystemTime::now(), max_age);
    ensure!(
        cfg!(any(target_os = "linux", target_os = "macos")),
        "Ohm build-cache cleanup requires Linux or macOS file locks"
    );
    let directory = gctx.home().as_path_unlocked().join(ROOTS);
    let mut errors = Vec::new();
    let mut register_roots = !dry_run;
    let mut counts = build_cache_gc::FileCounts::default();
    let mut progress = Progress::with_style(
        if dry_run { "Scanning" } else { "Cleaning" },
        ProgressStyle::Indeterminate,
        gctx,
    );
    if gctx.shell().verbosity() == Verbosity::Quiet {
        progress.disable();
    }
    let show_progress = progress.is_enabled();
    let mut progress_result = Ok(());
    let mut update = |counts: &build_cache_gc::FileCounts| {
        if progress_result.is_ok() && progress.update_allowed() {
            let action = if dry_run { "eligible" } else { "removed" };
            progress_result = progress.tick_now(
                0,
                0,
                &format!(
                    " {}, {:.1} {action}",
                    entry_count(counts),
                    HumanBytes(counts.bytes)
                ),
            );
        }
    };
    let roots = match root {
        Some(root) => vec![gctx.cwd().join(root).canonicalize()?],
        None => {
            let mut tick = || update(&counts);
            let mut roots = match registered_roots(&directory, &mut tick) {
                Ok(roots) => roots,
                Err(error) => {
                    errors.push(format!(
                        "failed to read {} ({error:#})",
                        directory.display()
                    ));
                    register_roots = false;
                    Vec::new()
                }
            };
            if let Some(build) = &gctx.build_config()?.build_dir
                && !build.raw_value().contains("{workspace-")
                && let Some(path) = gctx.build_dir(&gctx.cwd().join("Cargo.toml"))?
            {
                discover_roots(path.as_path_unlocked(), 0, &mut roots, &mut tick)?;
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
                discover_roots(&cache, 4, &mut roots, &mut tick)?;
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
    enum Cache<'a> {
        Shared(&'a Path),
        #[cfg(any(target_os = "linux", target_os = "macos"))]
        Private(&'a [build_cache_gc::worktrees::registry::ManagedTarget]),
    }
    let caches = roots.iter().map(|root| Cache::Shared(root.as_path()));
    #[cfg(any(target_os = "linux", target_os = "macos"))]
    let targets = if root.is_some() {
        Vec::new()
    } else {
        match build_cache_gc::worktrees::registry::worktrees(gctx, dry_run, &mut || update(&counts))
        {
            Ok(targets) => targets,
            Err(error) => {
                errors.push(format!(
                    "failed to read private target registry ({error:#})"
                ));
                Vec::new()
            }
        }
    };
    #[cfg(any(target_os = "linux", target_os = "macos"))]
    let moving_release = if targets.is_empty() {
        None
    } else {
        build_cache_gc::worktrees::provenance::current_moving_release(gctx)
    };
    #[cfg(any(target_os = "linux", target_os = "macos"))]
    let caches = caches.chain(
        targets
            .chunk_by(|left, right| left.target == right.target)
            .map(Cache::Private),
    );
    let explicit_root = root.is_some();
    age.recheck();
    for cache in caches {
        let root = match &cache {
            Cache::Shared(root) => *root,
            #[cfg(any(target_os = "linux", target_os = "macos"))]
            Cache::Private(owners) => &owners[0].target,
        };
        gctx.shell()
            .verbose(|shell| shell.status("Checking", root.display()))?;
        // A registered path can be reused for something else, especially under /tmp.
        if matches!(&cache, Cache::Shared(_))
            && !explicit_root
            && fs::symlink_metadata(root.join(Layout::SHARED_REGISTRY_CACHE_MARKER))
                .is_err_and(|error| error.kind() == std::io::ErrorKind::NotFound)
        {
            gctx.shell().status(
                "Skipping",
                format!("{} (shared cache marker is missing)", root.display()),
            )?;
            continue;
        }
        let mut summary = build_cache_gc::Summary {
            counts,
            progress: show_progress.then_some(&mut update),
            ..Default::default()
        };
        let result = match &cache {
            Cache::Shared(_) => collect_root(
                root,
                dry_run,
                &mut age,
                current_ohm.as_deref(),
                &mut summary,
            ),
            #[cfg(any(target_os = "linux", target_os = "macos"))]
            Cache::Private(owners) => build_cache_gc::worktrees::collect(
                owners,
                &targets,
                &roots,
                dry_run,
                &mut age,
                moving_release.as_ref(),
                &mut summary,
            ),
        };
        if let Err(error) = result {
            errors.push(format!("{} ({error:#})", root.display()));
        } else if matches!(&cache, Cache::Shared(_))
            && register_roots
            && let Err(error) = register_root(gctx, root)
        {
            errors.push(format!("failed to register {} ({error:#})", root.display()));
        }
        counts = summary.counts;
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
    drop(progress);
    let byte_count = if counts.bytes == 0 {
        String::new()
    } else {
        format!(", {:.1} total", HumanBytes(counts.bytes))
    };
    gctx.shell().status(
        if dry_run { "Summary" } else { "Removed" },
        format!("{}{byte_count}", entry_count(&counts)),
    )?;
    if dry_run {
        gctx.shell().warn("no files deleted due to --dry-run")?;
    }
    ensure!(
        errors.is_empty(),
        "could not clean the following paths:\n  {}",
        errors.join("\n  ")
    );
    progress_result.context("failed to display cleanup progress")
}

fn entry_count(counts: &build_cache_gc::FileCounts) -> String {
    match (counts.files, counts.directories) {
        (0, 1) => "1 directory".to_owned(),
        (0, 2..) => format!("{} directories", counts.directories),
        (1, _) => "1 file".to_owned(),
        (files, _) => format!("{files} files"),
    }
}

/// Finds marked roots near cache-directory tops without traversing artifact trees.
/// Symlinks and inaccessible directories never expand discovery's reach.
fn discover_roots(
    path: &Path,
    depth: usize,
    roots: &mut Vec<PathBuf>,
    tick: &mut dyn FnMut(),
) -> CargoResult<()> {
    tick();
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
            discover_roots(&entry.path(), depth - 1, roots, tick)?;
        }
    }
    Ok(())
}

/// Drains productive batches, releasing build locks between them.
fn collect_root(
    root: &Path,
    dry_run: bool,
    age: &mut GcAge,
    current_ohm: Option<&str>,
    total: &mut build_cache_gc::Summary<'_>,
) -> CargoResult<()> {
    let mut state = build_cache_gc::CollectionState::default();
    if dry_run {
        return build_cache_gc::collect(root, true, age, current_ohm, &mut state, total);
    }
    loop {
        let mut summary = build_cache_gc::Summary {
            counts: std::mem::take(&mut total.counts),
            progress: total.progress.take(),
            ..Default::default()
        };
        let result =
            build_cache_gc::collect(root, false, age, current_ohm, &mut state, &mut summary);
        let progress = summary.retired > 0 || summary.deleted_entries > 0 || summary.advanced;
        total.retired += summary.retired;
        total.deleted_entries += summary.deleted_entries;
        total.counts = summary.counts;
        total.progress = summary.progress;
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

fn registered_roots(directory: &Path, tick: &mut dyn FnMut()) -> CargoResult<Vec<PathBuf>> {
    if !directory.try_exists()? {
        return Ok(Vec::new());
    }
    validate_directory(directory)?;
    let mut roots = Vec::new();
    for entry in fs::read_dir(directory)? {
        tick();
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
    fn the_cutoff_only_moves_earlier_and_includes_the_exact_boundary() {
        let hour = Duration::from_hours(1);
        let start = SystemTime::UNIX_EPOCH + hour * 4;
        let mut age = GcAge::new(start, hour);
        assert!(age.expired(start - hour));
        assert!(!age.expired(start - hour + Duration::from_nanos(1)));
        for (now, elapsed, expected) in [
            (start + hour * 2, hour, start - hour),
            // Half an hour of scanning elapsed when a two-hour rollback became visible.
            (start - hour * 3 / 2, hour / 2, start - hour * 3),
            (start + hour, hour, start - hour * 3),
        ] {
            age.recheck_at(now, elapsed);
            assert_eq!(age.cutoff(), Some(expected));
        }
        assert_eq!(GcAge::new(start, Duration::MAX).cutoff(), None);
    }

    #[test]
    fn reports_payload_counts_during_each_cleanup_batch() -> CargoResult<()> {
        let directory = tempfile::tempdir()?;
        let root = directory.path();
        let context = "0123456789abcdef";
        let payload = root.join("debug/build/registries").join(context);
        let metadata = root
            .join(build_cache_gc::DIRECTORY)
            .join("dependencies")
            .join(context);
        fs::create_dir_all(&payload)?;
        fs::create_dir_all(&metadata)?;
        fs::write(metadata.join("usage"), b"gc bookkeeping")?;
        File::create(root.join(Layout::SHARED_REGISTRY_CACHE_MARKER))?;
        File::create(root.join("debug/.cargo-build-lock"))?;
        // Span two deletion batches and start with the totals from a previous root.
        for i in 0..300 {
            fs::write(payload.join(i.to_string()), b"ab")?;
        }
        for dry_run in [true, false] {
            let mut readings = Vec::new();
            let mut update = |counts: &build_cache_gc::FileCounts| {
                readings.push((counts.files, counts.bytes));
            };
            let mut summary = build_cache_gc::Summary {
                counts: build_cache_gc::FileCounts {
                    files: 1,
                    bytes: 10,
                    ..Default::default()
                },
                progress: Some(&mut update),
                ..Default::default()
            };
            let mut age = GcAge::new(SystemTime::now(), Duration::from_hours(1));
            collect_root(root, dry_run, &mut age, None, &mut summary)?;
            assert_eq!((summary.counts.files, summary.counts.bytes), (301, 610));
            readings.dedup();
            assert_eq!(
                readings,
                (0..=300).map(|i| (1 + i, 10 + 2 * i)).collect::<Vec<_>>()
            );
            assert_eq!(payload.exists(), dry_run);
            assert_eq!(metadata.exists(), dry_run);
        }
        Ok(())
    }

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
        discover_roots(directory.path(), 4, &mut roots, &mut || {})?;
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
