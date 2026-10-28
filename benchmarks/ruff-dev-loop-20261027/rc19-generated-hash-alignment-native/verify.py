"""Replay data, behavioral and acquisition gates. No executable from the campaign needs to be loaded."""
from pathlib import Path
import hashlib,json,sys
D=Path(__file__).resolve().parent
read=lambda p:json.loads((D/p).read_bytes())
sha=lambda p:hashlib.sha256((D/p).read_bytes()).hexdigest()
arms=read('release-subjects.json');images={k:i['image']for k,i in arms['images']['arms'].items()}
assert arms['heads']==['235f9228651b74c591e6f62cae4c9b761448dd2d','2f6f0d690ac1f787832ad86d2205d2a7429ad171']
assert images=={'A':'50c9529780a0042c7a6be321edc15d1e016f2bf1612ff02040db4273976a3131','B':'998a208821e4ae7a44175267aaaac08a135e93eab733e879f5b0663a4e923056'}
assert arms['images']['builder']['profile']=='481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7'
assert arms['externs']=={'src/lib.rs':80,'src/bin/cargo/main.rs':81} and len(set(arms['args'].values()))==2
edges=arms['edges'];assert edges['terminal']and len(edges['regular'])==135 and len(edges['inflight'])==20 and edges['directory']=='EISDIR'and edges['missing']=='ENOENT'
assert len({(x['prefix'],x['bytes'])for x in edges['regular']})==135 and len({(x['prefix'],x['mode'])for x in edges['inflight']})==20
reg='2d40c0ba8f68ba2bfadc489db876b49f5c442de4';phase={'forward':['initial','mutate','hold','restore'],'reverse':['initial','mutate','hold'],'mode':['initial','change_mode','mode_hold','mode_restore']}
result={}
for role in ['primary-linux','independent-linux']:
 n=read(role+'.json');o=read(role+'-output-forensics.json');assert n['role']==role and n['numeric_plan_ref']==reg and n['complete']and n['native_source']==sha('reproduce/wall-final.py') and n['unmodified_runner']==sha('reproduce/host-wall-v2.py')
 def owner(r,c):
  assert r['actual_cargo_sha256']==images[c] and r['euid']==r['egid']==['1000']*4 and r['uid_map'].split()==['0','0','4294967295']and r['same_ordinary_mount'] and r['affinity']==list(range(8))
  a=r['paths'];assert set(a)>=set(['/','/home','$HOME']) and a['/']['uid']==a['/home']['uid']==0 and a['$HOME']['uid']==1000 and all(v['uid']in(0,1000)and v['gid']!=65534 and int(v['mode'],8)&2==0 for v in a.values())
 def reads(z,arm):
  assert z['registry_cache_hits']=={'/.ohm-git-index-sha1dc-v1/':1,'/.ohm-registry-json-v2/':118} and len(z['trace_digest_map'])>=2 and z['registry_inputs']['registry read paths']>0
  assert z['exec'].count('cargo')>=2 and not(set(z['exec'])&{'rustc','cc','ld','ld.bfd','collect2','rust-lld','ld.lld','wild','as'})
  for name,count in [('generated.rs',1787150),('generated_phf.rs',554093),('zipped_typeshed.zip',5577690)]:
   f=z['file_observations'][name];assert f['bytes']==2*count and f['requests']>=4 and (f['first'][0]==16384)==(arm=='A')
 assert {r['seed']+r['image']for r in n['same_seed_crossovers']}=={'AA','AB','BA','BB'}
 for r in n['same_seed_crossovers']:
  assert r['same_data'] and r['before']==r['after'] and r['rows']==r['fresh']==182;owner(r['ownership'],r['image']);reads(r['physical'],r['image'])
 for arm,z in n['per_arm'].items():
  assert (z['cold_fresh'],z['cold_rows'],z['warm_fresh'],z['warm_rows'])==(0,182,182,182)
  assert len(z['all_declared_files'])==330 and all(len(k)==len(v['sha256'])==64 and v['bytes']>0 for k,v in z['all_declared_files'].items());owner(z['actual'],arm);reads(z['physical'],arm)
  assert z['products']==o['roles'][arm] and sorted(v['size']for v in z['generated'].values())==[554093,1787150,5577690]
 a,b=n['per_arm']['A'],n['per_arm']['B'];assert all(a[k]==b[k]for k in ('unit_roster','checks','generations','reader','generated'))and a['all_declared_files'].keys()==b['all_declared_files'].keys()
 for pair,x in o['pairs'].items():
  assert x['complete_byte_accounting']and len(x['archive_members'])==7
  al=x['archive_members'];assert [f['kind']for f in al]==['/','//','lib.rmeta','lib.rmeta-link']+['ELF codegen unit']*3 and all(al[i]['before']==al[i]['after']for i in (0,4,5,6))
  for f in x['metadata_fields']:
   assert f['offset']>=0 and len(f['A'])==len(f['B'])==32 and f['A']!=f['B']
  assert x['raw_different_bytes']<=16*len(x['metadata_fields']) and len(x['metadata_fields'])in(0,17)
 if role=='primary-linux':
  assert len(o['roles'])==4 and any(o['roles'][c]['.rmeta']==o['roles']['B']['.rmeta']for c in ('S0','S1'));assert o['pairs']['A-S0']['raw_different_bytes']>0 and o['pairs']['S0-S1']['raw_different_bytes']>0
 for typ,phases in phase.items():
  xx=[n['regular_file_changes'][arm+'-'+typ]for arm in 'AB'];assert [r['phase']for r in xx[0]]==[r['phase']for r in xx[1]]==phases
  for ra,rb in zip(*xx):
   assert all(ra[k]==rb[k]for k in('phase','dirty','rows','fresh','program','mode','outer_zip','quantity','events','native_generation','unit_identities'))
   for arm,r in zip('AB',(ra,rb)):
    x=r['phase'];expected='changed'if typ=='forward'and x in ('mutate','hold')else'old';other='old'if expected=='changed'else'changed'
    assert r['rows']==182 and r['fresh']==182-len(r['dirty']) and r['cargo']==images[arm] and r['program']==a['reader']
    assert all(r['quantity'][ext][expected]==k and r['quantity'][ext][other]==0 for ext,k in [('.rlib',2),('.rmeta',1)])
    if x=='initial':assert r['dirty']==[] and r['events']==['0','0','terminal opens 2 exit 0']
    if x=='mutate':assert r['dirty']==['ty_vendored']and r['events']==['0','1','terminal opens 2 exit 0']
    if typ=='mode':
     assert r['dirty']==(['ty_vendored']if x in ('change_mode','mode_restore')else[])
  if typ=='mode':assert xx[0][0]['mode']==xx[0][3]['mode']and xx[0][1]['mode']==xx[0][2]['mode']==xx[0][0]['mode']^0o100
 result[role]={'preflight':n['preflight_raw'],'cohorts':len(o['roles']),'ordinary_warm':182,'complete_files':330,'physical_crossovers':4,'counterfactual_file_controls':22,'raw_different_bytes_cold_A_B':o['pairs']['A-B']['raw_different_bytes'],'cache_hits':119}
print(json.dumps({'native_gates_passed':True,'whole_command_timing':'none','file_digest_cases':155,'hosts':result},sort_keys=True,indent=2))
