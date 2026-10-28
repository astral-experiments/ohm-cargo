"""Run the unchanged H8 comparison with the two recovered, physically private registry stores."""
import fcntl, importlib.util, json, os, shutil, sys
from pathlib import Path
H=Path('/home/dev-user/.cache/ohm-output-path-ruff-20261028');O=H/'qualified-whole-h8-v2';old=H/'qualified-whole-v1';P=H/'amendment.json'
spec=importlib.util.spec_from_file_location('recovery',H/'recover-registry.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r);g=r.worker();s=g['s'];g['out']=O

def check(mode,anchor):
 paths=[Path(p) for p in anchor['dot_d']];prods=[Path(p) for p in anchor['products']]
 assert g['proofs']()==anchor['proofs'] and g['stamps'](prods)==anchor['product_stamps'] and set(g['depfiles'](mode))==set(paths) and g['contents'](paths)==anchor['dot_d'] and g['contents'](prods)==anchor['products'],mode

def run(phase):
 a=json.loads(P.read_bytes());assert g['sha'](H/'whole-paths.py')==a['original_worker'] and g['sha'](H/'plan.json')==a['original_plan'];assert g['sha'](H/'recover-registry.py')==a['activation_helper'] and g['sha'](Path(__file__))==a['phase_worker']
 assert g['sha'](H/'subjects/qualified-pair.json')==g['plan']['matched_pair'] and all(g['sha'](p)==g['plan']['subjects'][k] for k,p in g['armfiles'].items());assert sorted(g['rustc_hashes']().values())==sorted(g['plan']['rust'].values());t=g['tools'];assert [g['sha'](p) for p in (t/'sdk/bin64/drrun',t/'sdk/lib64/release/libdynamorio.so',t/'client/libpidcounter.so')]==g['plan']['counter']
 assert not any(old.glob('*/ir/*/record.json')) and not any(old.glob('*/wall/*/record.json'));assert g['sha'](H/'rejected-v1-diagnostic.json')==a['original_failure']
 modes={'workspace':'matched-workspace','test':'test'}
 if phase=='qualify':O.mkdir()
 else:
  assert phase=='score' and (H/'h8-physical-scoring.grant').read_text().strip()==g['sha'](P) and not any(O.glob('*/ir/*/record.json')) and not any(O.glob('*/wall/*/record.json'))
  q=json.loads((O/'qualify.json').read_bytes());assert q['anchors']==a['anchors'] and q['amendment']==g['sha'](P)
 keys={}
 for mode,key in modes.items():
  prior=old/mode/'qual';new=O/mode/'qual';assert g['sha'](prior/'anchor.json')==a['anchors'][mode];anchor=json.loads((prior/'anchor.json').read_bytes());assert r.registry_id(r.V/key)==a['registry'][mode] and r.registry_id(r.live)==a['registry']['test']
  if phase=='qualify':shutil.copytree(prior,new)
  assert g['sha'](new/'anchor.json')==a['anchors'][mode]
  with r.activated(key):
   check(mode,anchor)
   if phase=='qualify':
    for arm in ('parent','candidate'):
     g['switch'](arm);paths=[Path(p) for p in anchor['dot_d']];before=g['stamps'](paths);target=O/mode/('isolation-'+arm);record=g['invoke'](target,mode,'audit');after=g['stamps'](paths);assert sorted(p for p in before if before[p]!=after[p])==anchor['legacy_rewrites'];assert record['units']==anchor['units'] and set(record['products'])==set(anchor['products']);keys[mode+'/'+arm]=g['sha'](target/'record.json');check(mode,anchor)
   else:g['score_mode'](mode);check(mode,anchor)
  assert r.registry_id(r.V/key)==a['registry'][mode] and r.registry_id(r.live)==a['registry']['test']
 receipt=dict(phase=phase,amendment=g['sha'](P),plan=g['sha'](H/'plan.json'),helper=g['sha'](H/'whole-paths.py'),anchors=a['anchors'],audits=keys,retained_registry=r.registry_id(r.live),physical_private={m:r.registry_id(r.V/k) for m,k in modes.items()});g['write'](O/(phase+'.json'),receipt);print(phase,receipt,flush=True)
if __name__=='__main__':
 assert len(sys.argv)==2 and sys.argv[1] in ('qualify','score');os.umask(0o077);os.sched_setaffinity(0,range(8))
 with s.LOCK.open('a') as lock:fcntl.flock(lock,fcntl.LOCK_EX);run(sys.argv[1])
