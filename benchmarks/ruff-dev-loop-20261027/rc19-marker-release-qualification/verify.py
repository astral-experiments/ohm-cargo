"""Verify included release pins, terminal PR checks and the manifest's SHA-256."""
import hashlib
import json
from pathlib import Path

here=Path(__file__).resolve().parent
load=lambda name:json.loads((here/name).read_bytes())
versions=[load(x) for x in ('18.json','19.json')]
a,b=versions
binding=load('bindings.json')
checks=load('checks.json')
assert binding['latest_tag']=='ohm-1.99.0-18' and binding['changed_rust_paths']==['src/tools/cargo']
assert binding['changed_project_paths']==['toolchains/1.99.0/19.json']
assert b['release']['ohm_revision']==19 and a['release']['ohm_revision']==18
assert a['bundled_tools']==b['bundled_tools']=={'wild':{'version':'0.11.0','sha256':'25012a78de164686f552b7703b5d0223adab4829c79cd1fb351108221d61c7d8'}}
for k in ('cargo','rust'):assert binding[k]==b['sources'][k]['revision']==checks['ohm-'+k]['head']
assert binding['packaging']==checks['ohm']['head']
for k in ('clippy','rustfmt'):assert a['sources'][k]==b['sources'][k]
assert hashlib.sha256((here/'19.json').read_bytes()).hexdigest()=='16057cc546490c630e40a6d1250129994caebb6f4d59e349265c72ae50d09e25'
for name,report in checks.items():
  succeeded=[]
  for check in report['checks']:
    assert check['status']=='completed' and check['head_sha']==report['head']
    if check['conclusion']=='skipped':assert (name,check['name'])==('ohm-cargo','Clippy APFS replay')
    else:assert check['conclusion']=='success';succeeded.append(check['name'])
  assert len(set(succeeded))=={'ohm':3,'ohm-rust':3,'ohm-cargo':8}[name]
print('Verified exact release pins and all 14 completed required checks across the three pull requests.')
