"""Use ordinary Cargo to rebuild only its two subject units over byte-identical upstream artifacts."""
from pathlib import Path
import fcntl,hashlib,json,os,re,shutil,signal,subprocess as sp,time
X=Path('/mnt/devbox-scratch/dev-user/ohm-producer-attestation-rc17-20261028');Y=Path('/mnt/devbox-scratch/dev-user/ohm-producer-attestation-pinned-20261028')
D=Path('/mnt/devbox-scratch/dev-user/ohm-observer-shipping-20261027');S=D/'states/raw-rc17'; CAN=D/'src-rc17';STATE=Y/'common-state'
A='A';I=X/'inputs';src0=X/'A/src'
def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,z):p.write_text(json.dumps(z,sort_keys=True,indent=2)+'\n')
def data(p):return json.loads(p.read_bytes())
def relocated(path):
 path=Path(path)
 if path.is_relative_to(S):
  name=path.relative_to(S)
  if name.parts[0] in ('shared','target','cargo-home'): return STATE/name
 return path
def compile_rows(w,stage):
 rows={}; jobs=set(); failed=[]
 for l in (w/'compiler.exec').read_text().splitlines():
  if 'execve(' not in l or '"--crate-name", ' not in l or '"--print=' in l:continue
  exe=l.split('execve("',1)[1].split('"',1)[0]
  if exe.rsplit('/',1)[-1]!='rustc' or ' = -1 ' in l:continue
  args=re.findall(r'"((?:\\.|[^"\\])*)"',l.split('execve(',1)[1])[1:]
  if '--crate-name' not in args: continue
  kr=args[args.index('--crate-name')+1];jobs.add((kr, args[args.index('--crate-type')+1] if '--crate-type' in args else 'unknown'))
  if kr!='cargo' or 'profile-use=' not in l:continue
  source=next((src for src in ('src/lib.rs','src/bin/cargo/main.rs') if src in args),None)
  if source is None:continue
  ext={};native={}
  for i,q in enumerate(args[:-1]):
   if q=='--extern':
    k,filename=args[i+1].split('=',1)
    canonical=Path(filename);p=relocated(canonical);assert p.is_file(),p
    files=[(p,filename)]
    if p.suffix=='.rmeta':
     other=p.with_suffix('.rlib');assert other.is_file(),other
     files.append((other,str(canonical.with_suffix('.rlib'))))
    ext[k]={n:sha(f) for f,n in files}
   if q=='-L' and args[i+1].startswith('native='):
    n=args[i+1][len('native='):];d=relocated(n)
    assert d.is_dir(),d
    for f in sorted(d.iterdir()):
     if f.is_file() and (f.suffix in ('.a','.o','.so') or '.so.' in f.name):native[str(Path(n)/f.name)]=sha(f)
  row={'argv':hashlib.sha256(b'\0'.join(v.encode() for v in args)).hexdigest(),'externs':ext,'native':native}
  assert source not in rows or rows[source]==row,(stage,source)
  rows[source]=row
 assert len(rows)==2 and len(rows['src/lib.rs']['externs'])==80 and len(rows['src/bin/cargo/main.rs']['externs'])==81,(stage,rows.keys(),jobs)
 return rows,sorted(jobs)
def commonrows(rows):
 return {src:{'argv':row['argv'],'native':row['native'],'externs':{k:v for k,v in row['externs'].items() if k!='cargo'}} for src,row in rows.items()}
def verify_source(arm):
 manifests={t:{n:(mode,g) for n,mode,g in data(I/(t+'.json'))['files']} for t in ('A',arm)}
 assert set(manifests['A'])==set(manifests[arm]);diff=sorted(n for n in manifests[arm] if manifests[arm][n]!=manifests['A'][n])
 assert len(diff) in (0,2)
 for name,(mode,g) in manifests[arm].items():
  p=(X/arm/'src'/name) if name in diff else (src0/name)
  buf=os.fsencode(os.readlink(p)) if mode=='120000' else p.read_bytes()
  assert hashlib.sha1(f'blob {len(buf)}\0'.encode()+buf).hexdigest()==g and (mode=='120000' or (p.stat().st_mode & 0o100!=0)==(mode=='100755')),(arm,name)
 return diff
