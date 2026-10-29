"""Select state transitions, actual direct .rmeta inputs and timing bounds from two preexisting censuses."""
from decimal import Decimal
from pathlib import Path
import hashlib
import json
import re
import sys

root, previous, output = map(Path, sys.argv[1:])
def read(path):
    return json.loads(path.read_bytes())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def nsec(seconds):
    return int(Decimal(seconds) * 1_000_000_000)

# Cargo enumerates its sorted unit graph. The 47 historical hash-to-unit witnesses
# distinguish profiles that share a crate name. Both fresh censi use the same 510 typed units.
old = read(previous)["phases"]["parent-edit"]["rustcs"]
names = {r["extra_filename"]: (r["completed_unchanged_local_hash"]["unit"], r["crate"]) for r in old if r.get("completed_unchanged_local_hash")}
assert len(names) == 47
leaf = {
    "05cbcd96d2a0befa": (330, "ruff_benchmark", "ty_project"),
    "9820abbac11acab0": (333, "ruff_dev", "ruff_workspace"),
    "220cc7862f3e1306": (466, "ty", "ty_server"),
    "3a4e79a3902250ba": (470, "ty_completion_bench", "ty_ide"),
    "e62e82fbd090fa46": (471, "ty_completion_eval", "ty_ide"),
}
names.update({s: (i, n) for s, (i, n, _) in leaf.items()})
lookup = {i: n for i, n in names.values()}
sources = [("ruff_python_index", "ruff_python_ast"), ("ruff_python_literal", "ruff_python_ast"), ("ruff_graph", "ruff_linter"), ("ty_test", "ty_python_semantic"), ("ty_project", "ty_python_semantic")]
phase_data = {}
def command(arm, direction, phase):
    d = root / arm / f"{direction}-{phase}"
    events = read(d / "native.json")
    status = read(d / "status.json")
    typed = [r for r in map(json.loads, (d / "cargo.jsonl").read_bytes().splitlines()) if r["reason"] == "compiler-artifact"]
    assert len(typed) == 510 and events["root_exit"] == status["rc"] == 0
    assert set(events["process_exit"].values()) == {0}
    assert status["stdout_sha256"] == sha(d/"cargo.jsonl") and status["stderr_sha256"] == sha(d/"stderr")
    stderr = (d / "stderr").read_text()
    real = []
    for e in events["events"]:
        if e["role"] != "rustc-full":
            continue
        args = e["argv"]
        stem = next(t.partition("=-")[2] for t in args if t.startswith("extra-filename=-"))
        real.append((stem, e["target"], args, e["argv_sha256"]))
    state = {int(idx): {"t_ns": nsec(t), "local_hash": v, "may_have_changed": "must rebuild" in msg} for t, idx, v, msg in re.findall(r"([\d.]+)s.*?early_cutoff: unit UnitIndex\((\d+)\) built with unchanged public API hash v1:([0-9a-f]+)([^\n]*)", stderr)}
    decision = {int(idx): {"t_ns": nsec(t), "message": msg} for t, idx, msg in re.findall(r"([\d.]+)s.*?early_cutoff: unit UnitIndex\((\d+)\) ((?:CAN|CANNOT) skip[^\n]+)", stderr)}
    metadata = set(re.findall(r'dependency on `(\w+)` is newer than we are [^\n]*?"/[^"]*/crates/(\w+)"', stderr))
    raw = {n: sha(d / n) for n in ("native.json", "cargo.jsonl", "stderr", "status.json", "summary.json")}
    basic = {"raw": raw, "rustc": len(real), "typed": len(typed), "typed_dirty": sum(not r["fresh"] for r in typed),
             "stale_mtime": sorted(f"{provider} -> {consumer}" for provider, consumer in metadata), "rustc_sha256": events["images"]["rustc"]["sha256"],
             "cargo_sha256": events["images"]["cargo"]["sha256"]}
    if phase != "edit":
        return basic
    product = {}
    for stem, name, args, _ in real:
        if stem in names:
            i, n = names[stem]
            assert n == name
            product[str(Path(args[args.index("--out-dir")+1]) / f"lib{name}-{stem}.rmeta")] = i
    graph = {}
    for stem, name, args, _ in real:
        if stem not in names:
            continue
        i = names[stem][0]
        graph[i] = {product[path] for pos, arg in enumerate(args[:-1]) if arg == "--extern" and (path := args[pos+1].partition("=")[2]) in product}
    by_name = {n: i for i, n in names.values() if n not in ("ruff_source_file", "ruff_text_size", "ruff_python_trivia", "ty", "ruff")}
    early = []
    for consumer, producer in sources:
        c, p = by_name[consumer], by_name[producer]
        assert p in graph[c]
        early.append({"consumer": consumer, "provider": producer, "provider_finish_after_consumer_ns": state[p]["t_ns"] - state[c]["t_ns"],
                      "consumer_declared_changed": state[c]["may_have_changed"], "producer_declared_changed": state[p]["may_have_changed"]})
    extras = []
    for stem, (i,n,dep) in leaf.items():
        dep_id = by_name[dep]
        row = {"stem": stem, "name": n, "id": i, "blocker_on_B": dep, "decision": decision[i], "blocker_report_ns": state[dep_id]["t_ns"], "blocker_changed": state[dep_id]["may_have_changed"]}
        rows = [r for r in typed if r["target"]["name"] == n and (("bin" in r["target"]["kind"]) if n != "ruff_benchmark" else ("lib" in r["target"]["kind"]))]
        assert len(rows) == 1 and not rows[0]["fresh"]
        row["typed_target_kind"] = rows[0]["target"]["kind"]
        if arm == "B":
            found, = [(args, digest) for s, _, args, digest in real if s == stem]
            row["argv_sha256"] = found[1]
            assert dep_id in graph[i] and f"dep '{dep}' has build_state=BuiltChanged" in row["decision"]["message"]
            assert "--emit=dep-info,metadata" in found[0]
            row["direct_input"] = sorted({Path(arg.split("=",1)[1]).name for j, arg in enumerate(found[0][1:]) if found[0][j]=="--extern" and arg.startswith(dep+"=")})
            if i in state:
                row["job_final_hash_log_ns"] = state[i]["t_ns"]
        else:
            assert all(s != stem for s,_,_,_ in real) and row["decision"]["message"] == "CAN skip - all deps allow early cutoff"
        assert row["decision"]["t_ns"] > row["blocker_report_ns"]
        extras.append(row)
    finish = re.search(r'Finished .+? in ([\d.]+)s', stderr)
    dirty_names = {r for r in re.findall(r'package_id=(\w+) [^\n]+? target="([^"]+)"}: [^\n]+? dirty: ([^\n]+)',stderr)}
    early_units = {c for c,_ in sources}
    basic.update({"parsed_rustc_roster":[{"stem": s, "name": n} for s,n,_,_ in real],
                  "decisions": extras, "five_candidate_early_edges": early,
                  "named_early_workers_prepared_dirty_reason": {n: sorted({reason for pkg, target, reason in dirty_names if pkg == n and target==n}) for n in sorted(early_units)},
                  "terminal_states": {f"{i}/{lookup.get(i,'unmapped')}": row for i,row in sorted(state.items())},
                  "logical_rmeta_edges": {f"{i}/{lookup[i]}": sorted(f"{idx}/{lookup[idx]}" for idx in edges) for i, edges in sorted(graph.items())},
                  "last_external_rustc": real[-1][1], "last_common_hash_log_ns":max(r["t_ns"] for i,r in state.items() if i not in {x[0] for x in leaf.values()}),
                  "reported_cargo_finish_ns": nsec(finish[1])})
    return basic

for arm in "AB":
    phase_data[arm]={}
    for direction in ("parent", "child"):
        phase_data[arm][direction] = {phase: command(arm,direction,phase) for phase in ("edit", "repeat-1", "repeat-2")}
out={"previous_unit_binding_sha256":sha(previous),"phase_data":phase_data}
output.write_text(json.dumps(out, sort_keys=True, indent=2)+"\n")
