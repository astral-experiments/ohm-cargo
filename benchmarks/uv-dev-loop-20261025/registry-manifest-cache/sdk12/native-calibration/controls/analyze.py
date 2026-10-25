"""Two raw gates, then all typed nanoseconds, then independent fixed decisions."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C
import paired


def gate(phase, result):
    point = result['paired_geometric_mean_count_reduction']
    low, high = result['bootstrap_count_reduction_interval']
    if phase == 'aa':
        return result['pairs'] == 8 and abs(point) <= .0035 and low <= 0 <= high and high-low <= .015
    assert phase == 'ab'
    return (result['pairs'] == result['wins'] == 8 and result['ties'] == 0
            and point >= .01 and low > .0025 and result['exact_two_sided_sign_p'] < .01)


def regression(result):
    return (result['pairs'] == result['losses'] == 8 and result['ties'] == 0
            and result['paired_geometric_mean_count_reduction'] < 0
            and result['bootstrap_count_reduction_interval'][1] < 0
            and result['exact_two_sided_sign_p'] < .01)


def summarize(pairs, phase, seed):
    assert len(pairs) == 8
    raw = paired.paired_count_statistics(pairs, confidence=.99, resamples=200000, seed=seed)
    names = {arm+'_'+kind+'_count': arm+'_'+kind+'_nanoseconds'
             for arm in ('baseline', 'candidate') for kind in ('mean', 'median')}
    result = {names.get(k, k): v for k, v in raw.items()}
    seconds = {k.removesuffix('_nanoseconds')+'_seconds': v/1e9
               for k, v in result.items() if k.endswith('_nanoseconds')}
    return {'raw_unit': 'nanoseconds', 'statistics': result, 'display_seconds': seconds,
            'gate_passed': gate(phase, raw), 'regression_gate_passed': phase == 'ab' and regression(raw)}


def decision(phase, summaries, protocol_sha):
    assert len(summaries) == 2
    both = all(row['gate_passed'] for row in summaries)
    bad = phase == 'ab' and all(row['regression_gate_passed'] for row in summaries)
    return {'state': 'two-independent-native-blocks', 'phase': phase,
            'protocol_sha256': protocol_sha, 'hosts': [r['hostname'] for r in summaries],
            'both_passed': both, 'replicated_regression': bad, 'withhold_PR': bad,
            'wall_gain_claim_allowed': phase == 'ab' and both,
            'ab_eligible': phase == 'aa' and both,
            'disposition': ('aa-qualified' if both else 'native-closed-AA-noise') if phase == 'aa'
                           else 'replicated-regression-withhold-PR' if bad
                           else 'both-native-gain-gates-pass' if both else 'native-inconclusive-no-wall-claim',
            'one_host_regression_requires_review': phase == 'ab' and any(r['regression_gate_passed'] for r in summaries) and not bad,
            'pooled_statistics': None, 'extensions': 0, 'replacements': 0,
            'publication_automatically_authorized': False}


def duration_rows(root, terminal):
    rows = []
    for sample in terminal['samples']:
        value = json.loads((Path(root)/(sample['label']+'.elapsed.json')).read_bytes())
        assert set(value) == {'unit', 'elapsed_ns'}
        assert value['unit'] == 'nanoseconds' and type(value['elapsed_ns']) is int and value['elapsed_ns'] > 0
        rows.append(dict(pair=sample['pair'], position=sample['position'], variant=sample['variant'], **value))
    return rows


def analyze(cohort, protocol, read_gate, read_samples, output):
    phase = cohort['phase']; assert phase in ('aa', 'ab')
    assert cohort['state'] == 'fixed-registry-native-cohort'
    assert len(cohort['members']) == 2
    assert [r['hostname'] for r in cohort['members']] == protocol['hosts']
    plan = protocol['phases'][phase]; assert plan['pairs_per_host'] == 8
    gates = []
    for member in cohort['members']:
        row = read_gate(member)
        assert row['state'] == 'all-native-raw-gates-passed'
        assert row['mode'] == 'measure' and row['phase'] == phase
        assert row['inputs_sha256'] == member['inputs_sha256'] and row['samples'] == 16
        assert row['elapsed_payloads_decoded'] is False
        gates.append(row)
    C.save(output/'both-raw-gates.json', {'state': 'both-complete-restored-native-gates',
                                        'gates': gates, 'elapsed_payloads_decoded': False})
    all_pairs = []
    for index, member in enumerate(cohort['members']):
        rows = read_samples(member); assert len(rows) == 16
        assert all(set(row) == {'pair', 'position', 'variant', 'unit', 'elapsed_ns'} for row in rows)
        pairs = []
        for number, order in enumerate(plan['orders'][str(index)]):
            chosen = rows[2*number:2*number+2]
            assert [(r['pair'], r['position'], r['variant']) for r in chosen] == [
                (number, pos, protocol['labels'][letter]) for pos, letter in enumerate(order)]
            assert all(type(r['elapsed_ns']) is int and r['elapsed_ns'] > 0 and r['unit'] == 'nanoseconds' for r in chosen)
            pairs.append(dict(order=order, **{r['variant']: r['elapsed_ns'] for r in chosen}))
        all_pairs.append(pairs)
    C.save(output/'both-duration-gates.json', {'state': 'all-32-typed-durations-before-statistics',
                                             'phase': phase, 'hosts': protocol['hosts']})
    summaries = []
    for index, (member, pairs) in enumerate(zip(cohort['members'], all_pairs)):
        summary = summarize(pairs, phase, plan['bootstrap_seeds'][index])
        summary.update(hostname=member['hostname'], phase=phase, pairs=pairs)
        C.save(output/('host-%d-summary.json' % index), summary)
        summaries.append(summary)
    result = decision(phase, summaries, cohort['protocol_sha256'])
    C.save(output/'decision.json', result)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('--receipt-sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    receipt = C.read_ref({'path': str(args.receipt), 'sha256': args.receipt_sha256})
    assert receipt['state'] == 'complete-registry-native-two-host-collection'
    protocol = C.read_ref(receipt['protocol']); cohort = C.read_ref(receipt['cohort'])
    assert cohort['protocol_sha256'] == receipt['protocol']['sha256']
    assert receipt['root_replay_admission'] is not None
    authority = C.read_ref(receipt['root_replay_admission'])
    assert authority['state'] == 'accepted-native-raw-replay-inputs'
    assert authority['cohort_sha256'] == receipt['cohort']['sha256']
    assert set(cohort['sources']) == {path.name for path in Path(__file__).parent.glob('*.py')}
    for name in cohort['sources']:
        assert C.sha(Path(__file__).with_name(name)) == cohort['sources'][name]
    import validate_raw
    def resolve(path):
        row = receipt['path_map'][path]
        assert C.sha(row['path']) == row['sha256']
        return Path(row['path'])
    def raw_gate(member):
        return validate_raw.validate(member['collection_root'], member['inputs_sha256'], protocol, resolve=resolve)
    def samples(member):
        root = Path(member['collection_root'])
        terminal = json.loads((root/'terminal.json').read_bytes())
        return duration_rows(root, terminal)
    args.output.mkdir(parents=True, exist_ok=False)
    analyze(cohort, protocol, raw_gate, samples, args.output)


if __name__ == '__main__':
    main()
