"""Recount the physical native processes, compare the changed/restored programs, and validate the retained exclusions."""
from collections import Counter
from pathlib import Path
import gzip, json, re
r=Path(__file__).resolve().parent
data=json.loads((r/'stages.json').read_bytes());events=json.loads(gzip.decompress((r/'physical-executions.json.gz').read_bytes()))
assert data['ruff']=='93526150df078af7dd8fc4226cdcc469539d2001' and data['release']=='1.99.0-18'
assert data['edit_file']=='crates/ty_server/src/document/range.rs' and data['original_source']!=data['edited_source']
assert data['roster_sha256']=='e3254bff0fba6072df809c053ef4e7d7b6490d144568bf3fb4cd6916bd4db316'
s=data['stages'];assert len(s)==11 and set(events)==set(s)|{'focused'}
ids={'cargo':'02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573','rustc':'c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60','stock-wild':'0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5','gcc':'1b99826121ae6682a634e5efe09bd3e3df58ce58e0b28f849114ab5b89139c26','collect2':'4d1f341ae5b763b513258ee2812422a45e063c30a2f1924a0cf63d3699f3a158'}
for stage,rows in events.items():
 d=s[stage] if stage in s else data['incomplete_controls'][stage];p=d['provenance'];assert (p['root'],p['home_parent'],p['euid'],p['uid_map'])==(0,0,1000,[0,0,4294967295]) and p['images']==ids
 assert Counter(x['role'] for x in rows)==d['counts'] and d['counts']['cargo']==1
 for x in rows:
  assert re.fullmatch('[0-9a-f]{64}',x['argv_sha256']) and x['dev']>0 and x['ino']>0
  if x['exit']:assert x['role'] in ('gcc','collect2') and x['exit']==1 and x['output'] in (None,'conftest')
 if stage=='focused':assert d['incomplete_verdict_oracle'] and d['cargo_succeeded'];continue
 assert d['exit']==0 and d['listed']==200 and d['units']==(300 if d['scope']=='focused' else 619)
 assert sorted(x['output'] for x in rows if x['role']=='stock-wild')==d['links']
 assert [x['target'] for x in rows if x['role']=='rustc-full']==d['full_compilers']
 changed=d['source']=='notebook';assert d['source_sha256']==data['edited_source' if changed else 'original_source']
 assert d['tests']==[[name,101 if changed else 0] for name in ('notebook::hover_past_end_of_cell','notebook::inlay_hints_range_past_end_of_cell')]
 assert d['e2e_linked']==('e2e-f978f73ba5a3a2ed' in d['links'])
repeats=('repeat-1','repeat-2','workspace-confirm','after-edit','final-repeat')
for n in repeats:
 d=s[n];assert (d['fresh'],d['full_compilers'],d['e2e_linked'])==(563,['ron'],True);assert all(d['counts'][k]==50 for k in ('rustc-link-only','gcc','collect2','stock-wild'));assert len(set(d['links']))==50 and d['links']==s['repeat-1']['links']
f=s['focused-repeat'];assert f['fresh']==300 and f['counts']=={'cargo':1}
for n in ('notebook-edit','restored'):
 d=s[n];assert d['e2e_linked'] and [d['counts'][k] for k in ('rustc-full','rustc-link-only','stock-wild')]==[12,43,52]
assert s['clean-edit']['fresh']==0 and s['clean-edit']['e2e_linked'] and s['clean-edit']['counts']['stock-wild']==188
for names,sha,size in [(('repeat-1','repeat-2','restored','final-repeat'),'be6b9375b66036f898876d7f55d745c7ea11d028f7b106c31a273c26e2cdcef7',226518976),(('notebook-edit','after-edit','clean-edit'),'d76ef359714fc4339f053598978ec5464829f7d09adb24cdfd6defcae3fb56e8',226518928)]:
 assert all((s[n]['e2e_sha256'],s[n]['e2e_bytes'])==(sha,size) for n in names)
assert s['workspace-confirm']['e2e_sha256']=='eb4c8725b51ab56ea7a0561c4d4782462b9571a636c800d8dd9be86050bd976c' and s['workspace-confirm']['e2e_bytes']==226518976
print('Verified 11 Ruff verdicts, the edited warm/clean ELF, the original/restored ELF and',sum(map(len,events.values())),'observed physical processes.')
