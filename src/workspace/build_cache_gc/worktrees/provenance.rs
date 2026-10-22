//! Immutable evidence that a private context was built with the moving Ohm toolchain.

use std::fs;
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};

use super::super::{
    FileIdentity, absent, installed_ohm_version, ohm_release, ohm_version, scoped_context_name,
};
use crate::util::GlobalContext;
use crate::workspace::build_cache_gc_roots::open_regular;

pub(crate) const MARKER: &str = ".ohm-private-context-v1";
pub(crate) const KEEP: &str = ".ohm-private-context-keep-v1";

pub(crate) struct MovingRelease {
    pub(crate) version: String,
    toolchains: PathBuf,
}

/// Read the installed moving alias even when the command itself selected a pinned compiler.
pub(crate) fn current_moving_release(gctx: &GlobalContext) -> Option<MovingRelease> {
    let toolchains = home::rustup_home_with_cwd(gctx.cwd())
        .ok()?
        .join("toolchains")
        .canonicalize()
        .ok()?;
    let alias = toolchains.join("ohm");
    if !fs::symlink_metadata(&alias).ok()?.is_symlink() {
        return None;
    }
    let sysroot = alias.canonicalize().ok()?;
    if !fs::symlink_metadata(sysroot.join("bin/rustc"))
        .ok()?
        .is_file()
    {
        return None;
    }
    let marker = read_marker(&sysroot.join(".ohm-version"))?;
    let version = std::str::from_utf8(&marker).ok()?.trim_end();
    ohm_release(version)?;
    (alias.canonicalize().ok()? == sysroot).then(|| MovingRelease {
        version: version.to_owned(),
        toolchains,
    })
}

/// The selected tool must be the moving rustup link and agree with the packaged release.
pub(crate) fn moving_release(
    rustc: &Path,
    verbose: &str,
    compiler: &FileIdentity,
    driver: &FileIdentity,
) -> Option<MovingRelease> {
    let version = ohm_version(verbose)?;
    let toolchains = home::rustup_home().ok()?.join("toolchains");
    if rustc != toolchains.join("ohm/bin/rustc") {
        return None;
    }
    let toolchains = toolchains.canonicalize().ok()?;
    let alias = toolchains.join("ohm");
    if !fs::symlink_metadata(&alias).ok()?.is_symlink()
        || alias.join("bin/rustc").canonicalize().ok()? != compiler.path
        || installed_ohm_version(compiler, driver).as_deref() != Some(version)
    {
        return None;
    }
    Some(MovingRelease {
        version: version.to_owned(),
        toolchains,
    })
}

/// Only a directory created by this build can acquire proof; old contents have unknown history.
pub(crate) fn record_new(
    root: &Path,
    path: &Path,
    context: &str,
    release: impl FnOnce() -> Option<MovingRelease>,
) -> io::Result<()> {
    if !absent(path) {
        return Ok(());
    }
    let Some(release) = release() else {
        return Ok(());
    };
    if !scoped_context_name(context)
        || path.file_name().and_then(|name| name.to_str()) != Some(context)
    {
        return Err(io::Error::other("invalid private compiler context"));
    }
    let parent = plain_target_directory(root, path.parent().unwrap(), true)?;
    let path = parent.join(context);
    match fs::create_dir(&path) {
        Ok(()) => {}
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => return Ok(()),
        Err(error) => return Err(error),
    }
    if path.canonicalize()? != path {
        return Err(io::Error::other("private context changed during creation"));
    }
    let mut marker = tempfile::NamedTempFile::new_in(&path)?;
    writeln!(marker, "{context}\n{}", release.version)?;
    marker
        .write_all(cargo_util::paths::path2bytes(&release.toolchains).map_err(io::Error::other)?)?;
    marker
        .persist_noclobber(path.join(MARKER))
        .map_err(|error| error.error)?;
    Ok(())
}

/// An external directory export or opaque compiler can continue to depend on this tree.
pub(crate) fn keep(root: &Path, path: &Path) -> io::Result<()> {
    match fs::symlink_metadata(path.join(MARKER)) {
        Ok(metadata) if !metadata.is_file() => return Ok(()),
        Ok(_) => {}
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(error),
    }
    let keep = path.join(KEEP);
    match fs::symlink_metadata(&keep) {
        Ok(_) => return Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(error) => return Err(error),
    }
    let directory = plain_target_directory(root, path, false)?;
    if directory.canonicalize()? != directory {
        return Err(io::Error::other(
            "private context changed before protecting it",
        ));
    }
    match fs::File::create_new(directory.join(KEEP)) {
        Ok(_) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => Ok(()),
        Err(error) => Err(error),
    }
}

