"""Summarize native ABBA/BAAB wall times. Each four-run block is one observation."""
import csv
import itertools
import math
from pathlib import Path
import random
import statistics
import sys

rows = list(csv.DictReader(Path(sys.argv[1]).open()))
mode_order = ('check', 'build', 'test')
for seed in sorted({row['seed'] for row in rows}):
    results = {}
    for mode in mode_order:
        samples = [r for r in rows if r['seed'] == seed and r['mode'] == mode]
        blocks = []
        for i in range(16):
            block = sorted((r for r in samples if int(r['block']) == i), key=lambda r:int(r['position']))
            assert [int(r['position']) for r in block] == list(range(4))
            arms = [r['arm'] for r in block]
            assert arms in (['parent','candidate','candidate','parent'], ['candidate','parent','parent','candidate'])
            times = {a: [math.log(int(r['elapsed_ns'])) for r in block if r['arm'] == a] for a in ('parent','candidate')}
            blocks.append(statistics.mean(times['candidate']) - statistics.mean(times['parent']))
        observed = abs(sum(blocks))
        p = sum(abs(sum(s*d for s,d in zip(signs, blocks))) >= observed for signs in itertools.product((-1, 1), repeat=len(blocks))) / 2**len(blocks)
        savings = lambda log_ratio: 100 * -math.expm1(log_ratio)
        rng = random.Random(int(seed))
        boot = sorted(savings(sum(rng.choices(blocks, k=len(blocks))) / len(blocks)) for _ in range(50000))
        median_ms = [statistics.median(int(r['elapsed_ns']) for r in samples if r['arm'] == arm)/1e6 for arm in ('parent','candidate')]
        results[mode] = (savings(statistics.mean(blocks)), boot[1249], boot[48749], p, sum(d < 0 for d in blocks), *median_ms)
    adjusted = 0
    for rank, mode in enumerate(sorted(results, key=lambda m: results[m][3])):
        point, lo, hi, p, favorable, parent, candidate = results[mode]
        adjusted = max(adjusted, min(1, (3-rank)*p))
        print(f'{seed} {mode}: {point:.3f}% [{lo:.3f}, {hi:.3f}], p={p:.6f}, Holm={adjusted:.6f}, {favorable}/16 blocks, {parent:.2f} → {candidate:.2f} ms')
