"""Audit exact registered input rows; calculate the 36 conditional randomization assignments."""
import csv,itertools,json,math,statistics,sys
from pathlib import Path
root=Path(__file__).resolve().parent
def analyze(rows,pairs):
    group=[{} for _ in pairs]
    for r in rows:
        i=int(r['pair'])-1;s=int(r['slot'])-1;a=r['arm'];n=int(r['elapsed_ns'])
        assert 0<=i<len(pairs) and s in (0,1) and a==pairs[i]['order'][s] and r['direction']==pairs[i]['direction'] and n>0 and s not in group[i]
        group[i][s]=(a,n)
    assert all(len(g)==2 for g in group)
    differences=[math.log(g[0][1]/g[1][1]) for g in group]
    signs=[1 if g[0][0]=='C' else -1 for g in group]
    pairs_log=[d*s for d,s in zip(differences,signs)];observed=statistics.mean(pairs_log)
    perms=[]
    for pos in itertools.product(*(list(itertools.combinations(range(k,len(group),2),2)) for k in (0,1))):
        plus=set(itertools.chain.from_iterable(pos));perms.append(statistics.mean(d if i in plus else -d for i,d in enumerate(differences)))
    assert len(perms)==36
    p=sum(abs(x)>=abs(observed)-1e-14 for x in perms)/len(perms)
    sec={a:statistics.median(n/1e9 for g in group for b,n in g.values() if a==b) for a in 'AC'}
    return {'executor_median_seconds':sec,'C_faster':sum(x<0 for x in pairs_log),'geometric_C_speedup_as_percent_time_saved':100*(1-math.exp(observed)),'paired_median_percent_time_saved':statistics.median(100*(1-math.exp(x)) for x in pairs_log),'assignments':len(perms),'two_sided_p':p}
if __name__=='__main__':
    p=json.loads((root/'plan.json').read_bytes())
    if sys.argv[1:]==['--self-test']:
        pairs=p['schedule']['parser'];rows=[{'pair':z['pair'],'slot':i+1,'arm':a,'elapsed_ns':100 if a=='A' else 80,'direction':z['direction']} for z in pairs for i,a in enumerate(z['order'])]
        t=analyze(rows,pairs);assert t['C_faster']==8 and abs(t['geometric_C_speedup_as_percent_time_saved']-20)<1e-9 and t['two_sided_p']==2/36
        for row in rows:row['elapsed_ns']=100
        t=analyze(rows,pairs);assert t['two_sided_p']==1 and t['geometric_C_speedup_as_percent_time_saved']==0
        print('8/8 known 20% and exact null passed across 36 admissible assignments')
    else:
        with Path(sys.argv[1]).open() as f:rows=list(csv.DictReader(f))
        assert len(rows)==32
        result={ed:analyze([r for r in rows if r['endpoint']==ed],p['schedule'][ed]) for ed in p['endpoint_order']}
        effects=[r['geometric_C_speedup_as_percent_time_saved'] for r in result.values()]
        result['wall_advance_gate']=any(r['C_faster']>=6 and e>=1 for r,e in zip(result.values(),effects)) and min(effects)>=-2
        print(json.dumps(result,indent=2))
