//! Native child for a fixed-fixture end-to-end Cargo integration rehearsal.
//! The known fixture restricts the environment, inactive LTO and system inputs. This is not a general input attestor.
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::{OsStr, OsString};
use std::fs::{self, OpenOptions};
use std::io::{self, Read};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};
use std::env;

use serde_json::{json, Value};

fn field(h:&mut blake3::Hasher,key:&[u8],data:&[u8]){
    h.update(&(key.len() as u64).to_le_bytes());h.update(key);
    h.update(&(data.len() as u64).to_le_bytes());h.update(data);
}
fn bytes(path:&Path)->io::Result<String> {
    let mut f=OpenOptions::new().read(true).custom_flags(libc::O_NONBLOCK).open(path)?;
    if !f.metadata()?.is_file(){return Err(io::Error::other("non-regular input"))}
    let mut h=blake3::Hasher::new(); let mut b=[0;65536];
    loop {let n=f.read(&mut b)?;if n==0 {break} h.update(&b[..n]);}
    Ok(h.finalize().to_hex().to_string())
}
fn normal_output(p:&Path)->bool {
    let Ok(m)=p.symlink_metadata() else{return false};
    let Ok(path)=std::ffi::CString::new(p.as_os_str().as_bytes()) else{return false};
    m.is_file() && m.uid()==unsafe{libc::geteuid()} && m.nlink()==1 && m.mode()&0o7000==0
      && m.mode()&0o700==0o700 && unsafe {libc::llistxattr(path.as_ptr(),std::ptr::null_mut(),0)}==0
}
fn stamp(p:&Path)->Option<Value>{let m=p.symlink_metadata().ok()?;Some(json!([m.dev(),m.ino(),m.size(),m.mode(),m.mtime(),m.mtime_nsec(),m.ctime(),m.ctime_nsec()]))}
fn input_key(args:&[OsString])->io::Result<(String,BTreeMap<String,String>,usize)>{
    let mut h=blake3::Hasher::new();let mut evidence=BTreeMap::new();let mut directories=Vec::new();let mut libraries=BTreeSet::new();
    let mut roles=0;let mut artifact_kinds=Vec::new();
    field(&mut h,b"schema",b"fixed-fixture-linux-ordinary-v1");
    field(&mut h,b"cwd",env::current_dir()?.as_os_str().as_bytes());
    for (i,a) in args.iter().enumerate() {
        let raw=a.as_os_str().as_bytes();let s=a.to_str().ok_or_else(||io::Error::other("non-utf8 fixture input"))?;
        let path=Path::new(s);
        let name=if path.file_name()==Some(OsStr::new("symbols.o")) { roles+=1;"[rustc symbols.o]".to_string() }
         else if let Some(t)=s.strip_prefix("-L").filter(|t|Path::new(t).file_name()==Some(OsStr::new("raw-dylibs"))){
            if fs::read_dir(t)?.next().is_some(){return Err(io::Error::other("nonempty private raw-dylibs"))} roles+=1;"-L[rustc empty raw-dylibs]".to_string()
         } else if let Some(t)=s.strip_prefix("-plugin-opt=-fresolution="){
            if fs::metadata(t)?.len()!=0{return Err(io::Error::other("nonempty GCC resolution"))}roles+=1;"[known-inactive GCC resolution]".to_string()
         } else {s.to_string()};
        field(&mut h,b"arg",name.as_bytes());
        if let Some(d)=s.strip_prefix("-L"){directories.push((name.clone(),PathBuf::from(d)));}
        if let Some(n)=s.strip_prefix("-l"){if !n.is_empty(){libraries.insert(n.to_string());}}
        if i>0 && args[i-1]==OsStr::new("-o"){continue}
        if s.starts_with('-'){continue}
        if matches!(path.extension().and_then(OsStr::to_str),Some("o"|"a"|"rlib"|"so")) {
            let value=bytes(path)?;field(&mut h,b"input bytes",value.as_bytes());evidence.insert(name,value);artifact_kinds.push(raw.len());
        }
    }
    // This fixture's linker environment and runtime SDK are independent, read-only controlled inputs.
    // Enumerate every -L/-l combination (including its absence), not just previous positive providers.
    for (directory,path) in directories{
        for name in &libraries{for suffix in [".so",".a"]{
            let name=format!("lib{name}{suffix}");let file=path.join(&name);let logical=format!("{directory}/{name}");
            field(&mut h,b"name",logical.as_bytes());
            let value=match bytes(&file){Ok(h)=>h,Err(e) if e.kind()==io::ErrorKind::NotFound=>"ENOENT".to_string(),Err(e)=>return Err(e)};
            field(&mut h,b"probe",value.as_bytes());evidence.insert(logical,value);
        }}
    }
    if roles!=3{return Err(io::Error::other("unexpected private native operand roles"))}
    Ok((h.finalize().to_hex().to_string(),evidence,artifact_kinds.len()))
}
fn status_code(code:std::process::ExitStatus)->u8{code.code().map_or(1,|x| x.clamp(0,255) as u8)}
fn main()->io::Result<ExitCode> {
    let orig:Vec<_>=env::args_os().collect();let args=&orig[1..];
    let stock=PathBuf::from(env::var_os("OHM_QA_NATIVE_STOCK").expect("private fixture linker"));
    let mut child=Command::new(&stock);child.arg0(&orig[0]).args(args);
    let outs=args.windows(2).filter(|w|w[0]=="-o").map(|w|Path::new(&w[1])).collect::<Vec<_>>();
    let Some(p)=outs.first().copied().filter(|p|outs.len()==1&&p.file_name().and_then(OsStr::to_str).is_some_and(|n|n.starts_with("reader_case-"))) else{return Err(child.exec())};
    let private=PathBuf::from(env::var_os("OHM_QA_NATIVE_STATE").unwrap());
    let mode=env::var("OHM_QA_NATIVE_PHASE").unwrap();let phase_dir=private.join("launches").join(&mode);fs::create_dir_all(&phase_dir)?;
    let receipt=private.join("authorized-image.json");
    // The parent command uses -j1 and the kernel jobserver pipe is verified empty.
    // A wider scheduler is outside this fixed-fixture handshake.
    let sole=unsafe {jobserver::Client::from_env()}.and_then(|client|client.try_acquire().ok()).is_some_and(|v|v.is_none());
    let old=stamp(p); let key=if sole{input_key(args)}else{Err(io::Error::other("no exclusively single-worker fixture jobserver"))};
    let current=key.as_ref().ok().map(|v|v.0.as_str());
    let previous=fs::read(&receipt).ok().and_then(|b|serde_json::from_slice::<Value>(&b).ok());
    let image=if normal_output(p){bytes(p).ok()}else{None};
    let mut decision="real-stock";let mut code=0u8;
    if mode!="train" && !mode.ends_with("gold") && current.is_some() && image.is_some() && previous.as_ref().is_some_and(|v|v["key"].as_str()==current && v["image"].as_str()==image.as_deref()) {
        decision="fixture-native-fresh";
    } else {code=status_code(child.status()?);}
    let after=stamp(p);let output=if normal_output(p){bytes(p).ok()}else{None};
    if mode=="train" && code==0 && output.is_some() && current.is_some() {
        fs::write(&receipt,serde_json::to_vec(&json!({"key":current,"image":output}))?)?;
    }
    let parent=unsafe{libc::getppid()};
    let row=json!({"phase":mode,"pid":std::process::id(),"uid":unsafe{libc::geteuid()},"parent_exe":fs::read_link(format!("/proc/{parent}/exe")).ok(),
        "arch":std::env::consts::ARCH,"single_worker":sole,"output":p,"key":current,"key_error":key.as_ref().err().map(ToString::to_string),"inputs":key.as_ref().ok().map(|v|&v.1),
        "explicit":key.as_ref().ok().map(|v|v.2),"native_args":args.iter().map(|v|v.to_string_lossy()).collect::<Vec<_>>(),
        "before":old,"after":after,"before_BLAKE3":image,"after_BLAKE3":output,"status":code,"decision":decision});
    fs::write(phase_dir.join(format!("{}.json",std::process::id())),serde_json::to_vec(&row)?)?;
    Ok(ExitCode::from(code))
}
