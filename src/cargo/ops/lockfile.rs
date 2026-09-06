use std::io::prelude::*;
use std::path::Path;

use crate::core::resolver::encode::into_resolve;
use crate::core::{Resolve, ResolveVersion, Workspace};
use crate::util::errors::CargoResult;
use crate::util::flock::FileOpenError;
use crate::util::{FileLock, Filesystem, GlobalContext};

use anyhow::Context as _;
use cargo_util_schemas::lockfile::TomlLockfile;

pub const LOCKFILE_NAME: &str = "Cargo.lock";

#[tracing::instrument(skip_all)]
pub fn load_pkg_lockfile(ws: &Workspace<'_>) -> CargoResult<Option<Resolve>> {
    load_pkg_lockfile_with(ws, |resolve, _contents| Ok(resolve))
}

/// Inspects a parsed lockfile without releasing its shared filesystem lock.
pub(super) fn load_pkg_lockfile_with<T>(
    ws: &Workspace<'_>,
    action: impl FnOnce(Resolve, &str) -> CargoResult<T>,
) -> CargoResult<Option<T>> {
    with_pkg_lockfile(ws, |contents, path| {
        let resolve = (|| -> CargoResult<Resolve> {
            let lockfile: TomlLockfile = toml::from_str(contents)?;
            into_resolve(lockfile, contents, ws)
        })()
        .with_context(|| format!("failed to parse lock file at: {}", path.display()))?;

        action(resolve, contents)
    })
}

/// Runs an operation on one consistent, shared-locked lockfile snapshot.
pub(super) fn with_pkg_lockfile<T>(
    ws: &Workspace<'_>,
    action: impl FnOnce(&str, &Path) -> CargoResult<T>,
) -> CargoResult<Option<T>> {
    let lock_root = ws.lock_root();
    let path = lock_root.as_path_unlocked().join(LOCKFILE_NAME);
    if !ws.gctx().files().exists(&path) {
        if let Some(inputs) = ws.gctx().session_inputs() {
            inputs.observe_missing_file(&path);
        }
        return Ok(None);
    }

    let mut f = open_locked_lockfile(&lock_root, ws.gctx())?;

    let contents = read_locked_lockfile(&mut f, ws.gctx())
        .with_context(|| format!("failed to read file: {}", f.path().display()))?;

    action(&contents, f.path()).map(Some)
}

/// Record filesystem open failures separately from advisory lock failures.
fn open_locked_lockfile(lock_root: &Filesystem, gctx: &GlobalContext) -> CargoResult<FileLock> {
    lock_root
        .open_ro_shared(LOCKFILE_NAME, gctx, "Cargo.lock file")
        .inspect_err(|error| {
            let Some(inputs) = gctx.session_inputs() else {
                return;
            };
            let path = lock_root.as_path_unlocked().join(LOCKFILE_NAME);
            if error.is::<FileOpenError>() {
                if let Some(error) = error.downcast_ref::<std::io::Error>() {
                    inputs.observe_file_error(&path, error.kind());
                    return;
                }
            }
            inputs.require_fresh(format!(
                "could not acquire lockfile {}: {error}",
                path.display()
            ));
        })
}

/// Observe the locked bytes before decoding, so invalid UTF-8 remains an input.
fn read_locked_lockfile(file: &mut FileLock, gctx: &GlobalContext) -> std::io::Result<String> {
    let mut contents = Vec::new();
    let read = file.read_to_end(&mut contents);
    if let Some(inputs) = gctx.session_inputs() {
        match &read {
            Ok(_) => inputs.observe_file(file.path(), &contents),
            Err(error) => inputs.observe_file_error(file.path(), error.kind()),
        }
    }
    read?;
    String::from_utf8(contents).map_err(|_| {
        std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "stream did not contain valid UTF-8",
        )
    })
}

/// Checks whether a lockfile snapshot encodes exactly the provided resolution.
pub(super) fn lockfile_matches_resolve(contents: &str, resolve: &Resolve) -> bool {
    contents
        .lines()
        .eq(serialize_resolve(resolve, Some(contents)).lines())
}

