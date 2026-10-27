from pathlib import Path
import json,subprocess as sp
h=Path('/home/dev-user/.cache/ohm-mixed-release-pilot-20261027')
q={};exec((h/'release-ruff.py').read_text().split("if sys.argv[1]=='init':")[0],q)
d=q['d'];one=q['one'];bits=h/'bounded-cargo-tested';assert q['sha'](bits)=='0f237cc3b506aa90c1224e6ed80f646566b424b78c8d74f288f6523d17fc8aa1';q['cargo_image']=bits
assert (h/'fullarchive-v3.rc').read_text().strip()=='0' and (h/'ordinary.rc').read_text().strip()=='0'
def evict(name,last):
 for line in (h/'evidence'/name/last/'stdout').read_bytes().splitlines():
  a=json.loads(line)
  if a.get('reason')=='compiler-artifact' and a['target']['name'] in ('ruff_wasm','ty_wasm'):
   p,=map(Path,[x for x in a['filenames'] if x.endswith('.rmeta')]);f=h/name/'target'/p.relative_to(d/'target').with_suffix('.rlink-cache.json')
   if f.is_file():f.unlink()
src='forced-same-input-1';seals=[]
for mode,suffix in [('original','restore'),('edited','edit')]:
 a=one('pair',mode,'tested-'+suffix);fresh=one('pair',mode,'tested-'+suffix+'-fresh');assert not fresh['procs']
 last=src;src='tested-full-'+suffix
 if not (h/'evidence/forced'/src/'result.json').is_file():evict('forced',last)
 b=one('forced',mode,src);fullfresh=one('forced',mode,src+'-fresh');assert not fullfresh['procs']
 expected_dirty=sorted(json.loads((h/'evidence/pair'/('restore' if suffix=='restore' else 'edit2')/'result.json').read_bytes())['dirty'])
 assert len(expected_dirty)==20
 for r in (a,b):
  assert r['units']==362 and r['cargo']==q['sha'](bits) and sorted(r['dirty'])==expected_dirty and all(len(r['native'][k])==2 for k in ['cc','collect2','ld.bfd'])
 assert sorted((n,t) for _,n,t in a['procs'])==sorted([('ruff_python_parser','full'),('ruff_wasm','HIR-and-native-link'),('ty_wasm','HIR-and-native-link')])
 assert sorted((n,t) for _,n,t in b['procs'])==sorted([(n,'full') for n in ('ruff_python_parser','ruff_wasm','ty_wasm')])
 for name in ('ruff_python_parser','ruff_wasm','ty_wasm'):
  x=a['artifacts'][name][0][1]; y=b['artifacts'][name][0][1];z={k:x[k]==y[k] for k in x.keys() if k!='.rlib'};assert all(z.values()),(mode,name,z)
  seals.append({'source':mode,'crate':name,'equal':z})
q['write'](h/'tested-ruff-comparison.json',seals)
