"""Verify the published counts and independently rederive layout from the original member manifest."""
import collections
import gzip
import hashlib
import importlib.util
import json
import re
from pathlib import Path

base=Path(__file__).resolve().parent
read=lambda name: json.loads((base/name).read_bytes())
valid=lambda v: isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) is not None
parser=read('result.json')
assert len(parser['family'])==92==len(parser['raw_file_sha256'])
assert set(parser['family'])==set(map(int,parser['raw_file_sha256']))
assert all(map(valid,parser['raw_file_sha256'].values()))
assert parser['expected_crate_types']==['lib']
assert parser['emit']==['--emit=dep-info,metadata,link']
assert parser['rlink_flags']==parser['save_temps_flags']==[]
assert parser['rlinks_before_after']==parser['cgu_aliases_before_after']==[[],[]]
assert parser['other_process_related_name_syscalls']=={}
rows=parser['aliases']
assert len(rows)==len({r['name']for r in rows})==len({r['workspace_cgu']for r in rows})==78
assert all(r['name'].endswith('.rcgu.o') and r['workspace_cgu'].endswith('.o') for r in rows)
assert all(r['work_product_same_inode_and_bytes'] and valid(r['input_sha256']) for r in rows)
for r in rows:
    assert r['hard_link_tid'] in parser['family'] and r['unlink_tid'] in parser['family']
    assert len(r['archive_input_open_sha256'])==1
    assert all(map(valid,[r['hard_link_sha256'],r['archive_input_open_sha256'][0],r['unlink_sha256']]))
for field in ['hard_link_sha256','unlink_sha256']:
    assert len({r[field]for r in rows})==len(rows)
assert parser['before_after_78_native_bytes']==sum(r['bytes']for r in rows)==4464192
events=parser['events']
assert 'copy' not in events and len(events['archive_rename'])==1 and len(events['metadata_cleanup'])==2
assert {r['name']for r in events['metadata_cleanup']}=={'lib.rmeta','lib.rmeta-link'}
assert parser['counts_parser_success']['linkat']==250
assert len(events['other_links'])+len(rows)==250
assert collections.Counter(r['class']for r in events['other_links'])=={'old incremental -> working generation':171,'other':1}
assert len({v['name'] for v in parser['before_visible']})==len({v['name']for v in parser['after_visible']})==3
assert {v['name']for v in parser['before_visible']}=={v['name']for v in parser['after_visible']}
assert len(parser['declared_outputs'])==2 and sum(v.endswith('.rmeta')for v in parser['declared_outputs'])==1
jobs=read('all-jobs.json')['all_rustc_jobs']
assert len(jobs)==len({v['root']for v in jobs})==38 and all(v['kind']=='full' and valid(v['exec_sha256']) for v in jobs)
assert collections.Counter(tuple(j['types'])for j in jobs)=={('lib',):30,('bin',):6,('cdylib','rlib'):2}
pure=[v for v in jobs if v['pure']]
assert all(v['save_temps_flags']==[] and v['rlink_flags']==[] and v['emit']==parser['emit']
           and not v['matched_error_counts'] and not v['kernel_copy_returned_bytes_over_all_family_files'] for v in pure)
for v in pure:
    c=v['counts'];assert c['hardlinked']==c['removed']==c['read_in_rustc']
    assert set(v['hardlink_source_classes'])=={'incremental working CGU'} and valid(v['matched_event_roster_sha256'])
assert sum(v['counts']['hardlinked']for v in pure)==4212
assert [(v['name'],v['counts']['unlinked_not_from_working_link']) for v in pure if v['counts']['unlinked_not_from_working_link']]==[('ruff_python_ast',2)]
assert next(v for v in pure if v['name']=='ruff_python_parser')['exec_sha256']==parser['raw_successful_exec_sha256']
native=read('object-custody.json'); values={k:v['value']for k,v in native['observed'].items()}
assert values=={'physical-hardlink':17,'borrowed-path':29,'early-fd':17,
                'cross-physical-copy':17,'cross-borrowed-path':29,'cross-early-fd':29}
assert len(set(native['variant_sha256']))==2 and all(map(valid,native['variant_sha256']))
assert all(v['input_sha256']==native['variant_sha256'][int(v['value']==29)] for v in native['observed'].values())
assert native['cross_device_errno']==18
layout=read('archive-ranges.json')
assert len(layout['products'])==31
assert all(r['native_payload_offset_delta']==0 and r['native_equal_offsets']==r['objects']==r['native_congruent_4096'] and
    r['native_headers_equal']==r['objects'] and r['all_member_ranges_equal']for r in layout['products'])
assert sum(r['objects']for r in layout['products'])==4306
assert sum(r['native_payload_bytes']for r in layout['products'])==509086792
assert sum(r['equal_native_suffix_bytes_proved']for r in layout['products'])==509345152
for r in layout['products']:
    assert all(v['length_equal']and v['offset_equal']for v in r['special_members'].values())
    assert {k for k,v in r['special_members'].items()if v['bytes_equal']}=={'/'}
old=base.parent/'rc18-ruff-fstring-private-cutoff'
if old.exists():
    assert hashlib.sha256((old/'SHA256SUMS').read_bytes()).hexdigest()=='a070a8dbba5b3ce8a873bc314d6adf8d203965be5c3c46de9c22395d8ee76bd9'
    spec=importlib.util.spec_from_file_location('archive_ranges',base/'reproduce/archive_ranges.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.compare(old)==layout
print('38 stock full rustcs; 4,212 pure-library create/read/unlink triples; 78 parser inputs; 31 aligned archives; 6 actual C consumers')