/// Generate a toml String of Cargo.lock from a Resolve.
pub fn resolve_to_string(ws: &Workspace<'_>, resolve: &Resolve) -> CargoResult<String> {
    let (_orig, out, _lock_root) = resolve_to_string_orig(ws, resolve);
    Ok(out)
}

/// Ensure the resolve result is written to fisk
///
/// Returns `true` if the lockfile changed
#[tracing::instrument(skip_all)]
pub fn write_pkg_lockfile(ws: &Workspace<'_>, resolve: &mut Resolve) -> CargoResult<bool> {
    let (orig, mut out, lock_root) = resolve_to_string_orig(ws, resolve);

    // If the lock file contents haven't changed so don't rewrite it. This is
    // helpful on read-only filesystems.
    if let Some(orig) = &orig {
        if are_equal_lockfiles(orig, &out, ws) {
            return Ok(false);
        }
    }

    if let Some(locked_flag) = ws.gctx().locked_flag() {
        let lockfile_path = lock_root.as_path_unlocked().join(LOCKFILE_NAME);
        let action = if ws.gctx().files().exists(&lockfile_path) {
            "update"
        } else {
            "create"
        };
        let lockfile_path = lockfile_path.display();
        anyhow::bail!(
            "cannot {action} the lock file {lockfile_path} because {locked_flag} was passed to prevent this\n\
             help: to generate the lock file without accessing the network, \
             remove the {locked_flag} flag and use --offline instead."
        );
    }

    // While we're updating the lock file anyway go ahead and update its
    // encoding to whatever the latest default is. That way we can slowly roll
    // out lock file updates as they're otherwise already updated, and changes
    // which don't touch dependencies won't seemingly spuriously update the lock
    // file.
    let default_version = ResolveVersion::with_rust_version(ws.lowest_rust_version());
    let current_version = resolve.version();
    let next_lockfile_bump = ws.gctx().cli_unstable().next_lockfile_bump;
    tracing::debug!("lockfile - current: {current_version:?}, default: {default_version:?}");

    if current_version < default_version {
        resolve.set_version(default_version);
        out = serialize_resolve(resolve, orig.as_deref());
    } else if current_version > ResolveVersion::max_stable() && !next_lockfile_bump {
        // The next version hasn't yet stabilized.
        anyhow::bail!("lock file version `{current_version:?}` requires `-Znext-lockfile-bump`")
    }

    if !lock_root.as_path_unlocked().exists() {
        lock_root.create_dir()?;
    }

    // Ok, if that didn't work just write it out
    lock_root
        .open_rw_exclusive_create(LOCKFILE_NAME, ws.gctx(), "Cargo.lock file")
        .and_then(|mut f| {
            f.file().set_len(0)?;
            f.write_all(out.as_bytes())?;
            if let Some(inputs) = ws.gctx().session_inputs() {
                inputs.publish_file(f.path(), out.as_bytes());
            }
            Ok(())
        })
        .with_context(|| {
            format!(
                "failed to write {}",
                lock_root.as_path_unlocked().join(LOCKFILE_NAME).display()
            )
        })?;
    Ok(true)
}

fn resolve_to_string_orig(
    ws: &Workspace<'_>,
    resolve: &Resolve,
) -> (Option<String>, String, Filesystem) {
    // Load the original lock file if it exists.
    let lock_root = ws.lock_root();
    let orig = open_locked_lockfile(&lock_root, ws.gctx());
    let orig = orig.and_then(|mut f| Ok(read_locked_lockfile(&mut f, ws.gctx())?));
    let out = serialize_resolve(resolve, orig.as_deref().ok());
    (orig.ok(), out, lock_root)
}

