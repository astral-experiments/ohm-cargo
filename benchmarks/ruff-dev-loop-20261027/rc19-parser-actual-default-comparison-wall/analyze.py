import argparse
from itertools import combinations
import json
import math
from pathlib import Path
import random
import statistics

def percentile(x,f):
    xs=sorted(x);k=(len(xs)-1)*f;lo=int(k);hi=math.ceil(k);return xs[lo]+(xs[hi]-xs[lo])*(k-lo)
def summarize(raw,orders,seed,draws):
    assert len(raw)==len(orders) and len(raw)%2==0 and sorted(orders)==['FR']*(len(raw)//2)+['RF']*(len(raw)//2)
    r=[pair['R'] for pair in raw];f=[pair['F'] for pair in raw];delta=[math.log(b/a) for a,b in zip(r,f)];observed=statistics.median(delta)
    gen=random.Random(seed);distribution=[statistics.median(gen.choices(delta,k=len(delta))) for _ in range(draws)]
    med_by_order={z:100*math.expm1(statistics.median(d for d,o in zip(delta,orders) if o==z)) for z in sorted(set(orders))}
    chronology=[math.log(row[o[1]]/row[o[0]]) for row,o in zip(raw,orders)]
    hits=0;tests=0
    for choose in combinations(range(len(orders)),len(orders)//2):
        after=set(choose);null=statistics.median([d if j in after else -d for j,d in enumerate(chronology)])
        hits+=abs(null)>=abs(observed)-1e-12;tests+=1
    return dict(pairs=len(raw),cached_median_seconds=statistics.median(r)/1e9,full_median_seconds=statistics.median(f)/1e9,
                paired_delta_seconds=statistics.median(b-a for a,b in zip(r,f))/1e9,
                paired_full_cost_percent=100*math.expm1(observed),lower95=100*math.expm1(percentile(distribution,.025)),
                upper95=100*math.expm1(percentile(distribution,.975)),slower_pairs=sum(b>a for a,b in zip(r,f)),
                same_pairs=sum(b==a for a,b in zip(r,f)),two_sided_balanced_p=hits/tests,
                permutation_count=tests,order_strata_percent=med_by_order)
def self_checks():
    orders=['RF','FR']*6
    null=summarize([{'R':10000,'F':10000} for _ in orders],orders,2,100);assert null['two_sided_balanced_p']==1 and null['paired_full_cost_percent']==0
    tied=summarize([{'R':10000,'F':14000} for _ in orders],orders,2,100);assert abs(tied['lower95']-40)<1e-9 and tied['two_sided_balanced_p']==524/924
    effect=summarize([{'R':10000,'F':14000+20*j} for j in range(12)],orders,2,100);assert effect['lower95']>=40 and effect['two_sided_balanced_p']==20/924 and effect['slower_pairs']==12
    drift=summarize([({'R':10000,'F':13000} if o=='RF' else {'R':13000,'F':10000}) for o in orders],orders,2,100);assert abs(drift['paired_full_cost_percent'])<1e-9 and drift['two_sided_balanced_p']==1
    return {x:y['two_sided_balanced_p'] for x,y in (('null',null),('known_effect',effect),('constant_ties',tied),('slot_only',drift))}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--selftest',action='store_true');ap.add_argument('--directory',type=Path,default=Path(__file__).resolve().parent);a=ap.parse_args()
    if a.selftest:print(json.dumps(self_checks(),sort_keys=True));return
    d=a.directory;plan=json.loads((d/'plan.json').read_bytes());term=json.loads((d/'wall-terminal.json').read_bytes());assert term['pairs']==12
    import hashlib
    digest=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
    for k,h in term['evidence'].items():assert digest(d/'wall'/k)==h,k
    rows=[]
    for idx,order in enumerate(plan['orders'],1):
        x={}
        for z in 'RF':
            nu=d/'wall'/f'{idx:02d}-edit'/z;clock=json.loads((nu/'clock.json').read_bytes());assert clock['exit']==0 and clock['elapsed']==clock['end']-clock['start']>0
            post=json.loads((nu/'post.json').read_bytes());assert post['cargo_rc']==0 and post['typed_fresh']==147
            assert min(json.loads((nu/'quiet.json').read_bytes())['idle'].values())>=.85
            assert post['products']['fixtures']['listed']==557 and post['products']['generate_inline_tests']['listed']==1
            reset=json.loads((d/'wall'/f'{idx:02d}-reset'/z/'post.json').read_bytes());assert reset['products']['fixtures']['listed']==558 and reset['typed_fresh']==147
            x[z]=clock
        assert x[order[0]]['end']<=x[order[1]]['start'];rows.append({z:x[z]['elapsed'] for z in 'RF'})
    result=summarize(rows,plan['orders'],plan['bootstrap_seed'],plan['bootstrap_draws']);result['raw_ns']=rows;result['synthetic']=self_checks();print(json.dumps(result,indent=2,sort_keys=True))
if __name__=='__main__':main()
