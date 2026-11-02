//! A cold link observes a namespace as well as the bytes read through it. Keep this
//! observation separate from the reusable action key. A later build may safely use
//! identical files at the same names even when Cargo replaced their inodes.
use std::collections::BTreeMap;
use std::fs;
use std::io;
use std::os::unix::fs::MetadataExt;
use std::path::{Component, Path, PathBuf};

use super::{Inputs, invalid};

#[derive(Clone, Copy, Eq, PartialEq)]
struct Identity {
    device: u64,
    inode: u64,
    mode: u32,
}

struct Node {
    identity: Identity,
    change: (i64, i64),
    link: Option<PathBuf>,
    // A directory used as a search namespace or the parent of a missing name
    // must not acquire and lose an entry during this particular link.
    entries: bool,
}

impl Identity {
    fn of(m: &fs::Metadata) -> Self {
        Self {
            device: m.dev(),
            inode: m.ino(),
            mode: m.mode(),
        }
    }
}

impl Node {
    fn read(path: &Path) -> io::Result<Self> {
        let m = fs::symlink_metadata(path)?;
        let link = m.is_symlink().then(|| fs::read_link(path)).transpose()?;
        Ok(Self {
            identity: Identity::of(&m),
            change: (m.ctime(), m.ctime_nsec()),
            link,
            entries: false,
        })
    }

    fn is_dir(&self) -> bool {
        self.identity.mode & libc::S_IFMT as u32 == libc::S_IFDIR as u32
    }
}

#[derive(Default)]
pub(super) struct Guard {
    nodes: BTreeMap<PathBuf, Node>,
    observation: Option<kqueue::Observation>,
}

impl Guard {
    pub(super) fn capture(inputs: &Inputs) -> io::Result<Self> {
        let mut guard = Self::default();
        for p in inputs.files.iter().chain(inputs.transient.values()) {
            guard.file(p)?;
        }
        for p in &inputs.directories {
            let resolved = guard
                .resolve(p, 0)?
                .ok_or_else(|| invalid("missing native search root"))?;
            let node = guard.nodes.get_mut(&resolved).unwrap();
            if !node.is_dir() {
                return Err(invalid("expected native search directory"));
            }
            node.entries = true;
        }
        for p in &inputs.missing {
            if guard.resolve(p, 0)?.is_some() {
                return Err(invalid("formerly missing native input exists"));
            }
        }
        guard.observation = Some(kqueue::Observation::start(&guard.nodes)?);
        Ok(guard)
    }

    fn file(&mut self, p: &Path) -> io::Result<()> {
        let resolved = self
            .resolve(p, 0)?
            .ok_or_else(|| invalid("missing native input"))?;
        if self.nodes[&resolved].identity.mode & libc::S_IFMT as u32 != libc::S_IFREG as u32 {
            return Err(invalid("expected a regular native input"));
        }
        Ok(())
    }

    fn resolve(&mut self, p: &Path, links: usize) -> io::Result<Option<PathBuf>> {
        if !p.is_absolute() || links > 40 {
            return Err(invalid("unsupported native path"));
        }
        let mut path = PathBuf::from("/");
        if !self.nodes.contains_key(&path) {
            self.nodes.insert(path.clone(), Node::read(&path)?);
        }
        for part in p.components() {
            if !self.nodes[&path].is_dir() {
                // A regular file cannot gain children without its entry changing.
                return Ok(None);
            }
            match part {
                Component::RootDir | Component::CurDir => continue,
                Component::ParentDir => {
                    path.pop();
                    continue;
                }
                Component::Normal(name) => path.push(name),
                Component::Prefix(_) => return Err(invalid("unsupported native path prefix")),
            }
            if !self.nodes.contains_key(&path) {
                match Node::read(&path) {
                    Ok(node) => {
                        self.nodes.insert(path.clone(), node);
                    }
                    Err(e) if e.kind() == io::ErrorKind::NotFound => {
                        self.nodes.get_mut(path.parent().unwrap()).unwrap().entries = true;
                        return Ok(None);
                    }
                    Err(e) => return Err(e),
                }
            }
            if let Some(link) = self.nodes[&path].link.as_ref() {
                let dest = path.parent().unwrap().join(link);
                let Some(resolved) = self.resolve(&dest, links + 1)? else {
                    return Ok(None);
                };
                path = resolved;
            }
        }
        Ok(Some(path))
    }

    pub(super) fn unchanged(&self) -> bool {
        self.observation.as_ref().is_some_and(|w| w.unchanged())
            && self.nodes.iter().all(|(p, before)| {
                Node::read(p).is_ok_and(|after| {
                    before.identity == after.identity
                        && before.link == after.link
                        && (before.is_dir() && !before.entries || before.change == after.change)
                })
            })
    }
}

mod kqueue {
    use super::*;
    use std::collections::BTreeSet;
    use std::ffi::CStr;
    use std::fs::File;
    use std::os::fd::{AsRawFd, FromRawFd};
    use std::os::unix::fs::OpenOptionsExt;
    use std::ptr;

