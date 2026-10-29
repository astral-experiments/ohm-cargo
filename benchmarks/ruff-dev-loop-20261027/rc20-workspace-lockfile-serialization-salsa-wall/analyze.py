"""Analyze every closed pair with the prespecified direction/order-stratified bootstrap."""
from collections import Counter
from itertools import product
import math, random, statistics
def median(xs):return statistics.median(xs)
def percentile(xs,p):
    x=p*(len(xs)-1);i=math.floor(x);return xs[i]+(xs[min(i+1,len(xs)-1)]-xs[i])*(x-i)
def signs(diffs):
    n=sum(d!=0 for d in diffs);w=sum(d>0 for d in diffs);k=min(w,n-w)
    return min(1.,2*sum(math.comb(n,j)for j in range(k+1))/2**n)
def summary(rows):
    av=[r['A']for r in rows];bv=[r['B']for r in rows];ds=[a-b for a,b in zip(av,bv)];rs=[100*d/a for d,a in zip(ds,av)]
    return dict(pairs=len(rows),A_median_ns=median(av),B_median_ns=median(bv),paired_median_saved_ms=median(ds)/1e6,paired_median_saved_pct=median(rs),candidate_faster=sum(d>0 for d in ds),ties=ds.count(0),p_sign=signs(ds))
def calculate(pairs,plan):
    out={};sums={}
    for j,k in enumerate(('edit','repeat','combined')):
        rows=[]
        for p in pairs:
            r={f:p[f]for f in ('pair','order','direction')}
            for a in 'AB':
                arm=p['arms'][a];r[a]=arm['edit']['ns']+arm['repeat']['ns'] if k=='combined' else arm[k]['ns']
            r['saved_pct']=100*(r['A']-r['B'])/r['A'];r['saved_ms']=(r['A']-r['B'])/1e6;rows.append(r)
        s=summary(rows);rng=random.Random(plan['interval_seed']+j);groups=[[r for r in rows if r['direction']==d and r['order']==o]for d,o in product(('reverse','restore'),('AB','BA'))]
        assert [len(g)for g in groups]==[8]*4
        boot_pct=[];boot_ms=[]
        for _ in range(plan['bounds']['bootstrap']):
            sample=[r for g in groups for r in rng.choices(g,k=8)]
            boot_pct.append(median([r['saved_pct'] for r in sample]));boot_ms.append(median([r['saved_ms']for r in sample]))
        s['ci95_pct']=[percentile(sorted(boot_pct),p)for p in (.025,.975)]
        s['ci95_ms']=[percentile(sorted(boot_ms),p)for p in (.025,.975)]
        s['direction']={d:summary([r for r in rows if r['direction']==d])for d in ('reverse','restore')}
        s['order']={o:summary([r for r in rows if r['order']==o])for o in ('AB','BA')}
        s['four_way']={g[0]['direction']+'-'+g[0]['order']:summary(g)for g in groups}
        s['most_adverse_percent']=min(rows,key=lambda r:r['saved_pct']);s['most_adverse_ms']=min(rows,key=lambda r:r['saved_ms']);s['largest_reduction_pct']=max(rows,key=lambda r:r['saved_pct'])
        out[k]=s
    prev=0
    for i,k in enumerate(sorted(out,key=lambda k:out[k]['p_sign'])):
        prev=max(prev,min(1,(3-i)*out[k]['p_sign']));out[k]['p_holm']=prev
    return dict(endpoints=out,passes_combined_gate=out['combined']['ci95_pct'][0]>0 and out['combined']['p_holm']<.05)
