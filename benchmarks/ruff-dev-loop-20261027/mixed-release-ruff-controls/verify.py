"""Recheck every released scoped gate from redacted execution receipts without a compiler or network."""
from pathlib import Path
from collections import Counter
import hashlib,json
b=Path(__file__).resolve().parent
def load(rel):return json.loads((b/rel).read_bytes())
def s(arm,name):return load('stages/'+arm+'/'+name+'.json')
for line in (b/'SHA256SUMS').read_text().splitlines():
 given,p=line.split('  ',1);assert hashlib.file_digest((b/p).open('rb'),'sha256').hexdigest()==given,p
pin=load('inputs.json');assert pin['unscored'] and pin['cargo_sha256']=='0f237cc3b506aa90c1224e6ed80f646566b424b78c8d74f288f6523d17fc8aa1'
assert hashlib.file_digest((b/'historical-parser.patch').open('rb'),'sha256').hexdigest()==pin['patch_sha256']
rows=[load(str(f.relative_to(b))) for f in (b/'stages').rglob('*.json')]
assert len(rows)==24 and {r['units'] for r in rows}=={362} and len({r['unit_roster_sha256'] for r in rows})==1
for r in rows:
 assert r['compiler_driver']==pin['rustc_sha256']
 for x in r['crate_processes']:
  if x['phase']=='HIR-and-native-link':
   assert x['checked_recipe_name'] in ('ruff_wasm.rlink','ty_wasm.rlink') and x['prior_sha256_mtime_ns'] is not None and x['prior_sha256_mtime_ns']==x['next_sha256_mtime_ns']
  if x['phase']=='checked-full-fallback':assert x['prior_sha256_mtime_ns']!=x['next_sha256_mtime_ns']
first=s('pair','edit1'); assert sorted((x['crate'],x['phase']) for x in first['crate_processes'])==sorted([('ruff_python_parser','full'),('ruff_wasm','checked-full-fallback'),('ty_wasm','checked-full-fallback')])
for suffix in ['restore','edit']:
 a=s('pair','tested-'+suffix);z=s('forced','tested-full-'+suffix)
 assert a['cargo']==z['cargo']==pin['cargo_sha256'] and a['fresh_false']==z['fresh_false'] and len(a['fresh_false'])==20
 assert sorted((x['crate'],x['phase']) for x in a['crate_processes'])==sorted([('ruff_python_parser','full'),('ruff_wasm','HIR-and-native-link'),('ty_wasm','HIR-and-native-link')]);assert sorted((x['crate'],x['phase']) for x in z['crate_processes'])==sorted((x,'full') for x in ('ruff_python_parser','ruff_wasm','ty_wasm'))
 for arm,r,name in [('pair',a,'tested-'+suffix),('forced',z,'tested-full-'+suffix)]:
  idle=s(arm,name+'-fresh');assert not idle['crate_processes'] and not idle['fresh_false'] and not idle['native_processes']
  assert Counter(i['executable'] for i in r['native_processes'])=={'cc':2,'collect2':2,'ld.bfd':2}
 for n in ('ruff_python_parser','ruff_wasm','ty_wasm'):
  x=a['artifacts'][n][0][1];y=z['artifacts'][n][0][1];assert all(x[k]==y[k] for k in x if k!='.rlib')
for n,expected,name in [('ruff_wasm',66,'0.17.0'),('ty_wasm',78,'93526150d')]:
 ordinary=load('final-ordinary-bridges.json')[n];assert len(ordinary['combinations'])==4 and {x['stdout'] for x in ordinary['combinations'].values()}=={name} and len({x['elf_sha256'] for x in ordinary['combinations'].values()})==1
 assert ordinary['native']['pair']==ordinary['native']['forced'] and ordinary['native']['pair']['zero_width_alloc']==[1,2,4,8,16,32]
 arc=load('final-archives.json')[n];a,z=arc['checked'],arc['full'];assert len(a['cgus'])==len(z['cgus'])==expected and [v[1] for v in a['cgus']]==[v[1] for v in z['cgus']]
 assert all(x[0]!=y[0] for x,y in zip(a['cgus'],z['cgus'])) and a['symbol_to_member_ordinal']==z['symbol_to_member_ordinal'] and a['ordinary']==z['ordinary']
 assert a['remaining_after_exhaustive_filename_decode']==z['remaining_after_exhaustive_filename_decode']=='00727573742d656e642d66696c65'
 zz=load('earlier-tested-image-identical-full/comparison.json')[n];assert zz['different_names_between_two_new_full_compiles']==expected
warm=load('warm-copy.json');assert len(warm['files'])==warm['original_number_of_outputs']==671 and all(x[2]==x[3] and x[4] for x in warm['files'])
unit=load('tests/cargo-unit.json');assert unit['sha']==pin['cargo_head'] and unit['returncode']==0 and len(unit['tests'])==9 and unit['peak_private_bytes']<2*2**30
inher=load('tests/cargo-inherited.json');assert inher['bounded_cargo_sha']==pin['cargo_head'] and len(inher['tests'])==3 and all(q['returncode']==0 and '1 passed; 0 failed' in q['stdout'] for q in inher['tests'])
print('Verified both directions, eight ordinary native importers, actual C exports, 12 unit tests and two independent ordinary full links on identical input.')
