"""Reopen returned Serde tokens and record only spans emitted from the imported bitflags field."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys
X=Path('/dev/shm/ohm-ron-consumed-v1-20261028');D=X/'return-source'
SDK=Path('/dev/shm/ohm-published-member-h2-20261028/installed17');CARGO=Path('/mnt/devbox-scratch/dev-user/ohm-observer-consumption-tools-20261028/fixed-cargo')
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def child():
 Q=X/'joins'
 vend=D/'vendor';vend.mkdir()
 for p in (Q/'vendor').iterdir():
  if p.name=='serde_derive-1.0.229':shutil.copytree(p,vend/p.name)
  else:(vend/p.name).symlink_to(p)
 d=vend/'serde_derive-1.0.229';f=d/'src/lib.rs';text=f.read_text()
 for name in ('serialize','deserialize'):
  s='    '+('ser' if name=='serialize' else 'de')+'::expand_derive_'+name+'(&mut input)\n        .unwrap_or_else(syn::Error::into_compile_error)\n        .into()'
  assert text.count(s)==1
  text=text.replace(s,'    let output: TokenStream = '+s.strip()+';\n    report("'+name+'", output.clone());\n    output')
 text+=r'''
fn report(which: &str, stream: TokenStream) {
    use std::io::Write as _;
    let Some(file) = std::env::var_os("RON_RETURN_LOG") else { return };
    let mut f=std::fs::OpenOptions::new().append(true).create(true).open(file).unwrap();
    for t in stream {
        let s=t.span(); let p=s.file();
        if p.ends_with("/bitflags-2.13.2/src/public.rs") && s.start().line()==17 && s.start().column()==37 && s.end().column()==98 {
            writeln!(f,"{} {:?} {:?} {}:{}..{}:{} {}",which,s,p,s.start().line(),s.start().column(),s.end().line(),s.end().column(),t).unwrap();
        }
        if let proc_macro::TokenTree::Group(g)=t {report(which,g.stream());}
    }
}
'''
 f.write_text(text);ck=d/'.cargo-checksum.json';j=json.loads(ck.read_bytes());j['files']['src/lib.rs']=h(f);ck.write_text(json.dumps(j))
 w=D/'probe';shutil.copytree(Q/'probe',w);c=w/'.cargo/config.toml';c.write_text(c.read_text().replace(str(Q/'vendor'),str(vend)))
 e={k:v for k,v in os.environ.items() if not k.startswith(('CARGO','RUST'))};e.update(PATH='/home/dev-user/.cargo/bin:'+e['PATH'],RUSTUP_HOME=str(Q/'rustup'),CARGO_HOME=str(D/'home'),CARGO_TARGET_DIR=str(D/'target'),CARGO_BUILD_BUILD_DIR=str(D/'shared'),CARGO_NET_OFFLINE='true',RUSTUP_AUTO_INSTALL='0',RON_RETURN_LOG=str(D/'returned.tsv'))
 for phase in ('native','repeat'):
  with (D/(phase+'.out')).open('wb') as a,(D/(phase+'.err')).open('wb') as b:
   p=subprocess.run(['cargo','+ohm','test','--no-run','--offline','--message-format=json','-j4'],cwd=w,env=e,stdout=a,stderr=b)
  if p.returncode:raise RuntimeError(((D/(phase+'.out')).read_text()[-2000:],(D/(phase+'.err')).read_text()[-350:]))
  rows=(D/'returned.tsv').read_text().splitlines();print(phase,len(rows),flush=True)
  (D/(phase+'.tsv')).write_text('\n'.join(rows)+'\n')
if __name__=='__main__':
 if '--child' in sys.argv:child()
 else:
  D.mkdir()
  cmd=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--ro-bind','/dev/shm','/dev/shm','--tmpfs','/tmp','--bind',str(X),str(X),'--ro-bind',str(CARGO),str(SDK/'bin/cargo'),'--','taskset','-c','0-3',sys.executable,'-B',__file__,'--child'];sys.exit(subprocess.run(cmd).returncode)

