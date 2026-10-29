from collections import Counter
import gzip,hashlib,json,re
from pathlib import Path
D=Path(__file__).resolve().parent
def read(p):return json.loads((gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes()))
def file(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest={n:h for h,n in (l.split('  ',1) for l in (D/'SHA256SUMS').read_text().splitlines())}
assert set(manifest)=={f.name for f in D.iterdir() if f.is_file() and f.name!='SHA256SUMS'}
deny=re.compile(rb'openai[.](org|com|internal)|artifactory[.]|authorization: bearer|github_pat_|ghp_[A-Za-z0-9]{16}|/home/dev-user|/mnt/devbox|charlie-ohm-',re.I)
for n,h in manifest.items():
 p=D/n;assert file(p)==h
 if n!='verify.py':assert not deny.search(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
s=read(D/'terminals.json');w=read(D/'withheld.json');u=read(D/'units.json.gz');raw=read(D/'raw-source-bindings.json')
assert w['outcome']=='withheld' and w['primary_pairs']==w['ordinary_pairs']==0 and len(raw)==len(u)==16
assert 'minimum' in (D/'original-traceback.txt').read_text()
assert (D/'original-literal-check.status').read_text().strip()=='1' and read(D/'original-literal-check.stdout')['equal'] is False
st=read(D/'capacity-stop.json');assert st['floor']==45*2**30 and min(st['minimum'])<st['floor'] and st['status']==-2 and st['actually_started']==17 and st['qualified']==16 and st['qty_partial_typed']==299 and st['missing_build_finished']
for arm,z in s.items():
 assert len(z)==(9 if arm=='parent' else 7)
 for key,r in z.items():
  k=arm+'/'+key;assert r['raw_qualified']==raw[k]['qualified.json'] and r['units']==len(u[k]) and sum(x['fresh'] for x in u[k])==r['fresh']
  if r['exit']==0:
   assert r['units']==300 and r['test_names']==200 and r['inventory']['status']==r['caller_record']['status']==0
   assert len(r['tests'])==2 and all(t['status']==0 for t in r['tests'].values())
   if key.endswith('repeat'):assert r['fresh']==300 and not r['full'] and not r['cached'] and not r['n_e2e_links']
  else:assert r['exit']==101 and r['errors'] and {x['code'] for x in r['errors']}=={'E0308'} and not r['n_e2e_links']
 e=z['03-historical'];c=z.get('08-independent-empty-edited',e);h,rr=z['01-original-cold'],z['06-restore']
 assert e['sha256']==c['sha256']!=h['sha256']==rr['sha256'] and e['caller_elf']==c['caller_elf']!=h['caller_elf']==rr['caller_elf']
 assert e['caller']=='accepted' and c['caller']=='accepted' and 'rejected' in h['caller'] and h['caller']==rr['caller']
 assert e['n_e2e_links']==1 and sorted(e['full'])==['e2e','ruff_python_parser'] and not e['cached'] and e['fresh']==285
 if arm=='parent':assert z['05-invalid']['errors']==z['09-independent-empty-invalid']['errors']
for label,p in s['parent'].items():
 if label not in s['child']:continue
 c=s['child'][label];assert p['exit']==c['exit']
 if p['exit']==0:assert all(p[k]==c[k] for k in ('sha256','caller_elf','caller','test_names','inventory'))
 else:assert p['errors']==c['errors']
assert s['parent']['03-historical']['parser_rlib']!=s['parent']['08-independent-empty-edited']['parser_rlib']
assert not all(w['cross_raw_parser_equal'].values())
print('16 terminal Cargo commands, 17th interrupted at 299 artifacts by the 45-GiB guard, 18th unattempted. Complete e2e/caller matches on comparable arms, original parser archive equality rejected. Zero primary and zero wall pairs.')
