//! Opt-in ownership and expiry of workspace-private incremental configurations.

use std::fs::{self, File, TryLockError};
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use anyhow::{Context as _, ensure};
use serde::{Deserialize, Serialize};

use crate::CargoResult;
use crate::core::Workspace;
use crate::core::compiler::{BuildRunner, CompileMode, Layout, Unit};
use crate::ops::CleanContext;
use crate::util::data_structures::{HashMap, HashSet};
use crate::util::flock;

pub const DIRECTORY: &str = "ohm-gc-v1";
const MARKER: &str = ".ohm-incremental-gc.json";
const REFRESH_INTERVAL: u64 = 60 * 60;

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Record {
    version: u32,
    unit: String,
    last_used: u64,
}

impl Record {
    fn parse(contents: &[u8], unit: &str) -> Option<Self> {
        let record: Self = serde_json::from_slice(contents).ok()?;
        (matches!(record.version, 1 | 2) && record.unit == unit && valid_unit_name(unit))
            .then_some(record)
    }

    fn expired(&self, now: u64, max_age: Duration) -> bool {
        // Version 2 refreshes at most hourly. Treat the end of that interval as
        // the last possible use, so throttling never causes premature expiry.
        let latest_use = if self.version == 2 {
            self.last_used.saturating_add(REFRESH_INTERVAL)
        } else {
            self.last_used
        };
        now.checked_sub(latest_use)
            .is_some_and(|age| Duration::from_secs(age) >= max_age)
    }

    fn needs_refresh(&self, now: u64) -> bool {
        self.version == 1
            || now
                .checked_sub(self.last_used)
                .is_some_and(|age| age >= REFRESH_INTERVAL)
    }
}

fn valid_unit_name(name: &str) -> bool {
    name.rsplit_once('-').is_some_and(|(name, hash)| {
        !name.is_empty()
            && name
                .chars()
                .all(|character| character.is_alphanumeric() || character == '_')
            && hash.len() == 16
            && hash.bytes().all(|byte| byte.is_ascii_hexdigit())
    })
}

pub(crate) fn enabled(build_runner: &BuildRunner<'_, '_>, unit: &Unit) -> bool {
    build_runner.bcx.gctx.cli_unstable().ohm_incremental_gc
        && build_runner.bcx.ws.shared_registry_cache_enabled()
        && unit.profile.incremental
        && matches!(
            unit.mode,
            CompileMode::Build | CompileMode::Test | CompileMode::Check { .. }
        )
}

/// Groups by Cargo's `-C metadata` value, preserving reuse across diagnostic flags.
/// Rustc still applies its own crate identity and session protocol within each root.
pub(crate) fn directory(build_runner: &BuildRunner<'_, '_>, unit: &Unit) -> PathBuf {
    let files = build_runner.files();
    let root = files.incremental_dir(unit);
    if !enabled(build_runner, unit) {
        return root.to_path_buf();
    }
    root.join(DIRECTORY).join(format!(
        "{}-{}",
        unit.target.crate_name(),
        files.metadata(unit).c_metadata()
    ))
}

/// Records graph use, including fresh units, while the build's profile lease is held.
pub(crate) fn record_use(build_runner: &mut BuildRunner<'_, '_>, unit: &Unit) -> CargoResult<()> {
    if !enabled(build_runner, unit) {
        return Ok(());
    }
    let layout_root = build_runner
        .files()
        .layout(unit.kind)
        .build_dir()
        .root()
        .to_path_buf();
    let directory = directory(build_runner, unit);
    let root = build_runner
        .incremental_gc
        .roots
        .entry(layout_root.clone())
        .or_insert_with(|| build_runner.bcx.ws.canonical_build_path(&layout_root))
        .clone();
    let directory = root.join(directory.strip_prefix(&layout_root)?);
    build_runner.incremental_gc.record(&root, &directory)
}

/// Caches directory validation within the build's workspace/profile leases.
#[derive(Default)]
pub(crate) struct Tracker {
    roots: HashMap<PathBuf, PathBuf>,
    directories: HashSet<PathBuf>,
}

