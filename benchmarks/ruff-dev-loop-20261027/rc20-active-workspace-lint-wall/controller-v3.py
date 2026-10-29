"""Admit and run immutable per-direction first-transition views one command at a time."""
from pathlib import Path
import json,os,re,signal,shutil,statistics,subprocess as sp,sys,time
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT));import timed_study as w
from wall import summarise_stderr
from mechanics import digest,get,store,inventory,sound_timing
from gates import gate
plan=get(ROOT/'protocol.json');PROTOCOL='3674278ba9eec35e70c80d2a7e0243c4ab1291c81b2af3169189b19affbfdc2b'
assert digest(ROOT/'protocol.json')==PROTOCOL and digest(ROOT/'study.py')==plan['native_source']
for key in ('LD_PRELOAD','RUSTFLAGS','RUSTC_WRAPPER','CARGO_LOG'):assert key not in w.env
def allocated(path):
 return sum(f.lstat().st_blocks*512 for f in [path,*path.rglob('*')])
def timer():
 path=ROOT/'wall-timer';path.mkdir();result=[]
 with (path/'stdout').open('xb')as so,(path/'stderr').open('xb')as se:
  for i in range(7):
   for delay in ([0,15,5,25]if i%2==0 else[25,5,15,0]):
    cmd=['/bin/true']if delay==0 else['/bin/sleep',f'{delay/1000:.3f}'];r=sound_timing(cmd,so,se,path,{'PATH':'/usr/bin:/bin','LC_ALL':'C'});result.append(dict(delay_ms=delay,**r));assert r['status']==0
 med={str(d):statistics.median([r['ns']/1e6 for r in result if r['delay_ms']==d])for d in (0,5,15,25)}
 assert med['0']<10 and all(d-.2<=med[str(d)]<=d+15 for d in (5,15,25))and min(med['15']-med['5'],med['25']-med['15'])>4
 store(path/'observation.json',dict(work=result,medians_ms=med,resolution_ns=round(time.clock_getres(time.CLOCK_MONOTONIC_RAW)*1e9)))
def native(sel,label,logger):
 result=[]
 for state in ('original','older'):
  for arm in ('A','B'):
   role=arm+'-'+label;p=w.start(sel,state,role,'trial')
   try:
    kinds=[('first',w.other(state)),('repeat',w.other(state))]
    if logger:
     for setup in ('enable-same-source','logged-settled'):w.send(p,setup,state,'logger')
    for tag,dest in kinds:w.send(p,tag,dest,'logger'if logger else'native')
    w.close(p,state)
   finally:w.clean(p)
   if logger:
    suf=b'resolve_with_registry:resolve_with_previous:register_patch_entries:'
    for setup in ('enable-same-source','logged-settled'):
     d=w.REP/sel/state/role/setup;rec=get(d/'result.json');old=get(w.REP/sel/state/(arm+'-trained')/'repeat/result.json')
     m=(d/'stderr').read_bytes();n=m.count(suf);h=m.count(b'reusing the cached workspace resolution')
     assert rec['source_state']==state and rec['oracle']==old['oracle'] and rec['semantic']==old['semantic'] and not rec['compile'] and not rec['links'] and all(rec['fresh'])
     assert (n>0)==(setup=='enable-same-source') and ((n>0)or(h>0)) and (rec['marker_after']==rec['marker_before'])==(setup=='logged-settled')
     if setup=='logged-settled':logged_source_marker=rec['marker_after']
   for tag,dest in kinds:
    prior=get(w.REP/sel/state/(arm+'-probe')/tag/'result.json');d=w.REP/sel/state/role/tag;r=get(d/'result.json');cl=get(w.REP/sel/dest/'A-cold/cold/result.json')
    assert r['semantic']==prior['semantic']==cl['semantic']and r['oracle']==prior['oracle']==cl['oracle']and sorted(r['compile'],key=str)==sorted(prior['compile'],key=str)and len(r['links'])==len(prior['links']) and r['source_digest']==prior['source_digest']
    assert sorted(r['typed'],key=str)==sorted(cl['typed'],key=str)and sorted(zip(r['typed'],r['fresh']),key=str)==sorted(zip(prior['typed'],prior['fresh']),key=str)
    count=r.get('workspace_cache_reuses')
    full=None
    if logger:
     logs=(d/'stderr').read_bytes();full=logs.count(b'resolve_with_registry:resolve_with_previous:register_patch_entries:')
     if tag=='first':assert r['marker_before']==logged_source_marker and (r['marker_after']==r['marker_before'])==(arm=='B')
     else:assert r['marker_after']==r['marker_before']
     assert count==logs.count(b'reusing the cached workspace resolution') and (full>0 or count>0)
     assert (full>0)==(tag=='first' and arm=='A') and (full>0 or count>0),(sel,state,arm,tag,full,count)
    
    result.append(dict(arm=arm,from_state=state,tag=tag,sha256=digest(d/'result.json'),work=len(r['compile']),links=len(r['links']),cache_reuses=count,full_registry_witnesses=full))
 return result
