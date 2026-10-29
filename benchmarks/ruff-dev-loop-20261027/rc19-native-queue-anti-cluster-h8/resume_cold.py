"""Consume the already-built empty receiver and finish only the two originally unexecuted restores."""
from pathlib import Path
from collections import Counter
import hashlib,json,os,sys,traceback
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_physical as r
from campaign_physical import *
cont=J/'safety-continuation-v1'
hashes={'events.json':'a654b0112ba1d2170fb7217f663b02fe819372dcd1cc3f131f1cbac370476326','cargo.stdout':'7647ef9979a0b272c3aa2f9ce568887b988ca2a4ab8dff4ab5b1e335b3a33408','cargo.stderr':'e1f71299ac507f09acbac92dd8619942d5c9359d16bae8ce592daa1cd8b37314'}
def signature(err,i):
 lines=err.read_bytes().splitlines();point=b'628:9:'if i==1 else b'657:5:'
 blocks=[lines[j+1:j+4]for j,line in enumerate(lines)if b'panicked at crates/ty_server/tests/e2e/notebook.rs:'+point in line]
 assert blocks and all(v==blocks[0]for v in blocks)
 assertion,left,right=blocks[0];assert assertion.startswith(b'assertion `left == right` failed')and left.startswith(b'  left: ')
 if i==1:assert b'expected no hover at Position { line: 0, character: 1 }'in assertion and b'Literal[1]'in left and right==b' right: None'
 else:assert b'line: 3, character: 1'in left and b'line: 3, character: 6'in left and right==b' right: []'
 return hashlib.sha256(b'\n'.join(blocks[0])).hexdigest()