impl Tracker {
    fn record(&mut self, root: &Path, directory: &Path) -> CargoResult<()> {
        let mut current = root.to_path_buf();
        for component in
            std::iter::once(None).chain(directory.strip_prefix(root)?.components().map(Some))
        {
            if let Some(component) = component {
                ensure!(
                    matches!(component, Component::Normal(_)),
                    "invalid incremental directory path"
                );
                current.push(component);
            }
            if !self.directories.contains(&current) {
                match fs::symlink_metadata(&current) {
                    Ok(metadata) => ensure!(
                        metadata.is_dir(),
                        "incremental directory contains a symlink or non-directory: {}",
                        current.display()
                    ),
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                        match fs::create_dir(&current) {
                            Ok(()) => {}
                            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                                // Another workspace can create a shared ancestor
                                // while both builds hold their shared profile lease.
                                ensure!(
                                    fs::symlink_metadata(&current)?.is_dir(),
                                    "incremental directory is not a plain directory: {}",
                                    current.display()
                                );
                            }
                            Err(error) => return Err(error.into()),
                        }
                    }
                    Err(error) => return Err(error.into()),
                }
                self.directories.insert(current.clone());
            }
        }
        let name = directory.file_name().unwrap().to_str().unwrap();
        ensure!(
            valid_unit_name(name),
            "invalid incremental configuration name"
        );
        let marker = directory.join(MARKER);
        let now = now()?;
        match fs::symlink_metadata(&marker) {
            Ok(metadata) => {
                ensure!(
                    metadata.is_file(),
                    "incremental ownership marker is not a regular file"
                );
                let record = Record::parse(&fs::read(&marker)?, name).with_context(|| {
                    format!("invalid incremental ownership marker: {}", marker.display())
                })?;
                if !record.needs_refresh(now) {
                    return Ok(());
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                ensure!(
                    fs::read_dir(&directory)?.next().is_none(),
                    "refusing to adopt unrecorded incremental data: {}",
                    directory.display()
                );
            }
            Err(error) => return Err(error.into()),
        }
        let record = Record {
            version: 2,
            unit: name.to_owned(),
            last_used: now,
        };
        // Stage outside the unit directory: a killed writer must not leave a
        // nonempty, unrecorded unit that subsequent builds refuse to enroll.
        // Persist replaces the marker itself rather than following a marker symlink.
        let mut temporary = tempfile::NamedTempFile::new_in(directory.parent().unwrap())?;
        temporary.write_all(&serde_json::to_vec(&record)?)?;
        temporary.persist(&marker)?;
        Ok(())
    }
}

pub(crate) const TRASH_DIRECTORY: &str = "ohm-gc-trash-v1";

