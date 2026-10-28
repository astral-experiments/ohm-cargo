"""Instrument a private copy of proc-macro2 to attribute the real ron joins and emitted spans."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,tarfile,tomllib,traceback
X=Path('/dev/shm/ohm-ron-consumed-v1-20261028')
P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
SDK=Path('/dev/shm/ohm-published-member-h2-20261028/installed17')
CARGO=Path('/mnt/devbox-scratch/dev-user/ohm-observer-consumption-tools-20261028/fixed-cargo')
Q=X/'joins'
def h(p):
 with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def store(p,v): p.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
def run():
 assert h(SDK/'bin/cargo')=='0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322'
 lock=P/'source/Cargo.lock'; entries=tomllib.loads(lock.read_text())['package']
 pkgs={(p['name'],p['version']):p for p in entries}
 done=set(); pending=[('ron','0.12.0')]
 while pending:
  key=pending.pop()
  if key in done:continue
  done.add(key)
  for s in pkgs[key].get('dependencies',[]):
   fields=s.split()
   match=[k for k in pkgs if k[0]==fields[0] and (len(fields)==1 or k[1]==fields[1])]; assert len(match)==1,(s,match)
   pending.append(match[0])
 vend=Q/'vendor';vend.mkdir()
 expected={}
 for name,ver in sorted(done):
  entry=pkgs[name,ver]; pkg=name+'-'+ver; arc,=(P/'registry-home/registry/cache').glob('*/'+pkg+'.crate'); assert h(arc)==entry['checksum']
  with tarfile.open(arc) as t:t.extractall(vend,filter='data')
  d=vend/pkg; files={str(p.relative_to(d)):h(p) for p in d.rglob('*') if p.is_file()}; store(d/'.cargo-checksum.json',{'package':entry['checksum'],'files':files});expected[pkg]=entry['checksum']
 store(Q/'registry.json',expected)
 src=Q/'probe'; (src/'src').mkdir(parents=True);(src/'src/lib.rs').write_text('pub fn result() -> String { ron::to_string(&17u32).unwrap() }\n#[test] fn correct(){assert_eq!(result(),"17")}\n')
 (src/'Cargo.toml').write_text('[package]\nname="ron_join_probe"\nversion="0.0.0"\nedition="2021"\n[dependencies]\nron="=0.12.0"\n[profile.dev]\nopt-level=1\ndebug="line-tables-only"\n')
 shutil.copy2(lock,src/'Cargo.lock')
 (src/'.cargo').mkdir();(src/'.cargo/config.toml').write_text(f'[source.crates-io]\nreplace-with="verified-vendor"\n[source.verified-vendor]\ndirectory="{vend}"\n')
 rustup=Q/'rustup';(rustup/'toolchains').mkdir(parents=True);(rustup/'toolchains/ohm').symlink_to(SDK)
 for mode in ('ordinary','diagnosed'):
  if mode=='diagnosed':
   crate,=vend.glob('proc-macro2-*');p=crate/'src/wrapper.rs'
   orig='(Span::Compiler(a), Span::Compiler(b)) => Span::Compiler(proc_macro_span::join(a, b)?),'
   text=p.read_text();assert text.count(orig)==1
   new='''(Span::Compiler(a), Span::Compiler(b)) => {
                let joined = proc_macro_span::join(a, b);
                if let Some(file) = std::env::var_os("RON_JOIN_REPORT") {
                    use std::io::Write as _;
                    let mut f = std::fs::OpenOptions::new().append(true).create(true).open(file).unwrap();
                    writeln!(f, "JOIN {:?} {:?} {:?} {:?} {:?} {}:{}..{}:{} {:?} {}:{}..{}:{} {:?}\\n{}\\nEND",
                        std::env::var_os("CARGO_CRATE_NAME"), a, b, joined, a.file(), a.start().line(), a.start().column(), a.end().line(), a.end().column(), a.source_text(),
                        b.start().line(), b.start().column(), b.end().line(), b.end().column(), b.source_text(), std::backtrace::Backtrace::force_capture()).unwrap();
                }
                Span::Compiler(joined?)
            },'''
   p.write_text(text.replace(orig,new));cs=crate/'.cargo-checksum.json';s=json.loads(cs.read_bytes());s['files']['src/wrapper.rs']=h(p);store(cs,s)
  arm=Q/mode;home=arm/'cargo';home.mkdir(parents=True)
  env={k:v for k,v in os.environ.items() if not k.startswith(('RUST','CARGO'))};env.update(RUSTUP_HOME=str(rustup),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(home),CARGO_TARGET_DIR=str(arm/'target'),CARGO_BUILD_BUILD_DIR=str(arm/'shared'),CARGO_NET_OFFLINE='true',PATH='/home/dev-user/.cargo/bin:'+env['PATH'])
  if mode=='diagnosed':env['RON_JOIN_REPORT']=str(arm/'joins.log')
  rows=[]
  for phase in ('first','repeat'):
   out=arm/(phase+'.out');err=arm/(phase+'.err')
   with out.open('wb') as a,err.open('wb') as b:
    r=subprocess.run(['cargo','+ohm','test','--no-run','--offline','-j4','--message-format=json'],cwd=src,env=env,stdout=a,stderr=b)
   if r.returncode:
    print(err.read_text()[-4500:]);print(out.read_text()[-4500:]);raise RuntimeError((mode,phase,r.returncode))
   msgs=[json.loads(s) for s in out.read_bytes().splitlines()];ron,=[s for s in msgs if s.get('reason')=='compiler-artifact' and s['target']['name']=='ron']
   ds=[p for d in (arm/'target',arm/'shared') for p in d.rglob('ron-*.d') if p.parent.name=='out'];assert len(ds)==1,ds
   row={'phase':phase,'fresh':ron['fresh'],'marker':b'ohm-foreign-span-bytes' in ds[0].read_bytes(),'dep_info':h(ds[0]),'features':ron['features'],'artifacts':[h(Path(f)) for f in ron['filenames']]};rows.append(row);print(mode,row,flush=True)
  store(arm/'result.json',rows)
if __name__=='__main__':
 if '--child' in sys.argv:run()
 else:
  X.mkdir(exist_ok=True);Q.mkdir()
  cmd=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--ro-bind','/dev/shm','/dev/shm','--tmpfs','/tmp','--bind',str(X),str(X),'--ro-bind',str(CARGO),str(SDK/'bin/cargo'),'--','taskset','-c','0-3',sys.executable,'-B',__file__,'--child']
  sys.exit(subprocess.run(cmd).returncode)

