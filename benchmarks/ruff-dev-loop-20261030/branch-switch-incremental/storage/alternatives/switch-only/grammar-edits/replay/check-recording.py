"""Rebuild the reviewer's exact commands from six original normal H9 Cargo receipts."""
from pathlib import Path
import gzip
import hashlib
import importlib.util
import json

here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("rerun", here / "replay-same-branch.py")
rerun = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rerun)
ledger = json.loads(gzip.decompress((here / "recorded-native-sample.json.gz").read_bytes()))
assert ledger["original_projection"] == "5ae6aa14a25ed7cdc0c55959878ab633429ed98c541241b8c8f64c97d581ded5"
assert ledger["definition"] == {"patch": rerun.sha(here / "parser-validation.patch"), "consumer": rerun.sha(here / "consumer.rs")}
assert len(ledger["samples"]) == 6
checks = []
for entry in ledger["samples"]:
    rows = []
    for r in entry["rows"]:
        if r["reason"] == "compiler-artifact":
            rows.append({**r, "target": {"kind": r["kind"], "name": r["name"]}})
        else:
            rows.append(r)
    units = [r for r in rows if r["reason"] == "compiler-artifact"]
    assert len(units) == entry["typed"] == 97
    assert sorted(r["target"]["name"] for r in units if not r["fresh"]) == entry["dirty"]
    assert rerun.cargo_argv() == entry["cargo"]
    cmd = rerun.reader_argv(units, rows, entry["supplemental_dirs_in_final_store"],
                            "/fixture/ops/consumer.rs", "/fixture/view/reader")
    assert cmd == entry["reader"], entry["slot"] + "/" + entry["phase"]
    state = entry["state"]
    assert entry["verdict"] == rerun.clean_verdict(state)
    assert entry["tree"] == rerun.TREES[state] and entry["grammar"] == rerun.PATTERN_SHA["C" if state == "C" else "B"]
    checks.append({"run": entry["slot"] + "/" + entry["phase"], "state": state, "dirty": len(entry["dirty"]),
                   "literal_reader_argv": hashlib.sha256(json.dumps(cmd, separators=(",", ":")).encode()).hexdigest(),
                   "verdict": entry["verdict"], "ELF": entry["ELF"]})
assert {r["state"] for r in checks} == set("ABC") and {r["dirty"] for r in checks} == {0, 1, 97}
assert len({r["ELF"] for r in checks}) == 3
print(json.dumps(checks, indent=2))
