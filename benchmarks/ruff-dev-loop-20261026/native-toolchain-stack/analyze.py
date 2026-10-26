"""Summarize a completed, independently ordered two-endpoint native replay."""
import csv
import itertools
import json
import math
from pathlib import Path
import statistics
import sys

source, out=map(Path,sys.argv[1:])
raw=list(csv.DictReader((source/'observations.csv').open()))
plan=json.loads((source/'plan.json').read_text())
valid=json.loads((source/'validation.json').read_text())
assert len(raw)==48
assert [(r['case'],int(r['pair']),r['arm']) for r in raw]==[
    (block['case'],block['pair'],arm) for block in plan['plan'] for arm in block['order']]
groups={}
for row in raw:
    case=row['case']; pair=int(row['pair']); arm=row['arm']; pos=int(row['position'])
    assert len(valid['rosters'][case][arm])==int(row['rustcs']) and pos in (0,1)
    groups.setdefault(case,{}).setdefault(pair,{})[arm]=(int(row['elapsed_ns']),pos)
summaries={}
for case,blocks in groups.items():
    assert len(blocks)==12
    diffs=[];slots=[];percent=[];parents=[];candidates=[]
    for pair in sorted(blocks):
        (parent,p),(new,n)=blocks[pair]['parent'],blocks[pair]['candidate']
        assert {p,n}=={0,1}
        parents.append(parent);candidates.append(new);diffs.append(parent-new)
        slots.append((parent-new) if p==0 else (new-parent));percent.append(100*(1-new/parent))
    percent.sort();observed=abs(sum(diffs));slotsum=sum(slots)
    assert sum(b['parent'][1]==0 for b in blocks.values())==6
    extreme=sum(abs(slotsum-2*sum(subset))>=observed for subset in itertools.combinations(slots,6))
    summaries[case]=dict(n=12,favorable=sum(d>0 for d in diffs),parent_median_s=statistics.median(parents)/1e9,
        candidate_median_s=statistics.median(candidates)/1e9,median_reduction=statistics.median(percent),
        interval=[percent[2],percent[-3]],range=[percent[0],percent[-1]],exact_p=extreme/math.comb(12,6))
last=0
for i,case in enumerate(sorted(summaries,key=lambda k:summaries[k]['exact_p'])):
    r=summaries[case];last=max(last,min(1,(2-i)*r['exact_p']));r['holm_p']=last
(out/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
print(json.dumps(summaries,indent=2))
