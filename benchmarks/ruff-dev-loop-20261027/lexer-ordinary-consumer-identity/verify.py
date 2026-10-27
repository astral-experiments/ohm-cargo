from pathlib import Path
import hashlib,json,collections
p=Path(__file__).resolve().parent;out=p/'observations';j=json.loads((out/'complete.json').read_bytes());rows=j['rows'];assert len(rows)==18 and len({x['driver'] for x in rows})==2
fmt=lambda h:bytes.fromhex(h)[::-1].hex()
orig=fmt(j['parser']['restored']['serialized_public_svh']);edit=fmt(j['parser']['edited']['serialized_public_svh']);assert orig!=edit and orig!=fmt(j['parser']['edited']['serialized_private_svh']); assert j['permitted_search_path_count']==232 and len(j['dirs_with_parser_before_private_overlay'])==len(j['private_parser_entries'])==1
for n in ('ruff_python_codegen','ruff_python_importer'):
 assert fmt(j['physical_restored'][n]['parser_edges'][0][2])==orig
assert fmt(j['fresh_edited_codegen']['parser_edges'][0][2])==edit
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
for r in rows:
 n=r['caller_or_producer'];v=r['parser'];d=out/(r['driver'][:8]+'-'+v+'-'+n);assert sha(d/'argv.json')==r['argv_sha256'] and sha(d/'stderr.jsonl')==r['stderr_sha256'] and json.loads((d/'observation.json').read_bytes())==r
 if n in ('ruff_python_codegen','ruff_python_importer') and v=='edited':
  assert r['status']==1 and [x['code'] for x in r['diagnostics']]==['E0460'];assert n in r['diagnostics'][0]['message'] and 'ruff_python_parser' in r['diagnostics'][0]['message'];log=(d/'loader-rejections.log').read_text();assert f'Rejecting via hash: expected {orig} got {edit}' in log
 elif n=='diag':
  assert r['status']==1 and [x['code'] for x in r['diagnostics']]==['E0061'];sp=r['diagnostics'][0]['definition_spans'][0];assert sp['line_start']==(1623 if v=='restored' else 1620) and sp['column_start']==8
 else: assert r['status']==0 and r['diagnostics']==[]
if (p/'SHA256SUMS').exists():
 for line in (p/'SHA256SUMS').read_text().splitlines():
  h,f=line.split('  ',1);assert sha(p/f)==h,f
s=json.loads((p/'selected-query-witnesses.json').read_bytes());assert all(set(i['result']['named'])=={'root'} for i in s['H2-retained-actual-restore']);assert len(s['H5-cache-only-edit']['units'])==2
print('verified 18 native compiler invocations, four exact E0460 loader rejections, four current E0061 definition notes, a freshly rebuilt Rust library and ordinary external caller')
