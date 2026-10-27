"""Direction-stratified paired, exactly balanced order assignment with Holm over both commands."""
import itertools,json,math,random,statistics,sys
from collections import Counter
def calc(orders,rows,seed):
    groups=[[],[]];paired=[[],[]];absolute=[[],[]];arms={a:[] for a in 'BC'}
    for i,(order,items) in enumerate(zip(orders,rows,strict=True)):
        assert order in ('BC','CB') and len(items)==2 and all(v>0 for v in items.values())
        ix=i%2;groups[ix].append(math.log(items[order[1]]/items[order[0]]));paired[ix].append(math.log(items['C']/items['B']))
        absolute[ix].append((items['C']-items['B'])*1e-6)
        for a in 'BC':arms[a].append(items[a]*1e-6)
    assert all(len(g)==12 for g in groups) and all(Counter(orders[k::2])=={'BC':6,'CB':6} for k in (0,1))
    sums=[[2*math.fsum(sel)-math.fsum(g) for sel in itertools.combinations(g,6)] for g in groups]
    obs=math.fsum(itertools.chain.from_iterable(paired));n=len(sums[0])*len(sums[1]);assert n==853776
    extreme=sum(abs(x+y)+1e-12>=abs(obs) for x,y in itertools.product(*sums));assert 2<=extreme<=n
    percent=lambda t:100*math.expm1(t)
    rng=random.Random(seed);p=[];dt=[]
    for _ in range(20000):
        ids=[(g,i) for g in (0,1) for i in rng.choices(range(12),k=12)]
        p.append(percent(statistics.fmean(paired[g][i] for g,i in ids)));dt.append(statistics.fmean(absolute[g][i] for g,i in ids))
    p.sort();dt.sort()
    return dict(n=24,median_B_ms=statistics.median(arms['B']),median_C_ms=statistics.median(arms['C']),geometric_mean_overhead_pct=percent(obs/24),mean_overhead_ms=statistics.fmean(itertools.chain.from_iterable(absolute)),ci95_pct=[p[499],p[19500]],ci95_absolute_ms=[dt[499],dt[19500]],upper97_5_pct=p[19500],upper97_5_ms=dt[19500],p_two_sided=extreme/n,extreme=extreme,assignments=n,small_margin_pass=p[19500]<3 and dt[19500]<5)
def analyze(plan,receipts):
    data=receipts['scored'];assert len(data)==96;out={}
    for ix,ep in enumerate(('check','build')):
        observed=[v for v in data if v['kind']==ep];orders=[];pairs=[]
        for i,entry in enumerate(plan['schedule']):
            pair=observed[2*i:2*i+2];order=entry[ep];assert len(pair)==2 and [x['arm'] for x in pair]==list(order)
            assert all(x['block']==i+1 and x['slot']==j and x['direction']==entry['direction'] for j,x in enumerate(pair,1))
            orders.append(order);pairs.append({x['arm']:x['receipt']['elapsed_ns'] for x in pair})
        out[ep]=calc(orders,pairs,2026102701+ix)
    p=0.
    for i,r in enumerate(sorted(out.values(),key=lambda v:v['p_two_sided'])):
        p=max(p,min(1,(2-i)*r['p_two_sided']));r['holm_p']=p
        r['slower']=p<.05 and r['ci95_pct'][0]>0
        r['faster']=p<.05 and r['ci95_pct'][1]<0
    return out
if __name__=='__main__':
    from pathlib import Path
    out=analyze(json.loads(Path(sys.argv[1]).read_bytes()),json.loads(Path(sys.argv[2]).read_bytes()));print(json.dumps(out,indent=2))
