//! Linux bind mounts can share a device number with the build directory.

use std::path::{Path, PathBuf};

use crate::util::CargoResult;
use crate::workspace::build_cache_gc::Summary;

pub(in crate::workspace::build_cache_gc) struct Mounts(Vec<PathBuf>);

impl Mounts {
    #[cfg(all(test, target_os = "linux"))]
    pub(in crate::workspace::build_cache_gc) fn for_test(paths: Vec<PathBuf>) -> Self {
        Self(paths)
    }

    /// The target can itself be a mount. Only its nested mountpoints are foreign.
    pub(in crate::workspace::build_cache_gc) fn read(root: &Path) -> CargoResult<Self> {
        #[cfg(target_os = "linux")]
        {
            use anyhow::Context as _;
            let table = std::fs::read("/proc/self/mountinfo")
                .context("could not check for nested mounts in the build directory")?;
            Self::from_mountinfo(root, &table)
        }
        #[cfg(not(target_os = "linux"))]
        {
            let _ = root;
            Ok(Self(Vec::new()))
        }
    }

    /// Refuse to enter a mount or detach a tree containing one.
    pub(in crate::workspace::build_cache_gc) fn blocked(
        &self,
        path: &Path,
        recursive: bool,
        summary: &mut Summary<'_>,
    ) -> bool {
        let Some(mount) = self.boundary(path, recursive) else {
            return false;
        };
        summary.skip_path(path, &format!("would cross mount at {}", mount.display()));
        true
    }

    fn boundary(&self, path: &Path, recursive: bool) -> Option<&Path> {
        self.0
            .iter()
            .find(|mount| path.starts_with(mount) || (recursive && mount.starts_with(path)))
            .map(PathBuf::as_path)
    }

    #[cfg(any(target_os = "linux", test))]
    fn from_mountinfo(root: &Path, table: &[u8]) -> CargoResult<Self> {
        use anyhow::Context as _;
        use std::ffi::OsStr;
        use std::os::unix::ffi::OsStrExt as _;

        anyhow::ensure!(!table.is_empty(), "empty /proc/self/mountinfo");
        let mut mounts = Vec::new();
        for line in table.split(|b| *b == b'\n').filter(|line| !line.is_empty()) {
            let mut field = line
                .split(|b| *b == b' ')
                .nth(4)
                .filter(|field| field.starts_with(b"/"))
                .context("invalid mountpoint in /proc/self/mountinfo")?;
            let mut name = Vec::with_capacity(field.len());
            while let Some((byte, rest)) = field.split_first() {
                if *byte == b'\\' {
                    let (escape, rest) = rest
                        .split_at_checked(3)
                        .context("incomplete mountpoint escape in /proc/self/mountinfo")?;
                    name.push(match escape {
                        b"040" => b' ',
                        b"011" => b'\t',
                        b"012" => b'\n',
                        b"134" => b'\\',
                        _ => anyhow::bail!("invalid mountpoint escape in /proc/self/mountinfo"),
                    });
                    field = rest;
                } else {
                    name.push(*byte);
                    field = rest;
                }
            }
            let path = Path::new(OsStr::from_bytes(&name));
            if path != root && path.starts_with(root) {
                mounts.push(path.to_owned());
            }
        }
        Ok(Self(mounts))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_device_mounts_block_only_their_own_context_or_trash() {
        let root = Path::new("/my target");
        let table = br#"1 0 8:1 / / rw - ext4 /dev/root rw
2 1 8:1 /targets /my\040target rw - ext4 /dev/root rw
3 2 8:1 /outside /my\040target/old/out/bind\134dir rw - ext4 /dev/root rw
4 2 8:1 /outside /my\040target/trash/entry/payload/bind rw - ext4 /dev/root rw
5 1 8:1 /outside /my\040target-elsewhere rw - ext4 /dev/root rw
"#;
        let mounts = Mounts::from_mountinfo(root, table).unwrap();
        let old = root.join("old");
        let nested = old.join(r"out/bind\dir");
        assert_eq!(mounts.boundary(&old, true), Some(nested.as_path()));
        assert_eq!(mounts.boundary(&old, false), None);
        assert_eq!(
            mounts.boundary(&nested.join("file"), false),
            Some(nested.as_path())
        );
        assert_eq!(
            mounts.boundary(&root.join("trash"), true),
            Some(root.join("trash/entry/payload/bind").as_path())
        );
        assert_eq!(mounts.boundary(&root.join("unrelated"), true), None);
        let mut summary = Summary::default();
        assert!(mounts.blocked(&old, true, &mut summary));
        assert_eq!(
            summary.skipped,
            [format!(
                "{} (would cross mount at {})",
                old.display(),
                nested.display()
            )]
        );
        assert!(Mounts::from_mountinfo(root, br"1 0 8:1 / /my\12 rw").is_err());
    }
}
