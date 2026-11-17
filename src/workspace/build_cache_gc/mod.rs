//! Conservative reclamation of retired shared-build namespaces.
//!
//! Builds batch context and dependency activity into SQLite without scanning artifacts.
//! Explicit GC reclaims legacy layouts, obsolete compilers, and idle dependencies.

use std::collections::{BTreeSet, VecDeque};
use std::fs::{self, File, Metadata, OpenOptions, TryLockError};
use std::io;
use std::path::{Component, Path, PathBuf};
use std::time::{Duration, Instant, SystemTime};

use anyhow::{Context as _, ensure};
use serde::{Deserialize, Serialize};

use crate::CargoResult;
use crate::compiler::Layout;
use crate::util::data_structures::{HashMap, HashSet};
use crate::util::flock::try_lock_exclusive;
use crate::workspace::build_cache_gc_roots::GcAge;

pub(crate) const DIRECTORY: &str = ".ohm-gc-v1";
pub(crate) const CONSUMERS_LOCK: &str = "consumers.lock";
pub(crate) const THINLTO: &str = ".ohm-thinlto-cache";
const TRASH: &str = ".ohm-gc-trash-v1";
const METADATA_TRASH: &str = ".ohm-gc-metadata-trash-v1";
const DELETE_BUDGET: usize = 256;
const RENAME_BUDGET: usize = 8;
#[cfg(test)]
const CONTEXT_MAX_IDLE: Duration = Duration::from_secs(60 * 60);
const LAST_USED: &str = "last-used"; // Legacy file-based bookkeeping.

mod tracker;
pub(crate) mod worktrees;
use tracker::Tracker;

/// Refreshes context and dependency activity at build start and completion.
/// The caller must hold a consumer lease until this guard has been dropped.
pub(crate) struct ContextUse {
    tracker: Tracker,
    context: String,
    entries: Option<Vec<PathBuf>>,
    used_through: tracker::Timestamp,
}

impl ContextUse {
    pub(crate) fn context(&self) -> &str {
        &self.context
    }

    /// `None` protects every dependency when importing an unresolved snapshot.
    pub(crate) fn new(
        mut tracker: Tracker,
        context: &str,
        mut entries: Option<Vec<PathBuf>>,
    ) -> CargoResult<Self> {
        ensure!(component(context), "invalid build context");
        if let Some(entries) = &mut entries {
            entries.sort();
            entries.dedup();
        }
        let used_through = tracker.touch(context, entries.as_deref(), SystemTime::now())?;
        Ok(Self {
            tracker,
            context: context.to_owned(),
            entries,
            used_through,
        })
    }

    /// Long builds renew activity at completion; short builds need no second query.
    fn refresh(&mut self, now: SystemTime) -> CargoResult<()> {
        if tracker::timestamp(now)? > self.used_through {
            self.used_through = self
                .tracker
                .touch(&self.context, self.entries.as_deref(), now)?;
        }
        Ok(())
    }
}

/// Counts importing private snapshots as use of their tracked contexts too.
pub(crate) fn record_seed_contexts(root: &Path, source: &Path) -> CargoResult<Vec<ContextUse>> {
    let records = metadata_dir(root, false)?.join("contexts");
    let mut usage = Vec::new();
    for parent in [
        source.to_path_buf(),
        source.join(crate::compiler::OHM_WORKTREE_CLIPPY_DIRECTORY),
    ] {
        if !plain_directory(&parent) {
            continue;
        }
        for entry in fs::read_dir(parent)? {
            let entry = entry?;
            let name = entry.file_name();
            let Some(context) = name.to_str().filter(|name| component(name)) else {
                continue;
            };
            if !entry.file_type()?.is_dir() {
                continue;
            }
            let tracker = Tracker::open(root)?;
            if tracker.context(context)?.is_none() {
                if !plain_directory(&records) {
                    continue;
                }
                let Some(record) =
                    read_record::<ContextRecord>(&records.join(format!("{context}.json")))
                        .filter(|record| record.supported() && record.context == context)
                else {
                    continue;
                };
                tracker.insert_context(&record)?;
            }
            usage.push(ContextUse::new(tracker, context, None)?);
        }
    }
    Ok(usage)
}

impl Drop for ContextUse {
    fn drop(&mut self) {
        if let Err(error) = self.refresh(SystemTime::now()) {
            tracing::debug!(?error, "could not refresh build-cache usage");
        }
    }
}

/// Missing or ambiguous usage records never establish inactivity.
fn context_expired(directory: &Path, context: &str, age: &GcAge) -> bool {
    let usage = directory.join(LAST_USED);
    if !plain_directory(&usage) {
        return false;
    }
    fs::symlink_metadata(usage.join(context))
        .ok()
        .filter(|metadata| metadata.is_file())
        .and_then(|metadata| metadata.modified().ok())
        .is_some_and(|modified| age.expired(modified))
}

/// The same concrete compiler-file identity used to partition shared artifacts.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FileIdentity {
    pub path: PathBuf,
    pub length: u64,
    pub modified: SystemTime,
    #[cfg(unix)]
    pub device: u64,
    #[cfg(unix)]
    pub inode: u64,
    #[cfg(unix)]
    pub changed: i64,
    #[cfg(unix)]
    pub changed_nanoseconds: i64,
    #[cfg(not(unix))]
    pub created: Option<SystemTime>,
}

impl FileIdentity {
    pub(crate) fn from_metadata(path: PathBuf, metadata: &Metadata) -> io::Result<Self> {
        #[cfg(unix)]
        use std::os::unix::fs::MetadataExt as _;
        Ok(Self {
            path,
            length: metadata.len(),
            modified: metadata.modified()?,
            #[cfg(unix)]
            device: metadata.dev(),
            #[cfg(unix)]
            inode: metadata.ino(),
            #[cfg(unix)]
            changed: metadata.ctime(),
            #[cfg(unix)]
            changed_nanoseconds: metadata.ctime_nsec(),
            #[cfg(not(unix))]
            created: metadata.created().ok(),
        })
    }
}

/// An existing filesystem anchor distinguishes removal from an unmounted volume.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Anchor {
    path: PathBuf,
    device: u64,
    inode: u64,
}

impl Anchor {
    #[cfg(unix)]
    fn for_path(path: &Path) -> CargoResult<Self> {
        use std::os::unix::fs::MetadataExt as _;
        let mut path = path.parent().context("path has no parent")?.to_path_buf();
        let mut metadata = fs::symlink_metadata(&path)?;
        ensure!(
            metadata.is_dir(),
            "filesystem anchor is not a plain directory"
        );
        while let Some(parent) = path.parent() {
            let parent_metadata = fs::symlink_metadata(parent)?;
            if !parent_metadata.is_dir() || parent_metadata.dev() != metadata.dev() {
                break;
            }
            metadata = parent_metadata;
            path = parent.to_path_buf();
        }
        Ok(Self {
            path,
            device: metadata.dev(),
            inode: metadata.ino(),
        })
    }

    #[cfg(not(unix))]
    fn for_path(_path: &Path) -> CargoResult<Self> {
        anyhow::bail!("build-cache reclamation requires Unix filesystem identities")
    }

    fn available(&self) -> bool {
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt as _;
            fs::symlink_metadata(&self.path).is_ok_and(|metadata| {
                metadata.is_dir() && metadata.dev() == self.device && metadata.ino() == self.inode
            })
        }
        #[cfg(not(unix))]
        {
            false
        }
    }

    /// Missing descendants are meaningful only while their original mount is available.
    fn covers(&self, path: &Path) -> bool {
        if !self.available() || !path.starts_with(&self.path) {
            return false;
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt as _;
            let mut parent = path.parent();
            while let Some(path) = parent {
                match fs::symlink_metadata(path) {
                    Ok(metadata) => {
                        return metadata.is_dir()
                            && metadata.dev() == self.device
                            && path.canonicalize().is_ok_and(|canonical| canonical == path);
                    }
                    Err(error) if error.kind() == io::ErrorKind::NotFound => parent = path.parent(),
                    Err(_) => return false,
                }
            }
        }
        false
    }
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ContextRecord {
    version: u32,
    context: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    ohm_version: Option<String>,
    compiler: FileIdentity,
    driver: FileIdentity,
    compiler_anchor: Anchor,
    driver_anchor: Anchor,
}

/// Orders published Ohm releases, including the numeric revision after Rust's version.
fn ohm_release(version: &str) -> Option<(semver::Version, u64)> {
    let (rust, revision) = version.strip_prefix("ohm-")?.rsplit_once('-')?;
    Some((semver::Version::parse(rust).ok()?, revision.parse().ok()?))
}

/// Recognizes the release tag printed by a packaged Ohm compiler's `-vV`.
pub(crate) fn ohm_version(verbose_version: &str) -> Option<&str> {
    verbose_version
        .lines()
        .next()?
        .split_whitespace()
        .find_map(|word| {
            let version = word.strip_prefix('(')?.strip_suffix(')')?;
            ohm_release(version).map(|_| version)
        })
}

/// Captures installation provenance once, without changing existing context hashes.
fn installed_ohm_version(compiler: &FileIdentity, driver: &FileIdentity) -> Option<String> {
    let bin = compiler.path.parent()?;
    if bin.file_name()? != "bin" {
        return None;
    }
    let sysroot = bin.parent()?;
    if !driver.path.starts_with(sysroot) {
        return None;
    }
    let version = String::from_utf8(read_regular(&sysroot.join(".ohm-version"))?).ok()?;
    ohm_release(version.trim()).map(|_| version.trim().to_owned())
}

impl ContextRecord {
    /// Version 2 uses context-scoped leases and is opaque to older collectors.
    fn supported(&self) -> bool {
        self.version
            == if scoped_context_name(&self.context) {
                2
            } else {
                1
            }
    }

    fn retired(&self) -> bool {
        [
            (&self.compiler, &self.compiler_anchor),
            (&self.driver, &self.driver_anchor),
        ]
        .iter()
        .any(|(identity, anchor)| {
            if !identity.path.is_absolute() || !anchor.covers(&identity.path) {
                return false;
            }
            match fs::symlink_metadata(&identity.path) {
                Ok(metadata) if metadata.is_file() => {
                    FileIdentity::from_metadata(identity.path.clone(), &metadata)
                        .is_ok_and(|current| current != **identity)
                }
                Err(error) if error.kind() == io::ErrorKind::NotFound => true,
                _ => false,
            }
        })
    }
}

/// Ensures metadata operations do not follow a replacement directory symlink.
pub(crate) fn metadata_dir(root: &Path, create: bool) -> CargoResult<PathBuf> {
    ensure!(
        plain_directory(root),
        "shared build root is not a plain directory"
    );
    let directory = root.join(DIRECTORY);
    if create {
        create_plain(&directory)?;
    }
    ensure!(
        plain_directory(&directory),
        "build-cache metadata is not a plain directory"
    );
    Ok(directory)
}

/// Records immutable compiler provenance and reuses the connection for activity updates.
pub(crate) fn record_context(
    root: &Path,
    context: &str,
    compiler: FileIdentity,
    driver: FileIdentity,
) -> CargoResult<Tracker> {
    ensure!(component(context), "invalid build context");
    let tracker = Tracker::open(root)?;
    tracker.record_context(context, compiler, driver)?;
    Ok(tracker)
}

#[derive(Default)]
pub(crate) struct Summary<'a> {
    pub retired: usize,
    pub retained: usize,
    /// A partial retirement or newly deferred candidate advanced this pass.
    pub advanced: bool,
    pub deleted_entries: usize,
    pub counts: FileCounts,
    /// Reports cumulative payload counts during unlocked discovery and traversal.
    pub progress: Option<&'a mut dyn FnMut(&FileCounts)>,
    pub errors: BTreeSet<String>,
    pub pending: bool,
    pub busy: bool,
    pub skipped: Vec<String>,
    pub blocking_locks: BTreeSet<PathBuf>,
    pub details: Vec<String>,
}

/// Work carried between batches of a single manual collection.
#[derive(Default)]
pub(crate) struct CollectionState {
    deferred: HashSet<Namespace>,
    dependencies: Option<VecDeque<Namespace>>,
}

impl Summary<'_> {
    fn tick(&mut self) {
        if let Some(update) = &mut self.progress {
            update(&self.counts);
        }
    }

    fn payload_entries(&mut self, path: &Path) -> CargoResult<Option<fs::ReadDir>> {
        match fs::read_dir(path) {
            Ok(entries) => Ok(Some(entries)),
            Err(error) => self.path_error(path, error.into()),
        }
    }

    /// Preserve inaccessible payloads while collecting their independent siblings.
    fn path_error<T: Default>(&mut self, path: &Path, error: anyhow::Error) -> CargoResult<T> {
        if let Some(cause) = error.downcast_ref::<io::Error>()
            && matches!(
                cause.kind(),
                io::ErrorKind::PermissionDenied | io::ErrorKind::ReadOnlyFilesystem
            )
        {
            self.errors.insert(format!("{} ({cause})", path.display()));
            return Ok(T::default());
        }
        Err(error)
    }

    fn skip_path(&mut self, path: &Path, reason: &str) {
        let detail = format!("{} ({reason})", path.display());
        if !self.skipped.contains(&detail) {
            self.skipped.push(detail);
        }
    }

    fn skip(&mut self, namespace: &Namespace) {
        self.busy = true;
        let detail = match namespace.scoped_context() {
            Some(context) => format!("context {context} (in use)"),
            None => "legacy caches (a build, program, or older collector is using this cache)"
                .to_owned(),
        };
        if !self.skipped.contains(&detail) {
            self.skipped.push(detail);
        }
    }
}

/// One probe per protection domain; busy domains do not block unrelated ones.
/// Dry runs release probes immediately, before counting any artifact trees.
#[derive(Default)]
struct CollectionLocks {
    // A missing key context denotes legacy protection; a missing value is busy.
    domains: HashMap<Option<String>, Option<Vec<CollectorLock>>>,
}

