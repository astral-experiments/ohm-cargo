from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parent
def g(name):return json.loads((p/name).read_bytes())
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
checks={}
for line in (p/'SHA256SUMS').read_text().splitlines():
 h,rel=line.split('  ',1);assert rel not in checks and not Path(rel).is_absolute() and '..' not in Path(rel).parts
 f=p/rel;assert not f.is_symlink() and sha(f)==h;checks[rel]=h
assert set(checks)=={str(f.relative_to(p)) for f in p.rglob('*') if f.is_file()}-{'SHA256SUMS'}
j=g('actual.json');bind=g('source.json');image=g('build.json')
assert j['source']==bind['fixed']==image['source'] and j['tree']==bind['tree']==image['tree']=='1eb329d8d137cd35b0b510c100c60676fa29b091'
assert j['parents']==bind['parents']==['613667eadce39c044ec1cf4327a985619de636f7','d387f81545e84fc0937556e55e5e9c4737c4159d']
assert j['source'] in image['version'] and image['cargo']==j['cargo']
assert g('build.json')['fresh_cargo_lib'] is False and not image['fresh_cargo_exe'] and image['exit']==0 and j['free']>24*2**30
assert j['historical-rust']=='e173035a5dd384e17ca6a178e1987a0a746260c3669459cfab3af580880927ba' and j['post-release-rust']=='c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60'
assert [a['name'] for a in j['sidecars']]==['enabled','dangling','disabled']
for a in j['sidecars']:
 row=a['case'];rs=row.get('records',row.get('rows'));assert row['cargo']==j['cargo'] and row['compiler']==j['historical-rust'] and [r['value'] for r in rs]==[17,29,29] and all(r['exit']==0 for r in rs) and all(f[1] for f in rs[-1]['typed'])
 if a['name']=='disabled':assert row['disabled']
 else:
  assert not row['sentinel_replaced'] and not row['cache_symlink']
  if a['name']=='dangling':assert not row['victim_existed_after']
  else:assert row['inode_preserved'] and row['before_sha']==row['after_sha']
assert [(a['case'],a['order']) for a in j['metadata']]==[('historical-unavailable','provider-late'),('historical-reproduce','provider-first'),('historical-ordinary','provider-late')]
for item in j['metadata']:
 rs=item['phases'];assert [a['phase'] for a in rs]==['original','original-repeat','edited','edited-repeat','edited-clean','restore','restore-repeat']
 assert [a['success'] for a in rs]==[True,True,False,False,False,True,True]
 ds=[rs[i]['diag'] for i in (2,3,4)];assert ds[0]==ds[1]==ds[2] and ds[0]['code']=='E0034' and ds[0]['line']==3 and ds[0]['crate']=='client/src/main.rs'
 for a in (rs[1],rs[6]):assert len(a['units'])==4 and all(z[1] for z in a['units'])
 assert bool(item['trace'])==(item['case']!='historical-ordinary')
tests=j['units']['cargo']['tests'];assert len(tests)==58 and len(set(tests))==58 and any('changed_or_pending_metadata_dependency' in t for t in tests) and any('public_api_hash_replaces_a_symlink' in t for t in tests)
assert len(set(j['units']['cargo-util']['tests']))==3
print('Combined #53: both source parents preserved, 9 writer commands, 21 metadata checks, 58 fingerprint tests and 3 filesystem helper tests verified.')
