"""Estimate paired effects under the registered within-endpoint balanced order assignment."""
import itertools
import json
import math
import random
import statistics
import sys
from pathlib import Path

def endpoint(rows,order,seed):
    assert [v['order'] for v in rows]==order and set(order)=={'BC','CB'} and order.count('BC')*2==len(order)
    assert all(set(v['ns'])=={'B','C'} and min(v['ns'].values())>0 for v in rows)
    logs=[math.log(v['ns']['C']/v['ns']['B']) for v in rows]
    slot=[v if s=='BC' else -v for s,v in zip(order,logs,strict=True)]
    n=len(logs);base=sum(slot);threshold=abs(sum(logs))
    denom=math.comb(n,n//2)
    extreme=sum(abs(2*sum(x)-base)+1.e-12>=threshold for x in itertools.combinations(slot,n//2))
    rng=random.Random(seed)
    interval=sorted(100*(1-math.exp(statistics.fmean(rng.choices(logs,k=n)))) for _ in range(100_000))
    def q(f):
        pos=f*(len(interval)-1);at=int(pos)
        return interval[at]*(1-(pos-at))+interval[at+1]*(pos-at)
    return dict(medians_s={a:statistics.median(v['ns'][a] for v in rows)/1.e9 for a in 'BC'},
        paired_reduction_pct=100*(1-math.exp(statistics.fmean(logs))),ci95=[q(.025),q(.975)],
        favorable=sum(v<0 for v in logs),pairs=n,extreme=extreme,assignments=denom,p_two_sided=extreme/denom)

def analyze(p,rows):
    out={k:endpoint(rows[k],p['orders'][k],p['seeds'][k]) for k in ('selection','cold')}
    running=0
    for i,k in enumerate(sorted(out,key=lambda k:out[k]['p_two_sided'])):
        x=out[k];running=max(running,min(1,(2-i)*x['p_two_sided']));x['holm']=running
        x['qualifies']=running<.05 and x['ci95'][0]>1 and x['favorable']*3>=2*x['pairs']
        x['material_regression']=running<.05 and x['ci95'][1]<-1
    return out
if __name__=='__main__':
    read=lambda s:json.loads(Path(s).read_bytes())
    print(json.dumps(analyze(read(sys.argv[1]),read(sys.argv[2])),sort_keys=True,indent=2))