/// Expires recorded configurations for the calling workspace, skipping busy profiles.
///
/// An exclusive profile lease conflicts with every shared-cache compiler lease,
/// including those inherited by children after Cargo exits. No fingerprint or
/// final artifact is removed, so an expired configuration remains buildable.
pub fn clean(ws: &Workspace<'_>, max_age: Duration, dry_run: bool) -> CargoResult<()> {
    ensure!(
        ws.gctx().cli_unstable().ohm_incremental_gc,
        "incremental cleanup requires -Zohm-incremental-gc"
    );
    ensure!(
        ws.shared_registry_cache_enabled(),
        "incremental cleanup requires -Zohm-shared-registry-cache"
    );
    ensure!(
        cfg!(any(target_os = "linux", target_os = "macos")),
        "incremental cleanup currently requires Linux or macOS"
    );
    ws.validate_shared_cache_target()?;
    let build_root = ws.canonical_build_path(ws.build_dir().as_path_unlocked());
    let target_root = ws.canonical_build_path(ws.target_dir().as_path_unlocked());
    for ancestor in ws.shared_cache_ancestors()? {
        for root in [&build_root, &target_root] {
            for protected in [&ancestor.build_root, &ancestor.target_root] {
                ensure!(
                    !root.starts_with(protected) && !protected.starts_with(root),
                    "nested Cargo cannot clean overlapping parent build or target directories"
                );
            }
        }
    }
    let namespaces = Layout::shared_workspace_cleanup_namespaces(ws);
    let mut context = CleanContext::new(ws.gctx());
    context.dry_run = dry_run;
    let now = now()?;
    let mut removed = 0;
    let mut retained = 0;
    let mut skipped = 0;
    let mut busy = 0;
    let mut reclaimed = 0;
    for profile in profiles(&build_root)? {
        let Some(_guard) = lock_profile(&profile)? else {
            busy += 1;
            continue;
        };
        for namespace in &namespaces {
            let incremental = profile.join("incremental").join(namespace);
            let managed = incremental.join(DIRECTORY);
            let trash = incremental.join(TRASH_DIRECTORY);
            let clippy = incremental.join(crate::core::compiler::OHM_WORKTREE_CLIPPY_DIRECTORY);
            let clippy_managed = clippy.join(DIRECTORY);
            let clippy_trash = clippy.join(TRASH_DIRECTORY);
            let mut reclaimed_paths = HashSet::default();
            // Retired configurations are no longer available to rustc, regardless
            // of their age. Finish prior collections before retiring more entries.
            for (root, trash, is_trash) in [
                (&trash, &trash, true),
                (&clippy_trash, &clippy_trash, true),
                (&managed, &trash, false),
                (&clippy_managed, &clippy_trash, false),
            ] {
                if !plain_descendants(&profile, root)? {
                    continue;
                }
                for entry in fs::read_dir(root)? {
                    let entry = entry?;
                    let directory = entry.path();
                    let Some(name) = entry.file_name().to_str().map(str::to_owned) else {
                        skipped += 1;
                        continue;
                    };
                    if !entry.file_type()?.is_dir() || !valid_unit_name(&name) {
                        skipped += 1;
                        continue;
                    }
                    // A collection can stop after removing its last marker but
                    // before removing the empty trash directory. `remove_dir`
                    // cannot delete an unrecognized payload in this recovery path.
                    if is_trash && fs::read_dir(&directory)?.next().is_none() {
                        if !dry_run {
                            fs::remove_dir(&directory)?;
                        }
                        reclaimed_paths.insert(directory);
                        reclaimed += 1;
                        continue;
                    }
                    let marker = directory.join(MARKER);
                    if !regular_file(&marker)? {
                        skipped += 1;
                        continue;
                    }
                    let Some(record) = Record::parse(&fs::read(&marker)?, &name) else {
                        skipped += 1;
                        continue;
                    };
                    if !is_trash && !record.expired(now, max_age) {
                        retained += 1;
                        continue;
                    }
                    if !plain_tree(&directory)? {
                        skipped += 1;
                        continue;
                    }
                    let destination = trash.join(&name);
                    if !is_trash {
                        match fs::symlink_metadata(&destination) {
                            Ok(_) if !(dry_run && reclaimed_paths.contains(&destination)) => {
                                skipped += 1;
                                continue;
                            }
                            Ok(_) => {}
                            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                            Err(error) => return Err(error.into()),
                        }
                    }
                    ws.gctx()
                        .shell()
                        .status(if dry_run { "Would expire" } else { "Expiring" }, &name)?;
                    if !is_trash && !dry_run {
                        create_plain_descendants(&profile, trash)?;
                        // Removing files from a finalized session in place can
                        // leave a usable dep-graph with a missing query cache after
                        // interruption. Hide the entire configuration atomically
                        // before deleting any files, while holding the profile lock.
                        fs::rename(&directory, &destination)?;
                    }
                    let deletion = if is_trash || dry_run {
                        &directory
                    } else {
                        &destination
                    };
                    remove_retired_configuration(&mut context, deletion)?;
                    if is_trash {
                        reclaimed_paths.insert(directory);
                        reclaimed += 1;
                    } else {
                        removed += 1;
                    }
                }
            }
        }
    }
    ws.gctx().shell().status(
        "Incremental",
        format!("{removed} configurations eligible, {reclaimed} trash entries eligible, {retained} retained, {skipped} unrecognized, {busy} busy profiles"),
    )?;
    context.display_summary()
}