impl CollectionLocks {
    fn acquire(
        &mut self,
        root: &Path,
        profiles: &[PathBuf],
        namespace: &Namespace,
        dry_run: bool,
        age: &mut GcAge,
        summary: &mut Summary<'_>,
    ) -> CargoResult<bool> {
        let context = namespace.scoped_context().map(str::to_owned);
        if let Some(guards) = self.domains.get(&context) {
            return Ok(guards.is_some());
        }
        for profile in profiles {
            ensure!(
                !crate::compiler::layout::shared_registry_directory_is_nfs(profile)?,
                "build-cache reclamation does not support NFS profiles"
            );
        }
        let mut paths = if let Some(context) = &context {
            vec![super::build_cache_gc_lease::context_lock(root, context)]
        } else {
            let mut paths = vec![root.join(DIRECTORY).join(CONSUMERS_LOCK)];
            paths.extend(
                profiles
                    .iter()
                    .map(|profile| profile.join(".cargo-build-lock")),
            );
            // Older Cargo's optional ThinLTO pruner runs after releasing profile locks.
            if plain_directory(&root.join(THINLTO)) {
                paths.push(root.join(THINLTO).join(".prune-lock"));
            }
            paths
        };
        if dry_run {
            paths.retain(|path| !absent(path));
        }
        let mut guards = Vec::new();
        for path in paths {
            match try_lock(&path, !dry_run) {
                Ok(Some(guard)) => {
                    guards.push(guard);
                    continue;
                }
                Ok(None) => {
                    summary.skip(namespace);
                    summary.blocking_locks.insert(path);
                }
                Err(error) => summary.path_error::<()>(&path, error)?,
            }
            self.domains.insert(context, None);
            return Ok(false);
        }
        age.recheck();
        if dry_run {
            guards.clear();
        }
        self.domains.insert(context, Some(guards));
        Ok(true)
    }
}

/// Cache payload totals exclude GC's own provenance and temporary staging files.
#[derive(Default, Debug, PartialEq, Eq)]
pub(crate) struct FileCounts {
    pub files: u64,
    pub directories: u64,
    pub bytes: u64,
}

impl FileCounts {
    fn record(&mut self, metadata: &Metadata) {
        self.record_entry(metadata.is_dir(), metadata.len());
    }

    fn record_entry(&mut self, directory: bool, len: u64) {
        if directory {
            self.directories += 1;
        } else {
            self.files += 1;
            // Match cargo clean: logical lengths, including symlinks, rather than disk blocks.
            self.bytes = self.bytes.saturating_add(len);
        }
    }

    #[cfg(test)]
    fn include(&mut self, other: &Self) {
        self.files += other.files;
        self.directories += other.directories;
        self.bytes = self.bytes.saturating_add(other.bytes);
    }
}

/// Retires legacy layouts, obsolete compilers, and idle contexts, dependencies, or backend objects.
pub(crate) fn collect(
    root: &Path,
    dry_run: bool,
    age: &mut GcAge,
    current_ohm: Option<&str>,
    state: &mut CollectionState,
    summary: &mut Summary<'_>,
) -> CargoResult<()> {
    collect_with_lock_budget(
        root,
        dry_run,
        age,
        Duration::from_millis(10),
        current_ohm,
        state,
        summary,
    )
}

/// Applies a soft deadline between bounded retirement steps, always allowing progress.
fn collect_with_lock_budget(
    root: &Path,
    dry_run: bool,
    age: &mut GcAge,
    lock_budget: Duration,
    current_ohm: Option<&str>,
    state: &mut CollectionState,
    summary: &mut Summary<'_>,
) -> CargoResult<()> {
    if !cfg!(any(target_os = "linux", target_os = "macos")) {
        return Ok(());
    }
    ensure!(
        regular(&root.join(Layout::SHARED_REGISTRY_CACHE_MARKER)),
        "not an owned shared registry cache"
    );
    ensure!(
        !crate::compiler::layout::shared_registry_directory_is_nfs(root)?,
        "build-cache reclamation does not support NFS"
    );
    // Previewing a legacy cache must not enroll it or create locks. Real collection
    // installs the same consumer lock used by new builds before inspecting profiles.
    let directory = root.join(DIRECTORY);
    if !dry_run || !absent(&directory) {
        metadata_dir(root, !dry_run)?;
    }
    let _collector = if dry_run {
        None
    } else {
        let path = directory.join("collector.lock");
        let Some(collector) = try_lock(&path, true)? else {
            summary.busy = true;
            summary.blocking_locks.insert(path);
            summary
                .skipped
                .push(format!("{} (another GC is running)", root.display()));
            return Ok(());
        };
        Some(collector)
    };
    let tracker = Tracker::existing(root, dry_run)?;
    let profiles = profiles(root)?;
    let mut ready = Vec::new();
    let mut discovered_dependencies = VecDeque::new();
    let mut trash_roots = profiles
        .iter()
        .map(|profile| profile.join(TRASH))
        .collect::<Vec<_>>();
    trash_roots.push(root.join(TRASH));
    for profile in &profiles {
        if let Some(parent) = profile.parent() {
            let trash = parent.join(TRASH);
            if !trash_roots.contains(&trash) {
                trash_roots.push(trash);
            }
        }
    }
    // Namespace discovery never holds consumer or build locks.
    for namespace in namespaces(root, &profiles, tracker.as_ref(), summary)? {
        summary.tick();
        if namespace
            .detail(root, &profiles, age, current_ohm, tracker.as_ref())
            .is_none()
        {
            summary.retained += 1;
            if let Namespace::Context(context) = &namespace
                && age.cutoff().is_some()
            {
                if state.dependencies.is_none() {
                    discovered_dependencies.extend(
                        idle_dependencies(root, &profiles, context, age, tracker.as_ref(), summary)
                            .unwrap_or_default(),
                    );
                }
                // One extra candidate distinguishes a full batch from completion.
                let limit = if dry_run {
                    usize::MAX
                } else {
                    DELETE_BUDGET + 1
                };
                for entry in thinlto_entries(root, context, age, limit, state, summary)? {
                    if entry
                        .detail(root, &profiles, age, current_ohm, tracker.as_ref())
                        .is_some()
                    {
                        let paths = entry.paths(root, &profiles);
                        ready.push((entry, paths));
                    }
                }
            }
            continue;
        }
        let paths = namespace.paths(root, &profiles);
        ready.push((namespace, paths));
    }
    ready.retain(|(namespace, _)| !state.deferred.contains(namespace));
    let dependencies = state.dependencies.get_or_insert(discovered_dependencies);
    if dry_run {
        // Preview every candidate without holding locks while counting artifacts.
        let mut locks = CollectionLocks::default();
        let mut sources = Vec::new();
        let dependencies = dependencies.drain(..).map(|dependency| {
            let paths = dependency.paths(root, &profiles);
            (dependency, paths)
        });
        for (namespace, paths) in ready.into_iter().chain(dependencies) {
            summary.tick();
            if !locks.acquire(root, &profiles, &namespace, true, age, summary)? {
                continue;
            }
            let Some(detail) =
                namespace.detail(root, &profiles, age, current_ohm, tracker.as_ref())
            else {
                continue;
            };
            let before = sources.len();
            for (source, trash) in paths {
                if trash == root.join(METADATA_TRASH) {
                    continue;
                }
                if retire(&namespace, root, &source, &trash, true, summary)
                    .or_else(|error| summary.path_error(&source, error))?
                {
                    sources.push(source);
                }
            }
            if sources.len() != before {
                summary.retired += 1;
                if matches!(namespace, Namespace::Dependency { .. })
                    || !summary.details.contains(&detail)
                {
                    summary.details.push(detail);
                }
            }
        }
        sources.sort_by_key(|path| path.components().count());
        let mut counted = HashSet::default();
        let mut remaining = usize::MAX;
        for source in sources {
            if source.ancestors().any(|parent| counted.contains(parent)) {
                continue;
            }
            counted.insert(source.clone());
            let device = filesystem_device(&fs::symlink_metadata(&source)?);
            remove_bounded(&source, device, &mut remaining, summary, true, None)?;
        }
        for trash in trash_roots {
            drain_trash(&trash, &mut remaining, summary, true, None)?;
        }
        return Ok(());
    }
    if !ready.is_empty() || !dependencies.is_empty() {
        // Finish file-only work before reserving a SQLite writer. A busy
        // database can then postpone only the remaining row deletions.
        ready.sort_by_key(|(namespace, _)| namespace.writes_usage_rows());
        // Individual objects have no rows to delete. Retire a file-sized batch,
        // still yielding at the same short deadline as other namespaces.
        let rename_budget = if dependencies.is_empty()
            && ready
                .iter()
                .all(|(namespace, _)| matches!(namespace, Namespace::ThinLto { .. }))
        {
            DELETE_BUDGET
        } else {
            RENAME_BUDGET
        };
        let deadline = Instant::now() + lock_budget;
        let mut locks = CollectionLocks::default();
        let tracker = match tracker {
            Some(tracker) => Some(tracker),
            None => Tracker::existing(root, false)?,
        };
        if let Some(tracker) = &tracker {
            tracker.conn.busy_timeout(Duration::ZERO)?;
        }
        let mut transaction = None;
        let mut remaining = rename_budget;
        let mut records_remaining = rename_budget;
        let mut ready = ready.into_iter();
        while !ready.as_slice().is_empty() || !dependencies.is_empty() {
            if remaining == 0
                || records_remaining == 0
                || (records_remaining < rename_budget && Instant::now() >= deadline)
            {
                summary.pending = true;
                break;
            }
            // Dependencies come last: file-only work can proceed with a busy
            // SQLite writer. Only take the next dependency when its batch has room.
            let (namespace, paths) = ready.next().unwrap_or_else(|| {
                let dependency = dependencies.pop_front().unwrap();
                let paths = dependency.paths(root, &profiles);
                (dependency, paths)
            });
            if !locks.acquire(root, &profiles, &namespace, false, age, summary)? {
                summary.advanced |= namespace.defer(&mut state.deferred);
                continue;
            }
            // Reserve the writer before rechecking usage when deleting rows.
            if namespace.writes_usage_rows()
                && transaction.is_none()
                && let Some(tracker) = &tracker
            {
                match rusqlite::Transaction::new_unchecked(
                    &tracker.conn,
                    rusqlite::TransactionBehavior::Immediate,
                ) {
                    Ok(guard) => transaction = Some(guard),
                    Err(error)
                        if error.sqlite_error_code() == Some(rusqlite::ErrorCode::DatabaseBusy) =>
                    {
                        summary.busy = true;
                        summary.skipped.push(format!(
                            "contexts and dependencies (usage database {} is busy)",
                            directory.join(tracker::DATABASE).display()
                        ));
                        if matches!(namespace, Namespace::Dependency { .. }) {
                            dependencies.push_front(namespace);
                        }
                        break;
                    }
                    Err(error) => return Err(error.into()),
                }
            }
            // A build may have added another profile since discovery. Do not
            // forget a context unless every profile was included in retirement.
            if matches!(namespace, Namespace::Context(_)) && profiles != self::profiles(root)? {
                summary.skip_path(
                    root,
                    "build profiles changed during cleanup; retry after builds finish",
                );
                summary.pending = true;
                break;
            }
            records_remaining -= 1;
            // Recheck usage while consumers of this namespace are excluded.
            let Some(detail) =
                namespace.detail(root, &profiles, age, current_ohm, tracker.as_ref())
            else {
                if let Some((source, _)) = paths.first()
                    && !safely_absent(root, source)
                {
                    summary.skip_path(
                        source,
                        "no longer eligible after rechecking last use and compiler metadata",
                    );
                }
                summary.advanced |= namespace.defer(&mut state.deferred);
                continue;
            };
            let mut retired = false;
            let mut partial = false;
            let skipped_before = summary.skipped.len() + summary.errors.len();
            for (source, trash) in &paths {
                if remaining == 0 || (remaining < rename_budget && Instant::now() >= deadline) {
                    summary.pending = true;
                    partial = true;
                    break;
                }
                if retire(&namespace, root, source, trash, false, summary)
                    .or_else(|error| summary.path_error(source, error))?
                {
                    remaining -= 1;
                    retired = true;
                    summary.advanced = true;
                }
            }
            if retired && summary.details.len() < 32 && !summary.details.contains(&detail) {
                summary.details.push(detail);
            }
            let completed = paths.iter().all(|(source, _)| safely_absent(root, source))
                && namespace
                    .paths(root, &profiles)
                    .iter()
                    .all(|(source, _)| safely_absent(root, source));
            if completed {
                if namespace.finish(&directory, tracker.as_ref(), summary)? {
                    summary.retired += 1;
                } else {
                    summary.advanced |= namespace.defer(&mut state.deferred);
                }
            } else if partial && matches!(namespace, Namespace::Dependency { .. }) {
                // The soft deadline may have elapsed while acquiring the lock.
                dependencies.push_front(namespace);
            } else if !partial {
                if summary.skipped.len() + summary.errors.len() == skipped_before {
                    for (source, _) in &paths {
                        if !safely_absent(root, source) {
                            summary.skip_path(source, "path changed during cleanup");
                        }
                    }
                }
                summary.advanced |= namespace.defer(&mut state.deferred);
            }
        }
        if let Some(transaction) = transaction {
            transaction.commit()?;
        }
    }
    // Retired paths are unreachable by consumers. Drain them even if a build
    // starts or another context remains in use.
    let mut remaining = DELETE_BUDGET;
    for trash in trash_roots {
        drain_trash(&trash, &mut remaining, summary, false, None)?;
    }
    let mut metadata_summary = Summary::default();
    drain_trash(
        &root.join(METADATA_TRASH),
        &mut remaining,
        &mut metadata_summary,
        false,
        None,
    )?;
    summary.deleted_entries += metadata_summary.deleted_entries;
    summary.pending |= metadata_summary.pending;
    summary.skipped.extend(metadata_summary.skipped);
    summary.errors.extend(metadata_summary.errors);
    Ok(())
}

#[derive(PartialEq, Eq, PartialOrd, Ord, Hash)]
enum Namespace {
    Context(String),
    LegacyWorkspace(String),
    Dependency { context: String, entry: PathBuf },
    ThinLto { context: String, entry: PathBuf },
    LegacyThinLto(String),
}

