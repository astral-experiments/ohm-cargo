#!/usr/bin/env python3
"""Deliberately small source-only tests. No synthetic observation is scored."""
import copy
import importlib.util
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location("analyze",HERE/"analyze.py")
a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
plan=json.loads((HERE/"plan.json").read_bytes())
def test_projection():
    # Explicitly synthetic observations exercise the contract of both stages.
    proof="f"*64
    references={}
    for arm in a.ARMS:
        phases={}
        for phase in a.PHASES:
            cold=phase=="empty-A"; fresh=phase=="unchanged-B"
            phases[phase]=dict(independent_empty_full_file_equality=True,raw_native_result=proof,
                cli=dict(sha256=proof,bytes=2_000_000),reader=dict(sha256=proof,bytes=1_500_000),
                verdict_sha256=proof,dirty_set_sha256=proof,real_rustc=379 if cold else 0 if fresh else 20,
                real_wild=69 if cold else 0 if fresh else 1)
        references[arm]=phases
    common=dict(source=plan["compiler_source"],cargo=plan["cargo_source"],native_independent_terminal=proof,
                physical_sdk_sha256=proof,observed_flag={"off":None,"on":plan["on_flag"]},native_reference=references,
                cross_option={k:dict(verdict_equal=True,ordinary_caller_equal=True) for k in "AB"})
    for stage in ("pilot","confirmation"):
        slots=[]
        for row in (x for x in a.schedule(plan) if x["stage"]==stage):
            arm=row["arm"];visits=[]
            for phase in a.PHASES:
                native=references[arm][phase]; packed=512 if arm=="on" and phase!="empty-A" else 0
                storage=dict(whole=2048+packed,target=1536+packed,shared=1024,shared_names=512,
                    incremental=1024+packed,incremental_exclusive=1024+packed,incremental_also_outside=0,
                    packed_bytes=packed,raw_table_bytes=512,filesystem_used=2048+packed,working_sessions=0,ledger_sha256=proof)
                visits.append(dict(phase=phase,source=plan["ruff"][phase[-1]],exit=0,typed_units=375,
                    dirty_units=375 if phase=="empty-A" else 0 if phase=="unchanged-B" else 20,
                    graph_sha256=plan["graph_sha256"],**{k:native[k] for k in ("cli","reader","verdict_sha256","dirty_set_sha256")},
                    result_sha256=proof,process_sha256=proof,elapsed_ns=31 if arm=="off" else 10,
                    user_cpu_us=20,system_cpu_us=1,git_ns=1,storage=storage))
            slots.append(dict(**row,physical_sdk_sha256=proof,physical_sdk_entries=57,empty_workspace=True,
                    actual_front_gate=True,front_sha256=proof,completion_sha256=proof,visits=visits))
        doc=dict(**common,slots=slots);result=a.compute(plan,doc,stage)
        assert result["go"] and result["effects"]["return-A"]["observations"][0]["allocation_delta"]["whole"]==512
        # Preserve ties at exactly 2x, and refuse mismatched native products.
        for slot in slots:
            for visit in slot["visits"]:
                if visit["phase"]=="return-B" and slot["arm"]=="off":visit["elapsed_ns"]=20
        assert not a.compute(plan,doc,stage)["go"]
        slots[0]["visits"][0]["reader"]=dict(sha256="0"*64,bytes=1_500_000)
        try:a.compute(plan,doc,stage)
        except ValueError:pass
        else:raise AssertionError("unmatched reader entered scores")
def test():
    a.self_test(plan)
    test_projection()
    # Constant outcomes make every assignment an exact tie at its specified sharp null.
    zero={d:{"observations":[{"off_ns":2,"on_ns":1,"off_first":i%2==0} for i in range(12)]}
          for d in ("return-A","return-B")}
    out=a.randomization(zero,2)
    assert all(v["raw_p"]==v["family_max_p"]==1 for v in out.values())
    # Populate matching random order and an equal effect in both directions.
    for v in zero.values():
        for i,row in enumerate(v["observations"]):
            row["off_first"]=(plan["schedule"][4+2*i]["arm"]=="off")
    out=a.randomization(zero,1)
    assert all(math.isclose(v["raw_p"],1/216) and v["family_max_p"]==v["raw_p"] for v in out.values())
    assert a.median_interval([1,1]+[2.1]*10)==[2.1,2.1]
    assert a.median_interval([1,1,2]+[2.1]*9)[0]==2
    order=copy.deepcopy(plan);order["order_draw_bytes"][0]=[0,252]
    try:a.schedule(order)
    except ValueError:pass
    else:raise AssertionError("invalid rejected draw accepted")
    print("Exact plan, paired ranks, ties, 216-assignments nulls and mutation guard passed.")
if __name__=="__main__":
    test()
