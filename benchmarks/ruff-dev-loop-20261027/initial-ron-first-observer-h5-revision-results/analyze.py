"""Balanced two-arm randomization test for a second host, conditional on six candidate-late slots."""
from pathlib import Path
from itertools import combinations
import argparse,csv,json,math,random,statistics
def analyze(plan,rows):
    orders=plan["schedule"]["orders"];assert sorted(orders)==["CD"]*6+["DC"]*6 and len(rows)==24
    f={k:[] for k in ("cold","first","settled","cold_plus_first")}
    for i,order in enumerate(orders,1):
        pair=rows[2*i-2:2*i]
        assert [x["arm"] for x in pair]==list(order) and all(int(x["block"])==i and int(x["slot"])==j for j,x in enumerate(pair,1))
        for k in f:
            t={x["arm"]:(int(x["cold_ns"])+int(x["first_ns"]) if k=="cold_plus_first" else int(x[k+"_ns"]))/1e9 for x in pair}
            assert all(v>0 and math.isfinite(v) for v in t.values());f[k].append(t)
    reports=[]
    for i,(phase,blocks) in enumerate(f.items()):
        ordered=[math.log(b[o[1]]/b[o[0]]) for o,b in zip(orders,blocks,strict=True)]
        ratios=[math.log(b["C"]/b["D"]) for b in blocks];obs=math.fsum(ratios);total=math.fsum(ordered)
        extreme=sum(abs(2*math.fsum(sel)-total)+1e-12>=abs(obs) for sel in combinations(ordered,6));assert extreme>=2
        gmr=lambda a:100*math.expm1(statistics.fmean(a));rng=random.Random(202610274100+i);samples=[];diffs=[];absolute=[b["C"]-b["D"] for b in blocks]
        for _ in range(20000):
            ids=rng.choices(range(12),k=12);samples.append(gmr(ratios[j] for j in ids));diffs.append(statistics.fmean(absolute[j] for j in ids))
        samples.sort();diffs.sort();h=samples[19750];a=1000*diffs[19750]
        z={"phase":phase,"control":"D","candidate":"C","n":12,"geomean_reduction_pct":-gmr(ratios),"lower_upper_95_reduction_pct":[-samples[19500],-samples[499]],"upper_98_75_overhead_pct":h,"upper_98_75_absolute_overhead_ms":a,"median_control_s":statistics.median(b["D"] for b in blocks),"median_candidate_s":statistics.median(b["C"] for b in blocks),"faster_pairs":sum(x<0 for x in ratios),"exact_two_sided_p":extreme/924,"balanced_assignments":924,"at_least_as_extreme":extreme}
        if phase=="cold":z["safety_pass"]=h<3
        if phase=="settled":z["safety_pass"]=h<5 and a<100
        reports.append(z)
    tests=[x for x in reports if x["phase"] in ("first","cold_plus_first")];adjusted=0
    for j,x in enumerate(sorted(tests,key=lambda x:x["exact_two_sided_p"])):
        adjusted=max(adjusted,min(1,(2-j)*x["exact_two_sided_p"]));x.update(holm_p=adjusted,claim_pass=adjusted<.05 and x["lower_upper_95_reduction_pct"][0]>0)
    return {"rows":reports,"claims_pass":all(x["claim_pass"] for x in tests),"floors_pass":all(x["safety_pass"] for x in reports if "safety_pass" in x)}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("plan",type=Path);p.add_argument("times",type=Path);a=p.parse_args()
    with a.times.open(newline="") as f:print(json.dumps(analyze(json.loads(a.plan.read_bytes()),list(csv.DictReader(f))),indent=2))
