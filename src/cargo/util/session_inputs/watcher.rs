//! Linux directory notifications used only to reuse filesystem topology.
//!
//! File bytes and artifact metadata remain polled. Unsupported filesystems,
//! notification failures, and mount changes leave the caller on the polling path.

use std::collections::BTreeMap;
use std::ffi::{CString, OsStr, OsString};
use std::fs;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};

use crate::util::data_structures::HashMap;

#[derive(Clone, Debug)]
pub(super) struct Token {
    generation: u64,
    watch: i32,
    name: Option<OsString>,
    own_revision: u64,
    entry_revision: u64,
}

#[derive(Debug)]
struct Watch {
    identity: (u64, u64),
    own_revision: u64,
    entries_revision: u64,
    names: BTreeMap<OsString, u64>,
}

#[derive(Debug, Default)]
pub(super) struct Watcher {
    fd: Option<OwnedFd>,
    generation: u64,
    disabled: bool,
    paths: BTreeMap<PathBuf, i32>,
    watches: HashMap<i32, Watch>,
    mounts: Option<Vec<u8>>,
}

impl Watcher {
    /// Start each validation at a drained queue and a checked mount topology.
    pub(super) fn synchronize(&mut self) {
        if self.disabled {
            return;
        }
        let mounts = match fs::read("/proc/self/mountinfo") {
            Ok(mounts) => mounts,
            Err(_) => {
                self.disable();
                return;
            }
        };
        if self
            .mounts
            .as_ref()
            .is_some_and(|previous| *previous != mounts)
        {
            self.invalidate();
        }
        self.mounts = Some(mounts);
        self.drain();
    }

