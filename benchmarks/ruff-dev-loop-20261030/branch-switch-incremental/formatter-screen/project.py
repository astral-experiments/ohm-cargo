"""Summarize only a completed and independently verified formatter screen."""
from pathlib import Path
import argparse
import hashlib
import json
import statistics

def main(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    doc = json.loads(path.read_bytes())
    order = doc["run_order"]
    installs = doc["installs"]
    assert order == ["admit-P", "admit-Q", "pair1-P", "pair1-Q", "pair2-Q", "pair2-P"]
    by_direction = {}
    for v in ["A", "B"]:
        profile = {}
        cost = {}
        hashes = {}
        for arm in ["P", "Q"]:
            admission = installs["admit-" + arm]["rows"]
            old = admission["return-" + v + "-native"]
            profile[arm] = old["native"]
            if v == "B":
                hashes[arm] = {"independent_empty": [admission["empty-B"]["elf"]]}
            else:
                hashes[arm] = {"independent_empty": [installs[f"pair{i}-{arm}"]["rows"]["empty-A"]["elf"] for i in [1, 2]]}
            hashes[arm]["traced_return"] = old["elf"]
            sampled = [installs[f"pair{i}-{arm}"]["rows"]["return-" + v] for i in [1, 2]]
            hashes[arm]["ordinary_return"] = [x["elf"] for x in sampled]
            cost[arm] = [{
                "elapsed_ns": x["real_elapsed_ns"],
                "cpu_user_s": x["real_user_s"],
                "cpu_system_s": x["real_sys_s"],
                "typed_artifacts": x["typed_count"],
                "dirty_artifacts": len(x["dirty"]),
                "tests_listed": x["test_count"],
                "opposite_type_E0308": True,
            } for x in sampled]
        paired = doc["visits"][v]
        by_direction[v] = {
            "cost": cost,
            "paired": paired,
            "median_elapsed_ratio": statistics.median(x["wall_ratio_P_over_Q"] for x in paired["pairs"]),
            "median_cpu_ratio": statistics.median(x["whole_cpu_ratio_P_over_Q"] for x in paired["pairs"]),
            "matched_native_eligibility": all(profile["P"].get(k) == profile["Q"].get(k) for k in ["full", "cached", "tools"]),
            "physical_native": profile,
            "same_source_executable_sha256": hashes,
        }
    return {
        "schema": 1,
        "raw_verification_sha256": digest,
        "protocol_manifest_sha256": doc["protocol"],
        "workload": "cargo +ohm test -p ruff_python_formatter --lib --no-run --locked --offline -j4 --message-format=json",
        "workload_repo": "astral-sh/ruff",
        "rust_repo": "astral-experiments/ohm-rust",
        "rust_sources": {"P": "7e71d3150938ff8ed82aca03416439d7e5b87ef3", "Q": "6b7f424ece4bc978ead5546b73e1b31d5ccb1e70"},
        "cargo_source": "2d44bd4aa68b9ba32cacb5a384ecc18fa5e7553c",
        "ruff_sources": {"A": "b5dba861cc38e3f7fb4524c9ceba3e01a474ea13", "B": "7b13f01ba1569887a25670820764b24c206da8e5"},
        "slots": {k: installs[k]["completion"] for k in order},
        "cargo_processes": sum(len(v["rows"]) for v in installs.values()),
        "ordinary_primary_processes": 8,
        "directions": by_direction,
        "invalid_formatter_error": {a: installs["admit-" + a]["rows"]["invalid-A"]["diagnostics"] for a in ["P", "Q"]},
        "unique_executable_artifacts": doc["elf_cas"],
    }

if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("verified",type=Path);a=p.parse_args()
    print(json.dumps(main(a.verified),sort_keys=True,indent=2))
