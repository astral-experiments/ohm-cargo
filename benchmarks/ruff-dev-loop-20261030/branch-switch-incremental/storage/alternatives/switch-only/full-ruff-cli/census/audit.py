"""Reopen genuine, explicitly separated release-style storage phases and their physical samples."""
from pathlib import Path
import collections,copy,gzip,hashlib,importlib.util,json,re,statistics,sys
D=Path(__file__).resolve().parent
def h(b):return hashlib.sha256(b).hexdigest()
def native(p):
 assert p['schema']=='08d49-whole-cli-v1' and p['primary_registration']=='29099ce877f5a6589ae36b6a61bf595b2102e8df2ff9a8c0eba114e5fba53138'
 assert p['category_registration']=='a31ce41abb0f0b2f71bdd588973abe126e074975dfb3d407871605b0213edadb'
 assert p['observed_source']['source']=='08d49cba6aacb0cac27a96eea335ed1c7439f483' and p['observed_source']['product']=='f125d6e661731b07d183b782962044c0b51109cca2badb5cc70ae052550b7388'
 ro=p['read_only_home'];assert ro['enrollment']=='54ffb9a2433e909fff8913c8e0624d81d50cd89a5e26b548945e9aab62a04091' and ro['original_handoff']=='b0858e6fe13d719b93ff642dea5c3edb8b5a11d9a52fdfc315bc6cac2c087aa6' and ro['outside']['digest']=='14d622a63fbd3c77c6ff8fe6e199f5a3c9e9e5c85cd7927bee94e72fbe3b8183'
 parked=ro['closed_original'];assert parked['original_cargo']==parked['original_rustc']==0 and parked['old_children']==[] and parked['retired_with_pidfd']
 assert parked['old_wait']['capacity'][1]<=parked['original_entrance_bytes']==145*2**30 and 140*2**30<parked['host_when_parked'][1]<=145*2**30 and parked['competing_native']==[]
 assert ro['outside']['real_home']==parked['real_home_identity'] and ro['outside']['real_home'][0]!=ro['outside']['scratch_parent'][0]
 assert p['physical_quiet']['competing_native']==[] and p['physical_quiet']['affinity']==list(range(24,28)) and p['physical_quiet']['other_owner_released_physical_quiet']
 assert p['prior_attestation']['previous_public_packet']=='94e6a8aa90d30950b70e8598966f29c55a557c09e40cd2f7e44d9589844022cf'
 orders=['empty-A','first-B','return-A','return-B','unchanged-B'];slots={'off-storage':orders,'on-storage':orders,'off-clean-B':['empty-B'],'on-clean-B':['empty-B']}
 assert set(p['slots'])==set(slots)
 roles=None;per={};sampler_count=0
 for slot,phases in slots.items():
  case=p['slots'][slot];kit=case['kit'];fs=case['graph'];arm=slot.split('-')[0];room=p['room'][slot];en=room['entry'];lo=room['minimum']
  assert len(en)==5 and en[0]>140*2**30+256*2**20 and en[1]>140*2**30 and en[2]>75*2**30 and en[3]>2*2**30+(850*2**20-en[4]) and all(t>n*2**30 for t,n in zip(lo,[140,140,52,2]))
  assert room['sampled_receipt_bytes']<=384*2**20 and room['separate_raw']<=850*2**20
  for mark in ('before','after'):
   mount=case['mount_checks'][mark]
   assert mount['real_home']==ro['outside']['real_home'] and mount['real_scratch']==ro['outside']['scratch_parent'] and mount['writable_HOME_budget']==0 and mount['all_visible_home_mounts_are_ro']
   assert mount['all_observed_aliases'] and all(a[1][1] is True and re.fullmatch('[0-9a-f]{64}',a[0]) for a in mount['all_observed_aliases'])
   assert mount['effective_capabilities']==0 and mount['no_new_privs']==1 and mount['physical_home_available']>140*2**30 and mount['physical_scratch_available']>140*2**30 and mount['separate_namespace']
   assert mount['verified_sdk_roles']==57 and mount['input_file_count']==len(ro['outside']['fixed_inputs'])==11 and mount['outside_input_sha']==ro['outside']['digest']
  assert len(kit)==57 and all(len(v)==6 for v in kit.values()) and fs['output_filesystem']==fs['source_filesystem']=='tmpfs' and fs['source_device']!=fs['output_device'] and fs['source_cap']==6*2**30 and fs['output_cap']==10*2**30
  product=p['source_build_payload'];members=product['native_files'];assert product['complete_product']==p['observed_source']['product'] and product['source']==p['observed_source']['source'] and len(members)==55
  assert set(kit)==set(members)|{'bin/cargo','lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'} and all(kit[k][-1]==digest for k,digest in members.items())
  assert product['complete_build']=='65f7a41f3db3774f958409a5070d24e3ccd8ec75410908d3d48fd3221dadd924' and product['unit_result']=='c0049dada67cf645e2ddebc2ef2f37b29643786d5218d7244b1a1467dd920fdc' and product['run_make_results']=='a9061c18ff8b5ee69050b8cb550555da4db4102abd05adf6674b67746012e6a1'
  if roles is None:roles=kit
  assert roles==kit and kit['lib/librustc_driver-4fa76f30fa0fea85.so'][-1]=='3ad2cc4c6a903ea54ddcf74b4cfb6b0fa48fa67a17c43827f9261c81475c3191'
  assert kit['bin/cargo'][-1]=='1d06626bcef3c5235676ada14f4b7107f56e98aef620f81b0e0c47381dbe0add' and kit['bin/rustc'][-1]=='fb5c1341de5f7ea9350478b52383cb407d6d184bc257e2941ff998fcdec4df18' and kit['lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'][-1]=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
  assert set(case['phase'])==set(phases);prev=0
  for tag in phases:
   v=case['phase'][tag];st=v['settled'];s=v['sampler'];rev=tag[-1]
   assert v['typed']==375 and v['graph']=='38d3fd49b035775102dd433f08a9bbc99dfe7b883e1bbf22f10d91b542433adb'
   assert v['source']=={'A':'b5dba861cc38e3f7fb4524c9ceba3e01a474ea13','B':'7b13f01ba1569887a25670820764b24c206da8e5'}[rev] and v['reader_observed']==('Expr=64 valid=1 rejected' if rev=='A' else 'Expr=56 valid=1 rejected')
   assert set(v['cli_verdicts'])=={'version','source','clean','warning','fixed','recheck','invalid'} and [v['cli_verdicts'][k]['status'] for k in ('version','source','clean','warning','fixed','recheck','invalid')]==[0,0,0,1,1,0,1]
   assert v['raw_exec'] and v['physical_receipt'] and v['typed_receipt'] and re.fullmatch('[0-9a-f]{64}',v['native_end'])
   for n,m in [('ruff','cli'),('reader','reader')]:
    c=v['custody'][n];assert c['origin'] in ('verified-current-object','verified-old-object','verified-new-object') and c['physically_compared'] and c['sha256']==c['retained_bytes']==v[m]['sha256'] and c['size']==v[m]['bytes'] and c['output_inode']>0
   if tag.startswith('empty'):
    assert v['dirty']==375 and [v['physical'][k] for k in ('SDK rustc','stock Wild','build script')]==[379,69,37]
   elif tag.startswith('unchanged'):assert v['dirty']==0 and v['physical']=={}
   else:assert v['dirty']==20 and v['physical']=={'GCC':1,'SDK rustc':20,'stock Wild':1,'collect2':1,'build script':1}
   assert (v['tables']['packed']['unique_inodes']==0)==(arm=='off' or tag.startswith('empty'))
   assert st['all']==st['products']+st['shared']-st['both_roots_same_inode'] and st['all_incremental']==st['incremental_only']+st['incremental_also_named_outside']
   assert s['start']==prev and s['end']==st['all'] and s['max_observed']>=max(prev,s['end']) and s['nominal_interval_ns']==10_000_000
   b=(D/'samples'/(slot+'--'+tag+'.tsv.gz')).read_bytes();raw=gzip.decompress(b);assert h(b)==v['sampler_gz'] and h(raw)==s['raw_sha256']
   rows=[tuple(map(int,l.split())) for l in raw.splitlines()];assert rows[0]==(0,prev) and len(rows)==s['count'] and rows[-1][1]==s['end'] and max(j[1] for j in rows)==s['max_observed']
   gaps=sorted(c[0]-a[0] for a,c in zip(rows,rows[1:]));assert min(gaps)>0 and s['gaps_ns']=={'min':min(gaps),'median':statistics.median(gaps),'p99':gaps[int(.99*(len(gaps)-1))],'max':max(gaps)}
   per.setdefault((arm,rev),[]).append(v);sampler_count+=1;prev=st['all']
 for (_,rev),items in per.items():
  for k in ('cli','reader','source','graph','typed','reader_observed','cli_verdicts'):assert len({json.dumps(v[k],sort_keys=True) for v in items})==1
 assert sampler_count==12
 return {k:{m:p['slots'][m+'-storage']['phase'][k]['settled']['all'] for m in ('off','on')} for k in orders}
def main():
 p=json.loads((D/'observations.json').read_bytes());base=native(p)
 sp=importlib.util.spec_from_file_location('class_audit',D/'verify-file-classes.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
 vals,ers=m.verify(p)
 out={'rechecked_samples':12,'two_cold_control_graphs_plus_two_initial_A_graphs':True,'whole':base,'class_phase_count':len(vals),'class_failures':ers}
 raw={'A':{},'B':{}}
 for rev in raw:
  for arm in ('off','on'):
   v=p['slots'][arm+'-storage']['phase']['return-'+rev]
   raw[rev][arm]={'current':v['cli']['sha256'],'exactly_the_8ea_product':v['cli']==v['prior_actual_hashes']['cli']}
 out['byte_comparison_to_preceding_independent_8ea']=raw
 return out
if __name__=='__main__':print(json.dumps(main(),indent=2,sort_keys=True))
