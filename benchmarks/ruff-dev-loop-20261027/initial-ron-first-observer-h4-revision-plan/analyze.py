"""Exact three-arm marginal estimates for first unchanged, cold+first, and two safety floors."""
from collections import Counter
from itertools import combinations,permutations,product
from pathlib import Path
import argparse,csv,json,math,random,statistics

def calculate(orders,blocks,control,seed):
    third="B" if control=="A" else "A"
    ratios=[math.log(row["C"]/row[control]) for row in blocks]
    groups=[[] for _ in range(3)];late=Counter()
    for order,b in zip(orders,blocks,strict=True):
        pos=order.index(third);first,last=[a for a in order if a!=third]
        groups[pos].append(math.log(b[last]/b[first]));late[pos]+=last=="C"
    assert late=={0:3,1:3,2:3} and list(map(len,groups))==[6,6,6]
    alternatives=[[2*math.fsum(x)-math.fsum(g) for x in combinations(g,3)] for g in groups]
    obs=math.fsum(ratios);extreme=sum(abs(math.fsum(t))+1e-12>=abs(obs) for t in product(*alternatives))
    gmr=lambda r:100*math.expm1(statistics.mean(r))
    rng=random.Random(seed)
    absolute=[b["C"]-b[control] for b in blocks]
    samples=[];diffs=[]
    for _ in range(20000):
        sel=rng.choices(range(18),k=18);samples.append(gmr([ratios[j] for j in sel]));diffs.append(statistics.mean(absolute[j] for j in sel))
    samples.sort();diffs.sort()
    return {"control":control,"candidate":"C","median_control_s":statistics.median(b[control] for b in blocks),"median_candidate_s":statistics.median(b["C"] for b in blocks),"paired_reduction_pct":-gmr(ratios),"bootstrap_95_reduction_pct":[-samples[19500],-samples[499]],"upper_overhead_98_75_pct":samples[19750],"upper_absolute_overhead_98_75_ms":1000*diffs[19750],"faster_blocks":sum(x<0 for x in ratios),"n":18,"balanced_assignments":8000,"at_least_as_extreme":extreme,"p_exact_2s":extreme/8000}
def analyze(plan,rows):
    orders=plan["schedule"]["orders"];assert Counter(map(tuple,orders))=={a:3 for a in permutations("ABC")} and len(rows)==54
    ts={}
    for phase in ("cold","first","settled","cold_plus_first"):ts[phase]=[]
    for i,order in enumerate(orders,1):
        group=rows[(i-1)*3:i*3];assert ([r["arm"] for r in group]==list(order) and all(int(r["block"])==i and int(r["slot"])==j for j,r in enumerate(group,1)))
        for phase in ts:
            b={r["arm"]:(int(r["cold_ns"])+int(r["first_ns"]) if phase=="cold_plus_first" else int(r[phase+"_ns"]))*1e-9 for r in group};assert all(v>0 and math.isfinite(v) for v in b.values());ts[phase].append(b)
    rows=[dict(phase=k,**calculate(orders,v,c,271026055+i*27+ord(c))) for i,(k,v) in enumerate(ts.items()) for c in ("A","B")]
    tests=[r for r in rows if r["phase"] in ("first","cold_plus_first")];p=0.
    for i,r in enumerate(sorted(tests,key=lambda d:d["p_exact_2s"])):
        p=max(p,min(1,(len(tests)-i)*r["p_exact_2s"]));r["holm_p"]=p;r["qualified"]=p<.05 and r["bootstrap_95_reduction_pct"][0]>0
    for r in rows:
        if r["phase"]=="cold":r["safety_pass"]=r["upper_overhead_98_75_pct"]<3
        if r["phase"]=="settled":r["safety_pass"]=r["upper_overhead_98_75_pct"]<5 and r["upper_absolute_overhead_98_75_ms"]<100
    return {"claims_pass":all(r["qualified"] for r in tests),"floors_pass":all(r["safety_pass"] for r in rows if "safety_pass" in r),"rows":rows}
if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("plan",type=Path);a.add_argument("times",type=Path);c=a.parse_args()
    with c.times.open(newline="") as f:obs=list(csv.DictReader(f))
    print(json.dumps(analyze(json.loads(c.plan.read_bytes()),obs),indent=2))
