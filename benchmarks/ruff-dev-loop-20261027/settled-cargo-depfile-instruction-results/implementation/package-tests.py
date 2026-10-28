import fcntl,hashlib,json,os,shutil,subprocess,tomllib
from pathlib import Path
H=Path('/home/dev-user/.cache/ohm-output-path-cargo-tests-20261028');F=Path('/home/dev-user/.cache/ohm-settled-cargo-20261028');P=Path('/mnt/devbox-scratch/dev-user/ohm-early-completion-20261027');C=Path('/home/dev-user/.cargo/bin/cargo')
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def save(p,x):p.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
with (P/'member-build-native.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);os.sched_setaffinity(0,range(12));assert shutil.disk_usage(H).free>110*2**30
 assert sha(H/'product.patch')=='78eddb19af579fafb87254823e15ae0dcbec1b17bb0ce449e73cf5cae49a6238'
 subprocess.run(['git','apply','--check',H/'product.patch'],cwd=H/'src',check=True)
 subprocess.run(['git','apply',H/'product.patch'],cwd=H/'src',check=True)
 frozen=json.loads((H/'source.json').read_bytes());assert all(sha(H/'src'/n)==v for n,v in frozen['source_sha256'].items())
 registry=H/'cargo-home/registry';seed=next((registry/'cache').iterdir());idx=next((registry/'index').iterdir());public='index.crates.io-1949cf8c6b5b557f'
 if not (registry/'cache'/public).exists():shutil.copytree(seed,registry/'cache'/public)
 if not (registry/'index'/public).exists():shutil.copytree(idx,registry/'index'/public)
 missing=[];verified=0
 for q in tomllib.loads((H/'src/Cargo.lock').read_text())['package']:
  if 'checksum' not in q:continue
  n=q['name']+'-'+q['version']+'.crate';paths=[p for base in [registry,F/'cargo-home/registry'] for p in (base/'cache').glob('*/'+n)]
  if not paths:missing.append(n);continue
  assert all(sha(p)==q['checksum'] for p in paths),n
  for d in (registry/'cache').iterdir():
   if not (d/n).exists():shutil.copy2(paths[0],d/n)
  verified+=1
 save(H/'dependencies.json',dict(verified=verified,missing=missing))
 if missing:print('missing inactive target archives',len(missing),missing[:8],flush=True)
 e=os.environ.copy()
 for k in list(e):
  if k.startswith(('CARGO_','RUSTUP_','RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','OHM_','LD_PRELOAD')):del e[k]
 e.update(CARGO_HOME=str(H/'cargo-home'),CARGO_TARGET_DIR=str(H/'target'),CARGO_BUILD_BUILD_DIR=str(H/'shared'),RUSTUP_HOME=str(F/'rustup'),PATH='/home/dev-user/.cargo/bin:/usr/local/bin:/usr/bin:/bin',CARGO_PROFILE_DEV_DEBUG='0',CARGO_PROFILE_TEST_DEBUG='0',CARGO_PROFILE_DEV_INCREMENTAL='false',CARGO_PROFILE_TEST_INCREMENTAL='false',CARGO_NET_OFFLINE='true',CFG_RELEASE_CHANNEL='dev')
 runs=[('encoded',['--lib','encoded_dep_info']),('path-integration',['--test','testsuite','dep_info::']),('generated',['--test','testsuite','build_script::generate_good_d_files'])]
 rec={}
 for name,args in runs:
  f=H/(name+'.log')
  with f.open('wb') as log:
   r=subprocess.run([C,'+ohm','test','--locked','--offline','-p','cargo','--features','ohm-defaults','-j8',*args],cwd=H/'src',env=e,stdout=log,stderr=subprocess.STDOUT)
  txt=f.read_text(errors='replace');result=[row for row in txt.splitlines() if row.startswith('test result:')];rec[name]=dict(rc=r.returncode,result=result,log=sha(f));save(H/'results.json',rec);print(name,rec[name],flush=True)
  if r.returncode and not result:raise RuntimeError(txt[-2200:])
