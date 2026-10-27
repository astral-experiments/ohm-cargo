"""Run the frozen scheduler trial order only after both native Ruff workflows pass."""
from pathlib import Path
import collections
import fcntl
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import tempfile
import traceback

here=Path(__file__).resolve().parent
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
analyze=module('analyze',here/'analyze-wall.py').analyze
p=Path('/mnt/devbox-scratch/dev-user/ohm-early-completion-20261027')
native=p/'run-native-v2/run.py';n=module('native',native);q=n.q
plan=n.load(here/'plan.json');o=p/'early-completion-wall-v2'
def store(root,name,b):root.joinpath(name).write_bytes(b)
def reference(workflow,arm):
    d=n.o/(workflow+'-'+arm)
    return n.load(d/'product.json'),n.o/(workflow+'-state-'+arm),n.load(d/'physical.json')

def frozen():
    q.source_gate();assert q.sha(native)==plan['native_runner']
    assert (p/'run-native-v2/exit').read_text()=='0' and (p/'run-ruff-v1/exit').read_text()=='0'
    assert {a:q.sha(f) for a,f in n.executables.items()}==n.roles==plan['cargo']
    official=n.load(p/'official/binding.json')
    assert official['archive_sha256']==plan['release_archive'] and official['hashes']==plan['release_tools']
    drivers=list((q.sdk/'lib').glob('librustc_driver-*.so'));assert len(drivers)==1
    assert q.sha(drivers[0])==official['hashes']['driver'] and q.sha(q.sdk/'bin/rustc')==official['hashes']['frontend']
    assert q.sha(p/'release-pair-v1/cargo-parent-repeat')==n.roles['B']
    grant=n.load(here/'grant.json')
    assert grant['manifest']==q.sha(here/'SHA256SUMS') and grant['native_complete']==q.sha(n.o/'complete.json')
    assert grant['matched_sources']==plan['matched_sources'] and len(grant['publication_commit'])==40
    good=n.load(n.o/'complete.json')
    for workflow in ('selection','cold'):
        for arm in 'BC':
            prod,st,phys=reference(workflow,arm)
            assert set(prod['native']) and len(prod['native'])==110
            assert good['results'][workflow][arm]['product']==q.sha(n.o/(workflow+'-'+arm)/'product.json')
            if workflow=='selection':
                assert len(phys['integration'][n.special])==len(phys['target_link_groups'][prod['e2e'][0]])==(2 if arm=='B' else 1)
        assert good['comparisons'][workflow+'/B']['exact']+len(good['comparisons'][workflow+'/B']['allowed'])==110
        assert good['comparisons'][workflow+'/C']['exact']+len(good['comparisons'][workflow+'/C']['allowed'])==110
    assert good['all_tests_executed_during_build']==0
    assert plan['ruff']==q.pin and plan['source_sha256']==q.original and plan['edited_sha256']==q.reversed_

