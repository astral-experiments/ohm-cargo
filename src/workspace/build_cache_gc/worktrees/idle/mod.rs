//! Removes idle private output in bounded batches under Cargo's target and profile locks.

use std::ffi::OsStr;
use std::fs;
use std::io::{self, Read as _};
use std::os::unix::fs::{DirEntryExt as _, MetadataExt as _, OpenOptionsExt as _};
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use super::collector::target_guard;
use super::{activity, at, mounts::Mounts, provenance, registry::ManagedTarget};
use crate::compiler::Layout;
use crate::util::CargoResult;
use crate::util::data_structures::{HashMap, HashSet};
use crate::workspace::build_cache_gc::{CollectorLock, Summary, absent, regular};

const PROFILE_LOCKS: [&str; 3] = [".cargo-build-lock", ".cargo-lock", ".cargo-artifact-lock"];

mod context;
pub(super) use context::collect_context;

/// Returns whether the target-wide pass superseded individual compiler contexts.
pub(super) fn collect(
    owner: &ManagedTarget,
    targets: &[ManagedTarget],
    shared_roots: &[PathBuf],
    dry_run: bool,
    summary: &mut Summary<'_>,
) -> CargoResult<bool> {
    let root = &owner.target;
    if !activity::idle(root, SystemTime::now()) {
        return Ok(false);
    }
    let default_target = targets
        .iter()
        .any(|target| target.target == *root && target.worktree.join("target") == *root);
    if !dedicated_target(root, default_target, shared_roots) {
        summary.skip_path(root, "could not verify a dedicated Cargo target");
        return Ok(false);
    }
    // Avoid scanning a target already in use. Release the lease during discovery.
    let Some(guard) = target_guard(owner, true, summary)? else {
        return Ok(true);
    };
    drop(guard);
    let mounts = Mounts::read(root)?;
    if mounts.blocked(&root.join(activity::MARKER), false, summary) {
        return Ok(false);
    }
    let plan = Plan::discover(root, targets, shared_roots, &mounts, summary)?;
    let mut reported = false;
    // Children precede parents. A newly populated directory therefore survives an rmdir,
    // even if another Cargo home enrolled it after discovery.
    for batch in plan.entries.rchunks(128) {
        let Some(_guard) = target_guard(owner, true, summary)? else {
            break;
        };
        if !activity::idle(root, SystemTime::now())
            || !dedicated_target(root, default_target, shared_roots)
        {
            return Ok(false);
        }
        let mounts = Mounts::read(root)?;
        if mounts.blocked(&root.join(activity::MARKER), false, summary) {
            return Ok(false);
        }
        let mut checked = HashMap::default();
        let Some(_profiles) = plan.lock_profiles(dry_run, &mounts, &mut checked, summary)? else {
            break;
        };
        if plan.remove_batch(batch, dry_run, &mounts, &mut checked, summary)? && !reported {
            summary.details.push(format!(
                "workspace target {} (unused for at least 1 hour)",
                root.display()
            ));
            reported = true;
        }
    }
    Ok(true)
}

struct Entry {
    path: PathBuf,
    inode: u64,
    parent: usize,
    directory: bool,
    removable: bool,
}

impl Entry {
    fn metadata(&self, device: u64) -> CargoResult<Option<fs::Metadata>> {
        match fs::symlink_metadata(&self.path) {
            Ok(m) => Ok((m.ino() == self.inode
                && m.dev() == device
                && m.is_dir() == self.directory)
                .then_some(m)),
            Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(None),
            Err(e) => Err(e.into()),
        }
    }

    fn children(
        &self,
        device: u64,
        summary: &mut Summary<'_>,
    ) -> CargoResult<Option<Vec<fs::DirEntry>>> {
        if self
            .metadata(device)
            .or_else(|error| summary.path_error(&self.path, error))?
            .is_none()
        {
            return Ok(None);
        }
        match fs::read_dir(&self.path).and_then(|entries| entries.collect()) {
            Ok(children) => Ok(Some(children)),
            Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(None),
            Err(e) => summary.path_error(&self.path, e.into()),
        }
    }

