from collections import Counter
from itertools import permutations
from pathlib import Path
import json
import math
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import evaluate, group_observations
from design import ARMS, CYCLES, NOMINAL, schedule


def synthetic(blocks, cost):
    rows = []
    for block in blocks:
        for c in block['cycles']:
            for slot, arm in enumerate(c['order'], 1):
                rows.append({
                    'block': block['block'], 'kind': c['kind'], 'cycle': c['cycle'],
                    'direction': c['direction'], 'slot': slot, 'arm': arm,
                    'elapsed_ns': round(cost(block, c, slot, arm) * 1e6),
                })
    return rows


blocks = schedule()
assert Counter(b['assignment'] for b in blocks) == {''.join(p): 4 for p in permutations(ARMS)}
for kind, n in CYCLES.items():
    for direction in ('edit', 'restore'):
        order = Counter(c['nominal'] for b in blocks for c in b['cycles']
                        if c['kind'] == kind and c['direction'] == direction)
        assert order == {''.join(p): n * 2 for p in permutations(NOMINAL)}
        for b in blocks:
            cycles = [x for x in b['cycles'] if x['kind'] == kind]
            assert [x['cycle'] for x in cycles] == list(range(1, n + 1))
            assert [x['direction'] for x in cycles] == ['edit', 'restore'] * (n // 2)
            for slot in range(3):
                assert Counter(x['order'][slot] for x in cycles if x['direction'] == direction) == {
                    arm: n // 6 for arm in ARMS
                }

out = {}
for label, offsets, floor, sensitive in [
    ('null', (0, 0, 0), True, False), ('old-probe-slower', (0, 20, 0), True, True),
    ('replacement-cost-too-high', (0, 20, 7), False, True),
]:
    rows = synthetic(blocks, lambda b, c, slot, a: 200 + offsets[ARMS.index(a)])
    result = evaluate(blocks, rows)
    assert len(rows) == 5184 and result['passes_baseline_overhead'] == floor
    assert result['reproduces_build_probe_effect'] == sensitive
    for r in result['comparisons']:
        v = offsets[ARMS.index(r['candidate_arm'])] - offsets[ARMS.index(r['control_arm'])]
        assert math.isclose(r['mean_overhead_ms'], v, abs_tol=1e-8)
        assert r['assignments'] == 343000 and (r['extreme'] == (343000 if v == 0 else 2))
    out[label] = {'samples': len(rows), 'small_margin': floor, 'sensitivity': sensitive}

rows = synthetic(blocks, lambda b, c, slot, a: 200 + slot * 12 + 7 * (c['direction'] == 'edit'))
slot_only = evaluate(blocks, rows)
assert not slot_only['reproduces_build_probe_effect']
assert all(r['two_sided_p'] == 1 and abs(r['geomean_overhead_pct']) < 1e-8
           for r in slot_only['comparisons'])
out['slot-and-direction-only'] = {'false_claims': False, 'samples': len(rows)}
try:
    rows[0], rows[1] = rows[1], rows[0]
    group_observations(blocks, rows)
except AssertionError:
    out['wrong-physical-order'] = {'rejected': True}
else:
    raise AssertionError('wrong physical arm order passed')
print(json.dumps(out, sort_keys=True))
