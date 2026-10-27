"""Estimate two whole-workspace effects with the actual balanced within-direction assignments."""
from itertools import combinations
from pathlib import Path
import bisect
import json
import math
import random
import statistics
import sys

def estimate(rows, seed):
    if len(rows)!=20: raise ValueError('incomplete endpoint')
    results={}
    distributions=[]
    logs_by_direction=[]
    for direction in ('edit','restore'):
        picked=[r for r in rows if r['direction']==direction]
        assert len(picked)==10 and sum(r['order']=='BC' for r in picked)==5
        ratios=[math.log(r['ns']['C']/r['ns']['B']) for r in picked]
        logs_by_direction.append(ratios)
        results[direction]=100*(1-math.exp(statistics.mean(ratios)))
        signed=[v if r['order']=='BC' else -v for r,v in zip(picked,ratios,strict=True)]
        distributions.append(sorted(2*sum(c)-sum(signed) for c in combinations(signed,5)))
    logs=logs_by_direction[0]+logs_by_direction[1]
    x,y=distributions;threshold=abs(sum(logs))
    count=sum(bisect.bisect_right(y,-threshold-a+1e-12)+len(y)-bisect.bisect_left(y,threshold-a-1e-12) for a in x)
    denominator=len(x)*len(y)
    rng=random.Random(seed); draws=[]
    for _ in range(100_000):
        total=sum(sum(rng.choices(period,k=10)) for period in logs_by_direction)
        draws.append(100*(1-math.exp(total/20)))
    draws.sort()
    def q(frac):
        loc=(len(draws)-1)*frac;i=int(loc)
        return draws[i]+(draws[i+1]-draws[i])*(loc-i)
    return dict(medians_s={a:statistics.median(r['ns'][a] for r in rows)/1e9 for a in 'BC'},
        paired_reduction_pct=100*(1-math.exp(statistics.mean(logs))),ci95=[q(.025),q(.975)],proportion_faster=sum(n<0 for n in logs)/20,
        per_direction_pct=results,exact_assignments=denominator,extreme_assignments=min(count,denominator),p=min(count,denominator)/denominator)

def analyze(obs, plan):
    report={}
    for mode in ('build','test'):
        rows=obs[mode]
        assert [{'direction':r['direction'],'order':r['order']} for r in rows]==plan['orders'][mode]
        assert all(set(r['ns'])=={'B','C'} and min(r['ns'].values())>0 for r in rows)
        report[mode]=estimate(rows,plan['bootstrap_seeds'][mode])
    running=0
    for i,m in enumerate(sorted(report,key=lambda m:report[m]['p'])):
        r=report[m];running=max(running,min(1,(2-i)*r['p']));r['holm']=running
        r['passes']=running<.05 and r['ci95'][0]>1.0 and min(r['per_direction_pct'].values())>0
    return report
if __name__=='__main__':
    read=lambda p:json.loads(Path(p).read_bytes())
    print(json.dumps(analyze(read(sys.argv[1]),read(sys.argv[2])),indent=2))
