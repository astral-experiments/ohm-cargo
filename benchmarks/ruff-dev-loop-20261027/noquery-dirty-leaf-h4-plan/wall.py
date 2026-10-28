"""Execute the registered three-arm nonobserver study. Native qualification and a separate grant are required."""
from collections import Counter
from pathlib import Path
import csv
import fcntl
import hashlib
import json
import os
import shutil
import sys
import traceback

sys.path.insert(0,str(Path(__file__).resolve().parent))
import design
import qualify as q


def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def as_json(obj):return json.loads(json.dumps(obj,sort_keys=True))


def gates(qualification):
    expected={}
    for kind in ('check','build'):
        for direction in ('edit','restore'):
            labels=tuple(kind+'-'+a for a in ('B','P','N','B2','P2','N2'))
            prior=[qualification['controls'][k][direction] for k in labels]
            same=[as_json(q.original.native(row)) for row in prior]
            assert same==[same[0]]*6
            expected[kind,direction]=same[0]
    return expected


def run(binding,qual,release):
    assert qual['binding']==q.sha(q.inputs/'frozen-binding.json')
    assert release['binding']==qual['binding'] and release['qualification']==q.sha(q.inputs/'native-qualification.json')
    assert release['plan']==q.sha(q.inputs/'plan.json') and release['scoring_grant']
    assert release['source']=={f:q.sha(q.here/f) for f in ('qualify.py','wall.py','design.py','analyze.py')}
    q.configure(binding);assert set(binding['cpus'])=={8,9,10,11}
    plan=json.loads((q.inputs/'plan.json').read_bytes());blocks=design.schedule();assert blocks==plan['blocks']
    refs=gates(qual)
    # Physical qualified states are still at the restored source. Catch drift before the first clock.
    for arm in 'BPN':
        for kind in ('check','build'):
            state=q.fixture.state_dir(kind,arm)
            row=q.fixture.observe(state,kind,arm,'wall-pre-fresh',False)
            assert row['fresh'] and not row['trace']['jobs'] and not row['trace']['observer_probes']
            assert as_json(q.original.native(row))==refs[kind,'restore']
    ledger=q.root/'wall-ledger';ledger.mkdir(mode=0o700);(ledger/'raw').mkdir();(ledger/'callers').mkdir()
    seen=Counter();scope=q.fixture.scoped
    def run_observation(arm,kind,direction,block,cycle,slot):
        state=q.fixture.state_dir(kind,arm);edited=direction=='edit';q.fixture.source(state,edited)
        label=f'wall-{block:02}-{cycle:02}-{slot}';destination=q.root/'records'/(kind+'-'+arm)/label
        prefix=ledger/'raw'/(f'{block:02}-{kind}-{cycle:02}-{slot}-{arm}');prefix.mkdir()
        invocations=[]
        def capture(args,work=None):
            res=scope(args,work);n=len(invocations);a=prefix/(str(n)+'.stdout');b=prefix/(str(n)+'.stderr')
            a.write_bytes(res.stdout);b.write_bytes(res.stderr)
            invocations.append({'status':res.returncode,'stdout':digest(a),'stderr':digest(b),'inside_cargo_timer':str(q.inputs/'inside.py') in [str(s) for s in args]})
            (prefix/'commands.json').write_text(json.dumps(invocations,sort_keys=True)+'\n');return res
        try:
            q.fixture.scoped=capture
            row=q.fixture.observe(state,kind,arm,label,edited,traced=False)
        finally:q.fixture.scoped=scope
        assert invocations[0]['inside_cargo_timer'] and sum(w['inside_cargo_timer'] for w in invocations)==1
        assert row['trace'] is None and not row['fresh'] and row['units']==1 and as_json(q.original.native(row))==refs[kind,direction]
        caller=destination/('caller.rmeta' if kind=='check' else 'caller')
        if not edited:
            assert caller.is_file();h=digest(caller);archive=ledger/'callers'/h
            if not archive.exists():archive.write_bytes(caller.read_bytes())
            assert archive.stat().st_size==caller.stat().st_size and digest(archive)==h
            caller.unlink();row['native_caller_file_sha256']=h
        else:assert not caller.exists()
        (prefix/'observation.json').write_text(json.dumps(row,sort_keys=True)+'\n')
        return row['elapsed_ns']
    with (ledger/'times.csv').open('x',newline='') as out:
        w=csv.DictWriter(out,fieldnames=['block','kind','cycle','direction','slot','arm','elapsed_ns']);w.writeheader();out.flush()
        for block in blocks:
            for cycle in block['cycles']:
                for slot,arm in enumerate(cycle['order'],1):
                    count={'block':block['block'],'kind':cycle['kind'],'cycle':cycle['cycle'],'direction':cycle['direction'],'slot':slot,'arm':arm}
                    assert shutil.disk_usage(q.root).free>binding['free_floor_bytes']
                    ns=run_observation(arm,cycle['kind'],cycle['direction'],block['block'],cycle['cycle'],slot)
                    w.writerow({**count,'elapsed_ns':ns});out.flush();os.fsync(out.fileno());seen[cycle['kind']]+=1
            print('validated randomized nonobserver block',block['block'],'of',len(blocks),flush=True)
    assert dict(seen)=={'check':4752,'build':432}
    for kind in ('check','build'):
        for arm in 'BPN':
            row=q.fixture.observe(q.fixture.state_dir(kind,arm),kind,arm,'wall-post-fresh',False)
            assert row['fresh'] and not row['trace']['jobs'] and not row['trace']['observer_probes']
            assert as_json(q.original.native(row))==refs[kind,'restore']
    (ledger/'complete.json').write_text(json.dumps({'binding':qual['binding'],'native_gate':release['qualification'],'plan':release['plan'],'times':digest(ledger/'times.csv'),'counts':dict(seen)},indent=2)+'\n')


if __name__=='__main__':
    binding=json.loads((q.inputs/'frozen-binding.json').read_bytes());native=json.loads((q.inputs/'native-qualification.json').read_bytes());r=json.loads((q.inputs/'registered-activation.json').read_bytes())
    try:
        with Path(binding['host_lock']).open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);run(binding,native,r)
    except BaseException:
        (q.root/'first-wall-failure.txt').open('x').write(traceback.format_exc());raise
