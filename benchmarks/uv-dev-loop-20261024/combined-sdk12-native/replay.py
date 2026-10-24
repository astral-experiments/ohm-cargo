"""Recompute the fixed native block gates from the published integer-ns pairs."""
import csv
import json
from pathlib import Path
import runpy
import statistics


def recompute(root):
    protocol = json.loads((root / 'protocol.json').read_text())
    paired_statistics = runpy.run_path(str(root / 'paired_stats.py'))['paired_statistics']
    grouped = {}
    with (root / 'pairs.csv').open(newline='') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ['endpoint', 'block', 'pair', 'order', 'baseline_ns', 'candidate_ns']
        for row in reader:
            endpoint = row['endpoint']
            assert endpoint in ('check', 'test-build')
            numeric = {}
            for key in ('block', 'pair', 'baseline_ns', 'candidate_ns'):
                numeric[key] = int(row[key])
                assert str(numeric[key]) == row[key]
            block, pair = numeric['block'], numeric['pair']
            assert block in (0, 1) and 0 <= pair < 24
            assert numeric['baseline_ns'] > 0 and numeric['candidate_ns'] > 0
            fixed = protocol['schedules'][endpoint][block]
            assert row['order'] == fixed['orders'][pair]
            selected = grouped.setdefault((endpoint, block), {})
            assert pair not in selected
            selected[pair] = {'order': row['order'], **numeric}
    results, endpoints = [], {}
    for endpoint in ('check', 'test-build'):
        assert (endpoint, 0) in grouped
        first_passed = False
        endpoint_blocks = []
        for block in (0, 1):
            present = (endpoint, block) in grouped
            if block == 1:
                assert present == first_passed, 'Inverse block must follow the original stop rule'
                if not present:
                    break
            selected = grouped[(endpoint, block)]
            assert set(selected) == set(range(24))
            raw = [selected[index] for index in range(24)]
            pairs = [{'order': row['order'], 'baseline': row['baseline_ns'] / 1e9,
                      'candidate': row['candidate_ns'] / 1e9} for row in raw]
            assert sum(pair['order'] == 'AB' for pair in pairs) == 12
            assert sum(pair['order'] == 'BA' for pair in pairs) == 12
            fixed = protocol['schedules'][endpoint][block]
            stats = paired_statistics(pairs, 0.99, 200000, fixed['seed'])
            interval = stats['bootstrap_time_reduction_interval']
            passed = (interval[0] > 0 and stats['exact_two_sided_sign_p'] < 0.01
                      and all(order['geometric_mean_speedup'] > 1 for order in stats['order'].values()))
            result = {'endpoint': endpoint, 'block': block, 'seed': fixed['seed'],
                      'state': 'valid-fixed-block', 'gate_passed': passed,
                      'geometric_reduction': stats['paired_geometric_mean_time_reduction'],
                      'ci99': interval, 'statistics': stats,
                      'median_ms': {arm: statistics.median(pair[arm] for pair in pairs) * 1000
                                    for arm in ('baseline', 'candidate')}}
            results.append(result)
            endpoint_blocks.append(result)
            if block == 0:
                first_passed = passed
        qualified = len(endpoint_blocks) == 2 and all(row['gate_passed'] for row in endpoint_blocks)
        endpoints[endpoint] = {
            'qualified': qualified,
            'valid_blocks': [row['block'] for row in endpoint_blocks],
            'disposition': ('both fixed blocks passed' if qualified else 'closed at first valid gate failure'),
            'inverse_block': 'run' if len(endpoint_blocks) == 2 else 'not run under fixed stop rule',
        }
    assert len(grouped) == len(results)
    return {'schema': 1, 'metric': 'whole_command_native_elapsed_ns',
            'blocks': results, 'endpoints': endpoints, 'pooled_result': None}


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    actual = recompute(root)
    expected = json.loads((root / 'results.json').read_text())
    assert actual == expected, 'Published results do not match the paired integer-ns data'
    for block in actual['blocks']:
        print(json.dumps({key: block[key] for key in
                          ('endpoint', 'block', 'gate_passed', 'geometric_reduction', 'ci99')}))
    print('Exact paired-statistics replay passed; failed performance gates remain failed.')
