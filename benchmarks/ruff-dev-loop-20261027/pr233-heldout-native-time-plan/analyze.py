"""Analyze every registered held-out endpoint on paired process elapsed times."""
from collections import Counter
from itertools import combinations, product
from pathlib import Path
import argparse, json, math, random, statistics

here=Path(__file__).resolve().parent
def evaluate(rows, endpoint_index):
    assert len(rows)==16
    seen=Counter(); ratios=[]; pos={'edit':[],'restore':[]}; by_round={}; b=[];c=[]
    for row in rows:
        direction=row['direction']; seq=row['arms']; times=[row['elapsed_ns'][a]*1e-9 for a in seq]
        assert all(n>0 and math.isfinite(n) for n in times)
        pair=dict(zip(seq,times));lr=math.log(pair['C']/pair['B'])
        seen[direction,seq[1]]+=1;pos[direction].append(math.log(times[1]/times[0]))
        b.append(pair['B']);c.append(pair['C']);ratios.append(lr)
        d=by_round.setdefault(row['block'],{});assert direction not in d;d[direction]=lr
    assert seen=={(direction,arm):4 for direction in pos for arm in 'BC'}
    assert len(by_round)==8 and all(set(r)==set(pos) for r in by_round.values())
    group_mean=[statistics.mean(r.values()) for r in by_round.values()]
    observed=math.fsum(ratios)
    loose=1e-12
    assignments=[]
    for d,g in pos.items():
        total=math.fsum(g)
        assignments.append([2*math.fsum(t)-total for t in combinations(g,4)])
    extremes=sum(abs(math.fsum(pair))+loose>=abs(observed) for pair in product(*assignments))
    reduce=lambda n:100*-math.expm1(n)
    rng=random.Random(2026102701+endpoint_index)
    ci=sorted(reduce(statistics.mean(rng.choices(group_mean,k=8))) for _ in range(20_000))
    return {'parent_median_seconds':statistics.median(b),'fixed_median_seconds':statistics.median(c),'reduction_percent':reduce(observed/16),'block_bootstrap_interval':[ci[499],ci[19500]],'faster_pairs':sum(r<0 for r in ratios),'exact_p':extremes/4900,'extreme_assignments':extremes,'assignments':4900,'median_by_direction':{k:{a:statistics.median(row['elapsed_ns'][a]*1e-9 for row in rows if row['direction']==k) for a in 'BC'} for k in pos}}
def analyze(plan,rows):
    assert len(rows)==len(plan['sequence'])==96
    for r,s in zip(rows,plan['sequence'],strict=True):
        assert all(r[k]==v for k,v in s.items()) and set(r['elapsed_ns'])==set('BC')
    results=[]
    for n,e in enumerate(plan['endpoints']):
        chosen=[r for r in rows if all(r[k]==v for k,v in e.items())]
        results.append(dict(e,**evaluate(chosen,n)))
    prev=0
    for i,entry in enumerate(sorted(results,key=lambda q:q['exact_p'])):
        prev=max(prev,min(1,(6-i)*entry['exact_p']));entry['holm_p']=prev
        entry['qualified_reduction']=prev<.05 and entry['block_bootstrap_interval'][0]>0 and entry['reduction_percent']>0
    return results
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('observations',type=Path);ap.add_argument('--plan',type=Path,default=here/'plan.json')
    a=ap.parse_args()
    print(json.dumps(analyze(json.loads(a.plan.read_bytes()),json.loads(a.observations.read_bytes())),sort_keys=True,indent=2))
