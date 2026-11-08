//! Filesystem paths and mount identities reported by the Linux kernel.

use std::ffi::OsStr;
use std::os::unix::ffi::OsStrExt as _;
use std::path::PathBuf;

use anyhow::{Context as _, ensure};

use crate::CargoResult;

/// Decodes an absolute root or mountpoint field from /proc/self/mountinfo.
pub(crate) fn decode_path(mut field: &[u8]) -> CargoResult<PathBuf> {
    ensure!(
        field.starts_with(b"/"),
        "invalid mountpoint in /proc/self/mountinfo"
    );
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
    Ok(PathBuf::from(OsStr::from_bytes(&name)))
}

/// Reads the mount ID of an open file, including on kernels without statx mount IDs.
#[cfg(target_os = "linux")]
pub(crate) fn fd_mount_id(file: &std::fs::File) -> std::io::Result<u64> {
    use std::os::fd::AsRawFd as _;

    use rustix::fs::{AtFlags, StatxFlags};

    if let Ok(stat) = rustix::fs::statx(file, "", AtFlags::EMPTY_PATH, StatxFlags::MNT_ID)
        && stat.stx_mask & StatxFlags::MNT_ID.bits() != 0
    {
        return Ok(stat.stx_mnt_id);
    }
    let info = std::fs::read_to_string(format!("/proc/self/fdinfo/{}", file.as_raw_fd()))?;
    info.lines()
        .find_map(|line| line.strip_prefix("mnt_id:"))
        .and_then(|id| id.trim().parse().ok())
        .ok_or(std::io::ErrorKind::Unsupported.into())
}

/// Detects containment hidden by a bind mount of a directory below the protected root.
#[cfg(target_os = "linux")]
pub(crate) fn is_bind_descendant(
    path: &std::path::Path,
    base: &std::path::Path,
) -> CargoResult<bool> {
    use std::fs::{self, File};
    use std::os::fd::AsRawFd as _;
    use std::os::unix::fs::MetadataExt as _;

    use rustix::fs::{Mode, OFlags};

    if fs::metadata(path)?.dev() != fs::metadata(base)?.dev() {
        return Ok(false);
    }
    let flags = OFlags::PATH | OFlags::DIRECTORY | OFlags::CLOEXEC;
    let left = File::from(rustix::fs::open(path, flags, Mode::empty())?);
    let right = File::from(rustix::fs::open(base, flags, Mode::empty())?);
    let left_id = fd_mount_id(&left)?;
    let right_id = fd_mount_id(&right)?;
    if left_id == right_id {
        return Ok(false);
    }
    let table = fs::read("/proc/self/mountinfo")
        .context("could not resolve worktree storage across mounts")?;
    let locate = |file: &File, id| {
        // Use the kernel's spelling for both the path and its mountpoint.
        let path = fs::read_link(format!("/proc/self/fd/{}", file.as_raw_fd()))?;
        filesystem_path(&path, id, &table)
    };
    Ok(locate(&left, left_id)?.starts_with(locate(&right, right_id)?))
}

/// Translates a path in one mount namespace view to its path from the filesystem root.
#[cfg(target_os = "linux")]
fn filesystem_path(path: &std::path::Path, mount: u64, table: &[u8]) -> CargoResult<PathBuf> {
    let id = mount.to_string();
    for line in table.split(|byte| *byte == b'\n') {
        let mut fields = line.split(|byte| *byte == b' ');
        if fields.next() != Some(id.as_bytes()) {
            continue;
        }
        let root = decode_path(fields.nth(2).context("missing mount root")?)?;
        let point = decode_path(fields.next().context("missing mountpoint")?)?;
        return Ok(root.join(path.strip_prefix(&point)?));
    }
    anyhow::bail!("mount {mount} for {} disappeared", path.display());
}

#[cfg(all(test, target_os = "linux"))]
mod tests {
    use super::*;
    use std::path::Path;

    #[test]
    fn bind_mount_paths_include_the_filesystem_root() -> CargoResult<()> {
        let table = br"1 0 8:1 /storage /cache rw - ext4 /dev/root rw
2 1 8:1 /storage/owned/sub\040dir /deeper/bind\134name rw - ext4 /dev/root rw
";
        assert_eq!(
            filesystem_path(Path::new(r"/deeper/bind\name/new"), 2, table)?,
            filesystem_path(Path::new("/cache/owned/sub dir/new"), 1, table)?,
        );
        Ok(())
    }
}
