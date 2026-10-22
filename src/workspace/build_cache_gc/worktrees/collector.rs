//! Detaches obsolete private contexts under the build lock, then unlinks their files.

use std::fs;
use std::io;
use std::os::unix::fs::MetadataExt as _;
use std::path::{Path, PathBuf};

use super::{mounts::Mounts, provenance, registry::ManagedTarget};
use crate::compiler::{Layout, OHM_WORKTREE_CLIPPY_DIRECTORY};
use crate::util::CargoResult;
use crate::workspace::build_cache_gc::{
    CollectorLock, RENAME_BUDGET, Summary, absent, create_plain, drain_trash, filesystem_device,
    plain_ancestors, plain_directory, profiles, remove_bounded, retire_path, scoped_context_name,
    try_lock, try_lock_file,
};

const TRASH_PREFIX: &str = ".ohm-worktree-gc-trash-v1-";

/// Visits only the private namespaces derived from the registered workspace and target.
pub(crate) fn collect(
    target: &ManagedTarget,
    dry_run: bool,
    current: Option<&provenance::MovingRelease>,
    summary: &mut Summary<'_>,
) -> CargoResult<()> {
    let root = &target.target;
    if crate::compiler::layout::shared_registry_directory_is_nfs(root)? {
        summary.skip_path(root, "filesystem does not support reliable build locks");
        return Ok(());
    }
    // Multiple workspaces can select one target. Staged payloads must be counted once.
    let trash = root.join(format!("{TRASH_PREFIX}{}", target.namespaces[0]));
    let mounts = Mounts::read(root)?;
    if mounts.blocked(&trash, true, summary) {
        return Ok(());
    }
    let mut candidates = Vec::new();
    if let Some(current) = current {
        for profile in profiles(root)? {
            let mut paths = Vec::new();
            for namespace in &target.namespaces {
                let base = profile.join("build/workspaces").join(namespace);
                for directory in [&base, &base.join(OHM_WORKTREE_CLIPPY_DIRECTORY)] {
                    if mounts.blocked(directory, false, summary)
                        || !plain_ancestors(root, directory)?
                        || !plain_directory(directory)
                    {
                        continue;
                    }
                    if let Some(entries) = summary.payload_entries(directory)? {
                        for entry in entries {
                            summary.tick();
                            let entry = entry?;
                            if entry.file_type()?.is_dir()
                                && let Some(context) = entry.file_name().to_str()
                                && scoped_context_name(context)
                                && !mounts.blocked(&entry.path(), true, summary)
                                && provenance::obsolete(&entry.path(), context, current).is_some()
                            {
                                paths.push(entry.path());
                            }
                        }
                    }
                }
            }
            if !paths.is_empty() {
                paths.sort();
                candidates.push((profile, paths));
            }
        }
    }
    let staged = plain_directory(&trash)
        && fs::read_dir(&trash)?
            .any(|entry| entry.is_ok_and(|entry| entry.file_type().is_ok_and(|ty| ty.is_dir())));
    if candidates.is_empty() && !staged {
        return Ok(());
    }

    let mounts = Mounts::read(root)?;
    if mounts.blocked(&trash, true, summary) {
        return Ok(());
    }
    // A busy target needs no new bookkeeping. Already detached trash can be drained
    // under a shared lease, even while a build is running.
    let Some(guard) = target_guard(target, !candidates.is_empty() && !staged, summary)? else {
        return Ok(());
    };
    let collector_path = trash.join("collector.lock");
    let collector = if !dry_run || !absent(&collector_path) {
        if !dry_run {
            create_plain(&trash)?;
        }
        let Some(lock) = try_lock(&collector_path, !dry_run)? else {
            summary.skip_path(root, "another garbage collector is using this target");
            summary.blocking_locks.insert(collector_path);
            return Ok(());
        };
        Some(lock)
    } else {
        None
    };
    drop(guard);

    let mut previews = Vec::new();
    if let Some(current) = current {
        'profiles: for (profile, paths) in candidates {
            // Resolving thousands of example outputs or following links onto another mount
            // must not hold up a build. Recheck the publication directories under the lease.
            let generation = output_generation(&profile)?;
            let published = published_links(&profile)?;
            for batch in paths.chunks(RENAME_BUDGET) {
                let Some(_guard) = target_guard(target, true, summary)? else {
                    break 'profiles;
                };
                if !same_collector(collector.as_ref(), &collector_path)? {
                    return Ok(());
                }
                if output_generation(&profile)? != generation {
                    summary.skip_path(&profile, "published build outputs changed during cleanup");
                    continue 'profiles;
                }
                for path in batch {
                    let context = path.file_name().unwrap().to_str().unwrap();
                    if mounts.blocked(path, true, summary) || !plain_ancestors(root, path)? {
                        continue;
                    }
                    let Some(old) = provenance::obsolete(path, context, current) else {
                        continue;
                    };
                    if published.iter().any(|output| output.starts_with(path)) {
                        summary.skip_path(
                            path,
                            "a published build output still refers to this context",
                        );
                        continue;
                    }
                    if retire_path(root, path, &trash, dry_run, summary, true)? {
                        summary.details.push(format!(
                            "private context {context} in {} (from {old}; current is {})",
                            target.worktree.display(),
                            current.version
                        ));
                        if dry_run {
                            previews.push(path.clone());
                        }
                    }
                }
            }
        }
    }

    // Recursive traversal can be slow. A shared lease allows ordinary builds and
    // keeps a simultaneous local clean from replacing directories beneath the walk.
    let Some(_guard) = target_guard(target, false, summary)? else {
        return Ok(());
    };
    // A mount can move with a retired directory. Check the actual staging paths
    // again before the recursive walk, including trash left by interrupted GC.
    let mounts = Mounts::read(root)?;
    if mounts.blocked(&trash, true, summary)
        || !same_collector(collector.as_ref(), &collector_path)?
    {
        return Ok(());
    }
    let mut remaining = usize::MAX;
    let device = filesystem_device(&fs::symlink_metadata(root)?);
    for path in previews {
        if mounts.blocked(&path, true, summary) {
            continue;
        }
        remove_bounded(
            &path,
            device,
            &mut remaining,
            summary,
            true,
            Some(&path.join(provenance::MARKER)),
        )?;
    }
    if dry_run && !staged {
        return Ok(());
    }
    drain_trash(
        &trash,
        &mut remaining,
        summary,
        dry_run,
        Some(provenance::MARKER),
    )
}

