"""Measure only when both strict mixed-library endpoints and independent ordinary callers passed."""
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

here=Path(__file__).resolve().parent
sys.path.insert(0,str(here))
from analyze import analyze
X=Path.home()/'.cache/ohm-233-position-qualified-20261027'
H=X/'mixed-native-abc-protocol-h3-v2'
Q=X/'mixed-alloc-same-compiler-protocol-v1'
ref=X/'mixed-alloc-same-compiler-qualification-v1'
sys.path[:0]=[str(Q),str(H)]
import helpers as q
from common import P,load,dump,sha
from state import source_clean,gate_free,verify_plan
from h3_host import check_h3
from namespace import skeleton
from products import compare_context
assert not sys.flags.optimize and socket.gethostname()=='charlie-ohm-trait-perf-1024' and sorted(os.sched_getaffinity(0))==list(range(24))
plan=load(here/'plan.json')
for f,digest in [(H,plan['original_support']),(Q,plan['qualification_protocol'])]:
    assert sha(f/'SHA256SUMS')==digest
    subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=f,check=True)
subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=here,check=True)
assert sha(here/'analyze.py')==plan['analyzer'] and sha(here/'study.py')==plan['runner']
bc=load(Q/'binding.json');orig=load(H/'runner-binding.json')
assert set(bc['arms'])=={'B','C'} and all(bc['arms'][arm]['driver_sha256']==plan['compiler'] for arm in 'BC')
for arm in 'BC':
    for key in ('cargo','driver'):assert sha(Path(bc['arms'][arm][key]))==bc['arms'][arm][key+'_sha256']
    assert bc['arms'][arm]['cargo_sha256']==plan['cargo'][arm]
check_h3(orig);verify_plan()
out=X/'mixed-alloc-cargo-wall-20261027-v1'
q.out=out;q.b=bc;q.binding=Q/'binding.json';q.fixture=ref/'fixture'
def phase_ref(mode,arm,edit):
    return load(ref/'receipts'/mode/arm/('first-edit' if edit else 'first-restore')/'receipt.json')
def accept():
    grant=load(here/'grant.json')
    for name,digest in grant['physical_receipts'].items():assert sha(ref/name)==digest
    pf=load(ref/'complete.json')
    assert pf['timed_samples']==0 and pf['native_source_index']==source_clean()==orig['host']['source_index_sha256']
    assert grant['qualification_manifest'].startswith('https://github.com/astral-sh/ohm-cargo/tree/') and grant['timing_plan'].startswith('https://github.com/astral-sh/ohm-cargo/tree/')
    for mode in ('build','test'):
        endpoint=pf['completed'][mode]
        assert endpoint['qualified'] and endpoint['native_rust_reader_gate'] and len(endpoint['comparisons'])==9 and all(r['ok'] for r in endpoint['comparisons'].values())
        for direction,n in [('edit',40),('restore',24)]:
            rows=load(ref/('readers-'+mode+'-'+direction+'.json'))
            assert len(rows)==n and all(r['rustc']==r['wrapper']==0 for r in rows)
def clone(mode,arm):
    src=ref/'state'/mode/arm;dst=q.state(mode,arm)
    gate_free(out,int(q.storage_bytes(src)*1.15));dst.parent.mkdir(parents=True,exist_ok=True)
    assert not dst.exists()
    subprocess.run(['cp','-a','--reflink=auto','--',src,dst],check=True)
    assert (dst/'source-state').read_text()=='original'
    seen={}
    for m in q.current_rows(ref/'receipts'/mode/arm/'first-restore-fresh'):
        if m['reason']!='compiler-artifact':continue
        for f in map(Path,m['filenames']):
            key,base=next((name,p) for name,p in [('target',q.TARGET),('shared',q.SHARED)] if f.is_relative_to(p))
            copied=dst/key/f.relative_to(base);origin=src/key/f.relative_to(base);a=origin.stat();b=copied.stat()
            if str(f) in seen:continue
            assert not copied.samefile(origin) and (a.st_size,a.st_mode,a.st_mtime_ns)==(b.st_size,b.st_mode,b.st_mtime_ns)
            dg=sha(origin);assert sha(copied)==dg
            seen[str(f)]=dg
    assert len(seen)>=plan['units'][mode]
    dump(out/('clone-'+mode+'-'+arm+'.json'),seen)
def control(mode,arm,tag,edit):
    first=q.call(mode,arm,arm,'edit',tag,edit)
    fresh=q.call(mode,arm,arm,'detailed-fresh',tag+'-fresh',edit)
    reference=phase_ref(mode,arm,edit);q.check_row(fresh,first);q.check_row(fresh,reference)
    compared=compare_context(fresh['product'],reference['product'])
    dump(out/('control-'+mode+'-'+arm+'-'+tag+'.json'),compared)
def endpoint(mode):
    for arm in 'BC':
        clone(mode,arm)
        fresh=q.call(mode,arm,arm,'detailed-fresh','entry',False)
        q.check_row(fresh,phase_ref(mode,arm,False))
        for tag,edit in [('pre-edit',True),('pre-restore',False)]:control(mode,arm,tag,edit)
    rows=[]
    for i,schedule in enumerate(plan['orders'][mode]):
        direction=schedule['direction'];edit=direction=='edit';pair={}
        for arm in schedule['order']:
            assert (q.state(mode,arm)/'source-state').read_text()==('original' if edit else 'edited')
            tag=f'{i+1:02d}-{direction}'
            timed=q.call(mode,arm,arm,'ordinary',tag,edit)
            fresh=q.call(mode,arm,arm,'fresh',tag+'-fresh',edit)
            q.check_row(fresh,phase_ref(mode,arm,edit))
            assert timed['status']==0 and timed['elapsed_ns']>0
            pair[arm]=timed['elapsed_ns']
        rows.append({**schedule,'ns':pair})
        dump(out/('ledger-'+mode+'.json'),rows)
    for arm in 'BC':
        for tag,edit in [('post-edit',True),('post-restore',False)]:control(mode,arm,tag,edit)
    return rows
with (P/'native-measure.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    accept();assert not out.exists();out.mkdir(mode=0o700);q.mount=skeleton(out)
    try:
        data={}
        for mode in ('build','test'):
            print('starting',mode,flush=True);data[mode]=endpoint(mode)
        accept();dump(out/'observations.json',data)
        dump(out/'statistics.json',analyze(data,plan))
        dump(out/'complete.json',dict(source_index=source_clean(),scored_commands=80,fresh_followups=80,plan=sha(here/'SHA256SUMS')))
    except BaseException:
        (out/'failure.txt').write_text(traceback.format_exc());raise
