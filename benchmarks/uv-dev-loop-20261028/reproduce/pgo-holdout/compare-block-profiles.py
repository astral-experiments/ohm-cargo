#!/usr/bin/env python3
"""Compare instrumented basic-block counters and LLVM compilation-unit names in retained training profiles."""
from array import array
import argparse
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("profdata", type=Path)
parser.add_argument("left", type=Path)
parser.add_argument("right", type=Path)
args = parser.parse_args()


def functions(profile):
    records = {}
    with subprocess.Popen(
        [args.profdata, "show", "--all-functions", "--counts", profile],
        stdout=subprocess.PIPE,
        text=True,
    ) as p:
        name = cfg = None
        for raw in p.stdout:
            line = raw.rstrip("\n")
            if (
                line.startswith("  ")
                and not line.startswith("   ")
                and line.endswith(":")
            ):
                name = line[2:-1]
            elif name and line.startswith("    Hash: "):
                cfg = line.split()[-1]
            elif name and line.startswith("    Block counts: ["):
                counts = line.removeprefix("    Block counts: [").removesuffix("]")
                assert cfg and name not in records, (name, cfg)
                records[name] = (
                    cfg,
                    array("Q", map(int, counts.split(", ")) if counts else ()),
                )
                name = cfg = None
        assert p.wait() == 0
    return records


left = functions(args.left)
right = functions(args.right)
common = set(left) & set(right)
unchanged = [name for name in common if left[name][0] == right[name][0]]
assert all(len(left[n][1]) == len(right[n][1]) for n in unchanged)
differences = {
    name: sum(abs(x - y) for x, y in zip(left[name][1], right[name][1]))
    for name in unchanged
    if left[name][1] != right[name][1]
}
changed_counters = sum(
    x != y for n in differences for x, y in zip(left[n][1], right[n][1])
)
print(
    json.dumps(
        {
            "left_functions": len(left),
            "right_functions": len(right),
            "common_names": len(common),
            "common_cfg_hashes": len(unchanged),
            "equal_cfg_total_counters": sum(len(left[n][1]) for n in unchanged),
            "functions_with_changed_counters": len(differences),
            "changed_counters": changed_counters,
            "sum_absolute_counter_differences": sum(differences.values()),
            "largest_delta_functions": sorted(differences.items(), key=lambda x: -x[1])[
                :4
            ],
        },
        indent=2,
    )
)
