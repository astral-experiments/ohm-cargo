from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parent
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
for line in (p/'SHA256SUMS').read_text().splitlines():
 h,n=line.split('  ',1);assert sha(p/n)==h
r=json.loads((p/'result.json').read_bytes()); ph=r['phases']; assert len(ph)==42 and len({v[4] for v in ph.values()})==42 and len({v[5] for v in ph.values()})==42
assert sum(v[0]==0 for v in ph.values())==36 and sum(v[0]==1 for v in ph.values())==6 and all(v[1]==1 and v[2]==(v[0]==0) for v in ph.values())
assert len(r['git_labels'])==len(set(r['git_labels'].values()))==3
valid=r['per_successful_elf_and_independent_failure'];assert [valid[k]['verdict'] for k in 'ABC']==['lock-oracle=17','lock-oracle=29','lock-oracle=41'] and len({valid[k]['elf_sha256'] for k in 'ABC'})==3 and valid['invalid'][0][0]=='E0308'
assert len(r['overlaps_and_retention'])==8 and r['kernel_traces']==690
for a,hold,settled in [('P',2,1),('G',3,2)]:
 phases=[x for x in r['overlaps_and_retention'] if x['arm']==a];assert len(phases)==4
 for x in phases:
  if x['phase']=='reader-protected-extra':
   assert len(x['while_reader'])==hold and len(x['quiescent'])==len(x['after_unlock'])==settled
  else:
   assert x['observed_distinct_exclusive_FLOCKs'] and x['survivor_identity_and_lock_preserved']
   if x['phase']=='overlap-success':assert x['actual_GC_EAGAIN'] and x['young_session_at_peer_GC_micros']>10000000
print('Verified all 42 direct rustcs, 36 stock link outcomes, six E0308s, six paired overlaps and both retention controls.')
