//! Share a bundled Clippy driver's ordinary dep-info checksum with that driver.
//! A process-local hint is available only after Cargo actually read the executable.

use super::BuildContext;
use super::fingerprint::dep_info::{Checksum, ChecksumAlgo};
use cargo_util::ProcessBuilder;
use std::fs::File;
use std::io;
use std::path::Path;

pub(super) const FDS_ENV: &str = "CARGO_OHM_CLIPPY_DRIVER_HASH_FDS";
pub(super) const VERSION_ENV: &str = "CARGO_OHM_CLIPPY_DRIVER_HASH_VERSION";

pub(super) struct ClippyDriverChecksum {
    #[cfg(all(target_os = "linux", target_arch = "x86_64"))]
    driver: linux::Driver,
}

impl ClippyDriverChecksum {
    pub(super) fn new(_bcx: &BuildContext<'_, '_>) -> Option<Self> {
        #[cfg(all(target_os = "linux", target_arch = "x86_64"))]
        {
            Some(Self {
                driver: linux::Driver::new(_bcx)?,
            })
        }
        #[cfg(not(all(target_os = "linux", target_arch = "x86_64")))]
        {
            None
        }
    }

    pub(super) fn read(
        &self,
        _path: &Path,
        algo: ChecksumAlgo,
        file: File,
        buffer: &mut [u8],
    ) -> io::Result<Checksum> {
        #[cfg(all(target_os = "linux", target_arch = "x86_64"))]
        if algo == ChecksumAlgo::Blake3
            && _path == self.driver.path
            && self.driver.proof.get().is_none()
        {
            // Keep the same open file throughout leasing, hashing, and handoff.
            let before = linux::read_lease(&file);
            let sum = Checksum::compute(algo, &file, buffer)?;
            if let Some(identity) = before {
                let _ = self.driver.record(file, identity, &sum);
            }
            return Ok(sum);
        }
        Checksum::compute(algo, file, buffer)
    }

    pub(super) fn pass_to(&self, _process: &mut ProcessBuilder) {
        #[cfg(all(target_os = "linux", target_arch = "x86_64"))]
        self.driver.pass_to(_process);
    }
}

#[cfg(all(target_os = "linux", target_arch = "x86_64"))]
mod linux {
    use super::*;
    use crate::compiler::CompileKind;
    use rustix::fs::{MemfdFlags, SealFlags, fcntl_add_seals, memfd_create};
    use std::ffi::OsStr;
    use std::fs::Metadata;
    use std::mem::MaybeUninit;
    use std::os::fd::AsRawFd;
    use std::os::unix::fs::{FileExt, MetadataExt};
    use std::path::PathBuf;
    use std::sync::{Arc, OnceLock, mpsc};
    use std::time::Duration;

    pub(super) struct Driver {
        pub path: PathBuf,
        pub proof: OnceLock<Proof>,
    }

    pub(super) struct Proof {
        record: Arc<File>,
        executable: Arc<File>,
        identity: [u64; 7],
        _monitor: mpsc::Sender<()>,
    }

    fn identity(metadata: Metadata) -> [u64; 7] {
        [
            metadata.dev(),
            metadata.ino(),
            metadata.len(),
            metadata.mtime() as u64,
            metadata.mtime_nsec() as u64,
            metadata.ctime() as u64,
            metadata.ctime_nsec() as u64,
        ]
    }

    // A read lease also rules out a writable mapping established before Cargo read the ELF.
    pub(super) fn read_lease(file: &File) -> Option<[u64; 7]> {
        // A local lease cannot exclude writes made by a different network filesystem client.
        if !matches!(
            rustix::fs::fstatfs(file).ok()?.f_type as libc::c_long,
            libc::EXT4_SUPER_MAGIC
                | libc::XFS_SUPER_MAGIC
                | libc::BTRFS_SUPER_MAGIC
                | libc::TMPFS_MAGIC
        ) {
            return None;
        }
        let mut action = MaybeUninit::<libc::sigaction>::uninit();
        let fd = file.as_raw_fd();
        const F_SETSIG_X86_64: libc::c_int = 10;
        // SAFETY: query the disposition; use the normally ignored SIGURG only if it has
        // no handler. F_SETSIG is the Linux x86_64 ABI constant.
        unsafe {
            if libc::sigaction(libc::SIGURG, std::ptr::null(), action.as_mut_ptr()) != 0
                || !matches!(
                    action.assume_init().sa_sigaction,
                    libc::SIG_DFL | libc::SIG_IGN
                )
                || libc::fcntl(fd, F_SETSIG_X86_64, libc::SIGURG) != 0
                || libc::fcntl(fd, libc::F_SETLEASE, libc::F_RDLCK) != 0
            {
                return None;
            }
        }
        file.metadata().ok().filter(Metadata::is_file).map(identity)
    }

