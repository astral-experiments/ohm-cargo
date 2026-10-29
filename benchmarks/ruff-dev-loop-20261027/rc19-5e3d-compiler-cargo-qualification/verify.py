"""Verify the complete portable Linux compiler and Cargo outcome ledger."""
import hashlib,json,re
from pathlib import Path
p=Path(__file__).resolve().parent
def js(f):return json.loads((p/f).read_bytes())
manifest={n:h for h,n in (l.split('  ',1) for l in (p/'SHA256SUMS').read_text().splitlines())};assert set(manifest)=={str(f.relative_to(p)) for f in p.rglob('*') if f.is_file() and f.name!='SHA256SUMS'} and all(hashlib.sha256((p/n).read_bytes()).hexdigest()==h for n,h in manifest.items())
c=js('compiler.json')
source=js('source.json')
parent='eef2f3425c1c6f7fddfb4555769a9f90fe1e0f53'
final='5e3de497d41f4d4fa98fce3082ea43076779de5d'
old_cargo='235f9228651b74c591e6f62cae4c9b761448dd2d'
new_cargo='34dad66fd2ac823bfb02c2c4a4bab02fb5ac4d31'
assert c['rust_commit']==source['source']==final and source['parent']==parent
assert source['tree']==c['source_tree']=='719e6a17c1ad764582809c8e7510e5ee6189e611'
assert source['parent_tree']=='535b2a406df8bf961fff7e2684682946fde1eb58'
assert source['changes'].split()==[':160000','160000',old_cargo,new_cargo,'M','src/tools/cargo']
assert len(source['scope'])==9 and all(a==b for a,b in source['scope'].values())
earlier=c['earlier_compiler']
assert earlier['source']==parent and earlier['driver']=='bd133fb9661e1b8785cfd038ae3f472994b75e3e69b974573555c9be296a4b81'
assert c['compiler_tree']==earlier['compiler_tree']==source['scope']['compiler'][0]=='e560860a8cf3f3c527e4d40fd74f1e828d1f4360'
assert source['scope']['library'][0]=='4f7a8f755164dc68fff80790db8a844ae030fd03'
assert earlier['llvm']==c['llvm'] and earlier['driver']!=c['driver'] and earlier['target_files']!=c['target_files']
assert earlier['frontend']==c['frontend']=='fa2ed3ec44adb4455d5323c4ee582becd5307cb4aae6b5cfc3cdc289b3140512'
assert c['driver']=='887bf8fc3c90090c1dd5be4af51e8c4a0f319a93db99b454dae35e96c7afde8b'
assert earlier['target_files'].keys()==c['target_files'].keys() and not set(earlier['target_files'].values()) & set(c['target_files'].values())
assert c['uid']==1000 and c['cpus']==[24,25,26,27] and c['max_build_volume_bytes']==12*2**30
assert c['source_patches_applied']==0 and c['optimized_stage']==1 and not c['pgo'] and not c['bolt']
assert c['exit']==0 and c['aborted'] is None and c['seed_verified_entries']==85286
assert c['minimum_free']['home']>=25*2**30 and c['minimum_free']['scratch']>=25*2**30 and c['minimum_free']['upper']>=2**30
assert len(c['target_files'])==53 and all(c['actual_stage1_compiles'][unit]==1 for unit in ('core','alloc','std'))
assert final in c['version'] and parent in earlier['version'] and c['commit_stamp']==[final,final[:9],'2026-10-29']
assert c['cargo']['A']['source']==old_cargo and c['cargo']['B']['source']=='b3360c5eda186845b9a2ba6e5330a97c07d4acf2'
for arm in c['cargo'].values():
 assert arm['frontend']==c['frontend'] and arm['driver']==c['driver'] and arm['stdlib_entries']==53
 assert final in arm['version']['rustc'] and arm['wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
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
t=js('compiler-tests.json')
for name in ('generic','separate_link'):
 x=t[name]
 assert x['exit']==0 and x['upstream_untouched'] and x['compiler_commit']==final and x['compiler_under_test']==c['frontend']
assert len(t['generic']['actual_final_rustc_execs'])==18 and len(t['separate_link']['actual_final_rustc_execs'])==8
assert sum(t['generic']['successful_execs'].get(x,0) for x in ('ld','ld.bfd','rust-lld'))>=12
for name,older in [('gitlink_wire',parent),('release_wire','a4fa11bcd38280639cb94daacc125472657db6c3')]:
 w=t[name]
 for side,version in [('old',older),('new',final)]:
  producer=w[side+'-producer']
  assert producer['exit']==0 and version[:9] in producer['metadata_version_string'] and '(Ohm metadata 1)' in producer['metadata_version_string']
  assert w[f'{side}-to-{side}']['exit']==0 and w[f'{side}-to-{side}-native']['stdout_sha256']==hashlib.sha256(b'29\n').hexdigest()
 for label in ('old-to-new','new-to-old'):
  assert w[label]['exit']==1 and w[label]['errors']==['E0514']
 assert w['old-producer']['metadata_member_sha256']!=w['new-producer']['metadata_member_sha256']
print('Verified the final compiler and standard library, both older Cargo controls, both checked-in compiler tests and each pair of native metadata readers.')
