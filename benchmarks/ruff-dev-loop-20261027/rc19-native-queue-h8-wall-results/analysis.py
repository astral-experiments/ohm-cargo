"""Analyze a complete machine's paired whole-Cargo-clock observations."""
import argparse
import json
import math
from pathlib import Path
import random
import statistics

parser = argparse.ArgumentParser()
parser.add_argument('host', choices=('primary', 'independent'))
parser.add_argument('samples', type=Path)
options = parser.parse_args()
orders = json.loads(Path(__file__).with_name('order.json').read_bytes())[options.host]['batches']
samples = json.loads(options.samples.read_bytes())
assert len(orders) == len(samples) == 2
batches = []
block_means = []
all_logs = []
controls = []
candidates = []
for rows, expected in zip(samples, orders, strict=True):
    assert len(rows) == len(expected) == 48
    logs = []
    for row, order in zip(rows, expected, strict=True):
        assert row['order'] == order
        for slot in ('A', 'B'):
            run = row[slot]
            assert run['exit'] == 0 and run['units'] == 619 and run['fresh'] == 563 and run['wall_ns'] > 0
        a, b = (row[s]['wall_ns'] / 1e9 for s in ('A', 'B'))
        controls.append(a)
        candidates.append(b)
        logs.append(math.log(b / a))
    all_logs.extend(logs)
    block_means.append([statistics.fmean(logs[i:i+8]) for i in range(0, 48, 8)])
    batches.append(1 - math.exp(statistics.fmean(logs)))
rng = random.Random(0x192356)
draws = sorted(1 - math.exp(statistics.fmean(x for group in block_means for x in rng.choices(group,k=len(group)))) for _ in range(100000))
interval = [draws[2499], draws[97499]]
negative = sum(x < 0 for x in all_logs)
positive = sum(x > 0 for x in all_logs)
n = negative + positive
p = min(1, 2 * sum(math.comb(n, i) for i in range(min(negative, positive) + 1)) / 2**n) if n else 1
reduction = 1 - math.exp(statistics.fmean(all_logs))
print(json.dumps({'pairs':len(all_logs), 'batch_reductions':batches, 'paired_reduction':reduction,
                  'median_a_seconds':statistics.median(controls), 'median_b_seconds':statistics.median(candidates),
                  'paired_95pct_interval':interval, 'faster':negative, 'two_sided_sign_p':p,
                  'passes_primary_clock':reduction >= 0.03 and interval[0] > 0 and min(batches) > 0 and p <= 0.05}, indent=2))
