//! A bounded Linux writer for a privately authenticated, already-present normal executable.
use std::ffi::OsStr;
use std::fs::{self, File, OpenOptions};
use std::io;
use std::os::fd::{AsRawFd, RawFd};
use std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt};
use std::path::Path;
use std::{mem, ptr, slice};

struct Map(*mut libc::c_void, usize);

impl Map {
    fn new(fd: RawFd, n: usize, writable: bool) -> io::Result<Self> {
        let prot = libc::PROT_READ | if writable { libc::PROT_WRITE } else { 0 };
        let p = unsafe { libc::mmap(ptr::null_mut(), n, prot, libc::MAP_SHARED, fd, 0) };
        if p == libc::MAP_FAILED {
            return Err(io::Error::last_os_error());
        }
        Ok(Self(p, n))
    }

    fn data(&self) -> &[u8] {
        unsafe { slice::from_raw_parts(self.0.cast(), self.1) }
    }
}

impl Drop for Map {
    fn drop(&mut self) {
        unsafe { libc::munmap(self.0, self.1); }
    }
}

fn supported(m: &fs::Metadata) -> bool {
    m.is_file() && m.nlink() == 1 && m.uid() == unsafe { libc::geteuid() }
        && m.mode() & 0o7000 == 0 && m.mode() & 0o700 == 0o700
        && m.len() != 0 && m.len() <= 500 * 1024 * 1024
}

fn ordinary_fs(fd: RawFd) -> io::Result<libc::c_long> {
    let mut stat = mem::MaybeUninit::<libc::statfs>::uninit();
    if unsafe { libc::fstatfs(fd, stat.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { stat.assume_init() }.f_type)
}

// The upstream receiver must additionally bind actual file kinds, source bytes, searched names,
// loader configuration and the otherwise-transparent two compiler/GCC private operands.
fn supported_args(args: &[std::ffi::OsString]) -> bool {
    let mut it=args.iter().map(|s| s.to_str());
    while let Some(s)=it.next() {
        let Some(s)=s else {return false};
        match s {
            "-o" | "-plugin" | "-dynamic-linker" => if it.next().flatten().is_none() {return false},
            "-m" => if it.next().flatten()!=Some("elf_x86_64") {return false},
            "-z" => if !matches!(it.next().flatten(), Some("now"|"relro"|"noexecstack")) {return false},
            "--build-id" | "--eh-frame-hdr" | "--hash-style=gnu" | "--as-needed" | "--no-as-needed" |
            "--push-state" | "--pop-state" | "--gc-sections" | "-Bstatic" | "-Bdynamic" | "-pie" => {}
            _ if s.starts_with("-L") || s.starts_with("-l") || s.starts_with("-plugin-opt=") => {}
            _ if !s.starts_with(['-', '@']) && matches!(Path::new(s).extension().and_then(|p| p.to_str()), Some("o"|"a"|"rlib")) => {}
            _ => return false,
        }
    }
    true
}

/// Exercise output publication only. The caller independently certifies inputs, width and cache provenance.
pub fn replay(args: &[std::ffi::OsString], width: usize, sealed: File) -> io::Result<&'static str> {
    if !supported_args(args) { return Ok("unsupported-arguments") }
    if std::env::vars_os().any(|(k,_)| k.to_string_lossy().starts_with("WILD_")) {return Ok("wild-options")}
    if width < 2 {
        return Ok("single-worker");
    }
    let flags = unsafe { libc::fcntl(sealed.as_raw_fd(),libc::F_GET_SEALS) };
    const MASK: libc::c_int = libc::F_SEAL_WRITE | libc::F_SEAL_GROW | libc::F_SEAL_SHRINK | libc::F_SEAL_SEAL;
    if flags < 0 || flags & MASK != MASK {
        return Ok("unsealed-input");
    }
    let out: Vec<_> = args.windows(2).filter(|a| a[0]==OsStr::new("-o")).collect();
    if out.len()!=1 { return Ok("output-grammar") }
    let out=Path::new(&out[0][1]);
    let m=match fs::symlink_metadata(out) { Ok(m) if supported(&m) => m, _ => return Ok("output-type") };
    if m.len()!=sealed.metadata()?.len() { return Ok("different-size") }
    // The old target must already exist. This catches symlinks, FIFOs and ETXTBSY; stock runs on any refusal.
    let read=match OpenOptions::new().read(true).custom_flags(libc::O_NOFOLLOW|libc::O_NONBLOCK|libc::O_NOATIME).open(out) {
        Ok(file)=>file,Err(_)=>return Ok("output-open")
    };
    let read_fd=read.as_raw_fd();
    let curr=read.metadata()?;
    if !supported(&curr) || (curr.dev(),curr.ino(),curr.len())!=(m.dev(),m.ino(),m.len()) {
        return Ok("output-race")
    }
    let fs_type=ordinary_fs(read_fd)?;
    if ![libc::EXT4_SUPER_MAGIC,libc::XFS_SUPER_MAGIC,libc::TMPFS_MAGIC].contains(&fs_type) {
        return Ok("unsupported-fs")
    }
    if unsafe { libc::flistxattr(read_fd,ptr::null_mut(),0) } != 0 {
        return Ok("output-xattrs")
    }
    let n=curr.len() as usize;
    let source=Map::new(sealed.as_raw_fd(),n,false)?;
    // A concurrently truncated, ordinary output must not SIGBUS this validation pass.
    let mut block=vec![0;64*1024];
    for (i, expected) in source.data().chunks(64*1024).enumerate() {
        let block=&mut block[..expected.len()];
        let Ok(())=read.read_exact_at(block,(i*64*1024) as u64) else {return Ok("output-read")};
        if block!=expected {return Ok("output-digest-mismatch")}
    }
    let file=match OpenOptions::new().read(true).write(true).custom_flags(libc::O_NOFOLLOW|libc::O_NONBLOCK).open(out) {
        Ok(file)=>file,Err(_)=>return Ok("output-open")
    };
    let actual=file.metadata()?;
    let stamp=|m:&fs::Metadata| (m.dev(),m.ino(),m.mode(),m.nlink(),m.len(),m.ctime(),m.ctime_nsec());
    if stamp(&actual)!=stamp(&curr) {return Ok("output-race")}
    let fd=file.as_raw_fd();
    file.set_len(n as u64)?;
    if fs_type!=libc::TMPFS_MAGIC {
        // Stock's implicit preallocation on ext4/XFS is best-effort.
        unsafe { libc::fallocate(fd,0,0,n as libc::off_t); }
    }
    let target=Map::new(fd,n,true)?;
    unsafe {
        ptr::copy_nonoverlapping(source.0.cast::<u8>(),target.0.cast::<u8>(),n);
        let mode=file.metadata()?.mode();
        libc::fchmod(fd, mode | ((mode & 0o444) >> 2));
    }
    drop(target);
    let now=fs::symlink_metadata(out)?;
    if (now.dev(),now.ino(),now.len(),now.nlink())!=(curr.dev(),curr.ino(),curr.len(),1) {
        return Ok("output-race-after")
    }
    Ok("hit")
}