    /// Record either all directory entries or one named entry, plus the directory itself.
    pub(super) fn observe(&mut self, directory: &Path, name: Option<&OsStr>) -> Option<Token> {
        if self.disabled || !directory.is_absolute() {
            return None;
        }
        // Bind registration to one opened directory. Watching the path after a
        // stat could instead cover a replacement inode or a different filesystem.
        let directory_handle = fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY)
            .open(directory)
            .ok()?;
        let metadata = directory_handle.metadata().ok()?;
        let identity = (metadata.dev(), metadata.ino());
        if let Some(watch) = self.paths.get(directory)
            && self.watches.get(watch)?.identity != identity
        {
            // The old inode can remain watched after a rename. Retire its tokens
            // instead of associating the new path with the old watch descriptor.
            self.invalidate();
        }
        let watch = match self.paths.get(directory) {
            Some(watch) => *watch,
            None => {
                if !supported_filesystem(directory_handle.as_raw_fd()) {
                    return None;
                }
                let fd = self.descriptor()?;
                let path = CString::new(format!("/proc/self/fd/{}", directory_handle.as_raw_fd()))
                    .expect("a directory descriptor contains no NUL bytes");
                let mask = libc::IN_ATTRIB
                    | libc::IN_CREATE
                    | libc::IN_DELETE
                    | libc::IN_DELETE_SELF
                    | libc::IN_MOVE_SELF
                    | libc::IN_MOVED_FROM
                    | libc::IN_MOVED_TO
                    | libc::IN_ONLYDIR;
                // SAFETY: path is NUL-terminated, the directory handle remains
                // open, and fd owns a live inotify instance.
                let watch = unsafe { libc::inotify_add_watch(fd, path.as_ptr(), mask) };
                if watch < 0 {
                    self.disable();
                    return None;
                }
                if self
                    .watches
                    .get(&watch)
                    .is_some_and(|state| state.identity != identity)
                {
                    self.invalidate();
                    return None;
                }
                self.paths.insert(directory.to_owned(), watch);
                self.watches.entry(watch).or_insert_with(|| Watch {
                    identity,
                    own_revision: 0,
                    entries_revision: 0,
                    names: BTreeMap::new(),
                });
                watch
            }
        };
        let state = self.watches.get_mut(&watch)?;
        let entry_revision = match name {
            Some(name) => *state.names.entry(name.to_owned()).or_default(),
            None => state.entries_revision,
        };
        Some(Token {
            generation: self.generation,
            watch,
            name: name.map(OsStr::to_owned),
            own_revision: state.own_revision,
            entry_revision,
        })
    }

    pub(super) fn unchanged(&self, token: &Token) -> bool {
        if self.disabled || token.generation != self.generation {
            return false;
        }
        let Some(watch) = self.watches.get(&token.watch) else {
            return false;
        };
        watch.own_revision == token.own_revision
            && match &token.name {
                Some(name) => watch.names.get(name) == Some(&token.entry_revision),
                None => watch.entries_revision == token.entry_revision,
            }
    }

    fn descriptor(&mut self) -> Option<i32> {
        if self.fd.is_none() {
            // SAFETY: inotify_init1 has no pointer arguments; the flags make draining
            // nonblocking and prevent compiler children from retaining the descriptor.
            let fd = unsafe { libc::inotify_init1(libc::IN_NONBLOCK | libc::IN_CLOEXEC) };
            if fd < 0 {
                self.disable();
                return None;
            }
            // SAFETY: the newly returned descriptor has no other owner.
            self.fd = Some(unsafe { OwnedFd::from_raw_fd(fd) });
        }
        Some(self.fd.as_ref()?.as_raw_fd())
    }

    fn drain(&mut self) {
        let Some(fd) = self.fd.as_ref().map(AsRawFd::as_raw_fd) else {
            return;
        };
        let mut buffer = [0_u8; 16 * 1024];
        loop {
            // SAFETY: buffer is writable for its complete length and fd remains open.
            let read = unsafe { libc::read(fd, buffer.as_mut_ptr().cast(), buffer.len()) };
            if read < 0 {
                match io::Error::last_os_error().kind() {
                    io::ErrorKind::Interrupted => continue,
                    io::ErrorKind::WouldBlock => break,
                    _ => self.disable(),
                }
                return;
            }
            if read == 0 {
                self.disable();
                return;
            }
            if !self.consume(&buffer[..read as usize]) {
                return;
            }
        }
    }

    fn consume(&mut self, buffer: &[u8]) -> bool {
        let header = std::mem::size_of::<libc::inotify_event>();
        let mut remaining = buffer;
        while !remaining.is_empty() {
            if remaining.len() < header {
                self.disable();
                return false;
            }
            // SAFETY: a complete header is available. The byte buffer need not be aligned.
            let event = unsafe {
                std::ptr::read_unaligned(remaining.as_ptr().cast::<libc::inotify_event>())
            };
            let Some(length) = header.checked_add(event.len as usize) else {
                self.disable();
                return false;
            };
            if length > remaining.len() {
                self.disable();
                return false;
            }
            if event.mask & (libc::IN_Q_OVERFLOW | libc::IN_IGNORED | libc::IN_UNMOUNT) != 0 {
                // Closing the instance also prevents a removed descriptor from being
                // confused with a later watch that reuses its integer identifier.
                self.invalidate();
                return false;
            }
            let Some(watch) = self.watches.get_mut(&event.wd) else {
                self.invalidate();
                return false;
            };
            let name = &remaining[header..length];
            let name = name.split(|byte| *byte == 0).next().unwrap_or_default();
            if name.is_empty() {
                watch.own_revision += 1;
            } else {
                watch.entries_revision += 1;
                if let Some(revision) = watch.names.get_mut(OsStr::from_bytes(name)) {
                    *revision += 1;
                }
            }
            remaining = &remaining[length..];
        }
        true
    }

    fn invalidate(&mut self) {
        self.generation += 1;
        self.fd = None;
        self.paths.clear();
        self.watches.clear();
    }

    fn disable(&mut self) {
        self.invalidate();
        self.disabled = true;
    }

    #[cfg(test)]
    pub(super) fn discard_events(&mut self) {
        let Some(fd) = self.fd.as_ref().map(AsRawFd::as_raw_fd) else {
            return;
        };
        let mut buffer = [0_u8; 16 * 1024];
        // SAFETY: the buffer is writable and the test retains ownership of fd.
        while unsafe { libc::read(fd, buffer.as_mut_ptr().cast(), buffer.len()) } > 0 {}
    }

    #[cfg(test)]
    pub(super) fn simulate_overflow(&mut self) {
        let event = libc::inotify_event {
            wd: -1,
            mask: libc::IN_Q_OVERFLOW,
            cookie: 0,
            len: 0,
        };
        // SAFETY: event is initialized and the borrowed bytes do not outlive it.
        let bytes = unsafe {
            std::slice::from_raw_parts(
                std::ptr::from_ref(&event).cast::<u8>(),
                std::mem::size_of_val(&event),
            )
        };
        self.consume(bytes);
    }

    #[cfg(test)]
    pub(super) fn simulate_failure(&mut self) {
        self.disable();
    }
}

