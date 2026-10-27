"""Summarize every admitted native identity, whole artifact and new ordinary Rust reader."""
import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parent
sys.path.insert(0, str(base / "run"))
from wire import read as read_source_map

def load(path):
    return json.loads(path.read_bytes())

def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def compare(rows, first, second):
    left, right = rows[first], rows[second]
    return {
        name: left[name] == right[name]
        for name in ("public", "private", "metadata_sha256", "rlib_sha256")
    }

order = ("chain-original", "chain-edited", "chain-restored", "empty-edited", "empty-original")
groups = []
for identity in load(base / "complete.json")["result"]:
    block, arm = identity["block"], identity["arm"]
    group = base / f"block-{block}" / arm
    rows = {}
    for label in order:
        record = load(group / label / "result.json")
        rows[label] = {
            "public": record["header"]["public"],
            "private": record["header"]["private"],
            "stable_crate_id": record["header"]["stable_crate_id"],
            "metadata_sha256": record["metadata_sha256"],
            "rlib_sha256": record["rlib_sha256"],
        }
        if block == 1 and label in ("chain-edited", "empty-edited"):
            raw = base / "raw-rmeta" / (record["metadata_sha256"] + ".rmeta")
            assert file_sha(raw) == record["metadata_sha256"]
            decoded = read_source_map(raw, base / "binding/edited-docstring.rs", "docstring.rs")
            assert decoded == record["physical_source"]
            assert decoded["lines"] == 1744 and decoded["normalized_bytes"] == 52874
    callers = {}
    for receipt in sorted(group.glob("ordinary-caller-*/result.json")):
        r = load(receipt)
        callers[receipt.parent.name.removeprefix("ordinary-caller-")] = {
            "exit": r["status"],
            "diagnostic_codes": r["codes"],
            "output_metadata_sha256": r.get("out_rmeta_sha256"),
        }
    native = load(group / "summary.json")["edited_native_comparison"]
    assert native["cgu_objects"] == [171, 171]
    groups.append({
        "block": block, "arm": arm, "observed_outputs": rows,
        "raw_and_identity_equal": {
            "edited_warm_vs_empty": compare(rows, "chain-edited", "empty-edited"),
            "restored_vs_empty_original": compare(rows, "chain-restored", "empty-original"),
            "empty_original_vs_second_empty_original": compare(rows, "chain-original", "empty-original"),
        },
        "edited_native_member_comparison": native,
        "ordinary_new_callers": callers,
    })
print(json.dumps({
    "groups": groups,
    "reader_endpoint": "rustc --emit=metadata, with codes and absence/presence of the new rmeta recorded; no executable issued or run.",
    "wire_oracles_independently_reread": 4,
}, indent=2))
