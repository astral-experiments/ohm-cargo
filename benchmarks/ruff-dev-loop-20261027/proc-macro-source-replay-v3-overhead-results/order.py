"""Descriptive order and resource summaries using every observation in the primary study."""
from pathlib import Path
import json, math, statistics

p=Path(__file__).parent
def val(q,k):return q["child"][k]
def med_pct(xs):return 100*math.expm1(statistics.median([math.log(x) for x in xs]))
all_rows=json.loads((p/"heldout/observations.json").read_bytes());out={}
for ep in ["retained","empty"]:
    rows=[r for r in all_rows if r["endpoint"]==ep]
    pairs=[rows[i:i+2] for i in range(0,len(rows),2)]
    assert len(pairs)==16 and all(a["pair"]==b["pair"]==i for i,(a,b) in enumerate(pairs))
    first,second=zip(*pairs)
    order={}
    for arm in ("parent","candidate"):
        ss=[pair for pair in pairs if pair[0]["arm"]==arm]
        c,pv=([[r for r in pair if r["arm"]==key][0] for pair in ss] for key in ("candidate","parent"))
        order[arm+"_first"]={"n":len(ss),"candidate_over_parent_median_pct":med_pct([val(a,"wall_ns")/val(b,"wall_ns") for a,b in zip(c,pv)])}
    out[ep]={"order_splits":order,"first_over_second_median_pct":med_pct([val(a,"wall_ns")/val(b,"wall_ns") for a,b in pairs]),"first_slower_pairs":sum(val(a,"wall_ns")>val(b,"wall_ns") for a,b in pairs),
             "first_or_second_medians":{n:{k:statistics.median([val(x,k) for x in group]) for k in ("wall_ns","cpu_user_s","cpu_system_s")} for n,group in [("first",first),("second",second)]},
             "wall_vs_system_time_pearson":statistics.correlation([val(x,"wall_ns") for x in rows],[val(x,"cpu_system_s") for x in rows]),
             "wall_vs_user_time_pearson":statistics.correlation([val(x,"wall_ns") for x in rows],[val(x,"cpu_user_s") for x in rows]),"removed":0}
print(json.dumps(out,sort_keys=True,indent=2))
