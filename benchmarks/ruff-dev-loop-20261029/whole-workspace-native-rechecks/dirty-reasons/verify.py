#!/usr/bin/env python3
import argparse
import collections
import copy
import gzip
import hashlib
import json
from pathlib import Path

def counts(observation, paired):
    rows = observation["actual_full"]
    assert observation["comparable"] and observation["active_units"] == 619
    assert observation["cargo_dirty_typed"] == 186 and observation["dirty_lines"] == 187
    assert len(rows) == len({r["unit"] for r in rows}) == 119
    assert observation["native"]["rustc-full"] == 119 and observation["native"].get("rustc-cached", 0) == 0
    assert all(observation["native"][kind] == 103 for kind in ["gcc", "collect2", "wild"])
    assert paired["unchanged_full_fresh_wild_extra"]["W-7277"] == [119, 433, 103, 53]
    assert paired["unchanged_full_fresh_wild_extra"]["W-K"] == [107, 470, 103, 53]
    reason_counts = collections.Counter()
    for row in rows:
        reasons = row["reason_classes"]
        details = row["details"]
        assert len(reasons) == 1 and details and row["matching_rows"] >= 1
        assert row["raw_log_line_pairs"] and row["matching_rows"] >= len(row["raw_log_line_pairs"])
        assert all(len(v) == 64 and int(v, 16) >= 0 for pair in row["raw_log_line_pairs"] for v in pair)
        assert len(row["actual_argv"]) == 64 and int(row["actual_argv"], 16) >= 0
        if reasons == ["dependency-fingerprint"]:
            assert all(v.startswith("unit-") and v[5:].isdigit() for v in details)
            reason_counts[reasons[0]] += 1
        else:
            assert len(details) == 1 and reasons[0] in ("MissingChecksum", "MissingFile")
            reason_counts[reasons[0] + "/" + details[0]] += 1
    assert dict(reason_counts) == observation["reason_by_full"] == {
        "dependency-fingerprint": 101, "MissingChecksum/ohm-recheck-dependent-links": 8,
        "MissingFile/ohm-recheck-dependent-links": 7, "MissingFile/ohm-untracked-relink-inputs": 2,
        "MissingFile/ohm-foreign-span-bytes": 1,
    }
    marker_rows = [r for r in rows if r["details"] == ["ohm-recheck-dependent-links"]]
    removed = {r["unit"]:r["package"] for r in marker_rows if r["kind"] == ["lib"] and not r["cargo_profile_test"]}
    assert removed == {r["unit"]:r["package"] for r in paired["compiler_jobs_saved_by_K"]}
    assert sorted(removed) == observation["saved_units"] and len(removed) == 12
    assert sorted(r["package"] for r in marker_rows if r["cargo_profile_test"]) == ["ty_ide", "ty_module_resolver", "ty_python_semantic"]
    assert sorted(r["package"] for r in rows if r["details"] == ["ohm-untracked-relink-inputs"]) == ["libm", "portable-atomic"]
    assert [r["package"] for r in rows if r["details"] == ["ohm-foreign-span-bytes"]] == ["ron"]
    return {"actual_full":len(rows), "lost_library_launches":len(removed), "immediate":dict(reason_counts)}

def main():
    ap = argparse.ArgumentParser(description="Verify the W/7277 unchanged-workspace compiler dirty-reason projection.")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    p = Path(__file__).resolve().parent
    names = set()
    for line in (p / "SHA256SUMS").read_text().splitlines():
        value, name = line.split("  ")
        assert name not in names and "/" not in name and hashlib.sha256((p/name).read_bytes()).hexdigest() == value
        names.add(name)
    assert {q.name for q in p.iterdir() if q.is_file()} == names | {"SHA256SUMS"}
    data = json.loads(gzip.decompress((p / "observations.json.gz").read_bytes()))
    raw = (p / "paired-census.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == data["independent_paired_census"]["report"]
    assert data["independent_paired_census"]["manifest"] == "0ee56569be5dde4d53197036487f385e3b6604a2d73e0ef3fee24d7484693c4f"
    history = json.loads(raw)
    result = counts(data, history)
    if args.self_test:
        for name in ("drop-compile","provider-marker-for-foreign-span","wrong-arm-link-count","wrong-saved-identity"):
            a,b=copy.deepcopy(data),copy.deepcopy(history)
            if name == "drop-compile":
                a["actual_full"].pop()
            elif name == "provider-marker-for-foreign-span":
                next(r for r in a["actual_full"] if r["package"]=="ron")["details"]=["ohm-recheck-dependent-links"]
            elif name == "wrong-arm-link-count":
                b["unchanged_full_fresh_wild_extra"]["W-K"][2] -= 1
            else:
                a["saved_units"][0] = "0"*16
            try: counts(a,b)
            except AssertionError: continue
            raise ValueError("mutation passed " + name)
        result["mutations_rejected"] = 4
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
