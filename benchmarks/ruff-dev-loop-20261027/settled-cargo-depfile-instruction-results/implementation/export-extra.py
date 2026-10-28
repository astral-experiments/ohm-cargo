"""Bind source tests and original scout receipts without including private registry endpoints."""
from pathlib import Path
import hashlib,json,gzip,shutil,re
H=Path('/home/dev-user/.cache/ohm-output-path-ruff-20261028');D=Path('/home/dev-user/.cache/ohm-settled-cargo-20261028');T=Path('/home/dev-user/.cache/ohm-output-path-cargo-tests-20261028');O=H/'portable-evidence-extra';O.mkdir();original={}
def save(n,p,compressed=False):
 data=p.read_bytes();name=str(n)+('.gz' if compressed else '');q=O/name;q.parent.mkdir(parents=True,exist_ok=True);new=re.sub(rb'socket-' rb'firewall-' rb'registry[.][A-Za-z0-9_.-]+-[a-f0-9]{16}',b'registry-fixture-hash',data);assert b'socket-' b'firewall-' b'registry' not in new,(p,new[:80]);original[name]={'original':hashlib.sha256(data).hexdigest(),'portable':hashlib.sha256(new).hexdigest()};q.write_bytes(gzip.compress(new,compresslevel=9,mtime=0) if compressed else new)
for n in ['results.json','full-cargo-unit-tests.json','dependencies.json','full-cargo-unit-tests.log','path-integration.log','generated.log','encoded.log']:
 save('cargo-tests/'+n,T/n,n.endswith('.log'))
for n in ['package-controls-v3','output-wire-control','observer-dot-d-control']:
 q=H/n;save('functional/'+n+'/complete.json',q/'complete.json')
 for arm in ['parent','candidate']:
  for p in sorted((q/arm).rglob('*')):
   if p.is_file() and p.name in ('public.d','encoded','row.json','stderr','err','status.json') and p.stat().st_size<131072:save('functional/'+n+'/'+str(p.relative_to(q)),p,p.name!='row.json')
# Stateful Rust fixture is local-path only and contains neither target nor shared directories.
for p in sorted((H/'observer-dot-d-control/src').rglob('*')):
 if p.is_file() and (p.suffix=='.rs' or p.name=='Cargo.toml'): save('functional/observer-fixture/'+str(p.relative_to(H/'observer-dot-d-control/src')),p)
for n in ['scoped-block/client.c','scoped-block/CMakeLists.txt','output-path-study/capture.json','output-path-study/input','output-path-study/output','output-path-study/replay.json','basic-block/top.json','basic-block/observations/complete.json']:
 if (D/n).is_file():save('profile/'+n,D/n,(D/n).stat().st_size>15000)
for name in ['scoped-block/rows','output-path-study']:
 for p in sorted((D/name).rglob('*')):
  if p.is_file() and (p.name.startswith(('count-','profile-')) or p.name in ('verified.json',) or name=='scoped-block/rows' and p.name in ('stderr','stdout') or p.suffix=='.args'):save('profile/'+str(p.relative_to(D)),p)
(O/'original-and-portable.json').write_text(json.dumps(original,indent=2,sort_keys=True)+'\n');files=sorted(p for p in O.rglob('*') if p.is_file());sf=O/'SHA256SUMS';sf.write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(O))+'\n' for p in files));print(len(files),hashlib.sha256(sf.read_bytes()).hexdigest())
