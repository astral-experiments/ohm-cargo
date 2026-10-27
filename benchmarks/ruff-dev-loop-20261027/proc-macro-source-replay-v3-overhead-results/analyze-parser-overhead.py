from pathlib import Path
import json, math, statistics, sys

observations=json.loads(Path(sys.argv[1]).read_bytes());plan=json.loads(Path(sys.argv[2]).read_bytes());assert len(observations)==64
by={(r['pair'],r['endpoint'],r['arm']):r for r in observations}
ordered=[(i,e,a) for i,b in enumerate(plan['blocks']) for e in b['endpoints'] for a in b[e]]
assert list(by)==ordered and len(by)==64
coverage=1-sum(math.comb(16,k) for k in range(13,17))/2**16
results={}
for e in ('retained','empty'):
    pairs=[]
    for i,b in enumerate(plan['blocks']):
        v,c=[by[i,e,a] for a in ('parent','candidate')]
        assert v['child']['exit']==c['child']['exit']==0 and (v['measured'],c['measured'])==(True,True)
        t,u=(r['child']['wall_ns'] for r in (v,c));assert t>0 and u>0
        pairs.append({'pair':i,'order':b[e],'parent_ns':t,'candidate_ns':u,'log_ratio':math.log(u/t)})
    logs=sorted(q['log_ratio'] for q in pairs)
    upper=math.expm1(logs[12]);md=math.expm1(statistics.median(logs))
    results[e]={'pairs':pairs,'counts':len(pairs),'parent_median_ns':statistics.median(q['parent_ns'] for q in pairs),'candidate_median_ns':statistics.median(q['candidate_ns'] for q in pairs),
                'paired_median_pct_overhead':100*md,'one_sided_upper_pct_overhead':100*upper,
                'num_shorter':sum(x<0 for x in logs),'num_below_3pct':sum(x<math.log(1.03) for x in logs),'noninferiority':upper<.03}
result={'per_endpoint_one_sided_coverage':coverage,'two_endpoint_minimum_familywise_coverage':1-2*(1-coverage),'pass_both':all(v['noninferiority'] for v in results.values()),'results':results}
print(json.dumps(result,indent=2,sort_keys=True))
