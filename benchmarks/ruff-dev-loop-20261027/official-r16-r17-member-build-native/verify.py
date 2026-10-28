"""Replay the native disposition and product commitments for the two actual published assets."""
from collections import Counter
from pathlib import Path
import hashlib,json,re,sys,tarfile
root=Path(__file__).resolve().parent;file=Path(sys.argv[1]) if len(sys.argv)>1 else root/'observations.tar.gz';h=lambda b:hashlib.sha256(b).hexdigest()
expected={'16':('957ca8144205008ddaee75ef35f9775b2e428271c6b044e38bbdd8196c6bbf3e','42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568','b0c412a7a8010a768f00546419a0b1bcfca382d7e70191df3ae72e30ac1ef3e5','c442c2a36e1f37c92f138a8fb367fc09982931b5f1055e9742fb402566ad46a4'),'17':('163267d26889b1bd2c467d7db97efee42cd2ac9dc9af2abc3a56ade8da9a9572','4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3','7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c','618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7')}
stub='721696b22e172c4f9dbe15ec5e04a04a9939188eca12d8110ab62f9de81d96a1';output={}
with tarfile.open(file) as f:
 def raw(n):return f.extractfile(n).read()
 def r(n):return json.loads(raw(n))
 assert len(f.getnames())==len(set(f.getnames())) and len(r('archives.json'))==2 and r('scored_commands.json')==0 and r('global_alias_unchanged.json')
 assert h(raw('repro/source-files.json'))=='644dc001d858e549d498c5e5ef0cae8961533807ff7ba53a71d4d6dd52f98788'
 assert {n:h(raw('repro/'+n)) for n in r('repro/source-files.json')}==r('repro/source-files.json')
 assert r('source.json')['commit']=='93526150df078af7dd8fc4226cdcc469539d2001'
 for ver in ('16','17'):
  info=r(ver+'/subject.json');end=r(ver+'/final-products.json');p=ver+'/';archive,cargo,rust,driver=expected[ver]
  assert (info['archive'],info['tool']['cargo'],info['tool']['rustc'],info['tool']['driver'])==(archive,cargo,rust,driver) and info['archive']==r('archives.json')[ver]
  assert info['tool']['wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5' and all('ohm-1.99.0-'+ver in v for v in info['versions'].values())
  assert info['sdk']=='sdk' and info['target']=='ruff target' and info['member']=='crates/ty_wasm'
  assert h(raw(p+'stub-typed-compilation.txt'))==stub and len(raw(p+'stub-typed-compilation.txt'))==18553
  rows=[];initial=None;zip0=None;diagnostic=None
  for n in range(4):
   k=p+str(n)+'/';a=r(k+'product.json');b=r(k+'processes.json');tr=r(k+'trace-commitments.json');x=r(k+'cargo-rows.json');orig=r(k+'raw.json')
   assert len(x)==a['units']==304 and all(not row[4] for row in x) and a['fresh']==sum(row[3] for row in x)
   roster=sorted(json.dumps(row[:3]+row[4:]) for row in x);assert not initial or roster==initial;initial=roster
   assert sorted([row[0],row[1]] for row in x if not row[3])==a['dirty'] and len(b['cargo'])==1
   jobs=[row[1:3] for row in b['jobs']];assert jobs==a['jobs'] and all('exec.'+str(row[0]) in tr for row in [*b['jobs'],*b['links']])
   counts={'rustc':dict(Counter(v[1] for v in jobs)),'wild':sum(row[1] for row in b['links']),'system':sum(not row[1] for row in b['links']),'queries':len(b['queries'])};assert counts==a['counts']==b['counts']
   assert a['native']==orig['native-processes.json'] and a['traces']==orig['trace-files.json'] and a['cargo_raw']==orig['stdout'] and a['stderr']==orig['stderr']
   assert a['argv']==['cargo','+ohm','build','--locked','--offline','-j4','--message-format=json']
   witness=a['caller'];assert witness['sha256']==orig['reader.stdout']==stub and witness['bytes']==18553 and witness['search_dirs']>0 and set(witness['externs'])=={'ty_vendored','ty_wasm'}
   assert orig['reader.stderr']==h(b'') and len(witness['binary'])==64
   z=a['compressed_zip'];assert len(z['offsets'])==2 and {Path(path).suffix for path in z['offsets']}=={'.rlib','.rmeta'} and all(v>=0 and path in a['products'] for path,v in z['offsets'].items())
   assert z['sha256']==end['zipped_typeshed.zip']['sha256'] and z['bytes']==end['zipped_typeshed.zip']['bytes'];assert not zip0 or z==zip0;zip0=z
   assert diagnostic is None or a['diagnostics']==diagnostic;diagnostic=a['diagnostics']
   if n==3:assert end['libty_wasm.so']['sha256']==a['products']['debug/libty_wasm.so'] and end['functools.pyi']=={'bytes':18553,'sha256':stub}
   rows.append({'phase':n,'fresh':a['fresh'],'units':a['units'],**counts,'typed_reader_bytes':witness['bytes'],'search_dirs':witness['search_dirs'],'zip_bytes':z['bytes'],'cdylib':a['products']['debug/libty_wasm.so']})
  output[ver]=rows
print(json.dumps(output,sort_keys=True,indent=2))
