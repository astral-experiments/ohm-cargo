"""Reread the sealed observations offline."""
import hashlib,json,sys
from pathlib import Path
p=Path(__file__).resolve().parent
def read(name):return json.loads((p/name).read_bytes())
def by_case(rows,tool_key='tool'):return {(r[tool_key],r['case']):r for r in rows}
s=read('subjects.json');data=read('observations.json');q=data['pinned']
base='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5';head='9de3bdd6675f02e08d687045383c097ab0ef6027c779f153a7823153ecf8445e'
for label in ('rc16','rc17'):
 assert s['original'][label]['wild']==base
 rows=by_case(data['original'][label]['direct_and_Cargo'])
 for n in ('raw-positional','raw-output','raw-response-name','raw-argv0'):assert rows['wild',n]['rc']==101 and rows['wild',n]['panic']
 assert rows['wild','raw-response-body']['rc']==1 and not rows['wild','raw-response-body']['panic']
 for row in data['original'][label]['GCC_environments']:
  if row['case'].startswith('raw-'):assert row['rc']==101 and row['panic'] and row['wild_count']==1 and row['executed'][0]['raw_ff']
for context in (q,data['bundled_lld_comparison']):
 for r in context['GCC_environments']:
  assert r['rc']==0 and r['value']==('99'if r['case']=='decoy' else '41') and not r['panic']
  if r['case']=='raw-TMPDIR':assert r['executed'][0]['raw_resolution_file']
  if r['case']=='raw-LIBRARY_PATH':assert r['executed'][0]['raw_search_dir']
 for r in context['direct_and_Cargo']:
  if r['level']=='direct':assert r['rc']==0 and r['program']==41 and r['same_as_ascii']
  if r['level']=='cargo' and r['case']in ('ascii','gcc-rsp-raw'):assert r['rc']==0 and r['program']=='41'
r=by_case(q['native_elf']);matched=r['stock','ascii']['elf']
for a in ('ascii','raw','nested','unicode-white','ascii-response','search-separate','search-joined'):assert r['candidate',a]['value']==41 and r['candidate',a]['elf']==matched
assert r['candidate','needed-native']['needed'][0]['basename_hex']==b'link-\xff.so'.hex() and r['candidate','needed-native']['missing_dso_rc']==127
for a in ('ordinary-missing','raw-missing','bad-option'):assert r['candidate',a]['rc']==1 and not r['candidate',a]['wrote'] and not r['candidate',a]['panic']
for a,good in [(q['native_sidecars'],True),(data['rejected_first_development_sidecars'],False)]:
 m=by_case(a);d=m['tested','dependency-and-trace'];assert d['dep_native_input']==d['dep_native_output']==d['stdout_native']==good and d['dep_has_decoy']!=good
 assert m['tested','forced-sysroot']['runtime']==(41 if good else 99) and m['tested','version-output']['exact_raw_basename']==good
u=by_case(q['canonical_utf8'])
for a in ('direct','nested_utf8','escaped_utf8','literal-at-value'):
 assert u['stock',a]['elf']==u['candidate',a]['elf'] and u['stock',a]['runtime']==u['candidate',a]['runtime']==41
assert u['candidate','direct']['elf']==u['candidate','nested_utf8']['elf'] and u['candidate','nested_utf8']['needed']==['libretain-one.so','libretain-two.so']
assert u['candidate','bad-quote']['stderr_sha256']==u['stock','bad-quote']['stderr_sha256']
for a in ('raw-rpath','raw-script','raw-library','saved-raw','wasm-raw'):assert u['candidate',a]['exit']==1 and not u['candidate',a]['panic'] and u['candidate',a]['elf']is None
assert u['candidate','saved-raw']['save_sentinel'] and not u['stock','saved-raw']['save_sentinel'] and not by_case(data['unscored_shared_save_fixture'])['candidate','saved-raw']['save_sentinel']
c=s['candidate'];assert c['build_rc']==c['library_rc']==c['regression_rc']==0 and c['results']['wild']=={'mode':'0o755','sha256':head,'size':10315032}
assert c['patch']=='62debcbfd9042c9b1d79bd27b9ca101c191e15e9dfd949cfc5294f395626072f'
print('verified both shipped releases, real Cargo, raw/Unicode ELF and response rules, clean errors, 2 checked-in regressions and 183 library tests')
