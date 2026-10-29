from pathlib import Path
import collections
import gzip
import hashlib
import json
import re

ROOT=Path(__file__).resolve().parent
def compute(rows):
    marks=sorted([(r["wild_exec_ns"],1,r["output_bytes"]) for r in rows]+[(r["wild_exit_ns"],-1,-r["output_bytes"]) for r in rows],key=lambda t:(t[0],t[1]))
    live=weight=busy2=busy4=peak=peakbytes=last=0
    for t,k,w in marks:
        assert t>=last
        if live>=2:busy2+=t-last
        if live>=4:busy4+=t-last
        last=t;live+=k;weight+=w;peak=max(peak,live);peakbytes=max(peakbytes,weight)
    assert live==weight==0
    return dict(peak_active_wild=peak,peak_sum_of_output_sizes_of_active_wild=peakbytes,elapsed_ns_with_two_or_more_wild=busy2,elapsed_ns_with_four_or_more_wild=busy4)
def check(d):
    assert d["schema"]==1 and len(d["observations"])==16
    all_names=set();previous={};commits=set();prior_source={}
    for i,item in enumerate(d["observations"]):
        s,edge,a=item["section"],item["flank"],item["arm"];n=(i//4,i%4//2,i%2)
        assert (s,edge,a)==(["batch1-series1","batch2-series2","plain-holdout","edit-nativeedit"][n[0]],["before","after"][n[1]],"AB"[n[2]])
        rows=item["targets"];names={r["target"] for r in rows}
        assert len(names)==len(rows)==50 and (not all_names or names==all_names);all_names=names
        assert len({r["wild_exec_ns"] for r in rows})==len(rows) and min(r["wild_exec_ns"] for r in rows)==0
        assert item["actual_workers"]==dict(cargo=1,full_rustc=1,link_only_rustc=50,gcc=50,collect2=50,stock_wild=50)
        assert re.fullmatch(r"[a-f0-9]{64}",item["source_trace_sha256"]) and item["source_trace_sha256"] not in commits
        commits.add(item["source_trace_sha256"])
        assert (item["cargo_exec_ns"]<=item["full_ron_exec_ns"]<=item["full_ron_exit_ns"]<=item["cargo_exit_ns"])
        for r in rows:
            assert re.fullmatch(r"[A-Za-z0-9_-]+",r["target"]) and r["prior_observed_bytes"]==r["output_bytes"]>0
            assert all(re.fullmatch(r"[0-9a-f]{64}",r[k]) for k in ("prior_observed_sha256","output_sha256"))
            assert item["cargo_exec_ns"]<=r["rustc_exec_ns"]<=r["gcc_exec_ns"]<=r["collect2_exec_ns"]<=r["wild_exec_ns"]<r["wild_exit_ns"]<=r["rustc_exit_ns"]<=item["cargo_exit_ns"]
        assert item["last_wild_exit_ns"]==max(r["wild_exit_ns"] for r in rows) and item["descriptive_overlap"]==compute(rows)
        ref=item["earlier_output_inventory"]
        if edge=="after" or s=="plain-holdout":
            assert ref["receipt_sha256"]==prior_source[a] and all((r["prior_observed_bytes"],r["prior_observed_sha256"])==previous[a][r["target"]] for r in rows)
        else:assert ref["kind"].startswith("held writable-layer-empty donor") and re.fullmatch(r"[0-9a-f]{64}",ref["source_uncompressed_tree_sha256"])
        prior_source[a]=item["source_result_sha256"];previous[a]={r["target"]:(r["output_bytes"],r["output_sha256"]) for r in rows}
    return len(commits),len(all_names)
if __name__=="__main__":
    obj=json.loads(gzip.decompress((ROOT/"timelines.json.gz").read_bytes()));assert check(obj)==(16,50)
    print("16 off-clock traces, 800 stock native intervals and rustc parents, 16 full ron and Cargo exit intervals, all earlier size references and overlap summaries verified.")
