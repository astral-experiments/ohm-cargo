"""Verify the compact instruction evidence without Cargo or private filesystem paths."""
from pathlib import Path
import math,statistics,json,gzip,hashlib
p=Path(__file__).resolve().parent
def read(f):return json.loads((gzip.open(p/f,'rb').read() if f.endswith('.gz') else (p/f).read_bytes()))
def sh(b):return hashlib.sha256(b).hexdigest()
def verify():
 b=read('binding.json.gz');rows=read('counts.json.gz');published=read('statistics.json');assert b['protocol_sha256']=='eaf1845996d4b4d8182fd4fb8ecc33bc8da414b0c492714b1cdcf3bcabc4ebc7' and b['admitted']=='ae49627468c050065ad24fd4d23a405d34c7915064331f7997b636d4e1ec467f'
 assert b['hardware']['syscall']==298 and b['hardware']['errno']==13 and b['hardware']['result']==-1 and b['hardware']['perf_stat_status']!=0
 for a,c in b['calibrations'].items():
  assert c['cargo']==b['control']['baseline'if a=='A'else'candidate'] and c['source']==b['software_inputs']['counter_source'] and c['drrun']==b['software_inputs']['runtime']['bin64/drrun']; assert len(c['calibrations'])==6
  for m,nt in [('thread',2),('c',1),('multi',3)]:
   rr=[c['calibrations'][m+'-'+str(n)]for n in (1000,2001000)]
   for g in rr:
    t=g['threads'];f=g['entries']; assert len(t)==len(set(t))==nt and sorted(t)==sorted(int(x[1])for x in f);assert sum(int(x[2]) for x in f)==g['ir'];assert g['other']==0 and g['loop']==sum(int(x[3])for x in f)
   d=rr[1]['ir']-rr[0]['ir'];assert abs(d-4000000)<40000 if m=='thread' else abs(d)<100000
 setup=b['qualified_version_and_rejected_discovery'];assert setup['registered_samples_before_refusal']==0 and sorted(x['successful_exec']for x in setup['additional_children'])==['getconf','lsb_release'] and setup['scored_exit']==0
 for a,g in b['physical_reopen']['arm'].items():
  assert g['read_only']and g['ordinary_euid']==1000 and g['caller_exit']==0 and g['stdout_sha256']==sh(b'17 29 12\n') and g['stderr_sha256']==sh(b'')
  assert sorted(g['files'][k]['sha256']for k in ('rmeta','rlib'))==b['seed']['products'] and g['files']['consumer']['sha256']==b['seed']['runtime'][1]
  assert g['files']['cargo']['sha256']==b['control']['baseline'if a=='A'else'candidate'] and all(g['files'][key]['sha256']==b['control'][key] for key in ('rustc','wild'))
 assert len(b['native'])==12
 for n in b['native']:
  assert n['compile']==n['link']==0 and n['outputs']==b['seed']['products']
  if n['tag']=='version':assert n['threads'] and n['argv_classes']==['cargo','cargo','drrun','libdynamorio.so']
  else:assert n['roster']==[['ruff_text_size',['lib'],[]]] and n['caller']==b['seed']['runtime'] and n['argv_classes']==['cargo','cargo']
 expected=[(e['pair'],e['endpoint'],e['order'],a,e['source'])for e in b['schedule']for a in e['order']];assert len(expected)==len(rows)==64
 assert expected==[(x['pair'],x['endpoint'],x['order'],x['arm'],x['source'])for x in rows]
 pairs={}
 for r in rows:
  a=r['arm'];end=r['endpoint'];repeat='repeat'in end;ts=r['threads'];fs=r['thread_entries'];pid=r['pid'];assert r['actual_original_arguments']==['build','-p','ruff_text_size','--locked','--offline']
  assert sorted(int(x[1])for x in fs)==ts and len(set(ts))==len(ts) and pid in ts and sum(int(x[2])for x in fs)==r['ir']>0
  assert [sum(int(x[j])for x in fs)for j in (3,4)]==[r['serializer'],r['fallback']]==([0,0]if repeat else[2,1]if a=='A' else[1,0])
  assert repeat==(r['before']==r['after']) and r['outputs']==b['seed']['products'] and r['lock']==b['control']['lockfile']
  assert all(x[0]==pid for x in r['execs']) and [x[1]for x in r['execs']]==['cargo','cargo','drrun','libdynamorio.so'];assert all(x['thread'] for x in r['clones'].values()) and set(ts)<={pid,*map(int,r['clones'])}
  assert r['physically_enrolled']==b['control']['baseline' if a=='A' else'candidate'] and all(len(v)==64 for v in r['raw_kernel'].values()) and r['stdout']==sh(b'')
  pairs.setdefault(end,{}).setdefault(r['pair'],{})[a]=r['ir']
 pvals={}
 for end,d in pairs.items():
  s=published[end];a=[d[i]['A']for i in range(1,9)];c=[d[i]['B']for i in range(1,9)];changes=[100*(x-y)/x for x,y in zip(a,c)];wins=sum(x>0 for x in changes);n=sum(x!=0 for x in changes);k=min(wins,n-wins);pval=min(1,2*sum(math.comb(n,j)for j in range(k+1))/2**n);pvals[end]=pval
  assert s['pairs']==[list(v)for v in zip(a,c)] and s['n']==8 and s['A_median']==statistics.median(a) and s['B_median']==statistics.median(c) and s['paired_reduction_pct']==statistics.median(changes) and s['median_order_interval_pct']==[min(changes),max(changes)] and s['wins']==wins and s['p_sign']==pval
  assert [q['order']for q in b['schedule']if q['endpoint']==end].count('AB')==4
 prev=0
 for j,end in enumerate(sorted(('reverse','restore'),key=pvals.get)):
  prev=max(prev,min(1,pvals[end]*(2-j)));assert published[end]['p_holm_directions']==prev
 return published
def reject_mutations():
 import copy,tempfile,sys,shutil
 global p
 home=p
 with tempfile.TemporaryDirectory()as tmp:
  p=Path(tmp)
  for f in ('binding.json.gz','counts.json.gz','statistics.json'):shutil.copyfile(home/f,p/f)
  original=read('counts.json.gz')
  for k in ('missing-row','unpaired-thread','unexpected-child','wrong-output','recount','wrong-elf','salvage-fallback','changed-order'):
   data=copy.deepcopy(original);v=data[0]
   if k=='missing-row':data.pop(1)
   elif k=='unpaired-thread':v['thread_entries'][0][1]=str(v['pid']+1000000)
   elif k=='unexpected-child':v['clones']['123456']={'parent':v['pid'],'thread':False}
   elif k=='wrong-output':v['outputs'][0]='f'*64
   elif k=='recount':v['ir']+=3
   elif k=='wrong-elf':v['physically_enrolled']='0'*64
   elif k=='salvage-fallback':v['thread_entries'][0][4]=str(int(v['thread_entries'][0][4])+1)
   elif k=='changed-order':data[0],data[1]=data[1],data[0]
   (p/'counts.json.gz').write_bytes(gzip.compress(json.dumps(data).encode(),mtime=0))
   try:verify()
   except (AssertionError,ValueError,KeyError):pass
   else:raise RuntimeError('accepted '+k)
  p=home
if __name__=='__main__':
 import sys
 results=verify()
 if '--self-test' in sys.argv:reject_mutations()
 print('64 original parent instruction counts, 12 calibration workloads and 10 true one-unit native controls verified.')
 print(json.dumps(results,indent=1,sort_keys=True))