    /// Recheck the observed inode before unlinking its name in the pinned parent.
    fn remove(
        &self,
        parent: &fs::File,
        dry_run: bool,
        device: u64,
        summary: &mut Summary<'_>,
    ) -> CargoResult<bool> {
        let name = self.path.file_name().unwrap();
        let Some(len) = at::entry_len(parent, name, device, self.inode, self.directory)? else {
            return Ok(false);
        };
        if !dry_run {
            match at::unlink(parent, name, self.directory) {
                Ok(()) => {}
                Err(e)
                    if matches!(
                        e.kind(),
                        io::ErrorKind::NotFound | io::ErrorKind::DirectoryNotEmpty
                    ) =>
                {
                    return Ok(false);
                }
                Err(e) => return Err(e.into()),
            }
        }
        summary.counts.record_entry(self.directory, len);
        summary.tick();
        Ok(true)
    }
}

struct Plan {
    entries: Vec<Entry>,
    profiles: Vec<usize>,
    device: u64,
}

impl Plan {
    fn at(path: &Path) -> CargoResult<Self> {
        let metadata = fs::symlink_metadata(path)?;
        anyhow::ensure!(
            metadata.is_dir(),
            "expected a directory at {}",
            path.display()
        );
        Ok(Self {
            entries: vec![Entry {
                path: path.to_owned(),
                inode: metadata.ino(),
                parent: 0,
                directory: true,
                removable: false,
            }],
            profiles: Vec::new(),
            device: metadata.dev(),
        })
    }

    fn discover(
        root: &Path,
        targets: &[ManagedTarget],
        shared_roots: &[PathBuf],
        mounts: &Mounts,
        summary: &mut Summary<'_>,
    ) -> CargoResult<Self> {
        let mut plan = Self::at(root)?;
        let keep: HashSet<&Path> = shared_roots
            .iter()
            .map(PathBuf::as_path)
            .chain(
                targets
                    .iter()
                    .flat_map(|target| [target.worktree.as_path(), target.target.as_path()]),
            )
            .collect();
        let shared = !absent(&root.join(Layout::SHARED_REGISTRY_CACHE_MARKER));
        // Unrecognized top-level directories can contain cross-target profiles. Only
        // enter their known Cargo layouts; stock Cargo may still be creating a profile.
        let mut directories = vec![(0, false, false)];
        while let Some((parent, cross_target, is_profile)) = directories.pop() {
            let directory = &plan.entries[parent];
            let Some(children) = directory.children(plan.device, summary)? else {
                plan.preserve(parent);
                continue;
            };
            if parent != 0 && contains_ownership_marker(&children) {
                plan.preserve(parent);
                continue;
            }
            if is_profile {
                plan.profiles.push(parent);
            }
            for child in children {
                summary.tick();
                let path = child.path();
                let name = child.file_name();
                let kind = child.file_type()?;
                let profile = kind.is_dir()
                    && (parent == 0 || cross_target)
                    && PROFILE_LOCKS.iter().any(|lock| regular(&path.join(lock)));
                let layout = matches!(
                    name.to_str(),
                    Some("doc" | "tmp" | "package" | "cargo-timings")
                );
                let skip = (parent == 0 && root_control(&name, shared))
                    || keep.contains(path.as_path())
                    || (cross_target && !profile && !layout)
                    || (is_profile && PROFILE_LOCKS.iter().any(|lock| name == *lock))
                    || (name == "registries"
                        && path.parent().is_some_and(|p| p.ends_with("build")))
                    || mounts.blocked(&path, false, summary)
                    || !(kind.is_dir() || kind.is_file() || kind.is_symlink());
                if skip {
                    plan.preserve(parent);
                    continue;
                }
                let container = kind.is_dir() && parent == 0 && !profile && !layout;
                let index = plan.entries.len();
                plan.entries.push(Entry {
                    path,
                    inode: child.ino(),
                    parent,
                    directory: kind.is_dir(),
                    removable: !profile && !container,
                });
                if profile || container {
                    plan.preserve(parent);
                }
                if kind.is_dir() {
                    directories.push((index, container, profile));
                }
            }
        }
        Ok(plan)
    }

