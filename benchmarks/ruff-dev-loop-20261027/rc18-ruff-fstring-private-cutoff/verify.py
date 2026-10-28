"""Validate the exported record without access to a builder or any private path."""
from collections import Counter
from pathlib import Path
import gzip,hashlib,json,re
D=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
read=lambda n:json.loads(gzip.decompress((D/n).read_bytes()))
full=read('full-historical.json.gz');slice=read('equal-width.json.gz');raw=read('all-rosters.json.gz');audit=json.loads((D/'audit.json').read_text());assert full['release']['cargo']=='02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573';assert full['source']['commit']==audit['source_commit'] and full['source']['parent']==audit['parent_commit'];assert full['source']['patch_sha256']==sha((D/'change.patch').read_bytes());assert slice['inputs']['patch']==sha((D/'slice.patch').read_bytes());assert slice['inputs']['file_bytes']>65000 and len(slice['inputs']['physically_different_offsets'])==2
commit=slice['native_commitments'];assert sha((D/'all-rosters.json.gz').read_bytes())==commit['gzip_sha256'];assert len(raw['archives'])==commit['archive_digests']==236 and len(raw['rmeta'])==commit['metadata_digests']==163;assert sum(len(x['members']) for x in raw['archives'].values())==30873==commit['members'];assert set(raw['phases'])==set(full['phases'])|set(slice['phases']);assert len(raw['phases'])==13
for h,a in raw['archives'].items():
 assert a['archive_sha256']==h;off=8
 for e in a['members']:
  assert e['offset']==off+60 and re.fullmatch('[a-f0-9]{64}',e['sha256']) and re.fullmatch('[a-f0-9]{64}',e['header_sha256']);off=e['offset']+e['bytes']+e['bytes']%2
 assert off==a['bytes']
for h,v in raw['rmeta'].items():assert v['sha256']==h and 'public_hash' in v['header'] and 'private hash' in v['header']
def perfile(phase):return {(q['crate'],tuple(q['kind']),tuple(sorted(q['files']))):q for q in raw['phases'][phase]}
def single(files,ext):
 matches={v['sha256'] for p,v in files.items() if p.endswith(ext)};assert len(matches)==1;return matches.pop()
for result in (full,slice):
 for edge,rows in result['local_libraries'].items():
  a,b=edge.split('__');left,right=perfile(a),perfile(b);assert set(left)==set(right) and len(left)==len(rows)==50
  for v in rows:
   matches=[k for k in left if k[:2]==(v['name'],tuple(v['kind'])) and single(left[k]['files'],'.rlib')==v['archive'][0] and single(right[k]['files'],'.rlib')==v['archive'][1]];assert len(matches)==1;key=matches[0];a1,a2=left[key]['files'],right[key]['files'];ar=[single(x,'.rlib')for x in (a1,a2)];rm=[single(x,'.rmeta')for x in (a1,a2)];assert v['archive']==ar and v['rmeta']==rm;native=[[(z['name'],z['sha256'])for z in raw['archives'][h]['members']if z['name'].endswith('.o')and z['elf']]for h in ar];assert (native[0]==native[1])==v['all_native_names_and_bytes_equal'];co=[Counter(z[1]for z in l)for l in native];assert (co[0]==co[1])==v['all_native_payload_multisets_equal'];assert sum((co[0]&co[1]).values())==v['identical_object_payloads'];assert [len(l)for l in native]==v['native_objects'];assert [re.search('public_hash (\\w+)',raw['rmeta'][h]['header'])[1]for h in rm]==[r['public']for r in v['root']]
def verdict(state,ns,expected,lines):
 for n in ns:
  z=state['phases'][n]['programs'];assert z['external_output']==expected and z['cli_lines']==lines and z['cli_exit']==1
 assert len({state['phases'][n]['programs']['complete_cli_json_sha256'] for n in ns})==1
orig=['Truthy','Unknown','Unknown','Unknown'];whole=['Unknown','Truthy','Truthy','Truthy'];token=['Unknown','Truthy','Unknown','Unknown'];verdict(full,['cold-current','settle-current','restored','unchanged-restored'],orig,[1]);verdict(full,['warm-reverse','unchanged-reverse','clean-reverse'],whole,[2,3,4]);verdict(slice,['slice-baseline','slice-restore','slice-restore-repeat'],orig,[1]);verdict(slice,['slice-warm','slice-repeat','slice-cold'],token,[2]); f=full['local_libraries']['settle-current__warm-reverse'];changed=[z for z in f if z['archive'][0]!=z['archive'][1]];assert len(changed)==32;assert all(z['rmeta'][0]!=z['rmeta'][1] and z['root'][0]['public']!=z['root'][1]['public']for z in changed);assert len([z for z in changed if z['all_native_payload_multisets_equal']])==31;assert [z['name']for z in changed if not z['all_native_payload_multisets_equal']]==['ruff_python_ast'];assert not any(z['all_native_names_and_bytes_equal']for z in changed)
for n in ('warm-reverse','restored'):
 z=full['phases'][n];assert (z['all_full'],len(z['pure_lib_full']),len(z['mixed_full']),len(z['binaries_full']),len(z['link_only']),len(z['stock_wilds']))==(38,30,2,6,0,8)
for n in ('settle-current','unchanged-reverse','unchanged-restored'):
 z=full['phases'][n];assert (z['all_full'],len(z['link_only']),len(z['stock_wilds']))==(2,4,5)
for n,expect in [('slice-warm',(4,6,8)),('slice-restore',(8,4,8)),('slice-baseline',(2,4,5)),('slice-repeat',(2,4,5)),('slice-restore-repeat',(2,4,5))]:
 z=slice['phases'][n];assert (z['all_full'],len(z['link_only']),len(z['native_outputs']))==expect
z=next(v for v in slice['local_libraries']['slice-baseline__slice-warm'] if v['name']=='ruff_python_ast');assert z['root'][0]['public']==z['root'][1]['public'] and z['root'][0]['private']!=z['root'][1]['private'];assert 'ohm-foreign-span-bytes' in slice['restored_depinfo']['ty_python_semantic']['current_depfiles'][0]['select_markers'];assert full['source_locations']['settle-current']['is_empty_f_string']['source']==['<other>/helpers.rs:1629'] and full['source_locations']['clean-reverse']['is_empty_f_string']['source']==['<other>/helpers.rs:1626']
for mode in ['slice-baseline','slice-warm','slice-cold','slice-restore']:assert slice['source_locations'][mode]['is_empty_f_string']['source']==['<other>/helpers.rs:1629']
for phase,expected in [('settle-current',orig),('warm-reverse',whole)]:
 a=full['stale_parser_controls'][phase];b=full['stale_parser_controls'][phase+'-stale-parser'];assert a['compile_status']==0 and a['output']==expected and b['compile_status']==1 and b['error_codes']==['E0460'] and a['selected']['ruff_python_ast']==b['selected']['ruff_python_ast'] and a['selected']['ruff_python_parser']!=b['selected']['ruff_python_parser']
assert audit['unique_released_cargo']==44 and audit['number_of_releases']==55 and not any(audit['exact_edit_hits'].values());print('Verified two source changes, 13 Cargo commands, 4 stock parser compatibility controls, 50 local libraries, 236 raw archives, 30,873 ordered members, and 163 metadata commitments.')
