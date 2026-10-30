"""Verify the closed single-donor compiler-only projection, then derive both registered effects."""
from pathlib import Path
import collections,gzip,hashlib,json,re,statistics
D=Path(__file__).resolve().parent
def h(b): return hashlib.sha256(b).hexdigest()
def sig(o):return h(json.dumps(o,sort_keys=True,separators=(',',':')).encode())
def j(n):return json.loads((D/n).read_bytes())
P=j('registration.json');raw=gzip.decompress((D/'observations.json.gz').read_bytes());o=json.loads(raw);t=j('issuer-verification.json')
assert h(raw)==t['projection'] and h((D/'registration.json').read_bytes())==t['registration']==o['plan'] and t['complete_reread'] and t['pids']==8 and t['cases']==38
assert o['commands']=={'cold_Cargo':2,'direct':38,'profiles':8,'native_flanks':8,'cold_direct':6,'native_Wild_during_profiled_library':0}
assert o['registered_orders']==P['orders']==[['K','R'],['R','K']] and o['calibration']['deltas']==[0,300000,0,300000,300000,0]
roles=o['source'];assert roles['R']['std']==roles['K']['std'] and len(roles['R']['std'])==53
for a in 'RK':
 v=roles[a]
 assert v['source']==P['state_sources'][a] and v['driver'][2]==P['state_sources']['drivers']['RK'.index(a)]and v['cargo']==P['state_sources']['cargo']and v['wild']==P['state_sources']['wild']
 assert v['driver'][0]>0 and v['driver'][1]>0 and re.fullmatch('[0-9a-f]{64}',v['driver_open'])and re.fullmatch('[0-9a-f]{64}',v['version'])
held=o['matched_cargo_donors'];assert set(held)=={'A','B'} and held['A']['ordinary_argv']==held['B']['ordinary_argv'] and held['A']['logical_shape_sha']==held['B']['logical_shape_sha']
for q in held.values():
 assert q['typed']==97 and q['full_native']>=1 and len(q['externs'])==16 and len(q['candidates'])==86 and len(q['listings'])==45 and len(q['native'])>0
 for group in ('externs','candidates','native'):
  for st in q[group].values():assert len(st)==4 and min(st[:3])>0 and re.fullmatch('[a-f0-9]{64}',st[3])
 reconstructed={'externs':q['externs'],'all_discovered_libraries':q['candidates'],'listings':q['listings'],'native':q['native']};assert sig(reconstructed)==q['canonical']
refs=o['empty_refs'];byrole={};total=count=0;seen_pids=set();candidate_states={}
for sl,rows in o['native_cases'].items():
 ref=sl.startswith('ref-');role=sl.split('-')[1]if ref else sl[-1];expected=[sl[-1]]if ref else P['phases'];assert len(rows)==len(expected)
 for n,state in enumerate(expected):
  k=f'{n:02d}-{state}';v=rows[k];c=held['A'if state=='A'else'B'];assert v['tree']==('a880a27e6d496af407411ba47a14279a631b40c3'if state=='C'else c['source']['tree'])
  assert v['actual_inputs']==c['commitment'] and v['canonical_inputs']==c['canonical']and v['environment']==c['captured_environment_sha']and v['argv']==c['ordinary_argv']
  assert v['verdict']==refs[role+'/'+state]==refs[('R'if role=='K'else'K')+'/'+state];vr=v['verdict']
  expected_verdict='Expr='+('64' if state=='A' else '56')+' signed-expression='+('accepted' if state=='C' else 'rejected')
  assert vr['verdict']==expected_verdict and set(vr['objects'])=={'ast','parser'}
  if state in 'AB':assert c['ELF']==vr['ELF'] and c['verdict']==vr['verdict']
  iscount=not ref and n in (4,5)
  if iscount:
   assert v['mode']=='count'and v['Ir']>0 and v['pid'] not in seen_pids;seen_pids.add(v['pid']);f=rows[('%02d'%(n+2))+'-'+state]
   assert f['mode']=='native'and v['flank']==f['result'] and v['argv']==f['argv']and v['verdict']==f['verdict']and len(set(v['jobserver_fds']))==2 and v['jobserver_pipe'].startswith('pipe:[')
   pid=v['pid'];assert set(v['raw'])=={'counts.json',f'output.{pid}.{pid}.gz',f'valgrind.{pid}.{pid}.gz',f'rustc.{pid}.argv',f'rustc.{pid}.fds',f'rustc.{pid}.jobserver'}
   assert all(sz>0 and re.fullmatch('[0-9a-f]{64}',hh)for sz,hh in v['raw'].values())
   byrole[sl,state]=v['Ir'];count+=1
  else:assert v['mode']=='native'
  total+=1
assert count==8 and total==38
cu=json.loads(gzip.decompress((D/'provider-custody.json.gz').read_bytes()));assert cu['closed']==h((D/'issuer-verification.json').read_bytes()) and cu['unique_payloads']>86 and cu['archive_bytes']<cu['original_bytes']<512*2**20 and cu['logical_members']=={'A':88,'B':88}
assert cu['all_other_actual_uninstrumented_full_compiler_processes']==30 and all(v['stock_wild_product']==20 for v in cu['cold_Cargo_native_products'].values())
raw_comparisons={'ast':0,'parser':0}
for sl,phases in o['native_cases'].items():
 for ph,obs in phases.items():
  cc=cu['native_cases'][sl+'/'+ph];assert cc['mode']==obs['mode'] and cc['result']==obs['result'] and (cc['native_tool_observation']=={'rustc':1} if cc['mode']=='native' else cc['native_tool_observation']=={'rustc':1,'stock_wild_product':0})
  if not sl.startswith('ref-'):
   ref=cu['native_cases']['ref-'+sl[-1]+'-'+obs['state']+'/00-'+obs['state']]['raw_rlibs']
   for crate in raw_comparisons:raw_comparisons[crate]+=int(cc['raw_rlibs'][crate]==ref[crate])
assert cu['whole_output_rlib_matches']=={'matches':raw_comparisons,'opportunities':{'ast':32,'parser':32}}

effects={}
for st,label in [('C','first_dirty_edit'),('B','immediate_restore')]:
 blocks=[{'R':byrole[f'pair-{n}-R',st],'K':byrole[f'pair-{n}-K',st]}for n in (1,2)]
 for x in blocks:x['K_minus_R']=x['K']-x['R'];x['K_over_R']=x['K']/x['R']
 raw=sum(z['R']for z in blocks);candidate=sum(z['K']for z in blocks)
 effects[label]={'blocks':blocks,'mean_R':raw/2,'mean_K':candidate/2,'mean_delta':(candidate-raw)/2,'ratio_of_sums':candidate/raw}
summary={'kind':'direct compiler-only, two mirrored blocks, no wall inference','commands':o['commands'],'paired_effects':effects,'absolute_data_and_gates_verified':True}
if (D/'result.json').exists():assert j('result.json')==summary
print(json.dumps(summary,sort_keys=True,indent=2))
