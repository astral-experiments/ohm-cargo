use ar_archive_writer::{ArchiveKind, DEFAULT_OBJECT_READER, NewArchiveMember, ObjectReader, write_archive_to_stream};
use memmap2::Mmap;
use std::ffi::{CStr, c_char, c_void};
use std::fs::{self, DirBuilder, File, OpenOptions};
use std::io::{self, BufWriter, Seek, SeekFrom, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{DirBuilderExt, FileExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

type Sink = unsafe extern "C" fn(*mut c_void, *const c_char) -> *mut c_void;
type Error = unsafe extern "C" fn(*const c_char) -> *mut c_void;
type Scan = unsafe extern "C" fn(*const u8, usize, *mut c_void, Sink, Error) -> *mut c_void;
static SCAN: OnceLock<Scan> = OnceLock::new();
static READER: ObjectReader = ObjectReader { get_symbols: symbols, ..DEFAULT_OBJECT_READER };

unsafe extern "C" fn accept(state: *mut c_void, name: *const c_char) -> *mut c_void {
    let sink = unsafe { &mut *(state as *mut &mut dyn FnMut(&[u8]) -> io::Result<()>) };
    match sink(unsafe { CStr::from_ptr(name) }.to_bytes()) {
        Ok(()) => std::ptr::null_mut(),
        Err(err) => Box::into_raw(Box::new(err)).cast(),
    }
}

unsafe extern "C" fn failure(message: *const c_char) -> *mut c_void {
    let message = unsafe { CStr::from_ptr(message) }.to_string_lossy();
    Box::into_raw(Box::new(io::Error::other(message.into_owned()))).cast()
}

fn symbols(buf: &[u8], mut sink: &mut dyn FnMut(&[u8]) -> io::Result<()>) -> io::Result<bool> {
    let err = unsafe {
        SCAN.get().unwrap()(buf.as_ptr(), buf.len(), (&raw mut sink).cast(), accept, failure)
    };
    if err.is_null() { Ok(true) } else { Err(unsafe { *Box::from_raw(err.cast::<io::Error>()) }) }
}

fn load_qualified_driver() -> io::Result<()> {
    // The study launcher verifies the driver and LLVM file digests before invocation.
    let path = std::env::var("LD_PRELOAD").map_err(io::Error::other)?;
    let maps = fs::read_to_string("/proc/self/maps")?;
    let mut bases = maps.lines().filter_map(|line| {
        let f: Vec<_> = line.split_whitespace().collect();
        (f.len() == 6 && f[2] == "00000000" && f[5] == path)
            .then(|| usize::from_str_radix(f[0].split('-').next()?, 16).ok()).flatten()
    });
    let base = bases.next().ok_or_else(|| io::Error::other("pinned driver mapping missing"))?;
    assert!(bases.next().is_none());
    let scan = unsafe { std::mem::transmute::<usize, Scan>(base + 0x61c25c0) };
    SCAN.set(scan).unwrap();
    Ok(())
}

const CHUNK: usize = 64 * 1024;

struct CheckedClone {
    file: File,
    current: Vec<u8>,
    previous: Vec<u8>,
    position: u64,
    retained: u64,
    old_len: u64,
}

impl CheckedClone {
    fn drain_chunk(&mut self) -> io::Result<()> {
        if self.current.is_empty() { return Ok(()); }
        let len = self.current.len();
        if self.position + len as u64 <= self.old_len {
            self.file.read_exact_at(&mut self.previous[..len], self.position)?;
            if self.previous[..len] == self.current[..] {
                self.retained += len as u64;
                self.position += len as u64;
                self.current.clear();
                return Ok(());
            }
        }
        self.file.write_all_at(&self.current, self.position)?;
        self.position += len as u64;
        self.current.clear();
        Ok(())
    }
}

impl Write for CheckedClone {
    fn write(&mut self, mut bytes: &[u8]) -> io::Result<usize> {
        let total = bytes.len();
        while !bytes.is_empty() {
            let take = bytes.len().min(CHUNK - self.current.len());
            // Compare and publish the very same captured current bytes.
            self.current.extend_from_slice(&bytes[..take]);
            bytes = &bytes[take..];
            if self.current.len() == CHUNK { self.drain_chunk()?; }
        }
        Ok(total)
    }
    fn flush(&mut self) -> io::Result<()> { self.drain_chunk() }
}

impl Seek for CheckedClone {
    fn seek(&mut self, seek: SeekFrom) -> io::Result<u64> {
        match seek {
            SeekFrom::Current(0) => Ok(self.position + self.current.len() as u64),
            _ => Err(io::Error::other("nonsequential GNU archive write")),
        }
    }
}

fn try_clone(dst: &File, output: &Path) -> io::Result<u64> {
    let old = OpenOptions::new().read(true).custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK).open(output)?;
    if !old.metadata()?.is_file() { return Err(io::Error::other("irregular incumbent")); }
    // Linux FICLONE. The old destination remains untouched.
    let err = unsafe { libc::ioctl(dst.as_raw_fd(), 0x40049409 as libc::c_ulong, old.as_raw_fd()) };
    if err != 0 { return Err(io::Error::last_os_error()); }
    // The private clone is the snapshot used by both comparison and publication.
    Ok(dst.metadata()?.len())
}

fn write_archive<W: Write + Seek>(out: W, members: &[NewArchiveMember<'_>]) -> io::Result<W> {
    let mut buffered = BufWriter::new(out);
    write_archive_to_stream(&mut buffered, members, ArchiveKind::Gnu, false, Some(false))?;
    buffered.flush()?;
    buffered.into_inner().map_err(|e| e.into_error())
}

struct Temp(PathBuf);
impl Drop for Temp {
    fn drop(&mut self) {
        let _ = fs::remove_file(self.0.join("tmp.a"));
        let _ = fs::remove_dir(&self.0);
    }
}

fn main() -> io::Result<()> {
    let args: Vec<_> = std::env::args_os().collect();
    assert_eq!(args.len(), 4);
    let optimized = match args[1].to_str() { Some("normal") => false, Some("cow") => true, _ => panic!("bad mode") };
    let (inputs, output) = (Path::new(&args[2]), Path::new(&args[3]));
    load_qualified_driver()?;
    let names = fs::read_to_string(inputs.join("members"))?;
    let mut members = Vec::new();
    for n in names.lines() {
        assert_eq!(Path::new(n).file_name().unwrap(), n);
        let data = unsafe { Mmap::map(&File::open(inputs.join(n))?)? };
        members.push(NewArchiveMember::new(data, &READER, n.to_owned()));
    }
    let mut root = output.parent().unwrap().to_owned();
    root.push(format!(".rlib-cow-{}", std::process::id()));
    DirBuilder::new().mode(0o700).create(&root)?;
    let root = Temp(root);
    let temp = root.0.join("tmp.a");
    let out = OpenOptions::new().create_new(true).write(true).read(optimized).open(&temp)?;
    let attempt = optimized.then(|| try_clone(&out, output));
    let (total, retained, cloned, fallback) = match attempt {
        Some(Ok(old_len)) => {
            let writer = CheckedClone { file: out, current: Vec::with_capacity(CHUNK), previous: vec![0; CHUNK],
                                        position: 0, retained: 0, old_len };
            let w = write_archive(writer, &members)?;
            w.file.set_len(w.position)?;
            (w.position, w.retained, true, 0)
        }
        other => {
            let errno = match other {
                Some(Err(e)) => { out.set_len(0)?; e.raw_os_error().unwrap_or(-1) }
                _ => 0,
            };
            let out = write_archive(out, &members)?;
            (out.metadata()?.len(), 0, false, errno)
        }
    };
    drop(members);
    if std::env::var_os("STUDY_ABORT_BEFORE_RENAME").is_some() {
        return Err(io::Error::other("injected failure before publication"));
    }
    fs::rename(temp, output)?;
    println!("{total} {retained} {cloned} {fallback}");
    Ok(())
}

