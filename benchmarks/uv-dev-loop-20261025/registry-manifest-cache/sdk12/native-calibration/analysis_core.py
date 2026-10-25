"""Exact frozen numerical functions, extracted without edits."""
import paired_stats as paired


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
