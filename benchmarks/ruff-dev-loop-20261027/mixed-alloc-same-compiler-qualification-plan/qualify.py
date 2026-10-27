"""Use a single compiler credential and independently rebuilt workspace states for both Cargo arms."""
from pathlib import Path
import fcntl
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import traceback

root=Path(__file__).resolve().parent
X=Path.home()/'.cache/ohm-233-position-qualified-20261027'
H=X/'mixed-native-abc-protocol-h3-v2'
sys.path.insert(0,str(H))
import helpers as q
from common import P,CARGO_HOME,load,dump,need,sha
from state import WASM,source_clean,inputs,seed,gate_free,verify_plan
from namespace import skeleton
from h3_host import check_h3
from products import compare_context
assert not sys.flags.optimize and socket.gethostname()=='charlie-ohm-trait-perf-1024'
assert sorted(os.sched_getaffinity(0))==list(range(24))
assert sha(H/'SHA256SUMS')=='59ca9193f8f6ddf4cff22ab023cc41733200d251f42e3400635f0e81c42a5d71'
subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=H,check=True)
subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=root,check=True)
bc=load(root/'binding.json');support=load(root/'support.json');orig=load(H/'runner-binding.json')
check_h3(orig);verify_plan()
q.b=bc;q.binding=root/'binding.json';q.out=X/'mixed-alloc-same-compiler-qualification-v1'
out=q.out
for k,v in support['old_inputs'].items():assert sha(H/k)==v
for arm in 'BC':
    row=bc['arms'][arm]
    for k in ('driver','cargo'):assert sha(Path(row[k]))==row[k+'_sha256']
    assert row['cargo_sha256']==orig['arms'][arm]['cargo_sha256']
driver=Path(bc['arms']['C']['driver'])
assert sha(driver)==sha(Path(bc['arms']['B']['driver']))==load(root/'plan.json')['compiler']
assert sha(driver.parent/'SHA256SUMS')==bc['frozen_source_manifest']
assert load(driver.parent/'receipt.json')['profiles']==bc['profiles']
for name,tool in bc['host']['host_tools'].items():
    assert Path(tool['path']).resolve()==Path(tool['resolved']) and sha(Path(tool['path']))==tool['sha256'],name
save=lambda rel,x:dump(out/rel,x)

def project(mode,tag,reg,local,expected,origin):
    gate_free(out, 13*2**30)
    dest=seed(q.state(mode,tag),q.fixture,CARGO_HOME)
    assert not any((dest/'shared').iterdir())
    entries=q.project(reg,dest/'target',q.state(mode,'B')/'target')
    assert all(not (dest/'target'/n).exists() for n in local)
    assert not any((dest/'shared').iterdir())
    if expected is not None:assert entries==expected
    save(mode+'-'+tag+'-registry.json',entries)
    return entries

def check_projection(mode,tag,reg,local,expected_plugin):
    items=q.current_rows(q.dest(mode,tag,'cold'))
    crates=[v for v in items if v['reason']=='compiler-artifact']
    assert len(crates)=={'build':501,'test':619}[mode]
    real=[]
    for v in crates:
        remote=v['package_id'].startswith(q.origin+'#')
        assert v['fresh']==remote,(mode,tag,v['package_id'],v['fresh'])
        for f in v['filenames']:
            unit=q.unit_of(f)
            if remote:assert unit in reg
            elif unit is not None:assert unit in local
        if v['target']['name']=='get_size_derive2':
            artifact,=v['filenames'];real.append(sha(q.state(mode,tag)/'target'/Path(artifact).relative_to(q.TARGET)))
    assert real==[expected_plugin]
    save(mode+'-'+tag+'-cold-oracle.json',dict(units=len(crates),fresh_registry=sum(v['fresh'] for v in crates),workspace_cold=sum(not v['fresh'] for v in crates),plugin=expected_plugin))

def readers(mode,label,states):
    rows=[];t=out/'independent-bridges'/mode/label;t.mkdir(parents=True)
    for crate in WASM:
        bridges={}
        for action in ['bridge','caller']:
            for state,(arm,ref,flags) in states.items():
                choices=bridges if action=='caller' else {'self':None}
                for origin,bridge in choices.items():
                    d=t/(crate+'-'+action+'-'+state+'-'+origin);d.mkdir()
                    extra=['--bind',str(d),str(out/'bridge-canonical')]
                    if bridge:extra+=['--ro-bind',str(bridge),str(out/'libordinary_bridge_input.rlib')]
                    cmd=[*q.command(q.state(mode,state),arm,extra),sys.executable,'-B',str(root/'bridge-status-worker.py'),'--root',str(out),'--action',action,'--crate',crate,'--arm',arm,'--out',str(d/'receipt'),'--binding',str(q.binding),'--details',str(ref/'receipt.json'),'--flags',str(flags/'receipt.json')]
                    z=subprocess.run(cmd,capture_output=True)
                    (d/'outer.stdout').write_bytes(z.stdout);(d/'outer.stderr').write_bytes(z.stderr)
                    rc=load(d/'receipt/rustc-status.json')['rustc_status']
                    if action=='bridge':
                        assert rc==z.returncode==0,(crate,state,z.stderr[-1400:])
                        # Populate after finishing this state so the fixed self iteration is unaltered.
                        bridges[state]=d/'libordinary_bridge.rlib'
                    native=load(d/'receipt/bridge.json')['runtime'] if z.returncode==0 else None
                    rows.append(dict(crate=crate,state=state,bridge_from=origin,action=action,rustc=rc,wrapper=z.returncode,runtime=native,receipt=str(d.relative_to(out))))
    save('readers-'+mode+'-'+label+'.json',rows)
    return all(v['rustc']==v['wrapper']==0 for v in rows)

