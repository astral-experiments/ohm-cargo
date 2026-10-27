"""Exact two-sided arm-order inference for all registered episodes."""
import argparse,bisect,itertools,json,math,random,statistics
from pathlib import Path
def analyze(order,source):
 keys=['changed','first-unchanged','changed-plus-first','second-unchanged'];data=[]
 for row in order:
  pair={arm:json.loads((source/str(row['order']).zfill(2)/arm/'change-family.json').read_bytes()) for arm in ('parent','candidate')}
  assert all(p['units']==[520]*3 for p in pair.values())
  sr=pair['candidate']['source'];assert sr==pair['parent']['source']
  vals={arm:[p['ns'][0],p['ns'][1],p['ns'][0]+p['ns'][1],p['ns'][2]] for arm,p in pair.items()}
  data.append({**row,'source':sr,'ns':vals})
 rng=random.Random(278431)
 def subset(k,d):
  rows=[r for r in data if d is None or r['direction']==d]
  return [math.log(r['ns']['candidate'][k]/r['ns']['parent'][k]) for r in rows]
 def reduce(z):return 100*(1-math.exp(z))
 def bootstrap(k):
  a,b=[subset(k,d) for d in ('reverse','restore')]
  outs=[]
  for _ in range(100000):
   v=sum(rng.choices(a,k=12))+sum(rng.choices(b,k=12));outs.append(reduce(v/24))
  outs.sort()
  def q(p):
   f=p*(len(outs)-1);n=int(f);return outs[n]+(f-n)*(outs[n+1]-outs[n])
  return [q(.025),q(.975)]
 def exact(k):
  pools=[]
  for d in ('reverse','restore'):
   rr=[r for r in data if r['direction']==d]
   assert len(rr)==12 and sum(r['arm_order'][-1]=='candidate' for r in rr)==6
   delta=[(1 if r['arm_order'][-1]=='candidate' else -1)*math.log(r['ns']['candidate'][k]/r['ns']['parent'][k]) for r in rr]
   pools.append([2*sum(c)-sum(delta) for c in itertools.combinations(delta,6)])
  first,second=pools;second.sort();total=len(first)*len(second)
  obs=abs(sum(subset(k,None)));out=sum(bisect.bisect_right(second,-obs-v+1e-12)+len(second)-bisect.bisect_left(second,obs-v-1e-12) for v in first)
  return {'extreme_assignments':min(out,total),'assignments':total,'p':min(out,total)/total}
 res={}
 for i,k in enumerate(keys):
  r={'paired_reduction_pct':reduce(statistics.mean(subset(i,None))),'medians_s':{arm:statistics.median(row['ns'][arm][i] for row in data)/1e9 for arm in ('parent','candidate')},
    'per_direction_reductions_pct':{d:reduce(statistics.mean(subset(i,d))) for d in ('reverse','restore')}}
  if i<3:r.update(ci95=bootstrap(i),**exact(i))
  res[k]=r
 running=0
 for j,k in enumerate(sorted(keys[:3],key=lambda c:res[c]['p'])):
  running=max(running,min(1,(3-j)*res[k]['p']));res[k]['holm']=running;res[k]['registered_gain']=running<.05 and res[k]['ci95'][0]>0
 return {'endpoints':res,'rows':data}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('order',type=Path);p.add_argument('scores',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
 result=analyze(json.loads(a.order.read_bytes()),a.scores);a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n');print(json.dumps(result['endpoints'],indent=2))
