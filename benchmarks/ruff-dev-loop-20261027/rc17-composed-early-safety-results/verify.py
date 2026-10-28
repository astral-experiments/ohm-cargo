"""Verify the H5/H8 QA payload, including its frozen runner schema and physical native observations."""
import argparse
import collections
import gzip
import hashlib
import json
import sys
from pathlib import Path
ap=argparse.ArgumentParser()
ap.add_argument('--native-raw', type=Path, help='optional H5/H8 private archive with raw-h5 and raw-h8 folders')
ap.add_argument('--protocol', type=Path, help='optional registered wall protocol directory; only its QA reader is invoked')
opts=ap.parse_args()
p=Path(__file__).resolve().parent
def j(n): return json.loads((p/n).read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def dig(x):return sha(json.dumps(x,sort_keys=True,separators=(',',':')).encode()+b'\n')
def h(f):return sha(f.read_bytes())
q=j('qa.json');assert q['status']=='pass' and set(q)=={'status','build','source','tests','observer','composed'}
r=json.loads(gzip.decompress((p/'common-recipe.json.gz').read_bytes()))
assert {k:len(v) for k,v in r['actual_rustc_argv'].items()}=={'src/lib.rs':874,'src/bin/cargo/main.rs':1040}
assert r['actual_outer_Cargo_argv'][1:]==['+ohm','build','--release','--locked','--offline','-p','cargo','--bin','cargo','--features','ohm-defaults','-j12']
assert r['physical_PGO_profile']=='481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7'
assert r['physical_rustc_sha256']=='b0c412a7a8010a768f00546419a0b1bcfca382d7e70191df3ae72e30ac1ef3e5'
for k,v in q['build'].items():
 b=j(v['evidence'])
 assert h(p/v['evidence'])==v['receipt_sha256'] and b['subject']==v['cargo_sha256']==q[k]
 assert dig(r)==v['recipe_sha256']==b['recipe']['canonical_decoded_sha256']
 assert v['profiles_sha256']==r['physical_PGO_profile']
 assert dig(b['source_recipe'])==v['source_recipe_sha256'] and b['source_recipe']['source_files']==3108
 assert h(p/b['receipt_raw']['file'])==b['receipt_raw']['sha256']
assert q['build']['observer']['source_recipe_sha256']!=q['build']['composed']['source_recipe_sha256']
assert j('build-replay.json')['source_recipe_sha256']==q['build']['observer']['source_recipe_sha256']
aa=j('original-aa-loads.json')
assert aa['control']==q['observer'] and aa['composed']==q['composed'] and aa['control']!=aa['replayed_control']
assert [x['mismatched'] for x in aa['image']]==[34,0,0,0]
assert aa['exceptions']==['e_shoff','GNU build ID descriptor','.symtab','.strtab']
s=j('scheduler-physical.json')
for n,c in [('default_and_fallback',14),('warm_evidence_and_fallback',41)]:
 a=s[n];assert a['exit']==0 and a['cargo']==q['composed'] and len(a['actual_cargo_processes'])==c
 assert h(p/('scheduler-'+n+'.log'))==a['raw']['log_sha256'] and '1 passed; 0 failed' in (p/('scheduler-'+n+'.log')).read_text()
 assert len(a['full_source_sha256'])==64 and len(a['harness'])==64
for name in q['tests']:
 rec=q['tests'][name];z=j(rec['evidence']);assert h(p/rec['evidence'])==rec['receipt_sha256'] and rec['exit']==z['exit']==0 and rec['subject']==z['subject']
 if name in ('missing-proof','used','unused','built-library'):
  assert rec['subject']==q['composed'] and len(z['actual_integration_rustcs'])=={'missing-proof':2,'used':2,'unused':1,'built-library':1}[name]
 elif name in ('observer-replacement','cached-state-migration'):
  assert z['before']['mtime']==z['after']['mtime'] and z['before']['size']==z['after']['size']==2 and z['before']['inode']!=z['after']['inode'] and z['before']['sha256']!=z['after']['sha256']
  assert [z['original_states'][a]['row']['value'] for a in ('change','again','repeat','clean')]==[17,17,17,29]
  assert [z['original_states'][a]['row']['fresh'] for a in ('again','repeat')]==[True,True]
  for k,v in z['measured_arms'].items():
   assert v['subject']==q[k]
   assert all(row['value']==29 and not row['complete'] and not row['fresh'] and row['rebuilt_units']==['hold_direct'] for row in v['rows'].values())
   assert all('sample=29' in v['native_stdout'][a] for a in ('again','repeat'))
 elif name=='ordinary-reader':
  assert 'include_str!' in z['source']
  for k,v in z['actual'].items():
   assert v['subject']==q[k] and [(r['value'],r['fresh'],len(r['actual_rustcs'])) for r in v['rows']]==[(17,False,1),(17,True,0),(29,False,1),(29,True,0)]
 else:raise ValueError(name)
for n in ('260','261'):
 ci=j('pr-'+n+'-ci.json');assert ci['headRefOid']==q['source']['guard' if n=='260' else 'observer']
 assert collections.Counter(v['conclusion'] for v in ci['checks'])=={'SUCCESS':8,'SKIPPED':1}
if opts.native_raw:
 for host in ('h5','h8'):
  d=opts.native_raw/('raw-'+host);ledger=j(host+'-original-sha256.json')
  assert len(ledger)>20 and all(h(d/k)==v for k,v in ledger.items()),host
if opts.protocol:
 sys.path.insert(0,str(opts.protocol.resolve()));import runner
 assert runner.ci_gate(p/'qa.json')==q
if (p/'SHA256SUMS').is_file():
 for line in (p/'SHA256SUMS').read_text().splitlines():
  expected,n=line.split('  ',1);assert h(p/n)==expected,n
print('PASS: both source recipes, three PGO Cargo images, two real scheduler tests, four migration builds, eight ordinary builds and exact PR check heads')
