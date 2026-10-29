"""Verify the included one-unit independent local example, including its rejected mutations."""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics

HERE = Path(__file__).resolve().parent


def demand(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate(d):
    demand(d["kind"] == "independent local replication" and d["workload"] == "build", "wrong scope")
    demand(len(set(d["cargo"])) == 2, "identical compilers")
    node, = d["statistics"]
    demand(node["units_in_plan"] == node["artifacts"] == 1 and node["declared_files"] == 2, "unexpected selection")
    pairs = d["chronology"]["build"]
    streams = d["ordinary_streams"]["build"]
    demand(len(streams) == len(pairs) == 128, "partial wall cohort")
    phases = defaultdict(list)
    for i in range(32):
        offset = i * 4
        direction = ("edit", "orig")[i % 2]
        order = ("AB", "BA", "BA", "AB")[i % 4]
        t = {}
        for j, arm in enumerate(order):
            for k, stage in enumerate(("edit", "repeat")):
                index = offset + j * 2 + k
                row, command = pairs[index], streams[index]
                demand([row[v] for v in ("pair", "source", "sequence", "arm", "phase")] == [i, direction, order, arm, stage], "incorrect visit")
                demand(command["ns"] == row["ns"] > 0 and command["exit"] == 0 and command["stdout"] == "", "bad process result")
                demand(re.fullmatch(r"    Finished `dev` profile \[optimized \+ debuginfo\] target\(s\) in [0-9]+\.[0-9]+s\n", command["stderr"]) is not None, "ordinary Cargo stderr")
                t[arm, stage] = row["ns"]
        for stage in ("edit", "repeat", "edit_plus_repeat"):
            counts = ([t[a,"edit"]+t[a,"repeat"] for a in "AB"] if stage == "edit_plus_repeat" else [t[a,stage] for a in "AB"])
            phases[stage].append((direction, order, *counts))
    for phase, samples in phases.items():
        stats = node["metrics"][phase]
        partition = {}
        ratios = []
        for way, order, a, b in samples:
            value = 100 * (a-b)/a
            partition.setdefault((way,order),[]).append(value)
            ratios.append(value)
        counts = Counter((v > 0) - (v < 0) for v in ratios)
        n = counts[-1] + counts[1]
        p = min(1.,2*sum(math.comb(n,k) for k in range(min(counts[1],counts[-1])+1))/2**n)
        median = statistics.median
        demand(stats["n"] == 32 and stats["parent_median_ms"] == median(x[2] for x in samples)/1e6 and
               stats["candidate_median_ms"] == median(x[3] for x in samples)/1e6 and
               stats["paired_median_ms"] == median((x[2]-x[3])/1e6 for x in samples) and
               stats["paired_reduction_pct"] == median(ratios) and stats["faster_pairs"] == counts[1] and
               stats["sign_test_p_two_sided"] == p, "statistics disagreement")
        demand(len(partition) == 4 and set(map(len,partition.values())) == {8}, "unbalanced strata")
        for side in ("orig", "edit"):
            demand(stats["direction_medians_pct"][side] == median(r for sample,r in zip(samples,ratios) if sample[0]==side), "direction statistic")
        rng = random.Random(0x0e398aa5)
        vals = sorted(median([rng.choice(group) for group in partition.values() for _ in group]) for __ in range(20000))
        demand(stats["bootstrap95_pct"] == [vals[int((len(vals)-1)*v)] for v in (0.025,0.975)], "interval mismatch")
    for stage, rows in d["guards"].items():
        expected = ["00-prepare", "01-edited", "02-restored", "03-settled", "99-terminal"]
        if stage == "mechanism":
            expected += ["04-reverse", "05-repeat", "06-restore", "07-repeat"]
        demand(Counter((r["arm"], r["stage"]) for r in rows) ==
               Counter([("C","00-prepare"),("C","00-frozen")]+[(a,s) for a in "AB" for s in expected]), "missing native controls")
        for r in rows:
            cold = r["arm"] == "C" and r["stage"]=="00-prepare"
            demand((r["rustc"],r["links"],r["typed_artifacts"]) == (int(cold),0,1), "native work changed")
            if stage == "mechanism":
                demand(r["full"]+r["hits"]>0,"missing resolver record")
                if r["arm"] in "AB" and r["stage"] not in ("00-prepare","99-terminal"):
                    full = r["arm"]=="A" and r["stage"] in ("01-edited","02-restored","04-reverse","06-restore")
                    demand((r["full"]>0)==full, "false mechanism")
        product = d["products"][stage+"-build"]
        demand(product["same_physical_runtime"] and len(product["runtime_roles"])==4 and len(product["files"])==2 and
               product["oracle"][0]=="17 29 12" and len(product["oracle"][1])==64,"incomplete compiled caller")
    demand(node["oracle"] == d["products"]["wall-build"]["oracle"],"wrong enrolled caller")


def main():
    data = json.loads((HERE/"local-result.json").read_bytes())
    validate(data)
    edits = {
        "removed command": lambda x: x["chronology"]["build"].pop(),
        "switched arm": lambda x: x["chronology"]["build"][0].update(arm="B"),
        "incorrect stdout": lambda x: x["ordinary_streams"]["build"][0].update(stdout="9"),
        "missing caller": lambda x: x["products"]["wall-build"]["oracle"].pop(),
        "unexpected native link": lambda x: x["guards"]["wall"][1].update(links=1),
        "false cache hit": lambda x: next(r for r in x["guards"]["mechanism"] if r["arm"]=="B" and r["stage"]=="01-edited").update(full=1),
        "incorrect estimate": lambda x: x["statistics"][0]["metrics"]["edit"].update(paired_reduction_pct=0),
    }
    for name, mutate in edits.items():
        copy = deepcopy(data)
        mutate(copy)
        try:
            validate(copy)
        except (ValueError, IndexError):
            continue
        raise ValueError("accepted mutation: "+name)
    source = json.loads((HERE/"source-exports.json").read_bytes())["arms"]
    demand(source["A"]["files"] == source["B"]["files"] == 3108 and source["A"]["stamp"] == source["B"]["stamp"] and
           source["A"]["tree"]!=source["B"]["tree"] and source["A"]["cargo_lock"]==source["B"]["cargo_lock"],"wrong exported sources")
    print(f"Verified 32 pairs, 128 processes, 32 native controls, 7 rejected mutations and two 3108-entry source exports.")


if __name__ == "__main__":
    main()
