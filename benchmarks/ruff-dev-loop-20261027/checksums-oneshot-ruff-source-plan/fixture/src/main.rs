mod before; mod after; mod sha;
use sha::Sha256;
use std::fs::{self,File,OpenOptions};
use std::io::{self,Read,Write};
use std::path::{Path,PathBuf};

#[derive(Debug,Clone,Copy)]
enum Alg { Blake3, Sha256 }

fn compute(r: impl Read, buf: &mut [u8], alg: Alg, new: bool) -> io::Result<[u8;32]> {
    if new {
        let algo=match alg { Alg::Blake3=>after::ChecksumAlgo::Blake3, Alg::Sha256=>after::ChecksumAlgo::Sha256 };
        after::Checksum::compute(algo,r,buf).map(after::Checksum::bytes)
    } else {
        let algo=match alg { Alg::Blake3=>before::ChecksumAlgo::Blake3, Alg::Sha256=>before::ChecksumAlgo::Sha256 };
        before::Checksum::compute(algo,r,buf).map(before::Checksum::bytes)
    }
}
fn expected(bytes:&[u8], alg:Alg)->[u8;32]{
    match alg { Alg::Blake3=>*blake3::hash(bytes).as_bytes(), Alg::Sha256=>{let mut h=Sha256::new();h.update(bytes);h.finish()} }
}
fn pattern(n:usize)->Vec<u8> {(0..n).map(|i|(i.wrapping_mul(47)^(i>>5)^(i>>11)) as u8).collect()}
#[derive(Clone,Copy,Debug)]
enum End { Eof, Zero(usize), Fail(usize,io::ErrorKind) }
struct Script<'a> { src:&'a[u8], pos:usize, max:usize, end:End, terminal:usize }
impl Read for Script<'_> {
    fn read(&mut self,buf:&mut[u8])->io::Result<usize>{
        assert!(!buf.is_empty(),"unexpected zero-length read");
        assert_eq!(self.terminal,0,"extra read following EOF/error");
        let limit=match self.end {End::Eof=>self.src.len(),End::Zero(n)|End::Fail(n,_)=>n.min(self.src.len())};
        if self.pos>=limit {
            self.terminal+=1;
            return match self.end{End::Fail(n,k) if n==self.pos=>Err(io::Error::new(k,"scripted rejection")), _=>Ok(0)};
        }
        let n=buf.len().min(self.max).min(limit-self.pos);
        buf[..n].copy_from_slice(&self.src[self.pos..self.pos+n]);self.pos+=n;Ok(n)
    }
}
fn synthetic(maxbuf:usize)->usize{
    let mut n=0; let mut buffer=vec![0;maxbuf];
    for len in [0,1,63,64,65,1023,1024,1025,8192,65535,65536,65537,131101]{
        let bytes=pattern(len);
        for maxread in [1,17,4096,65536,usize::MAX] {
            for end in [End::Eof,End::Zero(0),End::Zero(7),End::Zero(65536),End::Fail(0,io::ErrorKind::PermissionDenied),End::Fail(1,io::ErrorKind::Interrupted),End::Fail(1023,io::ErrorKind::UnexpectedEof),End::Fail(65535,io::ErrorKind::InvalidData),End::Fail(65536,io::ErrorKind::Other),End::Fail(65537,io::ErrorKind::WouldBlock)]{
                let stop=match end{End::Eof=>len,End::Zero(p)|End::Fail(p,_)=>p.min(len)};
                for alg in [Alg::Blake3,Alg::Sha256] {
                    let truth=match end{End::Fail(p,k) if p==stop=>Err(k),_=>Ok(expected(&bytes[..stop],alg))};
                    for new in [false,true]{
                        let mut sr=Script{src:&bytes,pos:0,max:maxread,end,terminal:0};
                        let actual=compute(&mut sr,&mut buffer,alg,new).map_err(|e|e.kind());
                        assert_eq!(actual,truth,"{len}/{maxbuf}/{maxread}/{end:?}/{alg:?}/{new}");assert_eq!((sr.pos,sr.terminal),(stop,1));
                    }
                    n+=1;
                }
            }
        }
    }
    n
}
struct ChangeDuring<'a> {file:File,path:&'a Path,grow:bool,changed:bool,short:usize}
impl Read for ChangeDuring<'_> {
    fn read(&mut self,target:&mut[u8])->io::Result<usize>{
        let n=target.len().min(self.short);let read=self.file.read(&mut target[..n])?;
        if !self.changed && read>0 {
            self.changed=true;
            if self.grow { OpenOptions::new().append(true).open(self.path)?.write_all(&pattern(90005))?; }
            else { OpenOptions::new().write(true).open(self.path)?.set_len(13)?; }
        }
        Ok(read)
    }
}
fn file_changes(tmp:&Path)->usize{
    let path=tmp.join("aliased real input");let alias=tmp.join("tracked symlink");
    #[cfg(unix)] std::os::unix::fs::symlink(&path,&alias).unwrap();
    #[cfg(not(unix))] let alias=path.clone();
    let mut count=0;let mut buf=vec![0;64*1024];
    for before_len in [0,7,65535,65536,65537]{
        for after_len in [0,9,65535,65536,65537,131089]{
            for alg in [Alg::Blake3,Alg::Sha256]{
                let payload=pattern(after_len);
                for new in [false,true]{
                    fs::write(&path,pattern(before_len)).unwrap();
                    let file=File::open(&alias).unwrap();assert_eq!(file.metadata().unwrap().len(),before_len as u64);
                    fs::write(&path,&payload).unwrap();
                    assert_eq!(compute(file,&mut buf,alg,new).unwrap(),expected(&payload,alg));
                }
                count+=1;
            }
        }
    }
    for initial in [42,65000,70000] {
        for short in [7,31,8193]{
            for grow in [false,true]{
                let src=pattern(initial);let want=if grow{[src.clone(),pattern(90005)].concat()}else{
                    src[..short.min(src.len()).max(13).min(src.len())].to_vec()
                };
                for alg in [Alg::Blake3,Alg::Sha256]{
                    for new in [false,true]{
                        fs::write(&path,&src).unwrap();let file=File::open(&alias).unwrap();assert_eq!(file.metadata().unwrap().len(),initial as u64);
                        let reader=ChangeDuring{file,path:&path,grow,changed:false,short};
                        assert_eq!(compute(reader,&mut buf,alg,new).unwrap(),expected(&want,alg));
                    }
                    count+=1;
                }
            }
        }
    }
    count
}
fn corpus_paths(dir:&Path)->Vec<PathBuf>{
    let n=fs::read_dir(dir).unwrap().count();assert_eq!(n,1238);
    (0..n).map(|i|dir.join(i.to_string())).collect()
}
fn replay(dir:&Path,new:bool,loops:usize)->[u8;32]{
    let paths=corpus_paths(dir);let mut buf=vec![0;64*1024];let mut ledger=blake3::Hasher::new();
    for _ in 0..loops{for p in &paths{
        let file=File::open(p).unwrap();let hash=compute(file,&mut buf,Alg::Blake3,new).unwrap();ledger.update(&hash);
    }}
    *ledger.finalize().as_bytes()
}