#[tracing::instrument(skip_all)]
fn serialize_resolve(resolve: &Resolve, orig: Option<&str>) -> String {
    let toml = toml::Table::try_from(resolve).unwrap();

    let mut out = String::new();

    // At the start of the file we notify the reader that the file is generated.
    // Specifically Phabricator ignores files containing "@generated", so we use that.
    let marker_line = "# This file is automatically @generated by Cargo.";
    let extra_line = "# It is not intended for manual editing.";
    out.push_str(marker_line);
    out.push('\n');
    out.push_str(extra_line);
    out.push('\n');
    // and preserve any other top comments
    if let Some(orig) = orig {
        let mut comments = orig.lines().take_while(|line| line.starts_with('#'));
        if let Some(first) = comments.next() {
            if first != marker_line {
                out.push_str(first);
                out.push('\n');
            }
            if let Some(second) = comments.next() {
                if second != extra_line {
                    out.push_str(second);
                    out.push('\n');
                }
                for line in comments {
                    out.push_str(line);
                    out.push('\n');
                }
            }
        }
    }

    if let Some(version) = toml.get("version") {
        out.push_str(&format!("version = {}\n\n", version));
    }

    let deps = toml["package"].as_array().unwrap();
    for dep in deps {
        let dep = dep.as_table().unwrap();

        out.push_str("[[package]]\n");
        emit_package(dep, &mut out);
    }

    if let Some(patch) = toml.get("patch") {
        let list = patch["unused"].as_array().unwrap();
        for entry in list {
            out.push_str("[[patch.unused]]\n");
            emit_package(entry.as_table().unwrap(), &mut out);
            out.push('\n');
        }
    }

    if let Some(meta) = toml.get("metadata") {
        // 1. We need to ensure we print the entire tree, not just the direct members of `metadata`
        //    (which `toml_edit::Table::to_string` only shows)
        // 2. We need to ensure all children tables have `metadata.` prefix
        let meta_table = meta
            .as_table()
            .expect("validation ensures this is a table")
            .clone();
        let mut meta_doc = toml::Table::new();
        meta_doc.insert("metadata".to_owned(), toml::Value::Table(meta_table));

        out.push_str(&meta_doc.to_string());
    }

    // Historical versions of Cargo in the old format accidentally left trailing
    // blank newlines at the end of files, so we just leave that as-is. For all
    // encodings going forward, though, we want to be sure that our encoded lock
    // file doesn't contain any trailing newlines so trim out the extra if
    // necessary.
    if resolve.version() >= ResolveVersion::V2 {
        while out.ends_with("\n\n") {
            out.pop();
        }
    }
    out
}

#[tracing::instrument(skip_all)]
fn are_equal_lockfiles(orig: &str, current: &str, ws: &Workspace<'_>) -> bool {
    // Avoid deserializing lockfiles when their contents already match.
    if orig.lines().eq(current.lines()) {
        return true;
    }

    // If we want to try and avoid updating the lock file, parse both and
    // compare them; since this is somewhat expensive, don't do it in the
    // common case where we can update lock files.
    if !ws.gctx().lock_update_allowed() {
        let res: CargoResult<bool> = (|| {
            let old: TomlLockfile = toml::from_str(orig)?;
            let new: TomlLockfile = toml::from_str(current)?;
            Ok(into_resolve(old, orig, ws)? == into_resolve(new, current, ws)?)
        })();
        if let Ok(true) = res {
            return true;
        }
    }

    false
}

fn emit_package(dep: &toml::Table, out: &mut String) {
    out.push_str(&format!("name = {}\n", &dep["name"]));
    out.push_str(&format!("version = {}\n", &dep["version"]));

    if dep.contains_key("source") {
        out.push_str(&format!("source = {}\n", &dep["source"]));
    }
    if dep.contains_key("checksum") {
        out.push_str(&format!("checksum = {}\n", &dep["checksum"]));
    }

    if let Some(s) = dep.get("dependencies") {
        let slice = s.as_array().unwrap();

        if !slice.is_empty() {
            out.push_str("dependencies = [\n");

            for child in slice.iter() {
                out.push_str(&format!(" {},\n", child));
            }

            out.push_str("]\n");
        }
        out.push('\n');
    } else if dep.contains_key("replace") {
        out.push_str(&format!("replace = {}\n\n", &dep["replace"]));
    }
}
