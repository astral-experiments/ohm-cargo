//! Reclaims an idle private target while keeping Cargo's synchronization files in place.

use std::ffi::OsStr;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use super::collector::{same_collector, target_guard};
use super::{activity, mounts::Mounts, registry::ManagedTarget};
use crate::compiler::Layout;
use crate::util::CargoResult;
use crate::workspace::build_cache_gc::{
    CollectorLock, RENAME_BUDGET, Summary, absent, create_plain, drain_trash, filesystem_device,
    plain_ancestors, plain_directory, profiles_matching, regular, remove_bounded, retire_path,
    try_lock,
};

const TRASH: &str = ".ohm-target-gc-trash-v1";
const PROFILE_LOCKS: [&str; 3] = [".cargo-build-lock", ".cargo-lock", ".cargo-artifact-lock"];

/// Returns whether the target-wide pass superseded individual compiler contexts.
pub(super) fn collect(
    owner: &ManagedTarget,
    targets: &[ManagedTarget],
    shared_roots: &[PathBuf],
    dry_run: bool,
    summary: &mut Summary<'_>,
) -> CargoResult<bool> {
    let root = &owner.target;
    let trash = root.join(TRASH);
    if !absent(&trash) && !plain_directory(&trash) {
        summary.skip_path(&trash, "cleanup directory is not a plain directory");
        return Ok(false);
    }
    let mut idle = activity::idle(root, SystemTime::now());
    let staged = plain_directory(&trash)
        && fs::read_dir(&trash)?.any(|entry| {
            entry.is_ok_and(|entry| entry.file_type().is_ok_and(|kind| kind.is_dir()))
        });
    if !idle && !staged {
        return Ok(false);
    }

    // Unlike retirement of a marked compiler context, a full clean requires
    // positive ownership of the whole directory. A reused checkout or a shared
    // cache's subdirectory must never be treated as disposable workspace output.
    let default_target = targets
        .iter()
        .any(|target| target.target == *root && target.worktree.join("target") == *root);
    if idle
        && (!dedicated_target(root, default_target)
            || shared_roots
                .iter()
                .any(|shared| root != shared && root.starts_with(shared)))
    {
        summary.skip_path(root, "could not verify a dedicated Cargo target");
        idle = false;
    }
    let mounts = Mounts::read(root)?;
    if mounts.blocked(&trash, true, summary) {
        return Ok(false);
    }
    if idle && mounts.blocked(&root.join(activity::MARKER), false, summary) {
        idle = false;
    }
    let plan = if idle {
        Plan::discover(root, targets, shared_roots, &mounts, summary)?
    } else {
        Plan::default()
    };
    if plan.paths.is_empty() && !staged {
        return Ok(idle);
    }

    let Some(guard) = target_guard(owner, !staged, summary)? else {
        return Ok(idle);
    };
    let lock_path = trash.join("collector.lock");
    let collector = if !dry_run || !absent(&lock_path) {
        if !dry_run {
            create_plain(&trash)?;
        }
        let Some(lock) = try_lock(&lock_path, !dry_run)? else {
            summary.skip_path(root, "another garbage collector is using this target");
            summary.blocking_locks.insert(lock_path);
            return Ok(idle);
        };
        Some(lock)
    } else {
        None
    };
    drop(guard);

    let mut previews = Vec::new();
    let mut reported = false;
    for batch in plan.paths.chunks(RENAME_BUDGET) {
        let Some(_guard) = target_guard(owner, true, summary)? else {
            break;
        };
        if !same_collector(collector.as_ref(), &lock_path)? {
            return Ok(false);
        }
        // A build can start between discovery and retirement, or between batches.
        if !activity::idle(root, SystemTime::now()) || !dedicated_target(root, default_target) {
            idle = false;
            break;
        }
        let Some(_profiles) = plan.lock_profiles(root, summary)? else {
            break;
        };
        for path in batch {
            if mounts.blocked(path, true, summary) {
                continue;
            }
            if retire_path(root, path, &trash, dry_run, summary, None, true)? {
                if !reported {
                    summary.details.push(format!(
                        "workspace target {} (unused for at least 1 hour)",
                        root.display()
                    ));
                    reported = true;
                }
                if dry_run {
                    previews.push(path);
                }
            }
        }
    }

    // Cargo can build again while we count or unlink the detached trees.
    let Some(_guard) = target_guard(owner, false, summary)? else {
        return Ok(idle);
    };
    let mounts = Mounts::read(root)?;
    if !same_collector(collector.as_ref(), &lock_path)? || mounts.blocked(&trash, true, summary) {
        return Ok(idle);
    }
    let device = filesystem_device(&fs::symlink_metadata(root)?);
    let mut remaining = usize::MAX;
    for path in previews {
        if !mounts.blocked(path, true, summary) && plain_ancestors(root, path)? {
            remove_bounded(path, device, &mut remaining, summary, true, None)?;
        }
    }
    if !dry_run || staged {
        drain_trash(&trash, &mut remaining, summary, dry_run, None)?;
    }
    Ok(idle)
}

