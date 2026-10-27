"""Reproject every numeric wire query discriminant with the writer's source revision."""
from pathlib import Path
import json,re,subprocess,hashlib
d=Path(__file__).resolve().parent;r='/home/dev-user/code/oss/ohm-rust-private-native-20261027'
sources={'B':'2fab350c','C':'27029b4b'};old=json.loads((d/'kinds.json').read_bytes());tables={}
for arm,ref in sources.items():
 ver=subprocess.check_output(['git','-C',r,'rev-parse',ref],text=True).strip()
 q=subprocess.check_output(['git','-C',r,'show',ver+':compiler/rustc_middle/src/queries.rs'])
 s=q.decode();ns=re.findall(r'^    non_query (\w+)',s,re.M)+re.findall(r'^    query (\w+)',s,re.M)
 tables[arm]=ns;assert ns[7]=='Metadata' and len(ns)in (356,357)
 (d/('writer-kinds-'+arm+'.json')).write_text(json.dumps(dict(revision=ver,bytes_sha256=hashlib.sha256(q).hexdigest(),kinds=ns),indent=2)+'\n')
assert tables['C']==old
for p in (d/'h5/captured/typed-queries').glob('*/*/*.json'):
 row=json.loads(p.read_bytes());ns=tables[row['arm']]
 for j in row['jobs']:
  result=j.get('result',{})
  if 'named' not in result: continue
  result['named']={s:{ns[old.index(k)]:v for k,v in m.items()} for s,m in result['named'].items()}
  result['direct_metadata_inputs']=[[s,ns[old.index(k)]]for s,k in result['direct_metadata_inputs']]
 dest=d/'h5/projected'/row['mode']/row['arm'];dest.mkdir(parents=True,exist_ok=True);(dest/(row['phase']+'.json')).write_text(json.dumps(row,indent=2,sort_keys=True)+'\n')
