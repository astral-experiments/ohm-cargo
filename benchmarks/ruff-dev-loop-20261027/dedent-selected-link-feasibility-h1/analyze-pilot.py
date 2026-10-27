from pathlib import Path
import json,math,statistics as st,sys
from collections import Counter
p=Path(__file__).resolve().parent
base=Path(sys.argv[1]) if len(sys.argv)>1 else p/'all-score-h1-v21/whole-pilot-v21/score'
plan=json.loads((p/'pilot-plan.json').read_bytes())
rows=json.loads((base/'complete.json').read_bytes());assert len(rows)==36
pair={}; by=[]; stats={}; widths=Counter()
for i,block in enumerate(plan['schedule']):
 rr=rows[i*3:i*3+3];assert [r['mode'] for r in rr]==block['order'] and all(r['block']==i and r['source']==block['direction'] for r in rr)
 dd={r['mode']:r['ns'] for r in rr};pair[i]=dd
 by.append(dict(block=i,source=block['direction'],order=block['order'],ns=dd,links={r['mode']:{n:v['width'] for n,v in r['links'].items()} for r in rr}))
 for r in rr:
  assert len(r['links'])==2 and all(v['admitted']==(r['mode']!='full') for v in r['links'].values())
  assert all(1<=v['width']<=8 for v in r['links'].values())
  widths.update(v['width'] for v in r['links'].values())
for contrast in ['oracle','selected']:
 logs=[math.log(d[contrast]/d['full']) for d in pair.values()]; cuts=[100*(1-math.exp(x)) for x in logs];f=sum(v>0 for v in cuts);n=len(cuts)
 pvalue=min(1,2*sum(math.comb(n,k) for k in range(min(n-f,f)+1))/2**n)
 ci=sorted(cuts);meds={ar:st.median(d[ar] for d in pair.values())/1e6 for ar in ['full',contrast]};stats[contrast]={ 'median_cut_pct':st.median(cuts),'logmedian_cut_pct':100*(1-math.exp(st.median(logs))),'median_raw_ms':meds,'favorable':f,'n':n,'exact_two_sided_sign_p':pvalue,'range_pct':[min(cuts),max(cuts)],'median_interval_pct':[ci[2],ci[-3]],'interval_coverage':1-2*sum(math.comb(n,k) for k in range(3))/2**n,'logs':logs,'pct':cuts,'by_direction_pct':{name:st.median(cuts[i] for i in range(n) if plan['schedule'][i]['direction']==name) for name in ('reversed','restored')}}
names=sorted(stats,key=lambda a:stats[a]['exact_two_sided_sign_p']);highest=0
for i,k in enumerate(names):
 highest=max(highest,min(1,(2-i)*stats[k]['exact_two_sided_sign_p']));stats[k]['holm_p']=highest
s=stats['selected'];gate=(s['median_cut_pct']>=2 and s['favorable']>=10 and s['holm_p']<.05)
out={'stats':stats,'gate_for_more_engineering':gate,'by_block':by,'all_widths':dict(sorted(widths.items()))}
print(json.dumps(out,indent=2))
