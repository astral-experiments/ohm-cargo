//! Conservative reclamation of retired shared-build namespaces.
//!
//! Builds enroll immutable provenance and refresh one timestamp per context.
//! Explicit GC reclaims removed owners, obsolete compilers, and idle contexts.

use std::fs::{self, File, Metadata, OpenOptions, TryLockError};
use std::io;
use std::path::{Component, Path, PathBuf};
use std::time::{Duration, Instant, SystemTime};

use anyhow::{Context as _, ensure};
use serde::{Deserialize, Serialize};

use crate::CargoResult;
use crate::compiler::Layout;
use crate::util;
use crate::util::data_structures::HashSet;
use crate::util::flock::try_lock_exclusive;
use crate::workspace::Workspace;

pub(crate) const DIRECTORY: &str = ".ohm-gc-v1";
pub(crate) const CONSUMERS_LOCK: &str = "consumers.lock";
const TRASH: &str = ".ohm-gc-trash-v1";
const DELETE_BUDGET: usize = 256;
const RENAME_BUDGET: usize = 8;
const CONTEXT_MAX_IDLE: Duration = Duration::from_secs(60 * 60);
const LAST_USED: &str = "last-used";

/// Refreshes a context at build start and completion, including failures and cache hits.
///
/// The caller must hold a consumer lease until this guard has been dropped.
/// Only this empty file's mtime changes; ownership records and artifacts are untouched.
pub(crate) struct ContextUse(File);

impl ContextUse {
    /// Opens one usage marker while the caller holds the root's consumer lease.
    pub(crate) fn new(root: &Path, context: &str) -> CargoResult<Self> {
        ensure!(component(context), "invalid build context");
        let directory = metadata_dir(root, false)?.join(LAST_USED);
        create_plain(&directory)?;
        let mut options = OpenOptions::new();
        options.read(true).write(true).create(true).truncate(false);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt as _;
            options.custom_flags(libc::O_NOFOLLOW);
        }
        let file = options.open(directory.join(context))?;
        ensure!(file.metadata()?.is_file(), "invalid context usage record");
        file.set_modified(SystemTime::now())?;
        Ok(Self(file))
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
            if entry.file_type()?.is_dir()
                && plain_directory(&records)
                && read_record::<ContextRecord>(&records.join(format!("{context}.json")))
                    .is_some_and(|record| record.version == 1 && record.context == context)
            {
                usage.push(ContextUse::new(root, context)?);
            }
        }
    }
    Ok(usage)
}

impl Drop for ContextUse {
    fn drop(&mut self) {
        if let Err(error) = self.0.set_modified(SystemTime::now()) {
            tracing::debug!(?error, "could not refresh build-context usage");
        }
    }
}

/// Missing or ambiguous usage records never establish inactivity.
fn context_expired(directory: &Path, context: &str, now: SystemTime) -> bool {
    let usage = directory.join(LAST_USED);
    if !plain_directory(&usage) {
        return false;
    }
    fs::symlink_metadata(usage.join(context))
        .ok()
        .filter(|metadata| metadata.is_file())
        .and_then(|metadata| metadata.modified().ok())
        .and_then(|modified| now.duration_since(modified).ok())
        .is_some_and(|idle| idle >= CONTEXT_MAX_IDLE)
}

/// The same concrete compiler-file identity used to partition shared artifacts.
#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
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
struct WorkspaceRecord {
    version: u32,
    namespace: String,
    workspace_root: PathBuf,
    target_root: PathBuf,
    worktree_root: PathBuf,
    git_common_dir: PathBuf,
    git_worktree_id: String,
    anchor: Anchor,
}

impl WorkspaceRecord {
    fn valid(&self, namespace: &str) -> bool {
        self.version == 1
            && self.namespace == namespace
            && Path::new(&self.git_worktree_id)
                .file_name()
                .is_some_and(|name| name == self.git_worktree_id.as_str())
            && self.workspace_root.is_absolute()
            && self.target_root.is_absolute()
            && self.worktree_root.is_absolute()
            && self.git_common_dir.is_absolute()
            && self.workspace_root.starts_with(&self.worktree_root)
            && namespace
                == util::short_hash(&(
                    "ohm-shared-workspace-v3",
                    &self.workspace_root,
                    &self.target_root,
                ))
    }

