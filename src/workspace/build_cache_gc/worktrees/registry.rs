//! Identifies private targets which an Ohm build or worktree creation has actually used.

use std::fs::{self, File, Metadata};
use std::io::{self, Read as _};
use std::os::unix::fs::MetadataExt as _;
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use anyhow::ensure;
use serde::{Deserialize, Serialize};

use super::super::Anchor;
use crate::compiler::Layout;
use crate::util::{CargoResult, GlobalContext, short_hash};
use crate::workspace::Workspace;
use crate::workspace::build_cache_gc_roots::open_regular;
use crate::workspace::workspace::shared_cache_path;

const REGISTRY: &str = ".ohm-worktree-targets-v1";

#[derive(Debug, Eq, PartialEq, Hash, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Identity {
    device: u64,
    inode: u64,
    created: Option<SystemTime>,
}

impl Identity {
    fn new(metadata: &Metadata) -> Self {
        Self {
            device: metadata.dev(),
            inode: metadata.ino(),
            created: metadata.created().ok(),
        }
    }
}

#[derive(Debug, Eq, PartialEq, Hash, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Binding {
    workspace: Identity,
    lock: Identity,
    // Locking and unlocking never change ctime. A replaced lock can reuse its inode.
    lock_changed: (i64, i64),
}

impl Binding {
    fn from_lock(worktree: &Path, lock: &Metadata) -> io::Result<Option<Self>> {
        let workspace = fs::metadata(worktree)?;
        Ok(
            (workspace.is_dir() && lock.is_file() && lock.nlink() == 1).then(|| Self {
                workspace: Identity::new(&workspace),
                lock: Identity::new(lock),
                lock_changed: (lock.ctime(), lock.ctime_nsec()),
            }),
        )
    }
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ManagedTarget {
    #[serde(with = "shared_cache_path")]
    pub(super) worktree: PathBuf,
    #[serde(with = "shared_cache_path")]
    pub(crate) target: PathBuf,
    binding: Binding,
    workspace_anchor: Option<Anchor>,
    target_anchor: Option<Anchor>,
    #[serde(skip)]
    pub(super) namespaces: Vec<String>,
}

impl ManagedTarget {
    fn new(worktree: PathBuf, target: PathBuf, binding: Binding) -> Self {
        // Preserve the enrollment if mount identity cannot be recorded. These
        // anchors authorize pruning only the registry record when a path disappears.
        let anchor = |path: &Path| {
            Anchor::for_path(path)
                .ok()
                .filter(|anchor| anchor.path.to_str().is_some())
        };
        Self {
            workspace_anchor: anchor(&worktree.join("Cargo.toml")),
            target_anchor: anchor(&target.join(Layout::PRIVATE_BUILD_LOCK)),
            worktree,
            target,
            binding,
            namespaces: Vec::new(),
        }
    }

    fn file_name(namespace: &str, binding: &Binding) -> String {
        format!("{}.json", short_hash(&(namespace, binding)))
    }

    fn current_binding(&self) -> Option<Binding> {
        if self.worktree.starts_with(&self.target)
            || self.worktree.canonicalize().ok()? != self.worktree
            || self.target.canonicalize().ok()? != self.target
        {
            return None;
        }
        let named = fs::symlink_metadata(self.target.join(Layout::PRIVATE_BUILD_LOCK)).ok()?;
        Binding::from_lock(&self.worktree, &named).ok()?
    }

    /// A path can be reused between discovery and locking, even by another checkout.
    pub(super) fn still_owned(&self, lock: &File) -> bool {
        self.current_binding().as_ref() == Some(&self.binding)
            && lock
                .metadata()
                .is_ok_and(|metadata| Identity::new(&metadata) == self.binding.lock)
    }

