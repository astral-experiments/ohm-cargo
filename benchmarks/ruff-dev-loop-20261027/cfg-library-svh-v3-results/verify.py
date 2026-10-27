"""Verify each native producer, all source/extern bindings, actual exec receipts and each new ordinary caller."""
from pathlib import Path
import hashlib,json,re,sys
O=Path(__file__).resolve().parent;J=lambda p:json.loads((O/p).read_bytes());H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();plan=J('binding/plan.json');m=J('binding/resolved-input-bindings.json');subject=J('binding/release-binding.json');assert subject['sha256']=='36d1fd142355c3ad9e0ce006c1e92b7e511cba70c431b09eb1e335f572d27d05';assert H(O/'binding/plan.json')=='b626b6198da7c6513b1b8a3917431b90e9dbfe7bcb4e8c801f2296f19c457cd2' and H(O/'binding/resolved-input-bindings.json')==plan['all_source_and_extern_bindings_sha256'];assert H(O/'binding/prior-normal-compiler.json')==plan['prior_direct_command_manifest_sha256']
e={k:hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest() for k,v in m['all_sources_from_authentic_dep_info'].items()};ex=hashlib.sha256(json.dumps({z['name']:z['current_real_sha256'] for z in m['direct_externs']},sort_keys=True).encode()).hexdigest();hfun=lambda z:hashlib.sha256(z.encode()).hexdigest();raw=O/'raw-rmeta';assert all(H(f)==f.stem for f in raw.glob('*.rmeta'));outputs=[];all_full=all_readers=0;program=J('binding/prior-normal-compiler.json')['argv'];complete=J('complete.json');assert len(complete['result'])==4;prior=J('source-manifests.json')
for record in complete['result']:
 b=record['block'];a=record['arm'];g=O/('block-'+str(b))/a;names=['chain-original','chain-edited','chain-restored','empty-edited','empty-original'];arm_hash=subject['sha256'] if a=='candidate' else plan['stock_rustc_driver'];p={}
 for n in names:
  q=json.loads((g/n/'result.json').read_bytes());s=q['source_state'];fin=q['input_bindings'];assert q['returncode']==0 and q['driver_sha256']==arm_hash and q['actual_compiler_argv']==program and fin['sources']==44 and fin['externs']==29;assert fin['source_roster_sha256']==e[s] and fin['direct_extern_roster_sha256']==ex
  assert q['originally_empty_incremental']==(n in ('chain-original','empty-edited','empty-original')) and bool(q['reused_initial_contents'])!=q['originally_empty_incremental'];assert q['header']['public']=='f321b448bc54bd2819e1fe053541ce11' and q['physical_source']['rmeta_sha256']==q['metadata_sha256'] and q['physical_source']['normalized_bytes']==int(prior[s]['bytes']);tr=(g/n/'compiler.exec').read_text();matches=[x for x in tr.splitlines() if 'execve("'+program[0]+'"' in x and re.search(r'= 0$',x)];assert len(matches)==1 and hfun(matches[0])==q['actual_exec_line_sha256'];p[n]=q;all_full+=1
  if b==1 and n in ('chain-edited','empty-edited'):assert (raw/(q['metadata_sha256']+'.rmeta')).is_file()
 names2={'warm-edited':'chain-edited','cold-edited':'empty-edited'};npass=0;bad=[]
 for bn in names2:
  bridge=json.loads((g/('ordinary-bridge-'+bn)/'result.json').read_bytes());assert bridge['ordinary_no_public_hash_option'] and bridge['status']==0 and bridge['producer']==p[names2[bn]]['header']
  for cn in names2:
   q=json.loads((g/('ordinary-caller-'+bn+'-vs-'+cn)/'result.json').read_bytes());assert q['selected_caller_producer']==p[names2[cn]]['header'] and q['same_source_state']=='edited';assert bn!=cn or q['status']==0
   if q['status']==0:npass+=1
   else:bad.append(q['codes']);assert 'E0460' in q['codes'] and bn!=cn
   all_readers+=1
 match=p['chain-edited']['header']['private']==p['empty-edited']['header']['private'];rest=p['chain-restored']['header']['private']==p['empty-original']['header']['private'];assert match==record['same_edited_private'] and rest==record['same_restored_private'];outputs.append([b,a,match,rest,npass,bad])
assert all_full==20 and all_readers==16;print(json.dumps({'validated_producer_invocations':all_full,'validated_new_consumers':all_readers,'observed_block_outcomes':outputs},indent=1))
