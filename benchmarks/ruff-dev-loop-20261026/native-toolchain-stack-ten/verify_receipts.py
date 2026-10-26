"""Validate complete command receipts and independently enumerate chronological slot swaps."""
import csv
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics
import sys


def digest(obj):
    return hashlib.sha256(json.dumps(obj, separators=(',', ':'), sort_keys=True).encode()).hexdigest()


def main(directory):
    plan = json.loads((directory / 'plan.json').read_text())
    qualification = json.loads(gzip.decompress((directory / 'qualification.json.gz').read_bytes()))
    receipts = json.loads(gzip.decompress((directory / 'command-receipts.json.gz').read_bytes()))
    results = json.loads((directory / 'summary.json').read_text())
    complete = json.loads((directory / 'completion.json').read_text())
    with (directory / 'observations.csv').open() as source, (directory / 'verification.csv').open() as guards:
        rows = list(csv.DictReader(source))
        verifications = list(csv.DictReader(guards))
    assert len(rows) == len(verifications) == len(receipts) == complete['expected_scored_commands'] == 96
    assert qualification['driver_ctimes'] == complete['driver_ctimes']
    assert qualification['seed_digests'] == complete['seed_digests']
    assert complete['index'] == plan['index'] and complete['source'] == plan['ruff']
    observed_slots = []
    for row, guard in zip(rows, verifications, strict=True):
        case, arm = row['case'], row['arm']
        block, position = int(row['block']), int(row['position'])
        observed_slots.append((case, block, position, arm))
        assert [row[x] for x in ('case', 'block', 'position', 'arm')] == [guard[x] for x in ('case', 'block', 'position', 'arm')]
        rec = receipts[f'{case}-{block:02}-{position}-{arm}']
        assert set(rec) == {'restore', 'before', 'edited', 'after'}
        q = qualification['cases'][case][arm]
        for stage in ('restore', 'before', 'after'):
            r = rec[stage]
            assert r['roster'] == [] and r['units'] == r['fresh'] == 520
            assert r['graph'] == guard['graph'] == plan['graph']
            assert r['diagnostics'] == guard['diagnostics'] == q['before']['diagnostics'] == q['after']['diagnostics']
        r = rec['edited']
        assert int(row['elapsed_ns']) == r['ns'] and r['ns'] > 0
        assert r['roster'] == q['roster'] and int(row['rustcs']) == len(r['roster'])
        assert r['threads'] == q['threads'] and len(r['threads']) == len(r['roster'])
        assert digest(r['roster']) == guard['roster_hash'] and digest(r['threads']) == guard['thread_map_hash']
        assert int(row['one_thread']) == sum(c['flags'][-1] == 1 for c in r['threads'].values())
        assert int(row['eight_threads']) == sum(c['flags'][-1] == 8 for c in r['threads'].values())
    assert observed_slots == [(entry['case'], entry['block'], i, a) for entry in plan['blocks'] for i, a in enumerate(entry['order'])]
    p = {}
    for case in ('private', 'public'):
        slots = [rows[i:i+4] for i in range(0, len(rows), 4) if rows[i]['case'] == case]
        # These contrasts depend only on the four chronological slots, irrespective of treatment.
        weights = []
        actual = []
        for block in slots:
            time = [int(r['elapsed_ns']) for r in block]
            weights.append(math.log(time[0] / time[1]) + math.log(time[3] / time[2]))
            actual.append(1 if block[0]['arm'] == 'A' else -1)
        observed = abs(math.fsum(x * y for x, y in zip(weights, actual, strict=True)))
        def score(orientation):
            return abs(math.fsum(x * y for x, y in zip(weights, orientation, strict=True)))
        count = sum(score(o) >= observed - 1e-12 for o in itertools.product((-1, 1), repeat=len(slots)))
        assert count == results[case]['extreme_orientations']
        p[case] = count / 2**len(slots)
        assert p[case] == results[case]['exact_two_sided_p']
        reduced = [100 * (1-1/math.exp(w * s / 2)) for w, s in zip(weights, actual, strict=True)]
        assert abs(statistics.median(reduced) - results[case]['median_block_reduction_percent']) < 1e-9
    lower, higher = sorted(p, key=p.get)
    assert results[lower]['two_endpoint_holm_p'] == min(1, 2*p[lower])
    assert results[higher]['two_endpoint_holm_p'] == min(1, max(2*p[lower], p[higher]))
    print(f"{len(receipts)} edited checks, {3*len(receipts)} zero-compiler fresh verifications, exact block inferences reproduced")


if __name__ == '__main__':
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent)
