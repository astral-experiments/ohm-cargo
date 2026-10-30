"""Reopen absolute counts and both failed gates. No paired estimate is produced."""
from pathlib import Path
from collections import Counter
import hashlib,json,gzip,re
p=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def j(n):
 b=(p/n).read_bytes()
 return json.loads(gzip.decompress(b)if n.endswith('.gz')else b)
def sig(x):return sha(json.dumps(x,sort_keys=True,separators=(',',':')).encode())
a=j('absolute-processes.json.gz');v=j('physical-inputs.json.gz');s=j('argv-shape.json');t=j('absolute-terminal.json');r=j('primary-rejection.json');prior=j('initial-plan.json')
assert t['primary_effects_interpreted']==t['diagnostic_effects_interpreted']==r['interpreted_primary_results']==0 and r['passed']is False
assert t['absolute']==sha(gzip.decompress((p/'absolute-processes.json.gz').read_bytes())) and t['unmatched_inputs']==sha(gzip.decompress((p/'physical-inputs.json.gz').read_bytes()))
assert t['primary_rejection']==sha((p/'primary-rejection.json').read_bytes()) and r['sources']['diagnostic-v2/registration.json']==v['registration']==sha((p/'diagnostic-plan.json').read_bytes())
assert r['sources']['ops/plan-counter.json']==sha((p/'initial-plan.json').read_bytes())
assert r['expected_literal_argv']==1 and r['observed_literal_argv']==2 and len(set(s['by_phase'].values()))==2
assert s['same_after_only_dir_substitution']and s['count']==len(s['positions'])==63 and s['unique_tokens']==214
assert Counter(n for ix,n in s['positions'])=={'out-dir':1,'extern':16,'search':46};assert len(set(s['sizes'].values()))==1
assert a['source']=={'R':prior['raw'],'K':prior['source']} and a['roles']['R']['standard_library']==a['roles']['K']['standard_library'] and len(a['roles']['R']['standard_library'])==53
assert a['counts']=={'blocks':2,'native_receipts':52,'profiles':8,'stock_wild_during_measured_builds':0} and a['provenance']['calibration']['deltas']==[0,300000,0,300000,300000,0]
cases=v['cases']; assert len(cases)==8 and sum(len(sy['phases']) for sy in cases.values())>=24
for slot,d in cases.items():
 assert len(d['externs'])==16 and len(d['native'])==1 and len(d['dependency_candidates'])==86 and len(d['search_names'])==45
 assert set(d['native_roles'])=={'native','dependency'}
 for ph,x in d['phases'].items(): assert x['typed']==97 and x['verified_extern_claims']==16 and x['ELF']==v['genuine_verdicts'][x['state']][0] and x['objects']==v['genuine_verdicts'][x['state']][1]
for field in ('externs','native','dependency_candidates','search_names'):
 keys=set.union(*(set(d[field])for d in cases.values()));deltas=[]
 for key in keys:
  groups={}
  for sk,sd in cases.items():groups.setdefault(sig(sd[field].get(key)),[]).append(sk)
  expect=v['provider_comparison'][field][key]; assert len(groups)==expect['unique'] and {k:sorted(w)for k,w in groups.items()}=={k:sorted(w)for k,w in expect['physical_groups'].items()}
  if len(groups)>1:deltas.append(key)
 assert sorted(deltas)==sorted(v['differing'][field])
assert sorted(v['differing']['externs'])==['get_size2','ruff_python_ast','ruff_python_trivia','ruff_text_size','unicode_names2']
assert len(v['differing']['dependency_candidates'])==22 and not v['differing']['search_names'] and not v['differing']['native']
absrows=[]
for role in 'RK':
 assert a['roles'][role]['driver']==prior['levels'][role]
 for block in (1,2):
  slot=f'pair-{block}-{role}'
  for phase,state in [('edit-B','C'),('restore-B','B')]:
   x=a['rows'][slot][phase];ref=a['refs'][role+'/'+state]
   assert x['Ir']>0 and x['ELF']==ref['ELF']==cases[slot]['phases'][phase]['ELF'] and x['verdict']==ref['verdict'] and x['native_objects']==ref['native_objects']['ruff_python_parser']
   assert x['argv']==x['native_argv_sha']==s['by_phase'][slot+'/'+phase]==v['actual_argv_sha256'][role]
   pid=x['PID']; assert set(x['raw_sha'])=={'counts.json',f'rustc.{pid}.argv',f'rustc.{pid}.fds',f'rustc.{pid}.jobserver',f'output.{pid}.{pid}.gz',f'valgrind.{pid}.{pid}.gz'} and len(set(x['jobserver']))==2
   assert all(n>0 and re.fullmatch('[a-f0-9]{64}',h)for n,h in x['raw_sha'].values())
   absrows.append({'image':role,'block':block,'state_transition':phase,'absolute_Ir':x['Ir'],'actual_pid':pid})
assert len(set(x['actual_pid']for x in absrows))==8
out={'registered_primary_passed':False,'strict_provider_diagnostic_passed':False,'paired_effects_interpreted':0,'absolute_processes':absrows}
if (p/'result.json').is_file():assert j('result.json')==out
print(json.dumps(out,sort_keys=True,indent=2))
