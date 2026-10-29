//! Conservative reclamation of retired shared-build namespaces.
//!
//! Builds enroll immutable provenance and refresh one timestamp per context.
//! Explicit GC reclaims legacy layouts, obsolete compilers, and idle contexts.

use std::fs::{self, File, Metadata, OpenOptions, TryLockError};
use std::io;
use std::path::{Component, Path, PathBuf};
use std::time::{Duration, Instant, SystemTime};

use anyhow::{Context as _, ensure};
use serde::{Deserialize, Serialize};

use crate::CargoResult;
use crate::compiler::Layout;
use crate::util::data_structures::HashSet;
use crate::util::flock::try_lock_exclusive;

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
        ohm_version: installed_ohm_version(&compiler, &driver),
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

/// Retires legacy layouts, obsolete compilers, and contexts idle for at least an hour.
pub(crate) fn collect(
    root: &Path,
    dry_run: bool,
    current_ohm: Option<&str>,
) -> CargoResult<Summary> {
    collect_at(root, dry_run, SystemTime::now(), current_ohm)
}

fn collect_at(
    root: &Path,
    dry_run: bool,
    now: SystemTime,
    current_ohm: Option<&str>,
) -> CargoResult<Summary> {
    collect_with_lock_budget(root, dry_run, now, Duration::from_millis(10), current_ohm)
}

