"""Recompute the workspace result from individual clocks and each slot's products."""

import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import statistics
import sys


def sha(data):
    return hashlib.sha256(data).hexdigest()


packet_path, plan_dir, admission_dir = map(Path, sys.argv[1:])
packet = json.loads(gzip.decompress(packet_path.read_bytes()))
assert packet['status'] == 'complete' and not packet['projection_errors']


def body(name):
    meta = packet['files'][name]
    data = packet['bodies'][meta['sha256']].encode()
    assert meta['capture'] == 'verbatim' and len(data) == meta['bytes'] and sha(data) == meta['sha256']
    return data


def obj(name):
    return json.loads(body(name))


assert all(body(f'launcher/{stage}.exit').strip() == b'0' for stage in ['admit', 'score', 'verify'])
assert body('admission.json') == (admission_dir / 'admission.json').read_bytes()
admitted = obj('admission.json')['native']
plan_bytes = (plan_dir / 'plan.json').read_bytes()
assert sha(plan_bytes) == packet['files']['protocol/plan.json']['sha256']
plan = json.loads(plan_bytes)
schedule = ['BC'] * 12 + ['CB'] * 12
random.Random(plan['schedule_seed']).shuffle(schedule)
assert schedule == plan['order']
allowed = admitted['allowed']
assert len(allowed) == 110 and len(admitted['registry']) == 78
assert len(packet['slots']) == 48
clocks = {'B': [], 'C': []}
slot_ratios = []
paired_ratios = []
variants = {}
last_stop = 0
for index, order in enumerate(schedule, 1):
    maps = {}
    for slot, arm in enumerate(order, 1):
        key = f'{index:02d}-{slot}-{arm}'
        assert key in packet['slots']
        start = obj(f'{key}/start.json')
        assert start['image'] == admitted['subjects'][arm] and start['native_binding'] == sha(body('admission.json'))
        clock = obj(f'{key}/ordinary/clock.json')
        assert clock['argv'] == plan['command'] and clock['returncode'] == 0
        assert last_stop < clock['start'] < clock['stop']
        elapsed = clock['stop'] - clock['start']
        last_stop = clock['stop']
        assert elapsed == clock['elapsed_ns'] == obj(f'{key}/verified.json')['elapsed_ns']
        clocks[arm].append(elapsed)
        maps[arm] = obj(f'{key}/first-110.json')
        follow = obj(f'{key}/unchanged/products.json')
        for products in (maps[arm], follow['native']):
            assert products.keys() == allowed.keys() and all(h in allowed[k] for k, h in products.items())
        for name in ['first-78-registry.json', 'unchanged/registry-native.json']:
            assert obj(f'{key}/{name}') == admitted['registry']
        for name in ['ordinary/e2e-list', 'unchanged/e2e-list']:
            assert sha(body(f'{key}/{name}')) == admitted['listing_sha256']
        assert (follow['units'], follow['fresh']) == (619, 563)
        assert follow['counts'] == {'full': 1, 'link-only': 50, 'wild': 50}
    changes = [Path(k).name for k in allowed if maps['B'][k] != maps['C'][k]]
    if changes:
        variants[index] = changes
    paired_ratios.append(math.log(clocks['C'][-1] / clocks['B'][-1]))
    slot_ratios.append(math.log(clocks[order[1]][-1] / clocks[order[0]][-1]))

official = obj('launcher/verify.out')
target = abs(sum(paired_ratios))
total = sum(slot_ratios)
n_extreme = sum(abs(2 * sum(terms) - total) >= target - 1e-12
                for terms in itertools.combinations(slot_ratios, len(schedule) // 2))
n_possible = math.comb(len(schedule), len(schedule) // 2)
randomizer = random.Random(plan['bootstrap_seed'])
resampled = []
for _ in range(plan['bootstrap_draws']):
    sample = [paired_ratios[int(randomizer.random() * len(schedule))] for _ in schedule]
    resampled.append(-100 * math.expm1(statistics.mean(sample)))
bounds = statistics.quantiles(resampled, n=40, method='inclusive')
summary = dict(medians_sec={arm: statistics.median(ns) / 1e9 for arm, ns in clocks.items()},
               paired_reduction_pct=-100 * math.expm1(statistics.mean(paired_ratios)),
               favorable=sum(x < 0 for x in paired_ratios), extreme=n_extreme, assignments=n_possible,
               p_two_sided=n_extreme / n_possible, ci95=[bounds[0], bounds[-1]])
reported = official['statistics']
for key in ['medians_sec', 'favorable', 'extreme', 'assignments', 'p_two_sided']:
    assert summary[key] == reported[key]
for x, y in zip([summary['paired_reduction_pct'], *summary['ci95']], [reported['paired_reduction_pct'], *reported['ci95']]):
    assert math.isclose(x, y, abs_tol=1e-12)
passed = summary['p_two_sided'] < plan['alpha'] and bounds[0] > plan['lower_percent_over'] and summary['favorable'] >= plan['minimum_favorable_pairs']
assert passed is reported['qualifies']
n_variants = sum(map(len, variants.values()))
assert (official['raw_exact'], official['raw_qualified_variants']) == (2640 - n_variants, n_variants)
assert (official['verified_pairs'], official['verified_clocks'], official['verified_listings'], official['test_bodies_timed']) == (24, 48, 96, 0)
print(json.dumps(dict(packet_sha256=sha(packet_path.read_bytes()), statistics=summary, qualified=passed,
                      first_and_followup_workspace_product_checks=96 * len(allowed), first_and_followup_registry_checks=96 * len(admitted['registry']),
                      test_listings=96, cross_arm_exact=2640-n_variants, stock_linker_variants_by_pair=variants), indent=2, sort_keys=True))
