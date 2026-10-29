import json
from pathlib import Path

p=Path(__file__).resolve().parent
result=json.loads((p/"roster.json").read_bytes())["phase_data"]
leaf={"ty_completion_bench":"ty_ide","ty_completion_eval":"ty_ide","ty":"ty_server","ruff_benchmark":"ty_project","ruff_dev":"ruff_workspace"}
for direction, initial_repeat in (("parent",24),("child",12)):
    a, b = (result[k][direction] for k in "AB")
    assert [a[k]["rustc"] for k in ("edit","repeat-1","repeat-2")] == [51,initial_repeat,1]
    assert [b[k]["rustc"] for k in ("edit","repeat-1","repeat-2")] == [56,1,1]
    assert all(d["typed"] == 510 for source in (a,b) for d in source.values())
    assert a["edit"]["typed_dirty"] == b["edit"]["typed_dirty"] == 56
    assert all(not r["stale_mtime"] for r in (a["edit"], b["edit"],b["repeat-1"],a["repeat-2"],b["repeat-2"]))
    stale = ["ruff_python_ast -> ruff_python_index"]
    if direction=="parent":
        stale.append("ruff_python_ast -> ruff_python_literal")
    assert a["repeat-1"]["stale_mtime"] == stale
    def units(edit):
        return {(r["stem"],r["name"]) for r in edit["parsed_rustc_roster"]}
    initial, candidate = a["edit"],b["edit"]
    assert units(initial) < units(candidate)
    assert {v[1] for v in units(candidate)-units(initial)} == set(leaf)
    assert candidate["last_external_rustc"] == "ruff_dev"
    times=[]
    for old,new in zip(initial["decisions"],candidate["decisions"],strict=True):
        assert old["name"] == new["name"] and old["blocker_on_B"] == new["blocker_on_B"] == leaf[new["name"]]
        assert not old["blocker_changed"] and new["blocker_changed"]
        assert old["decision"]["message"] == "CAN skip - all deps allow early cutoff"
        assert new["decision"]["message"] == f"CANNOT skip - dep '{leaf[new['name']]}' has build_state=BuiltChanged"
        assert old["decision"]["t_ns"] > old["blocker_report_ns"] and new["decision"]["t_ns"] > new["blocker_report_ns"]
        assert len(new["direct_input"])==1 and new["direct_input"][0].endswith(".rmeta")
        times.append(new["decision"]["t_ns"])
    for edge in candidate["five_candidate_early_edges"]:
        if edge["consumer"] in {"ruff_python_index", "ty_project", "ruff_graph", "ty_test"}:
            assert edge["provider_finish_after_consumer_ns"]>0 and edge["consumer_declared_changed"]
    bench, = [row for row in candidate["decisions"] if row["name"]=="ruff_benchmark"]
    print(direction, {
        "five_extra_pct_of_repeat_count_reduction": round(500/(initial_repeat-1),2),
        "end_after_first_denial_ms":round((candidate["reported_cargo_finish_ns"]-min(times))/1e6,2),
        "end_after_last_denial_ms":round((candidate["reported_cargo_finish_ns"]-max(times))/1e6,2),
        "benchmark_denial_to_final_hash_ms":round((bench["job_final_hash_log_ns"]-bench["decision"]["t_ns"])/1e6,3),
    })
