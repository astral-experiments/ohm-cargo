"""Recompute the paired statistics and compare every executable to its empty-target reference."""
from collections import Counter
import json
from pathlib import Path
import runpy

here=Path(__file__).resolve().parent
analyze=runpy.run_path(str(here/"analyze.py"))["analyze"]
read=lambda p:json.loads((here/p).read_bytes())
plan,subjects=read("plan.json"),read("subjects.json")
rows={r["phase"]:r for r in read("commands.json")}
assert len(rows)==114 and sum(r["timed"] for r in rows.values())==48
assert sum(bool(r["images"]) for r in rows.values())==66 and all(r["status"]==0 for r in rows.values())
assert subjects["sha256"]["P"]==plan["cargo_parent"] and subjects["sha256"]["C"]==plan["cargo_candidate"]
assert subjects["sha256"]["driver"]==plan["driver"] and subjects["source_manifest"]==plan["fixture_manifest"]
old,new=(rows[f"empty-{i}"] for i in (0,1))
gold={v["source"]:v["native_products"] for v in (old,new)}
assert len(gold)==2 and all(r["native_products"]==gold[r["source"]] for r in rows.values())
for name in old["native_products"]:
    assert (old["native_products"][name]["output"] == new["native_products"][name]["output"]) == (name=="hold_plain")
for step in plan["orders"]:
    for phase in ("noop","edit"):
        for arm in "PC":
            k=f"{step['block']:02}-{phase}-{arm}"
            r=rows["audit-"+k]
            assert bool(r["images"]) and not r["timed"] and rows["native-"+k]["timed"]
            assert r["source"] == rows["native-"+k]["source"]
            expected = ({"full":2,"relink":1} if arm=="P" else {}) if phase=="noop" else {"full":4,"relink":1}
            assert Counter(x["mode"] for x in r["roster"])==expected
            if arm=="C":
                assert len(r["readers"])==2 and all(v["complete"] and v["valid_trailer"] for v in r["readers"])
assert analyze(rows,plan)==read("analysis.json")
print("Verified both statistical endpoints, 48 timed commands, 66 process audits, and three complete native binaries per command.")
