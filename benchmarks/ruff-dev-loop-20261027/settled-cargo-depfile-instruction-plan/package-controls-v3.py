"""Exercise two PGO Cargo builds at one logical SDK, with retained independent native target states."""
import importlib.util,os,fcntl,hashlib,json,shutil,subprocess,sys
from pathlib import Path
h=Path('/home/dev-user/.cache/ohm-output-path-ruff-20261028')
def module():
 spec=importlib.util.spec_from_file_location('fixture',h/'prepare-path-fixture.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p);return p
s=module();ROOT=h/'package-controls-v3';SRC=ROOT/'source';ACTIVE=ROOT/'active'
subj=h/'subjects'; BIN=h/'runtime/bin/cargo'
def switch(arm):
 p=subj/('qualified-'+arm)/'cargo';want=json.loads((subj/'qualified-pair.json').read_text())[arm]['sha256'];assert s.sha(p)==want
 tmp=BIN.with_name('next-private-cargo');shutil.copy2(p,tmp);os.replace(tmp,BIN);assert s.sha(BIN)==want
def manifest(d,n):return f'[package]\nname="{n}"\nversion="0.1.0"\nedition="2024"\n'+d
def write(n,c):p=SRC/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(c)
def subrun(arm,name,args,extra=None,ok=True,raw_cwd=None):
 e=s.env('library');e.update(CARGO_HOME=str(ROOT/'registry-home'),CARGO_TARGET_DIR=str(ACTIVE/'target'),CARGO_BUILD_BUILD_DIR=str(ACTIVE/'shared'));e.update(extra or {})
 o=ROOT/arm/name;o.mkdir(parents=True);cmd=[s.CARGO,'+ohm',*args];r=subprocess.run(cmd,cwd=raw_cwd or SRC,env=e,capture_output=True)
 (o/'stdout').write_bytes(r.stdout);(o/'stderr').write_bytes(r.stderr);s.save(o/'call.json',dict(argv=list(map(str,cmd)),rc=r.returncode,stdout=s.sha(o/'stdout'),stderr=s.sha(o/'stderr')))
 if ok:assert r.returncode==0,(name,r.stderr[-700:])
 return r
def all_d():return {p.name:p.read_bytes() for p in sorted((ACTIVE/'target/debug').glob('*.d'))}
def enc(row):return {k:hashlib.sha256(v).hexdigest() for k,v in row.items()}
def main():
 os.umask(0o077);os.sched_setaffinity(0,range(8));assert (h/'ready.json').exists()
 ROOT.mkdir();(ROOT/'registry-home').mkdir()
 write('Cargo.toml','[workspace]\nmembers=["reader","input"]\nresolver="2"\n');write('input/Cargo.toml',manifest('[lib]\ncrate-type=["rlib","cdylib"]\n','input'));write('reader/Cargo.toml',manifest('[dependencies]\ninput={path="../input"}\n','reader'))
 write('reader/src/main.rs','fn main(){println!("{}",input::answer());}\n');write('input/assets/input space','17');(SRC/'input/assets/alias').symlink_to('input space')
 write('input/src/other.rs','pub fn number()->u8{29}\n')
 write('input/build.rs','fn main(){for p in ["assets/./input space","assets/input space","assets/alias","build.rs","./build.rs"]{println!("cargo::rerun-if-changed={p}");}}\n')
 # A separately discovered non-Unicode project path may be rejected earlier than Cargo's external .d writer.
 raw=os.fsencode(ROOT)+b'/non-utf8-\xff';os.makedirs(raw+b'/src');open(raw+b'/Cargo.toml','wb').write(b'[package]\nname="nonutf8"\nversion="0.1.0"\nedition="2024"\n');open(raw+b'/src/lib.rs','wb').write(b'pub fn a(){}')
 rows={}
 for arm in ('parent','candidate'):
  ACTIVE.mkdir();switch(arm);write('input/src/lib.rs','pub fn answer()->u8{17}\n')
  subrun(arm,'initial',['build','--workspace','--offline','--quiet']);g=all_d();assert set(g)=={'libinput.d','reader.d'}
  for contents in g.values():
   assert b'/input/assets/./input\\ space' in contents and b'/input/assets/input\\ space' not in contents and b'/input/assets/alias' in contents,contents
  out=ACTIVE/'target/debug';assert subprocess.check_output([out/'reader']).strip()==b'17'
  for p in out.glob('*.d'):os.utime(p,ns=(1_000_000_000,1_000_000_000))
  subrun(arm,'repeat',['build','--workspace','--offline','--quiet']);assert g==all_d();rewritten=sorted(p.name for p in out.glob('*.d') if p.stat().st_mtime_ns!=1_000_000_000);assert rewritten==['libinput.d'],rewritten
  (out/'reader.d').unlink();(out/'libinput.d').write_bytes(b'wrong\n')
  subrun(arm,'recreate',['build','--workspace','--offline','--quiet']);assert g==all_d()
  subrun(arm,'basedir',['build','--workspace','--offline','--quiet'],dict(CARGO_BUILD_DEP_INFO_BASEDIR=str(SRC)));rel=all_d();assert all(b'input/assets/input\\ space' in line and b'input/assets/alias' in line and b'/input/assets/./' not in line for line in rel.values())
  write('input/src/lib.rs','pub fn answer()->u16{u16::from(other::number())} mod other;\n');subrun(arm,'edit',['build','--workspace','--offline','--quiet']);updated=all_d();assert set(updated)==set(g) and all(b'/input/src/other.rs' in v for v in updated.values()) and subprocess.check_output([out/'reader']).strip()==b'29'
  non=subrun(arm,'nonutf',['build','--offline','--quiet'],raw_cwd=raw,ok=False)
  rows[arm]=dict(original=enc(g),basedir=enc(rel),edit=enc(updated),nonutf_rc=non.returncode,nonutf_stderr=hashlib.sha256(non.stderr).hexdigest(),before=17,after=29,rewrote_on_repeat=rewritten)
  ACTIVE.rename(ROOT/('saved-'+arm))
 assert rows['parent']==rows['candidate'],rows
 s.save(ROOT/'complete.json',rows)
with s.LOCK.open('a') as lock:fcntl.flock(lock,fcntl.LOCK_EX);main()