assert (X/'complete.json').is_file() and sha(D/'assets/rustc-pgo.profdata')=='481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7'
env=dict(os.environ,PATH='/home/dev-user/.cargo/bin:'+os.environ['PATH'],RUSTUP_HOME=str(S/'rustup'),CARGO_HOME=str(S/'cargo-home'),CARGO_TARGET_DIR=str(S/'target'),CARGO_BUILD_BUILD_DIR=str(S/'shared'),CARGO_NET_OFFLINE='true',CARGO_PROFILE_RELEASE_INCREMENTAL='false',CFG_RELEASE_CHANNEL='dev',RUSTFLAGS='-Cprofile-use='+str(D/'assets/rustc-pgo.profdata')+' -Cllvm-args=-pgo-warn-missing-function=false')
for k in ('RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','CARGO_ENCODED_RUSTFLAGS','CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST','CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST'):env.pop(k,None)
with (D.parent/'ohm-spaced-ruff-20261027/matched-qualify.lock').open('a') as f:
 fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);assert shutil.disk_usage(Y.parent).free>64*2**30
 STATE.mkdir()
 for n in ('target','shared','cargo-home'):
  sp.run(['cp','-a','--reflink=auto',str(X/'A/state'/n),str(STATE/n)],check=True)
 assert (STATE/'target/release/cargo').stat().st_ino!=(X/'A/state/target/release/cargo').stat().st_ino
 reference=None
 for stage,arm in [('seed','A'),('A','A'),('Q','Q'),('N','N'),('A-repeat','A')]:
  w=Y/stage;w.mkdir();diff=verify_source(arm)
  saved=w/'previous-cargo-unit-dirs';saved.mkdir();dirs=set()
  for lab in ('lib-cargo','bin-cargo'):
   for p in (STATE/'target/release/build/workspaces').rglob(lab):
    assert p.parent.name=='fingerprint' and p.parent.parent.parent.name=='cargo';dirs.add(p.parent.parent)
  assert len(dirs)==2,(stage,dirs)
  for idx,p in enumerate(sorted(dirs)):p.rename(saved/(str(idx)+'-'+p.name))
  a=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(src0),str(CAN)]
  for d in diff:a+=['--ro-bind',str(X/arm/'src'/d),str(CAN/d)]
  for d in ('target','shared','cargo-home'):a+=['--bind',str(STATE/d),str(S/d)]
  a+=['--chdir',str(CAN),'--','taskset','-c','8-23','/home/dev-user/.cargo/bin/cargo','+ohm','build','--release','--offline','--locked','-p','cargo','--bin','cargo','--features','ohm-defaults','-j12']
  with (w/'build.log').open('wb') as handle:
   proc=sp.Popen(['strace','-f','-qq','-s','65535','-e','trace=execve,execveat','-o',str(w/'compiler.exec'),*a],env=env,stdout=handle,stderr=sp.STDOUT,start_new_session=True)
   while proc.poll() is None:
    if shutil.disk_usage(Y).free<25*2**30:os.killpg(proc.pid,signal.SIGTERM);proc.wait();raise RuntimeError(('25GiB floor',stage))
    time.sleep(.5)
  assert proc.returncode==0,(stage,(w/'build.log').read_text()[-2000:])
  rows,jobs=compile_rows(w,stage);save(w/'actual-inputs.json',rows)
  stable=commonrows(rows);src=data(I/(arm+'.json'))['commit']
  output=w/'cargo';shutil.copy2(STATE/'target/release/cargo',output)
  version=sp.check_output([output,'-Vv'],text=True);assert version==(D/'subjects/rc17-complete-v4.version').read_text()
  r={'stage':stage,'subject':src,'compiler':sha(D/'assets/stock16-sdk/bin/rustc'),'profile':sha(D/'assets/rustc-pgo.profdata'),'version':version,'binary':sha(output),'jobs':jobs,'source_verified':3108,'changed_source_paths':diff,'native_log':sha(w/'compiler.exec'),'actual_inputs_sha256':sha(w/'actual-inputs.json'),'common_nonproduct_inputs_sha256':hashlib.sha256(json.dumps(stable,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'argv':a}
  save(w/'receipt.json',r);print(stage,src,r['binary'],len(jobs),r['common_nonproduct_inputs_sha256'],flush=True)
  if stage=='seed':continue
  assert jobs==[('cargo','bin'),('cargo','lib')],(stage,jobs)
  if reference is None:reference=stable
  else:assert stable==reference,(stage,'changed dependency or compiler flags')
  if stage=='A-repeat':assert r['binary']==data(Y/'A/receipt.json')['binary'],('full repeat ELF',r['binary'],data(Y/'A/receipt.json')['binary'])
 save(Y/'complete.json',{k:data(Y/k/'receipt.json') for k in ('A','Q','N','A-repeat','seed')})
