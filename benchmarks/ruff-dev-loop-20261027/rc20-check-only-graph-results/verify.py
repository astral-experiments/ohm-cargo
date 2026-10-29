"""Reopen all original monotonic brackets after the terminal native checks, then independently re-run the frozen analysis."""
import gzip,hashlib,json,math,re,subprocess,sys
from collections import Counter
from pathlib import Path
p=Path(__file__).resolve().parent
def get(f):return json.loads((p/f).read_bytes())
def canon(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def proj(f):return json.loads(gzip.decompress((p/f).read_bytes()))
x=proj('terminal.json.gz');before=proj('before.json.gz');order=get('order.json');binding=get('clock-binding.json');declared=get('summary.json');pairs=get('pairs.json');assert x['exit']==0
assert x['grant']['instruction']=='score exactly 80 prospective pairs'and x['grant']['host_exclusive']and x['grant']['published_plan_commit']=='0f2276b6ee86256801ccaf063eac239a5d00f67e'
assert x['native']==binding['native_sha256']==hashlib.sha256(gzip.decompress((p/'before.json.gz').read_bytes())).hexdigest()
assert x['grant']['public_manifest_sha256']=='7dc8fe69b78c54cc9a026c32ce5d5b6630e7977bd49cc576c6499b2180ff9974'
assert len(pairs)==len(x['rows'])==len(order['pairs'])==len(x['streams'])==80 and pairs==x['rows']
last=-1;rows=0
for i,(r,exp)in enumerate(zip(pairs,order['pairs']),1):
 assert exp=={k:r[k] for k in exp} and i==r['pair'];s=x['streams'][f'pair-{i:02}']
 for side in ('before','after'):assert min(s[side]['free'])>24*2**30+256*2**20
 for arm in r['order']:
  vals=[];record=s[arm];live=before['shapes'][r['case']+'-'+arm]
  for pos,ph in enumerate(('settled','edited','repeat')):
   d=record[ph];c=d['brackets'];ns=c['end_ns']-c['start_ns']
   assert c['exit']==0 and ns>0 and last<c['start_ns'] and d['typed']==canon(live[pos]['artifacts']);last=c['end_ns'];rows+=1
   key=hashlib.sha256((json.dumps({'start_ns':c['start_ns'],'end_ns':c['end_ns'],'exit':0})+'\n').encode()).hexdigest()
   assert key==d['raw']['clock.json'];vals.append(ns)
  assert vals==r[arm]and record['rmeta']==live[-1]['rmeta_shape']and record['source']==live[-1]['source']
for group,org in before['shapes'].items():
 for z in org:
  post=x['post'][f"{group}/{z['phase']}/result.json"]
  assert all(z[k]==post[k]for k in ('phase','resolution','rustc','native','markers','rmeta_shape','artifacts'))
assert rows==480 and len(x['post'])==18
result=json.loads(subprocess.check_output([sys.executable,'-ISB',p/'analyze.py',p/'order.json',p/'pairs.json']));assert result==declared
assert hashlib.sha256((p/'analyze.py').read_bytes()).hexdigest()==binding['analysis']
print('Verified 480 interval brackets in original order, all predeclared Cargo checks, 18 post-native anchors, and frozen paired analysis.')
