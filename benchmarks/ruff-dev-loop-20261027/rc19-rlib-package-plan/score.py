"""Score a completed 24-triplet plain Cargo command run. Never inspect an incomplete cohort."""
import argparse
from collections import Counter
from itertools import product
import json
import math
from pathlib import Path
import statistics

def effect(logs):return -math.expm1(statistics.mean(logs))
def pair_summary(logs):
    blocks=[statistics.mean(logs[i:i+6]) for i in range(0,24,6)]
    assert len(logs)==24 and len(blocks)==4
    samples=sorted(effect([blocks[i] for i in selection]) for selection in product(range(4),repeat=4))
    def quantile(p):
        off=p*(len(samples)-1);i=int(off)
        return samples[i]+(samples[min(i+1,len(samples)-1)]-samples[i])*(off-i)
    wins=sum(x<0 for x in logs);loss=sum(x>0 for x in logs)
    p=min(1,2*sum(math.comb(wins+loss,k) for k in range(min(wins,loss)+1))/2**(wins+loss))
    return dict(paired_reduction=effect(logs),interval=[quantile(.025),quantile(.975)],faster=wins,sign_p=p,
                directions=[effect(logs[::2]),effect(logs[1::2])],blocks=[-math.expm1(x) for x in blocks])

def score(order,rows):
    assert len(rows)==len(order)==24
    assert [v['index'] for v in rows]==list(range(1,25))
    assert all({key:v[key] for key in ('index','block','direction','order')}==origin for v,origin in zip(rows,order,strict=True))
    assert len({r['order'] for r in rows})==6
    for offset in range(0,24,6):
        block=rows[offset:offset+6]
        assert len({v['order'] for v in block})==6
        for direct in ('historical','parent'):
            part=[r['order'] for r in block if r['direction']==direct]
            assert len(part)==3 and all(set(v[i] for v in part)==set('SAC') for i in range(3))
    values={}
    for row in rows:
        assert row['valid'] and set(row['arms'])==set('SAC')
        for rec in row['arms'].values():
            for phase in ('edit','repeat'):
                assert rec[phase]['exit']==0 and rec[phase]['ns']>0
    for phase in ('edit','repeat','loop'):
        def duration(rec):
            return rec['edit']['ns']+rec['repeat']['ns'] if phase=='loop' else rec[phase]['ns']
        medians={arm:statistics.median(duration(r['arms'][arm]) for r in rows)/1e9 for arm in 'SAC'}
        packs={}
        for before,after in [('S','C'),('A','C'),('S','A')]:
            ratios=[math.log(duration(row['arms'][after])/duration(row['arms'][before])) for row in rows]
            packs[before+after]=pair_summary(ratios)
        values[phase]=dict(medians_seconds=medians,comparisons=packs)
    verdict=values['loop']['comparisons']['SC']
    supports=(verdict['paired_reduction']>=.01 and verdict['interval'][0]>0 and verdict['sign_p']<=.05
              and all(v>0 for v in verdict['directions']) and values['loop']['comparisons']['AC']['paired_reduction']>0
              and values['edit']['comparisons']['SC']['paired_reduction']>0 and values['repeat']['comparisons']['SC']['paired_reduction']>=-.03)
    return dict(qualified_mechanism_on_host=supports,endpoint=values)

if __name__=='__main__':
    arg=argparse.ArgumentParser(description=__doc__);arg.add_argument('host',choices=['one','two']);arg.add_argument('pairs',type=Path);a=arg.parse_args()
    order=json.loads((Path(__file__).resolve().parent/'order.json').read_text())[a.host]
    print(json.dumps(score(order,json.loads(a.pairs.read_text())),sort_keys=True,indent=2))

