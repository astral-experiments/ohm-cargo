"""Compare the shipped and source-matched controls in complete balanced three-treatment blocks."""
from collections import defaultdict
import csv
import itertools
import json
import math
from pathlib import Path
import random
import statistics
import sys


def analyze(path):
    plan = json.loads((path / "plan.json").read_bytes())
    assert json.loads((path / "complete.json").read_bytes())["source_clean"]
    orders = plan["orders"]
    assert len(orders) == 18 and len({tuple(order) for order in orders}) == 6
    rows = list(csv.DictReader((path / "observations.csv").open()))
    assert len(rows) == 3 * len(orders)
    elapsed = []
    for block, order in enumerate(orders, 1):
        sample = [r for r in rows if int(r["pair"]) == block]
        assert [r["arm"] for r in sample] == order and all(r["order"] == "/".join(order) for r in sample)
        for arm in order:
            fresh = json.loads((path / f"{arm}-pair-{block:02}-edit-fresh/receipt.json").read_bytes())
            assert fresh["fresh"] == (501 if plan["mode"] == "build" else 619) and not fresh["dirty"]
        elapsed.append({r["arm"]: int(r["elapsed_ns"]) / 1e9 for r in sample})
    gate = {}
    for arm in ("shipped", "parent", "candidate"):
        gate[arm] = []
        for stage in ("verify-edit", "verify-final-edit"):
            receipt = json.loads((path / f"{arm}-{stage}/receipt.json").read_bytes())
            gate[arm].append({k: receipt[k] for k in ("full_links","wild_events","processes","roster_sha")})
        assert gate[arm][0]["roster_sha"] == gate[arm][1]["roster_sha"]
        assert gate[arm][0]["processes"] == gate[arm][1]["processes"]
    assert len({r[0]["roster_sha"] for r in gate.values()}) == 1
    assert len({tuple(sorted(r[0]["processes"].items())) for r in gate.values()}) == 1
    assert all(gate["shipped"][i]["full_links"] == gate["parent"][i]["full_links"] for i in (0, 1))
    min_skipped = min(gate["parent"][i]["full_links"] - gate["candidate"][i]["full_links"] for i in (0, 1))
    results = []
    for control, other in (("shipped", "parent"), ("parent", "shipped")):
        by_slot = defaultdict(list)
        by_order = defaultdict(list)
        ratios = []
        for order, times in zip(orders, elapsed):
            pair = [arm for arm in order if arm != other]
            positional = math.log(times[pair[1]] / times[pair[0]])
            by_slot[order.index(other)].append(positional)
            ratio = math.log(times["candidate"] / times[control])
            ratios.append(ratio)
            by_order[tuple(order)].append(ratio)
        assert all(len(group) == 3 for group in by_order.values())
        observed = statistics.mean(ratios)
        slot_sums = []
        for slot in range(3):
            values = by_slot[slot]
            assert len(values) == 6
            slot_sums.append([2 * sum(chosen) - sum(values) for chosen in itertools.combinations(values, 3)])
        null = [sum(parts)/len(ratios) for parts in itertools.product(*slot_sums)]
        pvalue = sum(abs(value)+1e-12 >= abs(observed) for value in null) / len(null)
        rng = random.Random("ohm-wild-package-ci-v1/" + path.name + "/" + control)
        boots = sorted(100 * (1-math.exp(sum(sum(rng.choices(group,k=3)) for group in by_order.values())/len(ratios))) for _ in range(20000))
        results.append(dict(endpoint=path.name,mode=plan["mode"],minimum_observed_skips=min_skipped,control=control,blocks=len(ratios),orders=6,assignments=len(null),
                            control_median_s=statistics.median(t[control] for t in elapsed),
                            candidate_median_s=statistics.median(t["candidate"] for t in elapsed),
                            reduction_pct=100*(1-math.exp(observed)),bootstrap95=[boots[499],boots[19500]],
                            faster_blocks=sum(r<0 for r in ratios),exact_p=pvalue,gate=gate))
    return results


if __name__ == "__main__":
    reports = [r for name in sys.argv[1:] for r in analyze(Path(name))]
    assert {r["mode"] for r in reports} == {"build","test"} and len(reports) == 6
    last = 0
    for i, r in enumerate(sorted(reports, key=lambda r: r["exact_p"])):
        last = min(1,max(last,(6-i)*r["exact_p"]))
        r["holm_p_six_tests"] = last
    print(json.dumps(reports,indent=2))
