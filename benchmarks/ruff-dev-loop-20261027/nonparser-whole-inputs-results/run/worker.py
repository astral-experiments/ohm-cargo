from pathlib import Path
from collections import Counter
import ast,fcntl,gzip,hashlib,json,os,re,shutil,signal,subprocess,sys,time,traceback
H=Path(__file__).resolve().parent;X=Path.home()/'.cache/ohm-233-position-qualified-20261027'; seed=X/'first-occurrence-worker-v2';sys.path.insert(0,str(seed))
from common import P,RUFF,FROZEN,SONAME,TARGET,SHARED,CARGO_HOME,env,sha,git
from namespace import skeleton,spawn_args
run=X/'nonparser-whole-inputs-campaign-v1'; ram=Path('/dev/shm/ohm-nonparser-whole-inputs-20261027'); plan=json.loads((H/'plan.json').read_bytes());ph='e8f487a236e5d308820ec34f9fdf69e2b8f562f96d85166154a51a736f9730b7'; cargo=X/'cargo-observer-fifo-qualification/guardv3';driver=X/'drivers/driver-dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f'; pin=plan['base'];paths=sorted({p for e in plan['edits'].values() for p in e['paths']});fmtstage='crates/ruff_python_formatter/resources/test/fixtures/black/cases';areas=[r for r in paths if not r.startswith(fmtstage+'/')]+[fmtstage]; routine=json.loads((seed/'binding.json').read_bytes());front=routine['host']['host_tools']['rustc_frontend']['sha256'];read=lambda p:json.loads(p.read_bytes())
def save(p,v):p.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
def facts(path):
 s=path.stat();return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def expect(what,context):
 if not what:raise ValueError(context)
def check_disk():
 h=shutil.disk_usage(X).free;t=shutil.disk_usage('/dev/shm').free;expect(h>=25*2**30 and t>=10*2**30,('physical safety floor',h,t));start=read(run/'baseline-disk.json');expect(start['home']-h<=32*2**30 and start['tmpfs']-t<=30*2**30,('reserved budget',h,t));return h,t
def runtask(arg):
 check_disk();p=subprocess.Popen(arg,start_new_session=True)
 try:
  while True:
   try:r=p.wait(timeout=3);break
   except subprocess.TimeoutExpired:check_disk()
  check_disk();expect(r==0,('private worker exited',r,arg[-5:]))
 except BaseException:
  if p.poll() is None:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
  raise

def fixtures():
 f=run/'fixture';o=f/'original';o.mkdir(parents=True);m={}
 for r in paths:
  target=o/r;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(RUFF/r,target);expect(git('hash-object',str(target))==git('rev-parse',pin+':'+r),r)
 m['original']={r:sha(o/r) for r in paths}
 for topic,row in plan['edits'].items():
  patch=H/(topic+'.patch');expect(sha(patch)==row['patch_sha256'],topic);dst=f/topic;shutil.copytree(o,dst)
  subprocess.run(['git','apply','--no-index','--reverse','--whitespace=nowarn',str(patch)],check=True,cwd=dst)
  m[topic]={r:sha(dst/r) if (dst/r).is_file() else None for r in paths};expect({r for r in paths if m[topic][r]!=m['original'][r]}==set(row['paths']),topic)
 save(f/'manifest.json',m)

def state(mode):return (run if mode=='build' else ram)/'state'/mode
def set_source(st,v):
 for r,h in read(run/'fixture/manifest.json')[v].items():
  p=st/'inputs'/r;q=run/'fixture'/v/r
  if h is None:
   if p.exists():p.unlink()
  elif not p.is_file() or sha(p)!=h:
   p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(q.read_bytes());p.chmod(q.stat().st_mode&0o777)
 (st/'view').write_text(v)
def seed_state(st):
 expect(not st.exists(),st);st.mkdir(parents=True,mode=0o700)
 for part in ('target','shared','registry-home','inputs'):(st/part).mkdir(mode=0o700)
 shutil.copytree(P/'rustup',st/'rustup',symlinks=True);expect((st/'rustup/toolchains/ohm').resolve()==FROZEN,'rustup selection')
 for r in ('registry','git','config','config.toml'):
  p=CARGO_HOME/r
  if p.exists():subprocess.run(['cp','-a','--reflink=auto','--',str(p.resolve()),str(st/'registry-home'/r)],check=True)
 expect((st/'registry-home/registry').is_dir() and not (st/'registry-home/registry').samefile((CARGO_HOME/'registry').resolve()),'isolated registry');d=st/'inputs'/fmtstage;d.parent.mkdir(parents=True);shutil.copytree(RUFF/fmtstage,d);set_source(st,'original')

