import json,hashlib
from pathlib import Path
p=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028/whole-wild-width-v2'); s='e2e-6a4ba41917b202dd'; mid=Path('debug/build/workspaces/88ed51a59715ff20/v2-440b30f8251b1ee7/ty_server/6a4ba41917b202dd'); ret={}
for color in ['observer','composed']:
 d=p/'states'/color; ret[color]={'state_exists':d.is_dir(),'subdirs':sorted(x.name for x in d.iterdir())if d.is_dir()else[],'candidates':{}}
 for k in ['target','shared']:
  td=d/k/mid
  if not td.is_dir():continue
  for x in td.rglob('*'):
   if (x.name.endswith('.rlink') or x.name.endswith('rlink-cache.json') or 'manifest' in x.name) and x.is_file() and x.stat().st_size < 10_000_000:
    raw=x.read_bytes(); rec={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()};ret[color]['candidates'][str(x.relative_to(td))]=rec
    if raw.startswith(b'{'):
     j=json.loads(raw);rec['envelope_keys']=list(j);j=j.get('manifest',j);rec['keys']=list(j);rec['version']=j.get('version');rec['objects_count']=len(j.get('objects',[]));rec['rlink_record']=j.get('rlink',{}).get('blake3');rec['executable_keys']=list(j.get('executable',{}))
print(json.dumps(ret,indent=2,sort_keys=True))
