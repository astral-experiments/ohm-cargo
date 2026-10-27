"""Verify the complete corrected Ruff cohort without assuming a particular optimization result."""
import argparse
import csv
import json
from pathlib import Path
import re


def load(path):
    return json.loads(path.read_bytes())


def logical_elf_paths(receipt):
    # Ohm puts a compiler fingerprint in this shared-output directory name.
    names = [re.sub(r'\bv2-[0-9a-f]{16}-all-native-all\b', 'v2-TOOLCHAIN-all-native-all', name) for name in receipt['elf']]
    assert len(names) == len(set(names))
    return set(names)


def audit(directory, subjects):
    plan = load(directory / 'plan.json')
    complete = load(directory / 'complete.json')
    assert plan['subjects']['driver'] == subjects and complete['source_clean'] and complete['pin'] == plan['pin']
    assert plan['subjects']['cargo']['parent'] == plan['subjects']['cargo']['candidate']
    assert re.fullmatch('[0-9a-f]{64}', complete['index_sha256'])
    mode = plan['mode']
    units, outputs = {'build': (501, 15), 'test': (619, 110)}[mode]
    pairs = plan['planned_pairs']
    assert pairs == 12 and len(plan['orders']) == pairs
    with (directory / 'observations.csv').open() as stream:
        measurements = list(csv.DictReader(stream))
    assert len(measurements) == 2 * pairs
    traces = {}
    rosters = set()
    paths = []
    diagnostics = {'original': 'Cannot mix t-string literals with string or bytes literals',
                   'edited': 'Bytes literal cannot be mixed with non-bytes literals'}
    for arm in ('parent', 'candidate'):
        def receipt(label):
            return load(directory / (arm + '-' + label) / 'receipt.json')
        def check_run(label, edited):
            data = receipt(label)
            assert data['fresh'] + len(data['dirty']) == units
            assert [d['message'] for d in data['parser_diagnostics']] == [diagnostics['edited' if edited else 'original']]
            rosters.add(data['roster_sha'])
            if 'elf' in data:
                assert len(data['elf']) == outputs
                paths.append(logical_elf_paths(data))
            return data
        fresh = [('before', False), ('after-edit-fresh', True), ('restore-discovery-fresh', False),
                 ('final-edit-fresh', True), ('final-fresh', False)]
        for i in range(1, pairs + 1):
            fresh.extend([(f'pair-{i:02}-edit-fresh', True), (f'restore-{i:02}-fresh', False)])
            rows = [r for r in measurements if int(r['pair']) == i]
            assert [r['arm'] for r in rows] == plan['orders'][i - 1]
            for row in rows:
                assert row['order'].split('/') == plan['orders'][i - 1]
                if row['arm'] == arm:
                    assert receipt(f'pair-{i:02}')['ns'] == int(row['elapsed_ns']) > 0
        for label, edited in fresh:
            assert not check_run(label, edited)['dirty']
        first, last = (check_run(label, True) for label in ('verify-edit', 'verify-final-edit'))
        assert first['processes'] == last['processes'] and first['crates'] == last['crates']
        for kind in ('rustc_full', 'rustc_link_only'):
            assert first['processes'].get(kind, 0) == sum(k == kind for k, _ in first['crates'])
        assert any(k == 'rustc_full' and name == 'ruff_python_parser' for k, name in first['crates'])
        traces[arm] = first['processes']
    assert len(rosters) == 1 and all(p == paths[0] for p in paths)
    return dict(mode=mode, units=units, elf_targets=outputs, pairs=pairs, fully_fresh_repetitions=2*len(fresh),
                trace_processes=traces, skipped_full_compiles=traces['parent']['rustc_full']-traces['candidate']['rustc_full'],
                roster_sha=rosters.pop(), graph_and_diagnostics_match=True, restored_index_sha=complete['index_sha256'])


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('parent_driver')
    cli.add_argument('candidate_driver')
    cli.add_argument('cohorts', nargs=2, type=Path)
    args = cli.parse_args()
    subjects = {'parent': args.parent_driver, 'candidate': args.candidate_driver}
    assert all(re.fullmatch('[0-9a-f]{64}', x) for x in subjects.values()) and len(set(subjects.values())) == 2
    print(json.dumps([audit(d, subjects) for d in args.cohorts], indent=2))