def cli(d,mode,view,arts):
 # Test mode's full workspace also builds the ordinary binaries Cargo uses for integration tests.
 bins={p.stem:p for p in (TARGET/'debug/ruff',TARGET/'debug/ty') if p.is_file()};z={}
 for name in ('ty','ruff'):
  if name not in bins:z[name]={'present':False};continue
  exe=bins[name];arg=[str(exe),*(['check','--output-format','concise',str(run/'oracle/observe.py')] if name=='ty' else ['format','--isolated','--no-cache','--stdin-filename','example.py','-'])];cfg=dict(env(),XDG_CACHE_HOME=str(d/'cli-cache'),NO_COLOR='1');q=subprocess.run(arg,cwd=run/'oracle',env=cfg,input=(run/'oracle/format-input.py').read_bytes() if name=='ruff' else b'',capture_output=True,timeout=30);z[name]={'present':True,'sha256':sha(exe),'returncode':q.returncode,'argv':arg,'stdout':q.stdout.decode(),'stderr':q.stderr.decode()}
  if name=='ty':expect(q.returncode==1 and (q.stdout+q.stderr).count(b'invalid-argument-type')==(2 if view=='ty-diagnostic' else 1),('ty fixture',view,z[name]))
  else:expect(q.returncode==0 and q.stdout==((run/'oracle/fmt-original.out').read_bytes() if view!='formatter' else (run/'oracle/fmt-edited.out').read_bytes()),('formatter fixture',view,z[name]))
 return z

def inventory(lines,previous):
 artifacts=[j for j in lines if j.get('reason')=='compiler-artifact']; old=read(previous) if previous and previous.is_file() else {}; seen={};groups={};regular=missing=0
 for j in artifacts:
  key=j['package_id']+'|'+j['target']['name']+'|'+','.join(j['target']['kind'])+'|'+str(j['profile']['test']); fs=list(j['filenames']);exe=j.get('executable'); fs+=([exe] if exe and exe not in fs else []);groups.setdefault(key,[]).extend(fs)
  for f in fs:
   if f in seen:continue
   p=Path(f)
   if not p.is_file():seen[f]={'exists':False};missing+=1;continue
   before=facts(p);prior=old.get(f,{});h=prior['sha256'] if prior.get('facts')==before else sha(p);after=facts(p);expect(after==before,('artifact replaced during independent scan',p));seen[f]={'exists':True,'facts':after,'sha256':h};regular+=1
 return artifacts,seen,groups,regular,missing

def main_inside(mode,view,label,phase):
 d=run/'receipts'/mode/label;cfg=env();expect(sha(FROZEN/'bin/cargo')==plan['subject']['cargo'].split()[-1] and sha(FROZEN/'lib'/SONAME)==plan['subject']['rustc'].split()[-1] and sha(FROZEN/'bin/rustc')==front,'bound release');expect(git('rev-parse','HEAD')==pin,'Ruff');m=read(run/'fixture/manifest.json')[view];expect(all((sha(RUFF/r) if (RUFF/r).is_file() else None)==h for r,h in m.items()),'source mounts')
 cmd=['cargo','+ohm',*(['build'] if mode=='build' else ['test','--no-run']),'--locked','--offline','--message-format=json','-j8'];calls='execve,execveat,clone,clone3,fork,vfork' if phase in ('edit','restore') else 'execve,execveat';calls+=',open,openat,openat2' if phase in ('edit','restore') else '';trace=['strace','-qq','-ff',*(['-yy'] if phase in ('edit','restore') else []),'-s','1048576','-e','trace='+calls,'-o',str(d/'exec'),*cmd];save(d/'setup.json',{'command':cmd,'tracing':calls,'source':view,'mode':mode,'parser':'first physical screen includes actual opens in edit/restore and execs at every other phase; missing or ephemeral data never certifies equality','source_set':m,'rustc_driver':sha(FROZEN/'lib'/SONAME),'frontend':front,'cargo':sha(FROZEN/'bin/cargo')});
 with (d/'stdout').open('wb') as so,(d/'stderr').open('wb') as se:q=subprocess.run(trace,env=cfg,cwd=RUFF,stdin=subprocess.DEVNULL,stdout=so,stderr=se)
 expect(q.returncode==0,(mode,label,q.returncode,(d/'stderr').read_text(errors='replace')[-1200:]));z=[json.loads(l) for l in (d/'stdout').read_bytes().splitlines()]; prev=run/'receipts'/mode/'last.json';arts,seen,groups,present,missing=inventory(z,Path(prev.read_text())/'artifact-state.json' if prev.is_file() else None);old=read(Path(prev.read_text())/'artifact-state.json') if prev.is_file() else {}; diff={p:{'old':old.get(p,{}).get('sha256'),'new':a.get('sha256')} for p,a in seen.items() if old.get(p,{}).get('sha256')!=a.get('sha256')};save(d/'artifact-state.json',seen);save(d/'artifact-groups.json',groups);save(d/'artifact-changes.json',diff);save(d/'cli.json',cli(d,mode,view,arts));prev.write_text(str(d));trace_parse(d,phase);typed=read(d/'process-totals.json');n={'build':501,'test':619}[mode];fresh=sum(x['fresh'] for x in arts);expect(len(arts)==n,('different workspace',len(arts),n));rec={'mode':mode,'label':label,'phase':phase,'source':view,'artifacts':len(arts),'fresh':fresh,'physical_products':present,'missing_products':missing,'different_raw_products':len(diff),'jobs':typed,'changed_artifacts_count':sum(not x['fresh'] for x in arts),'stdout_sha256':sha(d/'stdout')};save(d/'receipt.json',rec);print('ACTUAL',json.dumps(rec,sort_keys=True),flush=True)