fn supported_filesystem(fd: i32) -> bool {
    let mut status = std::mem::MaybeUninit::<libc::statfs>::uninit();
    // SAFETY: fd remains open and status points to writable statfs storage.
    if unsafe { libc::fstatfs(fd, status.as_mut_ptr()) } != 0 {
        return false;
    }
    // SAFETY: fstatfs initialized the structure on success.
    let filesystem = unsafe { status.assume_init() }.f_type as u64;
    // Network, FUSE, overlay, and pseudo filesystems can have changes outside
    // this watch instance's event coverage. Keep them on the exact polling path.
    [
        libc::EXT4_SUPER_MAGIC as u64,
        libc::XFS_SUPER_MAGIC as u64,
        libc::BTRFS_SUPER_MAGIC as u64,
        libc::TMPFS_MAGIC as u64,
    ]
    .contains(&filesystem)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn watched_tempdir() -> Option<tempfile::TempDir> {
        let dir = tempfile::tempdir().unwrap();
        let mut watcher = Watcher::default();
        watcher.synchronize();
        watcher.observe(dir.path(), None).map(|_| dir)
    }

    #[test]
    fn named_entries_ignore_unrelated_sibling_changes() {
        let Some(dir) = watched_tempdir() else {
            return; // This host uses the polling fallback.
        };
        let mut watcher = Watcher::default();
        watcher.synchronize();
        let named = watcher
            .observe(dir.path(), Some(OsStr::new("watched")))
            .unwrap();
        let entries = watcher.observe(dir.path(), None).unwrap();
        fs::write(dir.path().join("unrelated"), "file").unwrap();
        watcher.synchronize();
        assert!(watcher.unchanged(&named));
        assert!(!watcher.unchanged(&entries));
        fs::write(dir.path().join("watched"), "file").unwrap();
        watcher.synchronize();
        assert!(!watcher.unchanged(&named));
    }

    #[test]
    fn replacing_a_watched_path_registers_the_new_directory() {
        let Some(dir) = watched_tempdir() else {
            return; // This host uses the polling fallback.
        };
        let path = dir.path().join("watched");
        fs::create_dir(&path).unwrap();
        let mut watcher = Watcher::default();
        watcher.synchronize();
        let old = watcher.observe(&path, None).unwrap();
        fs::rename(&path, dir.path().join("old")).unwrap();
        fs::create_dir(&path).unwrap();
        watcher.synchronize();
        let replacement = watcher.observe(&path, None).unwrap();
        assert!(!watcher.unchanged(&old));
        assert!(watcher.unchanged(&replacement));
        fs::write(path.join("new"), "file").unwrap();
        watcher.synchronize();
        assert!(!watcher.unchanged(&replacement));
    }

    #[test]
    fn removed_watches_and_changed_mount_topology_retire_old_tokens() {
        let Some(dir) = watched_tempdir() else {
            return; // This host uses the polling fallback.
        };
        let path = dir.path().join("watched");
        fs::create_dir(&path).unwrap();
        let mut watcher = Watcher::default();
        watcher.synchronize();
        let old = watcher.observe(&path, None).unwrap();
        fs::remove_dir(&path).unwrap();
        watcher.synchronize();
        assert!(!watcher.unchanged(&old));
        fs::create_dir(&path).unwrap();
        let current = watcher.observe(&path, None).unwrap();
        watcher.synchronize();
        assert!(watcher.unchanged(&current));
        watcher.mounts = Some(Vec::new());
        watcher.synchronize();
        assert!(!watcher.unchanged(&current));
    }
}
