"""Create a genuinely cold official -16 Ruff workspace check state at the canonical paths."""
from pathlib import Path
import fcntl,hashlib,json,os,shutil,subprocess,sys,traceback
X=Path.home()/'.cache/ohm-233-position-qualified-20261027';Q=X/'build-script-current-stock-cold-v1';RAM=Path('/dev/shm/ohm-build-script-current-stock-seed-v1')
OLD=X/'cfg-library-first-v1-campaign/state/check';OFF=json.loads((X/'build-script-current-stock-sdk-v1/official.json').read_bytes());S=Path(OFF['sdk_root'])
sys.path[:0]=[str(X/'first-occurrence-worker-v2'),str(X/'nonparser-whole-inputs-impl-v1')]
from common import CARGO_HOME, TARGET, SHARED, P, FROZEN, RUFF, sha, dump, env, git
from namespace import skeleton
from process_scan import parse
def main():
 assert git('rev-parse','HEAD')=='93526150df078af7dd8fc4226cdcc469539d2001' and not git('status','--porcelain')
 assert not Q.exists() and not RAM.exists() and shutil.disk_usage(X).free>25*2**30 and shutil.disk_usage(RAM.parent).free>18*2**30
 Q.mkdir(mode=0o700);RAM.mkdir(mode=0o700);(RAM/'target').mkdir();(RAM/'shared').mkdir()
 for k in ('registry-home','rustup'):
  subprocess.run(['cp','-a','--reflink=auto','--',OLD/k,RAM/k],check=True);assert not (OLD/k).samefile(RAM/k)
 assert (RAM/'rustup/toolchains/ohm').resolve()==FROZEN.resolve()
 inherited=sorted([str(p.relative_to(RAM)) for n in ('target','shared') for p in (RAM/n).iterdir()]);assert not inherited
 d=Q/'exec';d.mkdir();base=skeleton(Q);envs=env()
 for k in ('RUSTC_LOG','CARGO_LOG','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','CARGO_ENCODED_RUSTFLAGS','RUSTFLAGS'):envs.pop(k,None)
 mounts=[v for a,b in [(Q,Q),(RAM/'target',TARGET),(RAM/'shared',SHARED),(RAM/'registry-home',CARGO_HOME),(RAM/'rustup',P/'rustup')] for v in ('--bind',str(a),str(b))]
 args=[*base,*mounts,'--ro-bind',str(S),str(FROZEN),'--chdir',str(RUFF),'--','taskset','-c','0-23']
 bindings={'empty_target_and_build_dir':inherited,'true_release':OFF,'command':['cargo','+ohm','check','--locked','--offline','--message-format=json','-j8']}
 dump(Q/'cold-binding.json',bindings);unit_id=None
 for phase in ('cold','untouched','second-untouched'):
  p=d/phase;p.mkdir();cmd=['strace','-qq','-ff','-s','1048576','-e','trace=execve,execveat','-o',str(p/'exec'),*bindings['command']]
  # Parse in the same mount namespace: the -16 frontend/driver/Wild are physically different from the old SDK.
  with (p/'cargo.stdout').open('wb') as out,(p/'cargo.stderr').open('wb') as err:cp=subprocess.run([*args,*cmd],cwd=RUFF,env=envs,stdout=out,stderr=err)
  assert cp.returncode==0,(phase,cp.returncode,(p/'cargo.stderr').read_text()[-900:])
  inner="import sys;sys.path[:0]="+repr([str(X/'first-occurrence-worker-v2'),str(X/'nonparser-whole-inputs-impl-v1')])+";from pathlib import Path;from process_scan import parse;parse(Path(sys.argv[1]),'cold')"
  subprocess.run([*args,sys.executable,'-B','-c',inner,str(p)],check=True,env=envs)
  rec=json.loads((p/'processes.json').read_bytes());rows=[json.loads(l) for l in (p/'cargo.stdout').read_bytes().splitlines()];arts=[r for r in rows if r['reason']=='compiler-artifact'];msgs=[r for r in rows if r['reason']=='compiler-message']
  assert len(arts)==520 and not msgs and any(r['reason']=='build-finished' and r['success'] for r in rows),(phase,len(arts),len(msgs))
  ids=sorted((r['package_id'],r['target']['name'],r['target']['kind'],r['profile']['test']) for r in arts)
  if unit_id is None:unit_id=ids
  assert ids==unit_id
  r={'units':520,'fresh':sum(r['fresh'] for r in arts),'physical':rec['typed_invocations'],'warnings':msgs,'unknown':rec['unclassified'],'trace':sha(p/'exec-traces.tar.zst'),'roster':hashlib.sha256(json.dumps(ids,sort_keys=True).encode()).hexdigest(),'stdout':sha(p/'cargo.stdout'),'stderr':sha(p/'cargo.stderr')}
  dump(p/'receipt.json',r);print(phase,r['fresh'],r['physical'],flush=True)
  if phase=='cold':assert rec['typed_invocations'].get('rustc-full',0)>200
  else:assert r['fresh']==520 and not any(rec['typed_invocations'].get(k,0) for k in ('rustc-full','rustc-link-only','wild'))
  assert shutil.disk_usage(X).free>25*2**30 and shutil.disk_usage(RAM).free>10*2**30
 dump(Q/'ready.json',{'actual_sdk':OFF['hashes'],'state':str(RAM),'empty_inputs':inherited,'all_three_phases':True})
if __name__=='__main__':
 try:
  with (P/'native-measure.lock').open('rb') as l:fcntl.flock(l,fcntl.LOCK_EX);main()
 except BaseException:
  if Q.is_dir():(Q/'failure.txt').write_text(traceback.format_exc())
  raise
