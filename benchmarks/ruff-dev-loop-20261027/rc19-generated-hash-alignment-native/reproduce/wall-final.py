"""Source-registered whole-command comparison. Slot capture begins only with a positive published native grant."""
from pathlib import Path
import hashlib,json,math,os,runpy,shutil,subprocess,sys,time,traceback
W=Path.home()/'.cache/ohm-script-hash-wall-rc19-v1';base=W/'host-wall-v2.py';sha256=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
assert sha256(base)=='c8ebf7aa4ac7269614eb6b6e3e5379330d46e684994a31f4d6ec234361962508';v=runpy.run_path(str(base))
D,C,switch,call,qualify,sha,save,read,dg,host,project,env,args,images,P,traces=(v[k]for k in ('D','C','switch','call','qualify','sha','save','read','dg','host','project','env','args','images','P','traces'))
PUBLIC='2d40c0ba8f68ba2bfadc489db876b49f5c442de4';private_role='primary-linux'if 'loader-'in host else 'independent-linux';out=D/'release-native-final';out.mkdir(exist_ok=True);rowspec=('ids','products','zips','checks','generations','reader','source','native_outputs')
def complete_product_map(label):
 raw=(traces/label/'stdout').read_bytes().splitlines();names={n for x in map(json.loads,raw)if x['reason']=='compiler-artifact'for n in x['filenames']};files={}
 for n in sorted(names):
  f=Path(n);assert f.is_file()and any((C/k)in f.parents for k in ('target','shared')),(n,label)
  key=hashlib.sha256(str(f.relative_to(C)).encode()).hexdigest();assert key not in files;files[key]={'sha256':sha(f),'bytes':f.stat().st_size}
 assert len(files)>=182,(len(files),label);return files
def gates(stage):
 record={};immutable=read(D/'fixed-inodes-qa-v1/setup.json');cross=read(D/'same-physical-crossover-v3/complete.json')
 assert sorted((r['seed'],r['image'])for r in cross['crossovers'])==[('A','A'),('A','B'),('B','A'),('B','B')] and all(r['initial']==r['after']and r['fresh']==182 and r['rows']==182 for r in cross['crossovers'])
 oracle=read(W/'bound-output-oracle.json');assert oracle['qualified']and oracle['host']==host
 for arm in 'AB':
  switch(arm);q=qualify(arm,'final-'+stage);expect=read(traces/('secure-pre-'+arm+'.json'));assert all(q[k]==expect[k]for k in rowspec),(stage,arm,'changed independent raw output')
  assert q['rows']==q['fresh']==182 and q['actual_exec']['exe']==images['arms'][arm]['image'];assert q['physical']['actual_registry_cache_reads']=={'/.ohm-git-index-sha1dc-v1/':1,'/.ohm-registry-json-v2/':118}
  for k,f in [('compiler',C/'sdk/bin/rustc'),('driver',next((C/'sdk/lib').glob('librustc_driver-*.so')))]:
   s=f.stat();assert [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]==immutable['identities'][arm][k][1]
  assert {Path(n).suffix:val for n,val in q['products'].items()}==oracle['roles'][arm]
  files=complete_product_map('final-'+stage+'-cache-'+arm);record[arm]={'eligible':True,'full_native':sha(traces/('final-'+stage+'-'+arm+'.json')),'files':files,'metadata':q['products'],'semantics':{k:dg(q[k])for k in('ids','zips','checks','generations','reader','source')},'arm':arm,'cache_hits':q['physical']['actual_registry_cache_reads'],'cargo':q['actual_exec']['exe'],'state_inode':C.stat().st_ino,'cargo_inode':(C/'sdk/bin/cargo').stat().st_ino,'worker_sha256':sha(Path(__file__))}
 assert record['A']['semantics']==record['B']['semantics']
 if stage=='post':
  before=read(out/'pre.json');assert all(before['arms'][a]['files']==record[a]['files']and before['arms'][a]['semantics']==record[a]['semantics']for a in 'AB')
 full={'terminal':True,'host':host,'arms':record,'oracle':sha(W/'bound-output-oracle.json'),'source_plan':PUBLIC,'source':sha(Path(__file__)),'base':sha(base),'same_seed':sha(D/'same-physical-crossover-v3/complete.json'),'images':sha(D/'images.json'),'plan':sha(D/'plan.json')};save(out/(stage+'.json'),full);return full
def score():
 pre=read(out/'pre.json');g=read(D/'grant-final.json');root=D/'score';assert not root.exists()
 assert g['host']==host and g['source_plan']==PUBLIC and g['native_admission']==sha(out/'pre.json')and g['native_release_ref']and len(g['native_release_ref'])==40 and g['worker']==sha(Path(__file__))and g['images']==sha(D/'images.json') and g['grant'] is True
 assert pre['terminal']and os.getloadavg()[0]<2.5 and shutil.disk_usage(D).free>(30 if private_role=='primary-linux'else 10)*2**30
 for k in ('RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUSTC','RUSTFLAGS','LD_PRELOAD','CARGO_LOG'):assert k not in env
 root.mkdir();ledger=root/'slots.jsonl';rows=[];state={'host':host,'plan':sha(D/'plan.json'),'worker':sha(Path(__file__)),'grant':sha(D/'grant-final.json'),'pre_guards':sha(out/'pre.json'),'terminal':False,'begin_load':os.getloadavg()}
 for i,order in enumerate(P['domains'][host]['strata']):
  for j,arm in enumerate(order):
   switch(arm);assert os.sched_getaffinity(0)==set(range(8))and C.stat().st_ino==pre['arms'][arm]['state_inode']and (C/'sdk/bin/cargo').stat().st_ino==pre['arms'][arm]['cargo_inode']
   d=root/f'{i:02}-{j}-{arm}';d.mkdir()
   with (d/'stdout').open('xb')as so,(d/'stderr').open('xb')as er:
    t=time.perf_counter_ns();rc=subprocess.run(args,cwd=project,env=env,stdin=subprocess.DEVNULL,stdout=so,stderr=er).returncode;u=time.perf_counter_ns()
   txt=(d/'stderr').read_text();fresh='Finished 'in txt and 'Compiling 'not in txt and 'error:'not in txt
   row={'stratum':i,'position':j,'arm':arm,'rc':rc,'start':t,'end':u,'elapsed_ns':u-t,'stdout':sha(d/'stdout'),'stderr':sha(d/'stderr'),'fresh_text':fresh};save(d/'clock.json',row)
   with ledger.open('a')as f:f.write(json.dumps(row,sort_keys=True)+'\n');f.flush()
   assert u>t and rc==0 and fresh and (d/'stdout').stat().st_size==0,(i,j,arm,rc,txt[-650:]);rows.append(row)
  assert shutil.disk_usage(D).free>(25 if private_role=='primary-linux'else 9)*2**30
 assert len(rows)==P['commands_per_host']==384;post=gates('post');state.update(rows=rows,post_guards=sha(out/'post.json'),terminal=True,end_load=os.getloadavg());save(root/'terminal.json',state);print('terminal',len(rows),flush=True)
if __name__=='__main__':
 mode=sys.argv[1];assert mode in ('pre','score')
 try:
  if mode=='pre':gates('pre');print('eligible',private_role,sha(out/'pre.json'),flush=True)
  else:score()
 except BaseException:
  (out/('failed-'+mode+'-'+str(time.time_ns())+'.txt')).write_text(traceback.format_exc());raise