def trace_parse(d,phase):
 from process_scan import parse
 parse(d,phase)

def run_all():
 expect(not run.exists() and not ram.exists(),'run root used');run.mkdir(mode=0o700);ram.mkdir(mode=0o700);save(run/'baseline-disk.json',{'home':shutil.disk_usage(X).free,'tmpfs':shutil.disk_usage('/dev/shm').free});check_disk();expect(sorted(os.sched_getaffinity(0))==list(range(24)),'CPU');expect(sha(H/'plan.json')==ph,'plan');expect(git('rev-parse','HEAD')==pin and not git('status','--porcelain'),'underlying source');
 with (P/'native-measure.lock').open('rb') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); fixtures();o=run/'oracle';o.mkdir();(o/'observe.py').write_text('def accept_ints(*args: int) -> None: ...\n\ndef fixed(args: tuple[None, None]) -> None:\n    accept_ints(*args)\n');(o/'format-input.py').write_bytes(b'#\tTabbed\npass #\tTabbed\n');(o/'fmt-original.out').write_bytes(b'# \tTabbed\npass  # \tTabbed\n');(o/'fmt-edited.out').write_bytes(b'# Tabbed\npass  # Tabbed\n');mount=skeleton(run);completed=[]
  for mode in ('build','test'):
   st=state(mode);seed_state(st);(run/'receipts'/mode).mkdir(parents=True)
   def call(v,n,p):
    set_source(st,v);d=run/'receipts'/mode/n;d.mkdir();a=spawn_args(mount,run,st,st/'registry-home',[],cargo,driver);i=a.index('--');binds=[]
    for r in areas:binds+=['--ro-bind',str(st/'inputs'/r),str(RUFF/r)]
    print('START',mode,n,sorted(check_disk()),flush=True);runtask([*a[:i],*binds,*a[i:],sys.executable,'-B',H/'worker.py','inside',mode,v,n,p]);return read(d/'receipt.json')
   call('original','cold','cold')
   for i in range(1,5):
    r=call('original','warm-'+str(i),'warm');tot=r['jobs'];
    if r['artifacts']==r['fresh'] and tot.get('rustc-full',0)==tot.get('rustc-link-only',0)==tot.get('wild',0)==0:break
   else:raise RuntimeError(('not warm',mode))
   for case in ('ty-diagnostic','formatter'):
    for view,phase in ((case,'edit'),('original','restore')):
     label=case+'-'+phase;r=call(view,label,phase);f=call(view,label+'-fresh','fresh');expect(f['artifacts']==f['fresh'] and not any(f['jobs'].get(k,0) for k in ('rustc-full','rustc-link-only','wild')),('immediate fresh',f));completed.append(r)
   save(run/(mode+'-complete.json'),completed)
  save(run/'complete.json',completed)
if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='inside':main_inside(*sys.argv[2:]);sys.exit()
 try:run_all()
 except BaseException:
  if run.exists():(run/'failure.txt').write_text(traceback.format_exc())
  raise
