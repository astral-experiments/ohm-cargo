"""Recompute the declared per-direction estimates from the 64 whole original pairs."""
import itertools,json,math,random,statistics,sys
from pathlib import Path
def median(x):return statistics.median(x)
def quant(x,q):
 x=sorted(x);s=(len(x)-1)*q;i=int(s)
 return x[i]+(x[min(i+1,len(x)-1)]-x[i])*(s-i)
def scores(blocks,kind,seed,sign_test):
 rows=[p for b in blocks for p in b]
 def values(x):
  a,b=x['A'],x['B']
  return (a[0],b[0]) if kind=='settled' else (a[1],b[1]) if kind=='edited' else (a[2],b[2]) if kind=='repeat' else (a[1]+a[2],b[1]+b[2])
 def to_row(x):
  a,b=values(x);return (1-b/a,(a-b)/1e6,math.log(a/b),a/1e6,b/1e6)
 pairs=[to_row(x) for x in rows];bb=[[to_row(x)for x in k]for k in blocks]
 rng=random.Random(seed);boots=[];deltas=[]
 for _ in range(20000):
  s=[r for _ in bb for r in rng.choice(bb)];boots.append(median([r[0] for r in s]));deltas.append(median([r[1]for r in s]))
 r={'n':len(rows),'A_median_ms':median([x[3]for x in pairs]),'B_median_ms':median([x[4]for x in pairs]),'paired_median_fraction_saved':median([x[0]for x in pairs]),'CI95_fraction':[quant(boots,.025),quant(boots,.975)],'paired_median_ms_saved':median([x[1]for x in pairs]),'CI95_ms':[quant(deltas,.025),quant(deltas,.975)],'B_faster':sum(v[0]>0 for v in pairs)}
 if sign_test:
  m=[statistics.mean([v[2] for v in k])for k in bb];obs=abs(sum(m));eps=1e-12*max(1,obs)
  r['p_two_sided_block_signflip']=sum(abs(sum(s*v for s,v in zip(pattern,m)))>=obs-eps for pattern in itertools.product((-1,1),repeat=len(m)))/(2**len(m))
 return r
def analyze(order,rows):
 fields=('pair','block','seed','edit','case','order')
 assert [[x[k]for k in fields] for x in rows]==[[x[k]for k in fields]for x in order['pairs']] and len(rows)==80
 for x in rows:assert all(isinstance(n,int)and not isinstance(n,bool)and n>0 for n in x['A']+x['B'])and len(x['A'])==len(x['B'])==3
 result={}
 for di,d in enumerate(('chronological','reverse','source-only')):
  blocks=[[p for p in rows if p['block']==i and p['case']==d]for i in range(1,9 if d=='source-only' else 17)]
  assert all(sorted(p['order']for p in b)==['AB','BA']for b in blocks)
  result[d]={k:scores(blocks,k,294160+di*30+j,k=='edited' and d!='source-only')for j,k in enumerate(('settled','edited','repeat','combined'))}
 s=sorted(('chronological','reverse'),key=lambda d:result[d]['edited']['p_two_sided_block_signflip']);previous=0.
 for i,d in enumerate(s):
  rv=result[d];a=rv['edited'];rp=rv['repeat'];p=max(previous,min(1,(2-i)*a['p_two_sided_block_signflip']));a['p_holm']=p;previous=p
  rv['settled_noninferiority']=rv['settled']['CI95_fraction'][0]>-.03 and rv['settled']['CI95_ms'][0]>-5
  rv['repeat_noninferiority']=rp['CI95_fraction'][0]>-.03 and rp['CI95_ms'][0]>-5
  rv['qualifies']=a['paired_median_fraction_saved']>=.02 and a['CI95_fraction'][0]>0 and p<.05 and rv['settled_noninferiority'] and rv['repeat_noninferiority'] and rv['combined']['paired_median_fraction_saved']>0
 g=result['source-only']['edited'];guard=g['CI95_fraction'][0]>-.03 and g['CI95_ms'][0]>-5
 result['source-only']['edit_noninferiority']=guard
 result['standalone_PR_gate']=guard and all(result[d]['qualifies']for d in ('chronological','reverse'))
 return result
if __name__=='__main__':print(json.dumps(analyze(json.loads(Path(sys.argv[1]).read_bytes()),json.loads(Path(sys.argv[2]).read_bytes())),sort_keys=True,indent=2))
