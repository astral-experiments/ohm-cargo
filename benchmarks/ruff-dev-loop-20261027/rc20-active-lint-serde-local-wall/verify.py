"""Verify the observed native process and product facts and recompute every paired interval."""
from pathlib import Path
import argparse,collections,copy,gzip,hashlib,json,math,re,statistics,sys
D=Path(__file__).resolve().parent;sys.path.insert(0,str(D));from local_stats import calculate
def read(n):
 f=D/n;b=f.read_bytes();return json.loads(gzip.decompress(b)if n.endswith('.gz')else b)
def filehash(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def sha_json(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def handle(plan,bind,nat,rows,archive,witness,timer):
 assert bind['schedule']==filehash(D/'protocol.json')=='fa4482ec1786dbaf6256f2e322b6450a3f5ee1e975cdc73b1167f9bdd8e263f9'
 assert bind['admission_data']['clock_count']==0 and bind['sources']['lock']==plan['root']['lock'] and len(timer['work'])==28 and bind['minimum_free'][0]>45*2**30 and bind['minimum_free'][1]>40*2**30 and bind['minimum_free'][2]>16*2**30 and bind['mounted']==3*2**30
 waits=[]
 for l in timer['kernel_text'].splitlines():
  if l.startswith('wait4('):
   m=re.match(r'wait4\((\d+), .*?, 0, NULL\)\s+=\s+(\d+)$',l);assert m and m[1]==m[2];waits.append(int(m[1]))
 assert waits==[z['pid'] for z in timer['work']]
 for a in archive.values():
  assert a['typed']==sha_json(a['projection']) and len(a['original_names'])==len(a['projection']['objects']) and a['projection']['symbol_count']>=0
 timed=[];returned=0;clean_cases=0
 for s in ('serde',):
  n=nat[s];assert len(n)==bind['native_rows'][s]
  for tag,v in n.items():
   st,role,phase=tag.split('/');arm=role[0];state=v['state'];assert arm in 'AB' and state in ('original','older')
   assert v['raw_source']==plan['root']['source_manifest'if state=='original'else'reverse_manifest'] and all(len(f[1])==64 and f[0]>=0 for f in v['files'].values())
   cc=n[state+'/A-cold/cold'];assert v['semantic']==cc['semantic'] and v['oracle']==cc['oracle']
   comp=[a for a in v['events']if a['role']=='real-rustc'];ln=[a for a in v['events']if a['role']=='native-link'];assert [a['role']for a in v['events'][:2]]==['rustup-proxy','cargo']
   for a in comp:
    if a['root']:assert a['lint']==(['--allow=clippy::large_stack_arrays']if state=='older'else[])
   fresh=[x[-1] for x in v['artifact_roster']]
   if phase=='cold':assert role.endswith('cold') and any(a['root']for a in comp);clean_cases+=1
   if phase in ('repeat','base','undo-repeat','logged-settled','enable-same-source'):assert not comp and not ln and all(fresh)
   if phase in ('first','undo') and role.endswith(('probe','logging-v2','logging-v3','logging','post')):
    assert len(comp)==(2 if s=='serde'else 1) and len(ln)==int(s=='serde') and all(a['root']for a in comp)
    if phase=='undo':returned+=1
   if role.endswith('logging-v3'):
    if phase=='enable-same-source':assert v['registry_full']>0 and v['fingerprints'][0]!=v['fingerprints'][1]
    if phase=='logged-settled':assert v['registry_full']==0 and v['registry_hit']>0 and v['fingerprints'][0]==v['fingerprints'][1]
    if phase in ('first','repeat'):
     full=arm=='A'and phase=='first';assert (v['registry_full']>0)==full and (full or v['registry_hit']>0)and (v['fingerprints'][0]!=v['fingerprints'][1])==full
   if 'library.rlib'in v['raw']:assert archive[v['raw']['library.rlib']]['typed']==v['semantic']['library.rlib']
   assert v['raw']['library.rmeta']==v['semantic']['library.rmeta']
   if s=='check':assert v['oracle']['code']=='E0599'and v['oracle']['valid_exit']==0 and v['oracle']['invalid_exit']!=0
   if s=='build':assert v['oracle']['value']=='17 29 12'and len(v['oracle']['caller'])==64
   if s=='serde':assert v['raw']['test']==v['oracle']['test_sha']and v['oracle']['all_passed']==3 and sorted(v['oracle']['list'])==['invalid_range_deserialization','range_serialization','size_serialization']
  if not bind['completed'][s]:assert s in bind['failure'];continue
  rr=rows[s];assert len(rr)==32;last=None
  for p,reg in zip(rr,plan['schedule'][s],strict=True):
   assert all(p[k]==reg[k]for k in reg)and set(p['arms'])=={'A','B'};st=p['from_state'];dest=p['to_state'];assert st!=dest
   for arm in p['order']:
    a=p['arms'][arm];base=n[st+'/'+arm+'-trained/repeat'];first=n[st+'/'+arm+'-probe/first'];cold_a=n[dest+'/A-cold/cold'];cold_b=n[dest+'/B-cold/cold']
    assert a['actual_cargo']==bind['sources'][arm] and a['source_digest']==first['raw_source'] and a['lock']==bind['sources']['lock'] and a['independent_clean']==[cold_a['digest'],cold_b['digest']]
    assert a['expected_first']==first['digest'] and a['mid']==a['marker_after']==first['fingerprints'][1] and a['marker_before']==base['fingerprints'][1]==first['fingerprints'][0]
    assert (a['marker_before']==a['mid'])==(arm=='B') and a['semantic']==cold_a['semantic']==cold_b['semantic'] and a['oracle']==cold_a['oracle']==cold_b['oracle']
    assert a['files']['library.rmeta']==a['semantic']['library.rmeta'] and a['jobs']['edit'] and not a['jobs']['repeat'] and a['inherited_artifacts']==hashlib.sha256(json.dumps(base['artifact_digests'],sort_keys=True).encode()).hexdigest()
    if s=='serde':assert a['files']['test']==a['oracle']['test_sha']
    for k in ('edit','repeat'):
     z=a[k];assert z['status']==0 and z['pid']>0 and 0<z['ns']==z['ended_ns']-z['started_ns'] and (last is None or z['started_ns']>last)
     assert a['raw_streams'][k+'.stdout']==[0,hashlib.sha256(b'').hexdigest()] and a['streams'][k+'.stderr']==a['raw_streams'][k+'.stderr'][1]
     timed.append(z['pid']);last=z['ended_ns']
 assert clean_cases==4 and returned==4 and len(timed)==128*sum(bind['completed'].values()) and len(set(timed))==len(timed)
 if witness:
  assert len(witness['views'])==8*sum(bind['completed'].values())
  for name,v in witness['views'].items():
   assert v['all_views_read_only'] and all(k['bytes']==witness['object_sizes'][k['sha256']] for k in v['files'].values())
   assert any(v['original_result']==r['digest']for r in nat[v['selection']].values()) if v['kind']=='cold' else any(v['original_result']==a['raw_result'] for p in rows[v['selection']]for a in p['arms'].values())
 return len(timed)
def main():
 args=argparse.ArgumentParser();args.add_argument('--self-test',action='store_true');opt=args.parse_args()
 files={f.name:filehash(f)for f in D.iterdir()if f.is_file()and f.name!='SHA256SUMS'}
 receipt={l[66:]:l[:64]for l in (D/'SHA256SUMS').read_text().splitlines()};assert files==receipt
 plan=read('protocol.json');bind=read('binding.json.gz');n=read('native.json.gz');r=read('pairs.json.gz');a=read('archive-witnesses.json.gz');w=read('reopened.json.gz')if(D/'reopened.json.gz').exists()else None;t=read('timer.json.gz')
 cnt=handle(plan,bind,n,r,a,w,t);stats=calculate(r['serde'],plan);assert stats==read('statistics.json')
 if opt.self_test:
  # Simulate independent corruptions in memory without altering the physical ledgers.
  sel=next(s for s in r if bind['completed'][s]);arm=r[sel][0]['arms']['A'];sample=n[sel]['original/A-probe/first'];evt=next(e for e in sample['events']if e['role']=='real-rustc')
  edits=[(arm['edit'],'ns',0),(arm,'actual_cargo','0'*64),(arm,'mid','0'*64),(arm['files'],'library.rmeta','0'*64),(evt,'lint',[]),(n['serde']['original/B-logging-v3/first'],'registry_full',1)]
  for d,k,v in edits:
   old=d[k];assert old!=v;d[k]=v
   try:handle(plan,bind,n,r,a,w,t)
   except (AssertionError,KeyError):pass
   else:raise RuntimeError('corruption accepted: '+k)
   finally:d[k]=old
 print('verified',cnt,'ordinary Cargo timing records, 4 independent empty builds and all native source, resolver and product checks')
if __name__=='__main__':main()
