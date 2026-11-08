//! Creates independent Git worktrees and imports a completed local build snapshot.

use std::fs;
use std::io;
use std::path::{Component, Path, PathBuf};

use anyhow::{Context as _, bail, ensure};
use cargo_util::ProcessBuilder;
use filetime::FileTime;

use crate::CargoResult;
use crate::compiler::Layout;
use crate::compiler::fingerprint::dep_info::{DepInfoPathType, EncodedDepInfo};
use crate::compiler::fingerprint::{OHM_WORKTREE_SCRIPT_RERUN, OHM_WORKTREE_SCRIPT_RESULT};
use crate::compiler::layout::PrivateBuildLease;
use crate::util::file_clone::try_clone;
use crate::util::{Filesystem, GlobalContext};
use crate::workspace::Workspace;
use crate::workspace::features::OhmProcMacroTrust;

/// Git checkout and destination storage for a new, independently writable worktree.
pub struct WorktreeOptions {
    pub manifest_path: PathBuf,
    pub path: PathBuf,
    pub branch: Option<String>,
    pub detach: bool,
    pub commit: Option<String>,
    pub target_dir: Option<PathBuf>,
}

/// Creates a Git worktree, then seeds private build state for Cargo to validate.
///
/// Importing never marks a compilation fresh: source checksums, configuration,
/// dependencies, and tracked environment still decide whether a result is reusable.
/// The final target directory is populated by the recipient's first Cargo build,
/// after that validation, rather than exposing an unvalidated donor executable.
pub fn worktree_add(gctx: &GlobalContext, opts: &WorktreeOptions) -> CargoResult<()> {
    let donor = Workspace::new(&opts.manifest_path, gctx)?;
    let mut git = ProcessBuilder::new("git");
    // A Git hook can export the calling repository's location and object database.
    for variable in [
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ] {
        git.env_remove(variable);
    }
    // Start both Git commands at the workspace. With core.worktree, Git can
    // report a root from which it would discover an enclosing repository.
    git.cwd(donor.root())
        .env_remove("GIT_CEILING_DIRECTORIES")
        .env("GIT_DISCOVERY_ACROSS_FILESYSTEM", "1");
    let output = git
        .clone()
        .args(&["rev-parse", "--show-toplevel"])
        .exec_with_output()
        .context("`cargo worktree` requires a Git working tree")?;
    // Drop Git's record terminator, preserving any newline in the directory name.
    let root = output.stdout.strip_suffix(b"\n").unwrap_or(&output.stdout);
    let git_root = cargo_util::paths::bytes2path(root)?.canonicalize()?;
    let destination = resolve_parent_dirs(&opts.path, gctx.cwd())?;
    ensure_absent(&destination, "worktree destination")?;
    ensure!(
        !destination.starts_with(&git_root) && !git_root.starts_with(&destination),
        "the new worktree must be outside the source worktree"
    );

    let target = opts
        .target_dir
        .as_deref()
        .map(|path| resolve_parent_dirs(path, gctx.cwd()))
        .transpose()?;
    if let Some(target) = &target {
        ensure_absent(target, "destination target directory")?;
        ensure!(
            !destination.starts_with(target),
            "destination target directory must not contain the new worktree"
        );
    }
    for protected in [
        git_root.clone(),
        donor.target_dir().into_path_unlocked(),
        donor.build_dir().into_path_unlocked(),
        donor.configured_build_dir().into_path_unlocked(),
    ] {
        let protected = physical_storage_path(&protected, gctx.cwd())?;
        ensure!(
            !destination.starts_with(&protected) && !protected.starts_with(&destination),
            "worktree destination overlaps source storage: {}",
            protected.display()
        );
        if let Some(target) = &target {
            ensure!(
                !target.starts_with(&protected) && !protected.starts_with(target),
                "destination target directory overlaps source storage: {}",
                protected.display()
            );
        }
    }

    git.args(&["worktree", "add"]);
    if let Some(branch) = &opts.branch {
        git.arg("-b").arg(branch);
    }
    if opts.detach {
        git.arg("--detach");
    }
    git.arg("--").arg(&destination);
    // Keep an omitted commit unset so Git can infer a branch from the destination.
    if let Some(commit) = &opts.commit {
        git.arg(commit);
    }
    git.exec()?;

    let seed = || -> CargoResult<(Seeded, PathBuf)> {
        // The selected commit may itself contain a target directory. Do not adopt it.
        let manifest = manifest_in_worktree(donor.root_manifest(), &git_root, &destination)?;
        ensure_plain_descendants(&destination, manifest.parent().unwrap())?;
        let target = target.unwrap_or_else(|| manifest.parent().unwrap().join("target"));
        ensure!(
            donor.canonical_build_path(&target) == target,
            "destination target directory changed through a checked-out symlink"
        );
        ensure_absent(&target, "destination target directory")?;
        let mut recipient = Workspace::new(&manifest, gctx)?;
        recipient.set_target_dir(Filesystem::new(target.clone()));
        if gctx.cli_unstable().ohm_worktree_seeds() && donor.shared_registry_cache_enabled() {
            return Ok((seed_shared_build(&donor, &recipient)?, target));
        }
        #[cfg(any(target_os = "linux", target_os = "macos"))]
        register_created_target(&recipient, PrivateBuildLease::acquire(&recipient, false))?;
        Ok((Seeded::default(), target))
    };
    let (seeded, target) = seed().with_context(|| {
        format!(
            "worktree was created at {}, but build-state seeding failed",
            destination.display()
        )
    })?;
    if seeded.files == 0 {
        gctx.shell().status(
            "Created",
            format!(
                "{} (no compatible build snapshot seeded)",
                destination.display()
            ),
        )?;
    } else {
        gctx.shell().status(
            "Seeded",
            format!(
                "{} files ({} bytes, {} reflinked files) for {}; the next build validates reuse",
                seeded.files,
                seeded.bytes,
                seeded.reflinked_files,
                destination.display()
            ),
        )?;
    }
    if seeded.skipped_profiles != 0 {
        gctx.shell().status(
            "Skipped",
            format!(
                "{} unprepared or unsupported build profiles",
                seeded.skipped_profiles
            ),
        )?;
    }
    if seeded.unclonable_profiles != 0 {
        gctx.shell().status(
            "Skipped",
            format!(
                "{} build profiles without copy-on-write support",
                seeded.unclonable_profiles
            ),
        )?;
    }
    gctx.shell().status("Target", target.display())?;
    Ok(())
}

