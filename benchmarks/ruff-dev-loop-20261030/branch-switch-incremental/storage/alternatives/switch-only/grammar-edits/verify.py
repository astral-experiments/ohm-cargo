from pathlib import Path
import hashlib,gzip,importlib.util,json
r=Path(__file__).resolve().parent; read=lambda n:json.loads((r/n).read_bytes()); j=json.loads(gzip.decompress((r/'observations.json.gz').read_bytes()));cfg=read('study.json');mode=j['filesystem']; assert mode in ('ext4','tmpfs')
reg='ext4-plan.json' if mode=='ext4' else 'ram-plan.json';expect=cfg['ext4_sha'if mode=='ext4' else 'ram_sha'];assert hashlib.sha256((r/reg).read_bytes()).hexdigest()==expect
assert j['principals']==cfg['orders']==[['R','K'],['K','R']] and j['qualification']['source']==cfg['compact'] and j['qualification']['tree']==cfg['expected_tree']
assert j['roles']['R']['std_ledger']==j['roles']['K']['std_ledger'] and j['roles']['R']['std_count']==j['roles']['K']['std_count']==53
for ro in ('R','K'):
 assert j['roles'][ro]['source']==cfg['raw' if ro=='R' else 'compact'] and j['roles'][ro]['sha']==(cfg['driver']['R'] if ro=='R' else j['qualification']['driver'])
 assert j['roles'][ro]['cargo']==cfg['cargo'] and j['roles'][ro]['wild']==cfg['wild']
for s,phases in j['observations'].items():
 ref=s.startswith('ref-');role=s.split('-')[1]if ref else s[-1]; assert len(phases)==(1 if ref else 16)
 for phase,x in phases.items():
  st=x['source'];assert x['typed']==97 and x['elf']==j['refs'][role+'/'+st]['elf'] and len(x['elf'])==64
  assert x['verdict']=='Expr='+('64'if st=='A'else '56')+' signed-expression='+('accepted'if st=='C'else'rejected')
  if 'unchanged' in phase:assert not x['dirty']
  elif 'edit-B' in phase or 'restore-B' in phase:assert x['dirty']==['ruff_python_parser']
  elif phase in ('empty','empty-A'):assert len(x['dirty'])==97
  else:assert x['dirty']==['ruff_python_ast','ruff_python_parser']
  if phase.startswith('native-'):
   k=x['kernel'];e=k['events'];assert k['full']==['ruff_python_parser'] and not k['wild'] and k['trace_files']>0 and not x['cargo_elapsed_ns']
   if role=='R' or phase!='native-edit-B':assert not e and not k['live_compiler_thread_owners'],(s,phase,e)
   else:
    for tb in ('dep-graph','query-cache'):assert e.get('ruff_python_parser/'+tb+'/open_read')==1
    assert not any(n.endswith('/create') for n in e)
    ro,=k['live_compiler_thread_owners'];assert ro['crate']=='ruff_python_parser' and ro['actual_rustc_inode']==j['roles']['K']['launcher_identity'][:2]
  else:assert x['cargo_elapsed_ns']>0 and x['kernel'] is None
  if role=='R':assert not x['storage']['packed_counts']
  assert 0<=x['storage']['alternate_exclusive']<=x['storage']['bytes']
spec=importlib.util.spec_from_file_location('study_stat',r/'analysis.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);a=m.analyze(j);assert a==read('results.json');assert a['native']=={'flanks':16,'physical_full':16,'physical_wild':0};assert a['oracles']['matching_final_ELFs']==68
print('68/68 real reference ELF verdicts, 4 independent empty B/C controls, 16 actual full parser rustcs in 16 diagnostic phases, 0 Wild in these library builds.')
print('All four first hot/second and later native table IO acceptance paths were recomputed in',mode)
