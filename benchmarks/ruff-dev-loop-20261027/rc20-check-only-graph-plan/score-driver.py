"""Consume one immutable native gate and registration. No interim effect output."""
import contextlib,fcntl,hashlib,json,os,re,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import experiment_v2 as e
import case_support as cs
def file_manifest(root):return {str(p.relative_to(root)):e.h(p)for p in sorted(root.rglob('*'))if p.is_file()}
def host():
 # Refuse another native build or known instruction profiler on this worker.
 ours=os.getpid();hits=[]
 for pp in Path('/proc').glob('[0-9]*'):
  try:
   if pp.stat().st_uid!=os.getuid():continue
   c=(pp/'comm').read_text().strip()
   if c in {'cargo','rustc','cc1','ld.bfd','valgrind','perf','callgrind','sccache'}:hits.append((pp.name,c))
  except (PermissionError,FileNotFoundError,ProcessLookupError):pass
 assert not hits,hits
 return {'load':Path('/proc/loadavg').read_text().split()[:3],'uptime':Path('/proc/uptime').read_text().split()[0],'free':e.bd(),'boot':e.h(Path('/proc/sys/kernel/random/boot_id')),'online':Path('/sys/devices/system/cpu/online').read_text().strip()}
def check_phase(arm,path,v,expect,ph):
 raw=v/ph
 with (raw/'clock.json').open('rb')as f:c=json.load(f)
 assert list(sorted(c))==['end_ns','exit','start_ns'] and c['end_ns']>c['start_ns']and c['exit']==0
 actual=e.decode(raw/'stdout');assert actual==expect['artifacts'],(ph,arm,actual,expect['artifacts'])
 return {'raw':{n:e.h(raw/n) for n in ('clock.json','stdout','stderr')},'shape_sha256':e.digestdict(actual)}
def normal_slot(arm,case,rd,native,op):
 seed,new=cs.cases[case];e.space();source=e.q/'seeds'/f'{seed}-{arm}';assert e.snapshot(source)==e.read(e.q/'seeds.json')['states'][source.name]['seed'];rd.mkdir()
 with e.slot_context(source)as tmp:
  path=e.clone(source,tmp);cs.activate(seed);r={}
  m=e.marks(path);assert m['.ohm-built-registry-ready']==0 and m['.ohm-check-graphs/*']>0
  for i,phase in enumerate(('settled','edited','repeat')):
   if phase=='edited':cs.activate(new)
   if op=='post':
    live=cs.one_native(arm,path,phase,rd)
    assert all(live[k]==native[i][k]for k in ('phase','resolution','rustc','native','artifacts','source','markers','rmeta_shape'))
    r[phase]={'result':e.h(rd/phase/'result.json')}
   else:
    if phase!='repeat':e.cli(e.guest(arm,path,e.src,['/usr/bin/python3','-ISB',e.p/'inner-clock.py',rd/'measured','before' if phase=='settled' else 'after']),env=e.base_env)
    r[phase]=check_phase(arm,path,rd/'measured',native[i],phase)
    if phase=='settled':assert e.digestdict(cs.rmeta_shape(e.inputs(path)))==native[i]['rmeta_shape']
  shape=e.digestdict(cs.rmeta_shape(e.inputs(path)));assert shape==native[2]['rmeta_shape'],(arm,case,'postcompile rmeta differs')
  assert e.snapshot(source)==e.read(e.q/'seeds.json')['states'][source.name]['seed']and e.marks(path)==native[2]['markers']
  r.update({'all_rmeta':shape,'state':e.source_inventory(),'seed':e.snapshot(source)});e.put(rd/'receipt.json',r)
def main():
 e.verify_subjects();e.space();reg=e.p/'clock-binding.json';grant=e.read(e.p/'score-grant.json');binding=e.read(reg)
 assert grant['instruction']=='score exactly 80 prospective pairs' and grant['registration_sha256']==e.h(reg) and len(grant['published_plan_commit'])==40 and grant['native_sha256']==e.h(e.q/'native-v3.json') and grant['host_exclusive']
 assert binding['order_sha256']==e.h(e.p/'order.json') and binding['inner_sha256']==e.h(e.p/'inner-clock.py') and binding['host_driver_sha256']==e.h(Path(__file__)) and binding['experiment_sha256']==e.h(e.p/'experiment_v2.py')
 assert binding['case_support_sha256']==e.h(e.p/'case_support.py')
 assert binding['source']==e.pin and e.h(e.q/'seeds.json')==e.read(e.q/'native-v3.json')['seeds']
 data=e.read(e.p/'order.json')['pairs'];assert len(data)==80 and list(range(1,81))==[r['pair']for r in data]
 raw=e.q/'score-v1';raw.mkdir(mode=0o700)
 native=e.read(e.q/'native-v3.json')['shapes'];ledger=[]
 with (raw/'lock').open('xb')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  try:
   e.put(raw/'start.json',{'host':host(),'inputs':{k:e.h(e.p/k)for k in ('clock-binding.json','score-grant.json','order.json','score-driver.py','inner-clock.py')},'seeds':e.h(e.q/'seeds.json'),'native':e.h(e.q/'native-v3.json')})
   for row in data:
    rr=raw/f"pair-{row['pair']:02}";rr.mkdir();e.put(rr/'before.json',host())
    for arm in row['order']:
     normal_slot(arm,row['case'],rr/arm,native[row['case']+'-'+arm],'score')
    e.put(rr/'after.json',host());ledger.append({'pair':row['pair'],'A':e.h(rr/'A/receipt.json'),'B':e.h(rr/'B/receipt.json'),'before':e.h(rr/'before.json'),'after':e.h(rr/'after.json')})
    if row['pair']%8==0:print('completed',row['pair'],'of 80 pairs',flush=True)
   post=raw/'post';post.mkdir()
   for v in cs.cases:
    for arm in ('A','B'):
     normal_slot(arm,v,post/(v+'-'+arm),native[v+'-'+arm],'post')
   e.state_workspace('new')
   e.put(raw/'terminal.json',{'status':'complete','pairs':ledger,'posts':file_manifest(post),'final_host':host()})
   print('All 80 original pairs and six post-run native sequences verified.',flush=True)
  except BaseException as x:
   e.put(raw/'failure.json',{'error':repr(x),'pairs_completed':len(ledger),'storage':e.bd()});raise
if __name__=='__main__':main()
