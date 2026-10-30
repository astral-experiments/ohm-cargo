#!/usr/bin/env python3
from pathlib import Path
import json,gzip,hashlib,os,sys
import importlib.util
d=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('study_analysis',d/'analysis.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);stats=mod.stats
def loaded(n):return json.loads(gzip.decompress((d/n).read_bytes()))
j=loaded('observations.json.gz');s=json.loads((d/'study.json').read_bytes());t=json.loads((d/'prior-same-compiler.json').read_bytes());assert j['principals']==s['orders']==[['R','K'],['K','R']]
assert len(j['refs'])==6 and all(len(v['elf'])==64 for v in j['refs'].values())
assert j['roles']['R']['std_ledger']==j['roles']['K']['std_ledger'] and j['roles']['R']['std_count']==j['roles']['K']['std_count']==53
for ro in ('R','K'):
 assert j['roles'][ro]['source']==s['raw' if ro=='R' else 'compact'] and j['roles'][ro]['sha']==s['driver'][ro] and j['roles'][ro]['cargo']==s['cargo'] and j['roles'][ro]['wild']==s['wild']
 total=sum(len(v)for v in j['observations'].values());assert total==68
for name,o in j['observations'].items():
 ref=name.startswith('ref-');ro=name.split('-')[1] if ref else name[-1]
 if ref:assert len(o)==1
 else:assert len(o)==16 and set(o)=={ph[0] for ph in s['phases']}
 for ph,x in o.items():
  a=x['source'];assert x['typed']==97 and x['elf']==j['refs'][ro+'/'+a]['elf'] and x['verdict']=='Expr='+('64' if a=='A' else '56')+' signed-expression='+('accepted'if a=='C'else'rejected')
  assert x['grammar']==j['source']['changed_sha256' if a=='C' else 'original_sha256']
  if ph.startswith('unchanged'):assert x['dirty']==[]
  elif 'edit-B' in ph or 'restore-B' in ph:assert x['dirty']==['ruff_python_parser']
  elif ph in ('empty-A','empty'):assert len(x['dirty'])==97
  else:assert x['dirty']==['ruff_python_ast','ruff_python_parser']
  if ph.startswith('native-'):
   k=x['kernel'];assert k['full']==x['dirty'] and k['wild']==0 and 'tables' not in k['actual_execs'] and k['trace_files']>0 and k['trace_bytes']>0 and x['cargo_elapsed_ns'] is None
   if ro=='R':assert not k['events'] and not k['live_compiler_thread_owners']
   if ro=='K':
    for crate in k['full']:
     for table in ('dep-graph','query-cache'):
      for verb in ('create','open_read'):assert k['events'].get(crate+'/'+table+'/'+verb)==1,(name,ph,crate,table,verb,k['events'])
    assert sorted(t['crate'] for t in k['live_compiler_thread_owners'])==k['full']
    assert all(t['actual_rustc_inode']==j['roles']['K']['launcher_identity'][:2] for t in k['live_compiler_thread_owners'])
  else:assert x['cargo_elapsed_ns']>0 and x['kernel'] is None
  for lib,ar in x['rlibs'].items():assert ar['objects']>=1 and ar['size']>0 and len(ar['sha'])==len(ar['object_body_set'])==64
  assert x['storage']['bytes']>=x['storage']['alternate_exclusive']>=0
  if ro=='R':assert not x['storage']['packed_counts']
assert t['source']=='8ea2252344ba85e7406f4f04f979053e2bd191b1' and t['verified_sha256']=='80ff481ef6b4f7f923300aeffbc07a6bbe28d2f3524626a11227883bb8e5a6db'
assert stats(j,t)==json.loads((d/'results.json').read_text())
print('68 real Cargo builds and 68 matched native ELF/verdicts; R/K, K/R; 16 traced physical edit/return controls; 53 common standard-library files and immutable per-role native compilers.')