    fn preserve(&mut self, mut index: usize) {
        while self.entries[index].removable {
            self.entries[index].removable = false;
            index = self.entries[index].parent;
        }
    }

    fn remove_batch(
        &self,
        batch: &[Entry],
        dry_run: bool,
        mounts: &Mounts,
        checked: &mut HashMap<usize, Option<fs::File>>,
        summary: &mut Summary<'_>,
    ) -> CargoResult<bool> {
        let mut removed = false;
        for entry in batch.iter().rev().filter(|entry| entry.removable) {
            if !mounts.blocked(&entry.path, false, summary)
                && self.valid_directory(entry.parent, mounts, checked, summary)?
            {
                removed |= entry
                    .remove(
                        checked[&entry.parent].as_ref().unwrap(),
                        dry_run,
                        self.device,
                        summary,
                    )
                    .or_else(|error| summary.path_error(&entry.path, error))?;
            }
        }
        Ok(removed)
    }

    /// Recheck each parent once per batch, before using pathnames under it.
    fn valid_directory(
        &self,
        index: usize,
        mounts: &Mounts,
        checked: &mut HashMap<usize, Option<fs::File>>,
        summary: &mut Summary<'_>,
    ) -> CargoResult<bool> {
        if let Some(directory) = checked.get(&index) {
            return Ok(directory.is_some());
        }
        let entry = &self.entries[index];
        if index != 0
            && (!self.valid_directory(entry.parent, mounts, checked, summary)?
                || mounts.blocked(&entry.path, false, summary))
        {
            checked.insert(index, None);
            return Ok(false);
        }
        let opened = if index == 0 {
            fs::OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW)
                .open(&entry.path)
        } else {
            at::open_dir(
                checked[&entry.parent].as_ref().unwrap(),
                entry.path.file_name().unwrap(),
            )
        };
        let directory = match opened {
            Ok(dir) => {
                let metadata = dir.metadata()?;
                (metadata.ino() == entry.inode
                    && metadata.dev() == self.device
                    && (index == 0
                        || !ownership_markers().any(|m| at::exists(&dir, m).unwrap_or(true))))
                .then_some(dir)
            }
            Err(e)
                if matches!(
                    e.kind(),
                    io::ErrorKind::NotFound | io::ErrorKind::NotADirectory
                ) || e.raw_os_error() == Some(libc::ELOOP) =>
            {
                None
            }
            Err(e) => summary.path_error(&entry.path, e.into())?,
        };
        let valid = directory.is_some();
        checked.insert(index, directory);
        Ok(valid)
    }

    /// Keep profile directories and their lock inodes in place for older Cargo versions.
    fn lock_profiles(
        &self,
        dry_run: bool,
        mounts: &Mounts,
        checked: &mut HashMap<usize, Option<fs::File>>,
        summary: &mut Summary<'_>,
    ) -> CargoResult<Option<Vec<CollectorLock>>> {
        let mut guards = Vec::new();
        for &profile in &self.profiles {
            if !self.valid_directory(profile, mounts, checked, summary)? {
                return Ok(None);
            }
            for name in PROFILE_LOCKS {
                let path = self.entries[profile].path.join(name);
                let directory = checked[&profile].as_ref().unwrap();
                match at::lock_profile(directory, name, !dry_run) {
                    Ok(Some(guard)) => guards.push(guard),
                    Ok(None) => {
                        summary.skip_path(&self.entries[0].path, "target directory is in use");
                        summary.blocking_locks.insert(path);
                        return Ok(None);
                    }
                    Err(error)
                        if dry_run
                            && error
                                .downcast_ref::<io::Error>()
                                .is_some_and(|e| e.kind() == io::ErrorKind::NotFound) => {}
                    Err(error) => {
                        summary.path_error::<()>(&path, error)?;
                        return Ok(None);
                    }
                }
            }
        }
        Ok(Some(guards))
    }
}

fn foreign_directory(path: &Path) -> bool {
    ownership_markers().any(|name| !absent(&path.join(name)))
}

fn contains_ownership_marker(children: &[fs::DirEntry]) -> bool {
    children.iter().any(|child| {
        let name = child.file_name();
        ownership_markers().any(|marker| name == marker)
    })
}

