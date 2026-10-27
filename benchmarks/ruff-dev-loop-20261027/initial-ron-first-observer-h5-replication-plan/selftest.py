from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parent))
from analyze import analyze
p=json.loads((Path(__file__).with_name("plan.json")).read_bytes())
for case in ("null","order","true","cold-harm","settled-harm"):
    rows=[]
    for i,o in enumerate(p["schedule"]["orders"],1):
        for j,arm in enumerate(o,1):
            mul=1+.12*(j-1) if case=="order" else 1
            cold=350*mul;first=25*mul;settled=4.0*mul
            if case in ("true","cold-harm","settled-harm") and arm=="C":
                first=4
                if case=="cold-harm":cold*=1.06
                if case=="settled-harm":settled+=.17
            rows.append(dict(block=i,slot=j,arm=arm,cold_ns=round(cold*1e9),first_ns=round(first*1e9),settled_ns=round(settled*1e9)))
    result=analyze(p,rows);r={x["phase"]:x for x in result["rows"]}
    # The 6% cold regression cancels the whole composite, even though the first command improves.
    assert result["claims_pass"]==(case in ("true","settled-harm")) and result["floors_pass"]==(case in ("null","true"))
    if case in ("null","order"):assert all(x["exact_two_sided_p"]==1 for x in r.values())
    if case=="true":assert r["first"]["at_least_as_extreme"]==2 and abs(r["first"]["geomean_reduction_pct"]-84)<.0001
    print(json.dumps(dict(case=case,claims=result["claims_pass"],floors=result["floors_pass"],first_extreme=r["first"]["at_least_as_extreme"]),sort_keys=True))
