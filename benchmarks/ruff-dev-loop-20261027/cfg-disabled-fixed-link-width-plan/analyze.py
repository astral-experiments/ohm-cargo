"""Evaluate the two marginal effects of a guarded compiler and Cargo on complete Ruff commands."""
import argparse
from collections import Counter
import csv
from itertools import combinations, permutations, product
import json
import math
from pathlib import Path
import random
import statistics


def load_blocks(path, orders):
    with path.open(newline='') as stream:
        rows=list(csv.DictReader(stream))
    assert len(orders)==18 and len(rows)==54
    assert Counter(map(tuple,orders))=={p:3 for p in permutations('ABC')}
    blocks=[]
    for i,order in enumerate(orders,1):
        group=rows[(i-1)*3:i*3]
        assert [r['arm'] for r in group]==list(order)
        assert all(int(r['block'])==i and int(r['slot'])==j for j,r in enumerate(group,1))
        block={r['arm']:int(r['elapsed_ns'])*1e-9 for r in group}
        assert all(t>0 and math.isfinite(t) for t in block.values())
        blocks.append(block)
    return blocks


def evaluate(orders, blocks, control, seed, candidate='C'):
    third=next(iter(set('ABC')-{control,candidate}))
    pos_deltas=[[] for _ in range(3)]
    late=Counter()
    ratios=[]
    for order,block in zip(orders,blocks,strict=True):
        third_slot=order.index(third)
        early,late_arm=[a for a in order if a!=third]
        pos_deltas[third_slot].append(math.log(block[late_arm]/block[early]))
        late[third_slot]+=int(late_arm==candidate)
        ratios.append(math.log(block[candidate]/block[control]))
    assert late=={0:3,1:3,2:3} and [len(g) for g in pos_deltas]==[6,6,6]
    exact=[]
    for group in pos_deltas:
        total=math.fsum(group)
        exact.append([2*math.fsum(chosen)-total for chosen in combinations(group,3)])
    observed=math.fsum(ratios)
    tails=sum(abs(math.fsum(parts))+1e-12>=abs(observed) for parts in product(*exact))
    rng=random.Random(seed)
    reduce=lambda xs:100*-math.expm1(statistics.mean(xs))
    samples=sorted(reduce(rng.choices(ratios,k=18)) for _ in range(20_000))
    return {'control_arm':control,'candidate_arm':'C','held_arm':third,'blocks':len(blocks),
            'control_median_s':statistics.median(b[control] for b in blocks),
            'candidate_median_s':statistics.median(b[candidate] for b in blocks),
            'geometric_elapsed_reduction_pct':reduce(ratios),'paired_bootstrap_95_pct':[samples[499],samples[19500]],
            'candidate_faster_blocks':sum(v<0 for v in ratios),'balanced_assignments':8000,
            'as_or_more_extreme':tails,'exact_two_sided_p':tails/8000}


def holm(rows):
    last=0.0
    for i,r in enumerate(sorted(rows,key=lambda r:r['exact_two_sided_p'])):
        last=max(last,min(1,(len(rows)-i)*r['exact_two_sided_p']))
        r['holm_p']=last
        r['qualified_wall_reduction']=r['paired_bootstrap_95_pct'][0]>0 and last<.05


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data',type=Path,help='Directory containing <endpoint>.csv for each registered endpoint.')
    args=parser.parse_args()
    plan=json.loads((Path(__file__).resolve().parent/'fixed-width-plan.json').read_bytes())
    primary=[];descriptive=[]
    for n,endpoint in enumerate((*plan['primary_endpoints'],'no-op')):
        orders=plan['orders'][endpoint];blocks=load_blocks(args.data/(endpoint+'.csv'),orders)
        for k,candidate,control in [('total','C','A'),('reuse','C','B'),('support-cost','B','A')]:
            row={'endpoint':endpoint,'contrast':candidate+':'+control,**evaluate(orders,blocks,control,20261027+3*n+ord(control),candidate)}
            (primary if k!='support-cost' and endpoint!='no-op' else descriptive).append(row)
    holm(primary)
    print(json.dumps({'primary':primary,'descriptive':descriptive},indent=2))

if __name__=='__main__':main()
