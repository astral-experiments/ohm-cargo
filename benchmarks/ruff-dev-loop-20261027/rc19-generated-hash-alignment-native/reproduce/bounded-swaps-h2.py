from pathlib import Path
import io,os,runpy,shutil,struct,subprocess,sys,zipfile
w=runpy.run_path(str(Path.home()/'.cache/ohm-script-hash-wall-rc19-v1/host-wall-v2.py'));globals().update({k:w[k] for k in ('D','C','images','switch','args','call','inventory','sha','save','caller','project')});x=D/'bounded-ptrace-adversaries-v4';x.mkdir();hook=x/'trace';subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror','-o',hook,D/'between-ptrace.c'],check=True);allrows={}
for arm in 'AB':
 switch(arm);orig=x/(arm+'-ordinary');orig.mkdir();
 for sub in ('target','shared','home'):(C/sub).rename(orig/sub)
 try:
  armsets={}
  for direction in ('forward','reverse','mode'):
   assert (C/'marker').read_text()==arm and shutil.disk_usage(D).free>11*2**30
   for name in ('target','shared','home'):subprocess.run(['cp','-a','--reflink=auto',orig/name,C/name],check=True);assert (C/name).stat().st_ino!=(orig/name).stat().st_ino
   paths=list((C/'target').rglob('zipped_typeshed.zip'));assert len(paths)==1,paths;p=paths[0];before=p.stat();old=p.read_bytes();changed=bytearray(old);end=old.rfind(b'PK\x05\x06');cd=struct.unpack_from('<I',old,end+16)[0];assert old[cd:cd+4]==b'PK\x01\x02';loc=struct.unpack_from('<I',old,cd+42)[0];assert old[loc:loc+4]==b'PK\x03\x04';changed[cd+12]^=1;changed[loc+10]^=1;changed=bytes(changed);assert [(i,v)for i,(u,v)in enumerate(zip(old,changed))if u!=v] and len(old)==len(changed)
   for b in (old,changed):assert zipfile.ZipFile(io.BytesIO(b)).read('stdlib/ty_extensions/pydantic.pyi')==(project/'crates/ty_vendored/ty_extensions/pydantic.pyi').read_bytes()
   def write(f,b):f.write_bytes(b);os.chmod(f,before.st_mode&0o7777);os.utime(f,ns=(before.st_atime_ns,before.st_mtime_ns));assert f.stat().st_size==len(old) and f.stat().st_mtime_ns==before.st_mtime_ns
   phases={'forward':['initial','mutate','hold','restore'],'reverse':['initial','mutate','hold'],'mode':['initial','change_mode','mode_hold','mode_restore']}[direction];q=[]
   for label in phases:
    r='bounded-ptrace-'+arm+'-'+direction+'-'+label;cmd=[*args,'--message-format=json'];log=x/(r+'.events')
    if label=='mutate':
     alt=C/'target/.ohm-qa-replacement';write(alt,changed if direction=='forward'else old)
     if direction=='reverse':write(p,changed)
     cmd=[str(hook),str(C/'sdk/bin/cargo'),str(p),str(alt),str(log),*cmd]
    if label=='restore':write(p,old)
    if label=='change_mode':os.chmod(p,(before.st_mode&0o7777)^0o100)
    if label=='mode_restore':os.chmod(p,before.st_mode&0o7777)
    if label=='initial':cmd=[str(hook),str(C/'sdk/bin/cargo'),str(p),'-',str(log),*cmd]
    d=call(r,cmd);rdata,rows=inventory(d,False);events=log.read_text().splitlines()if log.exists() else [];assert label!='mutate' or (len(events)>=2 and sum('mutated 1'in v for v in events)==1),events
    act={};expected=changed if direction=='forward' and label in ('mutate','hold')else old
    for name in rdata['products']:
     data=Path(name).read_bytes();ext=Path(name).suffix;act[ext]={'old':data.count(old),'changed':data.count(changed)};assert data.count(expected)==(2 if ext=='.rlib'else 1)and data.count(changed if expected==old else old)==0,(r,act)
    dirty=[a['target']['name']for a in rows if a['reason']=='compiler-artifact'and not a['fresh']];assert label!='mutate'or dirty==['ty_vendored'],(label,dirty)
    if label=='initial':assert rdata['fresh']==182,(r,rdata['fresh'])
    q.append({'phase':label,'native_outputs':rdata['products'],'program':caller(d,rows),'dirty':dirty,'mode':p.stat().st_mode&0o7777,'zip':sha(p),'events':[i.split(' mutated ')[-1]for i in events],'archive_members':act,'compiler_hash':images['arms'][arm]['image'],'generation':rdata['generations']});print(arm,direction,label,dirty,flush=True)
   armsets[direction]=q;dst=x/(arm+'-retained-'+direction);dst.mkdir()
   for sub in ('target','shared','home'):(C/sub).rename(dst/sub)
   # The full output, generation and program digests are sealed per phase before this private, reproducible copy is reclaimed.
   save(dst/'phase-outcomes.json',q)
   for sub in ('target','shared','home'):
    item=dst/sub; assert item.parent==dst and item.is_dir() and not item.is_symlink();shutil.rmtree(item)
  allrows[arm]=armsets
 finally:
  failed=x/(arm+'-interrupted');failed.mkdir()
  for sub in ('target','shared','home'):
   if (C/sub).exists():(C/sub).rename(failed/sub)
   (orig/sub).rename(C/sub)
for k in allrows['A']:
 for r,s in zip(allrows['A'][k],allrows['B'][k]):assert {n:v for n,v in r.items()if n not in ('compiler_hash','native_outputs')}=={n:v for n,v in s.items()if n not in ('compiler_hash','native_outputs')},(k,r['phase'])
save(x/'complete.json',{'terminal':True,'rows':allrows,'hook':sha(hook)});print('admitted',sha(x/'complete.json'))
