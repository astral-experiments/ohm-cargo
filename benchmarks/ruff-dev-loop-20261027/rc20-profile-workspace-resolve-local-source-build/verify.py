"""Verify both independent source builds, captured Ruff native roles and all 256 clocks."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics

HERE = Path(__file__).resolve().parent
A = "2fe90823d8eadc95de56c2cde8d41e0082aac0eb"
B = "97e5acfb7b8eefde1ce07d703fc4849d6d36e37c"


def check(ok, label):
    if not ok:
        raise ValueError(label)


def read(name):
    return json.loads((HERE / name).read_bytes())


def verify(build, receipt, links, run):
    aa, bb = build["arms"]
    check(receipt["baseline"] == A and receipt["source"] == B and
          [aa["git"], bb["git"]] == [A, B] and receipt["arms"]["A"]["version"] == receipt["arms"]["B"]["version"], "source and version")
    check(receipt["baseline_binary"] != receipt["cargo_sha256"] and
          run["cargo"] == [aa["cargo"], bb["cargo"]] == [receipt["baseline_binary"], receipt["cargo_sha256"]], "source-built images")
    check(run["rustc"] == links["expected_rustc"] == build["rust"] and run["wild"] == links["expected_wild"] == build["wild"] and
          run["driver"] == build["driver"] and build["verified_downloaded_crates"]==523, "held SDK")
    check(aa["compiler_arguments"] == bb["compiler_arguments"] and len(aa["compiler_arguments"]) ==
          aa["actual_rustc"] == bb["actual_rustc"] == build["equal_literal_rustc_argv"] == 383, "literal compiler arguments")
    for arm in (aa,bb):
        check(arm["inputs"] == 3108 and arm["successful_artifacts"] == 383 and
              arm["rustc_images"] == [{"basename":"rustc","file_sha256":build["rust"],"processes":383}], "compiler binary and product census")
    check(aa["linker_processes"] == bb["linker_processes"] and
          {e["role"]:e["count"] for e in aa["linker_processes"]} == {"sdk/gcc-ld/ld.lld":49,"sdk/rust-lld":49,"system/ld":1}, "bootstrap native closure")
    check([(e["mode"],e["lane"]) for e in links["warmup"]] == [(mode,lane) for lane in ("mechanism","wall") for mode in ("build","test")],"warmup roster")
    for r in links["warmup"]:
        nc,nl = (1,0) if r["mode"]=="build" else (15,6)
        check((r["roles"].get("selected-rustc",0),r["roles"].get("selected-stock-Wild",0))==(nc,nl) and
              len(r["all_native_argv"])==nc+nl,"real Ruff compiler/linker inputs")
    check(run["public_stream_projection"]=={"build":{"occurrences":128,"verified_literal_path_substitutions":0},"test":{"occurrences":128,"verified_literal_path_substitutions":128}},"stream projection coverage")
    names = ["invalid_range_deserialization","range_serialization","size_serialization"]
    for mode in ("build","test"):
        stats, = [r for r in run["statistics"] if r["workload"] == mode]
        check(stats["units_in_plan"] == (1 if mode=="build" else 19), "unit count")
        check(stats["oracle"] == run["products"]["wall-"+mode]["oracle"] and
              stats["oracle"][0] == ("17 29 12" if mode=="build" else names),"executed oracle")
        for lane,guards in run["guards"].items():
            selected = [r for r in guards if r["workload"]==mode]
            check(len(selected) == (20 if lane=="mechanism" else 12), "native control count")
            for native in selected:
                cold = native["arm"]=="C" and native["stage"]=="00-prepare"
                wanted = ((1,0) if mode=="build" else (15,6)) if cold else (0,0)
                check((native["rustc"],native["links"])==wanted,"unexpected extra work")
                if lane=="mechanism" and native["arm"] in ("A","B") and native["stage"] not in ("00-prepare","99-terminal"):
                    full = native["arm"]=="A" and native["stage"] in ("01-edited","02-restored","04-reverse","06-restore")
                    check((native["full"]>0)==full and native["full"]+native["hits"]>0,"resolver behavior")
        src=run["chronology"][mode]; streams=run["ordinary_streams"][mode]
        check(len(src)==len(streams)==128,"complete cohort")
        grouped={p:[] for p in ("edit","repeat","edit_plus_repeat")}
        for i in range(32):
            order=("AB","BA","BA","AB")[i%4]
            direction=("edit","orig")[i%2]
            ns={}
            for j,arm in enumerate(order):
                for k,step in enumerate(("edit","repeat")):
                    n=4*i+2*j+k; e,cmd=src[n],streams[n]
                    check([e[f] for f in ("pair","sequence","source","arm","phase")]==[i,order,direction,arm,step],"misordered clock")
                    check(cmd["exit"]==0 and cmd["stdout"]=="" and re.search(r"Finished .* profile .* target\(s\)",cmd["stderr"]) and
                          e["ns"]==cmd["ns"]>0,"unsuccessful or unbound process")
                    check(cmd["stdout_sha256"]==hashlib.sha256(b"").hexdigest() and re.fullmatch("[0-9a-f]{64}",cmd["stderr_sha256"]), "missing literal source stream hash")
                    if mode=="build":
                        check(hashlib.sha256(cmd["stderr"].encode()).hexdigest()==cmd["stderr_sha256"],"package stderr hash")
                    else:
                        rel,=[path for path in run["products"]["wall-test"]["files"] if Path(path).name.startswith("serde-")]
                        check(cmd["stderr"].splitlines()[1:]==["  Executable tests/serde.rs (<workspace-view>/"+rel+")"], "unbound projected test executable")
                    ns[arm,step]=e["ns"]
            for step in grouped:
                a,b = ([ns[arm,"edit"]+ns[arm,"repeat"] for arm in "AB"] if step=="edit_plus_repeat" else [ns[arm,step] for arm in "AB"])
                grouped[step].append((a,b,(direction,order)))
        for step,rows in grouped.items():
            metrics=stats["metrics"][step]; vals=[100*(a-b)/a for a,b,_ in rows]; median=statistics.median
            check(median(vals)==metrics["paired_reduction_pct"] and median(a for a,_,__ in rows)/1e6==metrics["parent_median_ms"] and
                  median(b for _,b,__ in rows)/1e6==metrics["candidate_median_ms"] and median((a-b)/1e6 for a,b,_ in rows)==metrics["paired_median_ms"],"effect")
            counts=Counter((v>0)-(v<0) for v in vals); n=counts[-1]+counts[1]
            p=min(1,2*sum(math.comb(n,k) for k in range(min(counts[-1],counts[1])+1))/2**n)
            check(metrics["n"]==32 and metrics["faster_pairs"]==counts[1] and p==metrics["sign_test_p_two_sided"], "sign test")
            strata={}
            for (_,__,group),v in zip(rows,vals):strata.setdefault(group,[]).append(v)
            check(len(strata)==4 and set(map(len,strata.values()))=={8},"stratification")
            for side in ("orig","edit"):
                check(median(v for (_,__,g),v in zip(rows,vals) if g[0]==side)==metrics["direction_medians_pct"][side],"direction effect")
            rng=random.Random(0x0e398aa5)
            boot=sorted(median([rng.choice(g) for g in strata.values() for __ in g]) for _ in range(20000))
            check(metrics["bootstrap95_pct"]==[boot[int((len(boot)-1)*k)] for k in (.025,.975)],"paired interval")


def main():
    groups=[read(n) for n in ("source-build.json","build-receipt.json","ruff-linked.json","source-run.json")]
    verify(*groups)
    independently = read("independent-build.json")
    assert independently["common_compiler_arguments"]==383 and independently["same_native_tools"] and independently["reported_full_version_equal"]
    for left,right in zip(groups[0]["arms"],independently["arms"]):
        check(left["compiler_arguments"]==right["arguments"] and left["cargo"]==right["cargo"] and
              left["actual_rustc"]==right["rustc"]==383 and left["successful_artifacts"]==right["typed_artifacts"]==383,"independent kernel reader")
        native = {("sdk/"+row["role"].split("/bin/",1)[-1] if row["role"].startswith("sdk/") else row["role"],row["sha256"],row["count"]) for row in right["linkers"]}
        check(native=={(r["role"],r["file_sha256"],r["count"]) for r in left["linker_processes"]},"independent native binary binding")
    mutations=[
        lambda b,r,l,x: b["arms"][1]["compiler_arguments"].pop(),
        lambda b,r,l,x: l["warmup"][1]["roles"].update({"selected-stock-Wild":0}),
        lambda b,r,l,x: x["ordinary_streams"]["test"][31].update(exit=1),
        lambda b,r,l,x: x["chronology"]["build"][30].update(arm="Z"),
        lambda b,r,l,x: x["products"]["wall-test"]["oracle"][0].pop(),
        lambda b,r,l,x: x["statistics"][1]["metrics"]["edit"].update(paired_reduction_pct=0),
    ]
    for mutate in mutations:
        sample=deepcopy(groups); mutate(*sample)
        try:verify(*sample)
        except (ValueError,IndexError):continue
        raise ValueError("false evidence accepted")
    print("Verified both 383-compiler builds, four stock Ruff warmups, 64 native controls, 256 ordinary commands, all paired effects, and six rejected mutations.")


if __name__=="__main__":main()
