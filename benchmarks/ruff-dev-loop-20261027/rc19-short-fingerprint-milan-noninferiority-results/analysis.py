"""Generate the prospectively balanced order and analyze only a complete qualifying series."""
import argparse
import itertools
import json
import math
import random
import statistics
from pathlib import Path

def order():
    rng = random.Random(0x280BEE)
    result = []
    for block in range(8):
        cells = list(itertools.product(("parent", "child"), ("BE", "EB")))
        rng.shuffle(cells)
        for source, arms in cells:
            result.append({"block": block, "pair": len(result), "source": source, "order": arms})
    return result

def quantile(values, fraction):
    index = (len(values) - 1) * fraction
    left = math.floor(index)
    return values[left] + (index-left) * (values[math.ceil(index)]-values[left])

def analyze(rows):
    assert [{k:row[k] for k in ("pair","block","source","order")} for row in rows] == order()
    assert all(set(row["wall_ns"]) == {"B","E"} and row["validated"] is True for row in rows)
    assert all(type(ns) is int and ns > 0 for row in rows for ns in row["wall_ns"].values())
    ratios = [(row["wall_ns"]["E"] - row["wall_ns"]["B"]) / row["wall_ns"]["B"] for row in rows]
    blocks = [ratios[i:i+4] for i in range(0,32,4)]
    rng = random.Random(0x280051)
    samples = sorted(statistics.median([x for _ in range(8) for x in rng.choice(blocks)]) for _ in range(50000))
    low, high = (quantile(samples, q) for q in (.025,.975))
    return {"pairs":32,"full_blocks":8,"resamples":50000,"relative_slowdown":statistics.median(ratios),
            "block_percentile_95":[low,high],"noninferior_3pct":high < .03,
            "unpaired_medians_ns":{arm:statistics.median(row["wall_ns"][arm] for row in rows) for arm in "BE"},
            "descriptive_source_medians":{s:statistics.median(v for v,row in zip(ratios,rows) if row["source"]==s) for s in ("parent","child")}}

if __name__ == "__main__":
    ap=argparse.ArgumentParser();ap.add_argument("input",nargs="?");args=ap.parse_args()
    print(json.dumps(analyze(json.loads(Path(args.input).read_bytes())) if args.input else order(),indent=2))
