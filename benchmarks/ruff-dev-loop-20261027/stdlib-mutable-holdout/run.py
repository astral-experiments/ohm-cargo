"""Replay the full historical Ruff standard-library edit on two independently warmed compilers."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

base=Path.home()/'.cache/ohm-233-position-qualified-20261027'
assets=base/'assets-cohort-v2'
here=Path(__file__).resolve().parent
plan=json.loads((here/'plan.json').read_bytes())
patch=here/'stdlib-mutable.patch'
output=base/'stdlib-holdout-exact-v1'
assert hashlib.sha256(patch.read_bytes()).hexdigest()==plan['patch_sha256']
assert not any(k in os.environ for k in ('RUSTFLAGS','RUSTC_WRAPPER','RUSTC_LOG')) and not any(k.startswith('WILD_') for k in os.environ)

def module(label,name):
    spec=importlib.util.spec_from_file_location(label,assets/name)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
s=module('series','revision-series.py'); w=module('worker','revision-worker.py')
source=s.RUFF/'crates/ruff_python_stdlib/src/typing.rs'
markdown=s.RUFF/'crates/ruff_linter/resources/mdtest/flake8-bugbear/mutable-argument-default.md'
case=b'from collections import ChainMap\nfrom weakref import WeakSet\n\ndef f(a=ChainMap(), b=WeakSet()):\n    pass\n'

def read(p):return json.loads(p.read_bytes())

def write(p,obj):p.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')

def verify(mode,edited):
    assert markdown.is_file() == (not edited)
    assert (b'"WeakKeyDictionary" | "WeakValueDictionary" | "WeakSet"' in source.read_bytes()) == (not edited)
    r=subprocess.run([w.TARGET/'debug/ruff','check','--isolated','--no-cache','--select','B006,B008','--output-format','json','--stdin-filename','stdlib_case.py','-'],input=case,cwd=s.RUFF,capture_output=True)
    diags=json.loads(r.stdout)
    assert r.returncode==1 and not r.stderr
    assert [(d['location']['row'],d['code']) for d in diags]==[(4,'B008' if edited else 'B006')]*2,(mode,edited,diags)
    return [{'code':d['code'],'row':d['location']['row'],'column':d['location']['column']} for d in diags]

if len(sys.argv)>1:
    assert sys.argv[1]=='--inside'
    mode,arm,label=sys.argv[2:];d=output/mode/arm
    assert w.sha(s.FROZEN/'bin/cargo')==plan['cargo'] and w.sha(s.FROZEN/'lib/librustc_driver-774a793a844d5500.so')==plan['drivers'][arm]
    assert s.git('rev-parse','HEAD')==plan['pin']
    if label=='before':
        w.run(d/'settle','settle',mode,'normal',False);w.run(d/'train','train',mode,'normal',False)
        w.run(d/label,label,mode,'reference',False)
    else:
        w.run(d/label,label,mode,'trace',False);w.run(d/(label+'-fresh'),label+'-fresh',mode,'fresh',False)
    write(d/label/'stdlib-diagnostics.json',verify(mode,label.startswith('edit-')))
    sys.exit(0)

assert not (output/'complete.json').exists()
with (s.P/'native-measure.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    assert (base/'qualification-posobs4fmt-c3/complete.json').is_file() and (base/'cargo-observer-ruff-final/complete.json').is_file()
    assert s.git('rev-parse','HEAD')==plan['pin'] and not s.git('status','--porcelain')
    index=Path(s.git('rev-parse','--path-format=absolute','--git-path','index'));index_digest=s.sha(index)
    files={n:((s.RUFF/n).read_bytes(), (s.RUFF/n).stat()) for n in (l.split('\t',2)[2] for l in s.git('apply','--numstat',patch).splitlines())}
    assert set(s.RUFF/n for n in files)=={source,markdown}
    output.mkdir();shutil.copyfile(here/'plan.json',output/'plan.json')
    results={}
    for mode,arms in plan['orders'].items():
        results[mode]={}
        for arm in arms:
            d=output/mode/arm;d.mkdir(parents=True)
            state=base/'cohort-state-v2'/arm
            target,shared=state/'target',state/'shared-build'
            assert target.is_dir() and shared.is_dir() and shutil.disk_usage(state).free>25*2**30
            drv=s.P/'subjects/parent-driver' if arm=='parent232' else base/'drivers'/('driver-'+plan['drivers'][arm]);assert w.sha(drv)==plan['drivers'][arm]
            cmd=['bwrap','--ro-bind','/','/','--proc','/proc','--dev-bind','/dev','/dev','--bind','/tmp','/tmp','--bind',str(output),str(output)]
            for p in (s.P/'registry-home',s.P/'rustup'):cmd+=['--bind',str(p),str(p)]
            for p,q in ((target,s.P/'native-target'),(shared,s.P/'shared')):cmd+=['--bind',str(p),str(q)]
            cargo=Path.home()/'.cache/ohm-mixed-cargo-release-20261027/cargo-observer3'
            for p,q in ((drv,s.FROZEN/'lib/librustc_driver-774a793a844d5500.so'),(cargo,s.FROZEN/'bin/cargo')):cmd+=['--ro-bind',str(p),str(q)]
            def run(label):subprocess.run([*cmd,'--','taskset','-c','0-23',sys.executable,'-B',__file__,'--inside',mode,arm,label],check=True)
            run('before');before=read(d/'before'/'receipt.json')
            reps=[]
            for i in (1,2):
                with s.edit(patch,files,index,index_digest):run(f'edit-{i}')
                run(f'restore-{i}')
                phases={}
                for phase in ('edit','restore'):
                    p=d/f'{phase}-{i}';r=read(p/'receipt.json');fresh=read(d/(p.name+'-fresh')/'receipt.json')
                    assert r['roster_sha']==before['roster_sha']==fresh['roster_sha'] and not fresh['dirty']
                    assert r['elf'].keys()==before['elf'].keys() and len(r['elf'])==(15 if mode=='build' else 110)
                    phases[phase]={k:r[k] for k in ('crates','processes','roster_sha')};phases[phase].update(stdlib=read(p/'stdlib-diagnostics.json'),fresh_units=fresh['fresh'])
                reps.append(phases)
            results[mode][arm]={'repetitions':reps,'same_process_rosters':reps[0]==reps[1]};write(output/'progress.json',results)
            print(mode,arm,reps[0]['edit']['processes'],reps[1]['edit']['processes'],flush=True)
    assert not s.git('status','--porcelain') and s.sha(index)==index_digest
    write(output/'complete.json',{'source_clean':True,'index_sha256':index_digest,'subjects':plan['drivers'],'results':results})