/// Discovers backend objects only during explicit GC, outside build locks.
fn thinlto_entries(
    root: &Path,
    context: &str,
    age: &GcAge,
    limit: usize,
    state: &CollectionState,
    summary: &mut Summary<'_>,
) -> CargoResult<Vec<Namespace>> {
    let parent = Path::new(THINLTO).join(context);
    let mut entries = Vec::new();
    for namespace in directory_names(root, &root.join(&parent), summary)? {
        if !thinlto_key(&namespace) {
            continue;
        }
        let directory = parent.join(namespace);
        let Some(children) = summary.payload_entries(&root.join(&directory))? else {
            continue;
        };
        for entry in children {
            summary.tick();
            let entry = entry?;
            let name = entry.file_name();
            let Some(name) = name.to_str() else { continue };
            let kind = entry.file_type()?;
            if (kind.is_file() && name.strip_suffix(".cache").is_some_and(thinlto_key))
                || (kind.is_dir() && name.starts_with("ohm-thinlto-"))
            {
                if !entry
                    .metadata()
                    .is_ok_and(|metadata| thinlto_expired(&metadata, age))
                {
                    continue;
                }
                let entry = Namespace::ThinLto {
                    context: context.to_owned(),
                    entry: directory.join(name),
                };
                if state.deferred.contains(&entry) {
                    continue;
                }
                entries.push(entry);
                if entries.len() == limit {
                    return Ok(entries);
                }
            }
        }
    }
    entries.sort();
    Ok(entries)
}

fn thinlto_key(name: &str) -> bool {
    name.len() == 32 && name.bytes().all(|byte| byte.is_ascii_hexdigit())
}

/// Rustc refreshes object mtimes on backend cache hits, including read-only reuse.
fn thinlto_expired(metadata: &Metadata, age: &GcAge) -> bool {
    metadata.modified().is_ok_and(|used| age.expired(used))
}

/// Selects expired rows outside build locks and validates their artifact paths.
fn idle_dependencies(
    root: &Path,
    profiles: &[PathBuf],
    context: &str,
    age: &GcAge,
    tracker: Option<&Tracker>,
    summary: &mut Summary<'_>,
) -> Option<Vec<Namespace>> {
    let tracker = tracker?;
    let state = tracker.supported_context(context)?;
    let cutoff = tracker::timestamp(age.cutoff()?).ok()?;
    if state.all_used.is_some_and(|used| used > cutoff) {
        return None;
    }
    // Older Cargo binaries can still touch their file-based context marker.
    // They do not record individual dependencies, so treat that as a snapshot.
    if legacy_usage(root, context)?.is_some_and(|used| used > cutoff) {
        return None;
    }
    let prefixes = profiles
        .iter()
        .map(|profile| {
            profile
                .strip_prefix(root)
                .unwrap()
                .join("build/registries")
                .join(context)
        })
        .collect::<HashSet<_>>();
    let mut idle = Vec::new();
    for entry in tracker.idle_dependencies(context, cutoff).ok()? {
        summary.tick();
        if !entry
            .components()
            .all(|part| matches!(part, Component::Normal(_)))
            || !entry
                .file_name()
                .and_then(|name| name.to_str())
                .is_some_and(namespace_hash)
            || !entry
                .parent()
                .and_then(Path::file_name)
                .and_then(|name| name.to_str())
                .is_some_and(component)
            || !entry
                .ancestors()
                .nth(2)
                .is_some_and(|parent| prefixes.contains(parent))
        {
            return None;
        }
        idle.push(Namespace::Dependency {
            context: context.to_owned(),
            entry,
        });
    }
    idle.sort();
    Some(idle)
}

/// Old context markers remain readable until their legacy artifacts are retired.
fn legacy_usage(root: &Path, context: &str) -> Option<Option<tracker::Timestamp>> {
    let path = root.join(DIRECTORY).join(LAST_USED).join(context);
    if safely_absent(root, &path) {
        return Some(None);
    }
    if !plain_ancestors(root, &path).ok()? {
        return None;
    }
    let metadata = fs::symlink_metadata(&path).ok()?;
    if !metadata.is_file() {
        return None;
    }
    Some(Some(tracker::timestamp(metadata.modified().ok()?).ok()?))
}

impl Namespace {
    /// A dependency popped from the queue cannot be rediscovered in this run.
    fn defer(self, deferred: &mut HashSet<Self>) -> bool {
        matches!(self, Self::Dependency { .. }) || deferred.insert(self)
    }

    fn writes_usage_rows(&self) -> bool {
        matches!(self, Self::Context(_) | Self::Dependency { .. })
    }

    fn scoped_context(&self) -> Option<&str> {
        match self {
            Self::Context(context)
            | Self::Dependency { context, .. }
            | Self::ThinLto { context, .. }
                if scoped_context_name(context) =>
            {
                Some(context)
            }
            _ => None,
        }
    }

    /// Missing legacy records permit eviction; malformed or newer records do not.
    fn detail(
        &self,
        root: &Path,
        profiles: &[PathBuf],
        age: &GcAge,
        current_ohm: Option<&str>,
        tracker: Option<&Tracker>,
    ) -> Option<String> {
        let directory = root.join(DIRECTORY);
        match self {
            Self::ThinLto { context, entry } => {
                // An unknown or malformed context never permits partial eviction.
                tracker?.supported_context(context)?;
                let path = root.join(entry);
                if !plain_ancestors(root, &path).ok()? {
                    return None;
                }
                let metadata = fs::symlink_metadata(path).ok()?;
                if !metadata.is_file() && !metadata.is_dir() {
                    return None;
                }
                thinlto_expired(&metadata, age).then(|| {
                    format!("ThinLTO objects for context {context} (unused for at least {age})")
                })
            }
            Self::LegacyThinLto(id) => {
                Some(format!("legacy ThinLTO context {id} (no usage records)"))
            }
            Self::Dependency { context, entry } => {
                let cutoff = tracker::timestamp(age.cutoff()?).ok()?;
                let tracker = tracker?;
                tracker.supported_context(context)?;
                let profile = root.join(entry.ancestors().nth(5)?);
                if !profiles.contains(&profile)
                    || legacy_usage(root, context)?.is_some_and(|used| used > cutoff)
                {
                    return None;
                }
                tracker
                    .dependency_expired(context, entry, cutoff)
                    .ok()?
                    .then(|| format!("dependency {} (unused for at least {age})", entry.display()))
            }
            Self::Context(id) => {
                let path = directory.join("contexts").join(format!("{id}.json"));
                let tracked = match tracker {
                    Some(tracker) => tracker.context(id).ok()?,
                    None => None,
                };
                let (record, expired) = if let Some(state) = tracked {
                    let last_used = state
                        .last_used
                        .into_iter()
                        .chain(legacy_usage(root, id)?)
                        .max();
                    let expired = age
                        .cutoff()
                        .and_then(|cutoff| tracker::timestamp(cutoff).ok())
                        .is_some_and(|cutoff| last_used.is_some_and(|used| used <= cutoff));
                    (state.record, expired)
                } else {
                    if (legacy_context_name(id) || scoped_context_name(id))
                        && safely_absent(root, &path)
                        && safely_absent(root, &directory.join(LAST_USED).join(id))
                    {
                        let kind = if scoped_context_name(id) {
                            "untracked"
                        } else {
                            "legacy"
                        };
                        return Some(format!("{kind} context {id} (no usage records)"));
                    }
                    if !plain_ancestors(root, &path).ok()? {
                        return None;
                    }
                    (
                        read_record::<ContextRecord>(&path)?,
                        context_expired(&directory, id, age),
                    )
                };
                if !record.supported() || record.context != *id {
                    return None;
                }
                let previous = record
                    .ohm_version
                    .clone()
                    .or_else(|| installed_ohm_version(&record.compiler, &record.driver));
                if let (Some(previous), Some(current)) = (previous.as_deref(), current_ohm)
                    && let (Some(previous_release), Some(current_release)) =
                        (ohm_release(previous), ohm_release(current))
                    && previous_release < current_release
                {
                    return Some(format!(
                        "context {id} (from {previous}; current is {current})"
                    ));
                }
                if record.retired() {
                    Some(format!(
                        "context {id} (compiler or driver changed or removed)"
                    ))
                } else if expired {
                    Some(format!("context {id} (unused for at least {age})"))
                } else {
                    None
                }
            }
            Self::LegacyWorkspace(id) => legacy_private_state(root, profiles)
                .then(|| format!("legacy workspace {id} (private state now lives in target)")),
        }
    }

    fn paths(&self, root: &Path, profiles: &[PathBuf]) -> Vec<(PathBuf, PathBuf)> {
        match self {
            Self::ThinLto { entry, .. } => {
                return vec![(root.join(entry), root.join(TRASH))];
            }
            Self::LegacyThinLto(id) => {
                return vec![(root.join(THINLTO).join(id), root.join(TRASH))];
            }
            _ => {}
        }
        if let Self::Dependency { entry, .. } = self {
            // Validated entries have profile/build/registries/context/package/hash.
            let profile = root.join(entry.ancestors().nth(5).unwrap());
            return vec![(root.join(entry), profile.join(TRASH))];
        }
        let mut paths = Vec::new();
        for profile in profiles {
            let sources = match self {
                Self::Context(id) => {
                    vec![profile.join("build/registries").join(id)]
                }
                Self::LegacyWorkspace(id) => vec![
                    profile.join("build/workspaces").join(id),
                    profile.join("incremental").join(id),
                ],
                Self::Dependency { .. } | Self::ThinLto { .. } | Self::LegacyThinLto(_) => {
                    unreachable!()
                }
            };
            paths.extend(
                sources
                    .into_iter()
                    .map(|source| (source, profile.join(TRASH))),
            );
        }
        if let Self::Context(id) = self {
            paths.push((root.join(THINLTO).join(id), root.join(TRASH)));
            paths.push((
                root.join(DIRECTORY).join("dependencies").join(id),
                root.join(METADATA_TRASH),
            ));
        }
        if let Self::LegacyWorkspace(id) = self {
            for base in std::iter::once(root).chain(profiles.iter().filter_map(|p| p.parent())) {
                for source in [
                    base.join("tmp").join(id),
                    base.join(format!(".rustdoc_fingerprint-{id}.json")),
                ] {
                    if !paths.iter().any(|(existing, _)| existing == &source) {
                        paths.push((source, base.join(TRASH)));
                    }
                }
            }
        }
        paths
    }

    fn finish(
        &self,
        directory: &Path,
        tracker: Option<&Tracker>,
        summary: &mut Summary<'_>,
    ) -> CargoResult<bool> {
        let paths = match self {
            Self::Dependency { .. } | Self::ThinLto { .. } | Self::LegacyThinLto(_) => Vec::new(),
            Self::Context(id) => vec![
                directory.join("contexts").join(format!("{id}.json")),
                directory.join(LAST_USED).join(id),
            ],
            Self::LegacyWorkspace(id) => {
                vec![directory.join("workspaces").join(format!("{id}.json"))]
            }
        };
        for path in paths {
            if plain_ancestors(directory, &path)?
                && regular(&path)
                && let Err(error) = fs::remove_file(&path)
            {
                return summary.path_error(&path, error.into());
            }
        }
        if let Some(tracker) = tracker {
            match self {
                Self::Context(id) => tracker.forget_context(id)?,
                Self::Dependency { context, entry } => tracker.forget_dependency(context, entry)?,
                Self::LegacyWorkspace(_) | Self::ThinLto { .. } | Self::LegacyThinLto(_) => {}
            }
        }
        Ok(true)
    }
}

/// The old shared layout is disposable, but a colocated target is still private state.
fn legacy_private_state(root: &Path, profiles: &[PathBuf]) -> bool {
    absent(&root.join(Layout::PRIVATE_BUILD_LOCK))
        && profiles.iter().all(|profile| {
            absent(&profile.join(".cargo-lock")) && absent(&profile.join(".cargo-artifact-lock"))
        })
}

/// Discovers only known Ohm namespace shapes inside a marked shared cache.
fn namespaces(
    root: &Path,
    profiles: &[PathBuf],
    tracker: Option<&Tracker>,
    summary: &mut Summary<'_>,
) -> CargoResult<Vec<Namespace>> {
    let mut namespaces = HashSet::default();
    if let Some(tracker) = tracker {
        for id in tracker.contexts()? {
            if component(&id) {
                namespaces.insert(Namespace::Context(id));
            }
        }
    }
    let records = root.join(DIRECTORY).join("contexts");
    if plain_ancestors(root, &records)? && plain_directory(&records) {
        for entry in fs::read_dir(records)? {
            summary.tick();
            let entry = entry?;
            let path = entry.path();
            if entry.file_type()?.is_file()
                && path
                    .extension()
                    .is_some_and(|extension| extension == "json")
                && let Some(id) = path
                    .file_stem()
                    .and_then(|name| name.to_str())
                    .filter(|id| component(id))
            {
                namespaces.insert(Namespace::Context(id.to_owned()));
            }
        }
    }
    // A deadline may leave only the dependency metadata of an untracked context.
    // Keep discovering it after its last artifact directory has been retired.
    for id in directory_names(root, &root.join(DIRECTORY).join("dependencies"), summary)? {
        if legacy_context_name(&id) || scoped_context_name(&id) {
            namespaces.insert(Namespace::Context(id));
        }
    }
    for profile in profiles {
        for id in directory_names(root, &profile.join("build/registries"), summary)? {
            if legacy_context_name(&id) || scoped_context_name(&id) {
                namespaces.insert(Namespace::Context(id));
            }
        }
        if legacy_private_state(root, profiles) {
            for parent in [
                profile.join("build/workspaces"),
                profile.join("incremental"),
            ] {
                for id in directory_names(root, &parent, summary)? {
                    if namespace_hash(&id) {
                        namespaces.insert(Namespace::LegacyWorkspace(id));
                    }
                }
            }
        }
    }
    for id in directory_names(root, &root.join(THINLTO), summary)? {
        if legacy_context_name(&id) || scoped_context_name(&id) {
            namespaces.insert(Namespace::Context(id));
        } else if thinlto_key(&id) && !namespaces.contains(&Namespace::Context(id.clone())) {
            namespaces.insert(Namespace::LegacyThinLto(id));
        }
    }
    if legacy_private_state(root, profiles) {
        for base in std::iter::once(root).chain(profiles.iter().filter_map(|p| p.parent())) {
            for id in directory_names(root, &base.join("tmp"), summary)? {
                if namespace_hash(&id) {
                    namespaces.insert(Namespace::LegacyWorkspace(id));
                }
            }
            for entry in fs::read_dir(base)? {
                let entry = entry?;
                let name = entry.file_name();
                if entry.file_type()?.is_file()
                    && let Some(id) = name
                        .to_str()
                        .and_then(|name| name.strip_prefix(".rustdoc_fingerprint-"))
                        .and_then(|name| name.strip_suffix(".json"))
                        .filter(|id| namespace_hash(id))
                {
                    namespaces.insert(Namespace::LegacyWorkspace(id.to_owned()));
                }
            }
        }
    }
    let mut namespaces = namespaces.into_iter().collect::<Vec<_>>();
    namespaces.sort();
    Ok(namespaces)
}

