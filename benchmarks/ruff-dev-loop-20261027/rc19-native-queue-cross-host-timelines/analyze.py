"""Compare the same physical scheduling intervals on 12 H8 and 16 C5 unscored traces."""
from collections import defaultdict
import gzip
import json
from pathlib import Path
from statistics import median
import sys

root=Path(__file__).resolve().parent
def read(path):
    return json.loads(gzip.decompress(path.read_bytes()))
def h8_rows(path):
    for r in read(path):
        entries=[(target,j["output_bytes"],*j["wild"],j["rustc"][1]) for target,j in r["bins"].items()]
        yield ("H8",str(r["b"])+"/"+r["p"],r["a"],False,r["events_sha256"],r["cargo"][1],r["ron"][1],entries)
def c5_rows(path):
    for r in read(path)["observations"]:
        entries=[(j["target"],j["prior_observed_bytes"],j["wild_exec_ns"],j["wild_exit_ns"],j["rustc_exit_ns"]) for j in r["targets"]]
        yield ("C5",r["section"]+"/"+r["flank"],r["arm"],r["section"].startswith("edit"),r["source_trace_sha256"],r["cargo_exit_ns"],r["full_ron_exit_ns"],entries)
def metric(line):
    host,label,arm,edit,source,cargo_end,ron_end,bins=line
    assert len(bins)==len({r[0] for r in bins})==50
    ordered=sorted(bins,key=lambda row:(-row[1],row[0]))
    big=ordered[:10]
    # Integral of choose(n_active_large, 2) is the sum of actual pair intersections.
    overlap=sum(max(0,min(left[3],right[3])-max(left[2],right[2])) for i,left in enumerate(big) for right in big[i+1:])
    start=min(r[2] for r in bins)
    finish=max(r[3] for r in bins)
    peak=max(sum(j[1] for j in bins if j[2]<=r[2]<j[3]) for r in bins)
    peak_n=max(sum(j[2]<=r[2]<j[3] for j in big) for r in big)
    e2e,=[r for r in bins if r[0]=="e2e-f978f73ba5a3a2ed"]
    item={"large_pair_overlap_s":overlap/1e9,"peak_live_output_gb":peak/1e9,"peak_large_count":peak_n,
          "last_start_to_last_exit_s":(finish-max(r[2] for r in bins))/1e9,"whole_wild_span_s":(finish-start)/1e9,
          "cargo_after_last_rustc_s":(cargo_end-max(ron_end,max(r[4] for r in bins)))/1e9,
          "aggregate_large_service_s":sum(r[3]-r[2] for r in big)/1e9,
          "e2e_start_s":(e2e[2]-start)/1e9,"e2e_service_s":(e2e[3]-e2e[2])/1e9}
    assert all(v>=0 for v in item.values())
    return {"host":host,"label":label,"arm":arm,"edit_flank":edit,"source_sha256":source,"metrics":item}
def construct():
    rows=[metric(r) for r in [*h8_rows(root/"h8-retained.json.gz"),*c5_rows(root/"c5/timelines.json.gz")]]
    assert len(rows)==28 and len({r["source_sha256"] for r in rows})==28
    groups=defaultdict(list)
    for r in rows:
        group=r["host"]+("-edit" if r["edit_flank"] else "-stationary")
        groups[group,r["arm"]].append(r["metrics"])
    summary={}
    for (group,arm),items in groups.items():
        assert len(items)==(2 if group=="C5-edit" else 6)
        summary.setdefault(group,{})[arm]={name:median(i[name] for i in items) for name in items[0]}
    return {"physical_traces":rows,"medians":summary}
if __name__=="__main__":
    result=construct()
    if "--emit" in sys.argv:
        print(json.dumps(result,indent=2,sort_keys=True))
    else:
        assert result==json.loads((root/"result.json").read_bytes())
        print("Verified 1,400 native intervals, the per-arm medians of the twelve comparable stationary flanks on each host, and four additional C5 edit flanks.")
