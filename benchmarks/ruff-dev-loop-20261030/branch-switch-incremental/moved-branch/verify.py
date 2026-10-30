"""Check the captured branch ref movements, real fixture verdicts, native links and empty references."""
import gzip
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
spec = json.loads((root / "source.json").read_bytes())
data = json.loads(gzip.decompress((root / "projection.json.gz").read_bytes()))
assert hashlib.sha256(gzip.decompress((root / "parser-validation.patch.gz").read_bytes())).hexdigest() == spec["patch_sha256"]
assert spec["A"] != spec["D"] and spec["A_tree"] == spec["D_tree"] != spec["C_tree"]
assert data["cold_elfs"]["A"]["reader"] != data["cold_elfs"]["C"]["reader"]
assert data["cold_elfs"]["A"]["test"] != data["cold_elfs"]["C"]["test"]
rows = data["phases"]
phases = {"empty-C":"C", "empty-A":"A", "first-B":"B", "return-moved-C":"C", "return-B":"B", "return-restored-D":"D"}
assert set(rows) == {arm + "-" + phase for arm in "PQ" for phase in phases}
traces = 0
for arm in "PQ":
    for phase, key in phases.items():
        tag = arm + "-" + phase
        row = rows[tag]
        assert (row["git"], row["tree"]) == (spec[key], spec[key + "_tree"])
        assert (row["typed"], row["tests"]) == (152, 557)
        assert row["upstream_test"] == "inline_err::signed_pattern_non_literal_operand.py"
        commands = row["commands"]
        assert all(cmd["exit"] == 0 for name, cmd in commands.items() if name != "upstream-test")
        assert row["test_exit"] == commands["upstream-test"]["exit"] == (101 if key == "C" else 0)
        expected = "accepted" if key == "C" else "rejected"
        assert row["verdict"] == f"Expr={56 if key == 'B' else 64} signed-expression={expected}"
        if key != "B":
            empty = data["cold_elfs"]["C" if key == "C" else "A"]
            assert row["reader_elf"] == empty["reader"] and row["test_elf"] == empty["test"]
        if "kernel_gzip" not in row:
            continue
        traces += len(row["kernel_gzip"])
        assert row["kernel_wild"] == 1
        assert sorted(row["kernel_compilers"]) == ["fixtures", "ruff_python_ast", "ruff_python_parser"]
        remembered, previous = ("empty-A", "first-B") if key == "C" else ("return-moved-C", "return-B")
        for crate, source in data["kernel_session_sources"][tag].items():
            assert source["origin"] == (remembered if arm == "Q" else previous)
            for candidate in (remembered, previous):
                other = rows[arm + "-" + candidate]
                crate_id, = [name for name in other["sessions_after"] if name.split("-")[0] == crate]
                created = set(other["sessions_after"][crate_id]) - set(other["sessions_before"].get(crate_id, ()))
                assert (source["session"] in created) == (source["origin"] == candidate)
        assert set(data["kernel_session_sources"][tag]) == {"fixtures", "ruff_python_ast", "ruff_python_parser"}
assert traces == data["native_traces"] == 1132
print("Verified two moved branches, four actual relinks, all 12 Cargo builds, and both clean executable pairs.")
