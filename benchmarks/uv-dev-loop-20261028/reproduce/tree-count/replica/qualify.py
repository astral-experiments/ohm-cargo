#!/usr/bin/env python3
"""Prospective primary gate for opening one role-sum replication endpoint."""
import csv
import math
from pathlib import Path
import statistics
import sys


def qualifies(root):
    root = Path(root)
    if list(root.glob("rejected-*.json")):
        return False
    if not (root / "admission.json").is_file() or not (root / "samples.csv").is_file():
        raise ValueError(f"{root.name} primary is incomplete")
    by_pair = {}
    with (root / "samples.csv").open() as f:
        for row in csv.DictReader(f):
            pair = by_pair.setdefault(int(row['pair']), {})
            if row['arm'] in pair or row['mode'] != 'count':
                raise ValueError(f"invalid primary row: {row}")
            pair[row['arm']] = int(row['value'])
    if set(by_pair) != set(range(10,18)) or any(set(v) != {'base','candidate'} for v in by_pair.values()):
        raise ValueError(f"{root.name} is missing a primary pair")
    changes = [1-p['candidate']/p['base'] for p in by_pair.values()]
    pos, neg = sum(v>0 for v in changes), sum(v<0 for v in changes)
    n = pos + neg
    p = min(1, 2*sum(math.comb(n,k) for k in range(min(pos,neg)+1))/2**n)
    return statistics.median(changes)>0 and p<.05/3


if __name__ == '__main__':
    sys.exit(0 if qualifies(sys.argv[1]) else 2)
