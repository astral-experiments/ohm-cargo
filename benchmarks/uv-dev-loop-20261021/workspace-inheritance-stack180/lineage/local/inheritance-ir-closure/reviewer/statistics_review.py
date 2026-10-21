"""Independent fixed-pair calculations. No work is performed at import time."""
import math
import random
import statistics

from evidence import need


def equal(observed, expected, label='value'):
    if isinstance(expected, dict):
        need(isinstance(observed, dict) and set(observed) == set(expected), label + ': keys differ')
        for name, value in expected.items():
            equal(observed[name], value, label + '.' + name)
    elif isinstance(expected, list):
        need(isinstance(observed, list) and len(observed) == len(expected), label + ': lengths differ')
        for index, value in enumerate(expected):
            equal(observed[index], value, f'{label}[{index}]')
    elif isinstance(expected, float):
        need(isinstance(observed, (float, int)) and not isinstance(observed, bool)
             and math.isfinite(observed) and math.isfinite(expected)
             and math.isclose(observed, expected, rel_tol=1e-12, abs_tol=1e-12), label + ': numeric value differs')
    else:
        need(type(observed) is type(expected) and observed == expected, label + ': value differs')


def paired(pairs):
    count = len(pairs)
    need(count in (12, 30), 'unplanned pair count')
    need(all(math.isfinite(pair[variant]) and pair[variant] > 0
             for pair in pairs for variant in ('baseline', 'candidate')), 'invalid paired observation')
    logs = [math.log(pair['baseline'] / pair['candidate']) for pair in pairs]
    generator = random.Random(1701)
    bootstrap = sorted(math.fsum(generator.choices(logs, k=count)) / count for _ in range(20000))

    def quantile(probability):
        position = (len(bootstrap) - 1) * probability
        low = int(position)
        fraction = position - low
        return bootstrap[low] * (1 - fraction) + bootstrap[min(low + 1, len(bootstrap) - 1)] * fraction

    alpha = (1 - 0.99) / 2
    interval = [math.exp(quantile(alpha)), math.exp(quantile(1 - alpha))]
    ratio = math.exp(math.fsum(logs) / count)
    wins = sum(pair['baseline'] > pair['candidate'] for pair in pairs)
    losses = sum(pair['baseline'] < pair['candidate'] for pair in pairs)
    non_ties = wins + losses
    sign = min(1.0, 2 * sum(math.comb(non_ties, index) for index in range(min(wins, losses) + 1))
               / 2 ** non_ties) if non_ties else 1.0
    return {
        'pairs': count, 'baseline_median_seconds': statistics.median(pair['baseline'] for pair in pairs),
        'candidate_median_seconds': statistics.median(pair['candidate'] for pair in pairs),
        'baseline_mean_seconds': math.fsum(pair['baseline'] for pair in pairs) / count,
        'candidate_mean_seconds': math.fsum(pair['candidate'] for pair in pairs) / count,
        'paired_geometric_mean_speedup': ratio,
        'paired_median_speedup': statistics.median(math.exp(value) for value in logs),
        'paired_geometric_mean_time_reduction': 1 - 1 / ratio,
        'confidence': 0.99, 'bootstrap_speedup_interval': interval,
        'bootstrap_time_reduction_interval': [1 - 1 / interval[0], 1 - 1 / interval[1]],
        'bootstrap_resamples': 20000, 'bootstrap_seed': 1701,
        'wins': wins, 'losses': losses, 'ties': count - wins - losses,
        'exact_two_sided_sign_p': sign, 'log_ratios': logs,
        'order': {order: {'pairs': len(selected), 'geometric_mean_speedup': math.exp(math.fsum(
            math.log(pair['baseline'] / pair['candidate']) for pair in selected) / len(selected))}
                  for order in ('AB', 'BA') if (selected := [pair for pair in pairs if pair['order'] == order])},
    }


def counts(pairs):
    values = paired(pairs)
    renamed = {}
    for name, value in values.items():
        for old, new in [('seconds', 'count'), ('speedup', 'ratio'), ('time_reduction', 'count_reduction')]:
            name = name.replace(old, new)
        renamed[name] = value
    renamed['order'] = {name: {'pairs': row['pairs'], 'geometric_mean_ratio': row['geometric_mean_speedup']}
                        for name, row in values['order'].items()}
    return renamed


def gate(phase, statistics_value):
    if phase == 'ir':
        reduction = statistics_value['paired_geometric_mean_count_reduction']
        interval = statistics_value['bootstrap_count_reduction_interval']
        order_key, count = 'geometric_mean_ratio', 12
    else:
        reduction = statistics_value['paired_geometric_mean_time_reduction']
        interval = statistics_value['bootstrap_time_reduction_interval']
        order_key, count = 'geometric_mean_speedup', 30
    checks = {
        'fixed_pairs': statistics_value['pairs'] == count,
        'at_least_one_percent': reduction >= 0.01,
        'positive_99_percent_lower_bound': interval[0] > 0,
        'two_sided_sign_p_at_most_0_01': statistics_value['exact_two_sided_sign_p'] <= 0.01,
        'both_orders_positive': set(statistics_value['order']) == {'AB', 'BA'} and all(
            row[order_key] > 1 for row in statistics_value['order'].values()),
    }
    return {'passes_gate': all(checks.values()), 'checks': checks, 'reduction': reduction,
            'interval_99': interval, 'sign_p': statistics_value['exact_two_sided_sign_p'],
            'significant_native_regression': phase == 'native' and interval[1] < 0
                and statistics_value['exact_two_sided_sign_p'] <= 0.01,
            'scope': 'Fixed independent pairs; no exclusions, extensions, pooling or interim effect inspection.'}