#[derive(Default)]
struct Plan {
    paths: Vec<PathBuf>,
    locks: Vec<PathBuf>,
}

impl Plan {
    fn discover(
        root: &Path,
        targets: &[ManagedTarget],
        shared_roots: &[PathBuf],
        mounts: &Mounts,
        summary: &mut Summary<'_>,
    ) -> CargoResult<Self> {
        let mut plan = Self::default();
        let mut keep: Vec<PathBuf> = shared_roots
            .iter()
            .map(PathBuf::as_path)
            .chain(
                targets
                    .iter()
                    .flat_map(|target| [target.worktree.as_path(), target.target.as_path()]),
            )
            .filter(|path| *path != root && path.starts_with(root))
            .map(Path::to_owned)
            .collect();
        for profile in profiles_matching(root, |dir| {
            PROFILE_LOCKS.iter().any(|lock| regular(&dir.join(lock)))
        })? {
            for name in PROFILE_LOCKS {
                let lock = profile.join(name);
                if !absent(&lock) {
                    keep.push(lock.clone());
                    plan.locks.push(lock);
                }
            }
            let registries = profile.join("build/registries");
            if !absent(&registries) {
                keep.push(registries);
            }
        }
        let shared = !absent(&root.join(Layout::SHARED_REGISTRY_CACHE_MARKER));
        let mut directories = vec![root.to_path_buf()];
        while let Some(directory) = directories.pop() {
            let Some(entries) = summary.payload_entries(&directory)? else {
                continue;
            };
            for entry in entries {
                summary.tick();
                let entry = entry?;
                let path = entry.path();
                if (directory == root && root_control(&entry.file_name(), shared))
                    || keep.contains(&path)
                {
                    continue;
                }
                if mounts.blocked(&path, false, summary) {
                    continue;
                }
                if entry.file_type()?.is_dir() {
                    // An independently owned cache can also have been registered under
                    // another Cargo home. Stop at its ownership marker.
                    if !absent(&path.join(Layout::SHARED_REGISTRY_CACHE_MARKER))
                        || !absent(&path.join(Layout::PRIVATE_BUILD_LOCK))
                    {
                        continue;
                    }
                    if keep.iter().any(|kept| kept.starts_with(&path)) {
                        directories.push(path);
                        continue;
                    }
                }
                if !mounts.blocked(&path, true, summary) {
                    plan.paths.push(path);
                }
            }
        }
        plan.paths.sort();
        plan.locks.sort();
        Ok(plan)
    }

    /// Stock Cargo shares the profile lock protocol without taking Ohm's target lease.
    fn lock_profiles(
        &self,
        root: &Path,
        summary: &mut Summary<'_>,
    ) -> CargoResult<Option<Vec<CollectorLock>>> {
        let mut guards = Vec::new();
        for path in &self.locks {
            if !plain_ancestors(root, path)? || !regular(path) {
                summary.skip_path(root, "profile lock changed during cleanup");
                return Ok(None);
            }
            let Some(guard) = try_lock(path, false)? else {
                summary.skip_path(root, "target directory is in use");
                summary.blocking_locks.insert(path.clone());
                return Ok(None);
            };
            guards.push(guard);
        }
        Ok(Some(guards))
    }
}

/// Old resolve caches could create the conventional target before Cargo wrote its tag.
/// An explicitly selected external path needs the tag before it can be cleaned as a whole.
fn dedicated_target(root: &Path, default_target: bool) -> bool {
    absent(&root.join(".git"))
        && absent(&root.join("Cargo.toml"))
        && ((default_target && absent(&root.join("CACHEDIR.TAG")))
            || crate::ops::validate_target_dir_tag(root).is_ok())
}

fn root_control(name: &OsStr, shared: bool) -> bool {
    name == "CACHEDIR.TAG"
        || name == Layout::PRIVATE_BUILD_LOCK
        || name == activity::MARKER
        || name == TRASH
        || name == crate::workspace::build_cache_gc::THINLTO
        || name
            .as_encoded_bytes()
            .starts_with(super::collector::TRASH_PREFIX.as_bytes())
        || (shared && name.as_encoded_bytes().starts_with(b".ohm-"))
}
