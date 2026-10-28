"""Paired geometric effects, direction-stratified uncertainty and full balanced order randomization."""
from itertools import combinations,product
from math import comb,exp,fsum,log
import random,statistics

def endpoint(rows,seed):
    strata={}
    for row in rows:strata.setdefault(row['direction'],[]).append(row)
    groups=list(strata.values())
    assert [len(g) for g in groups] in ([24],[12,12])
    assert all(sum(r['order']=='BC' for r in g)==len(g)//2 for g in groups)
    logs=[[log(r['c']/r['b']) for r in g] for g in groups];all_logs=[v for group in logs for v in group]
    pool=[]
    for g,vals in zip(groups,logs,strict=True):
        slots=[x if r['order']=='BC' else -x for r,x in zip(g,vals,strict=True)]
        total=fsum(slots);half=len(g)//2
        pool.append((slots,total,half))
    threshold=abs(fsum(all_logs))
    if len(pool)==1:
        slots,total,half=pool[0];extreme=sum(abs(2*fsum(xs)-total)+1e-12>=threshold for xs in combinations(slots,half))
    else:
        marg=[[2*fsum(xs)-total for xs in combinations(slots,half)] for slots,total,half in pool]
        extreme=sum(abs(x+y)+1e-12>=threshold for x,y in product(*marg))
    assignments=1
    for g in groups:assignments*=comb(len(g),len(g)//2)
    rng=random.Random(seed);n=len(all_logs);b=[]
    for _ in range(100_000):
        mean=fsum(fsum(rng.choices(g,k=len(g))) for g in logs)/n;b.append(100*(1-exp(mean)))
    b.sort()
    def quant(x):
        pos=x*(len(b)-1);idx=int(pos);frac=pos-idx
        return b[idx]+frac*(b[idx+1]-b[idx])
    return dict(n=n,medians_s={a:statistics.median(r[a] for r in rows)*1e-9 for a in ('b','c')},pairs_faster=sum(v<0 for v in all_logs),
                reduction_pct=100*(1-exp(fsum(all_logs)/n)),ci95=[quant(.025),quant(.975)],
                extremes=extreme,assignments=assignments,p=extreme/assignments)
def analyze(plan,ledger):
    out={k:endpoint(series,plan['bootstrap'][k]) for k,series in ledger.items()}
    assert set(out)=={'edit','first_unchanged','edit_plus_first','project_unchanged'}
    previous=0
    for i,k in enumerate(sorted(out,key=lambda k:out[k]['p'])):
        a=out[k];previous=max(previous,min(1,(len(out)-i)*a['p']));a['holm']=previous
        a['qualifies']=previous<.05 and a['ci95'][0]>1. and a['pairs_faster']>=16
        a['material_regression']=previous<.05 and a['ci95'][1]<-1.
    return out
