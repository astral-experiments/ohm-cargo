"""Project sixteen off-clock native flanks to times relative to each command's first Wild exec."""
from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import os
import stat
import sys

root=Path(sys.argv[1]).resolve();rep=root/"native-ready-order19/reports"
def bfile(p):
    q=p.resolve(strict=True)
    fd=os.open(q,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_NOATIME)
    def meta(s):return (s.st_dev,s.st_ino,s.st_size,s.st_mode,s.st_atime_ns,s.st_ctime_ns,s.st_mtime_ns)
    with os.fdopen(fd,"rb") as f:
        st=os.fstat(f.fileno());assert stat.S_ISREG(st.st_mode);b=f.read();assert meta(st)==meta(os.fstat(f.fileno()))==meta(q.stat())
    return b
def sha(b):return hashlib.sha256(b).hexdigest()
def jread(p):return json.loads(bfile(p))
def prior_root(label,arm,outs):
    family="reopened-edit-relative-v1-"+("validation" if arm=="A" else "qa") if label=="edit-nativeedit" else label.split("-")[0]
    d=rep/("trained-v6-start-"+family+"-"+arm)
    rec=bfile(d/"result.json");h=bfile(d/"target.jsonl.gz");u=gzip.decompress(h);s=json.loads(rec)
    assert sha(u)==s["observations"]["target"]["observed"]["tree_sha256"]
    table={}
    required={str(Path(k).relative_to("target")):k for k in outs}
    for line in u.splitlines():
        row=json.loads(line);assert len(row)>=7
        rel=os.fsdecode(bytes.fromhex(row[0]))
        if rel in required:
            assert row[1]==stat.S_IFREG and len(row)==10 and rel not in table
            table[required[rel]]={"bytes":row[7],"sha256":row[9]}
    assert set(table)==set(outs)
    return table,{"kind":"held writable-layer-empty donor inventory before section preparation","phase":family+"-"+arm,
                  "source_inventory_gz_sha256":sha(h),"source_uncompressed_tree_sha256":sha(u),"receipt_sha256":sha(rec)}

def duration(events):
    changes=sorted([(t[0],1,t[2]) for t in events]+[(t[1],-1,-t[2]) for t in events],key=lambda t:(t[0],t[1]))
    active=0;weight=0;mx=0;wt=0;last=0;two=0;four=0
    for time,delta,w in changes:
        assert time>=last
        if active>=2:two+=time-last
        if active>=4:four+=time-last
        active+=delta;weight+=w;mx=max(mx,active);wt=max(wt,weight);last=time
    assert active==weight==0
    return {"peak_active_wild":mx,"peak_sum_of_output_sizes_of_active_wild":wt,"elapsed_ns_with_two_or_more_wild":two,"elapsed_ns_with_four_or_more_wild":four}
prev={};samples=[]
for label in ("batch1-series1","batch2-series2","plain-holdout","edit-nativeedit"):
    for edge in ("before","after"):
        for arm in "AB":
            logical=f"clock-v4-{label}-trace-{edge}-{arm}"
            d=rep/logical;et=bfile(d/"execs.json");rb=bfile(d/"result.json");ex=json.loads(et);rec=json.loads(rb)
            assert rec["exit"]==ex["root_exit"]==0 and rec["execs_sha256"]==sha(et) and rec["units"]==619 and rec["fresh"]==563
            ev=ex["events"];counts=Counter(x["role"] for x in ev)
            assert counts["cargo"]==counts["rustc-full"]==1 and all(counts[n]==50 for n in ("rustc-link-only","gcc","collect2","stock-wild"))
            assert all(ex["process_exit"][str(x["pid"])]==0 for x in ev)
            assert len({x["pid"] for x in ev})==len(ev)
            by={x["pid"]:x for x in ev};lo=lambda pid:ex["exit_ns"][str(pid)]
            cargo,=[x for x in ev if x["role"]=="cargo"]
            ron,=[x for x in ev if x["role"]=="rustc-full"];assert ron["target"]=="ron" and ron["ppid"]==cargo["pid"]
            outs=rec["products"];assert len(outs)==50
            if edge=="before" and label!="plain-holdout":
                previous,source=prior_root(label,arm,outs)
            else:
                previous,source=prev[arm]
            assert set(outs)==set(previous)
            wild=[x for x in ev if x["role"]=="stock-wild"];zero=min(x["start_ns"] for x in wild);rows=[]
            for w in wild:
                gc2=by[w["ppid"]];gcc=by[gc2["ppid"]];rust=by[gcc["ppid"]]
                assert gc2["role"]=="collect2" and gcc["role"]=="gcc" and rust["role"]=="rustc-link-only" and rust["ppid"]==cargo["pid"]
                assert Path(w["out"]).name==Path(gc2["out"]).name==Path(gcc["out"]).name
                out=str(Path(w["out"]).relative_to(root));assert out in previous and out in outs
                start=lambda x:x["start_ns"]-zero;end=lambda x:lo(x["pid"])-zero
                assert start(cargo)<=start(rust)<=start(gcc)<=start(gc2)<=start(w)<=end(w)<=end(gc2)<=end(gcc)<=end(rust)<=end(cargo)
                rows.append({"target":Path(out).name,"rust_crate":rust["target"],"output_bytes":outs[out]["size"],"output_sha256":outs[out]["sha256"],
                             "prior_observed_bytes":previous[out]["bytes"],"prior_observed_sha256":previous[out]["sha256"],
                             "rustc_exec_ns":start(rust),"rustc_exit_ns":end(rust),"gcc_exec_ns":start(gcc),"collect2_exec_ns":start(gc2),"wild_exec_ns":start(w),"wild_exit_ns":end(w)})
            assert len({x["target"] for x in rows})==50
            rows.sort(key=lambda x:(x["wild_exec_ns"],x["target"]))
            times=[(x["wild_exec_ns"],x["wild_exit_ns"],x["output_bytes"]) for x in rows]
            out={"section":label,"flank":edge,"arm":arm,"source_trace_sha256":sha(et),"source_result_sha256":sha(rb),
                 "actual_workers":{"cargo":1,"full_rustc":1,"link_only_rustc":50,"gcc":50,"collect2":50,"stock_wild":50},"earlier_output_inventory":source,
                 "cargo_exec_ns":cargo["start_ns"]-zero,"cargo_exit_ns":lo(cargo["pid"])-zero,
                 "full_ron_exec_ns":ron["start_ns"]-zero,"full_ron_exit_ns":lo(ron["pid"])-zero,"last_wild_exit_ns":max(x[1] for x in times),
                 "targets":rows,"descriptive_overlap":duration(times)}
            samples.append(out)
            prev[arm]=({k:{"bytes":v["size"],"sha256":v["sha256"]} for k,v in outs.items()},
                       {"kind":"previous retained native qualification on same physical lane","phase":label+"-trace-"+edge+"-"+arm,"receipt_sha256":sha(rb)})
assert len(samples)==16
packet={"schema":1,"observations":samples,"clock":"execve and wait4 sampling wall-time nanoseconds relative to first actual Wild exec in each diagnostic command",
        "size_scope":"the prior observation comes from the named earlier inventory; the native tracer did not sample the incumbent at exec. Output size is the physically read completed native file."}
sys.stdout.buffer.write(gzip.compress((json.dumps(packet,separators=(",",":"),sort_keys=True)+"\n").encode(),compresslevel=9,mtime=0))