/// Keeps retired ownership until every payload file has been removed.
fn remove_retired_configuration(
    context: &mut CleanContext<'_>,
    directory: &Path,
) -> CargoResult<()> {
    for child in fs::read_dir(directory)? {
        let child = child?;
        if child.file_name() != MARKER {
            context.rm_rf(&child.path())?;
        }
    }
    if !context.dry_run {
        // CleanContext can report an inaccessible child without failing.
        // Preserve the marker if any payload remains to be retried.
        for child in fs::read_dir(directory)? {
            ensure!(
                child?.file_name() == MARKER,
                "incremental payload remains after cleanup: {}",
                directory.display()
            );
        }
    }
    context.rm_rf(&directory.join(MARKER))?;
    if !context.dry_run {
        fs::remove_dir(directory)?;
    }
    Ok(())
}

fn now() -> CargoResult<u64> {
    Ok(SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs())
}

fn regular_file(path: &Path) -> CargoResult<bool> {
    match fs::symlink_metadata(path) {
        Ok(metadata) => Ok(metadata.is_file()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(error.into()),
    }
}

fn plain_descendants(root: &Path, path: &Path) -> CargoResult<bool> {
    let mut current = root.to_path_buf();
    for component in std::iter::once(None).chain(path.strip_prefix(root)?.components().map(Some)) {
        if let Some(component) = component {
            ensure!(
                matches!(component, Component::Normal(_)),
                "invalid incremental directory path"
            );
            current.push(component);
        }
        match fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.is_dir() => {}
            Ok(_) => return Ok(false),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
            Err(error) => return Err(error.into()),
        }
    }
    Ok(true)
}

fn create_plain_descendants(root: &Path, path: &Path) -> CargoResult<()> {
    ensure!(
        plain_descendants(root, root)?,
        "incremental build root is not a plain directory"
    );
    let mut current = root.to_path_buf();
    for component in path.strip_prefix(root)?.components() {
        ensure!(
            matches!(component, Component::Normal(_)),
            "invalid incremental directory path"
        );
        current.push(component);
        match fs::create_dir(&current) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(error) => return Err(error.into()),
        }
        ensure!(
            fs::symlink_metadata(&current)?.is_dir(),
            "incremental directory contains a symlink or non-directory: {}",
            current.display()
        );
    }
    Ok(())
}

fn plain_tree(root: &Path) -> CargoResult<bool> {
    for entry in walkdir::WalkDir::new(root) {
        let entry = entry?;
        if !entry.file_type().is_dir() && !entry.file_type().is_file() {
            return Ok(false);
        }
    }
    Ok(true)
}

/// Visits only the existing host/profile and target/profile layouts.
fn profiles(root: &Path) -> CargoResult<Vec<PathBuf>> {
    if !plain_descendants(root, root)? {
        return Ok(Vec::new());
    }
    let mut profiles = Vec::new();
    for entry in fs::read_dir(root)? {
        let entry = entry?;
        if !entry.file_type()?.is_dir() {
            continue;
        }
        let path = entry.path();
        if regular_file(&path.join(".cargo-build-lock"))? {
            profiles.push(path);
        } else {
            for nested in fs::read_dir(&path)? {
                let nested = nested?;
                if nested.file_type()?.is_dir()
                    && regular_file(&nested.path().join(".cargo-build-lock"))?
                {
                    profiles.push(nested.path());
                }
            }
        }
    }
    profiles.sort_unstable_by(|left, right| {
        (left.parent() != Some(root))
            .cmp(&(right.parent() != Some(root)))
            .then_with(|| left.cmp(right))
    });
    Ok(profiles)
}

