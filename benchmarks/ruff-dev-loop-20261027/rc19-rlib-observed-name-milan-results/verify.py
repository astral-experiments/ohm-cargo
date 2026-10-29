"""Verify every portable identity and both independent native witnesses in each original direction."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
from collections import Counter

here=Path(__file__).resolve().parent
args=argparse.ArgumentParser(description=__doc__)
args.add_argument('--archive-root',type=Path,help='optionally re-read the actual retained archive and independent LLVM golden in every phase')
args=args.parse_args()
r=json.loads((here/'native.json').read_bytes())
assert r['scores']==0 and r['unchanged_schedules_and_thresholds']
assert r['original_transplant']=={'cargo_exit':0,'guard_exit':1,'native_counts':{'cargo':1,'rustc-query':30,'rustc-full':252,'gcc':50,'collect2':50,'stock-wild':50}}
assert r['registration_sha256']=='ede5626127dff33daac2eadb4f0a67125694f9c16b5f9a965e7b44cc858909f2'
assert r['receipts']['read-only-host-seed-v2.json']=='2382ed9c5b9fd5307432814d12b280f596c25641090ece5ec4f52564c2719603'
assert r['seed_report_sha256']==r['receipts']['v2-seed-qualified.json']=='a86be1a3aa80b2406a4af30cad2856b2531485c87b1dcf665c9554fd03a03d37'
old='39268dec6160e5b3812330e903e7e3ccb6408f7eb0954af6041e3d274af856df'
for a,z in r['seed'].items():
 assert z['arm']==a and z['sole_image']=='cargo' and z['full_compilers']==z['queries']==z['native_links']==0
 assert z['fresh']==z['units']==248 and z['files']==452 and z['root_sha256']==old
 assert z['before_after_sha256']=='64619248a515a474eb68e13b778d3d2ac5cdea6c7e96b4e5b7af53fa5e0023d0'
ids=r['subvolume_ids'];assert len({ids['immutable_seed'],*ids['paired'].values(),*ids['unchanged_controls'].values()})==5
for source,lines in [('H',[1]),('P',[2,3,4])]:
 z=r['fresh_machine_references'][source]
 assert [x[2]for x in z['typed']]==[0,248] and all(x[1]==248 for x in z['typed'])and z['typed'][0][3]==z['typed'][1][3]==z['program']['linter']
 assert z['program']['exit']==0 and z['program']['stdout']==''.join(f'{n} SIM222\n'for n in lines)
assert r['order']==['parent-B','parent-A','historical-B','historical-A'] and set(r['order'])==set(r['rows'])
F=runpy.run_path(str(here/'name_oracle.py'))
roster=sorted('ruff_db ruff_linter ruff_python_ast ruff_python_codegen ruff_python_importer ruff_python_index ruff_python_literal ruff_python_parser ruff_python_semantic ruff_ranged_value'.split())
for kind,source in [('parent','P'),('historical','H')]:
 gold=r['rows'][kind+'-A']['current_inputs']
 invs=[];sigs=[];caller=[]
 for a in 'BA':
  step=r['rows'][kind+'-'+a];w=step['current_inputs'];watch=step['passive_watch'];cur=step['current'];lit=step['literal_equality'];match=step['matched_names_at_open']
  assert w['arm']==step['arm']==a and step['kind']==kind and w['whole_file_equal']
  assert w['bytes']==cur['initial_bytes']==cur['new_bytes']==lit['bytes']==101719820
  assert w['successful_target_clones']==int(a=='B')
  names=[x['name'] for x in w['member_inputs']];members=w['archive_members'];assert len(names)==258 and len(members)==260 and names[:2]==['lib.rmeta','lib.rmeta-link']
  assert [x['name']for x in members]==['/','//',*names]
  assert [{k:x[k]for k in ('name','size','sha256')}for x in members[2:]]==w['member_inputs']
  true=F['by_stem'](names[2:]);seen=F['by_stem']([x['name']for x in watch['edit']['objects']])
  assert true==seen and len(true)==256 and [e['role']for e in watch['edit']['events']]==['create','publish','remove']
  assert not watch['repeat']['events'] and not watch['repeat']['objects'] and watch['edit']['returncode']==watch['repeat']['returncode']==0
  assert match['equal'] and match['count']==256 and match['sha256']==lit['names_sha256']==hashlib.sha256(b'\0'.join(sorted(n.encode()for n in names[2:]))).hexdigest()
  assert (lit['literal_equal'],lit['fields'],lit['objects'])==(True,512,256)
  assert lit['current_nonce']==next(iter(seen.values())).decode()
  assert lit['reference_sha256']==gold['product_sha256'] and lit['actual_sha256']==lit['expected_sha256']==w['oracle_sha256']==w['product_sha256']==cur['new_sha256']==cur['repeat_sha256']
  assert cur['initial_fd_sha256']==(old if kind=='parent'else r['rows']['parent-'+a]['current']['new_sha256'])
  assert cur['replaced_inode'] and cur['initial_fd_sha256']!=cur['new_sha256'] and cur['fresh']==[238,248] and cur['dirty']==roster and cur['repeat_roles']==['cargo'] and cur['declared_files']==452
  queries=[x for x in w['compiler_invocations']if x['role']=='query'];full=[x for x in w['compiler_invocations']if x['role']=='full']
  assert len(full)==10 and sorted(x['target']for x in full)==roster and len(queries)<=int(a=='B')
  sigs.append(sorted((x['target'],x['without_origin_sha256'])for x in full))
  invs.append([step['raw_receipts'][k+'-inventory.json']for k in ('edit','repeat')])
  got=step['actual_and_independent_native_caller'];assert got['exit']==0 and got['linter']==w['product_sha256'] and got['input']==r['fresh_machine_references'][source]['program']['input']
  assert got['stdout']==r['fresh_machine_references'][source]['program']['stdout'] and got['stderr_sha256']==hashlib.sha256(b'').hexdigest()
  assert step['actual_independent_caller_raw_sha256']==[got['executable']]*2
  assert got['executable']==r['rows'][kind+'-A']['actual_and_independent_native_caller']['executable']
  if source=='H':
   assert got['executable']==r['fresh_machine_references'][source]['program']['executable']
  assert set(w['controls'])=={'object-name','metadata-byte'} and len({*w['controls'].values(),w['product_sha256']})==3
  assert step['modified_controls']['accepted']==lit and set(step['modified_controls']['rejected'])=={'wrong-current-name','missing-current-name','wrong-real-source','changed-object-byte'}
  assert all(d['exception']in('AssertionError','ValueError')for d in step['modified_controls']['rejected'].values())
  assert all(re.fullmatch('[a-f0-9]{64}',v)for v in step['raw_receipts'].values())
  caller.append(got['executable'])
  if args.archive_root:
   d=args.archive_root/(kind+'-A')/'rebuild/reference';ar,=d.iterdir()
   reconstructed=F['verify'](ar,gold,watch['edit'],args.archive_root/(kind+'-'+a)/'published.rlib')
   assert reconstructed==lit
 assert invs[0]==invs[1] and sigs[0]==sigs[1] and caller[0]==caller[1]
 assert all(x>=f for x,f in zip([r['frees_after_native'][n]for n in ('home','scratch','image')],[25*2**30,25*2**30,2*2**30]))
 print(source,'two actual 258-input reconstructions, 256 independent names, 512 fields, four native callers and eight name controls passed')

elf=json.loads((here/'cold-warm-elf.json').read_bytes())
sections=json.loads((here/'cold-warm-sections.json').read_bytes())
symbols=json.loads((here/'cold-warm-symbols.json').read_bytes())
assert elf['full_sha256']==[r['fresh_machine_references']['P']['program']['executable'],r['rows']['parent-A']['actual_and_independent_native_caller']['executable']]
assert elf['equal_file_width'] is False and elf['bytes']==[75800480,75800496]
assert elf['section_count']==40 and set(elf['differing_sections'])=={'.note.gnu.build-id','.strtab','.symtab','.shstrtab'}
assert sections['all_program_headers_equal'] and sections['elf_header_differences']=={'6':[75797920,75797936]} and sections['allocated_data_difference_only_gnu_build_id']
assert (symbols['symbol_count'],symbols['identical_name_and_metadata_count'],symbols['unmatched_full_symbol_count'])==(85338,85293,[45,45])
def normalize(records):
 return sorted((re.sub(r'\.llvm\.\d+', '.llvm.{decimal}',v['symbol']),v['fields_after_name'],v['copies'])for v in records)
cold,warm=symbols['unmatched_cold_examples'],symbols['unmatched_warm_examples']
assert len(cold)==len(warm)==45 and normalize(cold)==normalize(warm)
assert symbols['all_fields_except_name_multisets_match'] and symbols['all_numeric_llvm_normalized_fields_equal']
print('Retained additional cold P native ELF discrepancy: 45 local LLVM decimal symbol suffixes out of 85,338 symbols, program headers equal, only the build ID differs among allocated section payloads.')