def admit():
 assert (ROOT/'native.exit').read_bytes()==b'0\n'
 # Qualify each command independently in the same unscored phase.
 cal=ROOT/'wall-timer.kernel';assert (ROOT/'wall-admit.exit').read_text()=='1\n' and digest(cal)==get(ROOT/'diagnostic-amendment.json')['timer_kernel']
 if not cal.is_file():sp.run(['taskset','-c','2','strace','-qq','-e','trace=wait4,waitid','-o',str(cal),'/usr/bin/python3','-IB',str(Path(__file__).resolve()),'timer'],check=True,timeout=60)
 timerdata=get(ROOT/'wall-timer/observation.json');waits=[]
 for l in cal.read_text().splitlines():
  if l.startswith('wait4('):
   m=re.match(r'wait4\((\d+), .*?, 0, NULL\)\s+=\s+(\d+)$',l);assert m and m[1]==m[2];waits.append(int(m[1]))
 assert waits==[x['pid']for x in timerdata['work']]and len(waits)==28 and 0<timerdata['resolution_ns']<=1000
 total=0;allg={}
 for s in w.selections:
  q=get(ROOT/('eligibility-'+s+'.json'));assert q==gate(w.REP,s);info={'native_gate':digest(ROOT/('eligibility-'+s+'.json')),'eligible':q['passed']}
  if q['passed']:
   info['logger']=native(s,'logging-v3',True)
   u=max(allocated(w.PH/s/t/(a+'-probe'))for t in ('original','older')for a in 'AB')
   info['probe_upper_max_bytes']=u;info['trial_budget_64_bytes']=round(64*u*1.15);total+=info['trial_budget_64_bytes']
  allg[s]=info;print('untimed admissions',s,info['eligible'],flush=True)
 free=w.disk();assert free[2]>16*2**30+total+150*2**20,(free,total)
 store(ROOT/'wall-admission.json',dict(plan=PROTOCOL,worker=digest(ROOT/'timed_study.py'),clock=digest(ROOT/'wall.py'),controller=digest(Path(__file__)),timer=digest(cal),preflight=get(ROOT/'wall-timer/observation.json')['medians_ms'],gates=allg,room=free,forecast_peak=total,clock_count=0))
def score(sel):
 g=get(ROOT/'wall-admission.json');assert g['plan']==PROTOCOL and g['gates'][sel]['eligible']and g['worker']==digest(ROOT/'timed_study.py')and g['clock']==digest(ROOT/'wall.py')and g['controller']==digest(Path(__file__));allin={}
 start=ROOT/('wall-start-'+sel+'.json');store(start,dict(admission=digest(ROOT/'wall-admission.json'),plan=PROTOCOL,space=w.disk(),load=os.getloadavg()))
 for st in ('original','older'):
  for arm in 'AB':
   donor,rep=w.leaf(sel,st,arm+'-trained');assert inventory(donor)==get(rep/'snapshot.json')
 order=[]
 for row in plan['schedule'][sel]:
  st=row['from_state'];to=row['to_state']
  for arm in row['order']:
   role=arm+'-slot'+str(row['pair']).zfill(2);p=w.start(sel,st,role,'trial')
   try:w.send(p,'measured',to,'pair');w.close(p,st)
   finally:w.clean(p)
   f=w.REP/sel/st/role/'measured/result.json';assert f.exists();order.append([row['pair'],st,arm,digest(f)])
  if row['pair']%8==0:print('qualified',sel,row['pair'],'pairs',flush=True)
 flanks=native(sel,'post',False)
 for st in ('original','older'):
  for arm in 'AB':
   donor,rep=w.leaf(sel,st,arm+'-trained');assert inventory(donor)==get(rep/'snapshot.json')
 store(ROOT/('wall-terminal-'+sel+'.json'),dict(admission=digest(ROOT/'wall-admission.json'),start=digest(start),plan=PROTOCOL,chronology=order,post=flanks,space=w.disk(),load=os.getloadavg(),complete=True))
if __name__=='__main__':
 if sys.argv[1]=='timer':timer()
 elif sys.argv[1]=='admit':admit()
 elif sys.argv[1]=='score':score(sys.argv[2])
