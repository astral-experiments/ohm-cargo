//! Removes obsolete private contexts in bounded batches under the build lock.

use std::fs;
use std::io;
use std::os::unix::fs::MetadataExt as _;
use std::path::{Path, PathBuf};

use super::{mounts::Mounts, provenance, registry::ManagedTarget};
use crate::compiler::{Layout, OHM_WORKTREE_CLIPPY_DIRECTORY};
use crate::util::CargoResult;
use crate::workspace::build_cache_gc::{
    CollectorLock, Summary, absent, plain_ancestors, plain_directory, profiles,
    scoped_context_name, try_lock_file,
};
use crate::workspace::build_cache_gc_roots::GcAge;

/// Shared targets have one idle timestamp and one set of outputs across their registrations.
pub(crate) fn collect(
    owners: &[ManagedTarget],
    targets: &[ManagedTarget],
    shared_roots: &[PathBuf],
    dry_run: bool,
    age: &mut GcAge,
    current: Option<&provenance::MovingRelease>,
    summary: &mut Summary<'_>,
) -> CargoResult<()> {
    let target = &owners[0];
    if crate::compiler::layout::shared_registry_directory_is_nfs(&target.target)? {
        summary.skip_path(
            &target.target,
            "filesystem does not support reliable build locks",
        );
        return Ok(());
    }
    let whole_target = super::idle::collect(target, targets, shared_roots, dry_run, age, summary)?;
    for owner in owners {
        collect_contexts(owner, dry_run, current.filter(|_| !whole_target), summary)?;
    }
    Ok(())
}

/// Visits only the private namespaces derived from the registered workspace and target.
fn collect_contexts(
    target: &ManagedTarget,
    dry_run: bool,
    current: Option<&provenance::MovingRelease>,
    summary: &mut Summary<'_>,
) -> CargoResult<()> {
    let root = &target.target;
    let mounts = Mounts::read(root)?;
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
    if let Some(current) = current {
        for (profile, paths) in candidates {
            let generation = output_generation(&profile)?;
            let published = published_links(&profile)?;
            for path in paths {
                let context = path.file_name().unwrap().to_str().unwrap();
                let Some(old) = provenance::obsolete(&path, context, current) else {
                    continue;
                };
                let detail = format!(
                    "private context {context} in {} (from {old}; current is {})",
                    target.worktree.display(),
                    current.version
                );
                super::idle::collect_context(target, &path, dry_run, &detail, summary, |summary| {
                    if output_generation(&profile)? != generation {
                        summary
                            .skip_path(&profile, "published build outputs changed during cleanup");
                        return Ok(false);
                    }
                    if published.iter().any(|output| output.starts_with(&path)) {
                        summary.skip_path(
                            &path,
                            "a published build output still refers to this context",
                        );
                        return Ok(false);
                    }
                    Ok(provenance::obsolete(&path, context, current).as_deref()
                        == Some(old.as_str()))
                })
                .or_else(|error| summary.path_error::<()>(&path, error))?;
            }
        }
    }
    Ok(())
}

pub(super) fn target_guard(
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
