"""Recompute the native gate from the two real traces and per-range/per-member SHA records."""
import gzip,hashlib,json
from pathlib import Path
from collections import Counter
root=Path(__file__).resolve().parent
d=json.loads(gzip.decompress((root/'evidence.json.gz').read_bytes()))
detail=json.loads((root/'member-detail.json').read_bytes());source=json.loads((root/'package-subject.json').read_bytes())
assert d['first_exit']==1 and d['first_zero_clock']and d['cold_status']==1 and d['custody_recheck_status']==0
assert d['subject']['candidate_cargo']=='0299c77b2ca9707e82bc418976399fdbc75611d8'
assert d['subject']['control_cargo']=='235f9228651b74c591e6f62cae4c9b761448dd2d'
assert d['subject']['candidate_rust']=='ae76b292cb224008e8188a07143797f7a4ce0ec5'
assert d['subject']['sdk_driver']=='f5d26f74e970e2891a8cbf8a044244d1cd9c0ca50d3af3894842cfb9858f781c'
assert d['subject']['wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
assert d['generation_micro']['delta']=={'Generation':['7','8']}and d['generation_micro']['tree_before']==d['generation_micro']['tree_after']
assert d['donor_final']['complete_tree']==d['seed_trees']
for k in d['donor_final']['before']:
 a,b=[d['donor_final'][t][k]for t in ('before','after')]
 assert a['readonly']==b['readonly']=='ro=true'and int(b['Generation'])>=int(a['Generation'])
 assert {n:v for n,v in a.items()if n!='Generation'}=={n:v for n,v in b.items()if n!='Generation'}
assert d['seed_trees']['seed']['regular_unique_bytes']==1368528501 and d['seed_trees']['pristine']['regular_inodes']==968
s=d['base'];expected='2 SIM222\n3 SIM222\n4 SIM222\n'
for k,want in [('historical','1 SIM222\n'),('parent',expected)]:
 c=d['cold'][k];assert (c['states']['empty']['units'],c['states']['empty']['fresh'],c['states']['settled']['fresh'])==(248,0,248)
 assert c['caller']['exit']==0 and c['caller']['stdout']==want and c['states']['empty']['sha256']==c['states']['settled']['sha256']==c['caller']['linter']
assert s==d['cold']['historical']['caller']['linter']=='3dc4253060abc0704b18356acd2bb134383b88538a3b0642a1ad97307ffaeaf0'
dirty=sorted('ruff_db ruff_linter ruff_python_ast ruff_python_codegen ruff_python_importer ruff_python_index ruff_python_literal ruff_python_parser ruff_python_semantic ruff_ranged_value'.split())
arms=d['arms'];a,b=arms['A'],arms['B']
assert a['root']=='23a695c9e8c82a6b2c60e3d91d9e7a43a2e2197225b0f67e132e4e8b2f31178f'
assert b['root']=='f65dca9af2207a0d3693486a5f55480e77be4816e9533814d805dca851e20c61'
assert a['prior']==b['prior']==s and len({a['root'],b['root'],d['cold']['parent']['caller']['linter']})==3
for k,v in arms.items():
 assert v['warm']=={'counts':{'cargo':1},'all_fresh':248}and v['artifact_count']==248 and v['dirty']==dirty
 assert v['program']['stdout']==expected and v['program']['linter']==v['root']and v['program']['exit']==0
 assert v['program']['executable']==a['program']['executable']!=d['cold']['parent']['caller']['executable']
 for phase,want in [('edit',238),('repeat',248)]:
  r=v['phases'][phase];p=r['physical']
  assert r['fresh']==want and p['root_exit']==0 and all(m['rc']==0 for m in p['rows'])
  roles={'cargo':1}
  if phase=='edit':roles['rustc-full']=10
  if phase=='edit'and k=='B':roles['rustc-query']=1
  assert p['role_counts']==dict(Counter(m['role']for m in p['rows']))==roles
  assert r['hint_count']==int(k=='B'and phase=='edit')
  ar={m['target']:m['arg_sha']for m in p['rows']if m['role']=='rustc-full'}
  normalized=dict(r['rustc_normalized'])
  assert set(ar)==set(normalized)==(set(dirty)if phase=='edit'else set())
  assert {n for n in ar if ar[n]!=normalized[n]}==({'ruff_linter'}if phase=='edit'and k=='B'else set())
  assert r['rustc_normalized']==a['phases'][phase]['rustc_normalized']and r['typed']==a['phases'][phase]['typed']
for akey,ts in detail['source_mtimes'].items():
 assert {n:v[0]for n,v in ts.items()}==source['parent']
assert detail['source_mtimes']['a']!=detail['source_mtimes']['b']
files=d['pair_files'];changed=[k for k,v in files.items()if v['A']!=v['B']]
assert len(files)==d['first_pair']['declared_path_count']==452 and len(changed)==10 and all(v.endswith('.rlib')for v in changed)
assert set(Path(k).name.removeprefix('lib').removesuffix('.rlib').split('-')[0]for k in changed)==set(dirty)
la,lb=a['archive_members'],b['archive_members'];assert len(la)==len(lb)==260
assert all((i['offset'],i['size'],i['header_sha'])==(j['offset'],j['size'],j['header_sha'])for i,j in zip(la,lb))
assert [i['name']for i,j in zip(la,lb)if i['sha']!=j['sha']]==detail['different_payload_names']==['//','lib.rmeta-link']
assert all(i['name'].endswith('.0ub3itk.rcgu.o') and j['name']==i['name'].replace('.0ub3itk.rcgu.o','.07y2oqw.rcgu.o') and i['sha']==j['sha'] for i,j in zip(la[4:],lb[4:]))
assert detail['different_name_count']==detail['same_cgu_bytes']==len(la)-4 and detail['same_offsets_sizes']==len(la)
r=detail['rmeta_link'];assert set(r['changed_sections'])=={'.rmeta-link'}and r['size']==18760
assert len(r['ranges'])==256 and all(b-a==6 for a,b in r['ranges'])and sum(b-a for a,b in r['ranges'])==r['different_bytes']==1536
assert set(map(tuple,r['changed_hex']))=={('75623369746b','3779326f7177')}
print('Verified 248 typed artifacts and 452 declared paths, two cold/settled references, both traced 10-to-0 edits, same normalized rustc arguments, same native caller output. Raw gate failed: ten archives and 256 CGU names differ. Zero clock samples.')
