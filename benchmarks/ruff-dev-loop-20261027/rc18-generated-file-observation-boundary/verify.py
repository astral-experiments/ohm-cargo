"""Recompute the complete observed scope, two open orders, authenticated output gates, and cost comparison offline."""
from collections import Counter
from pathlib import Path
import hashlib,json,random,statistics,sys
D=Path(__file__).resolve().parent
def read(n):return json.loads((D/n).read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def verify():
 commands=read('commands.json'); profiles=read('profiles.json'); source=read('source-audit.json'); traces=read('physical-traces.json');selected=read('selected-inputs.json')
 assert commands['cargo_file_sha256']=='02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573' and commands['ruff']=='93526150df078af7dd8fc4226cdcc469539d2001'
 assert commands['ordinary']['program_artefacts']=={'.rlib':'8b44e1442003c8e1ef51b9989db2dca5128762dbb33022b3833b623ce5b5fadf','.rmeta':'7cc5a9e8c78ac557742bd3240b857807efd743fb9f4e6d350f4106a72e19adbf'}
 for runs in ('trusted_json','untrusted_json'):assert len(commands[runs]['commands'])==7 and all(x['artifacts']==182 for x in commands[runs]['commands'])
 ordinary_times=[q['ns']for q in commands['ordinary']['commands']if q['ns']is not None]
 assert len(ordinary_times)==7 and min(ordinary_times)>0
 for cohort in traces.values():
  for trace in cohort.values():
   assert trace['exec_roles']==['rustup','official-Cargo'] and len(trace['children_raw_traces_sha256'])==13
   assert trace['policy_marker']=={'openat':3,'close':3,'fchmod':3,'renameat':3,'statx':6,'write':3}
   paths=trace['script_paths'];assert len(paths)==46 and len({k.rsplit('/',1)[0]for k in paths})==23
   assert [(sum(v['opens']for k,v in paths.items()if k.endswith('/'+suffix)),sum(v['bytes']for k,v in paths.items()if k.endswith('/'+suffix)))for suffix in ('stdout','root-output')]==[(50,326100),(48,7354)]
 for label,obs in selected['commands'].items():
  assert len(obs)==6 and len({x['source_trace']for x in obs})==1 and obs[0]['source_trace']in traces['ordinary'][label]['children_raw_traces_sha256']
  assert [x['name']for x in obs]==['generated.rs','generated_phf.rs','generated.rs','generated_phf.rs','zipped_typeshed.zip','zipped_typeshed.zip']
  assert all(obs[i]['open_line']<obs[i]['close_line'] for i in range(6))
  assert all(obs[i]['close_line']<obs[i+1]['open_line']for i in range(5))
  for n,record in selected['files'].items():
   assert record['dep_info'] and all(x['algorithm']=='blake3'and x['bytes']==record['bytes']for x in record['dep_info'])
   for k,o in zip((16384,65536),[x for x in obs if x['name']==n]):
    assert o['requests']=={str(k):(record['bytes']+k-1)//k+1}
 for profile in profiles.values():
  assert profile['normal_termination'] and profile['events']=='events: Ir' and profile['executed_ir']+1==profile['last_totals_ir']
  for q in profile['functions'].values():
   assert q['inclusive_incoming']==sum(x[1]for x in q['incoming'].values())==q['local_cost']+sum(x[1]for x in q['outgoing'].values())
 observed=profiles['ordinary']['functions'];dig=observed['cargo::compiler::fingerprint::worktree::result_digest']['inclusive_incoming'];full=profiles['ordinary']['last_totals_ir'];assert dig==31657779 and full==313383176
 assert source['cargo_distinct_live_or_pr_heads']==287
 for name in ('result_digest','hash_tree','hash_file','load_script_result'):
  assert len({v[name]['sha256']for v in source['source_blobs'].values()if name in v})==1
 sync=read('synchronized.json');prods=commands['ordinary']['program_artefacts'];new_meta='58735d88ceda76a52da8f24e204d207c188d0d1699310be958f7d917f9c3f7a3'
 for direction,q in sync.items():
  assert q['terminal']and q['same_mtime']and q['differing_bytes']==[10,5519002]and q['zip_size']==5577690 and q['commands'][0]['dirty']==[]
  assert len(q['commands'])==(4 if direction=='first_old_second_changed' else 3)
  for i,v in enumerate(q['commands']):
   changed=v['label']in ('between','holding_changed')
   assert v['rc']==0 and v['artifacts']==182 and v['dirty']==(['ty_vendored']if i else [])
   if i<2:assert len(v['hook_log'])==2 and v['hook_log'][0].endswith('mutated 0')and v['hook_log'][1].endswith(f'mutated {int(i==1)}')
   else:assert not v['hook_log']
   assert v['zip']==q['zip_changed'if changed else'zip_old']
   for p in v['products']:
    count=2 if p['file']=='.rlib'else 1
    assert p['changed_zip']==count*changed and p['old_zip']==count*(not changed)
    if p['file']=='.rmeta':assert p['sha256']==(new_meta if changed else prods['.rmeta'])
 plan=read('leaf-cost-plan.json');r=read('leaf-cost-results.json');assert r['terminal']and sha(D/'leaf-cost-plan.json')==r['plan_sha256']and sha(D/'reproduce/leaf-cost.c')==plan['source_sha256']
 assert r['overlap']=={n:{'bytes':v['bytes'],'sha256':v['sha256']}for n,v in selected['files'].items()} and r['ending_inputs']=={n:v['sha256']for n,v in r['overlap'].items()}
 total=sum(v['bytes']for v in r['overlap'].values());assert total==7918933
 assert r['cpu']==28 and r['start_load'][0]<2 and r['memory_available']>10*2**30
 orders=['raw-copy']*12+['copy-raw']*12;random.Random(plan['schedule_seed']).shuffle(orders);assert plan['orders']==orders and len(r['slots'])==48
 cds={c['label']:c for c in r['controls']};base=cds['original']['raw_blake3'];assert base==[selected['files'][n]['dep_info'][0]['digest']for n in ('generated.rs','generated_phf.rs','zipped_typeshed.zip')]
 assert cds['different']['raw_blake3']==cds['changed']['raw_blake3']!=base and cds['reverse']['raw_blake3']==base
 assert [cds[l]['changed_copy_paths']for l in ['original','different','reverse','changed']]==[0,1,1,0]
 diffs=[];slots=r['slots']
 for i,order in enumerate(orders):
  pair=slots[2*i:2*i+2];assert [x['arm']for x in pair]==order.split('-')
  for j,x in enumerate(pair):
   assert (i,j)==(x['block'],x['slot'])and x['raw_blake3']==base and x['copy_misses']==0 and x['read_bytes']==2*total and x['ns']>0 and x['peak_saved_bytes']==(5577690 if x['arm']=='copy'else 0)
  rr={x['arm']:x for x in pair};diffs.append(rr['copy']['ns']-rr['raw']['ns'])
 for arm in ['raw','copy']:
  assert statistics.median(x['ns']for x in slots if x['arm']==arm)==r['median_ns'][arm] and statistics.median(x['minflt']for x in slots if x['arm']==arm)==r['median_minor_faults'][arm]
 assert statistics.median(diffs)==r['median_paired_delta_ns'] and sum(x<0 for x in diffs)==r['copy_favorable']
 return {'ordinary_full_command_median_ms':statistics.median(ordinary_times)/1e6,'fully_fresh_artifacts':182,'physical_output_bytes_per_first_and_second_read':total,'two_script_generations_hashing_pct_ir':round(100*dig/full,3),'changed_zip_cases':2,'raw_ms':r['median_ns']['raw']/1e6,'copy_ms':r['median_ns']['copy']/1e6,'paired_extra_ms':r['median_paired_delta_ns']/1e6,'copy_quicker':r['copy_favorable'],'pairs':len(diffs)}
if __name__=='__main__':print(json.dumps(verify(),sort_keys=True))
