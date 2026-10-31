use std::borrow::Cow;
use std::fs::Metadata;
use std::io;
use std::path::{Component, Path, PathBuf};

#[cfg(target_os = "linux")]
use {
    rustix::fs::{Mode, OFlags, ResolveFlags},
    std::{fs::File, os::fd::AsRawFd},
};

/// A cache entry reached from its configured root without crossing a Linux mount.
pub(super) struct MountPath {
    path: PathBuf,
    #[cfg(target_os = "linux")]
    file: File,
}

impl MountPath {
    pub(super) fn root(path: &Path) -> io::Result<Self> {
        #[cfg(target_os = "linux")]
        let file = rustix::fs::open(
            path,
            OFlags::PATH | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )?
        .into();
        #[cfg(not(target_os = "linux"))]
        if !std::fs::symlink_metadata(path)?.is_dir() {
            return Err(io::ErrorKind::NotADirectory.into());
        }
        Ok(Self {
            path: path.to_owned(),
            #[cfg(target_os = "linux")]
            file,
        })
    }

    /// A final symlink is itself an entry. Intermediate symlinks are never followed.
    pub(super) fn child(&self, relative: &Path) -> io::Result<Self> {
        let mut name = PathBuf::new();
        for component in relative.components() {
            let Component::Normal(component) = component else {
                return Err(io::ErrorKind::InvalidInput.into());
            };
            #[cfg(not(target_os = "linux"))]
            if !std::fs::symlink_metadata(self.path.join(&name))?.is_dir() {
                return Err(io::ErrorKind::NotADirectory.into());
            }
            name.push(component);
        }
        #[cfg(target_os = "linux")]
        let file = if name.as_os_str().is_empty() {
            self.file.try_clone()?
        } else {
            Self::open_beneath(&self.file, &name, OFlags::PATH)?
        };
        let mut path = self.path.clone();
        if !name.as_os_str().is_empty() {
            path.push(name);
        }
        #[cfg(not(target_os = "linux"))]
        std::fs::symlink_metadata(&path)?;
        Ok(Self {
            path,
            #[cfg(target_os = "linux")]
            file,
        })
    }

    /// Open a nonempty relative path without entering nested mounts or following symlinks.
    /// For a final O_PATH lookup, the symlink itself is an allowed entry.
    #[cfg(target_os = "linux")]
    pub(super) fn open_beneath(root: &File, name: &Path, access: OFlags) -> io::Result<File> {
        let flags = access | OFlags::NOFOLLOW | OFlags::CLOEXEC;
        let resolve = ResolveFlags::BENEATH | ResolveFlags::NO_XDEV | ResolveFlags::NO_SYMLINKS;
        match rustix::fs::openat2(root, name, flags, Mode::empty(), resolve) {
            Ok(fd) => Ok(fd.into()),
            Err(rustix::io::Errno::NOSYS) => Self::open_before_openat2(root, name, flags),
            Err(error) => Err(error.into()),
        }
    }

    #[cfg(target_os = "linux")]
    fn open_before_openat2(root: &File, name: &Path, flags: OFlags) -> io::Result<File> {
        fn mount_id(file: &File) -> io::Result<u64> {
            let info = std::fs::read_to_string(format!("/proc/self/fdinfo/{}", file.as_raw_fd()))?;
            info.lines()
                .find_map(|line| line.strip_prefix("mnt_id:"))
                .and_then(|id| id.trim().parse().ok())
                .ok_or(io::ErrorKind::Unsupported.into())
        }
        let expected = mount_id(root)?;
        let mut parent = root.try_clone()?;
        let mut components = name.components().peekable();
        while let Some(component) = components.next() {
            let Component::Normal(component) = component else {
                return Err(io::ErrorKind::InvalidInput.into());
            };
            let flags = if components.peek().is_none() {
                flags
            } else {
                OFlags::PATH | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC
            };
            parent = rustix::fs::openat(&parent, component, flags, Mode::empty())?.into();
            if mount_id(&parent)? != expected {
                return Err(rustix::io::Errno::XDEV.into());
            }
        }
        Ok(parent)
    }

    pub(super) fn path(&self) -> &Path {
        &self.path
    }

    /// Require the last component to be a directory before using it as a parent.
    pub(super) fn child_dir(&self, relative: &Path) -> io::Result<Self> {
        let entry = self.child(relative)?;
        if !entry.metadata()?.is_dir() {
            return Err(io::ErrorKind::NotADirectory.into());
        }
        Ok(entry)
    }

    /// Address the pinned directory when using APIs that take paths instead of descriptors.
    pub(super) fn address(&self) -> Cow<'_, Path> {
        #[cfg(target_os = "linux")]
        {
            Cow::Owned(PathBuf::from(format!(
                "/proc/self/fd/{}",
                self.file.as_raw_fd()
            )))
        }
        #[cfg(not(target_os = "linux"))]
        {
            Cow::Borrowed(&self.path)
        }
    }

    pub(super) fn metadata(&self) -> io::Result<Metadata> {
        #[cfg(target_os = "linux")]
        {
            self.file.metadata()
        }
        #[cfg(not(target_os = "linux"))]
        {
            std::fs::symlink_metadata(&self.path)
        }
    }
}

#[cfg(all(test, target_os = "linux"))]
mod tests {
    use super::*;
    use std::fs;
    use std::os::unix::fs::symlink;

    #[test]
    fn renamed_parent_and_final_symlink() -> io::Result<()> {
        let dir = tempfile::tempdir()?;
        let root = MountPath::root(dir.path())?;
        let old = dir.path().join("before");
        fs::create_dir(&old)?;
        symlink("missing", old.join("link"))?;
        let parent = root.child(Path::new("before"))?;
        fs::rename(&old, dir.path().join("after"))?;
        fs::create_dir(&old)?;
        fs::write(old.join("link"), b"replacement")?;

        let link = parent.child(Path::new("link"))?;
        assert!(link.metadata()?.is_symlink());
        assert!(link.child(Path::new("child")).is_err());
        fs::remove_file(parent.address().join("link"))?;
        assert_eq!(fs::read(old.join("link"))?, b"replacement");
        Ok(())
    }
}
