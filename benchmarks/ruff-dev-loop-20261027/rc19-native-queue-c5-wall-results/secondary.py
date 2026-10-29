"""Apply the registered plain-output and edit/repeat decisions to completed pair files."""
import argparse
import json
import math
import random
import statistics
from pathlib import Path


def effect(log_ratios):
    return -math.expm1(statistics.fmean(log_ratios))


def seconds(value):
    assert value['exit'] == 0 and value['wall_ns'] > 0
    return value['wall_ns'] / 1e9


def summarize(values):
    return {'paired_reduction': effect([math.log(b / a) for a, b in values]),
            'median_a_seconds': statistics.median(a for a, _ in values),
            'median_b_seconds': statistics.median(b for _, b in values),
            'pairs': len(values)}


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('host', choices=('primary', 'independent'))
parser.add_argument('order_file', type=Path)
parser.add_argument('plain_file', type=Path)
parser.add_argument('--edit-file', type=Path)
args = parser.parse_args()
order = json.loads(args.order_file.read_bytes())[args.host]
plain = json.loads(args.plain_file.read_bytes())
assert len(plain) == 16 and [r['order'] for r in plain] == order['plain']
result = {'plain': summarize([(seconds(r['A']), seconds(r['B'])) for r in plain])}
result['passes_plain'] = result['plain']['paired_reduction'] > 0
if args.edit_file:
    assert args.host == 'primary'
    edits = json.loads(args.edit_file.read_bytes())
    assert len(edits) == 12 and [r['order'] for r in edits] == order['edit_and_repeat']
    assert [r['state'] for r in edits] == ['notebook', 'original'] * 6
    phases = {}
    for phase, expected_fresh in [('edit', 559), ('repeat', 563)]:
        assert all(r[a][phase]['units'] == 619 and r[a][phase]['fresh'] == expected_fresh for r in edits for a in 'AB')
        phases[phase] = [(seconds(r['A'][phase]), seconds(r['B'][phase])) for r in edits]
    for r in edits:
        expected = 'd76ef359714fc4339f053598978ec5464829f7d09adb24cdfd6defcae3fb56e8' if r['state'] == 'notebook' else 'be6b9375b66036f898876d7f55d745c7ea11d028f7b106c31a273c26e2cdcef7'
        for arm in 'AB':
            behavior = r[arm]['behavior']
            assert behavior['sha256'] == expected and behavior['listed'] == 200
            assert len(behavior['tests']) == 2 and {v['exit'] for v in behavior['tests'].values()} == {101 if r['state'] == 'notebook' else 0}
    totals = [(a1 + a2, b1 + b2) for (a1, b1), (a2, b2) in zip(phases['edit'], phases['repeat'], strict=True)]
    ratios = [math.log(b / a) for a, b in totals]
    cycles = [statistics.fmean(ratios[i:i + 2]) for i in range(0, 12, 2)]
    rng = random.Random(0x192357)
    samples = sorted(effect(rng.choices(cycles, k=6)) for _ in range(100000))
    total = summarize(totals)
    total['paired_95pct_interval'] = [samples[2499], samples[97499]]
    result.update(edit=summarize(phases['edit']), repeat=summarize(phases['repeat']), edit_plus_repeat=total,
                  passes_edit=total['paired_reduction'] >= -0.05 and samples[97499] >= 0)
else:
    assert args.host == 'independent'
print(json.dumps(result, indent=2))
