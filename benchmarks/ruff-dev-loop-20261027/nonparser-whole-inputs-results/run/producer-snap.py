from pathlib import Path
import hashlib,json,os,shutil,time,sys
X=Path.home()/'.cache/ohm-233-position-qualified-20261027'; Q=X/'nonparser-whole-inputs-campaign-v1';D=Q/'producer-snapshots';D.mkdir(mode=0o700); P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/native-target');S=Path('/dev/shm/ohm-nonparser-whole-inputs-20261027/state/test');J=lambda x:json.loads(x.read_bytes());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
seen={};need={'warm-1':'original','ty-diagnostic-edit-fresh':'ty-diagnostic','ty-diagnostic-restore-fresh':'original','formatter-edit-fresh':'formatter','formatter-restore-fresh':'original'};# artifact-state is published before optional CLI/process audit and any next mutation.
while len(seen)<len(need) and not (Q/'failure.txt').is_file():
 for label,view in need.items():
  stage=Q/'receipts/test'/label
  if label in seen or not (stage/'artifact-state.json').is_file():continue
  current=(S/'view').read_text();target=stage/'artifact-state.json'
  try:allfiles=J(target)
  except json.JSONDecodeError:continue
  if current!=view:seen[label]={'miss':'source moved before capture','want':view,'actual':current};continue
  spec={} if 'warm' in label else {'ty_python_semantic'} if 'ty-diagnostic' in label else {'ruff_python_formatter'}
  if not spec:spec={'ty_python_semantic','ruff_python_formatter'}
  dest=D/label;dest.mkdir();rows=[]
  for n in sorted(spec):
   metas=[(Path(p),a) for p,a in allfiles.items() if '/'+n+'/' in p and p.endswith('.rmeta') and Path(p).name.startswith('lib'+n+'-')];assert len(metas)==1,(n,metas)
   md,a=metas[0];src=S/'target'/md.relative_to(P);raw=src.read_bytes();h=hashlib.sha256(raw).hexdigest();assert h==a['sha256'];m=dest/src.name;m.write_bytes(raw);assert sha(m)==h
   rows.append({'crate':n,'path':str(md),'rmeta_sha256':h,'reported_sha256':a['sha256'],'bytes':len(raw)})
  assert (S/'view').read_text()==view;seen[label]={'view':view,'source_sha256':sha(stage/'setup.json'),'artifact_state_sha256':sha(target),'units':rows};(dest/'receipt.json').write_text(json.dumps(seen[label],sort_keys=True,indent=2)+'\n')
 time.sleep(.18)
(D/'complete.json').write_text(json.dumps(seen,sort_keys=True,indent=2)+'\n');print(json.dumps(seen),flush=True)
