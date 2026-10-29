"""Independent coordinator statistics; do not pool with the earlier machine."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from analysis_lint import interval,describe
def calculate(rows,plan):
 assert len(rows)==len(plan['schedule']['serde'])==32
 for a,b in zip(rows,plan['schedule']['serde']):assert all(a[k]==b[k]for k in b)
 result={}
 for i,k in enumerate(('edit','repeat','combined')):
  spread=[]
  for x in rows:
   r={t:x[t]for t in ('pair','order','direction')}
   for arm in 'AB':
    a=x['arms'][arm];r[arm]=a['edit']['ns']+a['repeat']['ns'] if k=='combined'else a[k]['ns']
   spread.append(r)
  seed=plan['interval_seed']+i
  est=interval(spread,seed,plan)
  est['direction']={d:interval([q for q in spread if q['direction']==d],seed+10*(j+1),plan)for j,d in enumerate(('reverse','restore'))}
  est['order']={o:describe([q for q in spread if q['order']==o])for o in ('AB','BA')}
  est['four_way']={d+'-'+o:describe([q for q in spread if (q['direction'],q['order'])==(d,o)])for d in ('reverse','restore')for o in ('AB','BA')}
  est['most_adverse_pct']=min(spread,key=lambda q:(q['A']-q['B'])/q['A'])
  est['most_adverse_ms']=min(spread,key=lambda q:q['A']-q['B'])
  result[k]=est
 result['primary_pass']=result['combined']['ci_pct'][0]>0 and result['combined']['p']<.05
 def bound(r):return dict(passed=r['ci_pct'][0]>=-3 and r['ci_ms'][0]>=-5,excludes_zero_slower=r['ci_pct'][1]<0)
 result['repeat_bounds']={d:bound(x)for d,x in result['repeat']['direction'].items()}
 result['pooled_repeat_descriptive']=bound(result['repeat'])
 result['all_gates']=result['primary_pass'] and all(v['passed']for v in result['repeat_bounds'].values())
 return result