/// Maps the package directory into the new checkout and keeps the manifest's final filename.
fn manifest_in_worktree(
    manifest: &Path,
    git_root: &Path,
    destination: &Path,
) -> CargoResult<PathBuf> {
    let mut recipient: Option<PathBuf> = None;
    let parents = manifest.parent().unwrap().ancestors().collect::<Vec<_>>();
    for directory in parents.into_iter().rev() {
        let path = if let Some(parent) = &recipient {
            let path = parent.join(directory.iter().next_back().unwrap());
            // An alias local to the donor may be absent in a fresh Git checkout.
            if directory.is_symlink()
                && path
                    .symlink_metadata()
                    .is_err_and(|error| error.kind() == io::ErrorKind::NotFound)
            {
                destination.join(directory.canonicalize()?.strip_prefix(git_root)?)
            } else {
                path
            }
        } else {
            // The caller can reach the Git repository through an external directory alias.
            let physical = directory.canonicalize()?;
            let Ok(relative) = physical.strip_prefix(git_root) else {
                continue;
            };
            destination.join(relative)
        };
        let physical = if path.is_symlink() {
            path.canonicalize()?
        } else {
            // A donor-only alias can live inside a directory Git did not copy.
            physical_storage_path(&path, destination)?
        };
        ensure!(
            physical.starts_with(destination),
            "package directory `{}` is outside the new worktree `{}`",
            physical.display(),
            destination.display()
        );
        recipient = Some(physical);
    }
    let directory = recipient.context("workspace manifest is outside the source repository")?;
    Ok(directory.join(manifest.file_name().unwrap()))
}