    fn retired(&self) -> bool {
        self.anchor.covers(&self.worktree_root)
            && absent(&self.worktree_root)
            && plain_directory(&self.git_common_dir)
            && git2::Repository::open(&self.git_common_dir).is_ok()
            && plain_or_absent(&self.git_common_dir.join("worktrees"))
            && absent(
                &self
                    .git_common_dir
                    .join("worktrees")
                    .join(&self.git_worktree_id),
            )
    }
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ContextRecord {
    version: u32,
    context: String,
    compiler: FileIdentity,
    driver: FileIdentity,
    compiler_anchor: Anchor,
    driver_anchor: Anchor,
}

impl ContextRecord {
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

/// Enrolls a linked worktree once; ordinary checkouts need no orphan tracking.
pub(crate) fn record_workspace(ws: &Workspace<'_>) -> CargoResult<()> {
    let root = ws.canonical_build_path(ws.configured_build_dir().as_path_unlocked());
    let namespace = Layout::shared_workspace_namespace(ws);
    let directory = metadata_dir(&root, true)?.join("workspaces");
    create_plain(&directory)?;
    let destination = directory.join(format!("{namespace}.json"));
    if fs::symlink_metadata(&destination).is_ok() {
        return Ok(());
    }
    let repo = git2::Repository::discover(ws.root())
        .ok()
        .filter(|repo| repo.is_worktree());
    let Some(repo) = repo else {
        // Negative enrollment is immutable too: ordinary checkouts and non-Git
        // projects do not need Git discovery again on each warm build.
        return write_new(
            &destination,
            &serde_json::json!({
                "version": 1,
                "namespace": namespace,
                "workspace_root": ws.canonical_build_path(ws.root()),
                "target_root": ws.canonical_build_path(ws.target_dir().as_path_unlocked()),
                "untracked": true,
            }),
        );
    };
    let git_dir = repo.path().canonicalize()?;
    let common = fs::read_to_string(git_dir.join("commondir"))?;
    let git_common_dir = git_dir.join(common.trim()).canonicalize()?;
    let git_worktree_id = git_dir
        .file_name()
        .and_then(|name| name.to_str())
        .context("Git worktree ID is not UTF-8")?
        .to_owned();
    ensure!(
        git_dir == git_common_dir.join("worktrees").join(&git_worktree_id),
        "unrecognized Git worktree registration"
    );
    let worktree_root = repo.workdir().context("bare worktree")?.canonicalize()?;
    let record = WorkspaceRecord {
        version: 1,
        namespace,
        workspace_root: ws.canonical_build_path(ws.root()),
        target_root: ws.canonical_build_path(ws.target_dir().as_path_unlocked()),
        anchor: Anchor::for_path(&worktree_root)?,
        worktree_root,
        git_common_dir,
        git_worktree_id,
    };
    write_new(&destination, &record)
}

/// Records provenance supplied by the context hasher without touching fresh records.
pub(crate) fn record_context(
    root: &Path,
    context: &str,
    compiler: FileIdentity,
    driver: FileIdentity,
) -> CargoResult<()> {
    ensure!(component(context), "invalid build context");
    let directory = metadata_dir(root, true)?.join("contexts");
    create_plain(&directory)?;
    let destination = directory.join(format!("{context}.json"));
    if fs::symlink_metadata(&destination).is_ok() {
        return Ok(());
    }
    let record = ContextRecord {
        version: 1,
        context: context.to_owned(),
        compiler_anchor: Anchor::for_path(&compiler.path)?,
        driver_anchor: Anchor::for_path(&driver.path)?,
        compiler,
        driver,
    };
    write_new(&destination, &record)
}

#[derive(Default, Debug)]
pub(crate) struct Summary {
    pub retired: usize,
    pub retained: usize,
    pub deleted_entries: usize,
    pub counts: FileCounts,
    pub pending: bool,
    pub busy: bool,
    pub details: Vec<String>,
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
        if metadata.is_dir() {
            self.directories += 1;
        } else {
            self.files += 1;
            // Match cargo clean: logical lengths, including symlinks, rather than disk blocks.
            self.bytes = self.bytes.saturating_add(metadata.len());
        }
    }

