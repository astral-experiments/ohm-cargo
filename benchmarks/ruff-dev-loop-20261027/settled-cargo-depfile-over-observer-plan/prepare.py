"""Create a separate real Ruff linter state and poisoned shipping baselines for the #261 composition."""
import fcntl,hashlib,importlib.util,json,os,shutil,subprocess,sys,tomllib
from pathlib import Path
H=Path(__file__).resolve().parent;old=Path('/home/dev-user/.cache/ohm-output-path-ruff-20261028');F=Path('/home/dev-user/.cache/ohm-settled-cargo-20261028');sdk=H/'runtime';rustup=H/'rustup';home=H/'cargo-home';R=Path('/home/dev-user/code/oss/ruff-output-paths-over261-20261028');base=Path('/home/dev-user/code/oss/ruff-early-completion-20261027');lock=Path('/mnt/devbox-scratch/dev-user/ohm-early-completion-20261027/member-build-native.lock');C=Path('/home/dev-user/.cargo/bin/cargo');PIN='93526150df078af7dd8fc4226cdcc469539d2001'
def sha(p):return hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
def store(p,x):p.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
def git(root,*args):return subprocess.check_output(['git','-C',root,*args],text=True).strip()
def env():
 e={k:v for k,v in os.environ.items() if not k.startswith(('CARGO_','RUSTC','RUSTDOC','RUSTFLAGS','RUSTUP_','OHM_','LD_PRELOAD'))};e.update(CARGO_HOME=str(home),CARGO_TARGET_DIR=str(H/'library/target'),CARGO_BUILD_BUILD_DIR=str(H/'library/shared'),RUSTUP_HOME=str(rustup),GIT_OPTIONAL_LOCKS='0',PATH='/home/dev-user/.cargo/bin:/usr/local/bin:/usr/bin:/bin',CARGO_TERM_COLOR='never',GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='user.email',GIT_CONFIG_VALUE_0='charlie.r.marsh@gmail.com');return e

def main():
 os.umask(0o077);os.sched_setaffinity(0,range(8));assert shutil.disk_usage(H).free>95*2**30 and shutil.disk_usage(lock.parent).free>60*2**30;assert sha(H/'private.patch')=='3f1869c672cf721af6ff04f0b84fe437212f0c7718bf96473caaf61d51bec1d1';stock=F/'release17/sdk';d=stock/'lib/librustc_driver-b03bf00bec23bb9a.so';assert sha(stock/'bin/cargo')=='4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3' and sha(stock/'bin/rustc')=='7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c' and sha(d)=='618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7'
 subprocess.run(['cp','-a','--reflink=auto',stock,sdk],check=True);assert sha(sdk/'bin/cargo')==sha(stock/'bin/cargo') and (sdk/'bin/cargo').stat().st_ino!=(stock/'bin/cargo').stat().st_ino;assert sha(sdk/'lib'/d.name)==sha(d);(rustup/'toolchains').mkdir(parents=True);(rustup/'toolchains/ohm').symlink_to(sdk);home.mkdir();(home/'registry').mkdir();
 for k in ('index','cache'):shutil.copytree(old/'cargo-home/registry'/k,home/'registry'/k,symlinks=True)
 (H/'library/shared').mkdir(parents=True);assert not R.exists() and git(base,'rev-parse','HEAD')==PIN;common=git(base,'rev-parse','--path-format=absolute','--git-common-dir');e=env();e['CARGO_TARGET_DIR']=str(H/'empty-worktree-donor');assert subprocess.check_output(['git','-C',base,'config','user.email'],text=True,env=e).strip()=='charlie.r.marsh@gmail.com';subprocess.run([C,'+ohm','worktree','add','-b','charlie/output-paths-composition-ruff-20261028',R,PIN,'--target-dir',H/'library/target'],cwd=base,env=e,check=True);assert git(R,'rev-parse','--path-format=absolute','--git-common-dir')==common and not git(R,'status','--short');cargo=[C,'+ohm','build','--lib','--locked','--offline','-j4'];testcase=R/'crates/ruff_linter';receipts={}
 for phase in ('original','historical-edit','settled'):
  if phase=='historical-edit':subprocess.run(['git','-C',R,'apply','--reverse',H/'private.patch'],check=True)
  p=H/('warm-'+phase);p.mkdir();cmd=cargo+['--message-format=json']
  with (p/'stdout').open('wb') as so,(p/'stderr').open('wb') as se:r=subprocess.run(cmd,cwd=testcase,env=env(),stdout=so,stderr=se)
  assert r.returncode==0,(p,(p/'stderr').read_text()[-750:]);rows=[v for x in (p/'stdout').read_bytes().splitlines() if (v:=json.loads(x)).get('reason')=='compiler-artifact'];assert len(rows)==268;dirty=[x['target']['name'] for x in rows if not x['fresh']];receipts[phase]=dict(units=len(rows),dirty=dirty,stdout=sha(p/'stdout'),stderr=sha(p/'stderr'));store(p/'record.json',receipts[phase]);print(phase,len(rows),len(dirty),flush=True)
 assert 'ruff_linter' in receipts['historical-edit']['dirty'] and not receipts['settled']['dirty'];assert git(R,'diff','--name-only')=='crates/ruff_linter/src/rules/ruff/helpers.rs';store(H/'ready.json',dict(source=PIN,source_sha=sha(R/'crates/ruff_linter/src/rules/ruff/helpers.rs'),patch=sha(H/'private.patch'),git_common=common,stock=sha(stock/'bin/cargo'),frontend=sha(sdk/'bin/rustc'),driver=sha(sdk/'lib'/d.name),receipts=receipts))
 # Create a real previously complete OBS1 in three actual native cases, at the precise target/source paths used later.
 spec=importlib.util.spec_from_file_location('adverse',H/'migration-fixture/exercise.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);gate=H/'adversarial';gate.mkdir();data={}
 for k in ('tracked-file','include-str','include-bytes'):
  active=gate/(k+'-active');rows=module.case(active,sdk,k,True,'preserved');assert rows['again'][:3]==[17,True,True] and rows['clean'][0]==29;data[k]=rows;active.rename(gate/(k+'-stock'));store(gate/'stock.json',data);print('genuine complete',k,rows['again'],flush=True)
 store(H/'native-ready.json',dict(stock=sha(sdk/'bin/cargo'),case_sha=sha(H/'migration-fixture/exercise.py'),baseline=sha(gate/'stock.json')))
if __name__=='__main__':
 with lock.open('a') as f:fcntl.flock(f,fcntl.LOCK_EX);main()