#[derive(Default)]
struct Seeded {
    files: u64,
    bytes: u64,
    reflinked_files: u64,
    skipped_profiles: usize,
    unclonable_profiles: usize,
}

/// Clones private state between target directories while holding their local guards.
///
/// Consumer leases protect legacy and scoped registry references without stopping
/// builds in other worktrees. The new recipient cannot be another seeding operation's donor.
fn seed_shared_build(donor: &Workspace<'_>, recipient: &Workspace<'_>) -> CargoResult<Seeded> {
    let shared_root = donor.canonical_build_path(donor.configured_build_dir().as_path_unlocked());
    ensure!(
        shared_root
            == recipient.canonical_build_path(recipient.configured_build_dir().as_path_unlocked()),
        "worktree seeding requires the same separate build directory in both worktrees"
    );
    let _consumer = crate::workspace::build_cache_gc_lease::ConsumerLease::acquire(&shared_root)?;
    let _donor_guard = PrivateBuildLease::acquire(donor, true)?;
    let _recipient_guard = PrivateBuildLease::acquire(recipient, true)?;
    let source_root = donor.canonical_build_path(donor.build_dir().as_path_unlocked());
    let destination_root = recipient.canonical_build_path(recipient.build_dir().as_path_unlocked());
    let source_namespace = Layout::shared_workspace_namespace(donor);
    let destination_namespace = Layout::shared_workspace_namespace(recipient);
    ensure!(
        source_namespace != destination_namespace,
        "worktree build namespaces must differ"
    );
    let profiles = build_profiles(&source_root)?;
    let mut seeded = Seeded::default();
    if cfg!(any(target_os = "linux", target_os = "macos"))
        && let Err(error) =
            crate::workspace::build_cache_gc_roots::register_root(recipient.gctx(), &shared_root)
    {
        tracing::debug!(?error, "could not register shared build root");
    }
    for profile in &profiles {
        ensure_plain_descendants(&source_root, profile)?;
        ensure_regular(&profile.join(".cargo-build-lock"))?;
        let workspaces = profile.join("build/workspaces");
        let source = workspaces.join(&source_namespace);
        if !plain_directory(&source)? {
            continue;
        }
        ensure_plain_descendants(profile, &source)?;
        if !seed_policy_allows(&source, donor.gctx().cli_unstable().ohm_proc_macro_trust)? {
            seeded.skipped_profiles += 1;
            continue;
        }
        let _context_leases =
            crate::workspace::build_cache_gc_lease::seed_leases(&shared_root, &source)?;
        let _context_uses = if cfg!(any(target_os = "linux", target_os = "macos")) {
            crate::workspace::build_cache_gc::record_seed_contexts(&shared_root, &source)
                .unwrap_or_else(|error| {
                    tracing::debug!(?error, "could not record seeded context usage");
                    Vec::new()
                })
        } else {
            Vec::new()
        };
        if let Some(profile_seeded) = seed_profile(
            &source_root,
            &destination_root,
            profile.strip_prefix(&source_root)?,
            &source_namespace,
            &destination_namespace,
            &try_clone,
        )? {
            seeded.files += profile_seeded.files;
            seeded.bytes += profile_seeded.bytes;
            seeded.reflinked_files += profile_seeded.reflinked_files;
        } else {
            seeded.unclonable_profiles += 1;
        }
    }
    #[cfg(any(target_os = "linux", target_os = "macos"))]
    register_created_target(recipient, Ok(_recipient_guard))?;
    Ok(seeded)
}

#[cfg(any(target_os = "linux", target_os = "macos"))]
fn register_created_target(
    ws: &Workspace<'_>,
    lease: CargoResult<PrivateBuildLease>,
) -> CargoResult<()> {
    if let Err(error) = lease.and_then(|lease| {
        crate::workspace::build_cache_gc::worktrees::registry::register_build(
            ws,
            &Layout::shared_workspace_namespace(ws),
            lease.file(),
        )
    }) {
        ws.gctx().shell().warn(format!(
            "could not register {} for private build-cache cleanup ({error:#})",
            ws.target_dir().as_path_unlocked().display()
        ))?;
    }
    Ok(())
}

