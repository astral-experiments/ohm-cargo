"""Supply exact Unix dep-info path bytes after normal Cargo unit freshness, before .d generation."""
import fcntl,importlib.util,json,os,shutil,struct,subprocess,sys,time
from pathlib import Path
H=Path('/home/dev-user/.cache/ohm-output-paths-over261-20261028');spec=importlib.util.spec_from_file_location('fixture',H/'prepare-path-fixture.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
O=H/'output-wire-control';R=O/'code';A=O/'active';bin=s.RT/'bin/cargo'
def w(n,x):p=R/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(x)
def supplement(raw,names):
 assert raw[:5]==b'\x01\0\0\0\xff' and raw[5] in (2,4) and raw[-41:-37]!=b'OBS1'
 n=int.from_bytes(raw[6:10],'little');i=10
 for _ in range(n):
  i+=1;size=int.from_bytes(raw[i:i+4],'little');i+=4+size;checksum=raw[i];i+=1
  if checksum:i+=8;size=int.from_bytes(raw[i:i+4],'little');i+=4+size
 add=b''.join(b'\0'+struct.pack('<I',len(p))+p+b'\0' for p in names)
 return raw[:6]+struct.pack('<I',n+len(names))+raw[10:i]+add+raw[i:]
def arm_run(arm):
 out=O/arm;out.mkdir();A.mkdir();(A/'home').mkdir()
 t=bin.with_name('wire-next');shutil.copy2(H/'subjects'/arm/'cargo',t);os.replace(t,bin)
 e=s.env('library');e.update(CARGO_HOME=str(A/'home'),CARGO_TARGET_DIR=str(A/'target'),CARGO_BUILD_BUILD_DIR=str(A/'shared'));cmd=[s.CARGO,'+ohm','build','--offline','-p','consumer','--quiet']
 subprocess.run(cmd,env=e,cwd=R,check=True)
 p,=[p for p in A.rglob('dep-lib-input') if p.parent.name=='fingerprint'];old=p.read_bytes();results={}
 for name,extra in [('alias',[b'data/./inside',b'data/inside',b'data/space input']),('raw-invalid',[b'zz-\xff',b'aa-\xfe'])]:
  gate=out/name;gate.mkdir();env=dict(e,OUTPUT_LIST_TEST_GATE=str(gate));so=(gate/'out').open('wb');se=(gate/'err').open('wb')
  proc=subprocess.Popen(cmd,env=env,cwd=R,stdout=so,stderr=se)
  try:
   deadline=time.monotonic()+30
   while not (gate/'ready').is_file():
    assert proc.poll() is None and time.monotonic()<deadline,(name,proc.returncode);time.sleep(.01)
   assert p.read_bytes()==old
   p.write_bytes(supplement(old,extra));(gate/'continue').touch()
   rc=proc.wait(timeout=30)
  finally:
   if proc.poll() is None:proc.terminate();proc.wait()
   so.close();se.close();p.write_bytes(old)
  if name=='alias':
   assert rc==0;d=(A/'target/debug/consumer.d').read_bytes();assert b'/data/./inside' in d and b'/data/inside' not in d and b'/data/space\\ input' in d,d
   (gate/'public.d').write_bytes(d)
  else:
   text=(gate/'err').read_bytes();assert rc==101 and b'not utf-8' in text and b'aa-' in text and b'zz-' not in text,text
  results[name]=dict(rc=rc,stderr=s.sha(gate/'err'),output=s.sha(gate/'public.d') if name=='alias' else None)
 A.rename(O/(arm+'-retained'));return results
with s.LOCK.open('a') as f:
 fcntl.flock(f,fcntl.LOCK_EX);os.sched_setaffinity(0,range(8));O.mkdir()
 w('Cargo.toml','[workspace]\nmembers=["input","consumer"]\nresolver="2"\n')
 w('input/Cargo.toml','[package]\nname="input"\nversion="0.1.0"\nedition="2024"\n');w('input/src/lib.rs','pub fn n()->u8{3}')
 w('consumer/Cargo.toml','[package]\nname="consumer"\nversion="0.1.0"\nedition="2024"\n[dependencies]\ninput={path="../input"}\n');w('consumer/src/main.rs','fn main(){println!("{}",input::n());}')
 w('consumer/build.rs','''fn main(){ println!("cargo::rerun-if-env-changed=OUTPUT_LIST_TEST_GATE"); if let Some(s)=std::env::var_os("OUTPUT_LIST_TEST_GATE"){let p=std::path::PathBuf::from(s);std::fs::write(p.join("ready"),b"").unwrap();for _ in 0..4000 {if p.join("continue").is_file(){return} std::thread::sleep(std::time::Duration::from_millis(10));}panic!("timeout")}}''')
 res={a:arm_run(a) for a in ('parent','candidate')};s.save(O/'complete.json',res);assert res['parent']==res['candidate'],res
