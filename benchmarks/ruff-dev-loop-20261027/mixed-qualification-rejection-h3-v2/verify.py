"""Replay the immutable failed admission and the two independent causal controls."""
import gzip
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

here = Path(__file__).resolve().parent
read = lambda p: json.loads(p.read_bytes())
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
record = here / "record"
gate = read(record / "rejection.json")
assert gate["rc"] == 1 and gate["no_scores"] and gate["no_test_mode"]
assert len(gate["primary_declared_mismatches"]) == 3 and gate["failure_sha"] == digest(record / "failure.txt")
all_commands = read(record / "all-completed-commands.json")
assert len(all_commands) == 35 and all(row["status"] == 0 and row["units"] == 501 for row in all_commands.values())
for arm in "ABC":
    command = all_commands[f"{arm}/first-edit"]
    assert command["wild"] == 8 and command["jobs"] == ({"full": 1, "checked-native": 2, "link-only": 6} if arm == "C" else {"full": 3, "link-only": 6})
    assert all_commands[f"{arm}/first-edit-fresh"]["fresh"] == 501
clone = read(record / "cloned-state-proof.json")
assert clone["distinct"] == 922 and clone["all_different_inodes"]

with tempfile.TemporaryDirectory() as tmp:
    dest = Path(tmp) / "metadata.json"
    subprocess.run([sys.executable, "-B", here / "source/localize-mixed-metadata.py", record, dest], stdout=subprocess.DEVNULL, check=True)
    raw = read(dest)
    for name, n in [("ruff_wasm", 66), ("ty_wasm", 78)]:
        for key in ("A-first-edit__gold-A-cold", "B-first-edit__gold-B-cold", "C-first-edit__gold-B-cold"):
            md = raw[key][name]
            assert md["diff_bytes_same_positions"] > 0 and md["root_or_tail_diff_bytes"] >= 32
            assert md["dependency_hash_mismatch_count"] > 0 and any(x.startswith("get_size_derive2-") for x in md["dependency_differences"])
            for item in ("public_svh", "private_svh", "rmeta_sha256"):
                assert len(set(md["identities"][item])) == 2
            assert len(set(md["identities"]["stable_crate_id"])) == 1
            assert md["raw_elf_equal"] and md["c_exports_equal"] and md["all_native_objects_equal"] and md["object_count"] == n
        matched = raw["C-first-edit__forced-C-forced-edit"][name]
        assert matched["diff_bytes_same_positions"] == 0 and matched["dependency_differences"] == {}
        assert matched["raw_elf_equal"] and matched["all_native_objects_equal"] and matched["symbol_to_member_ordinal_equal"]

base = here / "readers-ablation"
rows = read(base / "all-readers.json")
exits = read(base / "actual-rustc-exits.json")
assert read(base / "complete.json")["rows"] == len(rows) == 30
failures = []
for row in rows:
    loc = base / row["case"] / "receipt"
    assert exits[row["case"]] == row["status"]
    assert digest(loc / "argv.json") == row["argv_sha"] and read(loc / "argv.json") == row["argv"]
    assert (loc / "stderr").read_text() == row["stderr"]
    if row["status"] == 1:
        assert row["codes"] == ["E0460"] and "error[E0460]" in row["stderr"]
        required = "ruff_db" if row["case"].endswith("independent-full-direct") else row["crate"]
        assert re.search(rf"possibly newer version of crate `{required}`", row["stderr"])
        failures.append(row["case"])
    else:
        assert row["status"] == 0 and not row["codes"]
        if row["action"] == "caller":
            assert row["runtime"] == ("0.17.0" if row["crate"] == "ruff_wasm" else "93526150d")
assert len(failures) == 10
assert all("versus-guarded-C" not in c and not c.startswith("C-") for c in failures)

macro = here / "registry-macro-v2"
data = read(macro / "complete.json")
assert data["no_timing"] and data["primary_failure_unchanged"]
values, text = set(), set()
for arm in "ABC":
    actual = data["arms"][arm]
    assert len(actual["actual_probe_diagnostics"]) == 1
    diagnostic = actual["actual_probe_diagnostics"][0]
    assert diagnostic in [json.loads(line)["message"] for line in (macro / f"{arm}-conflict.stderr").read_bytes().splitlines()]
    values.add(diagnostic)
    text.add(actual["compiled_plugins"]["get_size_derive2"]["sections"][".text"]["sha256"])
assert len(values) == len(text) == 3
orders = set()
for tag, v in data["arms"]["same_B_repeated_expansions"].items():
    path = macro / f"expanded-{tag}.rs"
    assert digest(path) == v["expanded_rust_sha256"]
    pairs = re.findall(r'"`(size|size_fn|ignore)` conflicts with mutually exclusive `(size|size_fn|ignore)`"', path.read_text())
    order = tuple(dict.fromkeys((a, b) for a, b in pairs if a < b))
    assert order == tuple(map(tuple, v["conflict_order"]))
    orders.add(order)
assert len(orders) == 4 and len(data["arms"]["same_B_repeated_expansions"]) == 8
print("Verified 35 unscored qualifying Cargo commands, three rejected raw cold oracles, 30 Rust readers (10 E0460), and four branch orders on eight identical-input expansions.")