/// Publishes a complete profile, or discards its entire stage when cloning is unavailable.
fn seed_profile(
    source_root: &Path,
    destination_root: &Path,
    profile: &Path,
    source_namespace: &str,
    destination_namespace: &str,
    clone_file: &impl Fn(&Path, &Path) -> CargoResult<bool>,
) -> CargoResult<Option<Seeded>> {
    let source_profile = source_root.join(profile);
    let destination_profile = destination_root.join(profile);
    let workspaces = destination_profile.join("build/workspaces");
    cargo_util::paths::create_dir_all(&workspaces)?;
    ensure_plain_descendants(destination_root, &workspaces)?;
    fs::OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(false)
        .open(destination_profile.join(".cargo-build-lock"))?;
    let source = source_profile
        .join("build/workspaces")
        .join(source_namespace);
    let destination = workspaces.join(destination_namespace);
    ensure_absent(&destination, "destination build namespace")?;
    let incremental_source = source_profile.join("incremental").join(source_namespace);
    let incremental = destination_profile.join("incremental");
    let incremental_destination = incremental.join(destination_namespace);
    ensure_absent(
        &incremental_destination,
        "destination incremental namespace",
    )?;
    let old_prefix = source.strip_prefix(source_root)?;
    let new_prefix = destination.strip_prefix(destination_root)?;

    // Stage both trees before publishing either. A failed copy never exposes
    // a partly copied fingerprint tree to the recipient.
    let stage = tempfile::Builder::new()
        .prefix(".ohm-worktree-seed-")
        .tempdir_in(&workspaces)?;
    let staged_build = stage.path().join("build");
    let mut seeded = Seeded::default();
    if !clone_tree(
        &source,
        &staged_build,
        old_prefix,
        new_prefix,
        false,
        &mut seeded,
        clone_file,
    )? {
        stage.close()?;
        return Ok(None);
    }
    let staged_incremental = stage.path().join("incremental");
    let has_incremental = plain_directory(&incremental_source)?;
    if has_incremental {
        ensure_plain_descendants(&source_profile, &incremental_source)?;
        cargo_util::paths::create_dir_all(&incremental)?;
        ensure_plain_descendants(destination_root, &incremental)?;
        if !clone_tree(
            &incremental_source,
            &staged_incremental,
            old_prefix,
            new_prefix,
            true,
            &mut seeded,
            clone_file,
        )? {
            stage.close()?;
            return Ok(None);
        }
        fs::rename(&staged_incremental, &incremental_destination)?;
    }
    fs::rename(&staged_build, &destination)?;
    Ok(Some(seeded))
}

