from itertools import combinations
from math import exp,fsum,log
import random,statistics

def analyze(plan,rows):
    assert len(rows)==12 and [r['order'] for r in rows]==plan['pair_order']
    assert sum(v=='16-17' for v in plan['pair_order'])==6
    logs=[log(r['17']/r['16']) for r in rows];slots=[x if r['order']=='16-17' else -x for x,r in zip(logs,rows,strict=True)]
    observed=abs(fsum(logs));total=fsum(slots)
    ext=sum(abs(2*fsum(c)-total)+1e-12>=observed for c in combinations(slots,6));p=ext/924
    rng=random.Random(plan['bootstrap'])
    samples=sorted(100*(1-exp(fsum(rng.choices(logs,k=12))/12)) for _ in range(100000))
    def quant(frac):
        pos=frac*(len(samples)-1);index=int(pos)
        return samples[index]+(samples[index+1]-samples[index])*(pos-index)
    lo,hi=quant(.025),quant(.975);wins=sum(x<0 for x in logs)
    return dict(pairs=12,medians_s={a:statistics.median(r[a] for r in rows)*1e-9 for a in ('16','17')},reduction_pct=100*(1-exp(fsum(logs)/12)),ci95=[lo,hi],faster=wins,extremes=ext,assignments=924,p=p,qualifies=p<.05 and lo>1. and wins>=10)
