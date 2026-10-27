"""Exact balanced two-sided, single-endpoint replication of genuine first selection."""
from pathlib import Path
import itertools,json,math,random,statistics,sys
def evaluate(plan,rows):
    order=plan['orders'];assert len(rows)==12 and sorted(order)==['BC']*6+['CB']*6 and [v['order'] for v in rows]==order
    assert [v['block'] for v in rows]==list(range(1,13)) and all(set(v['ns'])==set('BC') and min(v['ns'].values())>0 for v in rows)
    d=[math.log(v['ns']['C']/v['ns']['B']) for v in rows];slot=[x if o=='BC' else -x for x,o in zip(d,order,strict=True)];total=math.fsum(slot);obs=abs(math.fsum(d));extreme=sum(abs(2*math.fsum(s)-total)+1e-12>=obs for s in itertools.combinations(slot,6))
    rng=random.Random(128562991);boot=sorted(100*(1-math.exp(statistics.fmean(rng.choices(d,k=12)))) for _ in range(100000))
    def pct(f):
        v=(len(boot)-1)*f;i=int(v);return boot[i]+(v-i)*(boot[i+1]-boot[i])
    p=extreme/math.comb(12,6);ci=[pct(.025),pct(.975)];favorable=sum(v<0 for v in d)
    return dict(control='B',candidate='C',n=12,assignments=924,at_least_as_extreme=extreme,p_exact_two_sided=p,median_B_s=statistics.median(z['ns']['B'] for z in rows)/1e9,median_C_s=statistics.median(z['ns']['C'] for z in rows)/1e9,paired_geomean_reduction_pct=100*(1-math.exp(statistics.fmean(d))),bootstrap_95_pct=ci,faster_pairs=favorable,qualifies=p<.05 and ci[0]>1 and favorable>=8)
if __name__=='__main__':print(json.dumps(evaluate(*[json.loads(Path(f).read_bytes()) for f in sys.argv[1:3]]),indent=2,sort_keys=True))
