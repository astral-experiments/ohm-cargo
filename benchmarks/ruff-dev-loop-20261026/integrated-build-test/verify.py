"""Recalculate both registered endpoint tests from the portable counter receipts."""

import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics
import sys


ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
ROLES = ("cargo", "rustc", "clang", "wild")
COLUMNS = ("cargo_dynamorio_ir", "rustc_cachegrind_ir", "clang_cachegrind_ir", "wild_cachegrind_ir")


def read_json(name):
    return json.loads((ROOT / name).read_bytes())


def read_rows(name):
    return [json.loads(line) for line in (ROOT / name).read_bytes().splitlines()]


def identity(row):
    return row["endpoint"], int(row["pair"]), int(row["position"]), row["arm"]


def quantify(pairs, group):
    def subtotal(row):
        return sum(row[key] for key in group)

    a = [subtotal(obs["parent"]) for obs in pairs]
    b = [subtotal(obs["candidate"]) for obs in pairs]
    changes = [100 * (1 - changed / original) for original, changed in zip(a, b)]
    return {
        "parent_median_ir": statistics.median(a),
        "candidate_median_ir": statistics.median(b),
        "median_paired_reduction_pct": statistics.median(changes),
        "favorable_pairs": sum(pct > 0 for pct in changes),
    }


def statistics_for(pairs):
    n = len(pairs)
    assert n == 12
    sums = [{arm: sum(obs[arm].values()) for arm in ("parent", "candidate")} for obs in pairs]
    differences = [s["parent"] - s["candidate"] for s in sums]
    observed = abs(sum(differences))
    by_run_position = [diff if obs["order"][0] == "parent" else -diff for diff, obs in zip(differences, pairs)]
    null = [
        abs(2 * sum(by_run_position[i] for i in first) - sum(by_run_position))
        for first in itertools.combinations(range(n), n // 2)
    ]
    changes = sorted(100 * (1 - s["candidate"] / s["parent"]) for s in sums)
    rank = max(i for i in range(n // 2 + 1) if 2 * sum(math.comb(n, j) for j in range(i)) / 2**n <= 0.05)
    return {
        "median_paired_reduction_pct": statistics.median(changes),
        "median_ci95_pct": [changes[rank - 1], changes[n - rank]],
        "balanced_randomization_p": sum(value >= observed for value in null) / len(null),
        "favorable": sum(change > 0 for change in changes),
        "collector_groups_descriptive": {
            "Cargo_DynamoRIO": quantify(pairs, ("cargo",)),
            "rustc_clang_Wild_Cachegrind": quantify(pairs, ("rustc", "clang", "wild")),
            "mixed_four_process_sum": quantify(pairs, ROLES),
        },
    }


def main():
    plan = read_json("plan.json")
    results = read_json("statistics.json")
    receipts = {identity(row): row for row in read_rows("counter-receipts.jsonl")}
    gates = {identity(row): row for row in read_rows("gates.jsonl")}
    native = read_json("native-oracles.json")
    processes = {}
    for row in read_rows("processes.jsonl"):
        key = identity(row)
        assert row["role"] not in processes.setdefault(key, {})
        processes[key][row["role"]] = row
    with (ROOT / "observations.csv").open(newline="") as f:
        observations = {identity(row): row for row in csv.DictReader(f)}
    assert set(observations) == set(receipts) == set(gates) == set(processes)
    assert len(observations) == 48
    calculated = {}
    for command, elf_count in (("build", 6), ("test", 102)):
        schedule = [order.split(",") for order in plan["schedule"][command]]
        assert len(schedule) == 12 and sum(order[0] == "parent" for order in schedule) == 6
        pairs = []
        for block, order in enumerate(schedule):
            obs = {"order": order}
            for position, arm in enumerate(order):
                key = command, block, position, arm
                rec, gate, row = receipts[key], gates[key], observations[key]
                raw = [line.split() for line in rec["cargo_dynamorio_thread_events"]]
                pid = raw[0][1]
                assert raw[0] == ["B", pid, "0", "0"] and raw[-1] == ["P", pid, "0", "0"]
                starts = sorted(line[2] for line in raw if line[0] == "T")
                ends = sorted(line[2] for line in raw if line[0] == "F")
                assert starts == ends and len(set(starts)) == len(starts)
                counters = {"cargo": sum(int(line[3]) for line in raw if line[0] == "F"), **rec["cachegrind_I_refs"]}
                assert tuple(counters[role] for role in ROLES) == tuple(int(row[c]) for c in COLUMNS)
                assert sum(counters.values()) == int(row["mixed_counter_component_sum"])
                assert counters == {role: processes[key][role]["ir"] for role in ROLES}
                assert len({p["pid"] for p in processes[key].values()}) == 4
                assert row["order"].split(",") == order and int(row["verified_ELFs"]) == elf_count
                oracle = native[command]["edited"]
                assert len(oracle["executables"]) == elf_count
                elf_map = {k: v["sha256"] for k, v in oracle["executables"].items()}
                serialized = json.dumps(elf_map, sort_keys=True, separators=(",", ":")).encode()
                assert row["normalized_elf_digest"] == hashlib.sha256(serialized).hexdigest()
                assert gate["all_ELFs_equals_native"] and gate["cache_inventory_before_equals_after"]
                assert gate["plain_stdout_bytes"] == 0 and gate["actual_rustc"] == ["ruff" if command == "build" else "fixtures"]
                ver = "1" if arm == "parent" else "2"
                assert gate["cache_inventory"][".ohm-registry-json-v" + ver]["count"] == (370 if command == "build" else 410)
                if arm == "candidate":
                    assert gate["cache_inventory"][".ohm-git-index-sha1dc-v1"]["count"] == 1
                obs[arm] = counters
            pairs.append(obs)
        for arm in ("parent", "candidate"):
            lane = [gate for key, gate in gates.items() if key[0] == command and key[3] == arm]
            assert len({json.dumps(gate["cache_inventory"], sort_keys=True) for gate in lane}) == 1
            assert len({gate["worktree_index_sha256"] for gate in lane}) == 1
        calculated[command] = statistics_for(pairs)
    ordered = sorted(calculated, key=lambda c: calculated[c]["balanced_randomization_p"])
    adjusted = 0
    for rank, command in enumerate(ordered):
        datum = calculated[command]
        adjusted = max(adjusted, min(1, (len(ordered) - rank) * datum["balanced_randomization_p"]))
        datum["holm_p"] = adjusted
        for key, value in datum.items():
            assert results[command][key] == value, (command, key, value, results[command][key])
    print(json.dumps(calculated, indent=2))


if __name__ == "__main__":
    main()