fn target_guard(
    target: &ManagedTarget,
    exclusive: bool,
    summary: &mut Summary<'_>,
) -> CargoResult<Option<CollectorLock>> {
    let path = target.target.join(Layout::PRIVATE_BUILD_LOCK);
    match try_lock_file(&path, false, exclusive)? {
        Some(lock) if target.still_owned(&lock.0) => Ok(Some(lock)),
        Some(_) => Ok(None),
        None => {
            if !absent(&path) {
                summary.skip_path(&target.target, "target directory is in use");
                summary.blocking_locks.insert(path);
            }
            Ok(None)
        }
    }
}

/// A full local clean can remove the collector lock between target leases.
fn same_collector(lock: Option<&CollectorLock>, path: &Path) -> CargoResult<bool> {
    let Some(lock) = lock else { return Ok(true) };
    let opened = lock.0.metadata()?;
    match fs::symlink_metadata(path) {
        Ok(named) => {
            Ok(named.is_file() && (named.dev(), named.ino()) == (opened.dev(), opened.ino()))
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(error.into()),
    }
}

type DirectoryStamp = (u64, u64, i64, i64);

/// Creating or replacing a published symlink changes its parent directory's ctime.
fn output_generation(profile: &Path) -> CargoResult<[Option<DirectoryStamp>; 2]> {
    let stamp = |path: &Path| -> CargoResult<_> {
        match fs::symlink_metadata(path) {
            Ok(stat) if stat.is_dir() => Ok(Some((
                stat.dev(),
                stat.ino(),
                stat.ctime(),
                stat.ctime_nsec(),
            ))),
            Ok(_) => anyhow::bail!("invalid output directory {}", path.display()),
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
            Err(error) => Err(error.into()),
        }
    };
    Ok([stamp(profile)?, stamp(&profile.join("examples"))?])
}

/// Cargo may publish a directory artifact, such as a dSYM, as a symlink.
fn published_links(profile: &Path) -> CargoResult<Vec<PathBuf>> {
    let mut result = Vec::new();
    for directory in [profile, &profile.join("examples")] {
        if absent(directory) {
            continue;
        }
        anyhow::ensure!(
            plain_directory(directory),
            "invalid output directory {}",
            directory.display()
        );
        for entry in fs::read_dir(directory)? {
            let entry = entry?;
            if entry.file_type()?.is_symlink() {
                match entry.path().canonicalize() {
                    Ok(path) => result.push(path),
                    Err(error) if error.kind() == io::ErrorKind::NotFound => {}
                    Err(error) => return Err(error.into()),
                }
            }
        }
    }
    Ok(result)
}
