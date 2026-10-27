"""Analyze balanced randomized pairs of complete Ruff commands, grouped by registered endpoint."""
import argparse
import csv
import itertools
import json
import math
from pathlib import Path
import random
import statistics

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('results',nargs='+',type=Path)
args=parser.parse_args()


def analyze(directory):
    plan=json.loads((directory/'plan.json').read_bytes())
    assert json.loads((directory/'complete.json').read_bytes())['source_clean']
    rows=list(csv.DictReader((directory/'observations.csv').open()))
    pairs=len(plan['orders']);assert pairs==12 and len(rows)==2*pairs
    ratios=[];position_differences=[];parent=[];candidate=[]
    for index,order in enumerate(plan['orders'],1):
        events=[r for r in rows if int(r['pair'])==index]
        assert [r['arm'] for r in events]==order and all(r['order']=='/'.join(order) for r in events)
        elapsed=[int(r['elapsed_ns'])*1e-9 for r in events]
        values=dict(zip(order,elapsed));parent.append(values['parent']);candidate.append(values['candidate'])
        ratios.append(math.log(values['candidate']/values['parent']))
        position_differences.append(math.log(elapsed[1]/elapsed[0]))
        for arm in order:
            assert not json.loads((directory/f'{arm}-pair-{index:02}-edit-fresh/receipt.json').read_bytes())['dirty']
    observed=statistics.mean(ratios)
    first=sum(order[0]=='parent' for order in plan['orders']);assert 2*first==pairs
    extremes=0;assignments=0
    for selected in itertools.combinations(range(pairs),first):
        treatment_second=set(selected)
        permuted=statistics.mean(d if i in treatment_second else -d for i,d in enumerate(position_differences))
        extremes+=abs(permuted)+1e-12>=abs(observed);assignments+=1
    rng=random.Random(831361);replicates=sorted(100*(1-math.exp(statistics.mean(rng.choices(ratios,k=pairs)))) for _ in range(20000))
    runs={arm:[] for arm in ['parent','candidate']}
    for arm in runs:
        for phase in ('verify-edit','verify-final-edit'):
            receipt=json.loads((directory/f'{arm}-{phase}/receipt.json').read_bytes())
            runs[arm].append({k:receipt.get(k) for k in ('processes','wild_events','full_links','roster_sha','parser_diagnostics')})
    return dict(endpoint=directory.name,pairs=pairs,parent_median_s=statistics.median(parent),candidate_median_s=statistics.median(candidate),
                geometric_elapsed_reduction_pct=100*(1-math.exp(observed)),paired_bootstrap_95_pct=[replicates[499],replicates[19500]],
                faster_pairs=sum(r<0 for r in ratios),order_balanced_exact_two_sided_p=extremes/assignments,assignments=assignments,qualification=runs)


reports=[analyze(p) for p in args.results]
by_p=sorted(reports,key=lambda r:r['order_balanced_exact_two_sided_p']);last=0
for rank,report in enumerate(by_p):
    adjusted=min(1,max(last,(len(reports)-rank)*report['order_balanced_exact_two_sided_p']))
    report['holm_p_across_submitted_endpoints']=adjusted;last=adjusted
print(json.dumps(reports,indent=2))
