"""Estimate first-acquisition overhead on a dirty library with no foreign observation."""
from collections import Counter
from itertools import combinations, product
from pathlib import Path
import csv
import json
import math
import random
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from design import ARMS, CLUSTERS, CYCLES, schedule


def group_observations(blocks, observations):
    groups = {kind: [] for kind in CYCLES}
    remaining = iter(observations)
    for block in blocks:
        local = {kind: [] for kind in CYCLES}
        for cycle in block['cycles']:
            measured = {}
            for slot, arm in enumerate(cycle['order'], start=1):
                row = next(remaining)
                assert (int(row['block']), row['kind'], int(row['cycle']), row['direction'],
                        int(row['slot']), row['arm']) == (block['block'], cycle['kind'],
                        cycle['cycle'], cycle['direction'], slot, arm)
                ns = int(row['elapsed_ns'])
                assert ns > 0
                measured[arm] = ns / 1e6
            local[cycle['kind']].append(measured)
        for kind, cycles in local.items():
            assert len(cycles) == CYCLES[kind]
            groups[kind].append(cycles)
    assert next(remaining, None) is None
    return groups


def conditional_probability(assignments, ratios, candidate, control):
    other, = set(ARMS) - {candidate, control}
    groups = [[] for _ in ARMS]
    late = Counter()
    for order, ratio in zip(assignments, ratios, strict=True):
        position = order.index(other)
        c_later = order.index(candidate) > order.index(control)
        groups[position].append(ratio if c_later else -ratio)
        late[position] += int(c_later)
    assert list(map(len, groups)) == [8, 8, 8] and late == {0: 4, 1: 4, 2: 4}
    alternate = [[2 * math.fsum(chosen) - math.fsum(group)
                  for chosen in combinations(group, 4)] for group in groups]
    observed = abs(math.fsum(ratios))
    extreme = sum(abs(math.fsum(values)) + 1e-12 >= observed for values in product(*alternate))
    assert extreme >= 2
    return extreme, 70 ** 3


def compare(groups, assignments, kind, candidate, control, seed):
    logs = [statistics.fmean(math.log(c[candidate] / c[control]) for c in block)
            for block in groups]
    deltas = [statistics.fmean(c[candidate] - c[control] for c in block) for block in groups]
    extreme, total = conditional_probability(assignments, logs, candidate, control)
    rng = random.Random(seed)
    log_boot, time_boot = [], []
    for _ in range(20000):
        sample = rng.choices(range(CLUSTERS), k=CLUSTERS)
        log_boot.append(100 * math.expm1(statistics.fmean(logs[i] for i in sample)))
        time_boot.append(statistics.fmean(deltas[i] for i in sample))
    log_boot.sort()
    time_boot.sort()
    row = {
        'endpoint': kind, 'candidate_arm': candidate, 'control_arm': control,
        'pairs': CLUSTERS * CYCLES[kind], 'randomized_blocks': CLUSTERS,
        'control_median_ms': statistics.median(c[control] for b in groups for c in b),
        'candidate_median_ms': statistics.median(c[candidate] for b in groups for c in b),
        'geomean_overhead_pct': 100 * math.expm1(statistics.fmean(logs)),
        'mean_overhead_ms': statistics.fmean(deltas),
        'ci95_overhead_pct': [log_boot[499], log_boot[19500]],
        'ci95_overhead_ms': [time_boot[499], time_boot[19500]],
        'extreme': extreme, 'assignments': total, 'two_sided_p': extreme / total,
    }
    if (candidate, control) == ('N', 'B'):
        row['small_margin_pass'] = log_boot[19500] < 3 and time_boot[19500] < 5
    return row


def evaluate(blocks, observations):
    assert blocks == schedule()
    groups = group_observations(blocks, observations)
    assignment = [b['assignment'] for b in blocks]
    reports = []
    for i, kind in enumerate(CYCLES):
        for j, (candidate, control) in enumerate([('N', 'B'), ('N', 'P'), ('P', 'B')]):
            reports.append(compare(groups[kind], assignment, kind, candidate, control,
                                   1027280800 + i * 10 + j))
    sensitivity = [r for r in reports if 'P' in (r['candidate_arm'], r['control_arm'])]
    adjusted = 0.0
    for i, row in enumerate(sorted(sensitivity, key=lambda r: r['two_sided_p'])):
        adjusted = max(adjusted, min(1.0, (len(sensitivity) - i) * row['two_sided_p']))
        row['holm_p'] = adjusted
        low, high = row['ci95_overhead_pct']
        row['direction_qualified'] = adjusted < .05 and (high < 0 if row['control_arm'] == 'P' else low > 0)
    return {
        'comparisons': reports,
        'passes_baseline_overhead': all(r['small_margin_pass'] for r in reports if 'small_margin_pass' in r),
        'reproduces_build_probe_effect': all(r['direction_qualified'] for r in sensitivity if r['endpoint'] == 'build'),
    }


if __name__ == '__main__':
    with Path(sys.argv[1]).open(newline='') as f:
        print(json.dumps(evaluate(schedule(), list(csv.DictReader(f))), indent=2))
