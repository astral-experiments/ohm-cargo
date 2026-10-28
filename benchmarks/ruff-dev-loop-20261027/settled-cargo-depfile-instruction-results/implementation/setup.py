"""Native observation of a fully settled private linter edit on published Ohm."""
import fcntl,hashlib,json,os,shutil,subprocess,sys,tomllib
from pathlib import Path
H=Path('/home/dev-user/.cache/ohm-settled-cargo-20261028')
P=Path('/mnt/devbox-scratch/dev-user/ohm-early-completion-20261027')
BASE=Path('/home/dev-user/code/oss/ruff-early-completion-20261027')
SRC=Path('/home/dev-user/code/oss/ruff-ohm-settled-cargo-20261028')
SDK=H/'release17/sdk';CARGO=Path('/home/dev-user/.cargo/bin/cargo')
PIN='93526150df078af7dd8fc4226cdcc469539d2001';GIT='git'
def sha(p):return hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
def emit(f,data):Path(f).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
def pre(s):return subprocess.check_output(s,text=True).strip()
def env():
    e=os.environ.copy()
    for k in list(e):
        if k.startswith(('CARGO_','RUSTC','RUSTDOC','RUSTFLAGS','RUSTUP_','OHM_','LD_PRELOAD')):del e[k]
    e.update(CARGO_HOME=str(H/'cargo-home'),CARGO_TARGET_DIR=str(H/'target'),CARGO_BUILD_BUILD_DIR=str(H/'shared'),RUSTUP_HOME=str(H/'rustup'),GIT_OPTIONAL_LOCKS='0',PATH='/home/dev-user/.cargo/bin:/usr/local/bin:/usr/bin:/bin',CARGO_TERM_COLOR='never')
    return e
def run(name,args,cwd,extra=None):
    out=H/'native'/name;out.mkdir(parents=True)
    with (out/'stdout').open('wb') as so,(out/'stderr').open('wb') as se:
        r=subprocess.run(args,cwd=cwd,env=dict(env(),**(extra or {})),stdout=so,stderr=se)
    emit(out/'call.json',{'args':list(map(str,args)),'rc':r.returncode,'stderr_sha256':sha(out/'stderr'),'stdout_sha256':sha(out/'stdout')})
    if r.returncode:raise RuntimeError((name,r.returncode,(out/'stderr').read_bytes()[-2500:]))
    return out
def registry():
    c=H/'cargo-home';c.mkdir(mode=0o700,exist_ok=True);seed=P/'release-pair-v1/crate-seed/registry';public='index.crates.io-1949cf8c6b5b557f'
    for kind in ['index','cache']:
        for known in (seed/kind).iterdir():
            if known.is_dir() and not (c/'registry'/kind/known.name).is_dir():shutil.copytree(known,c/'registry'/kind/known.name)
    publiccache=c/'registry/cache'/public
    rows=[]
    for pkg in tomllib.loads((BASE/'Cargo.lock').read_text())['package']:
        if 'checksum' not in pkg:continue
        n=f"{pkg['name']}-{pkg['version']}.crate";p=publiccache/n
        if not p.is_file():shutil.copy2(P/'inputs/crates'/n,p)
        assert sha(p)==pkg['checksum'],n;rows.append([n,pkg['checksum']])
        for repo in (c/'registry/cache').iterdir():
            if not (repo/n).is_file():shutil.copy2(p,repo/n)
            assert sha(repo/n)==pkg['checksum'],n
    emit(H/'registry-lock.json',rows)
