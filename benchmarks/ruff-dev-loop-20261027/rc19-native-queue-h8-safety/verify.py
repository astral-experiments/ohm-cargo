from pathlib import Path
from collections import Counter
import json,gzip
p=Path(__file__).resolve().parent
def read(name):
 b=(p/name).read_bytes()
 return json.loads(gzip.decompress(b)if name.endswith('.gz')else b)
expected={'cargo':1,'rustc-full':1,'rustc-link-only':50,'gcc':50,'collect2':50,'stock-wild':50}
groups=read('memory.json.gz'); assert set(groups)=={'first_one_id','ordinary_full_map','ordinary_equal_inputs'}
for mode,runs in groups.items():
 assert len(runs)==6
 for r in runs:
  lim,arm=r['limit_gib'],r['arm']; assert r['exit']==0 and r['native']==expected and set(r['process_statuses'])=={'0'}
  assert r['hardware_limit_bytes']==lim*2**30==int(r['after']['memory.max']) and r['swap_max']==r['after']['memory.swap.max']=='0' and r['after']['memory.swap.current']=='0'
  assert r['max_group_bytes']==int(r['after']['memory.peak']) and r['measured_over_max_bytes']==max(0,r['max_group_bytes']-r['hardware_limit_bytes'])
  assert 0<r['native_overlap']['max_concurrent_wild_parents']<=50
  if mode=='ordinary_equal_inputs':assert len(r['matched_argv'])==64 and r['actual_descendant_service_asserted']
  before,after=[dict(x.split() for x in r[k]['memory.events'].splitlines())for k in ('before','after')]
  assert before['oom']==after['oom']=='0' and before['oom_kill']==after['oom_kill']=='0'
  elf=read(f'{mode}-{arm}-{lim}-elf.json.gz'); assert set(elf['before'])==set(elf['after']) and len(elf['after'])==50
  overlap=r['native_overlap'];assert overlap['largest_sum_of_incumbent_output_bytes']==sum(elf['before'][k]['bytes']for k in overlap['largest_sum_names'])
  assert all(elf['before'][k]['fields']['normalized']==elf['after'][k]['fields']['normalized']for k in elf['after'])and r['known_field_normalized_equal']==50
  m=read(f'{mode}-{arm}-{lim}-sample.json.gz')['samples'];assert max(x[2]for x in m)==r['sampled_max_sum_rss_bytes']and max(x[3]or 0 for x in m)==r['sampled_max_sum_pss_bytes']
s=read('tiny.json');assert len(s)==18 and s['failed-source']['status']==101
edges=read('adverse-file-types.json')
same=lambda data:{k:(v['kind'],v['output_path_digest'],v['bytes']if k=='zero' else None)for k,v in data.items()}
assert same(edges['baseline'])==same(edges['candidate'])==same(edges['diagnostic'])
assert {k:v['kind']for k,v in edges['baseline'].items()}=={'removed':'missing','symlink':'link','zero':'regular','failed-output':'directory'}
for k,v in edges['baseline'].items():assert len(v['output_path_digest'])==64 and not any(name[1]=='alpha'for name in s[k]['estimate']['accepted'])
assert edges['baseline']['zero']['bytes']==0
for i in ['check-fresh','build-fresh','test-fresh']:assert not s[i]['roles'] and not s[i]['estimate']['stats'] and not s[i]['estimate']['accepted']
assert read('unit-test.json')['reported_status']==0 and '1 passed; 0 failed' in read('unit-test.json')['stdout']
warm=read('warm.json');assert len(warm)==4
for k,row in warm.items():
 assert [r['fresh']for r in row['warm']]==[563,563]; n=read('batch-'+k+'-native.json.gz')
 assert n['counts']==expected and n['units']==619 and n['fresh']==563 and n['programs']['listing']['listing_entries']==200
 assert len(n['output_files'])==50 and len(n['native_argv'])==150 and len(n['rust'])==51
 assert all(z['exit']==0 for z in n['programs'].values())
import hashlib
rank=read('physical-wild-launch-order.json.gz')
for b in ('1','2'):
 for a in ('A','B'):
  rr=rank[b][a];assert len(rr['rows'])==50 and [m['rank']for m in rr['rows']]==list(range(1,51))
  assert sorted(m['descending_size_rank']for m in rr['rows'])==list(range(1,51))
def sha(f):return hashlib.sha256((p/f).read_bytes()).hexdigest()
for b,proof in read('rust-explicit-inputs.json').items():
 docs={}
 for arm,expected in proof['arms'].items():
  name=f'rust-inputs-batch-{b}-{arm}.json.gz';assert sha(name)==expected;docs[arm]=read(name)
 assert set(docs['A'])==set(docs['B']) and len(docs['A'])==51
 groups=Counter()
 for key,unit in docs['A'].items():
  other=docs['B'][key];assert unit['role']==other['role'] and unit['target']==other['target']
  for u,v in zip(unit['inputs'],other['inputs'],strict=True):
   assert all(u[k]==v[k] for k in ('kind','crate','arg_index','name_sha256'))
   same=(u['size'],u['sha256'])==(v['size'],v['sha256'])
   groups[unit['role']+'/'+u['kind']+('/same'if same else'/changed')]+=1
 assert dict(groups)==proof['classes'] and groups['rustc-link-only/rlink/same']==50 and groups['rustc-full/crate_root/same']==1
 assert not groups['rustc-full/explicit_extern/changed']
for code in ('initial-independent','matched-batch1','matched-batch2'):
 detail=read('operands-'+code+'.json'); captured={}
 for a in ('A','B'):
  name='operands-'+code+'-'+a+'.json.gz';assert sha(name)==detail['members'][a];captured[a]=read(name)
 L,R=captured['A'],captured['B'];assert set(L['ordered'])==set(R['ordered']) and len(L['ordered'])==50
 observed=Counter()
 for target,args in L['ordered'].items():
  paired=R['ordered'][target];assert len(args)==len(paired)
  for (i,x),(j,y)in zip(args,paired):
   assert i==j;u,v=L['inputs'][x],R['inputs'][y];assert u['kind']==v['kind']and u['is_cgu']==v['is_cgu']
   typ=('same_name'if x==y else'different_name')+('_missing'if u['sha256'] is None or v['sha256'] is None else ('_same_bytes'if (u['bytes'],u['sha256'])==(v['bytes'],v['sha256'])else'_different_bytes'))
   observed[typ]+=1
   if u['is_cgu']:observed['cgu_'+typ]+=1
 assert dict(observed)==detail['counts']
 if code=='initial-independent':
  assert sum(v for k,v in observed.items()if k.startswith('cgu_different_name'))==3060
  actually={key for key,u in L['inputs'].items()if key in R['inputs']and u['sha256']!=R['inputs'][key]['sha256']}
  left_names=read('initial-same-name-changed-archives.json');assert len(left_names)==45 and set(left_names)==actually
  assert all(name.endswith('.rlib')and L['inputs'][key]['is_archive']for key,name in left_names.items())
 else:
  assert set(observed)=={'same_name_same_bytes','cgu_same_name_same_bytes'}
  cert=read('quiescent-copy-'+code[-1]+'.json'); assert cert['real_rust_argv']==51 and cert['identical_ordered_native_recipes_after_three_validated_temporary_roles']==150
  assert cert['copy']['two_states_share_no_inodes'] and cert['copy']['logical_bytes_verified_per_arm']>10*2**30
  assert cert['copy']['unique_source_inodes']==cert['copy']['unique_copy_inodes']
print('Verified 18 memory-limited Ruff commands, four native arm admissions, 18 fallback cases, complete ordered explicit operands and the Rust unit test.')
