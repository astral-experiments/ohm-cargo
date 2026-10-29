#!/usr/bin/env python3
from pathlib import Path
import collections,gzip,hashlib,json
s=Path(__file__).resolve().parent
def get(n):return json.loads((s/n).read_bytes())
for line in (s/'SHA256SUMS').read_text().splitlines():
 d,n=line.split('  ',1);assert hashlib.sha256((s/n).read_bytes()).hexdigest()==d,n
r=json.load(gzip.open(s/'native.json.gz'));assert len(r)==28,len(r)
def count(j):
 return tuple(j['physical'].get(k,0) for k in ('full','link-only','linker'))
for j in r.values():assert j['physical']==dict(collections.Counter(k['tag'] for k in j['processes']))
for role in ('released','corrected'):
 def at(store,phase):return r[f'{role}/{store}/{phase}']
 o=at('warm','01-original-repeat');ed=at('warm','02-historical');rep=at('warm','03-historical-repeat');cl=at('clean-good','cold');bad=at('warm','04-invalid');badc=at('clean-bad','cold');back=at('warm','05-restore')
 assert count(ed)==(1,1,1) and count(rep)==(0,0,0) and ed['counts']=={'total':147,'fresh':144}
 assert [(x['tag'],x['crate']) for x in ed['processes'] if x['tag']!='linker']==[('full','ruff_python_parser'),('link-only','fixtures')]
 assert ed['selected']['fixtures']['sha256']!=o['selected']['fixtures']['sha256']
 assert ed['selected']['generate_inline_tests']['sha256']==o['selected']['generate_inline_tests']['sha256']
 for j in [o,ed,rep,cl,back]:
  assert all(v['test_exit']==0 for v in j['selected'].values())
  assert 'ruff_python_parser' in j['selected']['generate_inline_tests']['rustc_unused_externs']
  assert 'insta' in j['selected']['generate_inline_tests']['rustc_unused_externs']
  assert 'ruff_python_parser' not in j['selected']['fixtures']['rustc_unused_externs']
 assert ed['caller']['verdict']==cl['caller']['verdict']=='accepted'
 assert o['caller']['verdict']==back['caller']['verdict']=='rejected: Star import cannot be parenthesized'
 assert all(x['exit']==101 and 'E0308' in x['errors'] for x in (bad,badc))
 assert count(at('warm','06-restored-repeat'))==(0,0,0)
def es(ph):return r['corrected/new-ty-e2e/'+ph]
o=es('01-cold');e=es('03-real-edit');v=es('06-restore')
assert count(o)==(304,0,48) and len([x for x in o['processes'] if x['crate']=='e2e'])==1
assert count(e)==(1,1,1) and count(es('02-unchanged'))==count(es('04-edited-repeat'))==(0,0,0)
assert len(e['typed'])==300 and sum(x['fresh'] for x in e['typed'])==285
assert o['selected']['e2e']['sha256']==v['selected']['e2e']['sha256']!=e['selected']['e2e']['sha256']
assert 'E0308' in es('05-invalid')['errors'] and count(es('05-invalid'))==(1,0,0)
for j in [o,e,v,es('02-unchanged'),es('04-edited-repeat')]:
 a=j['selected']['e2e'];assert a['listed']==200 and len(a['tests'])==2 and all(x['exit']==0 and x['one_passed'] for x in a['tests'])
for ph in ['02-first-repeat','03-settled-repeat','05-edit-repeat']:
 b=r['corrected/unified-ron/'+ph]
 assert count(b)==(1,2,2) and len(b['typed'])==150 and sum(x['fresh'] for x in b['typed'])==146
 assert [x['crate'] for x in b['processes'] if x['tag']=='full']==['ron']
 z=b['terminal_native_operands'];assert len(z)==2 and all(i['psm_directories']==1 and i['find_gcc_s'] for i in z)
 for n in z:
  used=n['target'].startswith('fixtures-');assert bool(n['ron_rlibs'])==bool(n['insta_rlibs'])==used
p=get('e2e-sections.json');assert p['original']['sections']['.text']['bytes']==27094629 and p['historical']['sections']['.text']['bytes']==27094405
assert p['original']['sections']['.text']['hash']!=p['historical']['sections']['.text']['hash']
c=get('e2e-observer-correction.json');assert c['all_suffix_bytes_match'] and c['size']==c['suffix_bytes']+4096 and c['cold_raw_sha256']==o['selected']['e2e']['sha256']
older=get('prior-official-release.json');assert older['public-release-workspace']['phases']['repeat']['native']['wild']==50 and len(older['public-release-workspace']['participating_native_targets'])==50
print('Verified 28 traced phases, both historical verdicts and invalid clean controls, 200 e2e tests listed, feature-unified real linker inputs and the initial observer exception.')
