"""Decide whether the real compiler recovers enough of an ordinary Ruff edit to justify a release trial."""
import argparse
import json
from pathlib import Path
import random
from statistics import median


def schedule(host):
    rng = random.Random({"genoa": 0x51A256, "milan": 0x51B256}[host])
    directions = [["AB", "AB", "BA", "BA"] for _ in range(2)]
    for orders in directions:
        rng.shuffle(orders)
    order = [visit for both in zip(*directions, strict=True) for visit in both]
    return list(zip(order, ["parent", "historical"] * 4, strict=True))


def screen(host, pairs):
    assert [(p["order"], p["direction"]) for p in pairs] == schedule(host)
    margins, fractions, loop_ratios = [], [], []
    for p in pairs:
        a, b = p["A"], p["B"]
        assert p["native_verified"] and p["roster_verified"]
        for arm in (a, b):
            oracle = arm["oracle"]
            assert oracle["literal_equal"] and oracle["objects"] == 256 and oracle["fields"] == 512
            assert arm["rlib_sha256"] == oracle["expected_sha256"] == oracle["actual_sha256"]
            assert len(arm["rlib_sha256"]) == 64 and arm["prior_sha256"] != arm["rlib_sha256"]
        assert a["oracle"]["reference_sha256"] == b["oracle"]["reference_sha256"]
        assert a["caller"] == b["caller"] == ([2, 3, 4] if p["direction"] == "parent" else [1])
        assert all(0 <= x["archive_lower_ns"] <= x["archive_upper_ns"] <= x["edit_ns"]
                   and x["repeat_ns"] > 0 for x in (a, b))
        aloop = a["edit_ns"] + a["repeat_ns"]
        delta = a["archive_lower_ns"] - b["archive_upper_ns"]
        margins.append(delta)
        fractions.append(delta / aloop)
        loop_ratios.append((b["edit_ns"] + b["repeat_ns"]) / aloop)
    return {
        "pairs": len(pairs),
        "lower_bound_component_savings_ns": margins,
        "positive": sum(d > 0 for d in margins),
        "median_conservative_savings_as_fraction_of_loop": median(fractions),
        "median_full_loop_ratio": median(loop_ratios),
        "eligible_for_optimized_trial":
            sum(d > 0 for d in margins) >= 6 and median(fractions) >= 0.01
            and median(loop_ratios) <= 1.02,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", choices=("genoa", "milan"))
    parser.add_argument("pairs", nargs="?", type=Path)
    args = parser.parse_args()
    result = screen(args.host, json.loads(args.pairs.read_bytes())) if args.pairs else schedule(args.host)
    print(json.dumps(result, indent=2))