fn directory_names(
    root: &Path,
    parent: &Path,
    summary: &mut Summary<'_>,
) -> CargoResult<Vec<String>> {
    let mut names = Vec::new();
    if plain_ancestors(root, parent)?
        && plain_directory(parent)
        && let Some(entries) = summary.payload_entries(parent)?
    {
        for entry in entries {
            summary.tick();
            let entry = entry?;
            if entry.file_type()?.is_dir()
                && let Some(name) = entry.file_name().to_str()
            {
                names.push(name.to_owned());
            }
        }
    }
    Ok(names)
}

fn namespace_hash(name: &str) -> bool {
    name.len() == 16 && name.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn legacy_context_name(name: &str) -> bool {
    let (hash, suffix) = name.split_at_checked(16).unwrap_or(("", ""));
    namespace_hash(hash)
        && matches!(
            suffix,
            "" | "-all"
                | "-native-all"
                | "-native-build-scripts"
                | "-all-native-all"
                | "-all-native-build-scripts"
        )
}

/// The namespace and record version jointly keep old root-wide collectors away.
pub(crate) fn scoped_context_name(name: &str) -> bool {
    name.strip_prefix("v2-").is_some_and(legacy_context_name)
}

/// Absence behind a symlink is not proof that the owned payload was removed.
fn safely_absent(root: &Path, path: &Path) -> bool {
    if !path.starts_with(root) {
        return false;
    }
    let mut current = root.to_path_buf();
    for component in path.strip_prefix(root).unwrap().components() {
        if !matches!(component, Component::Normal(_)) {
            return false;
        }
        current.push(component);
        match fs::symlink_metadata(&current) {
            Err(error) if error.kind() == io::ErrorKind::NotFound => return true,
            Ok(metadata) if metadata.is_dir() && current != path => {}
            _ => return false,
        }
    }
    false
}

fn retire(
    namespace: &Namespace,
    root: &Path,
    source: &Path,
    trash: &Path,
    dry_run: bool,
    summary: &mut Summary<'_>,
) -> CargoResult<bool> {
    retire_path(
        root,
        source,
        trash,
        dry_run,
        summary,
        matches!(namespace, Namespace::Dependency { .. })
            .then_some("dependency path is no longer a plain directory"),
        false,
    )
}

fn retire_path(
    root: &Path,
    source: &Path,
    trash: &Path,
    dry_run: bool,
    summary: &mut Summary<'_>,
    non_directory_reason: Option<&str>,
    allow_symlink: bool,
) -> CargoResult<bool> {
    if safely_absent(root, source) {
        return Ok(false);
    }
    if !plain_ancestors(root, source)? {
        summary.skip_path(source, "parent is not a plain directory");
        return Ok(false);
    }
    let metadata = fs::symlink_metadata(source)?;
    if let Some(reason) = non_directory_reason
        && !metadata.is_dir()
    {
        summary.skip_path(source, reason);
        return Ok(false);
    }
    if !(metadata.is_dir() || metadata.is_file() || allow_symlink && metadata.is_symlink()) {
        summary.skip_path(source, "not a regular file or directory");
        return Ok(false);
    }
    if filesystem_device(&metadata)
        != filesystem_device(&fs::symlink_metadata(trash.parent().unwrap())?)
    {
        summary.skip_path(
            source,
            "on a different filesystem from the cleanup directory",
        );
        return Ok(false);
    }
    if dry_run {
        return Ok(true);
    }
    create_plain(trash)?;
    let stage = tempfile::Builder::new()
        .prefix("entry-")
        .tempdir_in(trash)?;
    fs::write(stage.path().join("owner"), b"ohm-build-gc-v1\n")?;
    // A separate mount fails rename. Never fall back to recursive source deletion.
    if let Err(error) = fs::rename(source, stage.path().join("payload")) {
        if error.kind() == io::ErrorKind::CrossesDevices {
            summary.skip_path(
                source,
                "on a different filesystem from the cleanup directory",
            );
            return Ok(false);
        }
        return Err(error)
            .with_context(|| format!("failed to move {} into cleanup trash", source.display()));
    }
    let _ = stage.keep();
    Ok(true)
}

fn drain_trash(
    trash: &Path,
    remaining: &mut usize,
    summary: &mut Summary<'_>,
    dry_run: bool,
    bookkeeping: Option<&str>,
) -> CargoResult<()> {
    if !plain_directory(trash) {
        return Ok(());
    }
    let Some(entries) = summary.payload_entries(trash)? else {
        return Ok(());
    };
    let device = filesystem_device(&fs::symlink_metadata(trash)?);
    for entry in entries {
        summary.tick();
        let entry = entry?;
        if !entry.file_type()?.is_dir() {
            continue;
        }
        let path = entry.path();
        drain_entry(&path, device, remaining, summary, dry_run, bookkeeping)
            .or_else(|error| summary.path_error(&path, error))?;
        if !dry_run && *remaining < 2 {
            summary.pending = true;
            break;
        }
    }
    Ok(())
}

/// A blocked entry in the trash must not prevent draining another retired path.
fn drain_entry(
    path: &Path,
    device: u64,
    remaining: &mut usize,
    summary: &mut Summary<'_>,
    dry_run: bool,
    bookkeeping: Option<&str>,
) -> CargoResult<()> {
    let owner = path.join("owner");
    match fs::symlink_metadata(&owner) {
        Ok(metadata) if !metadata.is_file() => return Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(error.into()),
        Ok(_) => {}
    }
    if fs::read(&owner)? != b"ohm-build-gc-v1\n" {
        return Ok(());
    }
    if fs::read_dir(path)?.any(|child| {
        !child.is_ok_and(|child| child.file_name() == "owner" || child.file_name() == "payload")
    }) {
        return Ok(());
    }
    let payload = path.join("payload");
    let bookkeeping = bookkeeping.map(|name| payload.join(name));
    remove_bounded(
        &payload,
        device,
        remaining,
        summary,
        dry_run,
        bookkeeping.as_deref(),
    )?;
    if !dry_run && absent(&payload) && *remaining >= 2 {
        fs::remove_file(owner)?;
        fs::remove_dir(path)?;
        *remaining -= 2;
        summary.deleted_entries += 2;
    }
    Ok(())
}

/// Visits siblings after a skipped subtree, but never removes its ancestors.
fn remove_bounded(
    path: &Path,
    device: u64,
    remaining: &mut usize,
    summary: &mut Summary<'_>,
    dry_run: bool,
    bookkeeping: Option<&Path>,
) -> CargoResult<bool> {
    remove_entry(path, device, remaining, summary, dry_run, bookkeeping)
        .or_else(|error| summary.path_error(path, error))
}

fn remove_entry(
    path: &Path,
    device: u64,
    remaining: &mut usize,
    summary: &mut Summary<'_>,
    dry_run: bool,
    bookkeeping: Option<&Path>,
) -> CargoResult<bool> {
    if absent(path) {
        return Ok(true);
    }
    if *remaining == 0 {
        return Ok(false);
    }
    let metadata = fs::symlink_metadata(path)?;
    if filesystem_device(&metadata) != device {
        summary.skip_path(path, "on a different filesystem; left untouched");
        return Ok(false);
    }
    if metadata.is_dir() {
        let mut complete = true;
        for child in
            fs::read_dir(path).with_context(|| format!("failed to read {}", path.display()))?
        {
            if *remaining == 0 {
                return Ok(false);
            }
            complete &= remove_bounded(
                &child?.path(),
                device,
                remaining,
                summary,
                dry_run,
                bookkeeping,
            )?;
        }
        if *remaining == 0 || !complete {
            return Ok(false);
        }
        if !dry_run && let Err(error) = fs::remove_dir(path) {
            if error.kind() == io::ErrorKind::DirectoryNotEmpty {
                summary.skip_path(path, "directory contents changed during cleanup");
                return Ok(false);
            }
            return Err(error).with_context(|| format!("failed to remove {}", path.display()));
        }
    } else if !dry_run {
        fs::remove_file(path).with_context(|| format!("failed to remove {}", path.display()))?;
    }
    *remaining -= 1;
    summary.deleted_entries += 1;
    if bookkeeping != Some(path) {
        summary.counts.record(&metadata);
        summary.tick();
    }
    Ok(true)
}

fn profiles(root: &Path) -> CargoResult<Vec<PathBuf>> {
    profiles_matching(root, |path| regular(&path.join(".cargo-build-lock")))
}

fn profiles_matching(root: &Path, is_profile: impl Fn(&Path) -> bool) -> CargoResult<Vec<PathBuf>> {
    let mut result = Vec::new();
    for entry in fs::read_dir(root)? {
        let entry = entry?;
        if !entry.file_type()?.is_dir() || entry.file_name().to_string_lossy().starts_with('.') {
            continue;
        }
        let path = entry.path();
        // A nested shared root has its own provenance and consumer leases.
        if regular(&path.join(Layout::SHARED_REGISTRY_CACHE_MARKER)) {
            continue;
        }
        if is_profile(&path) {
            result.push(path);
            continue;
        }
        for child in fs::read_dir(path)? {
            let child = child?;
            if child.file_type()?.is_dir() && is_profile(&child.path()) {
                result.push(child.path());
            }
        }
    }
    result.sort_by(|a, b| (a.parent() != Some(root), a).cmp(&(b.parent() != Some(root), b)));
    Ok(result)
}

/// GC guards end at their lexical scope, even if another thread forked while held.
/// Consumer leases deliberately have different semantics and remain held by children.
pub(crate) struct CollectorLock(File);

impl Drop for CollectorLock {
    fn drop(&mut self) {
        if let Err(error) = crate::util::flock::unlock(&self.0) {
            tracing::debug!(?error, "could not release build-cache collector lock");
        }
    }
}

pub(crate) fn try_lock(path: &Path, create: bool) -> CargoResult<Option<CollectorLock>> {
    try_lock_file(path, create, true)
}

fn try_lock_file(path: &Path, create: bool, exclusive: bool) -> CargoResult<Option<CollectorLock>> {
    let mut options = OpenOptions::new();
    options.read(true).write(true).create(create);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt as _;
        options.custom_flags(libc::O_NOFOLLOW);
    }
    let file = match options.open(path) {
        Ok(file) => file,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error.into()),
    };
    let Some(lock) = try_lock_opened(file, exclusive)? else {
        return Ok(None);
    };
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt as _;
        let current = fs::symlink_metadata(path)?;
        let opened = lock.0.metadata()?;
        ensure!(
            current.is_file() && current.dev() == opened.dev() && current.ino() == opened.ino(),
            "cache lock changed during acquisition"
        );
    }
    Ok(Some(lock))
}

/// Locks an opened regular file and releases the collector's lock at scope exit.
fn try_lock_opened(file: File, exclusive: bool) -> CargoResult<Option<CollectorLock>> {
    ensure!(
        file.metadata()?.is_file(),
        "cache lock is not a regular file"
    );
    let acquired = if exclusive {
        try_lock_exclusive(&file)
    } else {
        crate::util::flock::try_lock_shared(&file)
    };
    match acquired {
        Ok(()) => {}
        Err(TryLockError::WouldBlock) => return Ok(None),
        Err(TryLockError::Error(error)) => return Err(error.into()),
    }
    Ok(Some(CollectorLock(file)))
}

fn plain_ancestors(root: &Path, path: &Path) -> CargoResult<bool> {
    let mut current = root.to_path_buf();
    for component in path.strip_prefix(root)?.components() {
        let Component::Normal(component) = component else {
            return Ok(false);
        };
        if !plain_directory(&current) {
            return Ok(false);
        }
        current.push(component);
    }
    Ok(true)
}

fn component(name: &str) -> bool {
    !name.is_empty()
        && name != "."
        && name != ".."
        && name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}
