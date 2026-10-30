"""Verify all 48 complete-process totals and recompute directional inference offline."""
import collections
import hashlib
import itertools
import json
from pathlib import Path
import random
import statistics
here=Path(__file__).resolve().parent
for row in (here/'SHA256SUMS').read_text().splitlines():
 h,name=row.split('  ',1)
 assert name not in ('','..') and '/'not in name and hashlib.sha256((here/name).read_bytes()).hexdigest()==h
def read(n):return json.loads((here/n).read_bytes())
r=read('runs.json');en=read('enrollment.json');old=read('native.json');result=read('summary.json')
assert len(r)==48 and len(set(x['run']for x in r))==48 and len(set(x['complete_raw_profile_sha256']for x in r))==48
assert old['cold_typed_full_rustc_Wild']==[39,39,8] and old['edit']==[39,1,0] and old['unchanged']==[39,0,0] and old['native_replicas']==4
assert en['schedule_sha256']==hashlib.sha256((json.dumps([[x['run'],x['direction'],{'W':'P','N':'Q'}[x['arm']],x['pair']] for x in r],sort_keys=True,indent=2)+'\n').encode()).hexdigest()
rng=random.Random(en['seed']);order={d:['W']*6+['N']*6 for d in ['forward','reverse']};blocks=['forward','reverse']*6
for d in ['forward','reverse']:rng.shuffle(order[d])
rng.shuffle(blocks);seq=[]
for i,first in enumerate(blocks):
 for d in [first,'forward'if first=='reverse'else'reverse']:
  fst=order[d][i]
  for arm in [fst,'N'if fst=='W'else'W']:seq.append((d,i+1,arm))
assert seq==[(x['direction'],x['pair'],x['arm'])for x in r]
assert en['calibration']['100001']-en['calibration']['1']==300000 and en['calibration']['fork-short']==en['calibration']['fork-long'] and 299000<en['calibration']['thread-long']-en['calibration']['thread-short']<301000
for x in r:
 assert x['total_Ir']>0 and x['clean_reader_matches_profiled_and_native'] and en['driver_sha256'][x['arm']]==x['driver_sha256']
 for k in ['actual_dirty_argv_sha256','complete_raw_profile_sha256','traced_argv_gzip_sha256','jobserver_sha256','inherited_FD_table_sha256','physical_counter_log_sha256','terminal_sha256']:assert len(x[k])==64 and all(c in '0123456789abcdef'for c in x[k])
 p=x['actual_process_roster'];assert p['native-initial']==p['profile-initial']==p['independent-changed']==[39,39,8] and p['native-warm']==p['native-edited-unchanged']==p['profile-warm']==p['profile-edited-unchanged']==[39,0,0] and p['native-edit']==[39,1,0]
 f=old['actual_reader_body_sha256_to_bytes_and_stdout'];a,b=[f[x[k]][1]for k in ('initial_reader_sha256','edited_reader_sha256')];wanted=('3.14 3.14 3.10','3.15 3.15 3.11');assert (a,b)==(wanted if x['direction']=='forward'else wanted[::-1])
def pct(vals,p):
 pos=(len(vals)-1)*p;i=int(pos)
 return vals[i]+(vals[min(i+1,len(vals)-1)]-vals[i])*(pos-i)
positive=[]
for d in ['forward','reverse']:
 work=[x for x in r if x['direction']==d];assert len(set(x['actual_dirty_argv_sha256']for x in work))==1
 by={i:[z for z in work if i==z['pair']]for i in range(1,13)};groups={'W':[],'N':[]};time_diffs=[];observed=0;eff=[];role={'W':[],'N':[]}
 for k,parts in by.items():
  x,y=parts;assert {x['arm'],y['arm']}=={'W','N'}
  w,n=sorted(parts,key=lambda z:z['arm'],reverse=True);assert [w['arm'],n['arm']]==['W','N'];a,b=w['total_Ir'],n['total_Ir']
  role['W'].append(a);role['N'].append(b);delta=1-b/a;eff.append(delta)
  groups[x['arm']].append(delta);observed+=a-b;time_diffs.append(x['total_Ir']-y['total_Ir'])
 rng=random.Random(en['bootstrap_seed']);meds=sorted(statistics.median([rng.choice(groups[a])for a in ['W','N']for _ in range(6)])for i in range(20000))
 ci=[pct(meds,.025),pct(meds,.975)];stats=result['directions'][d]
 p=sum(abs(sum(y if j in first else -y for j,y in enumerate(time_diffs)))>=abs(observed) for first in itertools.combinations(range(12),6))/924
 m=statistics.median(eff);good=sum(x>0 for x in eff)
 assert m==stats['median_fraction'] and ci==stats['ci95'] and p==stats['two_sided_exact_p'] and good==stats['favorable']
 assert role['W']==stats['counts_by_role']['P'] and role['N']==stats['counts_by_role']['Q'] and eff.count(0)==stats['ties']
 assert [statistics.median(role[k])for k in ['W','N']]==[stats['median_Ir'][k]for k in ['P','Q']]
 positive.append(m>0 and ci[0]>0 and good>=10 and p<.05)
assert result['qualified']==all(positive)
print('Verified 48 counts, two clean reader programs, calibrated process scope and both independent paired endpoints.')
