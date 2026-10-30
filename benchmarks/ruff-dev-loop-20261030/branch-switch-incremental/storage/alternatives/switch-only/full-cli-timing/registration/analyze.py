#!/usr/bin/env python3
"""Analyze the preregistered branch-return observations. Requires Python 3.11+."""
import argparse
import itertools
import json
import math
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("off", "on")
PHASES = ("empty-A", "first-B", "return-A", "return-B", "unchanged-B")
GIB = 2**30

def require(condition, message):
    if not condition:
        raise ValueError(message)

def sha256_text(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)

def geometric_median(values):
    return math.exp(statistics.median(math.log(x) for x in values))

def median_interval(values):
    require(len(values) == 12, "the confirmation needs exactly 12 independent pairs")
    ordered = sorted(values)
    # P(Bin(12, 1/2) <= 2) = 79/4096, P(Bin(12, 1/2) >= 11) = 13/4096.
    return [ordered[2], ordered[10]]

def schedule(plan):
    slots = []
    def add(stage, n, order):
        for arm in order:
            slots.append(dict(stage=stage, pair=n, arm=arm, slot=f"{stage}-{n:02d}-{arm}"))
    add("pilot", 1, ("on", "off"))
    add("pilot", 2, ("off", "on"))
    for block in range(3):
        numbers = range(4*block+1, 4*block+5)
        draw = [v for v in plan["order_draw_bytes"][block] if v < 252]
        require(len(draw) == 1 and draw[0] == plan["order_draw_bytes"][block][-1], "unbiased block draw")
        off_first = set(list(itertools.combinations(numbers, 2))[draw[0] % 6])
        for n in numbers:
            add("confirmation", n, ARMS if n in off_first else tuple(reversed(ARMS)))
    return slots