def mode_study(mode):
    gate_free(out,(45 if mode=='test' else 26)*2**30)
    seed(q.state(mode,'B'),q.fixture,CARGO_HOME)
    first_b,initial_b=q.train(mode,'B','B')
    origin=q.dest(mode,'B','cold')
    reg,local,origins=q.units(origin/'stdout')
    save(mode+'-registry-overview.json',dict(registry={str(k):v for k,v in reg.items()},excluded={str(k):v for k,v in local.items()}))
    save(mode+'-verified-crate-archives.json',q.verify_packages(set(reg.values()),q.state(mode,'B')/'registry-home'))
    save(mode+'-registry-source-commands.json',q.filtered_argv_set(reg,origins,origin,True))
    anchored=project(mode,'C',reg,local,None,origin)
    plugin,={v['sha256'] for n,v in anchored.items() if '/get-size-derive2/' in n and n.endswith('.so')}
    first_c,initial_c=q.train(mode,'C','C');check_projection(mode,'C',reg,local,plugin)
    project(mode,'gold-B',reg,local,anchored,origin)
    _,gold=q.train(mode,'gold-B','B',True);check_projection(mode,'gold-B',reg,local,plugin)
    compared={}
    def compare(name,got,reference):
        try:compared[name]=dict(ok=True,details=compare_context(got['product'],reference['product']))
        except ValueError as e:compared[name]=dict(ok=False,mismatch=str(e))
        save(mode+'-structural.json',compared)
    compare('original-cold-C-B',initial_c,initial_b)
    for arm in 'BC':
        for edit,name in [(True,'edit'),(False,'restore')]:
            altered=q.call(mode,arm,arm,'conditioning','condition-'+name,edit)
            fresh=q.call(mode,arm,arm,'detailed-fresh','condition-'+name+'-fresh',edit)
            q.check_row(fresh,altered)
    q.clone(mode,q.dest(mode,'C','condition-restore-fresh'))
    eligible=True
    for edit,label in [(True,'edit'),(False,'restore')]:
        current={}
        flags={}
        for arm in 'BC':
            current[arm]=q.call(mode,arm,arm,'edit','first-'+label,edit)
            fresh=q.call(mode,arm,arm,'fresh','first-'+label+'-fresh',edit);q.check_row(fresh,current[arm])
            flags[arm]=(arm,q.dest(mode,arm,'first-'+label),q.dest(mode,arm,'cold'))
            ref=gold if edit else {'B':initial_b,'C':initial_c}[arm]
            compare(label+'-'+arm+'-independent-full',current[arm],ref)
        compare(label+'-C-B',current['C'],current['B'])
        prior=q.dest(mode,'C','condition-restore-fresh') if edit else q.dest(mode,'forced-C','forced-edit')
        force=q.call(mode,'forced-C','C','forced','forced-'+label,edit,force=prior)
        fresh=q.call(mode,'forced-C','C','fresh','forced-'+label+'-fresh',edit);q.check_row(fresh,force)
        compare(label+'-C-forced-same-state',current['C'],force)
        flags['forced-C']=('C',q.dest(mode,'forced-C','forced-'+label),q.dest(mode,'C','cold'))
        if edit:flags['gold-B']=('B',q.dest(mode,'gold-B','initial-fresh'),q.dest(mode,'gold-B','cold'))
        eligible=readers(mode,label,flags) and eligible
    return dict(qualified=eligible and all(v['ok'] for v in compared.values()),native_rust_reader_gate=eligible,comparisons=compared)

with (P/'native-measure.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);assert not out.exists();gate_free(X,82*2**30)
    out.mkdir(mode=0o700);index=source_clean()
    assert index==orig['host']['source_index_sha256']
    q.mount=skeleton(out);q.fixture=inputs(out)
    (out/'bridge-canonical').mkdir();(out/'libordinary_bridge_input.rlib').touch()
    src=out/'bridge-src';src.mkdir()
    (src/'caller.rs').write_text('fn main() { println!("{}", ordinary_bridge::observed()); }\n')
    for k,v in [('ruff_wasm','ruff_wasm::Workspace::version()'),('ty_wasm','ty_wasm::version()')]:
        (src/(k+'.rs')).write_text('pub fn observed() -> String { '+v+'.to_string() }\n')
    completed={}
    try:
        for mode in ('build','test'):
            print('starting unscored',mode,flush=True);completed[mode]=mode_study(mode)
            save('progress.json',completed)
        assert source_clean()==index
        save('complete.json',dict(completed=completed,native_source_index=index,timed_samples=0))
    except BaseException:
        (out/'failure.txt').write_text(traceback.format_exc());raise
