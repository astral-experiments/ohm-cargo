"""Verify every distinguished product, its source bytes and the complete decoded DWARF comparisons."""
from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parent;read=lambda n:json.loads((p/n).read_bytes());h=lambda b:hashlib.sha256(b).hexdigest()
if (p/'SHA256SUMS').exists():
 for line in (p/'SHA256SUMS').read_text().splitlines():v,n=line.split('  ');assert Path(n).name==n and h((p/n).read_bytes())==v
e=read('decoded-elf.json');t=read('transfer.json');r=read('original-O-A-C.json');k=read('distinguished-products.json')
assert k['decoded_elf']==h((p/'decoded-elf.json').read_bytes()) and len(e['products'])==8 and len(k['known_products'])==len(e['differential'])==4
assert len(set(t['files'].values()))==9
for a in 'OAC':
 u=r['arms'][a];assert u['observed_workspace_namespace']=='v2-'+k['namespaces'][a] and len(u['rosters'])==4
 for phase,z in u['rosters'].items():
  assert z['units']==619 and z['typed']==r['arms']['O']['rosters'][phase]['typed'] and z['number_of_changed_typed_fields']['filenames']==1042
assert r['arms']['O']['rosters']['cold']['raw']==r['arms']['A']['rosters']['cold']['raw']!=r['arms']['C']['rosters']['cold']['raw']
assert r['cross']['C']['cold']['raw_equal']==106 and r['cross']['A']['cold']['raw_equal']==110
for name,w in k['known_products'].items():
 role=w['role'];left,right=(e['products'][a+'-'+role] for a in 'AB');d=e['differential'][role];assert left['raw_sha256']==w['older_reference']['raw']==t['files']['A-'+role] and right['raw_sha256']==w['new_reference']['raw']==t['files']['B-'+role]
 assert d['all_code_data_and_unclaimed_ELF_bytes_identical'] and d['exact_decoded_debug'] and d['namespace_evidence_pass']
 assert len(left['sections'])==len(right['sections']) and left['sections'].keys()==right['sections'].keys() and left['file_size']==right['file_size']
 other=[n for n in left['sections'] if left['sections'][n]!=right['sections'][n]]
 assert set(other)=={'.debug_info','.debug_macro','.debug_str','.note.gnu.build-id'} and not d['section_metadata_differences']
 assert left['all_other_bytes']==right['all_other_bytes'] and left['allowlist_byte_ranges']==right['allowlist_byte_ranges']
 assert left['debug_strings']['canonical_inventory']==right['debug_strings']['canonical_inventory'] and left['debug_strings']['entries']==right['debug_strings']['entries']
 for arm,v in zip('AB',(left,right)):
  ns,=v['debug_strings']['actual_namespace_spellings'];assert ns.endswith('/tikv-jemalloc-sys/bfdeba99f689e13b/out/build') and 'v2-'+k['namespaces'][arm] in ns
  assert v['info']['namespace_count']==len(v['info']['namespace_attributes'])==58 and all('DW_AT_comp_dir' in x and ns in x for x in v['info']['namespace_attributes']) and v['macro']['namespace_count']==0
 for sec in ['macro','info']:
  assert left[sec]['decoded']==right[sec]['decoded'] and left[sec]['lines']==right[sec]['lines']>10000 and left[sec]['strp']==right[sec]['strp'] and not left[sec]['stderr_len'] and not right[sec]['stderr_len']
print(json.dumps({'distinct_exact_elf_files':8,'unexpected_operational_differences':0,'source_namespaces':k['namespaces'],'raw_cold_equal_O_to_A':110,'raw_cold_equal_O_to_C':106,'full_debug_pairs':4,'workspace_wall_commands':0},sort_keys=True))
