"""Run each registered command's finite phase, keep each first failure and its logs."""
from pathlib import Path
import json,subprocess as sp,sys
R=Path(__file__).resolve().parent
assert (R/'wall-admit.exit').read_text()=='0\n'
g=json.loads((R/'wall-admission.json').read_bytes())
result={}
for name in ('check','build','serde'):
 if not g['gates'][name]['eligible']:continue
 prefix='score-'+name
 with (R/(prefix+'.stdout')).open('xb') as out,(R/(prefix+'.stderr')).open('xb') as err:
  code=sp.run(['/usr/bin/timeout','--signal=TERM','--kill-after=10s','1800','/usr/bin/taskset','-c','29,30','/usr/bin/python3','-IB',R/'controller.py','score',name],cwd=R,stdout=out,stderr=err).returncode
 with (R/(prefix+'.exit')).open('x') as f:f.write(str(code)+'\n')
 result[name]=code;print(name,'terminal',code,flush=True)
with (R/'series-closure.json').open('x')as f:json.dump(result,f,sort_keys=True)
sys.exit(int(any(result.values())))
