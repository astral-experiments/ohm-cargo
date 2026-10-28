"""Summarize the preregistered two-batch experiment on real whole-workspace Cargo wall time."""
import argparse
import json
import math
from pathlib import Path
import random
import statistics

p=argparse.ArgumentParser()
p.add_argument("samples",type=Path)
p.add_argument("--order",type=Path,default=Path(__file__).with_name("order.json"))
ns=p.parse_args()
samples=json.loads(ns.samples.read_bytes())
schedule=json.loads(ns.order.read_bytes())["batches"]
assert len(samples)==len(schedule)==2
groups=[];all_a=[];all_b=[];batches=[]
for batch,orders in zip(samples,schedule,strict=True):
    assert len(orders["order"])==len(batch)==24
    aa=[];bb=[]
    for pair,expected in zip(batch,orders["order"],strict=True):
        assert pair["order"]==expected and set(expected)=={"A","B"} and len(expected)==2
        for slot in ("A","B"):
            call=pair[slot]
            assert call["exit"]==0 and call["units"]==619 and call["wall_ns"]>0
        aa.append(pair["A"]["wall_ns"]/1e9);bb.append(pair["B"]["wall_ns"]/1e9)
    logs=[math.log(b/a) for a,b in zip(aa,bb,strict=True)]
    groups.append(logs);all_a.extend(aa);all_b.extend(bb)
    batches.append({"median_a":statistics.median(aa),"median_b":statistics.median(bb),
                    "paired_reduction":1-math.exp(statistics.mean(logs)),"faster":sum(b<a for a,b in zip(aa,bb))})
rng=random.Random(0x61950)
bootstrap=[]
for _ in range(100000):
    draws=[v for pop in groups for v in rng.choices(pop,k=len(pop))]
    bootstrap.append(1-math.exp(statistics.fmean(draws)))
bootstrap.sort()
ci=[bootstrap[2499],bootstrap[97499]]
logs=sum(groups,[])
non_ties=[v for v in logs if v!=0]
k=min(sum(v<0 for v in non_ties),sum(v>0 for v in non_ties));n=len(non_ties)
p_sign=min(1,2*sum(math.comb(n,i) for i in range(k+1))/2**n) if n else 1
result={"pairs":len(logs),"median_control_seconds":statistics.median(all_a),"median_candidate_seconds":statistics.median(all_b),
        "paired_reduction":1-math.exp(statistics.fmean(logs)),"paired_95pct_interval":ci,"exact_two_sided_sign_p":p_sign,
        "batches":batches,"passes_clock_gate":ci[0]>0 and p_sign<=0.05 and all(b["paired_reduction"]>0 for b in batches)}
print(json.dumps(result,indent=2))