/// Enumerates the known host/profile and target/profile layouts without following links.
fn build_profiles(root: &Path) -> CargoResult<Vec<PathBuf>> {
    if !plain_directory(root)? {
        return Ok(Vec::new());
    }
    let mut profiles = Vec::new();
    for entry in fs::read_dir(root)? {
        let entry = entry?;
        if !entry.file_type()?.is_dir() {
            continue;
        }
        let path = entry.path();
        if path.join(".cargo-build-lock").try_exists()? {
            profiles.push(path);
            continue;
        }
        for nested in fs::read_dir(&path)? {
            let nested = nested?;
            if nested.file_type()?.is_dir()
                && nested.path().join(".cargo-build-lock").try_exists()?
            {
                profiles.push(nested.path());
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

/// Clones regular snapshot files into private inodes, retaining their original mtimes.
///
/// Returns false if a file cannot be cloned; there is no byte-copy fallback.
/// Mutable hardlinks, active compiler sessions, and path-bearing relink recipes
/// are not imported. Prepared build-script results are copied for comparison,
/// and the recipient must rerun each script before reusing its consumers.
fn clone_tree(
    source: &Path,
    destination: &Path,
    old_prefix: &Path,
    new_prefix: &Path,
    incremental: bool,
    seeded: &mut Seeded,
    clone_file: &impl Fn(&Path, &Path) -> CargoResult<bool>,
) -> CargoResult<bool> {
    fs::create_dir(destination)?;
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let name = entry.file_name();
        let text = name.to_string_lossy();
        let ty = entry.file_type()?;
        if text.ends_with("-working")
            || text == crate::compiler::OHM_WORKTREE_CLIPPY_DIRECTORY
            || text == ".cargo-workspace-lock"
            || text == ".lock"
            || text.ends_with(".rlink")
            || text.contains(".rlink-")
        {
            continue;
        }
        let source = entry.path();
        let destination = destination.join(&name);
        if ty.is_dir() {
            let build_script = has_build_script_execution(&source)?;
            if build_script && !has_build_script_result(&source)? {
                continue;
            }
            if !clone_tree(
                &source,
                &destination,
                old_prefix,
                new_prefix,
                incremental,
                seeded,
                clone_file,
            )? {
                return Ok(false);
            }
            if build_script {
                // A snapshot is evidence for comparing the next execution,
                // never permission to skip a script in a different checkout.
                fs::write(
                    destination
                        .join("fingerprint")
                        .join(OHM_WORKTREE_SCRIPT_RERUN),
                    b"",
                )?;
                seeded.files += 1;
            }
        } else if ty.is_file() {
            let metadata = entry.metadata()?;
            if incremental && text.ends_with(".lock") {
                // A finalized session needs a lock file, but never its donor's inode.
                fs::File::create(&destination)?;
            } else {
                if !clone_file(&source, &destination)? {
                    return Ok(false);
                }
                fs::set_permissions(&destination, metadata.permissions())?;
                seeded.bytes += metadata.len();
                seeded.reflinked_files += 1;
                if text.starts_with("dep-")
                    && source
                        .parent()
                        .is_some_and(|parent| parent.ends_with("fingerprint"))
                {
                    if !relocate_dep_info(&destination, old_prefix, new_prefix)? {
                        seeded.bytes -= metadata.len();
                        seeded.reflinked_files -= 1;
                        continue;
                    }
                }
            }
            filetime::set_file_times(
                &destination,
                FileTime::from_last_access_time(&metadata),
                FileTime::from_last_modification_time(&metadata),
            )?;
            seeded.files += 1;
        }
        // Unknown files and symlinks are omitted. Missing outputs force ordinary
        // recompilation; following a link could copy or mutate unrelated storage.
    }
    Ok(true)
}

fn has_build_script_execution(unit: &Path) -> CargoResult<bool> {
    let fingerprint = unit.join("fingerprint");
    if !plain_directory(&fingerprint)? {
        return Ok(false);
    }
    for entry in fs::read_dir(fingerprint)? {
        if entry?
            .file_name()
            .to_string_lossy()
            .starts_with("run-build-script-")
        {
            return Ok(true);
        }
    }
    Ok(false)
}

fn has_build_script_result(unit: &Path) -> CargoResult<bool> {
    match fs::symlink_metadata(unit.join("fingerprint").join(OHM_WORKTREE_SCRIPT_RESULT)) {
        Ok(metadata) => Ok(metadata.file_type().is_file()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(error.into()),
    }
}

/// Rebases generated-file dependencies into the recipient's private namespace.
fn relocate_dep_info(path: &Path, old_prefix: &Path, new_prefix: &Path) -> CargoResult<bool> {
    let Some(mut info) = EncodedDepInfo::parse(&fs::read(path)?) else {
        // Unknown formats cannot certify source contents in the recipient.
        fs::remove_file(path)?;
        return Ok(false);
    };
    // Rewrite older observer records as incomplete even when no paths need rebasing.
    let mut changed = info.observer.is_some();
    for (kind, path, _) in &mut info.files {
        if matches!(
            kind,
            DepInfoPathType::BuildRootRelative | DepInfoPathType::RegistryAbsolute
        ) && let Ok(relative) = path.strip_prefix(old_prefix)
        {
            *path = new_prefix.join(relative);
            changed = true;
        }
    }
    if changed {
        fs::write(path, info.serialize()?)?;
    }
    Ok(true)
}

/// Keeps snapshot traversal within the profile whose build lock we hold.
fn ensure_plain_descendants(root: &Path, path: &Path) -> CargoResult<()> {
    let relative = path.strip_prefix(root)?;
    let mut current = root.to_path_buf();
    ensure!(
        plain_directory(&current)?,
        "snapshot root is not a plain directory: {}",
        current.display()
    );
    for component in relative.components() {
        current.push(component);
        ensure!(
            plain_directory(&current)?,
            "snapshot path is not a plain directory: {}",
            current.display()
        );
    }
    Ok(())
}

/// Resolves symlinks before applying each parent component, including after missing directories.
fn physical_storage_path(path: &Path, cwd: &Path) -> CargoResult<PathBuf> {
    let realpath = |path: &Path| {
        path.canonicalize().map_or_else(
            |_| gix::path::realpath_opts(path, cwd, gix::path::realpath::MAX_SYMLINKS),
            Ok,
        )
    };
    let mut physical = PathBuf::new();
    for component in cwd.join(path).components() {
        if component == Component::ParentDir {
            physical = realpath(&physical)?;
            physical.pop();
        } else {
            physical.push(component);
        }
    }
    Ok(realpath(&physical)?)
}

/// Resolves the parent directories and preserves the final directory entry.
fn resolve_parent_dirs(path: &Path, cwd: &Path) -> CargoResult<PathBuf> {
    let path = cwd.join(path);
    match (path.parent(), path.file_name()) {
        (Some(parent), Some(name)) => Ok(physical_storage_path(parent, cwd)?.join(name)),
        _ => physical_storage_path(&path, cwd),
    }
}

fn ensure_absent(path: &Path, description: &str) -> CargoResult<()> {
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
        Ok(_) => bail!("{description} already exists: {}", path.display()),
    }
}

/// Checks the donor's retained history against this import's explicit trust policy.
fn seed_policy_allows(namespace: &Path, proc_macro_trust: OhmProcMacroTrust) -> CargoResult<bool> {
    let marker = namespace.join(crate::compiler::OHM_WORKTREE_SEED_MARKER);
    match fs::symlink_metadata(&marker) {
        Ok(metadata) if metadata.file_type().is_file() => {}
        Ok(_) => return Ok(false),
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(false),
        Err(error) => return Err(error.into()),
    }
    let deny = namespace.join(crate::compiler::OHM_WORKTREE_SEED_DENY_MARKER);
    match fs::symlink_metadata(deny) {
        Ok(_) => return Ok(false),
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(error) => return Err(error.into()),
    }
    let local_macro = namespace.join(crate::compiler::OHM_WORKTREE_SEED_LOCAL_PROC_MACRO_MARKER);
    match fs::symlink_metadata(local_macro) {
        // clone_tree must retain this marker so a subsequent fork checks trust again.
        Ok(metadata) => {
            Ok(metadata.file_type().is_file() && proc_macro_trust == OhmProcMacroTrust::All)
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(true),
        Err(error) => Err(error.into()),
    }
}

fn ensure_regular(path: &Path) -> CargoResult<()> {
    ensure!(
        fs::symlink_metadata(path)?.file_type().is_file(),
        "snapshot lock is not a regular file: {}",
        path.display()
    );
    Ok(())
}

fn plain_directory(path: &Path) -> CargoResult<bool> {
    match fs::symlink_metadata(path) {
        Ok(metadata) => Ok(metadata.file_type().is_dir()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(error.into()),
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use crate::compiler::{OHM_WORKTREE_SEED_LOCAL_PROC_MACRO_MARKER, OHM_WORKTREE_SEED_MARKER};

    #[test]
    fn unsupported_clone_discards_both_stages_and_their_counts() -> CargoResult<()> {
        let root = tempfile::tempdir()?;
        let recipient = tempfile::tempdir()?;
        let profile = root.path().join("debug");
        let workspaces = profile.join("build/workspaces");
        let incremental = profile.join("incremental");
        fs::create_dir_all(workspaces.join("donor"))?;
        fs::create_dir_all(incremental.join("donor"))?;
        fs::write(workspaces.join("donor/output"), b"artifact")?;
        fs::write(incremental.join("donor/query-cache.bin"), b"cache")?;
        let recipient_workspaces = recipient.path().join("debug/build/workspaces");
        let recipient_incremental = recipient.path().join("debug/incremental");

        // Finish staging the build tree, then reject the first incremental file.
        // This callback exercises publication/cleanup without requiring a particular FS.
        let result = seed_profile(
            root.path(),
            recipient.path(),
            Path::new("debug"),
            "donor",
            "recipient",
            &|src, dst| {
                if src.starts_with(&incremental) {
                    Ok(false)
                } else {
                    fs::copy(src, dst)?;
                    Ok(true)
                }
            },
        )?;
        assert!(result.is_none());
        assert_eq!(fs::read_dir(&workspaces)?.count(), 1);
        assert_eq!(fs::read_dir(&incremental)?.count(), 1);
        assert_eq!(fs::read_dir(&recipient_workspaces)?.count(), 0);
        assert_eq!(fs::read_dir(&recipient_incremental)?.count(), 0);

        // A retry sees absent destinations and reports only its committed files.
        let result = seed_profile(
            root.path(),
            recipient.path(),
            Path::new("debug"),
            "donor",
            "recipient",
            &|src, dst| {
                fs::copy(src, dst)?;
                Ok(true)
            },
        )?
        .unwrap();
        assert_eq!(result.files, 2);
        assert_eq!(result.bytes, 13);
        assert_eq!(fs::read_dir(&workspaces)?.count(), 1);
        assert_eq!(fs::read_dir(&incremental)?.count(), 1);
        assert_eq!(fs::read_dir(&recipient_workspaces)?.count(), 1);
        assert_eq!(fs::read_dir(&recipient_incremental)?.count(), 1);
        for (base, destination_base, name) in [
            (&workspaces, &recipient_workspaces, "output"),
            (&incremental, &recipient_incremental, "query-cache.bin"),
        ] {
            let source = base.join("donor").join(name);
            let destination = destination_base.join("recipient").join(name);
            let original = fs::read(&source)?;
            assert!(!same_file::is_same_file(&source, &destination)?);
            fs::write(destination, b"child")?;
            assert_eq!(fs::read(source)?, original);
        }
        Ok(())
    }

    #[test]
    fn clone_io_error_cleans_the_unpublished_profile() -> CargoResult<()> {
        let root = tempfile::tempdir()?;
        let profile = root.path().join("debug");
        let workspaces = profile.join("build/workspaces");
        fs::create_dir_all(workspaces.join("donor"))?;
        fs::write(workspaces.join("donor/output"), b"artifact")?;
        let error = seed_profile(
            root.path(),
            root.path(),
            Path::new("debug"),
            "donor",
            "recipient",
            &|_, _| Err(io::Error::from(io::ErrorKind::PermissionDenied).into()),
        )
        .err()
        .unwrap();
        assert_eq!(
            error.downcast_ref::<io::Error>().unwrap().kind(),
            io::ErrorKind::PermissionDenied
        );
        assert_eq!(fs::read_dir(&workspaces)?.count(), 1);
        assert_eq!(fs::read(workspaces.join("donor/output"))?, b"artifact");
        Ok(())
    }

    #[test]
    fn local_macro_trust_cannot_drop_a_symlinked_taint_marker() {
        let root = tempfile::tempdir().unwrap();
        fs::write(root.path().join(OHM_WORKTREE_SEED_MARKER), "7\n").unwrap();
        let taint = root.path().join(OHM_WORKTREE_SEED_LOCAL_PROC_MACRO_MARKER);
        let target = root.path().join("taint");
        fs::write(&target, "local macro\n").unwrap();
        std::os::unix::fs::symlink(&target, &taint).unwrap();
        assert!(!seed_policy_allows(root.path(), OhmProcMacroTrust::All).unwrap());

        // A broken symlink must not turn a tainted donor into an untainted one.
        fs::remove_file(target).unwrap();
        assert!(!seed_policy_allows(root.path(), OhmProcMacroTrust::All).unwrap());
    }
}
