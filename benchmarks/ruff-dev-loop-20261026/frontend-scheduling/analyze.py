"""Analyze the predeclared native ABBA/BAAB holdouts at the block level."""
import argparse
import csv
import itertools
import json
import math
from pathlib import Path
import random
import statistics

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('source',type=Path)
ap.add_argument('output',type=Path)
a=ap.parse_args()
rows=[json.loads(s) for s in (a.source/'samples.jsonl').read_text().splitlines()]
design=json.loads((a.source/'plan.json').read_bytes())
repeat=design['phase']=='repeat'
blocks=16 if repeat else 8
groups=['parser','scoped'] if repeat else ['lint','parser','scoped']
prefix='repeat' if repeat else 'native'
assert len(rows)==blocks*4*len(groups) and [r['index'] for r in rows]==list(range(len(rows)))
assert design['plan']==[[r['block'],r['workload'],r['arm']] for r in rows]
assert all(r['units']==(90 if r['workload']=='scoped' else 520) for r in rows)
with (a.output/(prefix+'.csv')).open('w',newline='') as stream:
    w=csv.writer(stream)
    w.writerow(['block','index','workload','arm','wall_ns','child_user_s','child_sys_s','units','rebuilt_package_lines','rmeta_files','api_files','artifact_differences'])
    for r in rows:
        w.writerow([r['block'],r['index'],r['workload'],r['arm'],r['wall_ns'],r['user_s'],r['sys_s'],r['units'],len(r['compile_lines']),r['metas'],r['apis'],','.join(r['parity_failures'])])

summary={}
def reduction(x):
    return 100*(-math.expm1(-x))
for key in groups:
    subset=[r for r in rows if r['workload']==key]
    logs=[]; cpu=[]; paired=[]
    for bid in range(blocks):
        block=[r for r in subset if r['block']==bid]
        arms=[r['arm'] for r in block]
        assert len(block)==4 and arms[0]==arms[3]!=arms[1]==arms[2]
        for i in (0,2):
            pair={r['arm']:r for r in block[i:i+2]}
            paired.append((pair['parent']['wall_ns'],pair['candidate']['wall_ns']))
        logs.append(statistics.mean(math.log(x/y) for x,y in paired[-2:]))
        av={arm:statistics.mean(r['user_s']+r['sys_s'] for r in block if r['arm']==arm) for arm in ['parent','candidate']}
        cpu.append(math.log(av['parent']/av['candidate']))
    observed=abs(sum(logs))
    p=sum(abs(sum(d*s for d,s in zip(logs,signs)))+1e-15>=observed for signs in itertools.product((-1,1),repeat=blocks))/2**blocks
    rng=random.Random(146911)
    boots=sorted(statistics.mean(rng.choices(logs,k=blocks)) for _ in range(50000))
    failed=[r['index'] for r in subset if r['parity_failures']]
    reference=subset[0]
    def inventory(r,kind):
        tag=f"{r['index']:03}-{r['workload']}-{r['arm']}-verify"
        return json.loads((a.source/tag/(kind+'.json')).read_text())
    differences={}
    for kind in ['metadata','api']:
        expected=inventory(reference,kind)
        paths=set()
        for r in subset:
            actual=inventory(r,kind)
            paths.update(k for k in expected.keys() | actual.keys() if expected.get(k)!=actual.get(k))
        differences[kind]=sorted(paths)
    summary[key]={'eligible':not failed,'different_samples':failed,'different_files':differences,
        'geometric_wall_reduction_percent':reduction(statistics.mean(logs)),
        'wall_reduction_95_percent_interval':list(map(reduction,[boots[1249],boots[48750]])),
        'two_sided_block_p':p,'favorable_blocks':sum(d>0 for d in logs),
        'median_parent_s':statistics.median(x for x,y in paired)/1e9,'median_candidate_s':statistics.median(y for x,y in paired)/1e9,
        'descriptive_child_cpu_reduction_percent':reduction(statistics.mean(cpu))}
ordered=sorted(summary,key=lambda k:summary[k]['two_sided_block_p'] if summary[k]['eligible'] else 1)
last=0
for i,k in enumerate(ordered):
    s=summary[k]
    raw=s['two_sided_block_p'] if s['eligible'] else 1
    last=max(last,min(1,(len(ordered)-i)*raw))
    s['holm_p']=last
(a.output/(prefix+'-summary.json')).write_text(json.dumps(summary,indent=2)+'\n')
for k,v in summary.items():
    print(k,{key:val for key,val in v.items() if key not in ('different_files','different_samples')},'unequal',len(v['different_samples']),{kind:len(f) for kind,f in v['different_files'].items()})
