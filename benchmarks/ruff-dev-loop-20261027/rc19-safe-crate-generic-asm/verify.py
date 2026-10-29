"""Verify the saved Cargo/rustc source, process and native observations off-line."""
from pathlib import Path
import hashlib,json,re,tarfile
p=Path(__file__).resolve().parent
def h(b):return hashlib.sha256(b).hexdigest()
proof=json.loads((p/'proof.json').read_bytes());stream={}
with tarfile.open(p/'streams.tar.gz','r:gz') as t:
 for e in t:
  assert e.isfile() and e.name not in stream and '..' not in Path(e.name).parts
  stream[e.name]=t.extractfile(e).read()
assert set(stream)==set(proof['files'])
for n,b in stream.items():
 index=proof['files'][n];assert index['portable_bytes']==len(b) and index['portable_sha256']==h(b) and re.fullmatch(r'[0-9a-f]{64}',index['sha256'])
c=proof['cached_outputs'];assert len(c['files'])==4 and {r['kind'] for r in c['files'].values()}=={'.o','.json','.rlink'}
assert all(not r['names_assembler_input'] and not r['contains_incbin'] for r in c['files'].values())
assert c['manifest_fields']==['executable','input_checksum','objects','proof_checksum','rlink','version']
def j(fn):return json.loads(stream[fn])
def capture(lane):
 result=j(lane+'/results.json')
 assert result['cargo']=='789c2f116732ed642565d0f92c500838f8cd53664fbe60f205a5621c43cbecf1'
 assert result['rustc']=='5694abe50767a22cebeccb767143f7404d5e81c4b1760cff4426466bf410e511'
 for n,r in result['rows'].items():
  base=lane+'/'+n+'/';assert r==j(base+'result.json')
  msg=[json.loads(l) for l in stream[base+'stdout'].splitlines() if l.startswith(b'{')]
  assert msg[-1]=={'reason':'build-finished','success':r['status']==0}
  shown=[x for x in stream[base+'stderr'].decode().splitlines() if 'Running ' in x and '--crate-name ' in x]
  assert r['compiler']==[{'name':x.split('--crate-name ',1)[1].split(' ',1)[0],'link_only':'-Z link-only' in x or '-Zlink-only' in x} for x in shown]
  if r['status']==0:
   assert any(x.get('executable') and x['target']['name']=='app' and x['fresh']==r['target_fresh'] for x in msg)
   assert re.fullmatch(r'[0-9a-f]{64}',r['elf'])
  else:
   assert r['status']==101 and r['missing'] and any('untracked.bin' in x['message']['rendered'] for x in msg if x['reason']=='compiler-message')
  for k,df in enumerate(r['depfiles']):
   b=stream[base+str(k)+'.d'];assert b'untracked.bin' not in b and b'app/src/main.rs' in b and proof['files'][base+str(k)+'.d']['sha256']==df['sha']
 return result['rows']
v=capture('official-generic');w=capture('official-held-switch')
def actual(rows,name,value,job):
 row=rows[name];assert row.get('value')==value and row['status']==(101 if value is None else 0)
 assert [c['link_only'] for c in row['compiler'] if c['name']=='app']==job
for arm in ['default','full']:
 use_cache=arm=='default';edited='9:17' if use_cache else '9:29'
 for phase,value,job in [('initial','5:17',[False]),('edited',edited,[use_cache]),('repeat',edited,[]),('empty-edited','9:29',[False]),('missing','7:17' if use_cache else None,[use_cache]),('empty-missing',None,[False]),('restore','5:17',[use_cache])]:
  actual(v,f'{arm}.{phase}',value,job)
  assert v[f'{arm}.{phase}']['sources']['app/src/main.rs']==h(stream['fixture/app/src/main.rs'])
for phase,value,job in [('initial','5:17',[False]),('poison','9:17',[True]),('confirm','9:17',[]),('disable','9:17',[]),('repeat','9:17',[]),('empty','9:29',[False]),('forced','9:29',[False]),('forced-repeat','9:29',[])]:
 actual(w,phase,value,job)
assert len({w[k]['elf'] for k in ['poison','confirm','disable','repeat']})==1
assert all(len(w[k]['depfiles'])==1 for k in w)
assert stream['fixture/app/src/main.rs'].startswith(b'#![forbid(unsafe_code)]') and b'asm!' not in stream['fixture/app/src/main.rs']
d=j('direct/result.json');assert d['upstream_compiled_without_payload'] and d['compiler']==j('official-generic/results.json')['rustc']
assert [(r['return'],r['program']) for r in d['rows']]==[(0,'17'),(0,'29'),(1,None),(0,'17')]
for r in d['rows']:
 dep='direct/'+r['state']+'/consumer.d';b=stream[dep]
 assert b'libengine.rlib' in b and b'# checksum:' in b and b'untracked.bin' not in b and proof['files'][dep]['sha256']==r['depinfo_sha256']
assert b'untracked.bin' in stream['direct/missing/stderr']
print(f"{len(v)+len(w)} Cargo commands, 5 direct rustc commands, {len(stream)} bound source and result streams.")