def randomization(effects, null_ratio):
    directions = ("return-A", "return-B")
    combinations = list(itertools.combinations(range(4), 2))
    # Divide each observed off time by the sharp multiplicative null before
    # reassignment. The two period effects then stay fixed within their pair.
    period = {}
    actual = {}
    for direction in directions:
        rows = effects[direction]["observations"]
        logs = [math.log(v["off_ns"] / v["on_ns"] / null_ratio) for v in rows]
        period[direction] = [v if row["off_first"] else -v for v,row in zip(logs,rows)]
        actual[direction] = math.fsum(logs)/len(logs)
    null = []
    for indexes in itertools.product(combinations, repeat=3):
        signs = [1 if i%4 in indexes[i//4] else -1 for i in range(12)]
        null.append({d:math.fsum(s*x for s,x in zip(signs,period[d]))/12 for d in directions})
    require(len(null)==216, "three independent six-way block assignments")
    return {d:{"raw_p":sum(t[d]>=actual[d]-1e-13 for t in null)/216,
               "family_max_p":sum(max(t.values())>=actual[d]-1e-13 for t in null)/216,
               "observed_mean_log_relative_to_null":actual[d]} for d in directions}

def check_visit(visit, phase, arm, plan, reference):
    revision = phase[-1]
    require(visit["phase"] == phase and visit["source"] == plan["ruff"][revision], "incorrect visit/commit")
    require(visit["exit"] == 0 and visit["typed_units"] == 375, "Cargo graph/verdict")
    require(visit["dirty_units"] == (375 if phase == "empty-A" else 0 if phase == "unchanged-B" else 20), "dirty roster")
    require(visit["graph_sha256"] == plan["graph_sha256"], "actual typed roster")
    for field in ("cli", "reader", "verdict_sha256", "dirty_set_sha256"):
        require(visit[field] == reference[field], f"{arm} / {phase} differs from independent native {field}")
    require(sha256_text(visit["result_sha256"]) and sha256_text(visit["process_sha256"]), "missing raw result")
    for field in ("elapsed_ns", "user_cpu_us", "system_cpu_us", "git_ns"):
        require(type(visit[field]) is int and visit[field] >= 0, f"invalid {field}")
    require(visit["elapsed_ns"] > 0 and (phase == "empty-A" or phase == "unchanged-B" or visit["git_ns"] > 0), "clock/source switch")
    s = visit["storage"]
    fields = ("whole", "target", "shared", "shared_names", "incremental", "incremental_exclusive",
              "incremental_also_outside", "packed_bytes", "raw_table_bytes")
    require(all(type(s[k]) is int and s[k]>=0 and s[k]%512==0 for k in fields), "allocated byte census")
    require(s["whole"] == s["target"] + s["shared"] - s["shared_names"] > 0, "whole unique-inode coverage")
    require(s["incremental"] == s["incremental_exclusive"] + s["incremental_also_outside"] <= s["whole"], "incremental coverage")
    require(s["filesystem_used"] == s["whole"] and s["working_sessions"] == 0 and sha256_text(s["ledger_sha256"]), "stable settled output")
    require((s["packed_bytes"] > 0) == (arm == "on" and phase != "empty-A"), "packed session tables or option")

def check_native(doc, plan):
    require(doc["source"] == plan["compiler_source"] and doc["cargo"] == plan["cargo_source"], "unmatched sources")
    require(sha256_text(doc["native_independent_terminal"]) and sha256_text(doc["physical_sdk_sha256"]), "native admission receipts")
    require(doc["observed_flag"] == {"off":None,"on":plan["on_flag"]}, "unexpected option")
    ref = doc["native_reference"]
    for arm in ARMS:
        require(list(sorted(ref[arm])) == sorted(PHASES), "incomplete native phase set")
        for phase in PHASES:
            row=ref[arm][phase]; clean = ref[arm]["empty-A" if phase[-1] == "A" else "first-B"]
            require(row["independent_empty_full_file_equality"] and sha256_text(row["raw_native_result"]), "missing scheme-matched reference")
            for key in ("cli", "reader"):
                v=row[key];require(sha256_text(v["sha256"]) and isinstance(v["bytes"],int) and v["bytes"] > 1_000_000 and clean[key]==v, "incomplete whole ELF")
            require(sha256_text(row["verdict_sha256"]) and row["verdict_sha256"]==clean["verdict_sha256"], "reference verdict")
            require(sha256_text(row["dirty_set_sha256"]), "missing exact dirty set")
            require(row["real_rustc"]==(379 if phase=="empty-A" else 0 if phase=="unchanged-B" else 20) and row["real_wild"]==(69 if phase=="empty-A" else 0 if phase=="unchanged-B" else 1), "physical native count")
    for rev in ("A", "B"):
        require(doc["cross_option"][rev]["verdict_equal"] and doc["cross_option"][rev]["ordinary_caller_equal"], "cross-option behavior")
    return ref

def compute(plan, doc, stage):
    ref=check_native(doc,plan)
    expected=[x for x in schedule(plan) if x["stage"] == stage]
    require(len(expected)==len(doc["slots"]), "complete chronological stage required")
    observed={}
    for registration, slot in zip(expected,doc["slots"]):
        require(all(slot[k]==v for k,v in registration.items()), "out-of-order, duplicate, or replacement installation")
        arm=slot["arm"]
        require(slot["physical_sdk_sha256"]==doc["physical_sdk_sha256"] and slot["physical_sdk_entries"]==57, "same physical compiler and tools")
        require(slot["empty_workspace"] and slot["actual_front_gate"] and len(slot["visits"])==5, "initial conditions")
        require(sha256_text(slot["front_sha256"]) and sha256_text(slot["completion_sha256"]), "missing installation receipts")
        for phase,visit in zip(PHASES,slot["visits"]):
            check_visit(visit,phase,arm,plan,ref[arm][phase])
            observed[slot["pair"],arm,phase]=visit
    effects={}
    n=2 if stage=="pilot" else 12
    for phase in PHASES:
        rows=[]
        for i in range(1,n+1):
            off,on=[observed[i,a,phase] for a in ARMS]
            cpu=lambda v:v["user_cpu_us"]+v["system_cpu_us"]
            require(cpu(off)>0 and cpu(on)>0,"nonpositive child CPU")
            wall=off["elapsed_ns"]/on["elapsed_ns"]
            storage_fields=("whole","incremental","incremental_exclusive","packed_bytes","raw_table_bytes")
            rows.append(dict(pair=i, off_first=expected[2*(i-1)]["arm"]=="off", off_ns=off["elapsed_ns"],
                on_ns=on["elapsed_ns"], elapsed_off_over_on=wall, cpu_off_over_on=cpu(off)/cpu(on),
                off_cpu_us=cpu(off), on_cpu_us=cpu(on), git_off_ns=off["git_ns"], git_on_ns=on["git_ns"],
                off_allocated_bytes={k:off["storage"][k] for k in storage_fields},
                on_allocated_bytes={k:on["storage"][k] for k in storage_fields},
                allocation_delta={k:on["storage"][k]-off["storage"][k] for k in storage_fields},
                whole_allocation_on_over_off=on["storage"]["whole"]/off["storage"]["whole"]))
        ratios=[r["elapsed_off_over_on"] for r in rows]
        out={"observations":rows,"median_paired_elapsed_speedup":geometric_median(ratios),
             "median_paired_cpu_speedup":geometric_median([r["cpu_off_over_on"] for r in rows]),
             "minimum_and_maximum_paired_elapsed":[min(ratios),max(ratios)],
             "order_specific_median_elapsed":{label:geometric_median([r["elapsed_off_over_on"] for r in rows if r["off_first"]==first]) for label,first in (("off_first",True),("on_first",False))},
             "pairs_exceeding_2x":sum(v>2 for v in ratios)}
        if stage=="confirmation" and phase in ("return-A","return-B"):
            out["simultaneous_elapsed_interval"]=median_interval(ratios)
        effects[phase]=out
    if stage=="pilot":
        go=all(o["off_ns"]>2*o["on_ns"] for phase in ("return-A","return-B") for o in effects[phase]["observations"])
    else:
        go=all(effects[ph]["simultaneous_elapsed_interval"][0]>2 for ph in ("return-A","return-B"))
    result = dict(stage=stage,pairs=n,go=go,effects=effects)
    if stage=="confirmation":
        result["randomization_over_216_assignments"]={str(m):randomization(effects,m) for m in (1,2)}
    return result

def self_test(plan):
    slots=schedule(plan)
    require(slots==plan["schedule"] and len(slots)==28 and len({s["slot"] for s in slots})==28, "frozen orders")
    for block in range(3):
        rows=slots[4+block*8:4+(block+1)*8:2]
        require([v["arm"] for v in rows].count("off")==2,"independent block balance")
    require(median_interval(list(range(1,13)))==[3,11], "rank bounds")
    require(median_interval([2]*12)==[2,2] and math.isclose(geometric_median([2,8]),4),"ties and paired estimator")
    uncertainty=(sum(math.comb(12,i) for i in range(3))+sum(math.comb(12,i) for i in range(11,13)))/2**12
    require(math.isclose(1-2*uncertainty,0.955078125),"simultaneous family coverage")

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan",type=Path,default=HERE/"plan.json")
    ap.add_argument("--stage",choices=("pilot","confirmation"))
    ap.add_argument("observations",type=Path,nargs="?")
    args=ap.parse_args()
    plan=json.loads(args.plan.read_bytes());self_test(plan)
    if args.observations:
        require(args.stage is not None,"choose --stage")
        d=json.loads(args.observations.read_bytes())
        print(json.dumps(compute(plan,d,args.stage),indent=2,sort_keys=True))
    else:
        print(json.dumps({"independent_confirm_pairs":12,"pilot_pairs":2,"physical_installations":28,"simultaneous_coverage_lower_bound":0.955078125},sort_keys=True))
if __name__=="__main__":
    main()
