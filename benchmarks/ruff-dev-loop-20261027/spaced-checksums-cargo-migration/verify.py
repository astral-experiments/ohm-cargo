from pathlib import Path
import hashlib,io,json,re,tarfile
p=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
if (p/'SHA256SUMS').exists():
 for l in (p/'SHA256SUMS').read_text().splitlines():
  s,n=l.split('  ',1);assert sha((p/n).read_bytes())==s
with tarfile.open(p/'cargo-and-reader.tgz','r:gz') as t,tarfile.open(p/'cargo-builder.tgz','r:gz') as b:
 def read(name,tar=t):return tar.extractfile(name).read()
 def obj(name):return json.loads(read(name))
 counts={'builds':0,'checks':0}
 def buildset(name):
  v=obj(name+'/result.json')
  for case,phases in v.items():
   for phase,r in phases.items():
    f=f'{name}/{case}/records/{phase}'
    assert obj(f+'/row.json')==r
    events=[json.loads(x) for x in read(f+'/stdout.jsonl').splitlines()]
    assert events[-1]=={'reason':'build-finished','success':True}
    arts=[e for e in events if e['reason']=='compiler-artifact'];a,=[e for e in arts if e['target']['name']=='hold_direct']
    assert len(arts)==r['units']==4 and a['fresh']==r['fresh'] and all(x['fresh'] for x in arts)==r['all_fresh']
    assert read(f+'/native').decode()==r['native'] and r['native'].strip().endswith('escape-value='+str(r['value']))
    fp=read(f+'/fingerprint');assert sha(fp)==r['fp_sha'] and fp[-41:-37].decode()==r['wire'] and fp[-33]==r['complete']
    assert sha(read(f+'/rustc.d'))==r['dep_sha']
    counts['builds']+=1
   assert phases['first']['real']==sha(read(f'{name}/{case}/original.rlib')) and phases['changed']['real']==sha(read(f'{name}/{case}/future.rlib'))
  return v
 ups=buildset('r16-cargo-upgrade-physical')
 for case,r in ups.items():
  assert r['first']['value']==r['train']['value']==r['unchanged']['value']==17
  assert r['upgrade']['value']==r['upgrade-noop']['value']==r['empty']['value']==29
  if case!='ordinary':
   assert r['changed']['value']==17 and r['changed']['all_fresh'] and r['changed']['complete']==1 and r['changed']['wire']=='OBS1'
   assert r['changed']['fp']==r['upgrade']['fp'] and r['changed']['depfile']==r['upgrade']['depfile'] and r['changed']['stamps']==r['upgrade']['stamps']
   assert r['changed']['real']==r['changed']['shadow'] and r['upgrade']['complete']==0 and not r['upgrade']['fresh'] and not r['upgrade-noop']['fresh']
   assert (r['upgrade']['shadow'] is None)==(case=='decoy-removed')
  else:assert r['unchanged']['all_fresh'] and r['changed']['value']==29 and not r['changed']['fresh'] and r['upgrade']['all_fresh']
 splits=buildset('r16-cargo-fix-physical')
 for case,r in splits.items():
  assert r['first']['value']==17 and r['changed']['value']==r['empty']['value']==29 and not r['changed']['fresh']
  assert r['unchanged']['all_fresh']==(case=='ordinary')
 chk=obj('raw-check-upgrade/result.json')
 for phase,row in chk.items():
  base='raw-check-upgrade/case/records/'+phase;assert obj(base+'/row.json')==row
  events=[json.loads(x) for x in read(base+'/stdout.jsonl').splitlines()]
  assert events[-1]=={'reason':'build-finished','success':row['exit']==0}
  diag=[d['message'] for d in events if d.get('reason')=='compiler-message' and d['message'].get('level')=='error']
  assert diag==row['diagnostics'];counts['checks']+=1
 assert counts=={'builds':36,'checks':6}
 assert chk['changed']['exit']==0 and chk['changed']['all_fresh']
 assert chk['corrected']['exit']==chk['independent']['exit']==101 and chk['corrected']['diagnostics']==chk['independent']['diagnostics'] and chk['corrected']['diagnostics'][0]['code']['code']=='E0308'
 fix=read('subjects/raw-fixed.sha256',b).decode().split()[0];assert fix=='dc377742bbae74011f4dca99b7c5ea3002e5af5b979149a6a2f8c0ba7bc726c4'
 assert b'legacy_observers_retrain_only_when_an_input_contains_spaces ... ok' in read('logs/unit.log',b)
 assert sha(read('assets/cargo-raw-paths.patch',b))=='28a36faf9edff3640428c58405dfc9163a2af6ca812e90f4f1cf417cff112fa5'
 assert sha(read('raw-rust-final.patch'))=='2b39032f1101dbab2cdbdb91e413f846d6bb78e568a9eea171d321468d30a7bb'
 red=obj('raw-rmake-stock-v2/receipt.json');assert red['exit']==101 and 'left == right' in red['stderr'] and red['driver']=='c442c2a36e1f37c92f138a8fb367fc09982931b5f1055e9742fb402566ad46a4'
 assert red['fixture']==sha(read('src/rust-raw/tests/run-make/checksum-freshness/rmake.rs'))
 assert sha(read('raw-rmake-stock-v2/case/libhelper.rlib')) in red['stderr'] and sha(read('raw-rmake-stock-v2/case/actual\\ dir/libhelper.rlib')) in red['stderr']
 print('Verified 36 ordinary builds and executed programs, six checks, committed parent rejection, Cargo migration unit, and both source patches.')
