"""Analyze complete preregistered paired series without merging the two hosts."""
import json, math, statistics, sys
from pathlib import Path


def median_interval(data):
    xs = sorted(data)
    n = len(xs)
    # Largest order whose two-sided, distribution-free coverage remains at least 95%.
    k = max(i for i in range(1, n // 2 + 1) if 40 * sum(math.comb(n, j) for j in range(i)) <= 2**n)
    return [xs[k-1], xs[n-k]], k


def analyze(plan, host, data):
    orders = plan['domains'][host]['strata']
    assert len(orders) == 48 and len(data) == len(orders) * 8
    effects, series, pos, neg = [], {'A': [], 'B': []}, 0, 0
    for i, order in enumerate(orders):
        group = data[i*8:i*8+8]
        assert ''.join(row['arm'] for row in group) == order
        assert order in ('ABBABAAB', 'BAABABBA')
        assert all(row['stratum'] == i and row['position'] == j and row['rc'] == 0 and type(row['elapsed_ns']) is int and row['elapsed_ns'] > 0 for j,row in enumerate(group))
        times = {arm: [r['elapsed_ns'] for r in group if r['arm'] == arm] for arm in 'AB'}
        for arm in 'AB': series[arm].extend(times[arm])
        a, b = (math.prod(times[arm]) for arm in 'AB'); pos += a > b; neg += a < b
        effects.append(-math.expm1(math.log(b/a)/4))
    n = pos + neg
    p = min(1, 2 * sum(math.comb(n,j) for j in range(min(pos, neg)+1)) / (2**n)) if n else 1
    ci,k = median_interval(effects)
    median = statistics.median(effects); m = plan['margins']
    return {'observations':len(data),'strata':len(orders),'positive':pos,'negative':neg,'ties':len(orders)-n,'raw_medians_ns':{arm:statistics.median(x) for arm,x in series.items()},'paired_median_reduction':median,'exact_95_ci':ci,'interval_order':k,'exact_two_sided_sign_p':p,'pass':median>m['per_host_median_reduction_min'] and ci[0]>m['per_host_exact_95_lower_min'] and p<m['per_host_exact_p_less_than'] and pos>=m['per_host_positive_min']}


def selftest(plan):
    result={}
    for host in plan['domains']:
        def fake(which):
            rows=[]
            for i, order in enumerate(plan['domains'][host]['strata']):
                for j, arm in enumerate(order):
                    units = {'null':100,'position_only':100+2*j,'gain':96 if arm=='B' else 100,'regression':104 if arm=='B' else 100,'subminimum':997 if arm=='B' else 1000}[which]
                    rows.append({'arm':arm,'stratum':i,'position':j,'rc':0,'elapsed_ns':units})
            return rows
        r={m:analyze(plan,host,fake(m)) for m in ('null','position_only','gain','regression','subminimum')}
        assert r['null']['ties']==48 and r['null']['exact_two_sided_sign_p']==1 and not r['null']['pass']
        # Opposite slots in the eight-observation sequence can have a nonlinear position effect,
        # whose sign randomizes with the mirror choice. It cannot pass either fixed host here.
        assert not r['position_only']['pass']
        assert r['gain']['pass'] and r['gain']['positive']==48 and math.isclose(r['gain']['paired_median_reduction'],.04)
        assert not r['regression']['pass'] and r['regression']['negative']==48 and not r['subminimum']['pass']
        fail={}
        for name, change in [('lost',lambda a:a.pop()),('order',lambda a:a.reverse()),('exit',lambda a:a[2].update(rc=1))]:
            xs=fake('gain');change(xs)
            try:analyze(plan,host,xs)
            except AssertionError:fail[name]='rejected'
            else:raise RuntimeError(name)
        result[host]={'cases':r,'invalid':fail}
    return result


if __name__ == '__main__':
    plan = json.loads(Path(__file__).with_name('plan.json').read_bytes())
    if sys.argv[1:] == ['--selftest']: out=selftest(plan)
    else:
        assert len(sys.argv)==3
        packets=[json.loads(Path(q).read_bytes()) for q in sys.argv[1:]]
        assert {x['host'] for x in packets}==set(plan['domains']) and all(x['terminal'] and x['pre_guards'] and x['post_guards'] for x in packets)
        out={q['host']:analyze(plan,q['host'],q['rows']) for q in packets};out['qualifies_both']=all(v['pass'] for v in out.values())
    print(json.dumps(out,indent=2,sort_keys=True))
