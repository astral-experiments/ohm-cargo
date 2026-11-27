//! Share a bundled Clippy driver's ordinary dep-info checksum with that driver.
//! A process-local hint is available only after Cargo actually read the executable.

use super::BuildContext;
use super::fingerprint::dep_info::{Checksum, ChecksumAlgo};
use cargo_util::ProcessBuilder;
use std::fs::File;
use std::io::{self, Read};
use std::path::Path;
use std::sync::OnceLock;

pub(super) const FDS_ENV: &str = "CARGO_OHM_CLIPPY_DRIVER_HASH_FDS";
pub(super) const VERSION_ENV: &str = "CARGO_OHM_CLIPPY_DRIVER_HASH_VERSION";

pub(super) struct ClippyDriverChecksum {
    #[cfg(all(target_os = "linux", target_arch = "x86_64"))]
    driver: linux::Driver,
    recording: OnceLock<()>,
    image: OnceLock<(Vec<u8>, Checksum)>,
}

impl ClippyDriverChecksum {
    pub(super) fn new(_bcx: &BuildContext<'_, '_>) -> Option<Self> {
        #[cfg(all(target_os = "linux", target_arch = "x86_64"))]
        {
            Some(Self {
                driver: linux::Driver::new(_bcx)?,
                recording: OnceLock::new(),
                image: OnceLock::new(),
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
            let sum = self.read_initial(&file, buffer)?;
            if let Some(identity) = before {
                let _ = self.driver.record(file, identity, &sum);
            }
            return Ok(sum);
        }
        Checksum::compute(algo, file, buffer)
    }

    /// Seed late comparisons from the initial freshness read. Read directly
    /// into the bounded image so a build without rechecks needn't copy it.
    #[cfg(all(target_os = "linux", target_arch = "x86_64"))]
    fn read_initial(&self, mut file: &File, buffer: &mut [u8]) -> io::Result<Checksum> {
        let algo = ChecksumAlgo::Blake3;
        let mut bytes = Vec::new();
        let Some(meta) = file
            .metadata()
            .ok()
            .filter(|meta| meta.is_file() && self.can_compare(&self.driver.path, algo, meta.len()))
        else {
            return Checksum::compute(algo, file, buffer);
        };
        if self.recording.set(()).is_err() || bytes.try_reserve_exact(meta.len() as usize).is_err()
        {
            return Checksum::compute(algo, file, buffer);
        }
        while bytes.len() < bytes.capacity() {
            if rustix::io::read(file, rustix::buffer::spare_capacity(&mut bytes))? == 0 {
                break;
            }
        }
        if bytes.len() == bytes.capacity() {
            let n = file.read(buffer)?;
            if n != 0 {
                // Preserve the observed stream if the file grew.
                let stream = bytes.as_slice().chain(&buffer[..n]).chain(file);
                return Checksum::compute(algo, stream, &mut [0; 8192]);
            }
        }
        let sum = Checksum::new(algo, blake3::hash(&bytes).into());
        let _ = self.image.set((bytes, sum));
        Ok(sum)
    }

    pub(super) fn can_compare(&self, _path: &Path, _algo: ChecksumAlgo, _len: u64) -> bool {
        #[cfg(all(target_os = "linux", target_arch = "x86_64"))]
        {
            _algo == ChecksumAlgo::Blake3 && _path == self.driver.path && _len <= 32 * 1024 * 1024
        }
        #[cfg(not(all(target_os = "linux", target_arch = "x86_64")))]
        false
    }

    /// Many workspace units can recheck this same executable after their prerequisites.
    /// Retain at most one bounded image per build and still read each fresh file through EOF.
    /// This makes no assumptions about writes, leases, or even inode identity.
    pub(super) fn compare(
        &self,
        mut file: impl Read,
        len: u64,
        buffer: &mut [u8],
    ) -> io::Result<Checksum> {
        let algo = ChecksumAlgo::Blake3;
        if let Some((bytes, sum)) = self.image.get() {
            let mut matched = 0;
            loop {
                let n = file.read(buffer)?;
                if n == 0 {
                    return Ok(if matched == bytes.len() {
                        *sum
                    } else {
                        Checksum::new(algo, blake3::hash(&bytes[..matched]).into())
                    });
                }
                if !bytes[matched..].starts_with(&buffer[..n]) {
                    // Hash precisely the stream we observed, without seeking or reopening.
                    let stream = (&bytes[..matched]).chain(&buffer[..n]).chain(file);
                    return Checksum::compute(algo, stream, &mut [0; 8192]);
                }
                matched += n;
            }
        }
        let mut bytes = Vec::new();
        if self.recording.set(()).is_err() || bytes.try_reserve_exact(len as usize).is_err() {
            return Checksum::compute(algo, file, buffer);
        }
        loop {
            let n = file.read(buffer)?;
            if n == 0 {
                let sum = Checksum::new(algo, blake3::hash(&bytes).into());
                let _ = self.image.set((bytes, sum));
                return Ok(sum);
            }
            if n > len as usize - bytes.len() {
                // The file grew after the metadata check. Keep the allocation bounded.
                let stream = bytes.as_slice().chain(&buffer[..n]).chain(file);
                return Checksum::compute(algo, stream, &mut [0; 8192]);
            }
            bytes.extend_from_slice(&buffer[..n]);
        }
    }

    pub(super) fn dispatch_to(&self, _process: &mut ProcessBuilder, _dep_info: &Path) {
        #[cfg(all(target_os = "linux", target_arch = "x86_64"))]
        {
            if _process.get_program() == self.driver.path.as_os_str() {
                self.driver.prepare_if_needed(_process, _dep_info);
                self.driver.pass_to(_process);
            }
        }
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
        attempted: OnceLock<()>,
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
                attempted: OnceLock::new(),
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

        pub(super) fn prepare_if_needed(&self, process: &ProcessBuilder, dep_info: &Path) {
            if self.proof.get().is_some() || self.attempted.get().is_some() {
                return;
            }
            // A dirty prerequisite can cause Cargo to skip this unit's ordinary
            // freshness reads. Fill on actual dispatch only if it previously
            // reported a BLAKE3 read of this exact driver and will emit dep-info.
            let mut incremental = false;
            let mut blake3 = false;
            let mut dep_output = false;
            for arg in process.get_args().filter_map(|arg| arg.to_str()) {
                if let Some(value) = arg.trim_start_matches("-C").strip_prefix("incremental=") {
                    incremental = !value.is_empty();
                }
                if let Some(value) = arg
                    .trim_start_matches("-Z")
                    .strip_prefix("checksum-hash-algorithm=")
                {
                    blake3 = value == "blake3";
                }
                if let Some(values) = arg.strip_prefix("--emit=") {
                    dep_output = values.split(',').any(|value| value == "dep-info");
                }
            }
            if !incremental || !blake3 || !dep_output {
                return;
            }
            let Ok(bytes) = cargo_util::paths::read_regular_bounded(dep_info, 1024 * 1024) else {
                return;
            };
            let Some(history) =
                crate::compiler::fingerprint::dep_info::EncodedDepInfo::parse(&bytes)
            else {
                return;
            };
            if !history.files.iter().any(|(_, path, input)| {
                path == &self.path
                    && input.as_ref().is_some_and(|(_, value)| {
                        value
                            .parse::<Checksum>()
                            .is_ok_and(|sum| sum.algo() == ChecksumAlgo::Blake3)
                    })
            }) {
                return;
            }
            // Multiple units can reach dispatch together. The old dep-info only
            // establishes that the read is useful. Always hash today's open ELF.
            self.attempted.get_or_init(|| {
                use std::os::unix::fs::OpenOptionsExt;
                let Ok(file) = File::options()
                    .read(true)
                    .custom_flags(libc::O_NONBLOCK | libc::O_NOCTTY)
                    .open(&self.path)
                else {
                    return;
                };
                let Some(before) = read_lease(&file) else {
                    return;
                };
                let Ok(sum) = Checksum::compute(ChecksumAlgo::Blake3, &file, &mut [0; 64 * 1024])
                else {
                    return;
                };
                let _ = self.record(file, before, &sum);
            });
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
                recording: OnceLock::new(),
                image: OnceLock::new(),
                driver: Driver {
                    path: path.into(),
                    proof: OnceLock::new(),
                    attempted: OnceLock::new(),
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
        fn recheck_reads_identical_replaced_and_resized_files_through_eof() {
            let tmp = tempdir().unwrap();
            let path = tmp.path().join("clippy-driver");
            let handoff = fixture(&path);
            assert!(handoff.can_compare(&path, ChecksumAlgo::Blake3, 6));
            assert!(!handoff.can_compare(&path, ChecksumAlgo::Blake3, 1 << 26));
            assert!(!handoff.can_compare(&path, ChecksumAlgo::Sha256, 6));
            assert!(!handoff.can_compare(tmp.path(), ChecksumAlgo::Blake3, 6));
            for data in [
                "abcdef", "abcdef", "abcde!", "!!cdef", "abc", "", "abcdef!", "abcdef",
            ] {
                let replacement = tmp.path().join("replacement");
                fs::write(&replacement, data).unwrap();
                fs::rename(&replacement, &path).unwrap();
                let sum = handoff
                    .compare(File::open(&path).unwrap(), 6, &mut [0; 2])
                    .unwrap();
                assert_eq!(sum.value(), blake3::hash(data.as_bytes()).as_bytes());
            }
            assert_eq!(handoff.image.get().unwrap().0, b"abcdef");
            assert!(handoff.driver.proof.get().is_none());
        }

        #[test]
        fn initial_read_seeds_rechecks_without_trusting_the_original_file() {
            let tmp = tempdir().unwrap();
            let path = tmp.path().join("clippy-driver");
            let handoff = fixture(&path);
            fs::write(&path, b"first").unwrap();
            let sum = read(&handoff, &path);
            assert_eq!(sum.value(), blake3::hash(b"first").as_bytes());
            assert_eq!(handoff.image.get().unwrap().0, b"first");
            for data in ["first", "other", "", "longer", "first"] {
                let sum = handoff.compare(data.as_bytes(), 5, &mut [0; 2]).unwrap();
                assert_eq!(sum.value(), blake3::hash(data.as_bytes()).as_bytes());
            }
        }

        #[test]
        fn incomplete_rechecks_do_not_publish_or_reuse_a_checksum() {
            struct Interrupted;
            impl Read for Interrupted {
                fn read(&mut self, _: &mut [u8]) -> io::Result<usize> {
                    Err(io::ErrorKind::Interrupted.into())
                }
            }
            let path = Path::new("clippy-driver");
            let data = b"abcdef".as_slice();
            for seed in [true, false] {
                let handoff = fixture(path);
                if seed {
                    handoff.compare(data, 6, &mut [0; 2]).unwrap();
                }
                let err = handoff
                    .compare(data.chain(Interrupted), 6, &mut [0; 2])
                    .unwrap_err();
                assert_eq!(err.kind(), io::ErrorKind::Interrupted);
                assert_eq!(handoff.image.get().is_some(), seed);
                let sum = handoff.compare(data, 6, &mut [0; 2]).unwrap();
                assert_eq!(sum.value(), blake3::hash(data).as_bytes());
            }
            let handoff = fixture(path);
            let sum = handoff.compare(data, 4, &mut [0; 2]).unwrap();
            assert!(handoff.image.get().is_none());
            assert_eq!(sum.value(), blake3::hash(data).as_bytes());
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
            handoff.driver.pass_to(&mut child);
            assert!(child.get_env(FDS_ENV).is_some());
            let mut other = ProcessBuilder::new(tmp.path().join("other"));
            handoff.driver.pass_to(&mut other);
            assert!(other.get_env(FDS_ENV).is_none());
            let replacement = tmp.path().join("replacement");
            fs::write(&replacement, b"other").unwrap();
            fs::rename(&replacement, &path).unwrap();
            let mut changed = ProcessBuilder::new(&path);
            handoff.driver.pass_to(&mut changed);
            assert!(changed.get_env(FDS_ENV).is_none());
            assert_eq!(
                read(&handoff, &path).value(),
                blake3::hash(b"other").as_bytes()
            );
        }

        #[test]
        fn a_skipped_freshness_read_needs_matching_history_and_current_options() {
            use crate::compiler::fingerprint::dep_info::{DepInfoPathType, EncodedDepInfo};

            let tmp = tempdir().unwrap();
            let path = tmp.path().join("clippy-driver");
            let history = tmp.path().join("dep-info");
            fs::write(&path, b"actual image").unwrap();
            let handoff = fixture(&path);
            let command = |incremental: bool| {
                let mut cmd = ProcessBuilder::new(&path);
                cmd.arg("--emit=dep-info,metadata")
                    .arg("-Zchecksum-hash-algorithm=blake3");
                if incremental {
                    cmd.arg("-C").arg("incremental=target/incremental");
                }
                cmd
            };
            let mut actual = command(true);
            fs::write(&history, b"malformed").unwrap();
            handoff.dispatch_to(&mut actual, &history);
            assert!(actual.get_env(FDS_ENV).is_none());
            let mut recorded = EncodedDepInfo::default();
            let false_old_sum = Checksum::new(ChecksumAlgo::Blake3, [0x99; 32]);
            recorded.files.push((
                DepInfoPathType::BuildRootRelative,
                path.clone(),
                Some((12, false_old_sum.to_string())),
            ));
            fs::write(&history, recorded.serialize().unwrap()).unwrap();
            let mut disabled = command(false);
            handoff.dispatch_to(&mut disabled, &history);
            assert!(disabled.get_env(FDS_ENV).is_none());
            assert!(handoff.driver.attempted.get().is_none());
            handoff.dispatch_to(&mut actual, &history);
            let Some(proof) = handoff.driver.proof.get() else {
                return;
            };
            assert!(actual.get_env(FDS_ENV).is_some());
            let mut sum = [0; 32];
            proof.record.read_exact_at(&mut sum, 72).unwrap();
            assert_eq!(&sum, blake3::hash(b"actual image").as_bytes());
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
            handoff.driver.pass_to(&mut child);
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
            handoff.driver.pass_to(&mut changed);
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
