from pathlib import Path
import hashlib,fcntl,json,os,shutil,subprocess,traceback
D=Path(__file__).resolve().parent;R=D/'unit-replay-v1';S=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
B=Path.home()/'.cache/ohm-mixed-cargo-release-20261027';C=Path('/dev/shm/ohm-current-cargo-units-cache-v1');CAN=B/'source';TARGET=B/'target';SYNC=B/'trusted-build';REG=B/'registry-home';RUP=S/'rustup'
def j(p,z):p.write_text(json.dumps(z,sort_keys=True,indent=1)+'\n')
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert D.is_dir() and not R.exists() and shutil.disk_usage(D).free>=25*2**30 and shutil.disk_usage(C.parent).free>17*2**30
 R.mkdir(mode=0o700)
 assert not C.exists();subprocess.run(['cp','-a','--reflink=auto','--',D.parent/'build-script-cargo-release-v1/independent-v4/cache',C],check=True)
 src=D/'qualified-source-v2';neg=R/'parent-with-test';shutil.copytree(src/'candidate',neg,symlinks=True)
 f=Path('src/compiler/fingerprint/mod.rs')
 new=(src/'candidate'/f).read_text();a=(src/'parent'/f).read_text()
 i='    #[test]\n    fn restored_check_metadata_uses_the_build_script_result_generation()';mark='    #[test]\n    fn unit_not_stale_due_to_dep_should_not_cutoff()'
 test=new[new.index(i):new.index(mark)]
 assert i not in a and i in new and new.count(mark)==a.count(mark)==1
 (neg/f).write_text(a.replace(mark,test+mark))
 for label,source,req in [('candidate',src/'candidate',0),('parent-with-regression',neg,101)]:
  assert not (R/(label+'.log')).exists()
  env=dict(os.environ,RUSTUP_HOME=str(RUP),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(REG),CARGO_TARGET_DIR=str(TARGET),CARGO_BUILD_BUILD_DIR=str(SYNC),CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',CARGO_PROFILE_TEST_DEBUG='0',CARGO_PROFILE_TEST_INCREMENTAL='false',CARGO_NET_OFFLINE='true',CFG_RELEASE_CHANNEL='dev')
  for k in ('RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER'):env.pop(k,None)
  args=['taskset','-c','24-31','bwrap','--ro-bind','/','/','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--bind',str(R),str(R),'--bind',str(C/'target'),str(TARGET),'--bind',str(C/'shared'),str(SYNC),'--bind',str(C/'registry'),str(REG),'--bind',str(C/'rustup'),str(RUP),'--ro-bind',str(source),str(CAN),'--chdir',str(CAN),'--','cargo','+ohm','test','--offline','--locked','-p','cargo','--lib','--features','ohm-defaults','-j8','restored_check_metadata_uses_the_build_script_result_generation']
  print('START',label,flush=True)
  with (R/(label+'.log')).open('wb') as out:p=subprocess.run(args,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT)
  l=(R/(label+'.log')).read_text(errors='replace');j(R/(label+'.json'),{'exit':p.returncode,'expected_exit':req,'source_file_sha256':h(source/f),'argv':args,'log_sha256':h(R/(label+'.log')),'last_lines':l.splitlines()[-20:]})
  assert p.returncode==req and ('1 passed;' in l if req==0 else '1 failed;' in l and 'assertion `left == right` failed' in l),(label,p.returncode,l[-1000:])
  print('MATCH',label,p.returncode,flush=True)
 assert C==Path('/dev/shm/ohm-current-cargo-units-cache-v1');shutil.rmtree(C)
if __name__=='__main__':
 try:
  with (S/'native-measure.lock').open('rb') as lock:fcntl.flock(lock,fcntl.LOCK_EX);main()
 except BaseException:(D/'units-failure.txt').write_text(traceback.format_exc());raise
