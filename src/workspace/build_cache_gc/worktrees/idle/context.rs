//! Uses the target collector's observed-entry deletion for individual obsolete contexts.

use super::*;

/// A foreign boundary keeps its enclosing obsolete context intact.
impl Plan {
    fn context(
        path: &Path,
        mounts: &Mounts,
        summary: &mut Summary<'_>,
    ) -> CargoResult<Option<Self>> {
        if mounts.blocked(path, true, summary) {
            return Ok(None);
        }
        let mut plan = match Self::at(path) {
            Ok(plan) => plan,
            Err(error)
                if error
                    .downcast_ref::<io::Error>()
                    .is_some_and(|error| error.kind() == io::ErrorKind::NotFound) =>
            {
                return Ok(None);
            }
            Err(error) => return Err(error),
        };
        let mut directories = vec![0];
        while let Some(parent) = directories.pop() {
            let directory = &plan.entries[parent];
            let Some(children) = directory.children(plan.device, summary)? else {
                return Ok(None);
            };
            if contains_ownership_marker(&children) {
                summary.skip_path(
                    path,
                    &format!(
                        "contains an independently owned directory at {}",
                        directory.path.display()
                    ),
                );
                return Ok(None);
            }
            for child in children {
                summary.tick();
                if parent == 0 && child.file_name() == provenance::MARKER {
                    continue;
                }
                let kind = child.file_type()?;
                let path = child.path();
                if mounts.blocked(&path, false, summary)
                    || !(kind.is_file() || kind.is_dir() || kind.is_symlink())
                {
                    return Ok(None);
                }
                let index = plan.entries.len();
                plan.entries.push(Entry {
                    path,
                    inode: child.ino(),
                    parent,
                    directory: kind.is_dir(),
                    removable: true,
                });
                if kind.is_dir() {
                    directories.push(index);
                }
            }
        }
        Ok(Some(plan))
    }

    fn same_context(&self) -> bool {
        let entry = &self.entries[0];
        !foreign_directory(&entry.path)
            && entry
                .metadata(self.device)
                .is_ok_and(|metadata| metadata.is_some())
    }
}

/// The caller rechecks compiler proof or staging ownership under every short target lease.
pub(in crate::workspace::build_cache_gc::worktrees) fn collect_context(
    owner: &ManagedTarget,
    path: &Path,
    dry_run: bool,
    detail: &str,
    summary: &mut Summary<'_>,
    mut eligible: impl FnMut(&mut Summary<'_>) -> CargoResult<bool>,
) -> CargoResult<()> {
    let Some(guard) = target_guard(owner, true, summary)? else {
        return Ok(());
    };
    if !eligible(summary)?
        || !crate::workspace::build_cache_gc::plain_ancestors(&owner.target, path)?
    {
        return Ok(());
    }
    drop(guard);
    let Some(plan) = Plan::context(path, &Mounts::read(&owner.target)?, summary)? else {
        return Ok(());
    };
    if plan.device != fs::symlink_metadata(&owner.target)?.dev() {
        summary.skip_path(path, "on a different filesystem from the target directory");
        return Ok(());
    }
    let mut reported = false;
    for batch in plan.entries.rchunks(128) {
        let Some(_guard) = target_guard(owner, true, summary)? else {
            return Ok(());
        };
        if !eligible(summary)?
            || !crate::workspace::build_cache_gc::plain_ancestors(&owner.target, path)?
            || !plan.same_context()
        {
            return Ok(());
        }
        let mounts = Mounts::read(&owner.target)?;
        let mut checked = HashMap::default();
        if plan.remove_batch(batch, dry_run, &mounts, &mut checked, summary)? && !reported {
            summary.details.push(detail.to_owned());
            reported = true;
        }
    }
    if dry_run {
        return Ok(());
    }
    let Some(_guard) = target_guard(owner, true, summary)? else {
        return Ok(());
    };
    if eligible(summary)?
        && crate::workspace::build_cache_gc::plain_ancestors(&owner.target, path)?
        && plan.same_context()
        && !Mounts::read(&owner.target)?.blocked(path, true, summary)
    {
        finish_context(path, plan.device, plan.entries[0].inode)?;
    }
    Ok(())
}

/// Keep the compiler proof until all payload is gone, so interrupted passes remain discoverable.
fn finish_context(path: &Path, device: u64, inode: u64) -> CargoResult<()> {
    if fs::read_dir(path)?
        .any(|entry| !entry.is_ok_and(|entry| entry.file_name() == provenance::MARKER))
    {
        return Ok(());
    }
    let parent = fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW)
        .open(path.parent().unwrap())?;
    let name = path.file_name().unwrap();
    let directory = at::open_dir(&parent, name)?;
    let metadata = directory.metadata()?;
    if metadata.ino() != inode || metadata.dev() != device {
        return Ok(());
    }
    match at::unlink(&directory, OsStr::new(provenance::MARKER), false) {
        Ok(()) => {}
        Err(e) if e.kind() == io::ErrorKind::NotFound => {}
        Err(e) => return Err(e.into()),
    }
    if at::entry_len(&parent, name, device, inode, true)?.is_none() {
        return Ok(());
    }
    match at::unlink(&parent, name, true) {
        Ok(()) => Ok(()),
        // Contents introduced by an unrelated writer remain durably unmarked.
        Err(error)
            if matches!(
                error.kind(),
                io::ErrorKind::NotFound | io::ErrorKind::DirectoryNotEmpty
            ) =>
        {
            Ok(())
        }
        Err(error) => Err(error.into()),
    }
}
