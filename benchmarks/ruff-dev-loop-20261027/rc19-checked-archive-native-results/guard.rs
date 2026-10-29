#![feature(rustc_private)]
extern crate libc;
#[path = "checked_file.rs"]
mod checked_file;

use checked_file::CheckedFile;
use std::fs::{self, File};
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::os::unix::fs::symlink;
use std::path::Path;

const N: usize = 196_625;

fn main() -> io::Result<()> {
    let dir = std::env::args_os().nth(1).unwrap();
    let d = Path::new(&dir);
    fs::create_dir(d)?;
    let old: Vec<u8> = (0..N).map(|i| (i.wrapping_mul(17) % 251) as u8).collect();
    let mut changed = old.clone();
    changed[0] ^= 1;
    changed[65_536] ^= 5;
    changed[N-1] ^= 3;
    let prior = d.join("prior");
    fs::write(&prior, &old)?;
    let link = d.join("symlink");
    symlink(&prior, &link)?;
    let fifo = d.join("fifo");
    assert!(std::process::Command::new("mkfifo").arg(&fifo).status()?.success());
    let small = d.join("small");
    fs::write(&small, b"old")?;
    let mut stale = File::open(&prior)?;
    for (tag, origin, data) in [
        ("equal", Some(prior.as_path()), old.as_slice()),
        ("changed", Some(prior.as_path()), changed.as_slice()),
        ("shorter", Some(prior.as_path()), &changed[..65_537]),
        ("longer", Some(small.as_path()), changed.as_slice()),
        ("grows", Some(prior.as_path()), [changed.as_slice(), &old[..100]].concat().leak()),
        ("empty", Some(prior.as_path()), &[]),
        ("none", None, changed.as_slice()),
        ("missing", Some(d.join("absent").leak()), changed.as_slice()),
        ("symlink-output", Some(link.as_path()), changed.as_slice()),
        ("directory", Some(d), changed.as_slice()),
        ("fifo-output", Some(fifo.as_path()), changed.as_slice()),
    ] {
        let dest = d.join(tag);
        let mut w = CheckedFile::new(File::create_new(&dest)?, origin)?;
        assert_eq!(w.write(&[])?, 0);
        for b in data.chunks(79_249) { w.write_all(b)?; }
        assert_eq!(w.stream_position()?, data.len() as u64);
        w.flush()?;
        assert_eq!(fs::read(dest)?, data, "{tag}");
        assert_eq!(fs::read(&prior)?, old, "{tag} mutated prior");
    }
    let seek_test = |w: &mut dyn SeekWrite| -> io::Result<()> {
        w.write_all(&old[..67_403])?;
        w.seek(SeekFrom::Current(-18))?;
        w.write_all(b"CHANGED")?;
        w.seek(SeekFrom::Start(99_005))?;
        w.write_all(b"HIGH")?;
        w.flush()?;
        w.write_all(b"AFTER-FLUSH")?;
        w.flush()
    };
    let mut checked = CheckedFile::new(File::create_new(d.join("seek-tested"))?, Some(&prior))?;
    seek_test(&mut checked)?;
    seek_test(&mut File::create_new(d.join("seek-stock"))?)?;
    assert_eq!(fs::read(d.join("seek-tested"))?, fs::read(d.join("seek-stock"))?);
    let mut limit = libc::rlimit { rlim_cur: 0, rlim_max: 0 };
    assert_eq!(unsafe {libc::getrlimit(libc::RLIMIT_FSIZE, &mut limit)}, 0);
    assert_eq!(limit.rlim_cur, libc::RLIM_INFINITY);
    let small_limit = libc::rlimit { rlim_cur: 512, rlim_max: limit.rlim_max };
    unsafe { libc::signal(libc::SIGXFSZ, libc::SIG_IGN); }
    for before in [true, false] {
        let dest = d.join(format!("limit-{before}"));
        let f = File::create_new(&dest)?;
        if before { assert_eq!(unsafe {libc::setrlimit(libc::RLIMIT_FSIZE, &small_limit)}, 0) }
        let mut w = CheckedFile::new(f, Some(&prior))?;
        if !before { assert_eq!(unsafe {libc::setrlimit(libc::RLIMIT_FSIZE, &small_limit)}, 0) }
        assert_eq!(w.write(&old[..800])?, 512);
        assert_eq!(w.write(&old[512..800]).unwrap_err().raw_os_error(), Some(libc::EFBIG));
        w.flush()?;
        assert_eq!(unsafe {libc::setrlimit(libc::RLIMIT_FSIZE, &limit)}, 0);
        assert_eq!(fs::read(dest)?, old[..512]);
    }
    let tmp = d.join("replace-temp");
    let mut w = CheckedFile::new(File::create_new(&tmp)?, Some(&prior))?;
    w.write_all(&changed)?;
    w.flush()?;
    fs::rename(tmp, &prior)?;
    let mut from_old_fd = Vec::new();
    stale.read_to_end(&mut from_old_fd)?;
    assert_eq!(from_old_fd, old);
    assert_eq!(fs::read(prior)?, changed);
    println!("15 cases passed. Current bytes, length, seek, file-size limits and old fd verified.");
    Ok(())
}
trait SeekWrite: Seek + Write {}
impl<T: Seek + Write> SeekWrite for T {}
