"""Analyze the twelve registered neighboring checkouts without excluding any pair."""
import argparse
import hashlib
from itertools import combinations
import json
from math import comb, exp, log
from pathlib import Path
from statistics import median

PHASES=("empty-A","first-B","return-A","return-B","unchanged-B")
def sign_p(n,positive):
    return min(1,2*sum(comb(n,k) for k in range(min(positive,n-positive)+1))/2**n)
def interval(values,target):
    values=sorted(values);n=len(values)
    k,coverage=max((k,c) for k in range(1,n//2+1)
                   if (c:=1-2*sum(comb(n,j) for j in range(k))/2**n)>=target)
    return {"order_statistics":[k,n-k+1],"range":[values[k-1],values[n-k]],"marginal_coverage":coverage}
def one(rows,orders):
    ps,qs=zip(*rows)
    ratios=[p/q for p,q in rows]
    chrono=[(log(p)-log(q))*(1 if o[0]=="P" else -1) for (p,q),o in zip(rows,orders)]
    n=len(rows);assert n==12 and sum(o[0]=="P" for o in orders)==6 and min(ps+qs)>0
    observed=abs(sum(d*(1 if o[0]=="P" else -1) for d,o in zip(chrono,orders)))
    hits=0;total=0
    for assignment in combinations(range(n),6):
        s=set(assignment);test=abs(sum((1 if i in s else -1)*x for i,x in enumerate(chrono)))
        hits+=test>=observed-1e-12;total+=1
    assert total==924
    positive=sum(x>2 for x in ratios)
    return {"parent":ps,"candidate":qs,"parent_median":median(ps),"candidate_median":median(qs),"paired_ratios":ratios,
            "paired_differences":[p-q for p,q in rows],"median_ratio":median(ratios),"geometric_mean_ratio":exp(sum(map(log,ratios))/n),
            "marginal95":interval(ratios,.95),"simultaneous_two_endpoints":interval(ratios,.975),"above_one":sum(x>1 for x in ratios),
            "above_two":positive,"equal_two":sum(x==2 for x in ratios),"paired_sign_p_against_two":sign_p(n,positive),
            "randomization_extreme":hits,"randomization_assignments":total,"balanced_randomization_p":hits/total,
            "by_order_median_ratio":{a+"-first":median(q for q,o in zip(ratios,orders) if o[0]==a) for a in ("P","Q")}}
def analyze(raw,schedule):
    slots=raw["slots"];ords=schedule["pairs"]
    ids=[f"n{i:02d}-{a}" for i,o in enumerate(ords,1) for a in o]
    assert list(schedule["order"][2:-2])==ids and set(slots)==set(ids)
    rows={}
    for phase in PHASES:
        def get(slot,k):
            rec=slots[slot][phase]
            if k=="wall_s":return rec["wall_ns"]/1e9
            if k=="cpu_s":return rec["user_s"]+rec["system_s"]
            if k=="with_git_s":return (rec["wall_ns"]+rec["git_ns"])/1e9
            if k=="git_s":return rec["git_ns"]/1e9
            return rec["incremental_allocated_bytes"]
        metrics=["wall_s","cpu_s","incremental_allocated_bytes"]
        if phase in ("first-B","return-A","return-B"): metrics+=["git_s","with_git_s"]
        rows[phase]={m:one([(get(f"n{i:02d}-P",m),get(f"n{i:02d}-Q",m)) for i in range(1,13)],ords) for m in metrics}
    endpoints={step:rows[step]['wall_s'] for step in ['return-A','return-B']}
    gate=all(x["simultaneous_two_endpoints"]["range"][0]>2 and x["balanced_randomization_p"]<.05 and x["paired_sign_p_against_two"]<.05 for x in endpoints.values())
    return {"pairs":12,"schedule":ords,"scope":"whole ordinary Cargo, source switch and tests timed separately","phase_metrics":rows,"both_wall_endpoints_exceed_two":gate}
if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("observations",type=Path);parser.add_argument("schedule",type=Path);args=parser.parse_args()
    result=analyze(json.loads(args.observations.read_bytes()),json.loads(args.schedule.read_bytes()))
    result["observations_sha256"]=hashlib.sha256(args.observations.read_bytes()).hexdigest()
    print(json.dumps(result,sort_keys=True,indent=2))
