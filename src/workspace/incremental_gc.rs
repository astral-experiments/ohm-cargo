//! Opt-in ownership and expiry of workspace-private incremental configurations.

use std::fs::{self, File, TryLockError};
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use anyhow::{Context as _, ensure};
use serde::{Deserialize, Serialize};

use crate::CargoResult;
use crate::compiler::{BuildRunner, CompileMode, Layout, Unit};
use crate::ops::CleanContext;
use crate::util::flock;
use crate::workspace::Workspace;

pub const DIRECTORY: &str = "ohm-gc-v1";
const MARKER: &str = ".ohm-incremental-gc.json";

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
        (record.version == 1 && record.unit == unit && valid_unit_name(unit)).then_some(record)
    }

    fn expired(&self, now: u64, max_age: Duration) -> bool {
        now.checked_sub(self.last_used)
            .is_some_and(|age| Duration::from_secs(age) >= max_age)
    }
}

fn valid_unit_name(name: &str) -> bool {
    name.rsplit_once('-').is_some_and(|(name, hash)| {
        !name.is_empty()
            && name
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
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

/// Gives each Cargo configuration its own root without changing rustc's session protocol.
pub(crate) fn directory(build_runner: &BuildRunner<'_, '_>, unit: &Unit) -> PathBuf {
    let files = build_runner.files();
    let root = files.incremental_dir(unit);
    if !enabled(build_runner, unit) {
        return root.to_path_buf();
    }
    root.join(DIRECTORY).join(format!(
        "{}-{}",
        unit.target.crate_name(),
        files.metadata(unit).unit_id()
    ))
}

/// Records graph use, including fresh units, while the build's profile lease is held.
pub(crate) fn record_use(build_runner: &BuildRunner<'_, '_>, unit: &Unit) -> CargoResult<()> {
    if !enabled(build_runner, unit) {
        return Ok(());
    }
    let layout = build_runner.files().layout(unit.kind).build_dir();
    let root = build_runner.bcx.ws.canonical_build_path(layout.root());
    let directory = root.join(directory(build_runner, unit).strip_prefix(layout.root())?);
    create_plain_descendants(&root, &directory)?;
    let name = directory.file_name().unwrap().to_str().unwrap();
    ensure!(
        valid_unit_name(name),
        "invalid incremental configuration name"
    );
    let marker = directory.join(MARKER);
    match fs::symlink_metadata(&marker) {
        Ok(metadata) => {
            ensure!(
                metadata.is_file(),
                "incremental ownership marker is not a regular file"
            );
            ensure!(
                Record::parse(&fs::read(&marker)?, name).is_some(),
                "invalid incremental ownership marker: {}",
                marker.display()
            );
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
        version: 1,
        unit: name.to_owned(),
        last_used: now()?,
    };
    // Persist replaces the marker itself rather than following a marker symlink.
    let mut temporary = tempfile::NamedTempFile::new_in(&directory)?;
    temporary.write_all(&serde_json::to_vec(&record)?)?;
    temporary.persist(&marker)?;
    Ok(())
}

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
    let namespace = Layout::shared_workspace_namespace(ws);
    let mut context = CleanContext::new(ws.gctx());
    context.dry_run = dry_run;
    let now = now()?;
    let mut removed = 0;
    let mut retained = 0;
    let mut skipped = 0;
    let mut busy = 0;
    for profile in profiles(&build_root)? {
        let Some(_guard) = lock_profile(&profile)? else {
            busy += 1;
            continue;
        };
        let managed = profile.join("incremental").join(&namespace).join(DIRECTORY);
        if !plain_descendants(&profile, &managed)? {
            continue;
        }
        for entry in fs::read_dir(&managed)? {
            let entry = entry?;
            let directory = entry.path();
            let Some(name) = entry.file_name().to_str().map(str::to_owned) else {
                skipped += 1;
                continue;
            };
            let marker = directory.join(MARKER);
            if !entry.file_type()?.is_dir() || !regular_file(&marker)? {
                skipped += 1;
                continue;
            }
            let Some(record) = Record::parse(&fs::read(&marker)?, &name) else {
                skipped += 1;
                continue;
            };
            if !record.expired(now, max_age) {
                retained += 1;
                continue;
            }
            if !plain_tree(&directory)? {
                skipped += 1;
                continue;
            }
            ws.gctx()
                .shell()
                .status(if dry_run { "Would expire" } else { "Expiring" }, &name)?;
            // Keep ownership until every data file has gone so an interrupted
            // deletion can be retried without adopting an unknown directory.
            for child in fs::read_dir(&directory)? {
                let child = child?;
                if child.file_name() != MARKER {
                    context.rm_rf(&child.path())?;
                }
            }
            if !dry_run {
                // CleanContext can report an inaccessible child without failing.
                // Do not discard ownership if any payload remains to be retried.
                for child in fs::read_dir(&directory)? {
                    ensure!(
                        child?.file_name() == MARKER,
                        "incremental payload remains after cleanup: {}",
                        directory.display()
                    );
                }
            }
            context.rm_rf(&marker)?;
            if !dry_run {
                fs::remove_dir(&directory)?;
            }
            removed += 1;
        }
    }
    ws.gctx().shell().status(
        "Incremental",
        format!("{removed} configurations eligible, {retained} retained, {skipped} unrecognized, {busy} busy profiles"),
    )?;
    context.display_summary()
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
        !crate::compiler::layout::shared_registry_directory_is_nfs(profile)?,
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
                br#"{"version":2,"unit":"example-0123456789abcdef","last_used":100}"#,
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
