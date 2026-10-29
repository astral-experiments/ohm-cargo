from pathlib import Path
import gzip,hashlib,json
p=Path(__file__).resolve().parent
for record in (p/'SHA256SUMS').read_text().splitlines():
 h,n=record.split('  ',1);assert hashlib.sha256((p/n).read_bytes()).hexdigest()==h,n
rows=json.loads(gzip.decompress((p/'native.json.gz').read_bytes()));binding=json.loads((p/'binding.json').read_bytes());plan=json.loads((p/'plan.json').read_bytes());assert len(rows)==14 and binding['cargo']==plan['cargo']
for arm in 'RF':
 for phase in ('01-original','02-original-unchanged','03-edit','04-edit-unchanged','05-invalid','06-original-restore','07-original-unchanged'):
  r=rows[phase+'-'+arm];n=r['counts'];assert r['route']['uid_map']==['0','0','4294967295'] and r['route']['affinity']==[24,25,26,27]
  assert all(z['sha']==binding['compiler'] for z in r['rustc']) and all(z['linker_sha256']==plan['wild'] for z in r['native'])
  if phase=='05-invalid':assert r['status']==101 and 'E0308' in r['errors'] and not r['native'];continue
  assert r['status']==0 and n['total']==147 and len(r['typed'])==147 and r['products']['fixtures']['listed']==(557 if r['mode']=='P' else 558) and r['products']['generate_inline_tests']['listed']==1
  assert r['caller']['verdict']==('accepted' if r['mode']=='P' else 'rejected: Star import cannot be parenthesized')
  if 'unchanged' in phase:assert not r['rustc'] and not r['native'] and n['fresh']==147
  if phase=='01-original':assert n['fresh']==0
  if phase=='03-edit':
   assert (n['full'],n['link'],n['wild'],n['fresh'])==((1,2,2,144) if arm=='R' else (3,0,2,144))
   assert sorted((z['unit'],z['link']) for z in r['rustc'] if not z['probe'])==[('fixtures',arm=='R'),('generate_inline_tests',arm=='R'),('ruff_python_parser',False)]
for phase in ('01-original','03-edit','06-original-restore'):
 a,b=[rows[phase+'-'+q] for q in 'RF']
 for n in ('fixtures','generate_inline_tests'):assert a['products'][n]['sha']==b['products'][n]['sha'] and a['products'][n]['list_sha']==b['products'][n]['list_sha']
print('Verified all 14 ordinary Cargo invocations, compiler/linker rosters, matched raw ELFs, test inventories, changed parser caller verdict and E0308.')