/// Reach a directory from the selected target without crossing a namespace symlink.
fn plain_target_directory(root: &Path, path: &Path, create: bool) -> io::Result<PathBuf> {
    let relative = path.strip_prefix(root).map_err(io::Error::other)?;
    let mut directory = root.canonicalize()?;
    if !fs::symlink_metadata(&directory)?.is_dir() {
        return Err(io::Error::other("private target is not a directory"));
    }
    for component in relative.components() {
        let Component::Normal(name) = component else {
            return Err(io::Error::other("private context escapes its target"));
        };
        directory.push(name);
        if create && absent(&directory) {
            match fs::create_dir(&directory) {
                Ok(()) => {}
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {}
                Err(error) => return Err(error),
            }
        }
        if !fs::symlink_metadata(&directory)?.is_dir() {
            return Err(io::Error::other(format!(
                "invalid private context directory: {}",
                directory.display()
            )));
        }
    }
    Ok(directory)
}

/// Returns the proven older packaged release for this exact, unprotected private context.
pub(crate) fn obsolete(path: &Path, context: &str, current: &MovingRelease) -> Option<String> {
    if !scoped_context_name(context)
        || path.file_name()?.to_str()? != context
        || !fs::symlink_metadata(path).ok()?.is_dir()
        || !absent(&path.join(KEEP))
    {
        return None;
    }
    let proof = read_marker(&path.join(MARKER))?;
    let mut fields = proof.splitn(3, |byte| *byte == b'\n');
    let id = fields.next()?;
    let release = std::str::from_utf8(fields.next()?).ok()?;
    (id == context.as_bytes()
        && fields.next()? == cargo_util::paths::path2bytes(&current.toolchains).ok()?
        && ohm_release(release)? < ohm_release(&current.version)?)
    .then(|| release.to_owned())
}

fn read_marker(path: &Path) -> Option<Vec<u8>> {
    let file = open_regular(path).ok()?;
    let mut proof = Vec::new();
    if file.take(8193).read_to_end(&mut proof).ok()? > 8192 {
        return None;
    }
    Some(proof)
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;

    #[test]
    fn proof_is_cold_and_only_authorizes_its_own_older_context() -> io::Result<()> {
        let temp = tempfile::tempdir()?;
        let root = temp.path();
        let release = |version: &str| MovingRelease {
            version: version.to_owned(),
            toolchains: root.join("toolchains"),
        };
        let id = "v2-0123456789abcdef";
        let path = temp.path().join(id);
        let older = "ohm-1.99.0-9";
        let current = release("ohm-1.99.0-10");
        record_new(root, &path, id, || Some(release(older)))?;
        record_new(root, &path, id, || {
            panic!("warm build rechecked compiler provenance")
        })?;
        assert_eq!(obsolete(&path, id, &current).as_deref(), Some(older));
        assert_eq!(obsolete(&path, id, &release(older)), None);
        assert_eq!(obsolete(&path, id, &release("ohm-1.98.1-1")), None);
        keep(root, &path)?;
        assert_eq!(obsolete(&path, id, &current), None);

        let other_id = "v2-fedcba9876543210";
        let other = temp.path().join(other_id);
        fs::create_dir(&other)?;
        record_new(root, &other, other_id, || {
            panic!("retrofitted an unknown directory")
        })?;
        assert_eq!(obsolete(&other, other_id, &current), None);
        fs::copy(path.join(MARKER), other.join(MARKER))?;
        assert_eq!(obsolete(&other, other_id, &current), None);
        fs::remove_file(other.join(MARKER))?;
        let external = temp.path().join("external");
        let mut proof = format!("{other_id}\n{older}\n").into_bytes();
        proof.extend_from_slice(cargo_util::paths::path2bytes(&current.toolchains).unwrap());
        fs::write(&external, proof)?;
        symlink(external, other.join(MARKER))?;
        assert_eq!(obsolete(&other, other_id, &current), None);
        Ok(())
    }

    #[test]
    fn a_symlinked_namespace_never_writes_into_its_destination() -> io::Result<()> {
        let temp = tempfile::tempdir()?;
        let root = temp.path().join("target");
        let external = temp.path().join("outside");
        fs::create_dir(&root)?;
        fs::create_dir(&external)?;
        symlink(&external, root.join("workspaces"))?;
        let id = "v2-0123456789abcdef";
        let path = root.join("workspaces/owner").join(id);
        let release = MovingRelease {
            version: "ohm-1.99.0-9".to_owned(),
            toolchains: temp.path().join("toolchains"),
        };
        assert!(record_new(&root, &path, id, || Some(release)).is_err());
        assert!(!external.join("owner").exists());
        let existing = external.join("owner").join(id);
        fs::create_dir_all(&existing)?;
        fs::write(existing.join(MARKER), b"external marker")?;
        assert!(keep(&root, &path).is_err());
        assert!(!existing.join(KEEP).exists());
        assert!(root.join("workspaces").is_symlink());
        Ok(())
    }
}
