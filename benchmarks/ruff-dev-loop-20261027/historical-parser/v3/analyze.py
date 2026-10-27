"""Compute the preregistered complete-block native time effects and two-sided exact P-values."""
from pathlib import Path
import collections,csv,itertools,json,math,random,statistics as st,sys
d=Path(sys.argv[1]).resolve() if sys.argv[1:] else Path(__file__).resolve().parent
plan=json.loads((d/'active-plan.json').read_bytes()); rows=[json.loads(l) for l in (d/'rows.jsonl').read_text().splitlines()]
assert len(rows)==len(plan['blocks'])*8
blocks=collections.defaultdict(list)
for r in rows:
    i=r['block'];spec=plan['blocks'][i-1]
    assert r['arm']==spec['order'][r['position']-1] and r['mode']==spec['endpoint']
    if r['phase']=='edited':blocks[r['mode'],i].append(r)
reported={};brows=[]
for mode in ('build','test'):
    effect=[];outer_minus_inner=[];outerA=[];times=collections.defaultdict(list);byorder=collections.defaultdict(list)
    for (m,i),rs in blocks.items():
        if m!=mode:continue
        rs.sort(key=lambda r:r['position']);assert len(rs)==4 and [r['position'] for r in rs]==[1,2,3,4]
        order=''.join(r['arm'] for r in rs);assert order in ('ABBA','BAAB')
        y=[math.log(r['elapsed_ns']/1e9) for r in rs];raw=(y[0]+y[3]-y[1]-y[2])/2
        delta=raw*(1 if order=='ABBA' else -1);effect.append(delta);outer_minus_inner.append(raw);outerA.append(order=='ABBA');byorder[order].append(delta)
        brows.append({'mode':m,'block':i,'order':order,'control_ns':';'.join(str(r['elapsed_ns']) for r in rs if r['arm']=='A'),'candidate_ns':';'.join(str(r['elapsed_ns']) for r in rs if r['arm']=='B'),'log_control_over_candidate':delta})
        for r in rs:times[r['arm']].append(r['elapsed_ns']/1e9)
    assert len(effect)==16 and sum(outerA)==8
    scale=lambda x:100*(1-math.exp(-x));mu=st.fmean(effect);n=0;extreme=0
    for comb in itertools.combinations(range(16),8):
        ix=set(comb);val=sum(v*(1 if j in ix else -1) for j,v in enumerate(outer_minus_inner))/16;n+=1
        if abs(val)>=abs(mu)-1e-12:extreme+=1
    rng=random.Random('ohm-private-native-history-ci-v1'+mode);boot=[]
    for _ in range(20000):
        sample=[rng.choice(v) for v in byorder.values() for _ in v]
        boot.append(scale(st.fmean(sample)))
    boot.sort();q=lambda p:boot[int(p*(len(boot)-1))]
    reported[mode]={'control_median_seconds':st.median(times['A']),'candidate_median_seconds':st.median(times['B']),'blocks':len(effect),'commands':sum(map(len,times.values())),'time_reduction_percent':scale(mu),'95_percentile_block_ci':[q(.025),q(.975)],'positive_blocks':sum(v>0 for v in effect),'exact_allocations':n,'exact_extreme':extreme,'exact_p_two_sided':extreme/n}
by_p=sorted(reported,key=lambda m:reported[m]['exact_p_two_sided']);previous=0
for i,m in enumerate(by_p):
    p=min(1,(2-i)*reported[m]['exact_p_two_sided']);previous=max(p,previous);reported[m]['holm_p']=previous
with (d/'blocks.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(brows[0]));w.writeheader();w.writerows(brows)
(d/'results.json').write_text(json.dumps(reported,indent=2)+'\n');print(json.dumps(reported,indent=2))
