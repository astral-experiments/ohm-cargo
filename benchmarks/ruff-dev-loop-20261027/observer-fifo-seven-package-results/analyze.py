"""Analyze both commands from the registered 12 balanced pairs using all command observations."""
from itertools import combinations
import json
import math
from pathlib import Path
import random
import statistics
import sys

def analyze(rows, plan):
    outcomes={}
    schedule=plan["orders"]
    for phase,key in (("noop","no_op"),("edit","edit_order")):
        p,c,chronological=[],[],[]
        for item in schedule:
            i=item["block"]
            zs={s:rows[f"native-{i:02d}-{phase}-{s}"]["ns"] for s in "PC"}
            assert all(x>0 for x in zs.values())
            p.append(zs["P"]); c.append(zs["C"])
            first,second=item[key]
            chronological.append(math.log(zs[first]/zs[second]))
        ratios=[math.log(x/y) for x,y in zip(p,c,strict=True)]
        avg=statistics.mean(ratios)
        obs=abs(sum(ratios))
        nulls=[abs(sum((1 if i in ids else -1)*x for i,x in enumerate(chronological)))
               for ids in combinations(range(12),6)]
        assert len(nulls)==924 and sum(item[key]=="PC" for item in schedule)==6
        value=lambda x:-100*math.expm1(-x)
        rng=random.Random(plan["bootstrap_seeds"][phase])
        sims=sorted(value(statistics.mean(rng.choices(ratios,k=12))) for _ in range(20000))
        outcomes[phase]={"median_ms":{"parent":statistics.median(p)/1e6,"candidate":statistics.median(c)/1e6},
                         "paired_reduction_pct":value(avg),"paired_bootstrap_95_pct":[sims[499],sims[19499]],
                         "faster_pairs":sum(x<y for x,y in zip(c,p,strict=True)),
                         "raw_two_sided_p":sum(x>=obs-1e-12 for x in nulls)/len(nulls)}
    order=sorted(outcomes,key=lambda k:outcomes[k]["raw_two_sided_p"])
    previous=0
    for i,k in enumerate(order):
        previous=max(previous,min(1,(2-i)*outcomes[k]["raw_two_sided_p"]))
        outcomes[k]["holm_two_sided_p"]=previous
    return outcomes

if __name__=="__main__":
    p=Path(__file__).resolve().parent
    rows={r["phase"]:r for r in json.loads((p/"commands.json").read_bytes())}
    print(json.dumps(analyze(rows,json.loads((p/"plan.json").read_bytes())),indent=2))
