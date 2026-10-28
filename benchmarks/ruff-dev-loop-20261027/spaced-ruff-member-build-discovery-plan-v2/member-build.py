"""Measure native process counts for plain Cargo builds from two real Ruff member directories."""
from pathlib import Path
import collections
import fcntl
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import traceback
import zipfile

here=Path(__file__).resolve().parent
p=Path('/mnt/devbox-scratch/dev-user/ohm-early-completion-20261027')
o=p/'member-build-spaces-native-v2'
logical=p/'member-build-canonical-v2'
sys.path.insert(0,str(p/'early-completion-wall-protocol-v2'))
sys.path.insert(0,str(here))
import importlib.util
spec=importlib.util.spec_from_file_location('stock',p/'early-completion-wall-protocol-v2/test-ruff.py')
q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)
import capture
from stub_bytes import read_stub

def state(pkg,layout):
    sample=o/(pkg+'-'+layout);sample.mkdir()
    own=sample/'state';q.state(own)
    target=logical/('ruff target' if layout=='spaced' else 'ruff-target')
    mounts=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp']
    for key in ('target','shared','cargo','home'):
        mounts+=['--bind',str(own/key),str(target if key=='target' else logical/key)]
    env=q.opts(own,q.sdk/'bin/cargo')[1]
    env.update(HOME=str(logical/'home'),CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(logical/'shared'),CARGO_HOME=str(logical/'cargo'),CARGO_BUILD_JOBS='4')
    member=q.src/'crates'/pkg
    def command(argv,dot):
        return subprocess.run([*mounts,'--bind',str(dot),str(dot),'--chdir',member,'--',*argv],env=env,capture_output=True,stdin=subprocess.DEVNULL)
    before=command(['rustc','+ohm','--print=sysroot'],sample)
    assert before.returncode==0 and Path(before.stdout.decode().strip()).resolve()==q.sdk.resolve()
    history=[];stable_roster=None
    for call in range(4):
        assert shutil.disk_usage(p).free>40*2**30
        dot=sample/('call-'+str(call));dot.mkdir();(dot/'trace').mkdir()
        cargo=['cargo','+ohm','build','--locked','--offline','-j4','--message-format=json']
        run=command(['strace','-f','-ff','-qq','-s','1048576','-e','trace=execve,execveat','-o',str(dot/'trace/exec'),*cargo],dot)
        (dot/'stdout').write_bytes(run.stdout);(dot/'stderr').write_bytes(run.stderr)
        q.put(dot/'command.json',dict(cmd=cargo,status=run.returncode,manifest=str(member/'Cargo.toml'),target=str(target),actual_sdk=str(q.sdk),
              stdout=q.sha(dot/'stdout'),stderr=q.sha(dot/'stderr')))
        assert run.returncode==0,(pkg,layout,call,run.stderr[-400:])
        stream=[json.loads(line) for line in run.stdout.splitlines()]
        assert stream[-1]=={'reason':'build-finished','success':True}
        units=[u for u in stream if u['reason']=='compiler-artifact']
        assert all(not u['profile']['test'] for u in units) and any(u['target']['name']=='ty_vendored' for u in units)
        roster=sorted(json.dumps({k:u[k] for k in ('package_id','manifest_path','target','profile','features','filenames','executable')},sort_keys=True) for u in units)
        if stable_roster is None:stable_roster=roster
        assert stable_roster==roster
        physical=capture.cmds(dot/'trace');q.put(dot/'physical.json',physical)
        products={}
        for u in units:
            if u['target']['name'] not in (pkg,'ty_vendored') or u['target']['kind']==['custom-build']:continue
            for f in map(Path,u['filenames']):
                assert f.is_relative_to(target)
                rel=f.relative_to(target);products[str(rel)]=q.sha(own/'target'/rel)
        assert products and (pkg!='ty_wasm' or any(f.endswith('.so') for f in products))
        zips={}
        for root in (own/'target',own/'shared'):
            for f in root.rglob('zipped_typeshed.zip'):
                z=zipfile.ZipFile(f);entries=z.namelist();assert 'stdlib/functools.pyi' in entries
                ref=(q.src/'crates/ty_vendored/vendor/typeshed/stdlib/functools.pyi').read_bytes()
                assert read_stub(z,'stdlib/functools.pyi')==ref
                zips[str(f.relative_to(own))]={'entries':len(entries),'zip':q.sha(f),'real_stub':hashlib.sha256(ref).hexdigest()}
        assert zips
        dirty=[u['target']['name'] for u in units if not u['fresh']]
        jobs=[(v['crate'],v['kind']) for v in physical['jobs']]
        row=dict(call=call,units=len(units),dirty=dirty,jobs=jobs,wild=len(physical['wild']),products=products,zips=zips,
                 paths=capture.digest('\n'.join(roster).encode()),diagnostics=sorted(json.dumps(u,sort_keys=True) for u in stream if u['reason']=='compiler-message'))
        q.put(dot/'product.json',row);history.append(row);q.put(sample/'progress.json',history)
        print(pkg,layout,call,len(units),len(dirty),len(jobs),row['wild'],flush=True)
    return history

def main():
    assert socket.gethostname()=='charlie-ohm-pkg-build-1024'
    assert (p/'early-completion-wall-protocol-v2/outer.exit').read_text()=='0' and not o.exists() and not logical.exists()
    assert shutil.disk_usage(p).free>95*2**30
    assert q.sha(q.sdk/'bin/cargo')=='42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568'
    os.sched_setaffinity(0,set(range(8)))
    with (p/'member-build-native.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);q.source_gate()
        o.mkdir(mode=0o700);logical.mkdir(mode=0o700)
        for n in ('ruff target','ruff-target','shared','cargo','home'):(logical/n).mkdir(mode=0o700)
        observed={}
        for pkg,layout in [('ty_wasm','spaced'),('ty_wasm','unspaced'),('ty_project','unspaced'),('ty_project','spaced')]:
            observed[pkg+'-'+layout]=state(pkg,layout)
        q.source_gate();q.put(o/'complete.json',observed)

if __name__=='__main__':
    try:main()
    except BaseException:
        if o.is_dir():(o/'failure.txt').write_text(traceback.format_exc())
        raise
