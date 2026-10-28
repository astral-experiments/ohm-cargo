"""Exercise three tracker reports against one installed, authenticated Cargo."""
import hashlib, http.server, io, json, os, signal, subprocess, tarfile, threading
from pathlib import Path
SDK=Path('/dev/shm/ohm-published-member-h2-20261028/installed17')
R=Path('/mnt/devbox-scratch/dev-user/ohm-release17-panic-audit-20261028')
R.mkdir(exist_ok=False)
def store(path,x):path.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(SDK/'bin/cargo')=='4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3'
def source(d, name, extra, code, lib=False):
    (d/'src').mkdir(parents=True)
    (d/'Cargo.toml').write_text(f'[package]\nname="{name}"\nversion="0.1.0"\nedition="2021"\n'+extra)
    (d/'src'/('lib.rs' if lib else 'main.rs')).write_text(code)
def call(d,n,args,extra=None):
    e={k:v for k,v in os.environ.items() if not k.startswith(('CARGO_','RUST'))}
    e.update(CARGO_HOME=str(d/'home'),CARGO_TARGET_DIR=str(d/'target'),CARGO_BUILD_BUILD_DIR=str(d/'shared'),RUSTC=str(SDK/'bin/rustc'),PATH=str(SDK/'bin')+':'+e['PATH'],LD_LIBRARY_PATH=str(SDK/'lib'),CARGO_BUILD_JOBS='2')
    e.update(extra or {})
    proc=subprocess.Popen([str(SDK/'bin/cargo'),*args],cwd=d,env=e,start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:o,er=proc.communicate(timeout=35)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid,signal.SIGKILL);o,er=proc.communicate();er+=b'\nAUDIT TIMEOUT'
    (d/(n+'.out')).write_bytes(o);(d/(n+'.err')).write_bytes(er)
    j={'argv':args,'rc':proc.returncode,'out':sha(d/(n+'.out')),'err':sha(d/(n+'.err')),'panic':b'panicked at' in er,'timeout':b'AUDIT TIMEOUT' in er}
    store(d/(n+'.json'),j);print(d.name,n,j['rc'],o[-85:],er[-200:],flush=True)
    return j
results={}
for label,pat in [('hash','lib-dep.public-api-hash'),('manifest','*.rlink-cache.json'),('recipe','*.rlink')]:
    d=R/('fifo-'+label);source(d,'app','[dependencies]\ndep={path="dep"}\n[workspace]\n','fn main(){println!("{}",dep::value());}')
    source(d/'dep','dep','','pub fn value()->u32{11}',True)
    j=call(d,'prime',['run','--offline','--quiet']);assert j['rc']==0 and (d/'prime.out').read_bytes()==b'11\n'
    files=sorted((d/'target').rglob(pat)); assert files,(d,pat)
    # Select the actual app recipe/manifest for the binary, as in the report.
    p=files[0];before=sha(p);p.unlink();os.mkfifo(p)
    (d/'dep/src/lib.rs').write_text('pub fn value()->u32{22}')
    j=call(d,'after',['run','--offline','--quiet']);results[label]={'outcome':j,'raw':(d/'after.out').read_text(),'entry':str(p.relative_to(d)),'old':before,'available':[str(x.relative_to(d)) for x in files]};store(R/'partial.json',results)
d=R/'null-env';source(d,'probe','[workspace]\n','fn main(){println!("{}",env!("SEEN"));}');(d/'build.rs').write_text('fn main(){ println!("cargo::rerun-if-env-changed=PROBE"); println!("cargo::rustc-env=SEEN={:?}",std::env::var_os("PROBE").as_ref().map(|v|v.as_encoded_bytes())); }')
j=call(d,'prime',['-Zohm-defaults=no','run','--offline','--quiet'],{'PROBE':os.fsdecode(b'\xff')});assert j['rc']==0
fp,=[p for p in d.rglob('run-build-script-*.json') if b'PROBE' in p.read_bytes()];s=json.loads(fp.read_bytes());(d/'before-fingerprint.json').write_bytes(fp.read_bytes())
for node in s['local']:
 if node.get('RerunIfEnvChanged',{}).get('var')=='PROBE':node['RerunIfEnvChanged']['val']=None;break
else:raise RuntimeError(s)
store(fp,s);j=call(d,'after',['-Zohm-defaults=no','run','--offline','--quiet']);results['null-env']={'outcome':j,'raw':(d/'after.out').read_text(),'synthetically_retained_legacy_null':True};store(R/'partial.json',results)
d=R/'wasm-edge';source(d,'app','[dependencies]\nactive-reg="=0.1.0"\n[workspace]\n','fn main(){println!("{}",active_reg::val());}')
index=d/'server';index.mkdir();readlog=[]
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_GET(self):readlog.append(self.path);super().do_GET()
    def __init__(self,*a,**k):super().__init__(*a,directory=str(index),**k)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);u='http://127.0.0.1:'+str(server.server_port)
threading.Thread(target=server.serve_forever,daemon=True).start();store(index/'config.json',{'dl':u+'/{crate}/{version}/download'})
for name,body,deps in [('absent-wasm','',[]),('active-reg',"[target.'cfg(target_arch = \"wasm32\")'.dependencies]\nabsent-wasm=\"=0.1.0\"\n",[{'name':'absent-wasm','req':'=0.1.0','features':[],'optional':False,'default_features':True,'target':'cfg(target_arch = "wasm32")','kind':'normal'}])]:
    cr=d/'packs'/name;source(cr,name,body,'pub fn val()->u32{47}',True);b=io.BytesIO()
    with tarfile.open(fileobj=b,mode='w:gz') as t:t.add(cr,arcname=name+'-0.1.0')
    raw=b.getvalue();meta={'name':name,'vers':'0.1.0','deps':deps,'cksum':hashlib.sha256(raw).hexdigest(),'features':{},'yanked':False}
    ix=index/name[:2]/name[2:4]/name;ix.parent.mkdir(parents=True,exist_ok=True);ix.write_text(json.dumps(meta)+'\n')
    if name=='active-reg':
        dest=index/name/'0.1.0'/'download';dest.parent.mkdir(parents=True);dest.write_bytes(raw)
(d/'.cargo').mkdir();(d/'.cargo/config.toml').write_text(f'[source.crates-io]\nreplace-with="local"\n[source.local]\nregistry="sparse+{u}/"\n')
rows=[call(d,'fetch',['fetch','--target','x86_64-unknown-linux-gnu'])]
server.shutdown()
for key,args in [('build',['build']),('check',['check']),('repeat',['check'])]:rows.append(call(d,key,args+['--locked','--offline']))
res={'rows':rows,'http_requests':readlog,'lock_contains_inactive':'name = "absent-wasm"' in (d/'Cargo.lock').read_text(),'inactive_package_archives':[str(x.relative_to(d)) for x in (d/'home').rglob('absent-wasm-0.1.0*')]}
results['inactive-wasm']=res;store(R/'complete.json',results)