    /// Watch the names that the linker will open, even if one is moved away and
    /// then put back. A write in an ancestor directory is usually just an output.
    pub(super) struct Observation {
        queue: File,
        files: Vec<(File, Option<blake3::Hash>)>,
    }

    impl Observation {
        pub(super) fn start(nodes: &BTreeMap<PathBuf, Node>) -> io::Result<Self> {
            // SAFETY: kqueue returns a new descriptor on success.
            let raw = unsafe { libc::kqueue() };
            if raw < 0 {
                return Err(io::Error::last_os_error());
            }
            let queue = unsafe { File::from_raw_fd(raw) };
            if unsafe { libc::fcntl(raw, libc::F_SETFD, libc::FD_CLOEXEC) } < 0 {
                return Err(io::Error::last_os_error());
            }
            let mut volumes = BTreeSet::new();
            let mut files = Vec::with_capacity(nodes.len());
            for (path, node) in nodes {
                // O_SYMLINK opens the actual directory entry when it is a symlink.
                let file = File::options()
                    .read(true)
                    .custom_flags(libc::O_EVTONLY | libc::O_SYMLINK)
                    .open(path)?;
                let fd = file.as_raw_fd();
                let meta = file.metadata()?;
                if Identity::of(&meta) != node.identity {
                    return Err(invalid("native input moved while being observed"));
                }
                if volumes.insert(meta.dev()) {
                    let mut fs = std::mem::MaybeUninit::<libc::statfs>::uninit();
                    if unsafe { libc::fstatfs(fd, fs.as_mut_ptr()) } < 0 {
                        return Err(io::Error::last_os_error());
                    }
                    // SAFETY: fstatfs initialized the structure, including the terminated name.
                    let fs = unsafe { fs.assume_init() };
                    if unsafe { CStr::from_ptr(fs.f_fstypename.as_ptr()) } != c"apfs"
                        || fs.f_flags & libc::MNT_LOCAL as u32 == 0
                    {
                        return Err(invalid("unverified native input filesystem"));
                    }
                }
                let mut flags = libc::NOTE_RENAME | libc::NOTE_DELETE | libc::NOTE_REVOKE;
                if node.entries || !node.is_dir() {
                    flags |= libc::NOTE_WRITE | libc::NOTE_LINK;
                    // Opening clang and reading archives can emit NOTE_ATTRIB.
                    // Regular files have a separate data generation and mode/ctime check.
                    if !meta.is_file() {
                        flags |= libc::NOTE_ATTRIB;
                    }
                }
                let event = libc::kevent {
                    ident: fd as libc::uintptr_t,
                    filter: libc::EVFILT_VNODE,
                    flags: libc::EV_ADD,
                    fflags: flags,
                    data: 0,
                    udata: ptr::null_mut(),
                };
                // SAFETY: both descriptors are live; event is the sole change.
                if unsafe { libc::kevent(raw, &event, 1, ptr::null_mut(), 0, ptr::null()) } < 0 {
                    return Err(io::Error::last_os_error());
                }
                let version = if meta.is_file() {
                    Some(
                        super::super::generation::data_version(&file, &meta)
                            .ok_or_else(|| invalid("unavailable native file write generation"))?,
                    )
                } else {
                    None
                };
                files.push((file, version));
            }
            Ok(Self { queue, files })
        }

        pub(super) fn unchanged(&self) -> bool {
            let mut queue = libc::pollfd {
                fd: self.queue.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            // An interruption or an error also makes this cold link ineligible.
            (unsafe { libc::poll(&mut queue, 1, 0) }) == 0
                && self.files.iter().all(|(file, version)| {
                    version.is_none()
                        || file
                            .metadata()
                            .ok()
                            .and_then(|m| super::super::generation::data_version(file, &m))
                            == *version
                })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;

    #[test]
    fn unrelated_output_is_allowed_but_a_restored_link_is_not() {
        let dir = tempfile::tempdir().unwrap();
        let archive = dir.path().join("archive");
        let link = dir.path().join("lib.a");
        let saved = dir.path().join("saved");
        fs::write(&archive, b"original").unwrap();
        symlink("archive", &link).unwrap();
        let mut inputs = Inputs::default();
        inputs.files.insert(link.clone());

        let guard = Guard::capture(&inputs).unwrap();
        fs::write(dir.path().join("output"), b"executable").unwrap();
        assert!(guard.unchanged());

        fs::rename(&link, &saved).unwrap();
        symlink("output", &link).unwrap();
        fs::remove_file(&link).unwrap();
        fs::rename(saved, link).unwrap();
        assert!(!guard.unchanged());

        let guard = Guard::capture(&inputs).unwrap();
        fs::write(&archive, b"modified").unwrap();
        fs::write(&archive, b"original").unwrap();
        assert!(!guard.unchanged());
    }

    #[test]
    fn a_temporarily_present_search_result_invalidates_the_link() {
        let dir = tempfile::tempdir().unwrap();
        let missing = dir.path().join("lib.a");
        let mut inputs = Inputs::default();
        inputs.missing.insert(missing.clone());
        let guard = Guard::capture(&inputs).unwrap();
        fs::write(&missing, b"found").unwrap();
        fs::remove_file(missing).unwrap();
        assert!(!guard.unchanged());
    }
}
