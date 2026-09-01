//! Creates independent Git worktrees and imports a completed local build snapshot.

mod copy;

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use anyhow::{Context as _, bail, ensure};
use cargo_util::ProcessBuilder;
use filetime::FileTime;

use crate::CargoResult;
use crate::core::Workspace;
use crate::core::compiler::Layout;
use crate::core::compiler::fingerprint::dep_info::{DepInfoPathType, EncodedDepInfo};
use crate::core::compiler::fingerprint::{OHM_WORKTREE_SCRIPT_RERUN, OHM_WORKTREE_SCRIPT_RESULT};
use crate::util::{Filesystem, GlobalContext};

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
    let repo = git2::Repository::discover(donor.root())
        .context("`cargo worktree` requires a Git working tree")?;
    let git_root = repo
        .workdir()
        .context("cannot seed from a bare repository")?;
    let git_root = git_root.canonicalize()?;
    let destination = donor.canonical_build_path(&opts.path);
    ensure_absent(&destination, "worktree destination")?;
    ensure!(
        !destination.starts_with(&git_root) && !git_root.starts_with(&destination),
        "the new worktree must be outside the source worktree"
    );

    let manifest = donor.root_manifest().canonicalize()?;
    let manifest = destination.join(manifest.strip_prefix(&git_root)?);
    let target = opts.target_dir.as_ref().map_or_else(
        || manifest.parent().unwrap().join("target"),
        |path| donor.canonical_build_path(path),
    );
    ensure_absent(&target, "destination target directory")?;
    for protected in [
        git_root.clone(),
        donor.target_dir().into_path_unlocked(),
        donor.build_dir().into_path_unlocked(),
    ] {
        let protected = donor.canonical_build_path(&protected);
        ensure!(
            !destination.starts_with(&protected) && !protected.starts_with(&destination),
            "worktree destination overlaps source storage: {}",
            protected.display()
        );
        ensure!(
            !target.starts_with(&protected) && !protected.starts_with(&target),
            "destination target directory overlaps source storage: {}",
            protected.display()
        );
    }
    ensure!(
        !destination.starts_with(&target),
        "destination target directory must not contain the new worktree"
    );

    let mut git = ProcessBuilder::new("git");
    git.arg("-C").arg(&git_root).args(&["worktree", "add"]);
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

    let seed = || -> CargoResult<Seeded> {
        // The selected commit may itself contain a target directory. Do not adopt it.
        ensure_plain_descendants(&destination, manifest.parent().unwrap())?;
        ensure!(
            donor.canonical_build_path(&target) == target,
            "destination target directory changed through a checked-out symlink"
        );
        ensure_absent(&target, "destination target directory")?;
        let mut recipient = Workspace::new(&manifest, gctx)?;
        recipient.set_target_dir(Filesystem::new(target.clone()));
        if !gctx.cli_unstable().ohm_worktree_seeds || !donor.shared_registry_cache_enabled() {
            return Ok(Seeded::default());
        }
        seed_shared_build(&donor, &recipient)
    };
    let seeded = seed().with_context(|| {
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
    gctx.shell().status("Target", target.display())?;
    Ok(())
}

#[derive(Default)]
struct Seeded {
    files: u64,
    bytes: u64,
    reflinked_files: u64,
    skipped_profiles: usize,
}

/// Copies only this donor's namespaces while holding the ordinary profile locks.
///
/// Taking exclusive profile locks also excludes child compilers and cleanup. Host
/// profiles precede cross-target profiles, matching compilation and `cargo clean`.
fn seed_shared_build(donor: &Workspace<'_>, recipient: &Workspace<'_>) -> CargoResult<Seeded> {
    let build_dir = donor.build_dir();
    let build_root = donor.canonical_build_path(build_dir.as_path_unlocked());
    ensure!(
        build_root == recipient.canonical_build_path(recipient.build_dir().as_path_unlocked()),
        "worktree seeding requires the same separate build directory in both worktrees"
    );
    let source_namespace = Layout::shared_workspace_namespace(donor);
    let destination_namespace = Layout::shared_workspace_namespace(recipient);
    ensure!(
        source_namespace != destination_namespace,
        "worktree build namespaces must differ"
    );
    let profiles = build_profiles(&build_root)?;
    let mut guards = Vec::with_capacity(profiles.len());
    for profile in &profiles {
        ensure_plain_descendants(&build_root, profile)?;
        ensure_regular(&profile.join(".cargo-build-lock"))?;
        guards.push(Filesystem::new(profile.clone()).open_rw_exclusive_create(
            ".cargo-build-lock",
            donor.gctx(),
            "worktree snapshot",
        )?);
    }

    let mut seeded = Seeded::default();
    for profile in &profiles {
        let workspaces = profile.join("build/workspaces");
        let source = workspaces.join(&source_namespace);
        if !plain_directory(&source)? {
            continue;
        }
        ensure_plain_descendants(profile, &source)?;
        if !seed_policy_allows(&source)? {
            seeded.skipped_profiles += 1;
            continue;
        }
        let destination = workspaces.join(&destination_namespace);
        ensure_absent(&destination, "destination build namespace")?;
        let incremental = profile.join("incremental");
        let incremental_source = incremental.join(&source_namespace);
        let incremental_destination = incremental.join(&destination_namespace);
        ensure_absent(
            &incremental_destination,
            "destination incremental namespace",
        )?;
        let old_prefix = source.strip_prefix(&build_root)?;
        let new_prefix = destination.strip_prefix(&build_root)?;

        // Stage both trees before publishing either. A failed copy never exposes
        // a partly copied fingerprint tree to the recipient.
        let stage = tempfile::Builder::new()
            .prefix(".ohm-worktree-seed-")
            .tempdir_in(&workspaces)?;
        let staged_build = stage.path().join("build");
        clone_tree(
            &source,
            &staged_build,
            old_prefix,
            new_prefix,
            false,
            &mut seeded,
        )?;
        let staged_incremental = stage.path().join("incremental");
        let has_incremental = plain_directory(&incremental_source)?;
        if has_incremental {
            ensure_plain_descendants(profile, &incremental_source)?;
            clone_tree(
                &incremental_source,
                &staged_incremental,
                old_prefix,
                new_prefix,
                true,
                &mut seeded,
            )?;
            fs::rename(&staged_incremental, &incremental_destination)?;
        }
        fs::rename(&staged_build, &destination)?;
    }
    drop(guards);
    Ok(seeded)
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
/// File cloning shares data blocks where supported and otherwise copies bytes.
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
) -> CargoResult<()> {
    fs::create_dir(destination)?;
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let name = entry.file_name();
        let text = name.to_string_lossy();
        let ty = entry.file_type()?;
        if text.ends_with("-working")
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
            clone_tree(
                &source,
                &destination,
                old_prefix,
                new_prefix,
                incremental,
                seeded,
            )?;
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
                let (bytes, reflinked) = copy::copy_file(&source, &destination)?;
                seeded.bytes += bytes;
                seeded.reflinked_files += u64::from(reflinked);
                if text.starts_with("dep-")
                    && source
                        .parent()
                        .is_some_and(|parent| parent.ends_with("fingerprint"))
                {
                    if !relocate_dep_info(&destination, old_prefix, new_prefix)? {
                        seeded.bytes -= metadata.len();
                        seeded.reflinked_files -= u64::from(reflinked);
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
    Ok(())
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
    let mut changed = false;
    for (kind, path, _) in &mut info.files {
        if *kind == DepInfoPathType::BuildRootRelative
            && let Ok(relative) = path.strip_prefix(old_prefix)
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

fn ensure_absent(path: &Path, description: &str) -> CargoResult<()> {
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
        Ok(_) => bail!("{description} already exists: {}", path.display()),
    }
}

fn seed_policy_allows(namespace: &Path) -> CargoResult<bool> {
    let marker = namespace.join(crate::core::compiler::OHM_WORKTREE_SEED_MARKER);
    match fs::symlink_metadata(&marker) {
        Ok(metadata) if metadata.file_type().is_file() => {}
        Ok(_) => return Ok(false),
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(false),
        Err(error) => return Err(error.into()),
    }
    let deny = namespace.join(crate::core::compiler::OHM_WORKTREE_SEED_DENY_MARKER);
    match fs::symlink_metadata(deny) {
        Ok(_) => Ok(false),
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