    pub(crate) fn include(&mut self, other: &Self) {
        self.files += other.files;
        self.directories += other.directories;
        self.bytes = self.bytes.saturating_add(other.bytes);
    }
}

/// Retires removed owners, obsolete compilers, and contexts idle for at least an hour.
pub(crate) fn collect(root: &Path, dry_run: bool) -> CargoResult<Summary> {
    collect_at(root, dry_run, SystemTime::now())
}

fn collect_at(root: &Path, dry_run: bool, now: SystemTime) -> CargoResult<Summary> {
    collect_with_lock_budget(root, dry_run, now, Duration::from_millis(10))
}

/// Applies a soft deadline between bounded retirement steps, always allowing progress.
fn collect_with_lock_budget(
    root: &Path,
    dry_run: bool,
    now: SystemTime,
    lock_budget: Duration,
) -> CargoResult<Summary> {
    let mut summary = Summary::default();
    if !cfg!(any(target_os = "linux", target_os = "macos")) || !root.join(DIRECTORY).exists() {
        return Ok(summary);
    }
    ensure!(
        regular(&root.join(Layout::SHARED_REGISTRY_CACHE_MARKER)),
        "not an owned shared registry cache"
    );
    ensure!(
        !crate::compiler::layout::shared_registry_directory_is_nfs(root)?,
        "build-cache reclamation does not support NFS"
    );
    let directory = metadata_dir(root, false)?;
    let _collector = if dry_run {
        None
    } else {
        let Some(collector) = try_lock(&directory.join("collector.lock"), true)? else {
            summary.busy = true;
            return Ok(summary);
        };
        Some(collector)
    };
    let Some(probe) = try_lock(&directory.join(CONSUMERS_LOCK), false)? else {
        summary.busy = true;
        return Ok(summary);
    };
    drop(probe);
    let profiles = profiles(root)?;
    let mut ready = Vec::new();
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
    // Potentially slow Git and filesystem discovery never holds consumer locks.
    for kind in ["workspaces", "contexts"] {
        let records = directory.join(kind);
        if !plain_directory(&records) {
            continue;
        }
        for entry in fs::read_dir(records)? {
            let entry = entry?;
            if !entry.file_type()?.is_file() {
                continue;
            }
            let path = entry.path();
            let Some(id) = path.file_stem().and_then(|name| name.to_str()) else {
                continue;
            };
            if !component(id) || path.extension().is_none_or(|extension| extension != "json") {
                continue;
            }
            if retirement_detail(&path, kind, id, now).is_none() {
                summary.retained += 1;
                continue;
            }
            let paths = owned_paths(root, &profiles, kind, id)?;
            ready.push((path.clone(), kind, id.to_owned(), paths));
        }
    }
    if dry_run {
        let Some(probe) = try_lock(&directory.join(CONSUMERS_LOCK), false)? else {
            summary.busy = true;
            return Ok(summary);
        };
        for profile in &profiles {
            ensure!(
                !crate::compiler::layout::shared_registry_directory_is_nfs(profile)?,
                "build-cache reclamation does not support NFS profiles"
            );
            let Some(_guard) = try_lock(&profile.join(".cargo-build-lock"), false)? else {
                summary.busy = true;
                return Ok(summary);
            };
        }
        drop(probe);

        // Preview every candidate, without deletion budgets or locks that block builds.
        // A later build may change this estimate; real collection rechecks ownership.
        let mut sources = Vec::new();
        for (record_path, kind, id, paths) in ready {
            let Some(detail) = retirement_detail(&record_path, kind, &id, now) else {
                continue;
            };
            let before = sources.len();
            for (source, trash) in paths {
                if retire(root, &source, &trash, true)? {
                    sources.push(source);
                }
            }
            if sources.len() != before {
                summary.retired += 1;
                summary.details.push(detail);
            }
        }
        // A retired worktree and compiler context can own overlapping private paths.
        sources.sort_by_key(|path| path.components().count());
        let mut counted = HashSet::default();
        let mut remaining = usize::MAX;
        for source in sources {
            if source.ancestors().any(|parent| counted.contains(parent)) {
                continue;
            }
            counted.insert(source.clone());
            let device = filesystem_device(&fs::symlink_metadata(&source)?);
            remove_bounded(&source, device, &mut remaining, &mut summary, true)?;
        }
        for trash in trash_roots {
            drain_trash(&trash, &mut remaining, &mut summary, true)?;
        }
        return Ok(summary);
    }
    if !ready.is_empty() {
        let deadline = Instant::now() + lock_budget;
        let Some(consumers) = try_lock(&directory.join(CONSUMERS_LOCK), false)? else {
            summary.busy = true;
            summary.pending = true;
            return Ok(summary);
        };
        // New consumers cannot create profiles now. If discovery raced a build,
        // retry with its complete layout instead of forgetting any owned paths.
        if profiles != self::profiles(root)? {
            summary.pending = true;
            return Ok(summary);
        }
        let mut guards = Vec::new();
        for profile in &profiles {
            ensure!(
                !crate::compiler::layout::shared_registry_directory_is_nfs(profile)?,
                "build-cache reclamation does not support NFS profiles"
            );
            let Some(guard) = try_lock(&profile.join(".cargo-build-lock"), false)? else {
                summary.busy = true;
                summary.pending = true;
                return Ok(summary);
            };
            guards.push(guard);
        }
        let mut remaining = RENAME_BUDGET;
        let mut records_remaining = RENAME_BUDGET;
        for (record_path, kind, id, paths) in ready {
            if remaining == 0
                || records_remaining == 0
                || (records_remaining < RENAME_BUDGET && Instant::now() >= deadline)
            {
                summary.pending = true;
                break;
            }
            records_remaining -= 1;
            // Only this bounded batch is revalidated while readers are excluded.
            let Some(detail) = retirement_detail(&record_path, kind, &id, now) else {
                continue;
            };
            let mut retired = false;
            for (source, trash) in &paths {
                if remaining == 0 || (remaining < RENAME_BUDGET && Instant::now() >= deadline) {
                    summary.pending = true;
                    break;
                }
                if retire(root, source, trash, false)? {
                    remaining -= 1;
                    retired = true;
                }
            }
            if retired && summary.details.len() < 32 {
                summary.details.push(detail);
            }
            // Keep ambiguous entries (symlinks, mount points, interrupted batches).
            // A future scan must still prove ownership before trying them again.
            // Finish this record's ownership proof even if the soft deadline elapsed.
            // Otherwise a slow filesystem can rename its last payload but never remove
            // the provenance, or make no progress at all after acquiring profile locks.
            let completed = paths.iter().all(|(source, _)| safely_absent(root, source))
                && owned_paths(root, &profiles, kind, &id)?
                    .iter()
                    .all(|(source, _)| safely_absent(root, source));
            if completed {
                if kind == "contexts" && plain_directory(&directory.join(LAST_USED)) {
                    match fs::remove_file(directory.join(LAST_USED).join(&id)) {
                        Ok(()) => {}
                        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
                        Err(error) => return Err(error.into()),
                    }
                }
                fs::remove_file(record_path)?;
            } else if remaining == 0 {
                summary.pending = true;
            }
            summary.retired += usize::from(completed);
        }
        drop(guards);
        drop(consumers);
    }
    // One small unlink chunk per pass, and no I/O when a consumer has arrived.
    // Explicit collection repeats productive passes within its wall-time budget.
    if let Some(probe) = try_lock(&directory.join(CONSUMERS_LOCK), false)? {
        drop(probe);
        let mut remaining = DELETE_BUDGET;
        for trash in trash_roots {
            drain_trash(&trash, &mut remaining, &mut summary, false)?;
        }
    } else {
        summary.busy = true;
    }
    Ok(summary)
}

/// Rechecks provenance and last use under the exclusive consumer lease before renaming.
fn retirement_detail(path: &Path, kind: &str, id: &str, now: SystemTime) -> Option<String> {
    if kind == "workspaces" {
        let record = read_record::<WorkspaceRecord>(path)?;
        (record.valid(id) && record.retired()).then(|| {
            format!(
                "worktree {} (directory and Git registration removed)",
                record.worktree_root.display()
            )
        })
    } else {
        let record = read_record::<ContextRecord>(path)?;
        if record.version != 1 || record.context != id {
            return None;
        }
        if record.retired() {
            Some(format!(
                "context {id} (compiler or driver changed or removed)"
            ))
        } else if context_expired(path.parent()?.parent()?, id, now) {
            Some(format!("context {id} (unused for at least 1 hour)"))
        } else {
            None
        }
    }
}

fn owned_paths(
    root: &Path,
    profiles: &[PathBuf],
    kind: &str,
    id: &str,
) -> CargoResult<Vec<(PathBuf, PathBuf)>> {
    let mut paths = Vec::new();
    for profile in profiles {
        let sources = if kind == "workspaces" {
            vec![
                profile.join("build/workspaces").join(id),
                profile.join("incremental").join(id),
            ]
        } else {
            context_paths(profile, id)?
        };
        paths.extend(
            sources
                .into_iter()
                .map(|source| (source, profile.join(TRASH))),
        );
    }
    if kind == "workspaces" {
        for base in std::iter::once(root.to_path_buf()).chain(
            profiles
                .iter()
                .filter_map(|p| p.parent().map(Path::to_path_buf)),
        ) {
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
    Ok(paths)
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

fn context_paths(profile: &Path, context: &str) -> CargoResult<Vec<PathBuf>> {
    let mut paths = vec![profile.join("build/registries").join(context)];
    let owners = profile.join("build/workspaces");
    if plain_ancestors(profile, &owners)? && plain_directory(&owners) {
        for entry in fs::read_dir(owners)? {
            let entry = entry?;
            paths.push(entry.path().join(context));
            if entry.file_type()?.is_dir() {
                paths.push(
                    entry
                        .path()
                        .join(crate::compiler::OHM_WORKTREE_CLIPPY_DIRECTORY)
                        .join(context),
                );
            }
        }
    } else {
        // Preserve provenance if an uninspectable private owner could still
        // contain this context. Missing parents are proved absent separately.
        paths.push(owners.join(context));
    }
    Ok(paths)
}

fn retire(root: &Path, source: &Path, trash: &Path, dry_run: bool) -> CargoResult<bool> {
    if !plain_ancestors(root, source)? || absent(source) {
        return Ok(false);
    }
    let metadata = fs::symlink_metadata(source)?;
    if !metadata.is_dir() && !metadata.is_file() {
        return Ok(false);
    }
    if filesystem_device(&metadata)
        != filesystem_device(&fs::symlink_metadata(trash.parent().unwrap())?)
    {
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
            return Ok(false);
        }
        return Err(error.into());
    }
    let _ = stage.keep();
    Ok(true)
}

fn drain_trash(
    trash: &Path,
    remaining: &mut usize,
    summary: &mut Summary,
    dry_run: bool,
) -> CargoResult<()> {
    if !plain_directory(trash) {
        return Ok(());
    }
    for entry in fs::read_dir(trash)? {
        let entry = entry?;
        if !entry.file_type()?.is_dir() {
            continue;
        }
        let path = entry.path();
        if read_regular(&path.join("owner")).as_deref() != Some(b"ohm-build-gc-v1\n") {
            continue;
        }
        if fs::read_dir(&path)?.any(|child| {
            !child.is_ok_and(|child| child.file_name() == "owner" || child.file_name() == "payload")
        }) {
            continue;
        }
        let payload = path.join("payload");
        remove_bounded(
            &payload,
            filesystem_device(&fs::symlink_metadata(trash)?),
            remaining,
            summary,
            dry_run,
        )?;
        if dry_run {
            continue;
        }
        if absent(&payload) && *remaining >= 2 {
            fs::remove_file(path.join("owner"))?;
            fs::remove_dir(path)?;
            *remaining -= 2;
            summary.deleted_entries += 2;
        } else {
            summary.pending = true;
        }
        if *remaining < 2 {
            summary.pending = true;
            break;
        }
    }
    Ok(())
}

fn remove_bounded(
    path: &Path,
    device: u64,
    remaining: &mut usize,
    summary: &mut Summary,
    dry_run: bool,
) -> CargoResult<()> {
    if *remaining == 0 || absent(path) {
        return Ok(());
    }
    let metadata = fs::symlink_metadata(path)?;
    if filesystem_device(&metadata) != device {
        return Ok(());
    }
    if metadata.is_dir() {
        for child in fs::read_dir(path)? {
            if *remaining == 0 {
                return Ok(());
            }
            remove_bounded(&child?.path(), device, remaining, summary, dry_run)?;
        }
        if *remaining == 0 {
            return Ok(());
        }
        if !dry_run && let Err(error) = fs::remove_dir(path) {
            if error.kind() == io::ErrorKind::DirectoryNotEmpty {
                return Ok(());
            }
            return Err(error.into());
        }
    } else if !dry_run {
        fs::remove_file(path)?;
    }
    *remaining -= 1;
    summary.deleted_entries += 1;
    summary.counts.record(&metadata);
    Ok(())
}

fn profiles(root: &Path) -> CargoResult<Vec<PathBuf>> {
    let mut result = Vec::new();
    for entry in fs::read_dir(root)? {
        let entry = entry?;
        if !entry.file_type()?.is_dir() || entry.file_name().to_string_lossy().starts_with('.') {
            continue;
        }
        let path = entry.path();
        if regular(&path.join(".cargo-build-lock")) {
            result.push(path);
            continue;
        }
        for child in fs::read_dir(path)? {
            let child = child?;
            if child.file_type()?.is_dir() && regular(&child.path().join(".cargo-build-lock")) {
                result.push(child.path());
            }
        }
    }
    result.sort_by(|a, b| (a.parent() != Some(root), a).cmp(&(b.parent() != Some(root), b)));
    Ok(result)
}

/// GC guards end at their lexical scope, even if another thread forked while held.
/// Consumer leases deliberately have different semantics and remain held by children.
struct CollectorLock(File);

impl Drop for CollectorLock {
    fn drop(&mut self) {
        if let Err(error) = crate::util::flock::unlock(&self.0) {
            tracing::debug!(?error, "could not release build-cache collector lock");
        }
    }
}

fn try_lock(path: &Path, create: bool) -> CargoResult<Option<CollectorLock>> {
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
    ensure!(
        file.metadata()?.is_file(),
        "cache lock is not a regular file"
    );
    match try_lock_exclusive(&file) {
        Ok(()) => {}
        Err(TryLockError::WouldBlock) => return Ok(None),
        Err(TryLockError::Error(error)) => return Err(error.into()),
    }
    let lock = CollectorLock(file);
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
fn plain_or_absent(path: &Path) -> bool {
    plain_directory(path) || absent(path)
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
fn write_new(path: &Path, value: &impl Serialize) -> CargoResult<()> {
    use std::io::Write as _;
    let mut temporary = tempfile::NamedTempFile::new_in(path.parent().unwrap())?;
    temporary.write_all(&serde_json::to_vec(value)?)?;
    match temporary.persist_noclobber(path) {
        Ok(_) => Ok(()),
        Err(e) if e.error.kind() == io::ErrorKind::AlreadyExists => Ok(()),
        Err(e) => Err(e.into()),
    }
}

#[cfg(all(test, any(target_os = "linux", target_os = "macos")))]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;

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
            record_context(
                &self.root,
                "abcdef",
                self.identity(&self.compiler)?,
                self.identity(&self.driver)?,
            )
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
    }

    #[test]
    fn missing_usage_preserves_context_and_provenance_is_immutable() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let path = cache.artifact("build/registries/abcdef")?;
        let record = cache.root.join(DIRECTORY).join("contexts/abcdef.json");
        let before = fs::metadata(&record)?.modified()?;
        cache.enroll()?;
        assert_eq!(before, fs::metadata(&record)?.modified()?);
        let summary = collect(&cache.root, false)?;
        assert_eq!(summary.retired, 0);
        assert!(path.exists());
        assert!(!cache.root.join(DIRECTORY).join("candidates.json").exists());
        Ok(())
    }

    #[test]
    fn idle_context_expires_with_installed_compiler_at_one_hour() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let shared = cache.artifact("build/registries/abcdef")?;
        let private = cache.artifact("build/workspaces/owner/abcdef")?;
        let incremental = cache.artifact("incremental/owner")?;
        drop(ContextUse::new(&cache.root, "abcdef")?);
        let usage = cache.root.join(DIRECTORY).join(LAST_USED).join("abcdef");
        let last_used = fs::metadata(&usage)?.modified()?;
        let expires = last_used + CONTEXT_MAX_IDLE;
        assert_eq!(
            collect_at(&cache.root, false, expires - Duration::from_nanos(1))?.retired,
            0
        );
        let dry_run = collect_at(&cache.root, true, expires)?;
        assert_eq!(dry_run.retired, 1);
        assert!(
            dry_run
                .details
                .iter()
                .any(|line| line.contains("unused for at least 1 hour"))
        );
        assert_eq!(dry_run.counts.files, 2);
        assert_eq!(dry_run.counts.bytes, 12);
        assert_eq!(fs::metadata(&usage)?.modified()?, last_used);
        assert!(shared.exists());
        let collected = collect_at(&cache.root, false, expires)?;
        assert_eq!(collected.retired, 1);
        assert_eq!(collected.counts, dry_run.counts);
        assert!(!shared.exists());
        assert!(!private.exists());
        assert!(!usage.exists());
        assert!(incremental.exists());
        assert!(cache.compiler.exists());
        assert!(cache.driver.exists());
        Ok(())
    }

    #[test]
    fn long_build_is_protected_and_refreshes_usage_on_completion() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        cache.artifact("build/registries/abcdef")?;
        let lease = crate::workspace::build_cache_gc_lease::ConsumerLease::acquire(&cache.root)?;
        let usage = ContextUse::new(&cache.root, "abcdef")?;
        usage
            .0
            .set_modified(SystemTime::now() - CONTEXT_MAX_IDLE * 2)?;
        assert!(collect(&cache.root, false)?.busy);
        let completed = SystemTime::now();
        drop(usage);
        drop(lease);
        let timestamp = cache.root.join(DIRECTORY).join(LAST_USED).join("abcdef");
        assert!(fs::metadata(&timestamp)?.modified()? >= completed);
        assert_eq!(collect(&cache.root, false)?.retired, 0);
        Ok(())
    }

