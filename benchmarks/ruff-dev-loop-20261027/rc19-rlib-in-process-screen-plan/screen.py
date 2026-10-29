"""Decide whether the real compiler recovers enough of an ordinary Ruff edit to justify a release trial."""
import argparse
import json
from pathlib import Path
from statistics import median


def schedule(host):
    order = ["AB", "BA", "BA", "AB", "BA", "AB", "AB", "BA"]
    if host == "milan":
        order = [s[::-1] for s in order]
    return list(zip(order, ["parent", "historical"] * 4, strict=True))


def screen(host, pairs):
    assert [(p["order"], p["direction"]) for p in pairs] == schedule(host)
    margins, fractions, loop_ratios = [], [], []
    for p in pairs:
        a, b = p["A"], p["B"]
        assert p["native_verified"] and p["roster_verified"]
        assert a["rlib_sha256"] == b["rlib_sha256"] and len(a["rlib_sha256"]) == 64
        assert a["prior_sha256"] == b["prior_sha256"] != a["rlib_sha256"]
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
