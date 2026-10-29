"""Validate both unmodified compiler publications against their own archived-input evidence."""
from pathlib import Path
import argparse,hashlib,json,re

def get(root,name):return json.loads((root/name).read_bytes())

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def verify(root):
 s=get(root,'summary.json');c=get(root,'comparison.json');pre=s['preflight'];assert s['protocol_git']=='a644772c28607282fc06bb7c72f08225ea04f0a6' and s['protocol_manifest']=='327f73c1f3d1e372358ea209223ad992087c2d54e093a2440d75e4d7eb2336f1'
 assert s['original_execution_exit']==1 and 'target is busy' in s['original_first_error'] and s['terminal']==0 and s['phase_status']=={'A':'verified','B':'verified'} and s['scored_measurements']==0
 assert s['continuation']['old_native_execution_replacements']==0 and s['native_execution_order']==c['order']==['B','A'] and c['continued_only_unattempted_calls'] and c['original_run_exit']==1
 assert pre['typed_units_verified']==248 and pre['actual_declared_files']==452 and pre['held_expected']==c['immutable_initial']=='3dc4253060abc0704b18356acd2bb134383b88538a3b0642a1ad97307ffaeaf0'
 assert pre['observer_launches']['initial_from_unprivileged_setpriv']==127 and pre['observer_launches']['actual_owner_launch']==0
 assert {p[0]['id'] for p in pre['snapshots'].values()}=={262,263};assert len({p[0]['UUID']for p in pre['snapshots'].values()})==2 and len({p[0]['Parent UUID']for p in pre['snapshots'].values()})==1
 assert all(pre['snapshots'][a][0]['readonly']=='ro=false' for a in 'BA')
 assert pre['cargo_a']=='6aaa263e68d2d77aeb8977166f9744f1fa8e0ea4df3216fe516355be68517bac' and pre['cargo_b']=='f5523b530225724e91671630257c11b6ba58d18800736a70f6cbe91a31ccd409'
 for label,stdout in [('original','1 SIM222\n'),('historical-parent','2 SIM222\n3 SIM222\n4 SIM222\n')]:
  ref=pre['empty_native_references'][label];assert ref['initial_fresh']==[0,248] and ref['caller']['exit']==0 and ref['caller']['stdout']==stdout and ref['caller']['linter']==ref['rlib_sha256']
 for name in ('donor-custody.json','continued-donor-custody.json'):
  d=get(root,name);assert set(d['tree'])=={'pristine','seed'}
  for v in ('pristine','seed'):
   assert d['before'][v]['readonly']==d['after'][v]['readonly']=='ro=true' and {k:v1 for k,v1 in d['before'][v].items() if k!='Generation'}=={k:v1 for k,v1 in d['after'][v].items() if k!='Generation'}
 assert get(root,'donor-custody.json')['tree']==get(root,'continued-donor-custody.json')['tree']
 rows={};norm={}
 for arm in ('B','A'):
  o=get(root,arm+'/observation.json');q=get(root,arm+'/reconstruction.json');i=get(root,arm+'/acquired.json');t=o['trace'];u=o['current'];se=o['start'];n=int(arm=='B');digest=q['product_sha256']
  assert o['status']=='verified' and q['arm']==arm and se['sha']==u['old_sha']==pre['held_expected'] and se['declared']==452 and se['uid']==1000 and se['affinity']==list(range(8))
  assert u['old']==u['old_held_after']==se['prior'] and u['new'][:2]!=u['old'][:2] and u['repeat']==u['new'] and u['new'][2]==q['bytes']==101719820
  assert c['compiled_archives'][arm]==q['oracle_sha256']==digest==u['new_sha']==o['source_files']['published.rlib']['sha256'];assert q['whole_file_equal'] and digest!=u['old_sha']
  assert o['source_files']['published.rlib']['size']==q['bytes'] and q['llvm_ar_sha256']=='eedd2efbdee80acf60e17e10adeddf31be0347226245f935be95efa3ae00ec79'
  assert t['terminal']==[0,1,258,1,n] and q['successful_target_clones']==len(t['clone'])==n and q['capture_sha256']==t['raw']['sha256']==u['capture']==c['capture_sha'][arm]
  assert len(t['publication'])==1 and t['publication'][0]['temporary']=='tmp.a';assert all(cl['return']==0 and cl['same_held_origin'] and cl['is_target_temporary'] and cl['line']<t['publication'][0]['line'] for cl in t['clone'])
  assert len(i)==len(q['member_inputs'])==258 and [r['ordinal']for r in i]==list(range(258)) and len({r['name']for r in i})==258 and [r['name']for r in i[:2]]==['lib.rmeta','lib.rmeta-link']
  assert all(re.fullmatch(r'ruff_linter-[a-z0-9]+\.[a-z0-9]+\.[a-z0-9]+\.rcgu\.o',r['name'])for r in i[2:]);assert all(r['dev']>0 and r['ino']>0 and r['observed_size']==r['size'] and len(r['original_trace_line_sha256'])==64 for r in i)
  assert [{k:r[k]for k in ('name','size','sha256')}for r in i]==q['member_inputs']
  members=q['archive_members'];assert len(members)==260 and [r['name']for r in members[:2]]==['/','//'];assert [{k:r[k]for k in ('name','size','sha256')}for r in members[2:]]==q['member_inputs']
  offset=8
  for memb in members:
   assert memb['offset']==offset+60 and memb['size']>0;offset+=60+memb['size']+(memb['size']%2)
  assert offset==q['bytes'];assert set(q['controls'])=={'object-name','metadata-byte'} and len({digest,*q['controls'].values()})==3
  comp=q['compiler_invocations'];roots={v['argv']['sha256'] for v in t['execs'] if v['actual_compiler']};assert roots=={v['raw_sha256']for v in comp}
  norm[arm]=sorted([v['target'],v['without_origin_sha256']]for v in comp if v['role']=='full');assert norm[arm]==c['normalized_full'] and len(norm[arm])==10 and sorted(u['dirty'])==[v[0]for v in norm[arm]]
  assert len([v for v in comp if v['role']=='query'])<=n and all(x['executable'] not in ('gcc','cc','collect2','ld.bfd','wild','wild-linker')for x in t['execs']);exits=dict(t['exits']);assert all(exits[v['pid']]==0 for v in t['execs']if v['actual_compiler'])
  assert u['fresh']==[238,248] and u['declared_path_count']==452 and u['repeat_roles']==['cargo'] and o['repeat']['root_exit']==0 and [e[0]for e in o['repeat']['events']]==['cargo'] and set(o['repeat']['process_exit'].values())=={0}
  ca,cr=(o['caller_'+r] for r in ('actual','reference'));assert ca==cr;rc=ca['native_result'];assert rc['linter']==digest and rc['exit']==0 and rc['stdout']=='2 SIM222\n3 SIM222\n4 SIM222\n' and ca['retained_program']['sha256']==rc['executable'] and ca['compiler_stderr']['size']==0 and ca['retained_program']['size']>0
  bind=o['native_input_binding']['reference'];assert bind['fresh_private_namespace']!=bind['enclosing_namespace'] and bind['declared_path_inside']==bind['ref_file'] and bind['real_uplift'][:2]!=bind['ref_file'][:2] and bind['source_sha256']==digest
  rows[arm]={'bytes':q['bytes'],'current':digest,'whole_file_match':True,'opened_files':len(i),'archive_members':len(members),'eligible_clone_count':n,'full_rustc':len(norm[arm]),'query':sum(v['role']=='query' for v in comp),'repeat_full':0,'caller':rc['executable'],'changed_controls':len(q['controls'])}
 assert norm['A']==norm['B']
 return {'arms':rows,'original_teardown_exit':1,'authorized_pending_continuation_exit':0,'order':['B','A'],'scored_samples':0}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path,nargs='?',default=Path(__file__).resolve().parent);args=p.parse_args();print(json.dumps(verify(args.directory),sort_keys=True,indent=2))
