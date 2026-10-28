"""Recompute registered paired effects, balanced-order permutation tests and descriptive intervals."""
from pathlib import Path
import hashlib,itertools,json,math,random,statistics,sys
ORDER=('library','workspace','test')
def stat(rows,kind,index):
 pairs={}
 for r in rows:
  if r['metric']==kind:pairs.setdefault(r['pair'],[]).append(r)
 assert len(pairs)==(16 if kind=='ir' else 32)
 val='ir' if kind=='ir' else 'elapsed_ns';effects=[];parents=[];candidates=[];seq=[];scores=[];memory={'parent':[],'candidate':[]}
 for i in range(len(pairs)):
  a,b=sorted(pairs[i],key=lambda r:r['position']);assert sorted([a['arm'],b['arm']])==['candidate','parent'] and a['position']==0 and b['position']==1
  x,y=(a,b) if a['arm']=='parent' else (b,a)
  parents.append(x[val]);candidates.append(y[val]);effects.append(100*(1-y[val]/x[val]));seq.append(math.log(a[val]/b[val]));scores.append(math.log(x[val]/y[val]))
  for r in (a,b):memory[r['arm']].append(r['maxrss_kib'])
 out=dict(n=len(effects),favorable=sum(x>0 for x in effects),median_percent=statistics.median(effects),parent_median=statistics.median(parents),candidate_median=statistics.median(candidates),median_paired_difference=statistics.median([x-y for x,y in zip(parents,candidates)]),range=[min(effects),max(effects)],median_peak_rss_kib={k:statistics.median(v) for k,v in memory.items()})
 if kind=='ir':
  total=sum(seq);obs=sum(scores);w=[2*sum(seq[i] for i in ids)-total for ids in itertools.combinations(range(16),8)]
  out['one_sided_p']=sum(x>=obs-1e-12 for x in w)/len(w);out['median_interval']=[sorted(effects)[3],sorted(effects)[12]]
 else:
  rng=random.Random(9173+index);boot=sorted(statistics.median(rng.choices(effects,k=32)) for _ in range(50000));out['median_interval']=[boot[1250],boot[48749]]
 return out
def main(root):
 root=Path(root);out={}
 for i,m in enumerate(ORDER):
  p=root/('h7' if m=='library' else 'h8')/m/'observations.json'
  if not p.exists():continue
  rows=json.loads(p.read_bytes());out[m]={kind:stat(rows,kind,i) for kind in ('ir','wall')}
 if 'library' in out and 'workspace' in out:
  prev=0.
  for j,m in enumerate(sorted(ORDER[:2],key=lambda m:out[m]['ir']['one_sided_p'])):
   s=out[m]['ir'];s['holm_p']=prev=max(prev,min(1.,(2-j)*s['one_sided_p']))
   s['qualified']=s['holm_p']<.05 and s['median_percent']>=1 and s['favorable']>=13 and s['median_interval'][0]>0
 return out
if __name__=='__main__':print(json.dumps(main(sys.argv[1]),indent=2,sort_keys=True))
