"""Verify each preserved libtest verdict against the independently enumerated executable."""
from pathlib import Path
import hashlib
import json
import re

root = Path(__file__).resolve().parent
results = json.loads((root/"results.json").read_text())
assert results["commit"] == "78bedbdaafd7cda72bee7c844888b44f3b902c61"
assert results["tree"] == "97fa889de60375779cb151d241654258025f9ae5" and results["files"] == 3108
assert results["test_binary"] == "aae373cddb590ecc04db2605b0acb13952226600cd2f5327935939621e698c99"
inventory = (root/"inventory.txt").read_bytes()
assert hashlib.sha256(inventory).hexdigest() == results["raw_sha256"]["complete-library-v2/inventory.txt"]
assert results["raw_sha256"]["complete-library/inventory.txt"] == results["raw_sha256"]["complete-library-v2/inventory.txt"]
names = sorted(row.removesuffix(": test") for row in inventory.decode().splitlines() if row.endswith(": test"))
assert names == results["complete_names"] and len(set(names)) == len(names) == 407
filtered = sorted(n for n in names if n.startswith("compiler::relink_cache_tests::"))
assert filtered == results["filtered_names"] and len(filtered) == 9
for file, expected, summary in zip(
    ["filtered.txt","complete-first.txt","complete-second.txt"],
    [filtered,names,names],
    [results["filtered_result"],*results["full_results"]],
    strict=True,
):
    lines = (root/file).read_text().splitlines()
    assert lines[0] == f"running {len(expected)} tests" and lines[-1] == summary
    assert len(lines) == len(expected) + 2
    rows = [re.fullmatch(r"test (\S+?)( - should panic)? \.\.\. ok",line) for line in lines[1:-1]]
    assert all(rows) and sorted(row[1] for row in rows) == expected
    panics = sorted(row[1] for row in rows if row[2])
    assert panics == (results["expected_panics"] if expected == names else [])
    assert f"{len(expected)} passed; 0 failed; 0 ignored" in summary
assert len(results["expected_panics"]) == 4
assert all(re.fullmatch("[a-f0-9]{64}",v) for v in results["raw_sha256"].values())
print("Verified the exact nine focused tests and all 407 names and verdicts in both full invocations.")
