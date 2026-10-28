from pathlib import Path
import ast, hashlib, json, os, subprocess, tempfile
H=Path.home();D=H/'.cache/ohm-align-script-hash-product-20261028-v1';W=D/'file-boundary-v3';W.mkdir();T=D/'images-v3';at=T/'A';token=['cargo','+ohm'];env={**os.environ,'RUSTUP_HOME':str(H/'.cache/ohm-ron-producer-freshness-20261028/official-installer-state/rustup')};env.pop('RUSTC',None);env.pop('RUSTFLAGS',None)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
fn={}
for arm in 'AB':
 s=(D/('source-v2-'+arm)/'src/compiler/fingerprint/worktree.rs').read_text();start=s.index('fn hash_file(');stop=s.index('\n}\n',start)+2;fn[arm]=s[start:stop]
raw={a:hashlib.sha256(b.encode()).hexdigest()for a,b in fn.items()};main=''.join('mod '+arm.lower()+' { use std::{fs,io::Read,path::Path}; type CargoResult<T>=std::io::Result<T>; pub '+s+' }\n'for arm,s in fn.items())+'''fn main(){let args:Vec<_>=std::env::args().collect();let mut h=blake3::Hasher::new();let n:usize=args[3].parse().unwrap();h.update(&vec![42u8;n]);let p=std::path::Path::new(&args[2]);let r=match args[1].as_str(){"A"=>a::hash_file(&mut h,p),"B"=>b::hash_file(&mut h,p),"oracle"=>{let len:u64=args[4].parse().unwrap();h.update(&len.to_le_bytes());h.update(&std::fs::read(p).unwrap());Ok(())},_=>panic!()};match r{Ok(())=>println!("{}",h.finalize()),Err(e)=>println!("errno {:?}",e.raw_os_error())}}''';s=W/'probe.rs';s.write_text(main);(W/'shim.c').write_bytes((D/'stream-edge.c').read_bytes());subprocess.run(['cc','-std=gnu11','-O2','-shared','-fPIC',W/'shim.c','-o',W/'shim.so'],check=True)
fixture=W/'fixture';(fixture/'src').mkdir(parents=True);(fixture/'Cargo.toml').write_text('[package]\nname="hash_boundary_case"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nblake3="=1.8.5"\n');(fixture/'src/main.rs').write_bytes(s.read_bytes());env.update(CARGO_HOME=str(D/'build-home'),CARGO_TARGET_DIR=str(W/'cargo-target'),CARGO_BUILD_BUILD_DIR=str(W/'cargo-shared'),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='2',CARGO_INCREMENTAL='0');proxy=str(H/'.cargo/bin/cargo');subprocess.run([proxy,'+ohm','generate-lockfile','--offline'],cwd=fixture,env=env,check=True);subprocess.run([proxy,'+ohm','build','--release','--locked','--offline'],cwd=fixture,env=env,check=True);assert '0aa83c34e62843d924f905e0f5c866eb1dd6545fc4d719e803d9ba6030371fce'in(fixture/'Cargo.lock').read_text();(W/'probe').symlink_to(W/'cargo-target/release/hash_boundary_case');ext=fixture/'Cargo.lock';size_sets=[0,1,7,63,64,65,1023,1024,1025,16383,16384,16385,65535,65536,65553];prefixes=[0,1,8,19,1024,16376,16383,16384,32775];rows=[];input=W/'input'
def run(arm,pre,env2=None,length=None,p=None):return subprocess.check_output([W/'probe',arm,p or input,str(pre),*([str(length)]if length is not None else [])],env=(None if env2 is None else {**os.environ,**env2}),text=True).strip()
for size in size_sets:
 rawdata=bytes((i%251 for i in range(size)));input.write_bytes(rawdata)
 for pre in prefixes:
  oracle=run('oracle',pre,length=size);x={a:run(a,pre)for a in 'AB'};assert x['A']==x['B']==oracle;rows.append({'bytes':size,'prefix':pre,'digest':oracle})
short=[];initial=bytes((i%251 for i in range(12983)));modes=('short','grow','shrink','eio','eintr')
for mode in modes:
 for pre in [0,1167,1788355,75306]:
  comp={}
  for arm in 'AB':
   input.write_bytes(initial);r=run(arm,pre,{'LD_PRELOAD':str(W/'shim.so'),'EDGE_MODE':mode,'EDGE_FILE':str(input)});b=input.read_bytes();oracle={'eio':'errno Some(5)','eintr':'errno Some(4)'}.get(mode)or run('oracle',pre,length=len(initial));assert r==oracle,(mode,pre,arm,r,oracle);assert b==({'grow':initial+b'\x07'*1547,'shrink':initial[:53]}.get(mode,initial));comp[arm]=r
  assert comp['A']==comp['B'];short.append({'mode':mode,'prefix':pre,'initial':len(initial),'final':len(b),'result':comp['A']})
for p,e in [(W/'missing',2),(W,21)]:
 for arm in 'AB':assert run(arm,23,p=p)==f'errno Some({e})'
out={'terminal':True,'actual_source_functions':raw,'probe':sha(W/'probe'),'cargo_lock':sha(ext),'blake3_crate_sha256':'0aa83c34e62843d924f905e0f5c866eb1dd6545fc4d719e803d9ba6030371fce','shim':sha(W/'shim.so'),'regular':rows,'inflight':short,'missing':'ENOENT','directory':'EISDIR'};f=W/'result.json';f.write_text(json.dumps(out,sort_keys=True,indent=2)+'\n');print(len(rows),len(short),sha(f),flush=True)