def slot(workflow,arm,num,sd,source):
    out=o/workflow/(str(num).zfill(2)+'-'+arm);out.mkdir()
    expected,ref,phys=reference(workflow,arm);exe=n.executables[arm]
    assert shutil.disk_usage(p).free>65*2**30
    with tempfile.TemporaryDirectory(dir=p,prefix='ohm-scheduler-trial-') as scratch:
        trial=Path(scratch);t=trial/'state';overlay=None
        if workflow=='selection':
            subprocess.run(['cp','-a','--reflink=auto','--',str(source),str(t)],check=True)
            rlib=q.printed(t,sd['path']);base=q.printed(source,sd['path'])
            assert not rlib.samefile(base) and q.sha(rlib)==q.sha(base)==sd['sha256']
            assert not q.printed(t,expected['e2e'][0]).exists()
            overlay=trial/'edited.rs';store(trial,'edited.rs',(p/'inputs/ruff-edited-inlay-hints.rs').read_bytes());overlay.chmod(0o444)
            assert q.sha(overlay)==plan['edited_sha256'] and overlay.stat().st_mtime_ns>rlib.stat().st_mtime_ns
        else:q.state(t)
        args,env=q.opts(t,exe,overlay)
        args+=['--bind',str(out),str(out),'--chdir',str(q.src),'--']
        actual=subprocess.check_output([*args,'sha256sum',str(q.sdk/'bin/cargo')],env=env).split()[0].decode()
        assert actual==plan['cargo'][arm]
        assert 'RUSTFLAGS' not in env and 'RUSTC_WRAPPER' not in env and 'CARGO_LOG' not in env
        assert sorted(os.sched_getaffinity(0))==plan['affinity']
        clock=out/'ordinary';clock.mkdir()
        cmd=['cargo','+ohm',*q.select,'--locked','--offline','-j8']
        subprocess.run([*args,'/usr/bin/python3','-B',str(here/'run-clock.py'),str(clock),*cmd],check=True,env=env)
        measurement=n.load(clock/'clock.json');assert measurement['returncode']==0 and measurement['elapsed_ns']>0
        assert not (clock/'stdout').read_bytes() and b'Finished' in (clock/'stderr').read_bytes() and b'Blocking waiting' not in (clock/'stderr').read_bytes()
        just_built={**expected,'native':{name:q.sha(q.printed(t,name)) for name in expected['native']}}
        before=n.compare(expected,just_built,ref,t)
        assert n.list_test(t,exe,just_built,clock,overlay)==n.load(n.o/'complete.json')['results'][workflow][arm]['test_list']
        followups=[]
        for k in range(1,(2 if workflow=='selection' else 3)+1):
            after=q.run(t,exe,q.select,out/('follow-'+str(k)),overlay)
            native_check=n.compare(expected,after,ref,t)
            followups.append(dict(dirty=after['dirty'],same=native_check['exact'],other=native_check['allowed'],roster=after['roster']))
            if not after['dirty']:break
        assert not followups[-1]['dirty']
        if workflow=='selection':assert len(followups)==1
        q.put(out/'verified.json',dict(workflow=workflow,arm=arm,ns=measurement['elapsed_ns'],subject=actual,
            original_reference=q.sha(n.o/(workflow+'-'+arm)/'product.json'),as_built=before,
            initial_native=just_built['native'],roster=after['roster'],followups=followups,dirty_seed=workflow=='cold',
            input=q.sha(overlay) if overlay else q.original,source_untouched=q.sha(q.src/q.file)==q.original,
            stdout=q.sha(clock/'stdout'),stderr=q.sha(clock/'stderr')))
    return measurement['elapsed_ns']

def main():
    assert socket.gethostname()=='charlie-ohm-pkg-build-1024' and not o.exists()
    subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=here,check=True)
    os.sched_setaffinity(0,set(plan['affinity']))
    with (p/'native-measure.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);frozen();o.mkdir(mode=0o700)
        rows={};source=q.lab/'official-before-selection';sd=n.load(q.lab/'complete.json')['seed_rlib']
        for workflow in ('selection','cold'):
            (o/workflow).mkdir();rows[workflow]=[]
            print('starting',workflow,flush=True)
            for i,order in enumerate(plan['orders'][workflow],1):
                values={a:slot(workflow,a,i,sd,source) for a in order}
                rows[workflow].append(dict(order=order,ns=values));q.put(o/('ledger-'+workflow+'.json'),rows[workflow])
            print('finished',workflow,len(rows[workflow]),flush=True)
        frozen();q.put(o/'all.json',rows);q.put(o/'result.json',analyze(plan,rows))
        q.put(o/'complete.json',dict(commands=2*sum(map(len,rows.values())),plan=q.sha(here/'SHA256SUMS'),native=q.sha(n.o/'complete.json')))
if __name__=='__main__':
    try:main()
    except BaseException:
        if o.is_dir():(o/'failure.txt').write_text(traceback.format_exc())
        raise
