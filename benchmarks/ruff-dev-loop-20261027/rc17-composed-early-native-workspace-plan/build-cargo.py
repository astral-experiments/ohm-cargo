"""Build the two private Ohm Cargo drafts together and repeat the control at the same path."""
from pathlib import Path
import fcntl, hashlib, json, os, shutil, socket, subprocess, time, traceback

here=Path(__file__).resolve().parent
scratch=here.parent
shipped=scratch/'ohm-observer-shipping-20261027'
prior=scratch/'ohm-producer-attestation-rc17-20261028'
control=scratch/'ohm-observer-consumption-cargo-v2-20261028'
source_state=scratch/'ohm-observer-consumption-cargo-20261028/state'
state=here/'state'
outer=shipped/'states/raw-rc17'
canonical=shipped/'src-rc17'

def read(f):
    return json.loads(f.read_bytes())
def save(f,obj):
    f.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')
def sha(f):
    with f.open('rb') as h:
        return hashlib.file_digest(h,'sha256').hexdigest()
def inputs(src,identity,spec,arm):
    src.mkdir()
    subprocess.run(['tar','xf',prior/'inputs/base-source.tar','-C',src],check=True)
    for name,mode,oid in identity['files']:
        f=src/name
        data=os.fsencode(os.readlink(f)) if mode=='120000' else f.read_bytes()
        assert hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()==oid and (mode=='120000' or bool(f.stat().st_mode&0o100)==(mode=='100755')),name
    for step in ('base','observer',*(['composed'] if arm=='composed' else [])):
        if step!='base':
            patch=here/('observer.patch' if step=='observer' else 'guard.patch')
            subprocess.run(['git','apply','--check',patch],cwd=src,check=True)
            subprocess.run(['git','apply',patch],cwd=src,check=True)
        assert {name:sha(src/name) for name in spec['files'][step]}==spec['files'][step]
    shutil.copy2(shipped/'assets/git-commit-info-rc17',src/'git-commit-info')
    # All touched times change relative to the preceding arm, while every source byte is verified.
    for name in spec['files'][arm]:
        os.utime(src/name,None)
def build(arm,ref,old,spec,identity):
    d=here/arm;d.mkdir();src=d/'src'
    inputs(src,identity,spec,arm)
    prefix=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(src),str(canonical)]
    for name in ('target','shared','cargo-home'):
        prefix+=['--bind',str(state/name),str(outer/name)]
    prefix+=['--chdir',str(canonical),'--','taskset','-c','8-23','/home/dev-user/.cargo/bin/cargo','+ohm']
    env=dict(os.environ,PATH='/home/dev-user/.cargo/bin:'+os.environ['PATH'],RUSTUP_HOME=str(outer/'rustup'),CARGO_HOME=str(outer/'cargo-home'),CARGO_TARGET_DIR=str(outer/'target'),CARGO_BUILD_BUILD_DIR=str(outer/'shared'),CARGO_NET_OFFLINE='true',CARGO_PROFILE_RELEASE_INCREMENTAL='false',CFG_RELEASE_CHANNEL='dev',RUSTFLAGS='-Cprofile-use='+str(shipped/'assets/rustc-pgo.profdata')+' -Cllvm-args=-pgo-warn-missing-function=false')
    for key in ('RUSTC_WORKSPACE_WRAPPER','RUSTC_WRAPPER','CARGO_ENCODED_RUSTFLAGS','CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST','CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST'):
        env.pop(key,None)
    cmd=prefix+['build','--release','--locked','--offline','-p','cargo','--bin','cargo','--features','ohm-defaults','-j12'];trace=d/'compiler.exec'
    with (d/'build.log').open('xb') as log:
        subprocess.run(['strace','-f','-qq','-s','65535','-e','trace=execve,execveat','-o',trace,*cmd],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    lines=trace.read_text().splitlines();full={}
    for name in ('src/lib.rs','src/bin/cargo/main.rs'):
        rows=[l for l in lines if '"--crate-name", "cargo"' in l and '"'+name+'"' in l and 'profile-use=' in l and '"link-only"' not in l and '= -1 ' not in l]
        assert len(rows)==1,(arm,name,len(rows))
        full[name]=hashlib.sha256(rows[0].encode()).hexdigest()
    binary=d/'cargo';shutil.copy2(state/'target/release/cargo',binary)
    v=subprocess.check_output([binary,'-Vv'],text=True);assert v==ref['version']==old['version']
    res=dict(arm=arm,base=spec['base'],source_leaves=len(identity['files']),changed=spec['files'][arm],patches=spec['patches'],cargo=sha(binary),version=v,full=full,trace=sha(trace),builder=ref['builder'],pgo=ref['pgo'],stamp=ref['stamp'])
    save(d/'receipt.json',res);return res
def main():
    assert socket.gethostname()=='charlie-ohm-cargo5-build-1025' and not state.exists()
    lock=(scratch/'ohm-spaced-ruff-20261027/matched-qualify.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    spec=read(here/'combined-build-inputs.json');identity=read(prior/'inputs/A.json')
    ref=read(prior/'A/receipt.json');old=read(control/'receipt.json')
    assert spec['base']==identity['commit']==old['base']=='a0c7d08c898d3fdff992f2f431dec57d2486add2'
    assert spec['observer']=='9a0170863f70d9a88a8b1d1f4c4e1fded4736a9c' and spec['guard']=='5bc102b855aeca105a6d4f077047bd7be3fef08d'
    assert {name:sha(here/(name+'.patch')) for name in ('observer','guard')}==spec['patches']
    assert old['cargo']==sha(control/'cargo')=='0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322' and sha(shipped/'assets/rustc-pgo.profdata')==ref['pgo']==old['pgo'] and sha(shipped/'assets/git-commit-info-rc17')==ref['stamp'] and old['compiler']==ref['builder']
    size=int(subprocess.check_output(['du','-s','-B1',source_state]).split()[0])
    assert shutil.disk_usage(here).free>size+40*2**30
    subprocess.run(['cp','-a','--reflink=auto',source_state,state],check=True)
    assert not (source_state/'target/release/cargo').samefile(state/'target/release/cargo')
    b=build('composed',ref,old,spec,identity);assert b['cargo']!=old['cargo']
    a=build('observer',ref,old,spec,identity)
    assert a['cargo']==old['cargo'],('replayed #261 differs',a['cargo'],old['cargo'])
    save(here/'matched.json',dict(observer=a['cargo'],composed=b['cargo'],exact_control=True,pgo=ref['pgo'],stamp=ref['stamp'],same_builder=ref['builder']))
try:
    main()
except BaseException:
    (here/'failure.txt').write_text(traceback.format_exc())
    raise
