"""Two further independent stock cold state references sharing only compiler files and the path spelling."""
from pathlib import Path
import json,os,runpy,shutil,subprocess
w=runpy.run_path(str(Path.home()/'.cache/ohm-script-hash-wall-rc19-v1/host-wall-v2.py'))
D,C,images,switch,args,call,inventory,sha,save,caller,read,traces=(w[k]for k in('D','C','images','switch','args','call','inventory','sha','save','caller','read','traces'))
os.umask(0o077);switch('A');X=D/'additional-stock-cold-v1';X.mkdir();seed=X/'untouched-A';seed.mkdir();original=read(traces/'secure-pre-A.json');sdk=read(D/'fixed-inodes-qa-v1/setup.json')['identities']['A'];driver=next((C/'sdk/lib').glob('librustc_driver-*.so'))
def check():
 for k,p in [('compiler',C/'sdk/bin/rustc'),('driver',driver)]:
  st=p.stat();assert [st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns]==sdk[k][1]and sha(p)==sdk[k][0]
 assert sha(C/'sdk/bin/cargo')==images['arms']['A']['image']
for n in ('target','shared','home'):(C/n).rename(seed/n)
recs=[]
try:
 for i in range(2):
  check();d=X/('reference-'+str(i));d.mkdir()
  for n in ('target','shared','home'):(C/n).mkdir()
  subprocess.run(['cp','-a','--reflink=auto',seed/'home/registry',C/'home/registry'],check=True)
  assert not any((C/'target').iterdir())and not any((C/'shared').iterdir())
  o=call('supplementary-fixed-stock-'+str(i),[*args,'--message-format=json']);r,rows=inventory(o,False);assert r['fresh']==0;r['reader']=caller(o,rows)
  for k in ('ids','zips','checks','generations','reader'):assert r[k]==original[k],(i,k)
  for nm,s in r['products'].items():
   f=Path(nm);to=d/('libty_vendored'+f.suffix);shutil.copy2(f,to);assert sha(to)==s
  for n in ('home','target','shared'):(C/n).rename(d/n)
  save(d/'outcome.json',r);recs.append(r);check();print('matched independent control',i,r['ids'],r['products'],flush=True)
finally:
 failed=X/'interrupted';failed.mkdir()
 for n in ('target','shared','home'):
  if (C/n).exists():(C/n).rename(failed/n)
  (seed/n).rename(C/n)
 check();assert all(sha(Path(f))==v for f,v in original['products'].items())
save(X/'complete.json',{'stock':recs,'original':{k:original[k]for k in ('ids','products','zips','checks','generations','reader')}})
