"""Capture receipts for the fixed Rust compiler after its screening command and fresh repeat."""
import hashlib
import json
import os
from pathlib import Path

cpus=[cpu for cpu in os.sched_getaffinity(0) if cpu>23]
if cpus: os.sched_setaffinity(0,{max(cpus)})
base=Path.home()/'.cache/ohm-233-position-qualified-20261027'
tag='posobs4fmt-c3'
eps=('doc-build','doc-test','parser-build','parser-test')
results={}
for ep in eps:
    folder=base/f'candidate-screen-{tag}-{ep}'
    complete=json.loads((folder/'complete.json').read_bytes());assert complete['source_clean']
    plan=json.loads((folder/'plan.json').read_bytes())
    each={}
    for arm, src in [('candidate',folder)]+([('parent232',base/f'controls-base-c3-{ep}'),('old233',base/f'controls-base-c3-{ep}')] if ep.startswith('doc') else []):
        prefix=arm if arm!='parent232' else 'parent'
        observed=json.loads((src/'plan.json').read_bytes())
        rows={}
        for phase in ('verify-edit','verify-noop'):
            p=src/f'{prefix}-{phase}'/'receipt.json';b=p.read_bytes();r=json.loads(b)
            assert len(r['dirty'])+r['fresh']==(501 if ep.endswith('build') else 619)
            rows[phase]={'receipt_sha256':hashlib.sha256(b).hexdigest(),'roster_sha':r['roster_sha'],'fresh_units':r['fresh'],'full_dirty_count':len(r['dirty']),'processes':r['processes'],'crates':r['crates']}
            if phase=='verify-noop':assert not r['dirty'] and not any(r['processes'].values())
        each[arm]={'driver':observed['subjects'][prefix],**rows}
    results[ep]=each
proof=json.loads((base/f'qualification-{tag}'/'release-semantics-approved.json').read_bytes());assert proof['driver']==results['doc-build']['candidate']['driver']
print(json.dumps({'ruff':complete['pin'],'compiler':proof['source'],'driver':proof['driver'],'cargo':json.loads((base/'assets-cohort-v2/plan.json').read_bytes())['cargo'],'endpoints':results},sort_keys=True,indent=2))
