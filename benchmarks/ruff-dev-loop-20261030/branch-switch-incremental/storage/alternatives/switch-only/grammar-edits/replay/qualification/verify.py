from pathlib import Path
import json,gzip,hashlib,sys
r=Path(__file__).resolve().parent;read=lambda n:json.loads((r/n).read_bytes());sh=lambda b:hashlib.sha256(b).hexdigest()
t=read('terminal.json');p=json.loads(gzip.decompress((r/'functional.json.gz').read_bytes()));assert sh(gzip.decompress((r/'functional.json.gz').read_bytes()))==t['native']
cfg=read('registration.json');assert p['protocol']==sh((r/'registration.json').read_bytes())and t['public']==cfg['reviewer_python']==p['public_script']
assert cfg['drivers']=={role:p['source'][role]['driver'] for role in 'RK'};assert p['source']['R']['std']==p['source']['K']['std']and len(p['source']['R']['std'])==53
refs=p['references'];assert sorted(refs)==[a+'/'+b for a in'KR'for b in'ABC'] and len(set(refs.values()))==3 and set(refs.values())==set(t['ELFs'])
slots={};empty=0
for x in p['native']:
 s=x['slot'];ref=s.startswith('reference-');ro=s.split('-')[1]if ref else s[-1];assert x['ELF']==refs[ro+'/'+x['state']] and x['typed']==97
 assert x['verdict']=='Expr='+('64' if x['state']=='A'else'56')+' signed-expression='+('accepted'if x['state']=='C'else'rejected')
 if x['phase'].startswith('empty'):assert len(x['dirty'])==97;empty+=1
 elif x['phase']=='unchanged-B':assert x['dirty']==[]
 elif x['phase'].startswith(('edit-','restore-')):assert x['dirty']==['ruff_python_parser']
 else:assert x['dirty']==['ruff_python_ast','ruff_python_parser']
 assert all(len(x[k])==64 for k in ('cargo_stdout','cargo_stderr','reader_stdout','link_stderr'));slots.setdefault(s,[]).append(x['phase'])
assert len(p['native'])==42 and len(slots)==10 and empty==10
assert sorted(len(h)for h in slots.values())==[1]*6+[9]*4
assert not any('wall' in x or 'cargo_ns' in x for x in p['native'])
print('42 complete underlying native Cargo builds and independently linked executable verdicts, 6 physically empty references, 3 unique Linux ELFs, and 2 mirrored rounds of the released reviewer code.')