/// Applies a soft deadline between bounded retirement steps, always allowing progress.
fn collect_with_lock_budget(
    root: &Path,
    dry_run: bool,
    now: SystemTime,
    lock_budget: Duration,
    current_ohm: Option<&str>,
) -> CargoResult<Summary> {
    let mut summary = Summary::default();
    if !cfg!(any(target_os = "linux", target_os = "macos")) {
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
    // Previewing a legacy cache must not enroll it or create locks. Real collection
    // installs the same consumer lock used by new builds before inspecting profiles.
    let directory = root.join(DIRECTORY);
    if !dry_run || !absent(&directory) {
        metadata_dir(root, !dry_run)?;
    }
    let _collector = if dry_run {
        None
    } else {
        let Some(collector) = try_lock(&directory.join("collector.lock"), true)? else {
            summary.busy = true;
            return Ok(summary);
        };
        Some(collector)
    };
    let consumers_path = directory.join(CONSUMERS_LOCK);
    if !dry_run || !absent(&consumers_path) {
        let Some(probe) = try_lock(&consumers_path, !dry_run)? else {
            summary.busy = true;
            return Ok(summary);
        };
        drop(probe);
    }
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
    // Namespace discovery never holds consumer or build locks.
    for namespace in namespaces(root, &profiles)? {
        if namespace
            .detail(root, &profiles, now, current_ohm)
            .is_none()
        {
            summary.retained += 1;
            continue;
        }
        let paths = namespace.paths(root, &profiles);
        ready.push((namespace, paths));
    }
    if dry_run {
        let probe = if absent(&consumers_path) {
            None
        } else {
            let Some(probe) = try_lock(&consumers_path, false)? else {
                summary.busy = true;
                return Ok(summary);
            };
            Some(probe)
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

        // Preview every candidate without holding locks while counting artifacts.
        let mut sources = Vec::new();
        for (namespace, paths) in ready {
            let Some(detail) = namespace.detail(root, &profiles, now, current_ohm) else {
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
        let Some(consumers) = try_lock(&consumers_path, false)? else {
            summary.busy = true;
            summary.pending = true;
            return Ok(summary);
        };
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
                return Ok(summary);
            };
            guards.push(guard);
        }
        let mut remaining = RENAME_BUDGET;
        let mut records_remaining = RENAME_BUDGET;
        for (namespace, paths) in ready {
            if remaining == 0
                || records_remaining == 0
                || (records_remaining < RENAME_BUDGET && Instant::now() >= deadline)
            {
                summary.pending = true;
                break;
            }
            records_remaining -= 1;
            // A build may have enrolled a legacy context since discovery. Recheck
            // while both new consumers and older Cargo builds are excluded.
            let Some(detail) = namespace.detail(root, &profiles, now, current_ohm) else {
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
            let completed = paths.iter().all(|(source, _)| safely_absent(root, source))
                && namespace
                    .paths(root, &profiles)
                    .iter()
                    .all(|(source, _)| safely_absent(root, source));
            if completed {
                namespace.finish(&directory)?;
            } else if remaining == 0 {
                summary.pending = true;
            }
            summary.retired += usize::from(completed);
        }
        drop(guards);
        drop(consumers);
    }
    // Unlink only retired payloads, outside the build locks and in small batches.
    if let Some(probe) = try_lock(&consumers_path, false)? {
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

#[derive(PartialEq, Eq, PartialOrd, Ord, Hash)]
enum Namespace {
    Context(String),
    LegacyWorkspace(String),
}

impl Namespace {
    /// Missing legacy records permit eviction; malformed or newer records do not.
    fn detail(
        &self,
        root: &Path,
        profiles: &[PathBuf],
        now: SystemTime,
        current_ohm: Option<&str>,
    ) -> Option<String> {
        let directory = root.join(DIRECTORY);
        match self {
            Self::Context(id) => {
                let path = directory.join("contexts").join(format!("{id}.json"));
                if legacy_context_name(id)
                    && safely_absent(root, &path)
                    && safely_absent(root, &directory.join(LAST_USED).join(id))
                {
                    return Some(format!("legacy context {id} (no usage records)"));
                }
                let record = read_record::<ContextRecord>(&path)?;
                if record.version != 1 || record.context != *id {
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
                } else if context_expired(&directory, id, now) {
                    Some(format!("context {id} (unused for at least 1 hour)"))
                } else {
                    None
                }
            }
            Self::LegacyWorkspace(id) => legacy_private_state(root, profiles)
                .then(|| format!("legacy workspace {id} (private state now lives in target)")),
        }
    }

    fn paths(&self, root: &Path, profiles: &[PathBuf]) -> Vec<(PathBuf, PathBuf)> {
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
            };
            paths.extend(
                sources
                    .into_iter()
                    .map(|source| (source, profile.join(TRASH))),
            );
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

    fn finish(&self, directory: &Path) -> CargoResult<()> {
        let paths = match self {
            Self::Context(id) => vec![
                directory.join(LAST_USED).join(id),
                directory.join("contexts").join(format!("{id}.json")),
            ],
            Self::LegacyWorkspace(id) => {
                vec![directory.join("workspaces").join(format!("{id}.json"))]
            }
        };
        for path in paths {
            if plain_ancestors(directory, &path)? && regular(&path) {
                fs::remove_file(path)?;
            }
        }
        Ok(())
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
fn namespaces(root: &Path, profiles: &[PathBuf]) -> CargoResult<Vec<Namespace>> {
    let mut namespaces = HashSet::default();
    let records = root.join(DIRECTORY).join("contexts");
    if plain_ancestors(root, &records)? && plain_directory(&records) {
        for entry in fs::read_dir(records)? {
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
    for profile in profiles {
        for id in directory_names(root, &profile.join("build/registries"))? {
            if legacy_context_name(&id) {
                namespaces.insert(Namespace::Context(id));
            }
        }
        if legacy_private_state(root, profiles) {
            for parent in [
                profile.join("build/workspaces"),
                profile.join("incremental"),
            ] {
                for id in directory_names(root, &parent)? {
                    if namespace_hash(&id) {
                        namespaces.insert(Namespace::LegacyWorkspace(id));
                    }
                }
            }
        }
    }
    if legacy_private_state(root, profiles) {
        for base in std::iter::once(root).chain(profiles.iter().filter_map(|p| p.parent())) {
            for id in directory_names(root, &base.join("tmp"))? {
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

fn directory_names(root: &Path, parent: &Path) -> CargoResult<Vec<String>> {
    let mut names = Vec::new();
    if plain_ancestors(root, parent)? && plain_directory(parent) {
        for entry in fs::read_dir(parent)? {
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
        // A nested shared root has its own provenance and consumer leases.
        if regular(&path.join(Layout::SHARED_REGISTRY_CACHE_MARKER)) {
            continue;
        }
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
        let summary = collect(&cache.root, false, None)?;
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
            collect_at(&cache.root, false, expires - Duration::from_nanos(1), None)?.retired,
            0
        );
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
        assert_eq!(fs::metadata(&usage)?.modified()?, last_used);
        assert!(shared.exists());
        let collected = collect_at(&cache.root, false, expires, None)?;
        assert_eq!(collected.retired, 1);
        assert_eq!(collected.counts, dry_run.counts);
        assert!(!shared.exists());
        assert!(
            private.exists(),
            "unrecognized private namespace is preserved"
        );
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
        assert!(collect(&cache.root, false, None)?.busy);
        let completed = SystemTime::now();
        drop(usage);
        drop(lease);
        let timestamp = cache.root.join(DIRECTORY).join(LAST_USED).join("abcdef");
        assert!(fs::metadata(&timestamp)?.modified()? >= completed);
        assert_eq!(collect(&cache.root, false, None)?.retired, 0);
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
        assert_eq!(collect(&cache.root, false, None)?.retired, 0);
        fs::remove_file(&usage)?;
        symlink(&cache.compiler, &usage)?;
        let before = fs::metadata(&cache.compiler)?.modified()?;
        assert!(ContextUse::new(&cache.root, "abcdef").is_err());
        assert_eq!(
            collect_at(
                &cache.root,
                false,
                SystemTime::now() + CONTEXT_MAX_IDLE * 2,
                None
            )?
            .retired,
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
        assert!(collect(&cache.root, false, None)?.busy);
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
            fs::read_dir(cache.root.join(DIRECTORY).join("contexts"))?.count(),
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
        let release = cache.root.join("release");
        fs::create_dir_all(release.join("build/registries/abcdef"))?;
        File::create(release.join(".cargo-build-lock"))?;
        fs::write(release.join("build/registries/abcdef/artifact"), b"cached")?;
        fs::remove_file(&cache.driver)?;
        let first =
            collect_with_lock_budget(&cache.root, false, SystemTime::now(), Duration::ZERO, None)?;
        assert!(first.pending);
        assert_eq!(first.retired, 0);
        let second =
            collect_with_lock_budget(&cache.root, false, SystemTime::now(), Duration::ZERO, None)?;
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
            let path = cache
                .root
                .join(DIRECTORY)
                .join("contexts")
                .join(format!("{id}.json"));
            let mut record = read_record::<ContextRecord>(&path).unwrap();
            record.ohm_version = version.map(str::to_owned);
            fs::write(path, serde_json::to_vec(&record)?)?;
            drop(ContextUse::new(&cache.root, id)?);
            cache.artifact(&format!("build/registries/{id}"))?;
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
        }
        for id in ["current", "newer", "unknown"] {
            assert!(cache.profile.join("build/registries").join(id).exists());
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
        let path = cache.root.join(DIRECTORY).join("contexts/abcdef.json");
        let mut record = read_record::<ContextRecord>(&path).unwrap();
        assert_eq!(record.ohm_version.as_deref(), Some("ohm-1.98.1-1"));
        record.ohm_version = None;
        fs::write(path, serde_json::to_vec(&record)?)?;
        drop(ContextUse::new(&cache.root, "abcdef")?);
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
        drop(ContextUse::new(&inner.root, id)?);
        inner.artifact(&format!("build/registries/{id}"))?;
        let nested = outer.root.join("nested");
        fs::rename(&inner.root, &nested)?;
        let lease = crate::workspace::build_cache_gc_lease::ConsumerLease::acquire(&nested)?;
        assert_eq!(collect(&outer.root, true, None)?.counts.files, 0);
        assert_eq!(collect(&outer.root, false, None)?.counts.files, 0);
        assert!(collect(&nested, false, None)?.busy);
        drop(lease);
        assert_eq!(collect(&nested, false, None)?.retired, 0);
        assert!(
            nested
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
        assert!(
            !cache
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
