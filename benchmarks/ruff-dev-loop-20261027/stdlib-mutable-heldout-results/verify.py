"""Recheck each held-out edit and restoration without a compiler or a Ruff checkout."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import re

here=Path(__file__).resolve().parent
data=json.loads((here/'observations.json').read_bytes())
plan=json.loads((here/'plan.json').read_bytes())
assert data['registered_plan']==plan and data['complete']['subjects']==plan['drivers']
assert data['complete']['source_clean'] and hashlib.sha256((here/'stdlib-mutable.patch').read_bytes()).hexdigest()==plan['patch_sha256']
for mode,arms in data['complete']['results'].items():
    assert set(arms)==set(plan['orders'][mode])
    for arm,body in arms.items():
        reps=body['repetitions'];assert len(reps)==plan['repetitions']==2 and body['same_process_rosters']==(reps[0]==reps[1])
        for i,rep in enumerate(reps,1):
            for phase in ('edit','restore'):
                r=data['witnesses'][mode][arm][f'{phase}-{i}'];obs=rep[phase]
                assert r['fresh_units']==obs['fresh_units']==(501 if mode=='build' else 619)
                assert r['roster_sha']==obs['roster_sha']==reps[0]['edit']['roster_sha']
                assert len(r['elf'])==(15 if mode=='build' else 110) and all(re.fullmatch(r'[0-9a-f]{64}',h) for h in r['elf'].values())
                events=r['physical']
                assert all(re.fullmatch(r'exec\.\d+',f) and re.fullmatch(r'[0-9a-f]{64}',h) for f,h,k,c in events)
                assert Counter(v[2] for v in events)==obs['processes']
                assert sorted([[v[2],v[3]] for v in events if v[3]])==obs['crates']
                assert r['diagnostics']==obs['stdlib']
                assert [(v['row'],v['code']) for v in r['diagnostics']]==[(4,'B008' if phase=='edit' else 'B006')]*2
        print(mode,arm,[p['edit']['processes'] for p in reps])

relations=json.loads((here/'stdlib-extern-relations.json').read_bytes())
for phase,items in relations.items():
    events=data['witnesses']['build']['posobs4fmt-c3'][phase]['physical']
    assert {(x[0],x[1],x[3]) for x in events if x[2]=='rustc_full'} == {(r['trace'],r['argv_sha256'],r['crate']) for r in items}
    assert sum(r['direct_stdlib_extern'] for r in items)==6