fn absent(path: &Path) -> bool {
    fs::symlink_metadata(path).is_err_and(|e| e.kind() == io::ErrorKind::NotFound)
}
fn plain_directory(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok_and(|m| m.is_dir())
}
fn filesystem_device(metadata: &Metadata) -> u64 {
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt as _;
        metadata.dev()
    }
    #[cfg(not(unix))]
    {
        let _ = metadata;
        0
    }
}
fn regular(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok_and(|m| m.is_file())
}
fn create_plain(path: &Path) -> CargoResult<()> {
    match fs::create_dir(path) {
        Ok(()) => {}
        Err(e) if e.kind() == io::ErrorKind::AlreadyExists => {}
        Err(e) => return Err(e.into()),
    }
    ensure!(
        plain_directory(path),
        "cache metadata contains a non-directory: {}",
        path.display()
    );
    Ok(())
}
fn read_regular(path: &Path) -> Option<Vec<u8>> {
    regular(path).then(|| fs::read(path).ok()).flatten()
}
fn read_record<T: for<'de> Deserialize<'de>>(path: &Path) -> Option<T> {
    serde_json::from_slice(&read_regular(path)?).ok()
}
#[cfg(all(test, any(target_os = "linux", target_os = "macos")))]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;

    /// Eligibility assertions should not depend on runner scheduling. Count limits
    /// remain active; the deadline test supplies its own explicit time budget.
    fn collect(
        root: &Path,
        dry_run: bool,
        current_ohm: Option<&str>,
    ) -> CargoResult<Summary<'static>> {
        collect_at(root, dry_run, SystemTime::now(), current_ohm)
    }

    fn collect_at(
        root: &Path,
        dry_run: bool,
        now: SystemTime,
        current_ohm: Option<&str>,
    ) -> CargoResult<Summary<'static>> {
        collect_with_lock_budget(
            root,
            dry_run,
            now,
            Duration::from_secs(60),
            current_ohm,
            &mut CollectionState::default(),
        )
    }

    fn collect_with_lock_budget(
        root: &Path,
        dry_run: bool,
        now: SystemTime,
        lock_budget: Duration,
        current_ohm: Option<&str>,
        state: &mut CollectionState,
    ) -> CargoResult<Summary<'static>> {
        let mut summary = Summary::default();
        super::collect_with_lock_budget(
            root,
            dry_run,
            &mut GcAge::simulated(now, CONTEXT_MAX_IDLE),
            lock_budget,
            current_ohm,
            state,
            &mut summary,
        )?;
        Ok(summary)
    }

    struct Cache {
        _temporary: tempfile::TempDir,
        root: PathBuf,
        compiler: PathBuf,
        driver: PathBuf,
        profile: PathBuf,
    }

    impl Cache {
        fn new() -> CargoResult<Self> {
            let temporary = tempfile::tempdir()?;
            let base = temporary.path().canonicalize()?;
            let root = base.join("cache");
            let profile = root.join("debug");
            fs::create_dir_all(&profile)?;
            File::create(root.join(Layout::SHARED_REGISTRY_CACHE_MARKER))?;
            File::create(profile.join(".cargo-build-lock"))?;
            let metadata = metadata_dir(&root, true)?;
            File::create(metadata.join(CONSUMERS_LOCK))?;
            let compiler = base.join("rustc");
            let driver = base.join("driver");
            fs::write(&compiler, b"compiler")?;
            fs::write(&driver, b"driver")?;
            Ok(Self {
                _temporary: temporary,
                root,
                compiler,
                driver,
                profile,
            })
        }

        fn enroll(&self) -> CargoResult<()> {
            self.enroll_context("abcdef")
        }

        fn enroll_context(&self, context: &str) -> CargoResult<()> {
            record_context(
                &self.root,
                context,
                self.identity(&self.compiler)?,
                self.identity(&self.driver)?,
            )
            .map(|_| ())
        }

        fn tracker(&self) -> CargoResult<Tracker> {
            Tracker::open(&self.root)
        }

        fn record(&self, context: &str) -> CargoResult<ContextRecord> {
            Ok(self.tracker()?.context(context)?.unwrap().record)
        }

        fn set_record(&self, record: &ContextRecord) -> CargoResult<()> {
            self.tracker()?.conn.execute(
                "UPDATE contexts SET record = ?2 WHERE context = ?1",
                rusqlite::params![record.context, serde_json::to_vec(record)?],
            )?;
            Ok(())
        }

        fn used(&self, context: &str) -> CargoResult<SystemTime> {
            Ok(SystemTime::UNIX_EPOCH
                + Duration::from_nanos(
                    self.tracker()?
                        .context(context)?
                        .unwrap()
                        .last_used
                        .unwrap()
                        .try_into()?,
                ))
        }

        fn age_context(&self, context: &str, used: SystemTime) -> CargoResult<()> {
            self.tracker()?.conn.execute(
                "UPDATE contexts SET last_used = ?2 WHERE context = ?1",
                rusqlite::params![context, tracker::timestamp(used)?],
            )?;
            Ok(())
        }

        fn identity(&self, path: &Path) -> CargoResult<FileIdentity> {
            Ok(FileIdentity::from_metadata(
                path.to_path_buf(),
                &fs::metadata(path)?,
            )?)
        }

        fn artifact(&self, relative: &str) -> CargoResult<PathBuf> {
            let path = self.profile.join(relative);
            fs::create_dir_all(&path)?;
            fs::write(path.join("artifact"), b"cached")?;
            Ok(path)
        }

        fn thinlto(&self, context: &str, key: usize, used: SystemTime) -> CargoResult<PathBuf> {
            let directory = self.root.join(THINLTO).join(context).join("0".repeat(32));
            fs::create_dir_all(&directory)?;
            let path = directory.join(format!("{key:032x}.cache"));
            fs::write(&path, b"backend")?;
            File::open(&path)?.set_modified(used)?;
            Ok(path)
        }
    }

    #[test]
    fn busy_context_preserves_its_artifacts_without_blocking_other_contexts_or_trash()
    -> CargoResult<()> {
        for recorded in [true, false] {
            let cache = Cache::new()?;
            let busy = "v2-0000000000000001";
            let idle = "v2-0000000000000002";
            for context in [busy, idle] {
                if recorded {
                    cache.enroll_context(context)?;
                    cache.age_context(context, SystemTime::UNIX_EPOCH)?;
                }
                cache.artifact(&format!("build/registries/{context}"))?;
                cache.thinlto(context, 0, SystemTime::UNIX_EPOCH)?;
            }
            let lease = crate::workspace::build_cache_gc_lease::ConsumerLease::acquire_context(
                &cache.root,
                busy,
            )?;
            let retired = cache.artifact("retired")?;
            assert!(retire(
                &Namespace::Context(idle.to_owned()),
                &cache.root,
                &retired,
                &cache.profile.join(TRASH),
                false,
                &mut Summary::default(),
            )?);
            for dry_run in [true, false] {
                let summary = collect(&cache.root, dry_run, None)?;
                assert_eq!(summary.counts.files, 3);
                assert_eq!(summary.counts.bytes, 19);
                assert_eq!(summary.skipped, [format!("context {busy} (in use)")]);
                assert!(cache.profile.join("build/registries").join(busy).is_dir());
                assert!(cache.root.join(THINLTO).join(busy).is_dir());
                assert_eq!(
                    cache.profile.join("build/registries").join(idle).exists(),
                    dry_run
                );
            }
            drop(lease);
            assert_eq!(collect(&cache.root, false, None)?.counts.files, 2);
            assert!(cache.tracker()?.contexts()?.is_empty());
        }
        Ok(())
    }

    #[test]
    fn legacy_locks_only_block_legacy_namespaces() -> CargoResult<()> {
        let cache = Cache::new()?;
        let context = "v2-0123456789abcdef";
        cache.enroll()?;
        cache.enroll_context(context)?;
        cache.age_context("abcdef", SystemTime::UNIX_EPOCH)?;
        cache.age_context(context, SystemTime::UNIX_EPOCH)?;
        let legacy = cache.artifact("build/registries/abcdef")?;
        let scoped = cache.artifact(&format!("build/registries/{context}"))?;
        let consumer = crate::workspace::build_cache_gc_lease::ConsumerLease::acquire(&cache.root)?;
        let profile = File::open(cache.profile.join(".cargo-build-lock"))?;
        crate::util::flock::lock_shared(&profile)?;
        fs::create_dir(cache.root.join(THINLTO))?;
        let pruner = File::create(cache.root.join(THINLTO).join(".prune-lock"))?;
        crate::util::flock::lock_exclusive(&pruner)?;
        for dry_run in [true, false] {
            let summary = collect(&cache.root, dry_run, None)?;
            assert_eq!(summary.counts.files, 1);
            assert!(summary.busy);
            assert!(legacy.exists());
            assert_eq!(scoped.exists(), dry_run);
        }
        drop((consumer, profile, pruner));
        assert_eq!(collect(&cache.root, false, None)?.counts.files, 1);
        Ok(())
    }

    #[test]
    fn busy_usage_writer_only_postpones_context_and_dependency_rows() -> CargoResult<()> {
        let cache = Cache::new()?;
        let context = "v2-0123456789abcdef";
        cache.enroll_context(context)?;
        cache.age_context(context, SystemTime::UNIX_EPOCH)?;
        let artifact = cache.artifact(&format!("build/registries/{context}"))?;
        cache.enroll()?;
        let entry = "debug/build/registries/abcdef/dep/1111111111111111";
        let dependency = cache.artifact(entry.strip_prefix("debug/").unwrap())?;
        dependency_use(&cache, &[entry], SystemTime::UNIX_EPOCH)?;
        let file_only = [
            cache.artifact("build/workspaces/0123456789abcdef")?,
            cache.thinlto("abcdef", 0, SystemTime::UNIX_EPOCH)?,
            cache.thinlto(&"d".repeat(32), 0, SystemTime::UNIX_EPOCH)?,
        ];
        let tracker = cache.tracker()?;
        tracker.conn.execute_batch("BEGIN IMMEDIATE")?;
        let summary = collect(&cache.root, false, None)?;
        assert!(summary.busy);
        assert_eq!(summary.retired, file_only.len());
        assert!(file_only.iter().all(|path| !path.exists()));
        assert!(artifact.exists());
        assert!(dependency.exists());
        tracker.conn.execute_batch("ROLLBACK")?;
        assert_eq!(collect(&cache.root, false, None)?.retired, 2);
        assert!(!artifact.exists());
        assert!(!dependency.exists());
        Ok(())
    }

    #[test]
    fn thinlto_uses_object_activity_within_a_live_context() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let now = SystemTime::UNIX_EPOCH + Duration::from_secs(1_800_000_000);
        cache.age_context("abcdef", now)?;
        let cold = cache.thinlto("abcdef", 0, now - CONTEXT_MAX_IDLE)?;
        let hot = cache.thinlto("abcdef", 1, now - CONTEXT_MAX_IDLE + Duration::from_secs(1))?;
        let refreshed = cache.thinlto("abcdef", 2, now - CONTEXT_MAX_IDLE)?;
        let staging = cold.parent().unwrap().join("ohm-thinlto-abandoned");
        fs::create_dir(&staging)?;
        fs::write(staging.join("entry"), b"unfinished")?;
        File::open(&staging)?.set_modified(now - CONTEXT_MAX_IDLE)?;
        let unrelated = cold.parent().unwrap().join("keep.txt");
        fs::write(&unrelated, b"unrecognized")?;

        let preview = collect_at(&cache.root, true, now, None)?;
        assert_eq!(preview.counts.files, 3);
        assert_eq!(preview.counts.bytes, 24);
        assert_eq!(
            preview.details.len(),
            1,
            "objects share a concise context summary"
        );
        assert!(!cache.root.join(THINLTO).join(".prune-lock").exists());
        assert!(cold.exists());
        assert!(staging.exists());
        // A compiler hit after discovery must be rechecked before retirement.
        File::open(&refreshed)?.set_modified(now)?;
        let lease = crate::workspace::build_cache_gc_lease::ConsumerLease::acquire(&cache.root)?;
        assert!(collect_at(&cache.root, false, now, None)?.busy);
        drop(lease);
        let collected = collect_at(&cache.root, false, now, None)?;
        assert_eq!(collected.counts.files, 2);
        assert_eq!(collected.counts.bytes, 17);
        assert!(!cold.exists());
        assert!(!staging.exists());
        assert!(hot.exists());
        assert!(refreshed.exists());
        assert!(unrelated.exists());
        assert!(cache.tracker()?.context("abcdef")?.is_some());
        Ok(())
    }

    #[test]
    fn thinlto_retirement_is_bounded_and_resumable() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let now = SystemTime::now();
        cache.age_context("abcdef", now)?;
        for key in 0..DELETE_BUDGET + 3 {
            cache.thinlto(
                "abcdef",
                key,
                now - CONTEXT_MAX_IDLE - Duration::from_secs(1),
            )?;
        }
        // Blocked objects must not fill discovery's limit on every later pass.
        let mut deferred = CollectionState::default();
        deferred.deferred.extend(thinlto_entries(
            &cache.root,
            "abcdef",
            &GcAge::new(now, CONTEXT_MAX_IDLE),
            DELETE_BUDGET + 1,
            &CollectionState::default(),
            &mut Summary::default(),
        )?);
        assert_eq!(
            thinlto_entries(
                &cache.root,
                "abcdef",
                &GcAge::new(now, CONTEXT_MAX_IDLE),
                DELETE_BUDGET + 1,
                &deferred,
                &mut Summary::default()
            )?
            .len(),
            2
        );
        let preview = collect_at(&cache.root, true, now, None)?;
        let limited = collect_with_lock_budget(
            &cache.root,
            false,
            now,
            Duration::ZERO,
            None,
            &mut CollectionState::default(),
        )?;
        assert_eq!(limited.retired, 1);
        assert!(limited.pending);
        let first = collect_at(&cache.root, false, now, None)?;
        assert_eq!(first.retired, DELETE_BUDGET);
        assert!(first.pending);
        let second = collect_at(&cache.root, false, now, None)?;
        assert_eq!(second.retired, 2);
        let mut counts = limited.counts;
        counts.include(&first.counts);
        counts.include(&second.counts);
        let mut pending = second.pending;
        while pending {
            let next = collect_at(&cache.root, false, now, None)?;
            assert_eq!(next.retired, 0);
            assert!(next.deleted_entries > 0);
            counts.include(&next.counts);
            pending = next.pending;
        }
        assert_eq!(counts, preview.counts);
        Ok(())
    }

    #[test]
    fn thinlto_preserves_unknown_records_and_symlinked_objects() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let now = SystemTime::now();
        let object = cache.thinlto("abcdef", 0, now - CONTEXT_MAX_IDLE - Duration::from_secs(1))?;
        let mut record = cache.record("abcdef")?;
        record.version = 2;
        cache.set_record(&record)?;
        assert_eq!(collect(&cache.root, false, None)?.retired, 0);
        assert!(object.exists());
        record.version = 1;
        cache.set_record(&record)?;
        fs::remove_file(&object)?;
        symlink(&cache.compiler, &object)?;
        assert_eq!(collect(&cache.root, false, None)?.retired, 0);
        assert!(cache.compiler.exists());
        // A tracked context with a future name shape is not untracked legacy data.
        let future = "f".repeat(32);
        record_context(
            &cache.root,
            &future,
            cache.identity(&cache.compiler)?,
            cache.identity(&cache.driver)?,
        )?;
        let mut record = cache.record(&future)?;
        record.version = 2;
        cache.set_record(&record)?;
        let object = cache.thinlto(&future, 0, now - CONTEXT_MAX_IDLE - Duration::from_secs(1))?;
        assert_eq!(collect(&cache.root, false, None)?.retired, 0);
        assert!(object.exists());
        Ok(())
    }

    #[test]
    fn legacy_thinlto_obeys_the_old_pruner_lock_and_preserves_unknown_paths() -> CargoResult<()> {
        let cache = Cache::new()?;
        fs::remove_dir_all(cache.root.join(DIRECTORY))?;
        let legacy = cache.root.join(THINLTO).join("0".repeat(32));
        fs::create_dir_all(&legacy)?;
        fs::write(legacy.join("1".repeat(32) + ".cache"), b"legacy")?;
        let unknown = cache.root.join(THINLTO).join("keep-me");
        fs::create_dir(&unknown)?;
        symlink(
            &cache._temporary.path(),
            cache.root.join(THINLTO).join("2".repeat(32)),
        )?;
        let preview = collect(&cache.root, true, None)?;
        assert_eq!(preview.counts.files, 1);
        assert_eq!(preview.counts.bytes, 6);
        assert!(!cache.root.join(DIRECTORY).exists());
        let lock_path = cache.root.join(THINLTO).join(".prune-lock");
        assert!(!lock_path.exists());
        let lock = try_lock(&lock_path, true)?.unwrap();
        assert!(collect(&cache.root, true, None)?.busy);
        assert!(collect(&cache.root, false, None)?.busy);
        assert!(legacy.exists());
        drop(lock);
        assert_eq!(collect(&cache.root, false, None)?.counts, preview.counts);
        assert!(!legacy.exists());
        assert!(unknown.exists());
        assert!(cache.compiler.exists());
        Ok(())
    }

    #[test]
    fn missing_usage_preserves_context_and_provenance_is_immutable() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let path = cache.artifact("build/registries/abcdef")?;
        let before = serde_json::to_vec(&cache.record("abcdef")?)?;
        cache.enroll()?;
        assert_eq!(before, serde_json::to_vec(&cache.record("abcdef")?)?);
        assert_eq!(cache.tracker()?.contexts()?.len(), 1);
        assert_eq!(collect(&cache.root, false, None)?.retired, 0);
        assert!(path.exists());
        assert!(!cache.root.join(DIRECTORY).join("contexts").exists());
        Ok(())
    }

    #[test]
    fn idle_context_expires_with_installed_compiler_at_one_hour() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let shared = cache.artifact("build/registries/abcdef")?;
        let private = cache.artifact("build/workspaces/owner/abcdef")?;
        let incremental = cache.artifact("incremental/owner")?;
        drop(ContextUse::new(
            cache.tracker()?,
            "abcdef",
            Some(Vec::new()),
        )?);
        let last_used = cache.used("abcdef")?;
        let expires = last_used + CONTEXT_MAX_IDLE;
        assert_eq!(
            collect_at(&cache.root, false, expires - Duration::from_nanos(1), None)?.retired,
            0
        );
        let database = cache.root.join(DIRECTORY).join(tracker::DATABASE);
        let before = fs::read(&database)?;
        let wal = cache.root.join(DIRECTORY).join("cache.sqlite-wal");
        let wal_before = fs::read(&wal)?;
        let dry_run = collect_at(&cache.root, true, expires, None)?;
        assert_eq!(dry_run.retired, 1);
        assert!(
            dry_run
                .details
                .iter()
                .any(|line| line.contains("unused for at least 1 hour"))
        );
        assert_eq!(dry_run.counts.files, 1);
        assert_eq!(dry_run.counts.bytes, 6);
        assert_eq!(
            fs::read(database)?,
            before,
            "dry run leaves the database unchanged"
        );
        assert_eq!(
            fs::read(wal)?,
            wal_before,
            "dry run does not checkpoint usage"
        );
        assert!(shared.exists());
        let collected = collect_at(&cache.root, false, expires, None)?;
        assert_eq!(collected.retired, 1);
        assert_eq!(collected.counts, dry_run.counts);
        assert!(!shared.exists());
        assert!(private.exists());
        assert!(cache.tracker()?.context("abcdef")?.is_none());
        assert!(incremental.exists());
        assert!(cache.compiler.exists());
        assert!(cache.driver.exists());
        Ok(())
    }

    /// Models prior use without sleeping or changing filesystem timestamps.
    fn dependency_use(cache: &Cache, entries: &[&str], used: SystemTime) -> CargoResult<()> {
        let entries = entries.iter().map(PathBuf::from).collect::<Vec<_>>();
        drop(ContextUse::new(
            cache.tracker()?,
            "abcdef",
            Some(entries.clone()),
        )?);
        let tracker = cache.tracker()?;
        for entry in entries {
            tracker.conn.execute(
                "UPDATE dependencies SET last_used = ?2 WHERE entry = ?1",
                rusqlite::params![
                    cargo_util::paths::path2bytes(&entry)?,
                    tracker::timestamp(used)?
                ],
            )?;
        }
        Ok(())
    }

    #[test]
    fn rollback_preserves_newly_used_objects_in_preview_and_cleanup() -> CargoResult<()> {
        let cache = Cache::new()?;
        let now = SystemTime::now();
        cache.enroll()?;
        cache.age_context("abcdef", now + Duration::from_hours(3))?;
        let recent = cache.thinlto("abcdef", 0, now)?;
        let legacy = cache.artifact("build/registries/0000000000000001")?;

        for dry_run in [true, false] {
            // GC starts two hours ahead, then the clock rolls back before taking the lease.
            let mut age = GcAge::new(now + Duration::from_hours(2), Duration::from_hours(1));
            assert!(age.expired(now));
            let mut summary = Summary::default();
            super::collect_with_lock_budget(
                &cache.root,
                dry_run,
                &mut age,
                Duration::from_secs(60),
                None,
                &mut CollectionState::default(),
                &mut summary,
            )?;
            assert_eq!(summary.retired, 1, "legacy data is immediately eligible");
            assert!(recent.is_file());
            assert_eq!(legacy.exists(), dry_run);
        }
        Ok(())
    }

    #[test]
    fn idle_dependency_variants_expire_while_overlapping_graphs_stay_warm() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let old = "debug/build/registries/abcdef/dep/1111111111111111";
        let current = "debug/build/registries/abcdef/dep/2222222222222222";
        let transitive = "debug/build/registries/abcdef/leaf/3333333333333333";
        let unknown = cache.artifact("build/registries/abcdef/unknown/4444444444444444")?;
        for entry in [old, current, transitive] {
            cache.artifact(entry.strip_prefix("debug/").unwrap())?;
        }
        let now = SystemTime::now();
        dependency_use(&cache, &[old, transitive], now - CONTEXT_MAX_IDLE)?;
        dependency_use(&cache, &[current, transitive], now)?;
        assert_eq!(
            collect_at(&cache.root, true, now - Duration::from_nanos(1), None)?.retired,
            0
        );
        let dry_run = collect_at(&cache.root, true, now, None)?;
        assert_eq!(dry_run.retired, 1);
        assert_eq!(dry_run.counts.files, 1);
        assert_eq!(dry_run.counts.bytes, 6);
        assert!(
            dry_run.details[0]
                .contains("dependency debug/build/registries/abcdef/dep/1111111111111111")
        );
        assert!(cache.root.join(old).is_dir());
        let removed = collect_at(&cache.root, false, now, None)?;
        assert_eq!(removed.counts, dry_run.counts);
        assert!(!cache.root.join(old).exists());
        assert!(cache.root.join(current).is_dir());
        assert!(cache.root.join(transitive).is_dir());
        assert!(
            unknown.is_dir(),
            "untracked entries have no proven last use"
        );
        assert_eq!(
            cache
                .tracker()?
                .conn
                .query_row("SELECT count(*) FROM dependencies", [], |row| row
                    .get::<_, usize>(0))?,
            2
        );
        Ok(())
    }

    #[test]
    fn dependency_batches_recheck_queued_entries_without_rescanning() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let now = SystemTime::now();
        let entries: Vec<_> = (0..RENAME_BUDGET + 3)
            .map(|i| format!("debug/build/registries/abcdef/dep/{i:016x}"))
            .collect();
        for entry in &entries {
            cache.artifact(entry.strip_prefix("debug/").unwrap())?;
        }
        let old = now - CONTEXT_MAX_IDLE * 2;
        dependency_use(
            &cache,
            &entries.iter().map(String::as_str).collect::<Vec<_>>(),
            old,
        )?;
        let mut state = CollectionState::default();
        let mut pass = || {
            collect_with_lock_budget(
                &cache.root,
                false,
                now,
                Duration::from_secs(60),
                None,
                &mut state,
            )
        };
        let first = pass()?;
        assert_eq!(first.retired, RENAME_BUDGET);
        assert!(first.pending);

        // Reuse one queued variant, replace another with an unrelated file,
        // and introduce a newly eligible row after the initial scan.
        let refreshed = &entries[RENAME_BUDGET];
        dependency_use(&cache, &[refreshed], now)?;
        let replaced = cache.root.join(&entries[RENAME_BUDGET + 1]);
        fs::remove_dir_all(&replaced)?;
        fs::write(&replaced, b"keep")?;
        let late = "debug/build/registries/abcdef/dep/ffffffffffffffff";
        cache.artifact(late.strip_prefix("debug/").unwrap())?;
        dependency_use(&cache, &[late], old)?;

        let second = pass()?;
        assert_eq!(second.retired, 1);
        assert!(!second.pending);
        assert!(cache.root.join(refreshed).is_dir());
        assert_eq!(fs::read(&replaced)?, b"keep");
        assert!(
            second
                .skipped
                .iter()
                .any(|detail| detail.ends_with("(dependency path is no longer a plain directory)"))
        );
        assert!(!cache.root.join(entries.last().unwrap()).exists());
        assert!(cache.root.join(late).is_dir());
        assert_eq!(collect_at(&cache.root, false, now, None)?.retired, 1);
        assert!(!cache.root.join(late).exists());
        Ok(())
    }

    #[test]
    fn dependency_usage_revalidates_activity_and_survives_long_builds() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let entry = "debug/build/registries/abcdef/dep/1111111111111111";
        cache.artifact(entry.strip_prefix("debug/").unwrap())?;
        let now = SystemTime::now();
        dependency_use(&cache, &[entry], now - CONTEXT_MAX_IDLE)?;
        let profiles = profiles(&cache.root)?;
        let tracker = cache.tracker()?;
        let candidates = idle_dependencies(
            &cache.root,
            &profiles,
            "abcdef",
            &GcAge::new(now, CONTEXT_MAX_IDLE),
            Some(&tracker),
            &mut Summary::default(),
        )
        .unwrap();
        assert_eq!(candidates.len(), 1);
        let lease = crate::workspace::build_cache_gc_lease::ConsumerLease::acquire(&cache.root)?;
        let mut usage = ContextUse::new(cache.tracker()?, "abcdef", Some(vec![entry.into()]))?;
        assert!(
            candidates[0]
                .detail(
                    &cache.root,
                    &profiles,
                    &GcAge::new(now, CONTEXT_MAX_IDLE),
                    None,
                    Some(&tracker)
                )
                .is_none()
        );
        dependency_use(&cache, &[entry], now - CONTEXT_MAX_IDLE * 2)?;
        cache.age_context("abcdef", now - CONTEXT_MAX_IDLE * 2)?;
        usage.used_through = tracker::timestamp(now - CONTEXT_MAX_IDLE * 2)?;
        assert!(collect(&cache.root, false, None)?.busy);
        let completed = SystemTime::now();
        drop(usage);
        drop(lease);
        assert!(cache.used("abcdef")? >= completed);
        // Completion can share a clock tick with the preceding read. Expiry is
        // inclusive, so use a cutoff strictly before that tick.
        assert!(!tracker.dependency_expired(
            "abcdef",
            Path::new(entry),
            tracker::timestamp(completed - Duration::from_nanos(1))?
        )?);
        assert_eq!(collect(&cache.root, false, None)?.retired, 0);
        Ok(())
    }

    #[test]
    fn snapshot_import_and_malformed_records_preserve_dependencies() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let entry = "debug/build/registries/abcdef/dep/1111111111111111";
        let artifact = cache.artifact(entry.strip_prefix("debug/").unwrap())?;
        let now = SystemTime::now();
        dependency_use(&cache, &[entry], now - CONTEXT_MAX_IDLE * 2)?;
        drop(ContextUse::new(cache.tracker()?, "abcdef", None)?);
        assert_eq!(collect(&cache.root, false, None)?.retired, 0);
        let tracker = cache.tracker()?;
        tracker
            .conn
            .execute("UPDATE contexts SET all_used = NULL", [])?;
        let original = cache.record("abcdef")?;
        tracker
            .conn
            .execute("UPDATE contexts SET record = x'00'", [])?;
        assert_eq!(collect(&cache.root, false, None)?.retired, 0);
        cache.set_record(&original)?;
        assert_eq!(collect(&cache.root, true, None)?.retired, 1);
        dependency_use(&cache, &["../../outside"], now - CONTEXT_MAX_IDLE * 2)?;
        assert_eq!(collect(&cache.root, false, None)?.retired, 0);
        assert!(artifact.is_dir());
        Ok(())
    }

    #[test]
    fn future_usage_is_preserved_and_database_symlinks_are_rejected() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let artifact = cache.artifact("build/registries/abcdef")?;
        cache.age_context("abcdef", SystemTime::now() + CONTEXT_MAX_IDLE)?;
        drop(ContextUse::new(
            cache.tracker()?,
            "abcdef",
            Some(Vec::new()),
        )?);
        assert_eq!(collect(&cache.root, false, None)?.retired, 0);
        let database = cache.root.join(DIRECTORY).join(tracker::DATABASE);
        let external = cache._temporary.path().join("database");
        fs::rename(&database, &external)?;
        symlink(&external, &database)?;
        let before = fs::read(&external)?;
        assert!(cache.tracker().is_err());
        assert!(collect(&cache.root, false, None).is_err());
        assert_eq!(fs::read(external)?, before);
        assert!(artifact.is_dir());
        Ok(())
    }

    #[test]
    fn corrupt_and_newer_databases_never_become_untracked_legacy_caches() -> CargoResult<()> {
        for state in ["corrupt", "newer", "missing"] {
            let cache = Cache::new()?;
            cache.enroll()?;
            let artifact = cache.artifact("build/registries/0123456789abcdef")?;
            if state == "corrupt" {
                // Checkpoint first: an intact WAL can recover damaged main-file pages.
                cache
                    .tracker()?
                    .conn
                    .execute_batch("PRAGMA wal_checkpoint(TRUNCATE)")?;
                fs::write(
                    cache.root.join(DIRECTORY).join(tracker::DATABASE),
                    b"invalid sqlite",
                )?;
            } else if state == "newer" {
                cache
                    .tracker()?
                    .conn
                    .pragma_update(None, "user_version", 999)?;
            } else {
                fs::remove_file(cache.root.join(DIRECTORY).join(tracker::DATABASE))?;
            }
            assert!(collect(&cache.root, true, None).is_err(), "{state}");
            assert!(collect(&cache.root, false, None).is_err(), "{state}");
            assert!(artifact.is_dir());
        }
        Ok(())
    }

    #[test]
    fn concurrent_builds_batch_usage_without_losing_rows() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let root = &cache.root;
        std::thread::scope(|scope| -> CargoResult<()> {
            let handles = (0..4)
                .map(|worker| {
                    scope.spawn(move || -> CargoResult<()> {
                        for index in 0..8 {
                            drop(ContextUse::new(
                                Tracker::open(root)?,
                                "abcdef",
                                Some(vec![PathBuf::from(format!(
                                    "debug/build/registries/abcdef/dep/{worker:08x}{index:08x}"
                                ))]),
                            )?);
                        }
                        Ok(())
                    })
                })
                .collect::<Vec<_>>();
            for handle in handles {
                handle.join().unwrap()?;
            }
            Ok(())
        })?;
        assert_eq!(
            cache
                .tracker()?
                .conn
                .query_row("SELECT count(*) FROM dependencies", [], |row| row
                    .get::<_, usize>(0))?,
            32
        );
        cache.tracker()?.forget_context("abcdef")?;
        assert_eq!(
            cache
                .tracker()?
                .conn
                .query_row("SELECT count(*) FROM dependencies", [], |row| row
                    .get::<_, usize>(0))?,
            0
        );
        Ok(())
    }

    #[test]
    fn throttled_usage_never_expires_early_or_blocks_on_a_writer() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let mut tracker = cache.tracker()?;
        let entries = [
            PathBuf::from("debug/build/registries/abcdef/dep/1111111111111111"),
            PathBuf::from("debug/build/registries/abcdef/dep/2222222222222222"),
        ];
        let resolution =
            Duration::from_secs(crate::workspace::global_cache_tracker::UPDATE_RESOLUTION);
        let boundary = std::time::UNIX_EPOCH + resolution * 1_000;
        let first = boundary + Duration::from_nanos(1);
        let last = boundary + resolution - Duration::from_nanos(1);
        let used_through = tracker.touch("abcdef", Some(&entries[..1]), first)?;
        assert_eq!(used_through, tracker::timestamp(boundary + resolution)?);
        let changes = tracker.conn.total_changes();
        let wal = cache.root.join(DIRECTORY).join("cache.sqlite-wal");
        let before = fs::read(&wal)?;

        // A warm reader neither acquires the writer lock nor changes the WAL.
        let mut writer = cache.tracker()?;
        let transaction = writer
            .conn
            .transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        tracker.touch("abcdef", Some(&entries[..1]), last)?;
        assert_eq!(tracker.conn.total_changes(), changes);
        assert_eq!(fs::read(&wal)?, before);
        drop(transaction);

        // A newly selected variant is registered even inside the same interval.
        tracker.touch("abcdef", Some(&entries), last)?;
        assert_eq!(tracker.conn.total_changes(), changes + 1);
        assert!(!tracker.dependency_expired("abcdef", &entries[0], tracker::timestamp(last)?)?);
        assert!(tracker.dependency_expired("abcdef", &entries[0], used_through)?);
        let expires = boundary + resolution + CONTEXT_MAX_IDLE;
        assert!(expires >= last + CONTEXT_MAX_IDLE);
        assert!(expires < first + CONTEXT_MAX_IDLE + resolution);

        // Crossing a bucket renews only the selected variant, not its sibling.
        tracker.touch(
            "abcdef",
            Some(&entries[..1]),
            boundary + resolution + Duration::from_nanos(1),
        )?;
        assert_eq!(
            tracker.idle_dependencies("abcdef", used_through)?,
            vec![entries[1].clone()]
        );
        Ok(())
    }

    #[test]
    fn completion_refreshes_only_after_the_recorded_interval() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let mut tracker = cache.tracker()?;
        let entries = Some(vec![PathBuf::from(
            "debug/build/registries/abcdef/dep/1111111111111111",
        )]);
        let used_through = tracker.touch("abcdef", entries.as_deref(), SystemTime::now())?;
        let mut usage = ContextUse {
            tracker,
            context: "abcdef".into(),
            entries,
            used_through,
        };
        let boundary = std::time::UNIX_EPOCH + Duration::from_nanos(used_through.try_into()?);
        let changes = usage.tracker.conn.total_changes();
        usage.refresh(boundary)?;
        assert_eq!(usage.tracker.conn.total_changes(), changes);
        usage.refresh(boundary + CONTEXT_MAX_IDLE)?;
        assert_eq!(
            usage.used_through,
            tracker::timestamp(boundary + CONTEXT_MAX_IDLE)?
        );
        assert_eq!(usage.tracker.conn.total_changes(), changes + 2);
        assert!(!usage.tracker.dependency_expired(
            "abcdef",
            &usage.entries.as_ref().unwrap()[0],
            used_through,
        )?);
        Ok(())
    }

    #[test]
    fn repeated_warm_usage_keeps_the_write_ahead_log_bounded() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let mut tracker = cache.tracker()?;
        let entries = [PathBuf::from(
            "debug/build/registries/abcdef/dep/0123456789abcdef",
        )];
        let resolution =
            Duration::from_secs(crate::workspace::global_cache_tracker::UPDATE_RESOLUTION);
        let now = std::time::UNIX_EPOCH + resolution * 1_000;
        for index in 0..2_000 {
            tracker.touch("abcdef", Some(&entries), now + resolution * index)?;
        }
        drop(tracker);
        // Automatic checkpoints still recycle the WAL even though exiting a build
        // no longer forces a checkpoint. Without them it grows with every update.
        assert!(
            fs::metadata(cache.root.join(DIRECTORY).join("cache.sqlite-wal"))?.len() < 1024 * 1024
        );
        assert_eq!(cache.used("abcdef")?, now + resolution * 1_999);
        Ok(())
    }

    #[test]
    fn file_based_contexts_remain_collectable_without_creating_a_database() -> CargoResult<()> {
        use std::os::unix::fs::PermissionsExt as _;

        let cache = Cache::new()?;
        cache.enroll()?;
        let record = cache.record("abcdef")?;
        let directory = cache.root.join(DIRECTORY);
        for suffix in ["", "-wal", "-shm"] {
            fs::remove_file(directory.join(format!("{}{suffix}", tracker::DATABASE)))?;
        }
        fs::create_dir(directory.join("contexts"))?;
        fs::write(
            directory.join("contexts/abcdef.json"),
            serde_json::to_vec(&record)?,
        )?;
        fs::create_dir(directory.join(LAST_USED))?;
        let used = SystemTime::now() - CONTEXT_MAX_IDLE;
        File::create(directory.join("last-used/abcdef"))?.set_modified(used)?;
        let artifact = cache.artifact("build/registries/abcdef")?;
        assert_eq!(collect(&cache.root, true, None)?.retired, 1);
        assert!(artifact.is_dir());
        let contexts = directory.join("contexts");
        fs::set_permissions(&contexts, fs::Permissions::from_mode(0o555))?;
        if tempfile::NamedTempFile::new_in(&contexts).is_err() {
            let mut state = CollectionState::default();
            let failed = collect_with_lock_budget(
                &cache.root,
                false,
                SystemTime::now(),
                Duration::from_secs(60),
                None,
                &mut state,
            )?;
            let record = contexts.join("abcdef.json");
            assert_eq!(failed.counts.files, 1);
            assert_eq!(failed.retired, 0);
            assert!(failed.errors.iter().any(|error| {
                error.starts_with(&format!("{} (Permission denied", record.display()))
            }));
            assert!(
                state
                    .deferred
                    .contains(&Namespace::Context("abcdef".into()))
            );
            assert!(record.is_file());
            assert!(directory.join("last-used/abcdef").is_file());
            assert!(!artifact.exists());
        }
        fs::set_permissions(&contexts, fs::Permissions::from_mode(0o755))?;
        assert_eq!(collect(&cache.root, false, None)?.retired, 1);
        assert!(!artifact.exists());
        assert!(!directory.join("contexts/abcdef.json").exists());
        assert!(!directory.join(tracker::DATABASE).exists());
        Ok(())
    }

    #[test]
    fn older_cargo_activity_protects_tracked_dependencies_and_missing_payloads_lose_rows()
    -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let entry = "debug/build/registries/abcdef/dep/1111111111111111";
        let artifact = cache.artifact(entry.strip_prefix("debug/").unwrap())?;
        dependency_use(&cache, &[entry], SystemTime::now() - CONTEXT_MAX_IDLE * 2)?;
        let directory = cache.root.join(DIRECTORY).join(LAST_USED);
        fs::create_dir(&directory)?;
        let marker = File::create(directory.join("abcdef"))?;
        assert_eq!(collect(&cache.root, true, None)?.retired, 0);
        marker.set_modified(SystemTime::now() - CONTEXT_MAX_IDLE * 2)?;
        assert_eq!(collect(&cache.root, true, None)?.retired, 1);
        fs::remove_dir_all(&artifact)?;
        collect(&cache.root, false, None)?;
        assert_eq!(
            cache
                .tracker()?
                .conn
                .query_row("SELECT count(*) FROM dependencies", [], |row| row
                    .get::<_, usize>(0))?,
            0
        );
        Ok(())
    }

    #[test]
    fn compiler_retirement_is_immediate_and_preserves_unrelated_incremental() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let shared = cache.artifact("build/registries/abcdef")?;
        let private = cache.artifact("build/workspaces/owner/abcdef")?;
        let other = cache.artifact("build/registries/other")?;
        let incremental = cache.artifact("incremental/owner")?;
        fs::remove_file(&cache.driver)?;
        let dry = collect(&cache.root, true, None)?;
        assert_eq!(dry.retired, 1);
        assert!(shared.exists());
        assert!(
            dry.details
                .iter()
                .any(|line| line.contains("compiler or driver changed or removed"))
        );
        assert_eq!(collect(&cache.root, false, None)?.retired, 1);
        assert!(!shared.exists());
        assert!(
            private.exists(),
            "unrecognized private namespace is preserved"
        );
        assert!(other.exists());
        assert!(incremental.exists());
        Ok(())
    }

    #[test]
    fn driver_replacement_is_obsolete_but_alias_retarget_is_not() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let record = cache.record("abcdef")?;
        let alias = cache._temporary.path().join("ohm");
        symlink(&cache.compiler, &alias)?;
        fs::remove_file(&alias)?;
        symlink(&cache.driver, &alias)?;
        assert!(!record.retired());
        fs::write(&cache.driver, b"replacement driver")?;
        assert!(record.retired());
        fs::remove_file(&cache.driver)?;
        symlink(&cache.compiler, &cache.driver)?;
        assert!(!record.retired(), "a replacement symlink is ambiguous");
        Ok(())
    }

    #[test]
    fn unavailable_filesystem_preserves_context() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let mut record = cache.record("abcdef")?;
        fs::remove_file(&cache.compiler)?;
        record.compiler_anchor.device ^= 1;
        assert!(!record.retired());
        cache.set_record(&record)?;
        let path = cache.artifact("build/registries/abcdef")?;
        assert_eq!(collect(&cache.root, false, None)?.retired, 0);
        assert!(path.exists());
        Ok(())
    }

    #[test]
    fn temporary_collector_guard_does_not_extend_to_inherited_descriptors() -> CargoResult<()> {
        let cache = Cache::new()?;
        let path = cache.root.join(DIRECTORY).join("collector.lock");
        let guard = try_lock(&path, true)?.unwrap();
        let inherited = guard.0.try_clone()?;
        drop(guard);
        assert!(try_lock(&path, false)?.is_some());
        drop(inherited);
        Ok(())
    }

    #[test]
    fn runtime_and_profile_readers_prevent_retirement_without_waiting() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let artifact = cache.artifact("build/registries/abcdef")?;
        fs::remove_file(&cache.driver)?;
        let consumers = OpenOptions::new()
            .read(true)
            .write(true)
            .open(cache.root.join(DIRECTORY).join(CONSUMERS_LOCK))?;
        crate::util::flock::lock_shared(&consumers)?;
        assert!(collect(&cache.root, false, None)?.busy);
        assert!(artifact.exists());
        crate::util::flock::unlock(&consumers)?;
        drop(consumers);
        let profile = OpenOptions::new()
            .read(true)
            .write(true)
            .open(cache.profile.join(".cargo-build-lock"))?;
        crate::util::flock::lock_shared(&profile)?;
        assert_eq!(
            collect(&cache.root, false, None)?.blocking_locks,
            BTreeSet::from([cache.profile.join(".cargo-build-lock")])
        );
        assert!(artifact.exists());
        crate::util::flock::unlock(&profile)?;
        drop(profile);
        assert!(!collect(&cache.root, false, None)?.busy);
        assert!(!artifact.exists());
        Ok(())
    }

    #[test]
    fn retirement_is_batched_and_removes_completed_bookkeeping() -> CargoResult<()> {
        let cache = Cache::new()?;
        for index in 0..RENAME_BUDGET + 2 {
            let context = format!("context-{index}");
            record_context(
                &cache.root,
                &context,
                cache.identity(&cache.compiler)?,
                cache.identity(&cache.driver)?,
            )?;
            cache.artifact(&format!("build/registries/{context}"))?;
        }
        fs::remove_file(&cache.driver)?;
        let preview = collect(&cache.root, true, None)?;
        assert_eq!(preview.retired, RENAME_BUDGET + 2);
        assert_eq!(preview.counts.files, (RENAME_BUDGET + 2) as u64);
        assert_eq!(preview.counts.bytes, ((RENAME_BUDGET + 2) * 6) as u64);
        let first = collect(&cache.root, false, None)?;
        assert!(first.retired <= RENAME_BUDGET);
        assert!(first.pending);
        assert_eq!(
            cache.tracker()?.contexts()?.len(),
            RENAME_BUDGET + 2 - first.retired
        );
        let mut completed = first.retired;
        for _ in 0..32 {
            let next = collect(&cache.root, false, None)?;
            assert!(next.retired <= RENAME_BUDGET);
            completed += next.retired;
            if !next.pending {
                break;
            }
        }
        assert_eq!(completed, RENAME_BUDGET + 2);
        assert_eq!(cache.tracker()?.contexts()?.len(), 0);
        assert!(!cache.root.join(DIRECTORY).join("candidates.json").exists());
        Ok(())
    }

    #[test]
    fn elapsed_soft_deadline_still_makes_progress() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        cache.artifact("build/registries/abcdef")?;
        let release = cache.root.join("release");
        fs::create_dir_all(release.join("build/registries/abcdef"))?;
        File::create(release.join(".cargo-build-lock"))?;
        fs::write(release.join("build/registries/abcdef/artifact"), b"cached")?;
        fs::remove_file(&cache.driver)?;
        let mut state = CollectionState::default();
        let first = collect_with_lock_budget(
            &cache.root,
            false,
            SystemTime::now(),
            Duration::ZERO,
            None,
            &mut state,
        )?;
        assert!(first.pending);
        assert!(first.advanced);
        assert_eq!(first.retired, 0);
        let second = collect_with_lock_budget(
            &cache.root,
            false,
            SystemTime::now(),
            Duration::ZERO,
            None,
            &mut state,
        )?;
        assert_eq!(second.retired, 1);
        assert!(cache.tracker()?.context("abcdef")?.is_none());
        Ok(())
    }

    #[test]
    fn partial_legacy_context_retirement_keeps_metadata_discoverable() -> CargoResult<()> {
        let cache = Cache::new()?;
        let context = "0123456789abcdef";
        let payload = cache.artifact(&format!("build/registries/{context}"))?;
        let metadata = cache
            .root
            .join(DIRECTORY)
            .join("dependencies")
            .join(context);
        fs::create_dir_all(&metadata)?;
        fs::write(metadata.join("usage"), b"gc bookkeeping")?;
        let first = collect_with_lock_budget(
            &cache.root,
            false,
            SystemTime::now(),
            Duration::ZERO,
            None,
            &mut CollectionState::default(),
        )?;
        assert!(first.pending);
        assert!(first.advanced);
        assert_eq!(first.retired, 0);
        assert!(!payload.exists());
        assert!(metadata.exists());

        // A fresh collection must also finish after the previous process exited.
        let second = collect_with_lock_budget(
            &cache.root,
            false,
            SystemTime::now(),
            Duration::ZERO,
            None,
            &mut CollectionState::default(),
        )?;
        assert_eq!(second.retired, 1);
        assert!(!metadata.exists());
        assert!(!second.pending);
        Ok(())
    }

    #[test]
    fn partial_context_batches_count_completion_once() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        for index in 0..RENAME_BUDGET + 2 {
            let profile = cache.root.join(format!("profile-{index}"));
            fs::create_dir_all(profile.join("build/registries/abcdef"))?;
            File::create(profile.join(".cargo-build-lock"))?;
            fs::write(profile.join("build/registries/abcdef/artifact"), b"cached")?;
        }
        fs::remove_file(&cache.driver)?;
        let first = collect(&cache.root, false, None)?;
        assert_eq!(first.retired, 0);
        assert!(first.pending);
        let mut completed = 0;
        for _ in 0..10 {
            let next = collect(&cache.root, false, None)?;
            completed += next.retired;
            if !next.pending {
                break;
            }
        }
        assert_eq!(completed, 1);
        assert!(cache.tracker()?.context("abcdef")?.is_none());
        Ok(())
    }

    #[test]
    fn trash_does_not_delete_another_filesystem() -> CargoResult<()> {
        let cache = Cache::new()?;
        let payload = cache.artifact("payload")?;
        let wrong_device = filesystem_device(&fs::symlink_metadata(&payload)?) ^ 1;
        let mut remaining = DELETE_BUDGET;
        let mut summary = Summary::default();
        remove_bounded(
            &payload,
            wrong_device,
            &mut remaining,
            &mut summary,
            false,
            None,
        )?;
        assert!(payload.join("artifact").exists());
        assert_eq!(remaining, DELETE_BUDGET);
        assert_eq!(summary.deleted_entries, 0);
        assert_eq!(
            summary.skipped,
            [format!(
                "{} (on a different filesystem; left untouched)",
                payload.display()
            )]
        );
        remove_bounded(
            &payload,
            wrong_device,
            &mut remaining,
            &mut summary,
            true,
            None,
        )?;
        assert_eq!(summary.counts, FileCounts::default());
        Ok(())
    }

    #[test]
    fn trash_deletion_is_bounded_resumable_and_does_not_follow_links() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let path = cache.artifact("build/registries/abcdef")?;
        for index in 0..DELETE_BUDGET + 5 {
            fs::write(path.join(index.to_string()), b"x")?;
        }
        symlink(&cache.compiler, path.join("external"))?;
        fs::remove_file(&cache.driver)?;
        let dry_run = collect(&cache.root, true, None)?;
        assert_eq!(dry_run.counts.files, (DELETE_BUDGET + 7) as u64);
        assert_eq!(
            dry_run.counts.bytes,
            (DELETE_BUDGET + 11) as u64 + fs::symlink_metadata(path.join("external"))?.len()
        );
        let first = collect(&cache.root, false, None)?;
        assert!(first.pending);
        assert_eq!(first.deleted_entries, DELETE_BUDGET);
        assert!(!path.exists());
        assert!(cache.compiler.exists());
        let pending = collect(&cache.root, true, None)?;
        assert_eq!(pending.retired, 0);
        let next = collect(&cache.root, false, None)?;
        assert!(!next.pending);
        assert_eq!(pending.counts, next.counts);
        let mut counts = first.counts;
        counts.include(&next.counts);
        assert_eq!(counts, dry_run.counts);
        assert!(cache.compiler.exists());
        Ok(())
    }

    #[test]
    fn legacy_cleanup_needs_no_records_or_age_and_preview_is_read_only() -> CargoResult<()> {
        let cache = Cache::new()?;
        fs::remove_dir_all(cache.root.join(DIRECTORY))?;
        let registry = cache.artifact("build/registries/0123456789abcdef-all-native-all")?;
        let private = cache.artifact("build/workspaces/0123456789abcdef/context")?;
        let incremental = cache.artifact("incremental/0123456789abcdef")?;
        let unknown = cache.artifact("build/registries/not-a-context")?;
        let thinlto = cache.artifact("thinlto/0123456789abcdef")?;
        let preview = collect(&cache.root, true, None)?;
        assert_eq!(preview.retired, 2);
        assert_eq!(preview.counts.files, 3);
        assert_eq!(preview.counts.bytes, 18);
        assert!(!cache.root.join(DIRECTORY).exists());
        assert!(registry.exists());
        assert!(private.exists());
        assert!(incremental.exists());
        let profile_lock = File::open(cache.profile.join(".cargo-build-lock"))?;
        crate::util::flock::lock_shared(&profile_lock)?;
        assert!(collect(&cache.root, true, None)?.busy);
        assert!(collect(&cache.root, false, None)?.busy);
        assert!(registry.exists());
        crate::util::flock::unlock(&profile_lock)?;
        drop(profile_lock);
        let collected = collect(&cache.root, false, None)?;
        assert_eq!(collected.counts, preview.counts);
        assert!(!registry.exists());
        assert!(!private.exists());
        assert!(!incremental.exists());
        assert!(unknown.exists());
        assert!(thinlto.exists());
        Ok(())
    }

    #[test]
    fn older_ohm_releases_expire_immediately_even_while_installed() -> CargoResult<()> {
        let cache = Cache::new()?;
        for (id, version) in [
            ("old-rust", Some("ohm-1.98.1-9")),
            ("old-ohm", Some("ohm-1.99.0-1")),
            ("current", Some("ohm-1.99.0-2")),
            ("newer", Some("ohm-1.99.0-10")),
            ("unknown", None),
        ] {
            record_context(
                &cache.root,
                id,
                cache.identity(&cache.compiler)?,
                cache.identity(&cache.driver)?,
            )?;
            let mut record = cache.record(id)?;
            record.ohm_version = version.map(str::to_owned);
            cache.set_record(&record)?;
            drop(ContextUse::new(cache.tracker()?, id, Some(Vec::new()))?);
            cache.artifact(&format!("build/registries/{id}"))?;
            cache.thinlto(id, 0, SystemTime::now())?;
        }
        assert_eq!(collect(&cache.root, true, None)?.retired, 0);
        let current = Some("ohm-1.99.0-2");
        let lease = crate::workspace::build_cache_gc_lease::ConsumerLease::acquire(&cache.root)?;
        assert!(collect(&cache.root, false, current)?.busy);
        drop(lease);
        let preview = collect(&cache.root, true, current)?;
        assert_eq!(preview.retired, 2);
        assert!(
            preview
                .details
                .iter()
                .all(|line| line.contains("current is ohm-1.99.0-2"))
        );
        assert_eq!(collect(&cache.root, false, current)?.counts, preview.counts);
        for id in ["old-rust", "old-ohm"] {
            assert!(!cache.profile.join("build/registries").join(id).exists());
            assert!(!cache.root.join(THINLTO).join(id).exists());
        }
        for id in ["current", "newer", "unknown"] {
            assert!(cache.profile.join("build/registries").join(id).exists());
            assert!(cache.root.join(THINLTO).join(id).exists());
        }
        assert!(cache.compiler.exists());
        assert!(cache.driver.exists());
        Ok(())
    }

    #[test]
    fn installed_version_is_recorded_and_old_records_can_use_the_install_marker() -> CargoResult<()>
    {
        let cache = Cache::new()?;
        let sysroot = cache._temporary.path().canonicalize()?.join("toolchain");
        fs::create_dir_all(sysroot.join("bin"))?;
        fs::create_dir_all(sysroot.join("lib"))?;
        let compiler = sysroot.join("bin/rustc");
        let driver = sysroot.join("lib/librustc_driver.so");
        fs::write(&compiler, b"compiler")?;
        fs::write(&driver, b"driver")?;
        fs::write(sysroot.join(".ohm-version"), b"ohm-1.98.1-1\n")?;
        record_context(
            &cache.root,
            "abcdef",
            cache.identity(&compiler)?,
            cache.identity(&driver)?,
        )?;
        let mut record = cache.record("abcdef")?;
        assert_eq!(record.ohm_version.as_deref(), Some("ohm-1.98.1-1"));
        record.ohm_version = None;
        cache.set_record(&record)?;
        drop(ContextUse::new(
            cache.tracker()?,
            "abcdef",
            Some(Vec::new()),
        )?);
        cache.artifact("build/registries/abcdef")?;
        let verbose = "rustc 1.98.1-dev (abcdef 2026-09-08) (ohm-1.98.1-2)\nbinary: rustc\n";
        assert_eq!(
            collect(&cache.root, false, ohm_version(verbose))?.retired,
            1
        );
        assert!(compiler.exists());
        assert!(driver.exists());
        assert_eq!(ohm_version("rustc 1.98.1 (abcdef 2026-09-08)"), None);
        assert_eq!(ohm_version("rustc 1.98.1-dev (ohm-unknown)"), None);
        Ok(())
    }

    #[test]
    fn legacy_cleanup_preserves_local_targets_and_ambiguous_context_records() -> CargoResult<()> {
        for lock in [
            ".ohm-build-lock",
            "debug/.cargo-lock",
            "debug/.cargo-artifact-lock",
        ] {
            let cache = Cache::new()?;
            File::create(cache.root.join(lock))?;
            let private = cache.artifact("build/workspaces/0123456789abcdef/context")?;
            let incremental = cache.artifact("incremental/0123456789abcdef")?;
            let registry = cache.artifact("build/registries/0123456789abcdef")?;
            let contexts = cache.root.join(DIRECTORY).join("contexts");
            fs::create_dir(&contexts)?;
            fs::write(
                contexts.join("0123456789abcdef.json"),
                b"unrecognized record",
            )?;
            assert_eq!(collect(&cache.root, false, None)?.retired, 0);
            assert!(private.exists());
            assert!(incremental.exists());
            assert!(registry.exists());
        }
        Ok(())
    }

    #[test]
    fn nested_roots_keep_their_own_context_records_and_consumer_locks() -> CargoResult<()> {
        let outer = Cache::new()?;
        let inner = Cache::new()?;
        let id = "0123456789abcdef";
        record_context(
            &inner.root,
            id,
            inner.identity(&inner.compiler)?,
            inner.identity(&inner.driver)?,
        )?;
        inner.age_context(id, SystemTime::UNIX_EPOCH)?;
        inner.artifact(&format!("build/registries/{id}"))?;
        let nested = outer.root.join("nested");
        fs::rename(&inner.root, &nested)?;
        let lease = crate::workspace::build_cache_gc_lease::ConsumerLease::acquire(&nested)?;
        assert_eq!(collect(&outer.root, true, None)?.counts.files, 0);
        assert_eq!(collect(&outer.root, false, None)?.counts.files, 0);
        assert!(collect(&nested, false, None)?.busy);
        drop(lease);
        assert_eq!(collect(&nested, false, None)?.retired, 1);
        assert!(
            !nested
                .join("debug/build/registries")
                .join(id)
                .join("artifact")
                .exists()
        );
        Ok(())
    }

    #[test]
    fn private_directory_symlinks_are_preserved() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let shared = cache.artifact("build/registries/abcdef")?;
        let outside = cache._temporary.path().join("outside");
        fs::create_dir(&outside)?;
        symlink(&outside, cache.profile.join("build/workspaces"))?;
        fs::remove_file(&cache.driver)?;
        assert_eq!(collect(&cache.root, false, None)?.retired, 1);
        assert!(!shared.exists());
        assert!(cache.tracker()?.context("abcdef")?.is_none());
        assert!(outside.exists());
        Ok(())
    }

    #[test]
    fn substituted_metadata_and_payload_ancestors_are_not_followed() -> CargoResult<()> {
        let cache = Cache::new()?;
        let outside = cache._temporary.path().join("outside");
        fs::create_dir(&outside)?;
        fs::create_dir(cache.profile.join("build"))?;
        symlink(&outside, cache.profile.join("build/registries"))?;
        fs::create_dir(outside.join("abcdef"))?;
        let mut summary = Summary::default();
        let source = cache.profile.join("build/registries/abcdef");
        assert!(!retire(
            &Namespace::Context("abcdef".to_owned()),
            &cache.root,
            &source,
            &cache.profile.join(TRASH),
            false,
            &mut summary,
        )?);
        assert_eq!(
            summary.skipped,
            [format!(
                "{} (parent is not a plain directory)",
                source.display()
            )]
        );
        assert!(outside.join("abcdef").exists());
        fs::rename(cache.root.join(DIRECTORY), cache.root.join("old-metadata"))?;
        symlink(&outside, cache.root.join(DIRECTORY))?;
        assert!(metadata_dir(&cache.root, true).is_err());
        Ok(())
    }
}