    #[test]
    fn future_and_symlinked_usage_markers_cannot_expire_contexts() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        cache.artifact("build/registries/abcdef")?;
        drop(ContextUse::new(&cache.root, "abcdef")?);
        let usage = cache.root.join(DIRECTORY).join(LAST_USED).join("abcdef");
        File::options()
            .write(true)
            .open(&usage)?
            .set_modified(SystemTime::now() + CONTEXT_MAX_IDLE)?;
        assert_eq!(collect(&cache.root, false)?.retired, 0);
        fs::remove_file(&usage)?;
        symlink(&cache.compiler, &usage)?;
        let before = fs::metadata(&cache.compiler)?.modified()?;
        assert!(ContextUse::new(&cache.root, "abcdef").is_err());
        assert_eq!(
            collect_at(&cache.root, false, SystemTime::now() + CONTEXT_MAX_IDLE * 2)?.retired,
            0
        );
        assert_eq!(fs::metadata(&cache.compiler)?.modified()?, before);
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
        let dry = collect(&cache.root, true)?;
        assert_eq!(dry.retired, 1);
        assert!(shared.exists());
        assert!(
            dry.details
                .iter()
                .any(|line| line.contains("compiler or driver changed or removed"))
        );
        assert_eq!(collect(&cache.root, false)?.retired, 1);
        assert!(!shared.exists());
        assert!(!private.exists());
        assert!(other.exists());
        assert!(incremental.exists());
        Ok(())
    }

    #[test]
    fn driver_replacement_is_obsolete_but_alias_retarget_is_not() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let record =
            read_record::<ContextRecord>(&cache.root.join(DIRECTORY).join("contexts/abcdef.json"))
                .unwrap();
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
        let record_path = cache.root.join(DIRECTORY).join("contexts/abcdef.json");
        let mut record = read_record::<ContextRecord>(&record_path).unwrap();
        fs::remove_file(&cache.compiler)?;
        record.compiler_anchor.device ^= 1;
        assert!(!record.retired());
        fs::write(record_path, serde_json::to_vec(&record)?)?;
        let path = cache.artifact("build/registries/abcdef")?;
        assert_eq!(collect(&cache.root, false)?.retired, 0);
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
        assert!(collect(&cache.root, false)?.busy);
        assert!(artifact.exists());
        crate::util::flock::unlock(&consumers)?;
        drop(consumers);
        let profile = OpenOptions::new()
            .read(true)
            .write(true)
            .open(cache.profile.join(".cargo-build-lock"))?;
        crate::util::flock::lock_shared(&profile)?;
        assert!(collect(&cache.root, false)?.busy);
        assert!(artifact.exists());
        crate::util::flock::unlock(&profile)?;
        drop(profile);
        assert!(!collect(&cache.root, false)?.busy);
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
        let preview = collect(&cache.root, true)?;
        assert_eq!(preview.retired, RENAME_BUDGET + 2);
        assert_eq!(preview.counts.files, (RENAME_BUDGET + 2) as u64);
        assert_eq!(preview.counts.bytes, ((RENAME_BUDGET + 2) * 6) as u64);
        let first = collect(&cache.root, false)?;
        assert!(first.retired <= RENAME_BUDGET);
        assert!(first.pending);
        assert_eq!(
            fs::read_dir(cache.root.join(DIRECTORY).join("contexts"))?.count(),
            RENAME_BUDGET + 2 - first.retired
        );
        let mut completed = first.retired;
        for _ in 0..32 {
            let next = collect(&cache.root, false)?;
            assert!(next.retired <= RENAME_BUDGET);
            completed += next.retired;
            if !next.pending {
                break;
            }
        }
        assert_eq!(completed, RENAME_BUDGET + 2);
        assert_eq!(
            fs::read_dir(cache.root.join(DIRECTORY).join("contexts"))?.count(),
            0
        );
        assert!(!cache.root.join(DIRECTORY).join("candidates.json").exists());
        Ok(())
    }

    #[test]
    fn elapsed_soft_deadline_still_makes_progress() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        cache.artifact("build/registries/abcdef")?;
        cache.artifact("build/workspaces/owner/abcdef")?;
        fs::remove_file(&cache.driver)?;
        let first =
            collect_with_lock_budget(&cache.root, false, SystemTime::now(), Duration::ZERO)?;
        assert!(first.pending);
        assert_eq!(first.retired, 0);
        let second =
            collect_with_lock_budget(&cache.root, false, SystemTime::now(), Duration::ZERO)?;
        assert_eq!(second.retired, 1);
        assert!(
            !cache
                .root
                .join(DIRECTORY)
                .join("contexts/abcdef.json")
                .exists()
        );
        Ok(())
    }

    #[test]
    fn partial_context_batches_count_completion_once() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        for index in 0..RENAME_BUDGET + 2 {
            cache.artifact(&format!("build/workspaces/owner-{index}/abcdef"))?;
        }
        fs::remove_file(&cache.driver)?;
        let first = collect(&cache.root, false)?;
        assert_eq!(first.retired, 0);
        assert!(first.pending);
        let mut completed = 0;
        for _ in 0..10 {
            let next = collect(&cache.root, false)?;
            completed += next.retired;
            if !next.pending {
                break;
            }
        }
        assert_eq!(completed, 1);
        assert!(
            !cache
                .root
                .join(DIRECTORY)
                .join("contexts/abcdef.json")
                .exists()
        );
        Ok(())
    }

    #[test]
    fn trash_does_not_delete_another_filesystem() -> CargoResult<()> {
        let cache = Cache::new()?;
        let payload = cache.artifact("payload")?;
        let wrong_device = filesystem_device(&fs::symlink_metadata(&payload)?) ^ 1;
        let mut remaining = DELETE_BUDGET;
        let mut summary = Summary::default();
        remove_bounded(&payload, wrong_device, &mut remaining, &mut summary, false)?;
        assert!(payload.join("artifact").exists());
        assert_eq!(remaining, DELETE_BUDGET);
        assert_eq!(summary.deleted_entries, 0);
        remove_bounded(&payload, wrong_device, &mut remaining, &mut summary, true)?;
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
        let dry_run = collect(&cache.root, true)?;
        assert_eq!(dry_run.counts.files, (DELETE_BUDGET + 7) as u64);
        assert_eq!(
            dry_run.counts.bytes,
            (DELETE_BUDGET + 11) as u64 + fs::symlink_metadata(path.join("external"))?.len()
        );
        let first = collect(&cache.root, false)?;
        assert!(first.pending);
        assert_eq!(first.deleted_entries, DELETE_BUDGET);
        assert!(!path.exists());
        assert!(cache.compiler.exists());
        let pending = collect(&cache.root, true)?;
        assert_eq!(pending.retired, 0);
        let next = collect(&cache.root, false)?;
        assert!(!next.pending);
        assert_eq!(pending.counts, next.counts);
        let mut counts = first.counts;
        counts.include(&next.counts);
        assert_eq!(counts, dry_run.counts);
        assert!(cache.compiler.exists());
        Ok(())
    }

    #[test]
    fn preview_counts_overlapping_worktree_and_context_payloads_once() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let checkout = cache.root.parent().unwrap().join("removed-worktree");
        let target = checkout.join("target");
        let namespace = util::short_hash(&("ohm-shared-workspace-v3", &checkout, &target));
        let repo = git2::Repository::init(cache.root.parent().unwrap().join("repo"))?;
        let record = WorkspaceRecord {
            version: 1,
            namespace: namespace.clone(),
            workspace_root: checkout.clone(),
            target_root: target,
            worktree_root: checkout.clone(),
            git_common_dir: repo.path().to_path_buf(),
            git_worktree_id: "removed-worktree".to_owned(),
            anchor: Anchor::for_path(&checkout)?,
        };
        let records = metadata_dir(&cache.root, true)?.join("workspaces");
        fs::create_dir(&records)?;
        write_new(&records.join(format!("{namespace}.json")), &record)?;
        cache.artifact("build/registries/abcdef")?;
        cache.artifact(&format!("build/workspaces/{namespace}/abcdef"))?;
        cache.artifact(&format!("incremental/{namespace}"))?;
        fs::remove_file(&cache.driver)?;
        let preview = collect(&cache.root, true)?;
        assert_eq!(preview.retired, 2);
        assert_eq!(preview.counts.files, 3);
        assert_eq!(preview.counts.bytes, 18);
        let collected = collect(&cache.root, false)?;
        assert_eq!(collected.retired, 2);
        assert_eq!(collected.counts, preview.counts);
        Ok(())
    }

    #[test]
    fn ambiguous_private_owners_keep_context_provenance() -> CargoResult<()> {
        let cache = Cache::new()?;
        cache.enroll()?;
        let shared = cache.artifact("build/registries/abcdef")?;
        let outside = cache._temporary.path().join("outside");
        fs::create_dir(&outside)?;
        symlink(&outside, cache.profile.join("build/workspaces"))?;
        fs::remove_file(&cache.driver)?;
        assert_eq!(collect(&cache.root, false)?.retired, 0);
        assert!(!shared.exists());
        assert!(
            cache
                .root
                .join(DIRECTORY)
                .join("contexts/abcdef.json")
                .exists()
        );
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
        assert!(!retire(
            &cache.root,
            &cache.profile.join("build/registries/abcdef"),
            &cache.profile.join(TRASH),
            false
        )?);
        assert!(outside.join("abcdef").exists());
        fs::rename(cache.root.join(DIRECTORY), cache.root.join("old-metadata"))?;
        symlink(&outside, cache.root.join(DIRECTORY))?;
        assert!(metadata_dir(&cache.root, true).is_err());
        Ok(())
    }
}