#[cfg(target_os="linux")]
fn packets(new:bool)->[u8;32]{
    use std::os::fd::FromRawFd;
    unsafe extern "C" {fn pipe2(fds:*mut i32,flags:i32)->i32;}
    let mut fds=[0;2];
    // Linux x86_64 O_DIRECT on a pipe preserves write packet boundaries.
    assert_eq!(unsafe{pipe2(fds.as_mut_ptr(),0o40000)},0);
    let mut writer=unsafe{File::from_raw_fd(fds[1])};
    let reader=unsafe{File::from_raw_fd(fds[0])};
    assert_eq!(writer.write(&[172]).unwrap(),1);
    assert_eq!(writer.write(&pattern(64)).unwrap(),64);
    drop(writer);
    compute(reader,&mut [0;64],Alg::Blake3,new).unwrap()
}
struct FixedRead {calls:usize,expected:usize}
impl Read for FixedRead{
    fn read(&mut self,out:&mut[u8])->io::Result<usize>{
        self.calls+=1;
        if out.len()!=self.expected{return Err(io::Error::new(io::ErrorKind::InvalidInput,"requested width changed"));}
        match self.calls {1=>{out[0]=172;Ok(1)},2=>{let p=pattern(self.expected);out.copy_from_slice(&p);Ok(p.len())},3=>Ok(0),_=>panic!("read after EOF")}
    }
}

fn main(){
    let args:Vec<_>=std::env::args().collect();
    let dir=Path::new(&args[2]);
    match args[1].as_str(){
        "packet-witness"=>{
            let gold=expected(&[vec![172],pattern(64)].concat(),Alg::Blake3);
            println!("parent={} candidate={} expected={}",blake3::Hash::from_bytes(packets(false)),blake3::Hash::from_bytes(packets(true)),blake3::Hash::from_bytes(gold));
            assert_eq!(packets(false),gold);
        }
        "check"=>{
            let gold=expected(&[vec![172],pattern(64)].concat(),Alg::Blake3);
            for new in [false,true] {
                assert_eq!(packets(new),gold);
                for alg in [Alg::Blake3,Alg::Sha256] {
                    let mut r=FixedRead{calls:0,expected:64};
                    assert_eq!(compute(&mut r,&mut [0;64],alg,new).unwrap(),expected(&[vec![172],pattern(64)].concat(),alg));assert_eq!(r.calls,3);
                }
            }
            let mut synthetic_count=0;for cap in [1,64,1024,65536]{synthetic_count+=synthetic(cap)}
            let file_count=file_changes(Path::new(&args[3]));let paths=corpus_paths(dir);let mut buf=vec![0;65536];
            let mut b3=blake3::Hasher::new();let mut sha=Sha256::new();
            for p in &paths{let bytes=fs::read(p).unwrap();for alg in [Alg::Blake3,Alg::Sha256]{
                let gold=expected(&bytes,alg);for new in [false,true]{assert_eq!(compute(File::open(p).unwrap(),&mut buf,alg,new).unwrap(),gold);}
                match alg{Alg::Blake3=>{b3.update(&gold);},Alg::Sha256=>{sha.update(&gold);}}
            }}
            for new in [false,true]{assert_eq!(replay(dir,new,1),*b3.finalize().as_bytes())}
            println!("synthetic={synthetic_count} physical={file_count} corpus={} blake3={} sha256={:02x?}",paths.len(),b3.finalize(),sha.finish());
        }
        "before"|"after"=>{let got=replay(dir,args[1]=="after",args[3].parse().unwrap());println!("{}",blake3::Hash::from_bytes(got));}
        _=>panic!("unknown action")
    }
}
