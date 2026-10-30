"""Recompute the paired comparisons from the opted-in and default compiler records."""
import gzip
import json
from pathlib import Path
import math
from statistics import median

ROOT = Path(__file__).resolve().parent
RETURNS = ("return-A", "return-B")
PHASES = {"empty-A", "first-B", "return-A", "return-B", "unchanged-B"}


def read_result(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def verify_product():
    data = json.loads((ROOT / "compiler.json").read_bytes())
    assert len(data["sdk_files"]) == 55
    for digest in data["sdk_files"].values():
        assert len(digest) == 64 and int(digest, 16) >= 0
    assert data["source"] == "c9119d267c9843f0fb5dcbc1cc05653eac6051e3"
    assert len(data["unit_tests"]) == 4
    assert data["run_make"] == {"ohm-branch-cache-opt-out": 7, "ohm-relink-assembler-inputs": 12}
    ordinary = json.loads((ROOT / "cargo-config.json").read_bytes())
    assert ordinary["source"] == data["source"]
    assert ordinary["driver"] in data["changed_from_parent"].values()
    visits = ordinary["outcomes"]
    assert [v["sessions"] for v in visits] == [1, 1, 1, 2, 2, 2, 1, 1, 1]
    assert (visits[7]["full"], visits[7]["wild"], visits[7]["fresh"], visits[7]["verdict"]) == (0, 0, True, "29")
    assert (visits[8]["full"], visits[8]["wild"], visits[8]["fresh"], visits[8]["verdict"]) == (1, 1, False, "41")
    return data


def paired(data, phase):
    return [
        tuple(data["samples"][f"pair-{i:02}-{arm}"][phase] for arm in "PQ")
        for i in range(1, data["recipe"]["pairs"] + 1)
    ]


def verify_sample(path, product):
    data = read_result(path)
    plan = data["recipe"]
    assert plan["commit"] == product["source"]
    assert plan["pairs"] in (2, 12)
    assert plan["orders"].count("PQ") == plan["orders"].count("QP") == plan["pairs"] // 2
    assert len(data["samples"]) == 2 * plan["pairs"]
    sdk_driver, = (h for name, h in product["sdk_files"].items() if name.startswith("lib/librustc_driver-"))
    assert data["driver_sha256"] == sdk_driver
    assert (data["shared_sdk_members"] == 55) == plan["same_sdk"]
    assert plan["same_sdk"] == plan["enable"]
    check = plan["workflow"] == "check"
    refs = data["references"]
    if plan.get("hold_sdk_identity"):
        identities = data["sdk_identities"]
        assert len(identities) == 4 + 2 * plan["pairs"]
        assert all(entry["files"] == identities[0]["files"] for entry in identities)
        assert set(identities[0]["files"]) == {"rustc", "driver", "cargo"}
    if not check:
        assert set(refs) == {"PA", "PB", "QA", "QB"}
        assert refs["PA"] != refs["PB"] and refs["QA"] != refs["QB"]
        if not plan["enable"]:
            assert refs["PA"] == refs["QA"] and refs["PB"] == refs["QB"]
    for name, observations in data["samples"].items():
        assert set(observations) == PHASES
        role = name[-1]
        for phase, record in observations.items():
            assert record["bytes"] > 0 and record["wall"] > 0 and record["cpu"] >= 0
            assert record["packed_tables"] == 0
            assert record["incremental_crate_directories"] >= 2
            assert len(record["stdout_sha256"]) == len(record["table_files_sha256"]) == 64
            if not check:
                assert refs[role + phase[-1]] == record["ELF"]
            if role == "P" or not plan["enable"] or phase == "empty-A":
                assert record["older"] == 0
                assert record["retained_sessions"] == record["incremental_crate_directories"]
            elif phase in RETURNS:
                assert record["older"] >= 2
                assert record["retained_sessions"] == 2 * record["incremental_crate_directories"]
            if plan["instructions"] and phase in RETURNS:
                counts = record["compiler_Ir"]
                assert set(counts) == {"ruff_python_ast", "ruff_python_parser"} and min(counts.values()) > 0
                assert counts == {k: v["Ir"] for k, v in record["counts"]["crates"].items()}
    for phase in RETURNS:
        rows = paired(data, phase)
        sizes = [q["bytes"] / p["bytes"] for p, q in rows]
        assert sizes == data["summary"][phase]["bytes_ratio"]
        if plan["instructions"]:
            ratios = [sum(p["compiler_Ir"].values()) / sum(q["compiler_Ir"].values()) for p, q in rows]
            assert ratios == data["summary"][phase]["instruction_ratios"]
        else:
            ratios = [p["wall"] / q["wall"] for p, q in rows]
            assert ratios == data["summary"][phase]["ratios"]
        interval = []
        if plan["pairs"] == 12:
            rank = max(k for k in range(1, 7)
                       if 2 * sum(math.comb(12, j) for j in range(k)) / 2**12 <= .05 / 2)
            ordered = sorted(ratios)
            interval = [ordered[rank - 1], ordered[-rank]]
        print(path.name, phase, f"{median(ratios):.3f}×", "interval", interval,
              "size", f"{median(sizes):.4f}×")


if __name__ == "__main__":
    compiler = verify_product()
    paths = sorted(ROOT.glob("*.json.gz"))
    assert paths
    for result in paths:
        verify_sample(result, compiler)
