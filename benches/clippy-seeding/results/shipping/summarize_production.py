#!/usr/bin/env python3
"""Validate the eight production receipts and report paired storage/phase costs."""
import argparse
import json
from pathlib import Path
import re
from statistics import median

ORDER = ['off1', 'on1', 'on2', 'off2', 'on3', 'off3', 'off4', 'on4']
TEST_COUNTS = {'02-donor-test': 812, '04-donor-noop': 812,
               '06-child-test': 812, '08-child-edit-test': 813, '10-child-noop': 813}
NOOPS = ['03b-donor-clippy-noop', '04-donor-noop',
         '09b-child-clippy-noop', '10-child-noop']


def summarize(root):
    rows = {}
    identities = set()
    for label in ORDER:
        receipt = json.loads((root / label / 'receipt.json').read_text())
        assert receipt['complete'] and receipt['production'] and receipt['require_quiet']
        assert receipt['enabled'] == label.startswith('on')
        assert receipt['environment']['CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION'] == (
            None if receipt['enabled'] else 'false')
        identities.add((receipt['cargo_sha256'], receipt['rustc_sha256'],
                        receipt['toolchain']['clippy_sha256'], receipt['harness_sha256']))
        steps = {item['name']: item for item in receipt['commands']}
        for step in steps.values():
            assert step['returncode'] == 0
            assert not any(item['rust'] for key in ['processes_before', 'processes_after']
                           for item in step[key])
        if receipt.get('controlled_background'):
            assert all(item['returncode'] == 0 for item in receipt['indexing'])
            assert re.search(r'\bindexing(?: and searching)? disabled\b',
                             receipt['indexing'][-1]['stdout'].lower())
            for name, step in steps.items():
                if int(name[:2]) < 2:
                    continue
                wait = step['background_wait']
                assert wait['consecutive_samples_required'] == 3
                assert wait['timeout_seconds'] == 60
                assert wait['maximum_single_process_cpu_percent'] == 20
                assert wait['maximum_aggregate_recorded_cpu_percent'] == 50
                assert wait['record_process_cpu_at_percent'] == 1
                assert len(wait['samples']) >= 3
                samples = [item['processes'] for item in wait['samples'][-3:]]
                samples.extend([step['processes_before'], step['processes_after']])
                for sample in samples:
                    assert not any(item['rust'] or item['cpu_percent'] >= 20 for item in sample)
                    assert sum(item['cpu_percent'] for item in sample) < 50
        for name, expected in TEST_COUNTS.items():
            passed = sum(int(line.split('test result: ok. ')[1].split()[0])
                         for line in steps[name]['summaries'] if 'test result: ok.' in line)
            assert passed == expected, (label, name, passed)
        for name in NOOPS:
            assert steps[name]['compiling_lines'] == steps[name]['checking_lines'] == 0
        if receipt['enabled']:
            assert receipt['seed_import']['files'] > 0
            assert receipt['seed_import']['reflinked_files'] > 0
        else:
            assert receipt['seed_import'] is None
        measurements = receipt['measurements']
        assert all(item['stable'] for item in measurements.values())
        source = measurements['sources']['volume_used_bytes']
        row = {f'{name}_physical_mib': (measurements[name]['volume_used_bytes'] - source) / 2**20
               for name in ['donor', 'child_fresh', 'final']}
        row['child_marginal_physical_mib'] = (
            measurements['final']['volume_used_bytes'] - measurements['donor']['volume_used_bytes']) / 2**20
        for phase, chosen in [('workflow', lambda n: int(n[:2]) >= 2),
                              ('donor', lambda n: 2 <= int(n[:2]) <= 4),
                              ('fork_and_child', lambda n: int(n[:2]) >= 5)]:
            for metric, fields in [('wall', ['elapsed_seconds']),
                                   ('cpu', ['child_user_seconds', 'child_system_seconds'])]:
                row[f'{phase}_{metric}_seconds'] = sum(
                    sum(step[field] for field in fields)
                    for name, step in steps.items() if chosen(name))
        for name in ['03-donor-clippy', '09-child-clippy', *NOOPS]:
            row[f'{name}_wall_seconds'] = steps[name]['elapsed_seconds']
            row[f'{name}_cpu_seconds'] = (
                steps[name]['child_user_seconds'] + steps[name]['child_system_seconds'])
        row['seed_import'] = receipt['seed_import']
        rows[label] = row
    assert len(identities) == 1
    assert len({json.loads((root / label / 'receipt.json').read_text()).get(
        'controlled_background', False) for label in ORDER}) == 1
    metrics = {}
    for metric in rows[ORDER[0]]:
        if metric == 'seed_import':
            continue
        modes = {mode: [row[metric] for label, row in rows.items() if label.startswith(mode)]
                 for mode in ['off', 'on']}
        result = {mode: {'median': median(values), 'min': min(values), 'max': max(values),
                         'samples': values} for mode, values in modes.items()}
        result['median_change_percent'] = 100 * (result['on']['median'] / result['off']['median'] - 1)
        result['paired_change_percent'] = [
            100 * (rows[f'on{i}'][metric] / rows[f'off{i}'][metric] - 1) for i in range(1, 5)]
        metrics[metric] = result
    return {'order': ORDER, 'identities': list(next(iter(identities))), 'rows': rows,
            'metrics': metrics,
            'physical_scope': 'Dedicated APFS allocator growth after donor checkout, including build state and child checkout; no pre-upgrade caches.',
            'timing_scope': 'Waited-child CPU and wall time; no instruction-count claim. External Rust checked before/after commands, not continuously.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('results', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.results), indent=2))
