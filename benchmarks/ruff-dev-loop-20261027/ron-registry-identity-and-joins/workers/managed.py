"""A Cargo-managed registry proc macro retains its Rust identity across a native C replacement."""
from pathlib import Path
import hashlib,json,os,re,shutil,struct,subprocess,sys,tarfile,time
X=Path('/dev/shm/ohm-ron-consumed-v1-20261028')
P=X/'managed'
SDK=Path('/dev/shm/ohm-published-member-h2-20261028/installed17')
CARGO=Path('/mnt/devbox-scratch/dev-user/ohm-observer-consumption-tools-20261028/fixed-cargo')
def h(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def store(p,v):p.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
def package(kind,body,files):
 d=P/'vendor'/(kind+'-0.1.0');(d/'src').mkdir(parents=True)
 (d/'Cargo.toml').write_text('[package]\nname="'+kind+'"\nversion="0.1.0"\nedition="2021"\n'+body)
 for name,s in files.items():(d/name).write_text(s)
 arc=P/(d.name+'.crate')
 with tarfile.open(arc,'w:gz') as t:t.add(d,arcname=d.name)
 checks={str(p.relative_to(d)):h(p) for p in d.rglob('*') if p.is_file()}
 store(d/'.cargo-checksum.json',{'package':h(arc),'files':checks})
 return h(arc)
def sections(p):
 data=p.read_bytes();off=struct.unpack_from('<Q',data,40)[0];step,n,si=struct.unpack_from('<HHH',data,58)
 rows=[struct.unpack_from('<IIQQQQIIQQ',data,off+i*step) for i in range(n)]
 start,length=rows[si][4:6];names=data[start:start+length];out={}
 for r in rows:
  name=names[r[0]:].split(b'\x00',1)[0].decode()
  if name in ('.rustc','.text','.dynsym'):out[name]=hashlib.sha256(data[r[4]:r[4]+r[5]]).hexdigest()
 assert len(out)==3;return out
def main():
 assert h(SDK/'bin/cargo')=='0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322'
 rustup=P/'rustup';(rustup/'toolchains').mkdir(parents=True);(rustup/'toolchains/ohm').symlink_to(SDK)
 packages={}
 packages['managed-tokens']=package('managed-tokens','',{'src/lib.rs':'#[macro_export] macro_rules! token {($m:ident) => { $m!(an_unambiguous_foreign_token) }; }\n'})
 packages['managed-macro']=package('managed-macro','[lib]\nproc-macro=true\n',{'src/lib.rs':r'''extern crate proc_macro;
use proc_macro::TokenStream;
extern "C" { fn chosen_value() -> u32; }
#[proc_macro] pub fn inspect(x: TokenStream) -> TokenStream {
    let span=x.into_iter().next().unwrap().span();
    format!("{:?}",format!("{span:?}")).parse().unwrap()
}
#[proc_macro] pub fn answer(_: TokenStream) -> TokenStream {
    let value=unsafe {chosen_value()};
    let dir=std::path::PathBuf::from(std::env::var_os("MANAGED_BARRIER").unwrap());
    if dir.join("armed").exists() {
        std::fs::write(dir.join("consumed"), value.to_string()).unwrap();
        let t=std::time::Instant::now();
        while !dir.join("resume").exists() {assert!(t.elapsed().as_secs()<90); std::thread::sleep(std::time::Duration::from_millis(5));}
    }
    value.to_string().parse().unwrap()
}
''','build.rs':r'''use std::{env,fs,path::PathBuf,process::Command};
fn main(){
 let dir=PathBuf::from(env::var_os("OUT_DIR").unwrap());
 let choice=env::var("MANAGED_OBJECT_SOURCE").unwrap();
 assert!(choice=="17" || choice=="29");
 fs::write(dir.join("native.c"),format!("unsigned chosen_value(void){{return {choice};}}")).unwrap();
 assert!(Command::new("cc").current_dir(&dir).args(["-fPIC","-c","native.c","-o","choice.o"]).status().unwrap().success());
 println!("cargo:rustc-link-arg={}",dir.join("choice.o").display());
 println!("cargo:rerun-if-env-changed=MANAGED_OBJECT_SOURCE");
}'''})
 packages['managed-reader']=package('managed-reader','[dependencies]\nmanaged-macro="=0.1.0"\nmanaged-tokens="=0.1.0"\n',{'src/lib.rs':'use managed_macro::inspect; pub const SPAN:&str=managed_tokens::token!(inspect); pub fn value()->u32{managed_macro::answer!()}\n'})
 store(P/'packages.json',packages)
 w=P/'ws';w.mkdir();(w/'.cargo').mkdir();(w/'.cargo/config.toml').write_text('[source.crates-io]\nreplace-with="verified-registry"\n[source.verified-registry]\ndirectory="'+str(P/'vendor')+'"\n')
 (w/'Cargo.toml').write_text('[workspace]\nresolver="2"\nmembers=["cli","precursor"]\n')
 for pkg,dep,body in [('precursor','managed-macro','fn main() {}'),('cli','managed-reader','fn main(){println!("{}",managed_reader::value());}')]:
  d=w/pkg;(d/'src').mkdir(parents=True);(d/'Cargo.toml').write_text('[package]\nname="'+pkg+'"\nversion="0.0.0"\nedition="2021"\n[dependencies]\n'+dep+'="=0.1.0"\n');(d/'src/main.rs').write_text(body)
 out={}
 for opt in ('full','default'):
  root=P/opt;root.mkdir(); b=root/'barrier';b.mkdir()
  def spawn(state,name,gen,pkg):
   d=root/state;d.mkdir(exist_ok=True);rec=root/name;rec.mkdir()
   e={k:v for k,v in os.environ.items() if not k.startswith(('RUST','CARGO'))}
   e.update(PATH='/home/dev-user/.cargo/bin:'+e['PATH'],RUSTUP_HOME=str(rustup),CARGO_HOME=str(d/'cargo'),CARGO_TARGET_DIR=str(d/'target'),CARGO_BUILD_BUILD_DIR=str(d/'shared'),RUSTUP_AUTO_INSTALL='0',CARGO_NET_OFFLINE='true',MANAGED_OBJECT_SOURCE=str(gen),MANAGED_BARRIER=str(b))
   if opt=='full':e['CARGO_ENCODED_RUSTFLAGS']='-Zpublic-api-hash=no'
   a=(rec/'out').open('wb');f=(rec/'err').open('wb')
   p=subprocess.Popen(['strace','-ff','-qq','-s','65535','-e','trace=execve','-o',str(rec/'exec'),'cargo','+ohm','build','--offline','--message-format=json','-j4','-p',pkg],cwd=w,stdout=a,stderr=f,env=e);a.close();f.close()
   return p
  def finish(p,name,pkg):
   rc=p.wait(timeout=150);r=root/name
   if rc:raise RuntimeError((opt,name,rc,(r/'err').read_text()[-1800:],(r/'out').read_text()[-2000:]))
   msgs=[json.loads(l) for l in (r/'out').read_bytes().splitlines()];arts=[m for m in msgs if m.get('reason')=='compiler-artifact'];m,=[a for a in arts if a['target']['name']=='managed_macro'];f=Path(m['filenames'][0]);real=[a for a in arts if a['target']['name']=='managed_reader']
   flags={}
   for trace in sorted(r.glob('exec.*')):
    for line in trace.read_text().splitlines():
     if not line.endswith(' = 0') or '"--crate-name",' not in line:continue
     nm=re.search(r'"--crate-name", "([^"]+)"',line)[1]
     if nm=='___':continue
     fs=re.findall(r'"(-Zpublic-api-hash(?:=no|=yes)?)"',line);flags[nm]=fs
     if opt=='full':assert fs and fs[-1]=='-Zpublic-api-hash=no',(nm,fs)
     if nm=='managed_reader':assert ('"managed_macro='+str(f)+'"') in line,line[-1100:]
   v=None
   if pkg=='cli':
    app,=[a for a in arts if a['target']['name']=='cli'];v=int(subprocess.check_output([app['executable']]))
   assert m['package_id'].startswith('registry+') and all(i['package_id'].startswith('registry+') for i in real)
   return {'rc':rc,'value':v,'cargo':{a['target']['name']:a['fresh'] for a in arts},'macro':str(f),'flags':flags,'reader_ids':[i['package_id'] for i in real]}
  raws={}
  for state,phase,gen in [('old','old-precursor',17),('new','new-precursor',29)]:
   row=finish(spawn(state,phase,gen,'precursor'),phase,'precursor');raws[state]=Path(row['macro'])
  old,new=raws['old'],raws['new'];s,t=sections(old),sections(new);assert s['.rustc']==t['.rustc'] and s['.dynsym']==t['.dynsym'] and s['.text']!=t['.text'],(s,t)
  ident=old.stat(); before=h(old);(b/'armed').touch()
  p=spawn('old','initial',17,'cli');end=time.monotonic()+90
  while p.poll() is None and not (b/'consumed').exists() and time.monotonic()<end:time.sleep(.01)
  assert (b/'consumed').read_text()=='17'
  loaded=[]
  for f in Path('/proc').glob('[0-9]*/maps'):
   try:lines=f.read_text().splitlines()
   except (OSError,UnicodeError):continue
   for l in lines:
    fields=l.split(maxsplit=5)
    if len(fields)==6 and fields[1]=='r-xp' and fields[4]==str(ident.st_ino) and fields[5]==str(old):loaded.append(int(f.parent.name))
  assert loaded,(old,ident)
  temp=old.with_name(old.name+'.new');shutil.copyfile(new,temp);os.utime(temp,ns=(ident.st_atime_ns,ident.st_mtime_ns));os.replace(temp,old)
  assert old.stat().st_mtime_ns==ident.st_mtime_ns and h(old)==h(new)!=before
  (b/'armed').unlink();(b/'resume').touch()
  runs={'initial':finish(p,'initial','cli')}
  for state,phase,gen in [('old','repeat',17),('old','again',17),('new','clean',29)]:
   runs[phase]=finish(spawn(state,phase,gen,'cli'),phase,'cli')
  dps=[p for p in (root/'old').rglob('managed_reader*.d') if p.parent.name=='out']
  assert len(dps)==1,dps
  out[opt]={'before':before,'after':h(new),'sections':[s,t],'in_compiler':loaded,'mtime_preserved':True,'foreign':b'ohm-foreign-span-bytes' in dps[0].read_bytes(),'phases':runs}
  store(P/'results.json',out);print(opt,'marker',out[opt]['foreign'],[(phase,v['value'],v['cargo'].get('managed_reader')) for phase,v in runs.items()],flush=True)
if __name__=='__main__':
 if '--child' in sys.argv:main()
 else:
  X.mkdir(exist_ok=True);P.mkdir()
  cmd=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--ro-bind','/dev/shm','/dev/shm','--tmpfs','/tmp','--bind',str(X),str(X),'--ro-bind',str(CARGO),str(SDK/'bin/cargo'),'--','taskset','-c','8-11',sys.executable,'-B',__file__,'--child'];sys.exit(subprocess.run(cmd).returncode)

