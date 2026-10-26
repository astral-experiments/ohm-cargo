#!/usr/bin/env python3
"""Recompute paired estimates, exact two-sided sign tests and balanced-order randomization tests."""
import collections
import csv
import itertools
import json
import math
from pathlib import Path
import statistics


def evaluate(pairs):
    a=[int(p['A']['wall_ns'])/1e9 for p in pairs];b=[int(p['B']['wall_ns'])/1e9 for p in pairs]
    k=len(pairs);orders=[p['A']['order'] for p in pairs]
    assert all(p['A']['order']==p['B']['order'] for p in pairs)
    assert orders.count('AB')==orders.count('BA')==k//2
    signed=[math.log(x/y) for x,y in zip(a,b)];chronology=[d if order=='AB' else -d for d,order in zip(signed,orders)]
    allocations=list(itertools.combinations(range(k),k//2)); observed=abs(sum(signed))
    extremes=sum(abs(sum(x if i in first else -x for i,x in enumerate(chronology)))>=observed-1e-10 for first in allocations)
    wins=sum(x>y for x,y in zip(a,b));effects=[100*(1-y/x) for x,y in zip(a,b)]
    return {'pairs':k,'medians_seconds':[statistics.median(a),statistics.median(b)],'paired_reduction_percent':statistics.median(effects),'range_paired_reduction_percent':[min(effects),max(effects)],'wins':wins,'two_sided_sign_p':min(1,2*sum(math.comb(k,i) for i in range(min(wins,k-wins)+1))/2**k),'order_conditional_exact_p':extremes/len(allocations),'extreme_order_allocations':extremes,'total_order_allocations':len(allocations)}


def main():
    root=Path(__file__).resolve().parent;groups=collections.defaultdict(lambda:collections.defaultdict(dict))
    for row in csv.DictReader((root/'observations.csv').open()):
        if row['cohort']=='neutral':continue
        key=row['cohort'],row['fixture'];trial=groups[key][int(row['pair'])];assert row['arm'] not in trial;trial[row['arm']]=row
    result={}
    for (cohort,fixture),group in groups.items():result.setdefault(cohort,{})[fixture]=evaluate([group[k] for k in sorted(group)])
    for cases in result.values():
        assert set(cases)=={'discovery','adjacent'}
        for metric in ['two_sided_sign_p','order_conditional_exact_p']:
            highest=0
            for i,case in enumerate(sorted(cases,key=lambda key:cases[key][metric])):
                highest=max(highest,(2-i)*cases[case][metric]);cases[case][metric+'_holm_two_fixtures']=min(1,highest)
    assert result==json.loads((root/'statistics.json').read_text());print(json.dumps(result,indent=2))

if __name__=='__main__':main()
