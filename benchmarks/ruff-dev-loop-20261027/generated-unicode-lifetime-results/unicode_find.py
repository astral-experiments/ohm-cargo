"""Locate the private run receipt on this exact layout from the real typed output."""
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent));from basic import *
raw=q/'unicode-lifetime-v1';g=Path(json.loads((raw/'restored/generated.json').read_bytes())['typed']['out_dir'])
rows={}
for z in (g.parent,g.parent.parent,g.parent/'run',s/'debug/build/workspaces'/Path(*g.parts[-5:-1]),s/(g.parent.relative_to(t))):
 if str(z) in rows:continue
 rows[str(z)]=sorted(str(v.relative_to(z))for v in z.glob('*') if v.name not in ['generated.rs','generated_alias.rs','generated_phf.rs'])
for c in [g.parent.parent,s/(g.parent.parent.relative_to(t))]:
 if c.is_dir():
  for n in ['stdout','output','root-output','stderr','invoked.timestamp']:
   rows[str(c)+'glob_'+n]=[str(f)for f in c.glob('*/*/'+n)]+[str(f)for f in c.glob('*/'+n)]
put(raw/'path-inspection.json',rows);print(json.dumps(rows))
