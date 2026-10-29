"""Inspect a complete off-clock order and test the size/overlap/queue-tail gate."""
from collections import Counter
from itertools import combinations
from math import comb
import json
from pathlib import Path
import random
from statistics import median
import sys

ROOT=Path(__file__).resolve().parent
LARGE=128*2**20
SMALL=32*2**20
def order():
    v=[];r=random.Random(2026102900451)
    for _ in range(3):
        a=['AB','BA'];r.shuffle(a);v.extend(a)
    return v

def metrics(targets):
    assert len(targets)==50
    for _,row in targets.items():
        assert len(row['wild'])==2 and row['wild'][0]<row['wild'][1] and row['old_bytes']>0
    large={k for k,v in targets.items()if v['old_bytes']>=LARGE}
    small={k for k,v in targets.items()if v['old_bytes']<=SMALL}
    assert len(large)==14 and len(small)==23
    events=sorted([(time,start,name)for name,row in targets.items()for start,time in [(1,row['wild'][0]),(0,row['wild'][1])]])
    last_time=events[0][0];peak=0;overlap=0;live=set();great=0
    for time,start,name in events:
        elapsed=time-last_time;currently=len(live&large)
        if elapsed:
            peak=max(peak,currently);great=max(great,len(live));overlap+=elapsed*comb(currently,2)
        last_time=time
        if start:live.add(name)
        else:live.remove(name)
    assert not live
    return {'large_pair_overlap_ns':overlap,'peak_large':peak,
            'tail_ns':events[-1][0]-max(row['wild'][0]for row in targets.values()),
            'wild_span_ns':events[-1][0]-events[0][0],'peak_all':great}

def verdict(pairs):
    assert [row['order']for row in pairs]==order()and all(set(r['arms'])=={'A','B'}for r in pairs)
    rows=[{a:metrics(r['arms'][a])for a in ['A','B']}for r in pairs]
    med=lambda a,k:median(q[a][k]for q in rows)
    assert all(q['A']['large_pair_overlap_ns']>0 for q in rows)
    ratio=median(q['B']['large_pair_overlap_ns']/q['A']['large_pair_overlap_ns']for q in rows)
    pass_gate=(ratio<=.9 and sum(q['B']['large_pair_overlap_ns']<q['A']['large_pair_overlap_ns']for q in rows)>=4
               and med('B','peak_large')<med('A','peak_large')and med('B','tail_ns')<=med('A','tail_ns')and med('B','wild_span_ns')<=med('A','wild_span_ns'))
    return {'paired_intersection_ratio_median':ratio,'native_mechanism_passed':pass_gate,'per_pair':rows,
            'arm_medians':{a:{k:med(a,k)for k in rows[0][a]}for a in 'AB'}}

def selftest():
    def roles(large_wave):
        fields={}
        for i in range(50):
            # Disjoint deterministic intervals for small/medium, spread differently for large.
            start=(i//large_wave)*10 if i<14 else i*10+400
            fields[str(i)]={'wild':[start,start+8], 'old_bytes': (LARGE if i<14 else SMALL if i<37 else SMALL+1)}
        return fields
    make=lambda a,b:[{'order':p,'arms':{'A':a,'B':b}}for p in order()]
    a=roles(7);b=roles(3)
    assert not verdict(make(a,a))['native_mechanism_passed']
    assert verdict(make(a,b))['native_mechanism_passed']
    b['49']['wild'][1]+=41
    assert not verdict(make(a,b))['native_mechanism_passed']
    assert Counter(order())=={'AB':3,'BA':3}
    print('null, lower overlap and long-tail rejection passed; order',','.join(order()))

if __name__=='__main__':
    if len(sys.argv)==1:selftest()
    else:print(json.dumps(verdict(json.loads(Path(sys.argv[1]).read_bytes())),sort_keys=True,indent=2))
