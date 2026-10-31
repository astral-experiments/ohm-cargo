"""Check the archived Cargo verdicts, profile stdout and PR workflow survey."""
import collections
import csv
import gzip
import hashlib
import json
from pathlib import Path

base = Path(__file__).resolve().parent
receipt = json.loads((base / "receipt.json").read_text())
for name, expected in receipt["offline_files"].items():
    assert hashlib.sha256((base / name).read_bytes()).hexdigest() == expected, name
with gzip.open(base / "verdicts.tsv.gz", "rt") as f:
    rows = list(csv.DictReader(f, delimiter="\t"))
assert len({(r["suite"], r["test"]) for r in rows}) == len(rows)
counts = collections.Counter((r["suite"], r["verdict"]) for r in rows)
assert counts == {("lib", "ok"): 410, ("cli", "ok"): 5, ("bench", "ignored"): 9,
                  ("integration", "ok"): 4405, ("integration", "ignored"): 423,
                  ("doc", "ok"): 3, ("doc", "ignored"): 1, ("shared", "ok"): 5,
                  ("clippy", "ok"): 8, ("profile", "ok"): 2}
final = receipt["qa_runs"][-1]
assert final["run"] == receipt["final_run"] and final["conclusion"] == "success"
assert all(h["failed"] == h["filtered"] == 0 for h in final["cargo_harnesses"])
for suite, names in final["actual_gated_names"].items():
    assert sorted(r["test"] for r in rows if r["suite"] == suite) == sorted(names)
for suffix in ("ohm_default_debuginfo", "ohm_default_debuginfo_respects_overrides"):
    name = f"profile_settings::{suffix}"
    stdout = (base / f"{suffix}.txt").read_text()
    assert stdout.splitlines().count(f"test {name} ... ok") == 1
    assert stdout.count("test result: ok. 1 passed; 0 failed; 0 ignored;") == 1
with (base / "open-pr-gate-audit.tsv").open() as f:
    audit = list(csv.DictReader(f, delimiter="\t"))
assert len(set(r["pr"] for r in audit)) == 167
assert collections.Counter(r["selector"] for r in audit) == {"stale-selector": 122, "no-explicit-selector": 45}
print("4823 standard passes, 433 ignored, 0 failed or filtered; 15 intended Ohm passes; 167 surveyed PR heads")