/// Uses an existing durable lock without Cargo's unsupported-lock fallback.
fn lock_profile(profile: &Path) -> CargoResult<Option<File>> {
    ensure!(
        !crate::core::compiler::layout::shared_registry_directory_is_nfs(profile)?,
        "incremental cleanup does not support NFS build directories"
    );
    let path = profile.join(".cargo-build-lock");
    ensure!(
        regular_file(&path)?,
        "build profile lock is not a regular file"
    );
    let mut options = fs::OpenOptions::new();
    options.read(true).write(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW);
    }
    let file = options.open(&path)?;
    match flock::try_lock_exclusive(&file) {
        Ok(()) => {}
        Err(TryLockError::WouldBlock) => return Ok(None),
        Err(TryLockError::Error(error)) => {
            return Err(error).context("incremental cleanup requires reliable profile locks");
        }
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        let opened = file.metadata()?;
        let current = fs::symlink_metadata(&path)?;
        ensure!(
            current.is_file() && current.dev() == opened.dev() && current.ino() == opened.ino(),
            "build profile lock changed while acquiring it"
        );
    }
    Ok(Some(file))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ownership_and_age_must_match() {
        let name = "example-0123456789abcdef";
        let record = Record::parse(
            br#"{"version":1,"unit":"example-0123456789abcdef","last_used":100}"#,
            name,
        )
        .unwrap();
        assert!(!record.expired(99, Duration::ZERO));
        assert!(!record.expired(109, Duration::from_secs(10)));
        assert!(record.expired(110, Duration::from_secs(10)));
        assert!(
            Record::parse(
                br#"{"version":3,"unit":"example-0123456789abcdef","last_used":100}"#,
                name
            )
            .is_none()
        );
        assert!(
            Record::parse(
                br#"{"version":1,"unit":"other-0123456789abcdef","last_used":100}"#,
                name
            )
            .is_none()
        );
        assert!(!valid_unit_name("../example-0123456789abcdef"));
        assert!(!valid_unit_name("example-1234"));
        assert!(valid_unit_name("café-0123456789abcdef"));
    }

    #[test]
    fn throttled_records_expire_after_the_latest_possible_use() {
        let record = Record {
            version: 2,
            unit: "example-0123456789abcdef".into(),
            last_used: 100,
        };
        assert!(!record.needs_refresh(99));
        assert!(!record.needs_refresh(100 + REFRESH_INTERVAL - 1));
        assert!(record.needs_refresh(100 + REFRESH_INTERVAL));
        assert!(!record.expired(99, Duration::ZERO));
        assert!(!record.expired(100 + REFRESH_INTERVAL - 1, Duration::ZERO));
        assert!(!record.expired(100 + REFRESH_INTERVAL + 9, Duration::from_secs(10)));
        assert!(record.expired(100 + REFRESH_INTERVAL + 10, Duration::from_secs(10)));
    }

    #[test]
    fn interrupted_enrollment_and_fresh_uses_do_not_rewrite_records() -> CargoResult<()> {
        let root = tempfile::tempdir()?;
        let managed = root.path().join(DIRECTORY);
        let unit = managed.join("café-0123456789abcdef");
        fs::create_dir_all(&unit)?;
        // A killed initial writer can leave its staging file beside the unit,
        // but the unit itself remains empty and can be enrolled on retry.
        fs::write(managed.join(".tmp-interrupted"), b"partial json")?;
        Tracker::default().record(root.path(), &unit)?;
        let marker = unit.join(MARKER);
        let before = fs::read(&marker)?;
        let modified = fs::metadata(&marker)?.modified()?;
        // A second writer must not need write permission when the lease is recent.
        let mut permissions = fs::metadata(&managed)?.permissions();
        let original = permissions.clone();
        permissions.set_readonly(true);
        fs::set_permissions(&managed, permissions)?;
        let result = Tracker::default().record(root.path(), &unit);
        fs::set_permissions(&managed, original)?;
        result?;
        assert_eq!(before, fs::read(&marker)?);
        assert_eq!(modified, fs::metadata(&marker)?.modified()?);
        Ok(())
    }

    #[cfg(unix)]
    #[test]
    fn directory_aliases_and_symlink_contents_are_rejected() -> CargoResult<()> {
        let root = tempfile::tempdir()?;
        let directory = root.path().join("plain");
        fs::create_dir(&directory)?;
        let alias = root.path().join("alias");
        std::os::unix::fs::symlink(&directory, &alias)?;
        assert!(!plain_descendants(root.path(), &alias)?);
        assert!(create_plain_descendants(root.path(), &alias.join("child")).is_err());
        assert!(!directory.join("child").exists());
        std::os::unix::fs::symlink(root.path(), directory.join("link"))?;
        assert!(!plain_tree(&directory)?);
        Ok(())
    }
}