def main():
 locks=r.stage();cont.mkdir();r.REPORT=cont
 d=REPORT/'empty-edited-clean';art=cont/'empty-edited-clean';art.mkdir()
 auth=c.read(J/'continuation-grant.json');assert auth['registration']=='f8208b91eb7765ad9f88f0d6d8c88b71b8d63091'
 assert (J/'launches/native-series/exit').read_text().strip()=='1'
 assert c.sha(J/'first-native-failure.txt')=='e5eedbe656f8ee7df00587a86c964dd42af3297871dbababc3d428b323e21f8d'
 assert c.sha(REPORT/'all-pairs.json')=='219f405547917611291d77c05f07cb561fae1ab41c98450c340f9af2bd940087'
 assert all(c.sha(d/k)==h for k,h in hashes.items())
 z=c.read(d/'events.json');assert z['root_exit']==0 and len(z['process_exit'])==len(set(x['pid']for x in z['events']))
 bad=[x for x in z['events']if z['process_exit'][str(x['pid'])]!=0]
 b,=bad;assert (b['role'],b['argv'][1:],b['argv_sha256'],z['process_exit'][str(b['pid'])])==('gcc',['-?'],'1b4cdf07fc751121ee9836e46d888fe05a40a9e830145c9620c45883370154d2',1)
 assert list(z['process_exit'].values()).count(1)==1 and set(z['process_exit'].values())=={0,1}
 counts=dict(Counter(x['role']for x in z['events']));assert counts=={'cargo':1,'rustc-query':29,'rustc-full':303,'gcc':51,'collect2':48,'stock-wild':48}
 for e in z['events']:
  raw=b'\0'.join(os.fsencode(v)for v in e['argv'])+b'\0';assert e['argv_sha256']==hashlib.sha256(raw).hexdigest()
 out=[json.loads(x)for x in (d/'cargo.stdout').read_bytes().splitlines()];assert out[-1]=={'reason':'build-finished','success':True}
 us=[u for u in out if u.get('reason')=='compiler-artifact'];u,=[u for u in us if u['target']['name']=='e2e'and u['target']['kind']==['test']and Path(u['manifest_path']).parent.name=='ty_server']
 logical=Path(u['executable']);st=state('clean');f=st/logical.relative_to(R)
 assert not f.is_symlink()and f.is_file()and f.name=='e2e-252695ecce9610da'and f.stat().st_size==213323448 and c.sha(f)=='f6de480999a7ceadb579e80ddabdbc3127127d15be690228c3cedfce306569ae'
 links=[(x['role'],x)for x in z['events']if x['out']and Path(x['out']).name==f.name];assert [k for k,_ in links]==['gcc','collect2','stock-wild']
 for _,e in links:assert f.samefile(st/Path(e['out']).relative_to(R))and z['process_exit'][str(e['pid'])]==0
 listing=[logical,'--list','--format','terse'];cases=('notebook::hover_past_end_of_cell','notebook::inlay_hints_range_past_end_of_cell')
 elicited={};signed={}
 save(art/'before.json',{'original':hashes,'existing_executable':c.sha(f),'existing_executable_len':f.stat().st_size,'existing_source_and_worker_sha256':c.sha(J/'run_physical.py'),'first_exception':c.sha(J/'first-native-failure.txt'),'six_pairs':c.sha(REPORT/'all-pairs.json'),'cold_input_target':'ty_server:e2e','cold_unit_name':f.name,'physical_counts':counts,'complete_elf_link_chain':[(k,e['argv_sha256'])for k,e in links],'sole_gcc_probe':{'argv':['cc','-?'],'hash':b['argv_sha256'],'exit':1},'authorized_sha256':c.sha(J/'continuation-grant.json')})
 for i,argv in enumerate([listing,*([logical,'--exact',k,'--test-threads=1','--nocapture']for k in cases)]):
  so=art/f'test-{i}.stdout';se=art/f'test-{i}.stderr'
  with so.open('xb')as sout,se.open('xb')as serr:rc=run(st,'A',argv,edited=True,stdout=sout,stderr=serr,timeout=120).returncode
  raw=so.read_bytes();assert rc==(101 if i else 0)
  if not i:assert c.sha(so)=='e3254bff0fba6072df809c053ef4e7d7b6490d144568bf3fb4cd6916bd4db316'and len(raw.splitlines())==200
  else:
   assert b'1 failed;' in raw and b'199 filtered out'in raw and os.fsencode('test '+cases[i-1]+' ... FAILED')in raw
   sig=signature(se,i);assert all(signature(REPORT/f'edit-{a}'/f'test-{i}.stderr',i)==sig for a in 'AB')
   signed[cases[i-1]]=sig
  elicited[str(i)]={'exit':rc,'stdout':c.sha(so),'stderr':c.sha(se)}
 cold={'units':len(us),'fresh':sum(u['fresh']for u in us),'runtime':elicited,'counts':{k:v for k,v in counts.items()if k!='rustc-query'},'e2e':{'bytes':f.stat().st_size,'sha':c.sha(f),'fields':elf.normalize(f)},'true_assertions':signed,'original_exec':hashes['events.json'],'gcc_feature_probe_only':True}
 save(art/'control.json',cold);print('same existing empty ELF, 200 entries; exact two assertion payloads match both edited arms',flush=True)
 restores=[r.safety(a,'restore')for a in 'AB'];r.matched_transition(*restores,'restore');edits=[c.read(REPORT/('edit-'+a)/'control.json')for a in 'AB']
 for i in range(2):assert restores[i]['e2e']['fields']['normalized']==c.read(HISTORIC/'qualification.json')['e2e']['fields']['normalized']
 for a in 'AB':
  original=c.read(REPORT/'signed-workspace.json');rr=restores[0 if a=='A'else 1]['workspace']
  assert set(rr)==set(original)
  # Even restored units may be relinked. Recheck all other bytes for nontrivial differences.
  base=GOLD
  for f,v in rr.items():
   if v!=original[f]:
    rel=Path(f).relative_to(R);assert elf.normalize(state(a)/rel)['normalized']==elf.normalize(base/rel)['normalized'],('restored full workspace bytes',a,f)
 compare={'targeted_empty':cold['e2e'],'full_edited':edits[0]['e2e'],'raw_equal':edits[0]['e2e']['sha']==cold['e2e']['sha'],'normalized_equal':edits[0]['e2e']['fields']['normalized']==cold['e2e']['fields']['normalized'],'clean_target':f.name if not isinstance(f,str)else 'e2e-252695ecce9610da','warm_target':c.read(HISTORIC/'qualification.json')['e2e']['basename'],'meaningful_assertions':signed}
 save(cont/'consumer-domains.json',compare)
 rows=c.read(REPORT/'all-pairs.json');result=r.screen.verdict(rows)
 save(cont/'terminal.json',{'native_screen':result,'groups':{'large':14,'small':23},'end_capacity':free(),'frozen_source':c.sha(J/'source-final.json'),'diagnostic':c.sha(REPORT/'instrumented/substitutions.json'),'raw_pair_sha':c.sha(REPORT/'all-pairs.json'),'safety':{k:c.sha(p/'control.json')for k,p in [('edit-A',REPORT/'edit-A'),('edit-B',REPORT/'edit-B'),('empty-edited-clean',art),('restore-A',cont/'restore-A'),('restore-B',cont/'restore-B')]},'continuation':{'existing_artifact_only':True,'no_resampled_commands':True,'original_failed_collector':c.sha(J/'first-native-failure.txt'),'authorization':c.sha(J/'continuation-grant.json'),'actual_original_raw':hashes,'consumer_domains':c.sha(cont/'consumer-domains.json')}})
 print('COMPLETE',result,flush=True)
if __name__=='__main__':
 try:main()
 except BaseException:(J/'first-continuation-failure.txt').write_text(traceback.format_exc());raise
