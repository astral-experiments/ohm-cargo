from pathlib import Path
import fcntl,hashlib,json,os,shutil,subprocess,sys,tarfile,traceback
BASE=Path(__file__).resolve().parent;D=BASE/'packaged-v5';P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');B=Path.home()/'.cache/ohm-mixed-cargo-release-20261027';C=Path('/dev/shm/ohm-current-cargo-release-cache-v1');source=BASE/'qualified-source-v2';ref=json.loads((BASE/'subject.json').read_bytes());candidate_patch=BASE/'candidate.patch';CAN=B/'source';T=B/'target';SH=B/'trusted-build';REG=B/'registry-home';RUSTUP=P/'rustup';SDK=(RUSTUP/'toolchains/ohm').resolve()
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,data):p.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
def sh(cmd,**kw):return subprocess.run(cmd,check=True,**kw)
def stamp_source(q):return {str(p.relative_to(q)):hashlib.sha256(os.fsencode(os.readlink(p))).hexdigest() if p.is_symlink() else sha(p) for p in sorted(q.rglob('*')) if (p.is_symlink() or p.is_file()) and p.name!='git-commit-info'}
def make():
 assert not source.exists() and not D.exists() and not C.exists() and shutil.disk_usage(C.parent).free>17*2**30
 assert sha(BASE/'source.tar.gz')==ref['source_tar_gzip_sha256'] and sha(candidate_patch)==ref['patch_sha256']
 source.mkdir()
 for arm in ('parent','candidate'):
  q=source/arm;q.mkdir()
  with tarfile.open(BASE/'source.tar.gz') as t:
   t.extractall(q,filter='data')
   for member in t:
    if not member.issym():continue
    link=q/member.name
    if os.readlink(link)!=member.linkname:
     assert (link.parent/member.linkname).resolve().is_relative_to(q.resolve())
     link.unlink();link.symlink_to(member.linkname)
  if arm=='candidate':sh(['git','apply','--check',str(candidate_patch)],cwd=q);sh(['git','apply',str(candidate_patch)],cwd=q)
  binding=json.loads((BASE/'source-sha.json').read_bytes())[arm];r=stamp_source(q);assert r==binding,(len(r),len(binding),[k for k in r if r.get(k)!=binding.get(k)][:5]);shutil.copy2(BASE/'git-commit-info',q/'git-commit-info')
 assert ref['previous_source_version_sha256']==sha(BASE/'git-commit-info')
 tool_sha={str(p):sha(p) for p in [SDK/'bin/cargo',SDK/'bin/rustc',*list((SDK/'lib').glob('librustc_driver*.so')),B/'rustc-pgo.profdata']};put(BASE/'builder.json',{'tool_hashes':tool_sha,'rustup_ohm':str(SDK),'source_pgo':str(B/'rustc-pgo.profdata'),'original_warmed_donor':str(B/'target-observer3'),'identical_binding_for_arms':{str(REG):str(C/'registry'),str(T):str(C/'target'),str(SH):str(C/'shared')},'source_manifest_sha256':sha(BASE/'source-sha.json'),'previous_source_version':(BASE/'git-commit-info').read_text()})
 D.mkdir(mode=0o700)
 for name in ('source-sha.json','subject.json','builder.json','git-commit-info'):shutil.copy2(BASE/name,D/name)
 from importlib.util import spec_from_file_location,module_from_spec
 sp=spec_from_file_location('native_release_package',BASE/'package-v2.py');pkg=module_from_spec(sp);sp.loader.exec_module(pkg)
 old=BASE.parent/'build-script-cargo-release-v1';seed=old/'independent-v4/private-common-seed';assert seed.is_dir()
 # This already-pruned immutable dependency seed is privately restored for each of three fresh actual compilations.
 put(D/'seed.json',json.loads((old/'independent-v4/seed.json').read_bytes()))
 def seed_hash():
  h=hashlib.sha256();n=0
  for p in sorted(seed.rglob('*')):
   if not (p.is_symlink() or p.is_file()):continue
   b=os.fsencode(os.readlink(p)) if p.is_symlink() else bytes.fromhex(sha(p))
   h.update(os.fsencode(p.relative_to(seed))+b'\0'+(b'L' if p.is_symlink() else b'F')+b+b'\0');n+=1
  return n,h.hexdigest()
 attestation=seed_hash();put(D/'seed-attestation.json',{'original_files':attestation[0],'tree_sha256':attestation[1]})
 floor=25*2**30
 for arm in ('parent','candidate'):
  q=source/arm;assert stamp_source(q)==json.loads((D/'source-sha.json').read_bytes())[arm]
 assert sha(B/'rustc-pgo.profdata')==ref['pgo']
 def proof(log):
  lines=log.read_text(errors='strict').splitlines()
  matches=[l for l in lines if '/bin/rustc ' in l and '--crate-name cargo --edition=2024' in l and (' src/lib.rs ' in l or ' src/bin/cargo/main.rs ' in l)]
  assert any(' src/lib.rs ' in l for l in matches) and any(' src/bin/cargo/main.rs ' in l for l in matches),len(matches)
  return matches
 def compile(arm,source_arm,library_test=False):
  q=source/source_arm;shutil.copystat(D/'git-commit-info',q/'git-commit-info');os.utime(q/'build.rs');os.utime(q/'src/compiler/fingerprint/mod.rs')
  n=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(D),str(D),'--bind',str(C/'registry'),str(REG),'--bind',str(C/'shared'),str(SH),'--bind',str(C/'target'),str(T),'--bind',str(C/'rustup'),str(RUSTUP),'--ro-bind',str(q),str(CAN),'--chdir',str(CAN),'--']
  env=dict(os.environ,RUSTUP_HOME=str(RUSTUP),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(REG),CARGO_TARGET_DIR=str(T),CARGO_BUILD_BUILD_DIR=str(SH),CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',CARGO_PROFILE_RELEASE_INCREMENTAL='false',CFG_RELEASE_CHANNEL='dev',RUSTFLAGS='-Cprofile-use='+str(B/'rustc-pgo.profdata')+' -Cllvm-args=-pgo-warn-missing-function=false',CARGO_NET_OFFLINE='true')
  if library_test:
   args=['cargo','+ohm','test','--locked','--offline','-p','cargo','--lib','--features','ohm-defaults','-j8','restored_check_metadata_uses_the_build_script_result_generation'];env['CARGO_PROFILE_TEST_DEBUG']='0';env['CARGO_PROFILE_TEST_INCREMENTAL']='false'
   env.pop('RUSTFLAGS',None)
  else:args=['cargo','+ohm','build','--release','--locked','--offline','-p','cargo','--bin','cargo','--features','ohm-defaults','-j8','-vv']
  cmd=['taskset','-c','24-31',*n,*args];put(D/(arm+'-invocation.json'),{'command':cmd,'environment':{k:v for k,v in env.items() if k.startswith(('RUSTUP_','CFG_','RUSTFLAGS','CARGO_PROFILE_','CARGO_UNSTABLE_'))},'fixture':source_arm});print('START',arm,flush=True)
  with (D/(arm+'-private.log')).open('wb') as f:cp=subprocess.run(cmd,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT)
  if library_test:
   put(D/(arm+'-result.json'),{'exit':cp.returncode,'tail':(D/(arm+'-private.log')).read_text(errors='replace').splitlines()[-18:]});assert cp.returncode==0,(arm,cp.returncode);return
  assert cp.returncode==0,(arm,cp.returncode,(D/(arm+'-private.log')).read_text(errors='replace')[-1600:]);dest=D/('cargo-'+arm);shutil.copyfile(C/'target/release/cargo',dest);dest.chmod(0o555)
  srcproof=proof(D/(arm+'-private.log'))
  vl=subprocess.check_output([str(dest),'-Vv'],text=True);assert 'commit-hash: 4c07cbf6bd91e170e3b8904eeb82436a6dbde358' in vl,vl
  put(D/(arm+'-result.json'),{'exit':0,'cargo_sha256':sha(dest),'cargo_bytes':dest.stat().st_size,'source':source_arm,'compiled_cargo_commands':[hashlib.sha256(l.encode()).hexdigest() for l in srcproof],'version':vl,'pgo':sha(B/'rustc-pgo.profdata'),'private_release_log_sha256':sha(D/(arm+'-private.log'))});print('READY',arm,sha(dest),flush=True);assert shutil.disk_usage(D).free>=floor
 for arm,src in [('parent','parent'),('candidate','candidate'),('parent-repeat','parent')]:
  assert not C.exists() and shutil.disk_usage(D).free>25*2**30 and shutil.disk_usage(C.parent).free>15*2**30
  sh(['cp','-a','--reflink=auto','--',seed,C]);assert not C.samefile(seed)
  compile(arm,src)
  orig=D/('raw-cargo-'+arm);(D/('cargo-'+arm)).rename(orig)
  saved=D/(arm+'-result.json');saved.rename(D/(arm+'-raw-result.json'))
  out=D/('cargo-'+arm);verified=pkg.strip(orig,out);put(saved,verified)
  print('PACKAGED',arm,sha(orig),sha(out),flush=True)
  assert C==Path('/dev/shm/ohm-current-cargo-release-cache-v1') and saved.is_file();shutil.rmtree(C)
 assert seed_hash()==attestation, 'immutable seed changed'
 assert sha(D/'cargo-parent')==sha(D/'cargo-parent-repeat'),('baseline not reproducible',sha(D/'cargo-parent'),sha(D/'cargo-parent-repeat'))
 put(D/'pair.json',{'parent':sha(D/'cargo-parent'),'parent-repeat':sha(D/'cargo-parent-repeat'),'candidate':sha(D/'cargo-candidate'),'raw':{n:sha(D/('raw-cargo-'+n)) for n in ('parent','candidate','parent-repeat')},'builder':sha(D/'builder.json'),'source':sha(D/'source-sha.json'),'packager_verify':sha(BASE/'package-v2.py'),'seed_tree':attestation[1],'pgo':ref['pgo'],'raw_source_tree':ref['source_git_tree'],'patch_sha256':ref['patch_sha256']})
 assert attestation[1]=='60a997f43d29e44fb0811848dae4edc8d4d7ac60d3caf03b85dec752e998541a'
 print('ALL PACKAGING GATES PASSED',flush=True)
if __name__=='__main__':
 try:
  with (P/'native-measure.lock').open('rb') as lk:fcntl.flock(lk,fcntl.LOCK_EX);make()
 except BaseException:(BASE/'failure-v5.txt').write_text(traceback.format_exc());raise
