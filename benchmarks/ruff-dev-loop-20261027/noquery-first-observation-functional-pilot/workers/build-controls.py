"""Build provenance-matched native Cargo release controls from independent copies of the same donor."""
import fcntl,hashlib,json,os,re,shutil,socket,subprocess as s,sys,time
from pathlib import Path
X=Path(__file__).resolve().parent.parent;I=X/'inputs'
D=Path('/mnt/devbox-scratch/dev-user/ohm-observer-shipping-20261027');S=D/'states/raw-rc17';canonical=D/'src-rc17';native=Path('/mnt/devbox-scratch/dev-user/ohm-spaced-ruff-20261027')
assert X==Path('/mnt/devbox-scratch/dev-user/ohm-producer-attestation-rc17-20261028') and socket.gethostname()=='charlie-ohm-cargo5-build-1025'
sha=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
dump=lambda p,x:p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def verify_source(r,arm):
 for o in json.loads((I/(arm+'.json')).read_bytes())['files']:
  n,mode,key=o; p=r/n
  assert (p.is_symlink() if mode=='120000' else p.is_file() and not p.is_symlink()),(arm,n)
  data=os.fsencode(os.readlink(p)) if mode=='120000' else p.read_bytes()
  assert hashlib.sha1(f'blob {len(data)}\x00'.encode()+data).hexdigest()==key,(arm,n)
  assert mode=='120000' or ((p.stat().st_mode & 0o100)!=0)==(mode=='100755'),(arm,n,mode)
assert sha(D/'assets/rustc-pgo.profdata')=='481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7'
assert sha(D/'assets/git-commit-info-rc17')=='4e83718109f1a02195592740c79a8b87a3cb472198db7cde721b0b948daf262d'
assert sha(D/'subjects/rc17-complete-v4')=='787ed90b5a14000ac0b1efc1d1aac5d730e0107b2e995cc0471138402759a4d5'
s.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=I,check=True)
assert (native/'rc17-spaced-wall-v3/result.json').is_file()
with (native/'matched-qualify.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert shutil.disk_usage(X).free>50*2**30
 for arm in ('A','N','Q'):
  w=X/arm;w.mkdir();r=w/'src';r.mkdir()
  s.run(['tar','xf',str(I/'base-source.tar'),'-C',str(r)],check=True)
  if arm!='A':s.run(['git','apply',str(I/(arm+'.patch'))],cwd=r,check=True)
  verify_source(r,arm);shutil.copy2(D/'assets/git-commit-info-rc17',r/'git-commit-info')
  state=w/'state';state.mkdir()
  for d in ('target','shared','cargo-home'):
   s.run(['cp','-a','--reflink=auto',str(S/d),str(state/d)],check=True)
  assert (state/'target/release/cargo').stat().st_ino!=(S/'target/release/cargo').stat().st_ino
  retained=w/'donor-package-archives';retained.mkdir();unitdirs=set()
  for label in ('bin-cargo','lib-cargo'):
   for p in (state/'target/release/build/workspaces').rglob(label):
    parent=p.parent.parent;assert parent.parent.name=='cargo' and p.parent.name=='fingerprint';unitdirs.add(parent)
  assert len(unitdirs)>=2
  for num,src in enumerate(sorted(unitdirs)):src.rename(retained/(str(num)+'-'+src.name))
  args=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(r),str(canonical)]
  for d in ('target','shared','cargo-home'):args+=['--bind',str(state/d),str(S/d)]
  env=dict(os.environ,PATH='/home/dev-user/.cargo/bin:'+os.environ['PATH'],RUSTUP_HOME=str(S/'rustup'),CARGO_HOME=str(S/'cargo-home'),CARGO_TARGET_DIR=str(S/'target'),CARGO_BUILD_BUILD_DIR=str(S/'shared'),CARGO_NET_OFFLINE='true',CARGO_PROFILE_RELEASE_INCREMENTAL='false',CFG_RELEASE_CHANNEL='dev',RUSTFLAGS='-Cprofile-use='+str(D/'assets/rustc-pgo.profdata')+' -Cllvm-args=-pgo-warn-missing-function=false')
  for v in ('RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','CARGO_ENCODED_RUSTFLAGS','CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST','CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST'):env.pop(v,None)
  cmd=args+['--chdir',str(canonical),'--','taskset','-c','8-23','/home/dev-user/.cargo/bin/cargo','+ohm','build','--release','--locked','--offline','-p','cargo','--bin','cargo','--features','ohm-defaults','-j12']
  trace=w/'compiler.exec';start=time.time();rfiles=open(w/'build.log','wb')
  p=s.Popen(['strace','-f','-qq','-s','65535','-e','trace=execve,execveat','-o',str(trace),*cmd],env=env,stdout=rfiles,stderr=s.STDOUT)
  while p.poll() is None:
   if shutil.disk_usage(X).free<25*2**30:p.terminate();p.wait();raise RuntimeError('25GiB floor')
   time.sleep(.8)
  rfiles.close();assert p.returncode==0,(arm,(w/'build.log').read_text()[-2500:])
  full={};probe=[]
  for l in trace.read_text().splitlines():
   if '"--crate-name", "cargo"' not in l or 'execve' not in l:continue
   if '"--print=' in l or '"link-only"' in l:continue
   for k in ('src/lib.rs','src/bin/cargo/main.rs'):
    if '"'+k+'"' in l and 'profile-use=' in l:full[k]=hashlib.sha256(l.encode()).hexdigest()
  assert len(full)==2,(arm,full)
  target=state/'target/release/cargo';dst=w/'cargo';shutil.copy2(target,dst);version=s.check_output([dst,'-Vv'],text=True)
  assert version==(D/'subjects/rc17-complete-v4.version').read_text()
  fds={'subject':json.loads((I/(arm+'.json')).read_bytes())['commit'],'full_compiles':full,'binary':sha(dst),'version':version,'stamp':sha(r/'git-commit-info'),'pgo':sha(D/'assets/rustc-pgo.profdata'),'builder':sha(D/'assets/stock16-sdk/bin/rustc'),'seconds':time.time()-start,'free':shutil.disk_usage(X).free,'old_A':sha(D/'subjects/rc17-complete-v4'),'identical_to_old_A':sha(dst)==sha(D/'subjects/rc17-complete-v4'),'trace_sha256':sha(trace),'cmd':cmd,'source_verified_leaves':len(json.loads((I/(arm+'.json')).read_bytes())['files'])}
  dump(w/'receipt.json',fds);print(arm,fds['subject'],fds['binary'],'compiles=2',flush=True)
 dump(X/'complete.json',{arm:json.loads((X/arm/'receipt.json').read_bytes()) for arm in ('A','N','Q')})
