from pathlib import Path
import argparse,hashlib,json,os,shutil,signal,subprocess,sys
def sha(data):return hashlib.sha256(data).hexdigest()
def record(p,x):p.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
def file(p):
 s=p.stat();return [s.st_dev,s.st_ino,s.st_mtime_ns,s.st_ctime_ns,s.st_size,sha(p.read_bytes())]
def put(p,b):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(b)
def require(v,msg):
 if not v:raise RuntimeError(str(msg))
parser=argparse.ArgumentParser()
parser.add_argument('--image',type=Path,required=True);parser.add_argument('--sha',required=True)
parser.add_argument('--sdk',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
x=parser.parse_args();root=x.output.resolve();root.mkdir(mode=0o700);base=Path(__file__).resolve().parent
require(sha(x.image.read_bytes())==x.sha,'image sha')
sdk=root/'ru/toolchains/ohm';(sdk/'bin').mkdir(parents=True);(sdk/'lib').symlink_to(x.sdk.resolve()/'lib',target_is_directory=True)
for role,src in [('rustc',x.sdk.resolve()/'bin/rustc'),('cargo',x.image.resolve())]:(sdk/'bin'/role).symlink_to(src)
ws=root/'ws';dep=root/'late/Cargo.toml';incoming=dep.with_name('Cargo.toml.incoming')
put(ws/'Cargo.toml','[workspace]\nmembers=["member"]\nexclude=["bridge"]\nresolver="2"\n')
put(ws/'member/Cargo.toml','[package]\nname="member"\nversion="0.1.0"\nedition="2021"\n[dependencies]\nbridge={path="../bridge"}\n')
put(ws/'member/src/lib.rs','pub fn answer()->u8{bridge::answer()}\n')
put(ws/'bridge/Cargo.toml','[package]\nname="bridge"\nversion="0.1.0"\nedition="2021"\n[dependencies]\nlate={path="../../late"}\n')
put(ws/'bridge/src/lib.rs','pub fn answer()->u8{late::answer()}\n')
put(dep,'[package]\nname="late"\nversion="0.1.0"\nedition="2021"\n')
put(root/'late/src/lib.rs','pub fn answer()->u8{29}\n')
env={'HOME':str(Path.home()),'PATH':os.environ.get('RUSTUP_PROXY_DIR', str(Path.home()/'.cargo/bin'))+':/usr/bin:/bin','LC_ALL':'C','RUSTUP_HOME':str(root/'ru'),'RUSTUP_AUTO_INSTALL':'0',
     'CARGO_HOME':str(root/'cargo-home'),'CARGO_TARGET_DIR':str(root/'target'),'CARGO_BUILD_BUILD_DIR':str(root/'build'),
     'CARGO_EXPERIMENTAL_RESOLVE_CACHE':'1','CARGO_NET_OFFLINE':'true','CARGO_TERM_COLOR':'never',
     'CARGO_LOG':'cargo::resolver::encode=debug,cargo::ops::resolve=debug'}
for n in ['cargo','rustc']:
 cp=subprocess.run([n,'+ohm','-Vv'],cwd=ws,env=env,capture_output=True,check=True);(root/(n+'-version')).write_bytes(cp.stdout)
marker=root/'target/.cargo-resolve-cache-v1';lock=ws/'Cargo.lock'
def met(label,*,locked=True,expected=0,actor=False,cache=True):
 floors=[shutil.disk_usage(root).free];require(floors[0]>16*2**20,floors)
 d=root/label;d.mkdir();before=file(lock) if lock.exists() else None
 args=['strace','-f','-qq','-ttt','-yy','-s','2048','-e','trace=open,openat,read,flock,close,rename,renameat,renameat2,execve','-o',d/'kernel.trace','cargo','+ohm','metadata','--format-version','1','--offline']
 if locked:args+=['--locked']
 A=subprocess.Popen([sys.executable,'-IB',base/'actor.py',root],stdout=(d/'actor.out').open('wb'),stderr=(d/'actor.err').open('wb'),start_new_session=True) if actor else None
 with (d/'stdout').open('wb') as so,(d/'stderr').open('wb') as se:
  P=subprocess.Popen(args,env={**env,'CARGO_EXPERIMENTAL_RESOLVE_CACHE':'1' if cache else '0'},cwd=ws,stdout=so,stderr=se,start_new_session=True)
  try:ret=P.wait(timeout=8)
  except subprocess.TimeoutExpired:
   os.killpg(P.pid,signal.SIGKILL);P.wait();ret=-1
 aret=None
 if A:
  try:aret=A.wait(timeout=2)
  except subprocess.TimeoutExpired:
   os.killpg(A.pid,signal.SIGKILL);A.wait();aret=-1
  if (root/'actor.json').exists():os.rename(root/'actor.json',d/'actor.json')
 res={'phase':label,'exit':ret,'writer_exit':aret,'lock_before':before,'lock_after':file(lock),'free':floors,
      'stdout_sha256':sha((d/'stdout').read_bytes()),'stderr_sha256':sha((d/'stderr').read_bytes()),'kernel_sha256':sha((d/'kernel.trace').read_bytes())}
 stderr=(d/'stderr').read_text();res['diagnostic']='error:'+stderr.split('error:',1)[1] if 'error:' in stderr else None
 if ret==0:
  meta=json.loads((d/'stdout').read_text());nodes={v['id']:v['name'] for v in meta['packages']};res['edges']=sorted([nodes[p['id']],nodes[other]] for p in meta['resolve']['nodes'] for other in p['dependencies'])
 record(d/'row.json',res)
 print(label,'exit',ret,'actor',aret,'edges',res.get('edges'),'diag',repr((res['diagnostic'] or '')[:400]),flush=True)
 require(ret==expected and (not actor or aret==0),(label,ret,aret,stderr[-750:]))
 if locked:require(before==res['lock_after'],label+' changed Cargo.lock')
 if ret==0:require(res['edges']==[['bridge','late'],['member','bridge']],res['edges'])
 return res
seed=met('seed',locked=False);require(marker.is_file(),'seed did not train marker');gold=lock.read_bytes();(root/'gold.lock').write_bytes(gold)
boundary=b'name = "late"\nversion = "0.1.0"';require(gold.count(boundary)==1,boundary)
bad=gold.replace(boundary,b'name = "late"\nversion = "not-a-version"');broken=b'version = [\n'
for stage,payload,exp in [('valid',gold,0),('semantic',bad,101)]:
 if marker.exists():marker.unlink()
 os.mkfifo(marker,0o600);os.rename(dep,incoming);lock.write_bytes(payload)
 row=met(stage+'-appears',expected=exp,actor=True)
 if marker.exists():marker.unlink()
 control=met(stage+'-present-control',expected=exp,cache=False)
 if exp==101:
  require(row['diagnostic']==control['diagnostic'] and 'failed to parse lock file' in row['diagnostic'],(row['diagnostic'],control['diagnostic']))
 else:require(row['edges']==control['edges'],stage)
if marker.exists():marker.unlink()
os.mkfifo(marker,0o600);lock.write_bytes(broken)
mal=met('malformed-first-no-writer',expected=101);require(marker.is_fifo(),'malformed unexpectedly changed FIFO');marker.unlink()
same=met('malformed-static-control',expected=101,cache=False);require(mal['diagnostic']==same['diagnostic'],mal)
lock.write_bytes(gold);met('recovered');met('unchanged')
record(root/'terminal.json',{'image':x.sha,'true_empty_writes':0,'stages':['seed','valid-appears','valid-present-control','semantic-appears','semantic-present-control','malformed-first-no-writer','malformed-static-control','recovered','unchanged']})
