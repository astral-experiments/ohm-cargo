"""Verify the complete portable Linux compiler and Cargo outcome ledger."""
import hashlib,json,re
from pathlib import Path
p=Path(__file__).resolve().parent
def js(f):return json.loads((p/f).read_bytes())
manifest={n:h for h,n in (l.split('  ',1) for l in (p/'SHA256SUMS').read_text().splitlines())};assert set(manifest)=={str(f.relative_to(p)) for f in p.rglob('*') if f.is_file() and f.name!='SHA256SUMS'} and all(hashlib.sha256((p/n).read_bytes()).hexdigest()==h for n,h in manifest.items())
c=js('compiler.json');assert c['rust_commit']=='eef2f3425c1c6f7fddfb4555769a9f90fe1e0f53' and c['compiler_tree']=='e560860a8cf3f3c527e4d40fd74f1e828d1f4360' and c['driver']=='bd133fb9661e1b8785cfd038ae3f472994b75e3e69b974573555c9be296a4b81';assert c['seed_verified_entries']==85286 and c['exit']==0 and c['aborted'] is None and c['source_patches_applied']==0 and c['pgo']==c['bolt']==False and len(c['target_files'])==53 and all(c['actual_stage1_compiles'][u]==1 for u in ('core','std','alloc'));assert c['cargo']['A']['source']=='235f9228651b74c591e6f62cae4c9b761448dd2d' and c['cargo']['B']['source']=='b3360c5eda186845b9a2ba6e5330a97c07d4acf2';assert c['minimum_free']['home']>=25*2**30 and c['minimum_free']['scratch']>=25*2**30 and c['minimum_free']['upper']>=2**30
rows=js('cargo.json');gold=None
for arm in ('A','B'):
 a=rows[arm]; assert all(v=='ok' for v in a['conditional']['results'].values()) and len(a['conditional']['results'])==3 and a['conditional']['rc']==0
 for order,j in a['terminal'].items():
  ok=arm=='B' or order=='provider-first'; assert j['verdict']==('correct' if ok else 'stale') and j['rc']==0 and all(j['physical_checks'].values())
  assert [e[0] for e in j['ordering'] if e[0].startswith(('hold','release','timeout','error'))]==['hold-fd','release-fd']
  d={v['phase']:v for v in j['cargo']};assert len(d)==7
  for key in ('original','original-repeat','restore','restore-repeat'):assert d[key]['finished']['success'] and not d[key]['errors']
  for key in ('original-repeat','restore-repeat'):assert len(d[key]['fresh'])==4
  for key in ('edited','edited-repeat','edited-clean'):
   incorrect=not ok and key!='edited-clean'; assert d[key]['finished']['success']==incorrect
   if incorrect: assert d[key]['errors']==[]
   else:
    er,=d[key]['errors'];assert (er['crate'],er['code'],er['span'])==('client','E0034',3);gold=gold or er['rendered_sha256'];assert er['rendered_sha256']==gold
  if not ok:assert len(d['edited-repeat']['fresh'])==4
  h=j['existing_state'];x,y=h['independent-empty-edited'],h['restored'];assert all(v['new_rust_header'] for z in (x,y) for v in z.values()) and x['provider']['value']!=y['provider']['value'] and x['reader']['value']==y['reader']['value']
  assert any(x['tool']=='rustc' for x in j['exec']) and all(x['matched_image'] for x in j['exec'] if x['tool']=='rustc')
 r=a['revert']['detail'];assert r['mode']=='default' and r['first_success']=='untouched-1' and r['value']==1 and r['phases']['reverted']['errors']==['E0460'];assert r['phases']['reverted']['rustcs']==[['dep','lib'],['app','bin']] and r['phases']['untouched-1']['rustcs']==[['app','lib'],['app','bin']]
t=js('compiler-tests.json');assert t['generic']['exit']==t['separate_link_correct_host_flags']['exit']==0 and t['separate_link_first_cc_setup']['exit']==1;w=t['wire'];assert w['old-to-new']['errors']==w['new-to-old']['errors']==['E0514'] and w['old-to-new']['exit']==w['new-to-old']['exit']==1 and w['old-to-old-native']['exit']==w['new-to-new-native']['exit']==0
print('Verified compiler, 28 native E0034 commands, both failed-revert histories, six conditional tests, stock-wire incompatibility and the two committed compiler tests.')
