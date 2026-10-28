"""Exact randomization and paired bootstrap over this experiment's single endpoint."""
import itertools
import json
import math
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def evaluate(plan, rows):
    orders = plan['order']
    expected=['BC']*12+['CB']*12
    random.Random(plan['schedule_seed']).shuffle(expected)
    assert expected == orders == [r['order'] for r in rows] and len(rows) == 24
    assert orders.count('BC') == orders.count('CB') == 12
    assert all(r['block'] == i and set(r['ns']) == {'B', 'C'} and
               all(type(t) is int and t > 0 for t in r['ns'].values()) for i, r in enumerate(rows, 1))
    ratios = [math.log(r['ns']['C'] / r['ns']['B']) for r in rows]
    slots = [ratio if order == 'BC' else -ratio for ratio, order in zip(ratios, orders)]
    total, observed = math.fsum(slots), abs(math.fsum(ratios))
    extreme = sum(abs(2 * sum(assignment) - total) + 1e-12 >= observed
                  for assignment in itertools.combinations(slots, 12))
    assignments = math.comb(24, 12)
    p = extreme / assignments
    randomizer = random.Random(plan['bootstrap_seed'])
    bootstrap = sorted(-100 * math.expm1(statistics.fmean(randomizer.choices(ratios, k=24)))
                       for _ in range(plan['bootstrap_draws']))
    def quantile(q):
        pos = q * (len(bootstrap) - 1)
        i = int(pos)
        return bootstrap[i] + (bootstrap[i+1] - bootstrap[i]) * (pos-i)
    lo, hi = quantile(.025), quantile(.975)
    favorable = sum(r < 0 for r in ratios)
    return dict(pairs=24, favorable=favorable, assignments=assignments, extreme=extreme,
                medians_sec={arm:statistics.median(r['ns'][arm] for r in rows)/1e9 for arm in ('B','C')},
                paired_reduction_pct=-100*math.expm1(statistics.fmean(ratios)), ci95=[lo, hi],
                p_two_sided=p, holm_single_endpoint=p,
                qualifies=p < plan['alpha'] and lo > plan['lower_percent_over'] and
                          favorable >= plan['minimum_favorable_pairs'],
                material_slowdown=p < plan['alpha'] and hi < -plan['lower_percent_over'])


def selftests(plan):
    def samples(kind):
        rows = []
        for i, order in enumerate(plan['order'], 1):
            b = 1_000_000_000 + i * 1000
            if kind == 'slot':
                ns = dict(zip(order, [b, 2*b]))
            else:
                ns = {'B':b, 'C':{'null':b, 'gain':b*3//5, 'loss':b*2}[kind]}
            rows.append(dict(block=i, order=order, ns=ns))
        return rows
    output = {key:evaluate(plan, samples(key)) for key in ('null', 'slot', 'gain', 'loss')}
    assert all(output[k]['p_two_sided'] == 1 and not output[k]['qualifies'] for k in ('null','slot'))
    assert output['gain']['extreme'] == 2 and output['gain']['qualifies']
    assert abs(output['gain']['paired_reduction_pct']-40)<1e-10 and output['loss']['material_slowdown']
    bad = samples('null');bad[0]['order'] = bad[0]['order'][::-1]
    try:
        evaluate(plan,bad)
    except AssertionError:
        pass
    else:
        raise RuntimeError('Wrong frozen order accepted')
    return output


if __name__ == '__main__':
    plan = json.loads((ROOT/'plan.json').read_bytes())
    if sys.argv[1:] == ['selftest']:
        result = selftests(plan)
    else:
        result = evaluate(plan, json.loads(Path(sys.argv[1]).read_bytes()))
    print(json.dumps(result, indent=2, sort_keys=True))
