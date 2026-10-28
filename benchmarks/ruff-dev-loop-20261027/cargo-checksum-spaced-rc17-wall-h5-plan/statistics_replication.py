"""Blocked order randomization and a paired bootstrap for two independent cold-state pairs."""
import itertools
import math
import random
import statistics as st

def analyze(blocks, plan):
    assert len(blocks) == 2 and all(len(block) == 6 for block in blocks)
    orders = [[row['order'] for row in block] for block in blocks]
    assert orders == plan['orders'] and all(r.count('BC') == r.count('CB') == 3 for r in orders)
    for block in blocks:
        assert all(set(x['ns']) == {'B', 'C'} and min(x['ns'].values()) > 0 for x in block)
    log = [[math.log(r['ns']['C']/r['ns']['B']) for r in block] for block in blocks]
    slots = [[v if o == 'BC' else -v for v,o in zip(values,order,strict=True)]
             for values,order in zip(log,orders,strict=True)]
    possible=[[2*sum(c)-sum(vals) for c in itertools.combinations(vals,3)] for vals in slots]
    threshold=abs(sum(map(sum,log)))
    extreme=sum(abs(a+b)+1e-12 >= threshold for a,b in itertools.product(*possible))
    rng=random.Random(plan['bootstrap_seed'])
    reduction=lambda v: 100*(-math.expm1(st.fmean(v)))
    flatten=lambda data: [v for group in data for v in group]
    estimate=reduction(flatten(log))
    boot=sorted(reduction(flatten([rng.choices(b,k=6) for b in log])) for _ in range(100_000))
    def quantile(p):
        pos=p*(len(boot)-1); j=int(pos)
        return boot[j]+(boot[j+1]-boot[j])*(pos-j)
    ci=[quantile(.025),quantile(.975)]
    result={'reduction_pct':estimate,'stratified_paired_bootstrap_95':ci,'exact_extreme':extreme,
            'exact_total':400,'exact_p_two_sided':extreme/400,'favorable':sum(v<0 for v in flatten(log)),
            'block_reductions_pct':[reduction(b) for b in log],
            'medians_seconds':{arm:st.median(x['ns'][arm]for x in flatten(blocks))/1e9 for arm in 'BC'}}
    result['qualifies']=(result['exact_p_two_sided']<.05 and ci[0]>1 and result['favorable']>=8
                         and min(result['block_reductions_pct'])>0)
    return result