    /// Forget only paths proven gone or replaced on their original mounted filesystem.
    fn stale(&self) -> bool {
        let changed = |path: &Path,
                       anchor: &Option<Anchor>,
                       expected: &Identity,
                       ctime: Option<(i64, i64)>| {
            if !anchor.as_ref().is_some_and(|anchor| anchor.covers(path)) {
                return false;
            }
            match fs::symlink_metadata(path) {
                Err(error) => error.kind() == io::ErrorKind::NotFound,
                Ok(metadata) if !metadata.is_symlink() && metadata.dev() == expected.device => {
                    Identity::new(&metadata) != *expected
                        || ctime
                            .is_some_and(|stamp| stamp != (metadata.ctime(), metadata.ctime_nsec()))
                }
                Ok(_) => false,
            }
        };
        changed(
            &self.worktree,
            &self.workspace_anchor,
            &self.binding.workspace,
            None,
        ) || changed(
            &self.target.join(Layout::PRIVATE_BUILD_LOCK),
            &self.target_anchor,
            &self.binding.lock,
            Some(self.binding.lock_changed),
        )
    }
}

/// Called under a private target lease. A warm build only looks up its existing record.
pub(crate) fn register_build(ws: &Workspace<'_>, namespace: &str, lock: &File) -> CargoResult<()> {
    register_target(
        &ws.gctx().home().as_path_unlocked().join(REGISTRY),
        ws.root(),
        ws.target_dir().as_path_unlocked(),
        namespace,
        lock,
    )
}

fn register_target(
    directory: &Path,
    worktree: &Path,
    target: &Path,
    namespace: &str,
    lock: &File,
) -> CargoResult<()> {
    let Some(binding) = Binding::from_lock(worktree, &lock.metadata()?)? else {
        return Ok(());
    };
    let namespace = namespace.split('/').next().unwrap();
    let path = directory.join(ManagedTarget::file_name(namespace, &binding));
    match fs::symlink_metadata(&path) {
        Ok(metadata) => {
            ensure!(
                metadata.is_file(),
                "invalid private target record at {}",
                path.display()
            );
            return Ok(());
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(error) => return Err(error.into()),
    }
    // Layout already resolved both paths to compute the namespace. Only new
    // registrations need the canonical paths themselves for future discovery.
    let worktree = worktree.canonicalize()?;
    let target = target.canonicalize()?;
    if worktree.starts_with(&target) {
        return Ok(());
    }
    let record = ManagedTarget::new(worktree, target, binding);
    // A replaced target can have a valid lock of its own while this build still
    // holds the old one. Enroll only the lock we actually acquired.
    if record.current_binding().as_ref() != Some(&record.binding) {
        return Ok(());
    }
    fs::create_dir_all(directory)?;
    ensure!(
        fs::symlink_metadata(directory)?.is_dir(),
        "invalid private target registry"
    );
    let mut temporary = tempfile::NamedTempFile::new_in(directory)?;
    serde_json::to_writer(&mut temporary, &record)?;
    match temporary.persist_noclobber(path) {
        Ok(_) => Ok(()),
        Err(error) if error.error.kind() == io::ErrorKind::AlreadyExists => Ok(()),
        Err(error) => Err(error.error.into()),
    }
}

/// Lists only observed targets that still belong to the same workspace and target generation.
pub(crate) fn worktrees(
    gctx: &GlobalContext,
    dry_run: bool,
    tick: &mut dyn FnMut(),
) -> CargoResult<Vec<ManagedTarget>> {
    let directory = gctx.home().as_path_unlocked().join(REGISTRY);
    registered_targets(&directory, dry_run, tick)
}

fn registered_targets(
    directory: &Path,
    dry_run: bool,
    tick: &mut dyn FnMut(),
) -> CargoResult<Vec<ManagedTarget>> {
    match fs::symlink_metadata(directory) {
        Ok(metadata) => ensure!(metadata.is_dir(), "invalid private target registry"),
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(error.into()),
    }
    let mut targets = Vec::new();
    for entry in fs::read_dir(directory)? {
        tick();
        let entry = entry?;
        if !entry.file_type()?.is_file() || entry.path().extension().is_none_or(|ext| ext != "json")
        {
            continue;
        }
        let Ok(file) = open_regular(&entry.path()) else {
            continue;
        };
        let Ok(mut record) = serde_json::from_reader::<_, ManagedTarget>((&file).take(64 * 1024))
        else {
            continue;
        };
        if !record.target.is_absolute() || !record.worktree.is_absolute() {
            continue;
        }
        let namespaces =
            Layout::shared_workspace_cleanup_namespaces_for_paths(&record.worktree, &record.target);
        if entry.file_name() != ManagedTarget::file_name(&namespaces[0], &record.binding).as_str() {
            continue;
        }
        if record.current_binding().as_ref() == Some(&record.binding) {
            record.namespaces = namespaces.into();
            targets.push(record);
        } else if !dry_run
            && record.stale()
            && let Ok(opened) = file.metadata()
            && fs::symlink_metadata(entry.path()).is_ok_and(|named| {
                named.is_file() && (named.dev(), named.ino()) == (opened.dev(), opened.ino())
            })
        {
            // A concurrent collector may already have removed this immutable record.
            if let Err(error) = fs::remove_file(entry.path())
                && error.kind() != io::ErrorKind::NotFound
            {
                tracing::debug!(?error, path = ?entry.path(), "could not forget private target");
            }
        }
    }
    targets.sort_by(|a, b| (&a.target, &a.worktree).cmp(&(&b.target, &b.worktree)));
    Ok(targets)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;

    #[test]
    fn enrollment_uses_the_builds_open_lock_after_target_replacement() -> CargoResult<()> {
        let temp = tempfile::tempdir()?;
        let root = temp.path().canonicalize()?;
        let workspace = root.join("workspace");
        let target = root.join("target");
        let registry = root.join(REGISTRY);
        fs::create_dir(&workspace)?;
        fs::create_dir(&target)?;
        let name = target.join(Layout::PRIVATE_BUILD_LOCK);
        let previous = File::create_new(&name)?;
        crate::util::flock::lock_shared(&previous)?;
        fs::rename(&target, root.join("previous-target"))?;
        fs::create_dir(&target)?;
        let replacement = File::create_new(&name)?;
        let namespaces = Layout::shared_workspace_cleanup_namespaces_for_paths(&workspace, &target);
        register_target(&registry, &workspace, &target, &namespaces[0], &previous)?;
        assert!(!registry.exists());
        register_target(&registry, &workspace, &target, &namespaces[0], &replacement)?;
        let targets = registered_targets(&registry, true, &mut || {})?;
        assert_eq!(targets.len(), 1);
        assert!(targets[0].still_owned(&replacement));
        assert!(!targets[0].still_owned(&previous));
        Ok(())
    }

    #[test]
    fn replaced_workspace_or_lock_invalidates_external_target_ownership() -> CargoResult<()> {
        let temp = tempfile::tempdir()?;
        let root = temp.path().canonicalize()?;
        let workspace = root.join("workspace");
        let target = root.join("external-target");
        fs::create_dir(&workspace)?;
        fs::create_dir(&target)?;
        let lock_path = target.join(Layout::PRIVATE_BUILD_LOCK);
        let original = File::create_new(&lock_path)?;
        let observe = || -> CargoResult<ManagedTarget> {
            Ok(ManagedTarget::new(
                workspace.clone(),
                target.clone(),
                Binding::from_lock(&workspace, &original.metadata()?)?.unwrap(),
            ))
        };
        let record = observe()?;
        assert!(record.still_owned(&original));
        fs::write(workspace.join("Cargo.lock"), "")?;
        assert!(record.still_owned(&original));

        let old_workspace = root.join("old-workspace");
        fs::rename(&workspace, &old_workspace)?;
        symlink(&old_workspace, &workspace)?;
        assert!(!record.still_owned(&original));
        fs::remove_file(&workspace)?;
        fs::create_dir(&workspace)?;
        assert!(!record.still_owned(&original));

        let replacement = observe()?;
        assert_ne!(replacement.binding, record.binding);
        assert!(replacement.still_owned(&original));
        fs::rename(&lock_path, target.join("original-lock"))?;
        let new_lock = File::create_new(lock_path)?;
        assert!(!replacement.still_owned(&original));
        assert!(!replacement.still_owned(&new_lock));
        Ok(())
    }

    #[test]
    fn forgets_only_verified_stale_records_during_actual_gc() -> CargoResult<()> {
        let temp = tempfile::tempdir()?;
        let root = temp.path().canonicalize()?;
        let workspace = root.join("workspace");
        let target = root.join("external");
        let registry = root.join(REGISTRY);
        for directory in [&workspace, &target, &registry] {
            fs::create_dir(directory)?;
        }
        let lock = target.join(Layout::PRIVATE_BUILD_LOCK);
        let guard = File::create_new(&lock)?;
        let binding = Binding::from_lock(&workspace, &guard.metadata()?)?.unwrap();
        let mut record = ManagedTarget::new(workspace.clone(), target.clone(), binding);
        let namespaces = Layout::shared_workspace_cleanup_namespaces_for_paths(&workspace, &target);
        let path = registry.join(ManagedTarget::file_name(&namespaces[0], &record.binding));
        let contents = serde_json::to_vec(&record)?;
        fs::write(&path, &contents)?;
        assert_eq!(registered_targets(&registry, true, &mut || {})?.len(), 1);
        fs::remove_dir(&workspace)?;
        assert!(registered_targets(&registry, true, &mut || {})?.is_empty());
        assert!(path.exists());
        // An unavailable mount cannot establish that the workspace was removed.
        record.workspace_anchor.as_mut().unwrap().device ^= 1;
        fs::write(&path, serde_json::to_vec(&record)?)?;
        assert!(registered_targets(&registry, false, &mut || {})?.is_empty());
        assert!(path.exists());
        fs::write(&path, contents)?;
        assert!(registered_targets(&registry, false, &mut || {})?.is_empty());
        assert!(!path.exists());
        assert!(lock.exists());
        Ok(())
    }
}
