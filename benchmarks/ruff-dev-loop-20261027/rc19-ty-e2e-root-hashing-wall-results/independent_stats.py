"""Recompute all 1,679,616 assignments directly from the 64 time-ordered stopwatch records."""
from itertools import product
from pathlib import Path
import argparse,json,math,random

def median(v):
 y=sorted(v);return (y[15]+y[16])/2

def main():
 ap=argparse.ArgumentParser();ap.add_argument('result',type=Path);args=ap.parse_args();d=args.result
 read=lambda n:json.loads((d/n).read_bytes())
 ticks=read('original-monotonic-clocks.json');a=read('analysis.json');assert len(ticks)==32;values=[];chron=[];orders=[]
 for i,r in enumerate(ticks,1):
  assert i==r['pair'];u,v=r['parent'],r['child']
  assert u['elapsed_ns']==u['end_ns']-u['start_ns'] and v['elapsed_ns']==v['end_ns']-v['start_ns']
  first='parent'if u['start_ns']<v['start_ns']else'child';last='child'if first=='parent'else'parent';assert r[first]['end_ns']<r[last]['start_ns']
  orders.append('RF'if first=='parent'else'FR');values.append(math.log(v['elapsed_ns']/u['elapsed_ns']));chron.append(math.log(r[last]['elapsed_ns']/r[first]['elapsed_ns']))
 assert orders==a['orders'];obs=median(values);assert obs==a['median_log_ratio']
 options=[]
 for j in range(0,32,4):
  assert sorted(orders[j:j+4])==['FR','FR','RF','RF'];opts=[]
  for mask in range(16):
   if mask.bit_count()!=2:continue
   opts.append(tuple(x*(+1 if mask>>i&1 else -1) for i,x in enumerate(chron[j:j+4])))
  options.append(opts)
 rare=all_n=0
 for sel in product(*options):
  sign=[y for block in sel for y in block];rare+=abs(median(sign))+1e-15>=abs(obs);all_n+=1
 assert rare==a['extreme'] and all_n==a['assignments']==1679616 and rare/all_n==a['two_sided_exact_p']
 rng=random.Random(a['bootstrap_seed']);boot=[]
 for _ in range(30000):
  idx=[rng.randrange(8)for _ in range(8)];boot.append(median([values[4*b+k] for b in idx for k in range(4)]))
 boot.sort();bound=[]
 for cut in (.025,.975):
  j=(len(boot)-1)*cut;lo=math.floor(j);hi=math.ceil(j);bound.append((1-(j-lo))*boot[lo]+(j-lo)*boot[hi])
 assert all(math.isclose(i,j,abs_tol=1e-15) for i,j in zip(bound,a['interval_log']))
 print(json.dumps({'exact_chronology':orders,'pairs':len(ticks),'extreme_assignments':rare,'total_assignments':all_n,'median_relative':math.expm1(obs),'matched_bootstrap_ci':list(map(math.expm1,bound)),'two_sided_p':rare/all_n},sort_keys=True))
if __name__=='__main__':main()
