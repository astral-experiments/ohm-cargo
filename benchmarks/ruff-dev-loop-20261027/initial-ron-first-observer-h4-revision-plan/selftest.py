"""Check prospectively fixed estimates, order balance, and both independent safety bounds."""
from pathlib import Path
import json, sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from analyze import analyze

def test(label):
    root=Path(__file__).resolve().parent
    plan=json.loads((root/"plan.json").read_bytes());rows=[]
    for i,order in enumerate(plan["schedule"]["orders"],1):
        for j,a in enumerate(order,1):
            cold=350.0;first=26.0;settled=4.3
            if label=="order":
                multiplier=1+0.10*(j-2);cold*=multiplier;first*=multiplier;settled*=multiplier
            if a=="C" and label in ("effect","cold-harm","settled-harm"):
                first=4.0
                if label=="cold-harm":cold*=1.06
                if label=="settled-harm":settled+=.21
            rows.append(dict(block=i,slot=j,arm=a,cold_ns=round(cold*1e9),first_ns=round(first*1e9),settled_ns=round(settled*1e9)))
    out=analyze(plan,rows)
    assert out["claims_pass"]==(label in ("effect","cold-harm","settled-harm"))
    assert out["floors_pass"]==(label in ("null","effect"))
    assert all(r["balanced_assignments"]==8000 for r in out["rows"])
    vals={r["phase"]+":"+r["control"]:r for r in out["rows"]}
    if label=="null":assert all(r["p_exact_2s"]==1 and r["paired_reduction_pct"]==0 for r in vals.values())
    if label=="order":assert all(abs(r["paired_reduction_pct"])<1e-10 and r["p_exact_2s"]==1 for r in vals.values())
    if label=="effect":assert abs(vals["first:A"]["paired_reduction_pct"]-100*22/26)<1e-8 and vals["first:A"]["at_least_as_extreme"]==2
    result=dict(case=label,claims_pass=out["claims_pass"],floors_pass=out["floors_pass"],first_p=vals["first:A"]["p_exact_2s"],cold_high=vals["cold:A"]["upper_overhead_98_75_pct"],settled_high_ms=vals["settled:A"]["upper_absolute_overhead_98_75_ms"])
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":test(sys.argv[1])
