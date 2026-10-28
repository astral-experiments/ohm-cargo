"""Prepare private ordinary Cargo states for actual historical Ruff source edits."""
from pathlib import Path
import hashlib,json,fcntl,os,shutil,stat,subprocess,sys,tomllib
which=sys.argv[1];assert which in ('h7','h8')
H=Path('/home/dev-user/.cache/ohm-output-path-ruff-20261028')
D=Path('/home/dev-user/.cache/ohm-settled-cargo-20261028') if which=='h7' else None
P=Path('/mnt/devbox-scratch/dev-user')
LOCK=P/('ohm-early-completion-20261027/member-build-native.lock' if which=='h7' else 'ohm-spaced-ruff-20261027/matched-qualify.lock')
R=Path('/home/dev-user/code/oss/ruff-output-paths-20261028');B=R.parent/('ruff-early-completion-20261027' if which=='h7' else 'ruff-spaced-input-donor-20261027')
PIN='93526150df078af7dd8fc4226cdcc469539d2001'
S=(D/'release17/sdk') if D else H/'release17/sdk'
CARGO=Path('/home/dev-user/.cargo/bin/cargo');RT=H/'runtime'
def sha(p):return hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
def save(p,value):p.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
def git(repo,*args):return subprocess.check_output(['git','-C',repo,*args],text=True).strip()
def env(mode):
 assert mode in ('library','workspace','test')
 e=os.environ.copy()
 for k in list(e):
  if k.startswith(('CARGO_','RUSTC','RUSTDOC','RUSTFLAGS','RUSTUP_','OHM_','LD_PRELOAD')):del e[k]
 e.update(CARGO_HOME=str(H/'cargo-home'),CARGO_TARGET_DIR=str(H/mode/'target'),CARGO_BUILD_BUILD_DIR=str(H/mode/'shared'),RUSTUP_HOME=str(H/'rustup'),GIT_OPTIONAL_LOCKS='0',PATH='/home/dev-user/.cargo/bin:/usr/local/bin:/usr/bin:/bin',CARGO_TERM_COLOR='never',GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='user.email',GIT_CONFIG_VALUE_0='charlie.r.marsh@gmail.com')
 return e
def cmds(mode):return [CARGO,'+ohm',*({'library':['build','--lib'],'workspace':['build'],'test':['test','--no-run']}[mode]),'--locked','--offline','-j4']
def cwd(mode):return R/'crates/ruff_linter' if mode=='library' else R
def run(name,mode,extra=(),trace=False):
 out=H/'qual'/mode/name;out.mkdir(parents=True)
 cmd=cmds(mode)+list(extra)
 if trace:cmd=['strace','-ff','-qq','-s','16384','-e','trace=execve','-o',out/'exec',*cmd]
 with (out/'stdout').open('wb') as so,(out/'stderr').open('wb') as se:
  c=subprocess.run(cmd,cwd=cwd(mode),env=env(mode),stdout=so,stderr=se)
 save(out/'status.json',dict(rc=c.returncode,argv=list(map(str,cmd)),stdout=sha(out/'stdout'),stderr=sha(out/'stderr')))
 assert c.returncode==0,(name,(out/'stderr').read_bytes()[-1100:])
 return out
