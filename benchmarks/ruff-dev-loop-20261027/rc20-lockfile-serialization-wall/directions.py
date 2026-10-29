"""Show both edit directions and the actual extremes without removing any pair."""

import gzip
import json
from pathlib import Path
from statistics import median


def describe(modes):
    out = {}
    for mode, info in modes.items():
        events = info["terminal"]["events"]
        endpoints = {}
        for phase in ("edit", "repeat", "edit_plus_repeat"):
            groups = {"edit": [], "orig": []}
            for pair in range(32):
                visits = events[4 * pair : 4 * pair + 4]
                times = {arm: sum(e["ns"] for e in visits if e["arm"] == arm and
                                  (phase == "edit_plus_repeat" or e["phase"] == phase)) for arm in "AB"}
                groups[visits[0]["source"]].append({
                    "pair": pair, "order": visits[0]["sequence"], "A_ns": times["A"], "B_ns": times["B"],
                    "reduction_pct": 100 * (times["A"] - times["B"]) / times["A"]
                })
            result = {}
            for source, rows in groups.items():
                ordered = sorted(rows, key=lambda r: (r["reduction_pct"], r["pair"]))
                result[source] = {
                    "pairs": len(rows),
                    "candidate_faster": sum(r["reduction_pct"] > 0 for r in rows),
                    "median_reduction_pct": median(r["reduction_pct"] for r in rows),
                    "median_by_order_pct": {order: median(r["reduction_pct"] for r in rows if r["order"] == order)
                                            for order in ("AB", "BA")},
                    "least_reduction": ordered[0], "greatest_reduction": ordered[-1]
                }
            endpoints[phase] = result
        out[mode] = endpoints
    return out


if __name__ == "__main__":
    path = Path(__file__).resolve().with_name("wall-native.json.gz")
    scan = json.loads(gzip.decompress(path.read_bytes()))["modes"]
    print(json.dumps(describe(scan), indent=2, sort_keys=True))