def main():
    os.umask(0o077);os.sched_setaffinity(0,range(8)); assert shutil.disk_usage(H).free>100*2**30 and shutil.disk_usage(P).free>60*2**30
    assert pre(['git','-C',BASE,'rev-parse','HEAD'])==PIN
    assert pre(['git','-C',BASE,'rev-parse','HEAD^{tree}'])=='62d3f106c5e41f6022847f26ff8c7dc00139f7b1'
    # The offline donor was imported without remotes; bind the complete public Git tree instead.
    assert not pre(['git','-C',BASE,'remote'])
    # This benchmark host lacks the coordinator's conditional Git identity. Scope it to these OSS subprocesses.
    os.environ.update(GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='user.email',GIT_CONFIG_VALUE_0='charlie.r.marsh@gmail.com')
    assert pre(['git','-C',BASE,'config','user.email'])=='charlie.r.marsh@gmail.com'
    common=pre(['git','-C',BASE,'rev-parse','--path-format=absolute','--git-common-dir'])
    assert common.startswith('/home/dev-user/code/oss/')
    (H/'rustup/toolchains').mkdir(parents=True,exist_ok=True)
    tool=H/'rustup/toolchains/ohm'
    if not tool.exists():tool.symlink_to(SDK,target_is_directory=True)
    assert tool.resolve()==SDK
    if (P/'rustup/settings.toml').is_file():shutil.copyfile(P/'rustup/settings.toml',H/'rustup/settings.toml')
    (H/'shared').mkdir(mode=0o700,exist_ok=True)
    if not SRC.exists():assert not (H/'target').exists()
    registry()
    binding={'archive':sha(H/'release17/package.tar.gz'),'tools':{n:sha(p) for n,p in [('cargo',SDK/'bin/cargo'),('rustc',SDK/'bin/rustc'),('driver',next((SDK/'lib').glob('librustc_driver-*.so')))]},'cargo_vv':pre([SDK/'bin/cargo','-Vv']),'rustc_vv':pre([SDK/'bin/rustc','-Vv']),'ruff':PIN,'git_common':common,'patch':sha(H/'private.patch')}
    emit(H/'inputs.json',binding)
    if not SRC.exists():run('worktree',[CARGO,'+ohm','worktree','add','-b','charlie/ohm-settled-cargo-20261028',SRC,PIN,'--target-dir',H/'target'],BASE,{'CARGO_TARGET_DIR':str(H/'unseeded-bootstrap-target')})
    assert pre(['git','-C',SRC,'rev-parse','--path-format=absolute','--git-common-dir'])==common
    assert pre(['git','-C',SRC,'branch','--show-current'])=='charlie/ohm-settled-cargo-20261028'
    assert pre(['git','-C',SRC,'rev-parse','HEAD'])==PIN and not pre(['git','-C',SRC,'status','--porcelain'])
    common_cmd=[CARGO,'+ohm','build','--lib','--locked','--offline','-j4'];cwd=SRC/'crates/ruff_linter'
    run('original-build',common_cmd,cwd)
    subprocess.run(['git','-C',SRC,'apply','--reverse',H/'private.patch'],check=True)
    changed=pre(['git','-C',SRC,'diff','--name-only']);assert changed=='crates/ruff_linter/src/rules/ruff/helpers.rs',changed
    run('edited-build',common_cmd,cwd)
    run('edited-repeat',common_cmd,cwd)
    d=run('edited-processes',['strace','-ff','-qq','-s','768','-e','trace=execve','-o',H/'physical-job',*common_cmd],cwd)
    probe=run('edited-fresh-json',[*common_cmd,'--message-format=json'],cwd)
    records=[json.loads(v) for v in (probe/'stdout').read_text().splitlines()];units=[r for r in records if r.get('reason')=='compiler-artifact'];assert len(units)>160 and all(r['fresh'] for r in units),(len(units),[r['target']['name'] for r in units if not r['fresh']])
    files=[p for p in (H/'cargo-home').iterdir() if p.name.startswith('.ohm') and p.is_dir()]
    sizes={p.name:len(list(p.glob('*'))) for p in files}
    trace={p.name:len([a for a in p.read_text().splitlines() if a.startswith('execve(') and '= 0' in a]) for p in H.glob('physical-job.*')}
    emit(H/'settled.json',{'units':len(units),'fresh':sum(x['fresh'] for x in units),'cache_sizes':sizes,'success_per_actor':trace,'full_elf':{str(p.relative_to(H/'target')):sha(p) for p in (H/'target/debug').glob('libruff_linter.*') if p.suffix in ('.rlib','.rmeta')},'changes':changed,'post_edited_diff':pre(['git','-C',SRC,'diff','--numstat'])})
if __name__=='__main__':
    with (P/'member-build-native.lock').open('a') as l:
        fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB);main()