def install():
 if not S.exists():
  assert not D and sha(H/'release17/package.tar.gz')=='163267d26889b1bd2c467d7db97efee42cd2ac9dc9af2abc3a56ade8da9a9572'
  unpack=H/'release17/unpack';unpack.mkdir()
  subprocess.run(['tar','-xzf',H/'release17/package.tar.gz','-C',unpack],check=True)
  installer,=unpack.glob('*/install.sh')
  with (H/'install.log').open('wb') as f:subprocess.run(['sh',installer,'--prefix='+str(S),'--disable-ldconfig'],stdout=f,stderr=subprocess.STDOUT,check=True)
 assert sha(S/'bin/cargo')=='4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3'
 assert sha(S/'bin/rustc')=='7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c'
 assert sha(S/'lib/librustc_driver-b03bf00bec23bb9a.so')=='618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7'
 (RT/'bin').mkdir(parents=True)
 for p in S.iterdir():
  if p.name!='bin':(RT/p.name).symlink_to(p)
 for p in (S/'bin').iterdir():
  if p.name=='cargo':shutil.copy2(p,RT/'bin/cargo')
  else:(RT/'bin'/p.name).symlink_to(p)
 (H/'rustup/toolchains').mkdir(parents=True);(H/'rustup/toolchains/ohm').symlink_to(RT)
 prior=(D/'cargo-home/registry') if D else None
 if prior:
  (H/'cargo-home/registry').mkdir(parents=True)
  for part in ('cache','index'):shutil.copytree(prior/part,H/'cargo-home/registry'/part)
 scope='library' if D else 'workspace'
 for mode in (['library'] if D else ['workspace','test']):
  (H/mode/'shared').mkdir(parents=True)
 assert git(B,'rev-parse','HEAD')==PIN and git(B,'rev-parse','HEAD^{tree}')=='62d3f106c5e41f6022847f26ff8c7dc00139f7b1'
 common=git(B,'rev-parse','--path-format=absolute','--git-common-dir');assert str(B.parent) in common
 e=env(scope);e['CARGO_TARGET_DIR']=str(H/'bootstrap-empty-target')
 assert subprocess.check_output(['git','-C',B,'config','user.email'],env=e,text=True).strip()=='charlie.r.marsh@gmail.com'
 assert not R.exists() and not (H/scope/'target').exists()
 subprocess.run([CARGO,'+ohm','worktree','add','-b','charlie/ohm-output-paths-20261028',R,PIN,'--target-dir',H/scope/'target'],cwd=B,env=e,check=True)
 assert git(R,'rev-parse','--path-format=absolute','--git-common-dir')==common and git(R,'status','--porcelain')==''
 for c in tomllib.loads((R/'Cargo.lock').read_text())['package']:
  if 'checksum' not in c:continue
  n=c['name']+'-'+c['version']+'.crate';cs=list((H/'cargo-home/registry/cache').glob('*/'+n));assert cs and all(sha(x)==c['checksum'] for x in cs),n
 if not D:
  src=H/'rustc-sources';src.mkdir()
 save(H/'source-state.json',dict(base=PIN,tree=git(R,'rev-parse','HEAD^{tree}'),patch=sha(H/('private.patch' if D else 'ty-private.patch')),cargo=sha(S/'bin/cargo'),compiler=sha(S/'bin/rustc'),driver=sha(S/'lib/librustc_driver-b03bf00bec23bb9a.so'),runtime_path=str(RT),worktree=str(R),git_common=common))
def main():
 os.umask(0o077);os.sched_setaffinity(0,range(8));assert shutil.disk_usage(H).free>105*2**30 and shutil.disk_usage(P).free>(60 if D else 25)*2**30
 with LOCK.open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  install()
  modes=['library'] if D else ['workspace','test']
  for mode in modes:run('original',mode)
  patch=H/('private.patch' if D else 'ty-private.patch');subprocess.run(['git','-C',R,'apply','--reverse',patch],check=True)
  assert git(R,'diff','--name-only')==('crates/ruff_linter/src/rules/ruff/helpers.rs' if D else 'crates/ty_python_semantic/src/types/relation.rs')
  for mode in modes:
   run('historical-edit',mode);run('warm',mode)
   o=run('warm-json',mode,['--message-format=json'],trace=True)
   artifacts=[d for l in (o/'stdout').read_text().splitlines() if (d:=json.loads(l)).get('reason')=='compiler-artifact']
   assert artifacts and all(d['fresh'] for d in artifacts)
   physical=[l.split('execve("',1)[1].split('"',1)[0] for p in o.glob('exec.*') for l in p.read_text().splitlines() if 'execve("' in l and l.endswith('= 0')]
   assert len(physical)==2 and all(Path(p).name=='cargo' for p in physical),(mode,physical)
   save(H/'qual'/mode/'warm.json',dict(units=len(artifacts),physical=physical,dot_d=sum(1 for p in (H/mode/'target/debug').glob('*.d')),git=git(R,'diff','--numstat')))
  save(H/'ready.json',dict(modes=modes,source=sha(H/'source-state.json')))
if __name__=='__main__':main()