    fn leased(file: &File) -> bool {
        // SAFETY: F_GETLEASE queries only the open file description.
        unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETLEASE) == libc::F_RDLCK }
    }

    impl Driver {
        pub(super) fn new(bcx: &BuildContext<'_, '_>) -> Option<Self> {
            if !bcx.gctx.cli_unstable().ohm_defaults()
                || bcx.gctx.get_env_os(VERSION_ENV) != Some(OsStr::new("1"))
                || !bcx.rustc().has_bundled_clippy_wrapper(
                    bcx.gctx,
                    &bcx.target_data.info(CompileKind::Host).sysroot,
                )
            {
                return None;
            }
            Some(Self {
                path: bcx
                    .rustc()
                    .workspace_wrapper
                    .as_ref()?
                    .canonicalize()
                    .ok()?,
                proof: OnceLock::new(),
            })
        }

        pub(super) fn record(&self, file: File, before: [u64; 7], sum: &Checksum) -> Option<()> {
            if !leased(&file)
                || file.metadata().ok().map(identity) != Some(before)
                || self.path.metadata().ok().map(identity) != Some(before)
            {
                return None;
            }
            let mut bytes = Vec::with_capacity(104);
            bytes.extend_from_slice(b"OHMCLP01");
            bytes.extend_from_slice(&u64::from(std::process::id()).to_le_bytes());
            for field in before {
                bytes.extend_from_slice(&field.to_le_bytes());
            }
            bytes.extend_from_slice(sum.value());
            let record = File::from(
                memfd_create(
                    "cargo-clippy-driver-hash",
                    MemfdFlags::CLOEXEC | MemfdFlags::ALLOW_SEALING,
                )
                .ok()?,
            );
            record.write_all_at(&bytes, 0).ok()?;
            fcntl_add_seals(
                &record,
                SealFlags::SEAL | SealFlags::SHRINK | SealFlags::GROW | SealFlags::WRITE,
            )
            .ok()?;
            let executable = Arc::new(file);
            let watch = executable.clone();
            let (stop, shutdown) = mpsc::channel();
            // A writer requesting an in-place update breaks the lease. Release it
            // promptly even if all Cargo's scheduling threads are waiting on long jobs.
            std::thread::Builder::new()
                .name("cargo-clippy-lease".into())
                .spawn(move || {
                    while let Err(mpsc::RecvTimeoutError::Timeout) =
                        shutdown.recv_timeout(Duration::from_millis(25))
                    {
                        if !leased(&watch) {
                            // SAFETY: release our lease on the same still-open file.
                            unsafe {
                                libc::fcntl(watch.as_raw_fd(), libc::F_SETLEASE, libc::F_UNLCK);
                            }
                            break;
                        }
                    }
                })
                .ok()?;
            self.proof
                .set(Proof {
                    record: Arc::new(record),
                    executable,
                    identity: before,
                    _monitor: stop,
                })
                .ok()
        }

        pub(super) fn pass_to(&self, process: &mut ProcessBuilder) {
            let Some(proof) = self.proof.get() else {
                return;
            };
            if process.get_program() != self.path.as_os_str()
                || !leased(&proof.executable)
                || self.path.metadata().ok().map(identity) != Some(proof.identity)
            {
                return;
            }
            tracing::trace!(path = ?self.path, "passing verified Clippy driver checksum");
            process
                .env(
                    FDS_ENV,
                    format!(
                        "{},{}",
                        proof.record.as_raw_fd(),
                        proof.executable.as_raw_fd()
                    ),
                )
                .inherit_file(proof.record.clone())
                .inherit_file(proof.executable.clone());
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        use std::fs;
        use tempfile::tempdir;

        fn fixture(path: &Path) -> ClippyDriverChecksum {
            ClippyDriverChecksum {
                driver: Driver {
                    path: path.into(),
                    proof: OnceLock::new(),
                },
            }
        }

        fn read(handoff: &ClippyDriverChecksum, path: &Path) -> Checksum {
            handoff
                .read(
                    path,
                    ChecksumAlgo::Blake3,
                    File::open(path).unwrap(),
                    &mut [0; 64],
                )
                .unwrap()
        }

        #[test]
        fn passes_only_the_checked_inode_and_retains_the_ordinary_checksum() {
            let tmp = tempdir().unwrap();
            let path = tmp.path().join("clippy-driver");
            fs::write(&path, b"first").unwrap();
            if read_lease(&File::open(&path).unwrap()).is_none() {
                // File leases may be disabled on this filesystem.
                return;
            }
            let handoff = fixture(&path);
            let sum = read(&handoff, &path);
            assert_eq!(sum.value(), blake3::hash(b"first").as_bytes());
            let proof = handoff.driver.proof.get().unwrap();
            let mut bytes = [0; 104];
            proof.record.read_exact_at(&mut bytes, 0).unwrap();
            assert_eq!(&bytes[..8], b"OHMCLP01");
            assert_eq!(&bytes[8..16], &u64::from(std::process::id()).to_le_bytes());
            assert_eq!(&bytes[72..], sum.value());
            assert_eq!(
                rustix::fs::fcntl_get_seals(&*proof.record).unwrap(),
                SealFlags::GROW | SealFlags::SHRINK | SealFlags::WRITE | SealFlags::SEAL
            );
            let mut child = ProcessBuilder::new(&path);
            handoff.pass_to(&mut child);
            assert!(child.get_env(FDS_ENV).is_some());
            let mut other = ProcessBuilder::new(tmp.path().join("other"));
            handoff.pass_to(&mut other);
            assert!(other.get_env(FDS_ENV).is_none());
            let replacement = tmp.path().join("replacement");
            fs::write(&replacement, b"other").unwrap();
            fs::rename(&replacement, &path).unwrap();
            let mut changed = ProcessBuilder::new(&path);
            handoff.pass_to(&mut changed);
            assert!(changed.get_env(FDS_ENV).is_none());
            assert_eq!(
                read(&handoff, &path).value(),
                blake3::hash(b"other").as_bytes()
            );
        }

        #[test]
        fn a_concurrent_writer_declines_or_breaks_the_handoff() {
            use std::os::unix::fs::PermissionsExt;
            use std::time::Instant;

            let tmp = tempdir().unwrap();
            let path = tmp.path().join("clippy-driver");
            // Use an interpreter so Linux allows writing the checked file while
            // the child, which has inherited the actual proof, remains alive.
            let script = br#"#!/bin/sh
set -eu
record=${CARGO_OHM_CLIPPY_DRIVER_HASH_FDS%,*}
image=${CARGO_OHM_CLIPPY_DRIVER_HASH_FDS#*,}
test -r /proc/self/fd/"$record"
test -r /proc/self/fd/"$image"
printf '%s' "$CARGO_OHM_CLIPPY_DRIVER_HASH_FDS" > "$1.tmp"
mv "$1.tmp" "$1"
i=0
while test ! -e "$2" && test "$i" -lt 300; do i=$((i + 1)); sleep .01; done
test -e "$2"
"#;
            fs::write(&path, script).unwrap();
            fs::set_permissions(&path, fs::Permissions::from_mode(0o755)).unwrap();
            let handoff = fixture(&path);
            let writer = File::options().write(true).open(&path).unwrap();
            assert_eq!(
                read(&handoff, &path).value(),
                blake3::hash(script).as_bytes()
            );
            assert!(handoff.driver.proof.get().is_none());
            drop(writer);
            read(&handoff, &path);
            let Some(proof) = handoff.driver.proof.get() else {
                return;
            };
            let mut child = ProcessBuilder::new(&path);
            handoff.pass_to(&mut child);
            let received = tmp.path().join("received");
            let finish = tmp.path().join("finish");
            child.arg(&received).arg(&finish);
            let child = std::thread::spawn(move || child.exec_with_output().unwrap());
            let deadline = Instant::now() + Duration::from_secs(3);
            while !received.exists() {
                assert!(Instant::now() < deadline, "child must inherit the proof");
                std::thread::sleep(Duration::from_millis(1));
            }
            let expected = format!(
                "{},{}",
                proof.record.as_raw_fd(),
                proof.executable.as_raw_fd()
            );
            assert_eq!(fs::read_to_string(&received).unwrap(), expected);
            let update = path.clone();
            let (done, written) = mpsc::channel();
            std::thread::spawn(move || {
                let start = Instant::now();
                fs::write(update, b"later").unwrap();
                done.send(start.elapsed()).unwrap();
            });
            let elapsed = written
                .recv_timeout(Duration::from_secs(3))
                .expect("writer must not wait for the kernel lease expiry");
            assert!(!leased(&proof.executable));
            let mut changed = ProcessBuilder::new(&path);
            handoff.pass_to(&mut changed);
            assert!(changed.get_env(FDS_ENV).is_none());
            assert_eq!(
                read(&handoff, &path).value(),
                blake3::hash(b"later").as_bytes()
            );
            fs::write(finish, b"").unwrap();
            child.join().unwrap();
            eprintln!(
                "blocking writer completed in {} microseconds",
                elapsed.as_micros()
            );
        }
    }
}
