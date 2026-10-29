from pathlib import Path
from collections import Counter
import gzip,hashlib,json,re
D=Path(__file__).resolve().parent
def read(s):
 f=D/s;b=f.read_bytes();return json.loads(gzip.decompress(b) if f.suffix=='.gz' else b)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
m={r.split('  ')[1]:r.split('  ')[0] for r in (D/'SHA256SUMS').read_text().splitlines()};assert set(m)=={f.name for f in D.iterdir() if f.is_file() and f.name!='SHA256SUMS'}
deny=re.compile(rb'openai[.](org|com|internal)|artifactory[.]|authorization: bearer|github_pat_|ghp_[A-Za-z0-9]{16}|/home/dev-user|/mnt/devbox|charlie-ohm-',re.I)
for p,h in m.items():
 f=D/p;assert sha(f)==h;data=gzip.decompress(f.read_bytes()) if f.suffix=='.gz' else f.read_bytes()
 if p!='verify.py':assert not deny.search(data),p
n=read('physical-archive-inputs.json.gz');pred=read('name-predictions.json.gz');r=read('reader-matrix.json');s=read('symbol-comparison.json.gz')
assert len(n)==len(pred)==4
for tag,v in n.items():
 a=pred[tag];ms=v['members'];files=v['ordered_acquired'];assert len(ms)==76 and len(files)==74
 assert [x['name'] for x in ms[:4]]==['/','//','lib.rmeta','lib.rmeta-link'] and all(x['sha256']==z['sha'] and x['size']==z['size'] and x['name']==z['name'] for x,z in zip(ms[2:],files,strict=True))
 assert v['publication_roles']==['create','publish','remove'] and set(v['observed_current_names'])=={o['name'] for o in ms[4:]}
 assert a['actual_sha256']==v['archive_full_sha256'] and len(a['fields'])==144 and all(q['old_sha256']==q['new_sha256'] for q in a['members'][4:])
 assert a['equal']==(tag!='A1/P-genuine-edit')
 assert v['all_inputs_before_publish'] and v['units']==300 and v['notebook_status']==[True,True] and v['fresh']==285
 assert sorted(x[1] for x in v['native'] if x[1])==['e2e','ruff_python_parser'] and all(x[-1]==0 for x in v['native'])
assert s['offsets']=={'120':998} and all(a[1:]==b[1:] and b[0]-a[0]==120 for a,b in zip(s['cold_symbols'],s['warm_symbols'],strict=True))
c=read('decoded-producers.json');assert c['warm1_and_warm2_all_lines_equal'] and len(c['changed_dependency_credentials'])==7
assert c['section_data']['warm']['.rmeta']['size']-c['section_data']['cold']['.rmeta']['size']==118
assert (D/'A1-rustc-metadata.txt').read_bytes()==(D/'A2-rustc-metadata.txt').read_bytes()!=(D/'cold-rustc-metadata.txt').read_bytes()
for mode in ('P-genuine-edit','H-genuine-restore'):
 assert all(n['A1/'+mode][k]==n['A2/'+mode][k] for k in ('e2e','caller_elf','caller_verdict','inventory_sha256'))
f=read('reader-file-hashes.json.gz');assert len(f['warm'])==len(f['cold'])==271 and f['warm'].keys()==f['cold'].keys()
assert len(r)==18 and Counter(row['status'] for row in r)=={0:10,1:8}
for row in r:
 assert row['status']==int(row['parser']!=row['rest']) and any(n.startswith('libruff_python_parser') for n in row['actually_opened'])
 if row['status']:assert {v['code'] for v in row['diagnostics']}=={'E0460'} and all(x['spans'][0][0]=='input.rs' for x in row['diagnostics'])
 if row['case']=='natural':
  assert any(n.startswith('libruff_db') for n in row['actually_opened'])
  if row['status']:assert any('which `ruff_db` depends on' in v['message'] and v['spans']==[['input.rs',1,1,1,22]] for v in row['diagnostics'])
print('4 independent parent archives, 296 captured member files, 998 symbol/offsets, 118 differing metadata bytes in length, 7 distinct upstream credentials, 18 real reader exits (10 success, 8 E0460), zero performance pairs.')
