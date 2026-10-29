"""Exact four-pair-block randomization and a block bootstrap for the preregistered median log ratio."""
from itertools import combinations,product
import json,math,random,statistics
from pathlib import Path
MED=statistics.median

def percentile(x,q):
 i=q*(len(x)-1);a=int(i);return x[a]+(x[min(a+1,len(x)-1)]-x[a])*(i-a)

def analyze(rows,orders,seed,*,replicates=30000):
 assert len(rows)==len(orders)==32
 assert all(sorted(orders[i:i+4])==['FR','FR','RF','RF'] for i in range(0,len(rows),4))
 assert all(type(r['parent'])==type(r['child'])==int and min(r.values())>0 for r in rows)
 effects=[math.log(r['child']/r['parent'])for r in rows];observed=MED(effects);chron=[e if o=='RF'else-e for e,o in zip(effects,orders)]
 extrema=0;n=0;picks=[]
 for i in range(0,len(rows),4):
  vals=chron[i:i+4];picks.append([tuple(v if j in c else-v for j,v in enumerate(vals))for c in combinations(range(4),2)])
 for blocks in product(*picks):
  v=MED(sum(blocks,()));n+=1;extrema+=abs(v)>=abs(observed)-1e-15
 assert n==6**8==1679616
 rng=random.Random(seed);blocks=[effects[i:i+4]for i in range(0,len(rows),4)];boot=sorted(MED([x for _ in blocks for x in blocks[rng.randrange(len(blocks))]])for _ in range(replicates));lo,hi=percentile(boot,.025),percentile(boot,.975);p=extrema/n
 direction='faster' if p<.05 and hi<0 else 'slower' if p<.05 and lo>0 else 'inconclusive'
 def row_stats(ids):return {'pairs':len(ids),'parent_median_ns':MED(rows[i]['parent'] for i in ids),'child_median_ns':MED(rows[i]['child'] for i in ids),'paired_median_ns':MED(rows[i]['child']-rows[i]['parent'] for i in ids),'median_relative_change':math.expm1(MED(effects[i]for i in ids))}
 return {**row_stats(list(range(32))),'median_log_ratio':observed,'interval_log':[lo,hi],'interval_relative':[math.expm1(lo),math.expm1(hi)],'two_sided_exact_p':p,'extreme':extrema,'assignments':n,'positive_benefit_count':sum(e<0 for e in effects),'direction':direction,'order_strata':{o:row_stats([i for i,v in enumerate(orders)if v==o]) for o in ('RF','FR')},'bootstrap':'resample eight intact consecutive four-pair blocks with replacement','replicates':replicates,'bootstrap_seed':seed}