fn ownership_markers() -> impl Iterator<Item = &'static str> {
    [
        ".git",
        "Cargo.toml",
        "CACHEDIR.TAG",
        Layout::PRIVATE_BUILD_LOCK,
        Layout::SHARED_REGISTRY_CACHE_MARKER,
    ]
    .into_iter()
    .chain(provenance::EXPORT_MARKERS)
}

/// An external target needs Cargo's tag. A shared root may come from another Cargo home.
fn dedicated_target(root: &Path, default_target: bool, known_roots: &[PathBuf]) -> bool {
    if !absent(&root.join(".git")) || !absent(&root.join("Cargo.toml")) {
        return false;
    }
    for ancestor in root.ancestors().skip(1) {
        if (known_roots.iter().any(|known| known == ancestor)
            || !absent(&ancestor.join(Layout::SHARED_REGISTRY_CACHE_MARKER)))
            && shared_payload(ancestor, root)
        {
            return false;
        }
    }
    let tag = root.join("CACHEDIR.TAG");
    if default_target && absent(&tag) {
        return true;
    }
    const TAG: &str = cargo_util::paths::CARGO_CACHE_TAG;
    let mut buffer = [0; TAG.len()];
    crate::workspace::build_cache_gc_roots::open_regular(&tag).is_ok_and(|mut file| {
        file.metadata()
            .is_ok_and(|metadata| metadata.len() == TAG.len() as u64)
            && file.read_exact(&mut buffer).is_ok()
            && buffer == TAG.as_bytes()
    })
}

/// Shared data lives directly under a profile or one target triple deeper.
/// Other subtrees can contain independently tagged targets, including Cargo's test fixtures.
fn shared_payload(shared: &Path, target: &Path) -> bool {
    let mut parts = target.strip_prefix(shared).unwrap().iter();
    let first = parts.next().unwrap();
    let Some(second) = parts.next() else {
        return true;
    };
    let Some(third) = parts.next() else {
        return true;
    };
    let directory = shared.join(first);
    first.as_encoded_bytes().starts_with(b".")
        || second == "build"
        || third == "build"
        || !absent(&directory.join(".cargo-build-lock"))
        || !absent(&directory.join(second).join(".cargo-build-lock"))
}

fn root_control(name: &OsStr, shared: bool) -> bool {
    name == "CACHEDIR.TAG"
        || name == Layout::PRIVATE_BUILD_LOCK
        || name == activity::MARKER
        || name == ".ohm-target-gc-trash-v1"
        || name == crate::workspace::build_cache_gc::THINLTO
        || name
            .as_encoded_bytes()
            .starts_with(b".ohm-worktree-gc-trash-v1-")
        || (shared && name.as_encoded_bytes().starts_with(b".ohm-"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stock_build_can_finish_opening_a_profile_after_discovery() -> CargoResult<()> {
        let temp = tempfile::tempdir()?;
        let root = temp.path();
        let debug = root.join("debug");
        let release = root.join("release");
        fs::create_dir(&debug)?;
        fs::create_dir(&release)?;
        fs::File::create_new(debug.join(".cargo-lock"))?;
        fs::write(release.join("initial-output"), b"release")?;
        let mounts = Mounts::read(root)?;
        let mut summary = Summary::default();
        let plan = Plan::discover(root, &[], &[], &mounts, &mut summary)?;

        // Release had no lock yet. Even its preexisting output is outside this run.
        let release_lock = fs::File::create_new(release.join(".cargo-lock"))?;
        release_lock.lock()?;
        assert!(
            !plan
                .entries
                .iter()
                .any(|entry| entry.removable && entry.path.starts_with(&release))
        );

        // Debug was established. Cargo can start using a second protocol lock
        // between discovery and deletion, while its original lock remains free.
        let path = debug.join(".cargo-artifact-lock");
        let held = fs::File::create_new(&path)?;
        held.lock()?;
        for dry_run in [true, false] {
            assert!(
                plan.lock_profiles(dry_run, &mounts, &mut HashMap::default(), &mut summary)?
                    .is_none()
            );
            assert!(summary.blocking_locks.contains(&path));
        }
        Ok(())
    }
}
