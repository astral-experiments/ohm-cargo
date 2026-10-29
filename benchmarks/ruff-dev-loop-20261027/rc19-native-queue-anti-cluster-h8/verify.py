"""Verify the complete off-clock substitution decision or conservatively report the preserved stop."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,sys
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root))
import screen
arg=Path(sys.argv[1])if len(sys.argv)>1 else root/'evidence.json.gz'
d=json.loads(gzip.decompress(arg.read_bytes()))
assert d['registration']=='f8208b91eb7765ad9f88f0d6d8c88b71b8d63091'and d['source']['head']=='76bec5f0997c6f804234e7351611850ec683e9e4' and d['source']['base']=='235f9228651b74c591e6f62cae4c9b761448dd2d'
assert d['old_qualification']=='50cc91d3be9e76f08d0846d27d6b5c6a61f0d0e413d2e02e32876024111b362e'and d['old_trace']=='c470cdf7dd57f21da992798720b84aa707759fb9115eb3c6b83396d4cd6f5f69'
a=d['image']['A']
for k,v in d['image'].items():
 assert len(v['hash'])==64 and v['version']==a['version']and v['builder_driver']==a['builder_driver']and v['PGO']==a['PGO']and v['commit_stamp']==a['commit_stamp'] and v['src_files']==3108
 for f,x in a['externs'].items():
  y=v['externs'][f];assert y['argv']==x['argv']and set(x['externs'])==set(y['externs'])
  assert all(y['externs'][n]==p for n,p in x['externs'].items()if not(f=='src/bin/cargo/main.rs'and n.endswith('-cargo')))
if d['status']!='terminal':
 assert d['native']is None
 assert d['first_native_exception'] is not None or d['status']=='setup stopped'
 print(d['status'],len(d['recorded_commands']),'observed commands; no timing result');raise SystemExit(0)
assert d['first_native_exception']['sha256']=='e5eedbe656f8ee7df00587a86c964dd42af3297871dbababc3d428b323e21f8d' and set(d['image'])=={'A','B','diagnostic'}
assert d['image']['A']['hash']=='6aaa263e68d2d77aeb8977166f9744f1fa8e0ea4df3216fe516355be68517bac'and d['image']['B']['hash']=='4b5e926d0213c6eaa574a6e8247bb26b773b08848cc9d80dfc8225c5aefab47a'
rows=d['recorded_commands'];pairs=[]
for n in ['qualify-'+a+'-'+str(i)for a in 'AB'for i in (1,2)]+[f'pair-{i:02}-{a}'for i in range(1,7)for a in 'AB']:
 r=rows[n];assert r['units']==619 and r['fresh']==563 and r['root_exit']==0 and r['build_finished']=={'reason':'build-finished','success':True}
 assert {k:v for k,v in r['physical'].items()if k!='rustc-query'}=={'cargo':1,'rustc-full':1,'rustc-link-only':50,'gcc':50,'collect2':50,'stock-wild':50}
 assert len(r['elf50'])==50 and len(r['workspace110'])==110 and len(r['all_rust'])==51 and len(r['temporary_and_native'])==150 and len(r['programs'])==3
 assert r['zip.json']['sha']==d['original_typeshed_sha256']
 assert all(v['exit']==0 for v in r['programs'].values())and r['programs']['listing']['listing_entries']==200
 assert all(v['exact']or v['normalized']==r['elf50'][Path(k).name][1]for k,v in r['workspace110'].items())
for i,order in enumerate(screen.order(),1):
 names=[f'pair-{i:02}-{a}'for a in order]
 p={a:rows[n]['intervals.json']['targets']for a,n in zip(order,names,strict=True)}
 x,y=(rows[n]for n in names);assert x['temporary_and_native']==y['temporary_and_native']and x['all_rust']==y['all_rust']and x['typed_roster']==y['typed_roster']
 assert x['workspace110'].keys()==y['workspace110'].keys()and all(l['raw']==y['workspace110'][k]['raw']or (l['normalized'] and l['normalized']==y['workspace110'][k]['normalized'])for k,l in x['workspace110'].items())
 pairs.append({'order':order,'arms':p})
assert d['native']['native_screen']==screen.verdict(pairs)
z=rows['instrumented']['substitutions.json'];assert z['n']==len(z['exact'])and z['n']>0
for r in z['exact']:
 good=r['chosen'];bad=r['default'];assert bad==r['ready'][-1]and r['jobs']==r['capacity']==len(r['active'])+1==8
 assert good[1]==bad[1]and good[3]<=screen.SMALL and bad[3]>=screen.LARGE and sum(s is not None and s>=screen.LARGE for _,s in r['active'])>=3
 assert good==next(v for v in reversed(r['ready'][:-1])if v[1]==bad[1]and v[3]is not None and v[3]<=screen.SMALL)
for n,codes in [('edit-A',[0,101,101]),('edit-B',[0,101,101]),('empty-edited-clean',[0,101,101]),('restore-A',[0,0,0]),('restore-B',[0,0,0])]:
 r=rows[n]['historical'];assert [r['runtime'][str(i)]['exit']for i in range(3)]==codes and r['runtime']['0']['stdout']=='e3254bff0fba6072df809c053ef4e7d7b6490d144568bf3fb4cd6916bd4db316'
extra=d['post_exception'];assert (extra['first_status'],extra['second_status'])==(1,0)
assert extra['authorization_sha']==d['native']['continuation']['authorization']==extra['cold_before']['authorized_sha256']
assert extra['source_sha']==hashlib.sha256((root/'resume_cold.py').read_bytes()).hexdigest()
assert extra['authorization_sha']==hashlib.sha256((root/'continuation-grant.json').read_bytes()).hexdigest()
assert d['native']['continuation']['no_resampled_commands']and d['native']['continuation']['existing_artifact_only']
assert extra['raw_pair_file']==d['native']['raw_pair_sha']==extra['cold_before']['six_pairs']=='219f405547917611291d77c05f07cb561fae1ab41c98450c340f9af2bd940087'
clean=rows['empty-edited-clean'];proof=extra['cold_before'];domains=extra['consumer_domains']
assert clean['units']==clean['historical']['units'] and clean['fresh']==0 and clean['root_exit']==0 and clean['build_finished']['success']
assert clean['physical']==proof['physical_counts']=={'rustc-full':303,'rustc-query':29,'gcc':51,'collect2':48,'stock-wild':48,'cargo':1}
assert clean['child_return_codes']=={'0':sum(clean['physical'].values())-1,'1':1}
assert proof['sole_gcc_probe']=={'argv':['cc','-?'],'hash':'1b4cdf07fc751121ee9836e46d888fe05a40a9e830145c9620c45883370154d2','exit':1}
assert all(clean['raw_files'][k]==v for k,v in proof['original'].items())
assert len(proof['complete_elf_link_chain'])==3 and [v[0]for v in proof['complete_elf_link_chain']]==['gcc','collect2','stock-wild']
assert domains['targeted_empty']['sha']==proof['existing_executable']=='f6de480999a7ceadb579e80ddabdbc3127127d15be690228c3cedfce306569ae'
assert domains['targeted_empty']['bytes']==proof['existing_executable_len']==213323448
assert domains['clean_target']=='e2e-252695ecce9610da' and domains['warm_target']=='e2e-f978f73ba5a3a2ed'
assert not domains['raw_equal'] and not domains['normalized_equal']
assert domains['meaningful_assertions']==clean['historical']['true_assertions'] and len(domains['meaningful_assertions'])==2
hz=d['diagnostic_id_binding'];assert hz['registered_events']==z['dispatches']==689 and len(hz['substitutions'])==z['n']==21
for k in ['edit','restore']:
 a,b=[rows[k+'-'+u]['historical']for u in 'AB'];cmp=d['transition_comparison'][k]
 assert a['rust']==b['rust']and a['unit_roster']==b['unit_roster']and a['counts']==b['counts']=={'cargo':1,'rustc-full':12,'rustc-link-only':43,'gcc':52,'collect2':52,'stock-wild':52}
 assert set(a['workspace'])==set(b['workspace'])and len(a['workspace'])==cmp['all']==110
 actual={n for n in a['workspace']if a['workspace'][n]!=b['workspace'][n]}
 assert actual==set(cmp['changed'])and len(actual)+cmp['exact']==110
 for n,val in cmp['changed'].items():
  assert val['a']==a['workspace'][n]and val['b']==b['workspace'][n]and val['fields_a']['normalized']==val['fields_b']['normalized']
print('Verified 12 prescribed commands, four original qualifications, full-source edit/clean/restore and',z['n'],'actual substitutions. Mechanism passed:',d['native']['native_screen']['native_mechanism_passed'])
