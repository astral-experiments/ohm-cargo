from pathlib import Path
from threading import Thread
import fcntl,hashlib,json,os,shutil,signal,subprocess,sys,time,traceback
I=Path(__file__).resolve().parent; X=I.parent; Q=X/'cfg-library-first-v1-campaign';RAM=Path('/dev/shm/ohm-cfg-library-first-v1');PRE=X/'first-occurrence-worker-v2';OLD=X/'nonparser-whole-inputs-impl-v1';sys.path.insert(0,str(PRE));sys.path.insert(0,str(OLD))
from common import P,RUFF,FROZEN,SONAME,TARGET,SHARED,CARGO_HOME,env,sha,git
from namespace import skeleton,spawn_args
from process_scan import parse
from worker import inventory
from artifacts import archive,metadata
J=lambda p:json.loads(p.read_bytes())
def dump(p,d):p.write_text(json.dumps(d,indent=1,sort_keys=True)+'\n')
plan=J(I/'plan.json');sel=plan['source_selection'];f=sel['file'];pin=plan['original_ruff'];subject=plan['subject'];driver=X/'drivers'/('driver-'+subject['rustc_driver_ohm_rust_pr233']);cargo=X/'cargo-observer-fifo-qualification/guardv3';pinh='ef1fb915efa17ef62757260d24cef7e958d2a980bfb0c6d3fd2a08aa8f7b8ed3'
def disk():
 h=shutil.disk_usage(X).free;t=shutil.disk_usage('/dev/shm').free;assert h>=25*2**30 and t>=10*2**30,('space floor',h,t);return [h,t]
def state(m):return (RAM if m=='test' else Q)/'state'/m
def watch(cmd):
 disk();p=subprocess.Popen(cmd,start_new_session=True)
 try:
  while p.poll() is None:
   try:p.wait(timeout=5)
   except subprocess.TimeoutExpired:disk()
  assert p.returncode==0,('worker',p.returncode,cmd[-6:])
 except BaseException:
  if p.poll() is None:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
  raise
def snapshots(mode,view,label,art,procs):
 d=Q/'receipts'/mode/label;key='docstring::tests::'+plan['test_control_name'];m={k:hashlib.md5((Q/'fixture'/k/Path(f).name).read_bytes()).digest() for k in ('original','edited')};rows=[]
 for j in art:
  if j['target']['name']!='ty_ide' or j['target']['kind']!=['lib']:continue
  entry={'profile':j['profile'],'cargo_target':j['target'],'features':j['features'],'cargo_fresh':j['fresh'],'files':{}};components={};F=set(str(p) for p in j['filenames']);physical=[r for r in procs['typed'] if r.get('crate')=='ty_ide' and r.get('test')==j['profile']['test']]
  for r in physical:
   args=r['argv']
   if '--out-dir' in args:
    od=Path(args[args.index('--out-dir')+1]);F.update(str(x) for x in od.glob('libty_ide-*.rmeta') if x.is_file());F.update(str(x) for x in od.glob('libty_ide-*.rlib') if x.is_file());F.update(str(x) for x in od.glob('ty_ide-*.d') if x.is_file())
  if j.get('executable'):
   exe=Path(j['executable']);F.add(str(exe));run=subprocess.run([str(exe),'--list','--format','terse'],capture_output=True,timeout=40);allnames=run.stdout.splitlines();hits=[line.decode() for line in allnames if key.encode() in line];entry['compiled_test_list']={'roster_sha256':hashlib.sha256(run.stdout).hexdigest(),'count':len(allnames),'specific_entries':hits,'exit':run.returncode,'argv_tail':['--list','--format','terse']};assert run.returncode==0 and bool(hits)==(view=='edited'),('test roster',hits,view);(d/'ty_ide-test-roster.txt').write_bytes(run.stdout)
  for f0 in sorted(F):
   p=Path(f0)
   if not p.is_file():continue
   h=sha(p);info={'sha256':h,'bytes':p.stat().st_size};entry['files'][str(p)]=info
   if p.suffix=='.d':
    text=p.read_bytes();info['tracks_edited_source']=f.encode() in text;info['source_spelling']=f;info['observer_markers']=sorted({x.decode() for x in text.split() if b'ohm-foreign-span-bytes' in x or b'ohm-untrackable-foreign-span' in x});(d/(p.name+'.original')).write_bytes(text)
   elif p.suffix in ('.rmeta','.rlib') and h not in components:
    if p.suffix=='.rmeta':
     components[h]=metadata(p,m)
     snap=d/'producer.rmeta';snap.write_bytes(p.read_bytes())
    else:components[h]=archive(p,'docstring.rs',m)
  entry['component_hashes']=components;entry['physical_invocations']=[{k:s.get(k) for k in ('kind','pid','crate','exec_sha256','image_sha256','argv')} for s in physical];rows.append(entry)
 dump(d/'producer.json',rows)
def inside(mode,view,label):
 d=Q/'receipts'/mode/label;assert sha(RUFF/f)==sel[('original' if view=='original' else 'edited')+'_sha256'] and sha(FROZEN/'lib'/SONAME)==subject['rustc_driver_ohm_rust_pr233'] and sha(FROZEN/'bin/cargo')==subject['cargo_ohm_pr254'] and sha(FROZEN/'bin/rustc')==subject['rustc_frontend'];cmd=['cargo','+ohm',*(['test','--no-run'] if mode=='test' else [mode]),'--locked','--offline','--message-format=json','-j8'];cfg=env();dump(d/'setup.json',{'command':cmd,'mode':mode,'view':view,'source_sha256':sha(RUFF/f),'cargo':sha(FROZEN/'bin/cargo'),'driver':sha(FROZEN/'lib'/SONAME),'frontend':sha(FROZEN/'bin/rustc')})
 with (d/'stdout').open('wb') as out,(d/'stderr').open('wb') as err:p=subprocess.run(['strace','-qq','-ff','-s','1048576','-e','trace=execve,execveat','-o',str(d/'exec'),*cmd],cwd=RUFF,env=cfg,stdout=out,stderr=err,stdin=subprocess.DEVNULL)
 parse(d,'cold');procs=J(d/'processes.json');tot=J(d/'process-totals.json');z=[json.loads(l) for l in (d/'stdout').read_bytes().splitlines()];prev=Q/'receipts'/mode/'previous';old=Path(prev.read_text())/'artifact-state.json' if prev.is_file() else None;art,seen,groups,regular,missing=inventory(z,old);prior=J(old) if old else {};changes={k:[prior.get(k,{}).get('sha256'),v.get('sha256')] for k,v in seen.items() if prior.get(k,{}).get('sha256')!=v.get('sha256')};dump(d/'artifact-state.json',seen);dump(d/'artifact-changes.json',changes);prev.write_text(str(d));fail=[j for j in z if j['reason']=='compiler-message'];dump(d/'diagnostics.json',fail)
 rec={'mode':mode,'label':label,'view':view,'cargo_status':p.returncode,'jobs':tot,'cargo_units':len(art),'fresh':sum(x['fresh'] for x in art),'products':regular,'missing':missing,'changed_files':len(changes),'physical_ty_ide':[(r['kind'],r['test'],r['exec_sha256']) for r in procs['typed'] if r['crate']=='ty_ide'],'active_tests_invoked_by_cargo':[e for _,e in procs['exec-images'] if e in {r['executable'] for r in art if r.get('executable') and r['profile']['test']}],'stdout_sha256':sha(d/'stdout'),'trace_sha256':sha(d/'exec-traces.tar.zst'),'diagnostics_sha256':sha(d/'diagnostics.json')};dump(d/'receipt.json',rec);print('ACTUAL',mode,label,rec,flush=True);assert p.returncode==0,('Cargo did not succeed',mode,label,(d/'stderr').read_text()[-2000:]);assert not rec['active_tests_invoked_by_cargo'];snapshots(mode,view,label,art,procs)
def main():
 assert git('rev-parse','HEAD')==pin and not git('status','--porcelain') and sha(I/'plan.json')==pinh and not Q.exists() and not RAM.exists();assert os.sched_getaffinity(0)==set(range(24));disk()
 with (P/'native-measure.lock').open('rb') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);Q.mkdir(mode=0o700);RAM.mkdir(mode=0o700);dump(Q/'initial-disks.json',disk());fixture=Q/'fixture'
  for view in ('original','edited'):
   o=fixture/view;o.mkdir(parents=True);tmp=o/'apply';dest=tmp/f;dest.parent.mkdir(parents=True);shutil.copyfile(RUFF/f,dest)
   if view=='edited':subprocess.run(['git','apply','-R','--no-index','--whitespace=nowarn',str(I/'historical.patch')],cwd=tmp,check=True)
   assert sha(dest)==sel[view+'_sha256'];shutil.copyfile(dest,o/Path(f).name)
  mount=skeleton(Q)
  for mode in ('build','check','test'):
   st=state(mode);st.mkdir(mode=0o700,parents=True)
   for p in ('target','shared','registry-home'):(st/p).mkdir(mode=0o700)
   shutil.copytree(P/'rustup',st/'rustup',symlinks=True);assert (st/'rustup/toolchains/ohm').resolve()==FROZEN
   for n in ('git','registry','config','config.toml'):
    p=CARGO_HOME/n
    if p.exists():subprocess.run(['cp','-a','--reflink=auto','--',str(p.resolve()),str(st/'registry-home'/n)],check=True)
   assert not (st/'registry-home/registry').samefile((CARGO_HOME/'registry').resolve());(Q/'receipts'/mode).mkdir(parents=True);fp=st/'active-source.rs';fp.write_bytes((fixture/'original'/Path(f).name).read_bytes());os.utime(fp,ns=( (RUFF/f).stat().st_atime_ns,(RUFF/f).stat().st_mtime_ns))
   def go(view,label):
    d=Q/'receipts'/mode/label;d.mkdir();incoming=(fixture/view/Path(f).name).read_bytes()
    if fp.read_bytes()!=incoming:fp.write_bytes(incoming)
    assert sha(fp)==sel[view+'_sha256'];start=spawn_args(mount,Q,st,st/'registry-home',[],cargo,driver);ix=start.index('--');print('START',mode,label,disk(),flush=True);watch([*start[:ix],'--ro-bind',str(fp),str(RUFF/f),*start[ix:],sys.executable,'-B',str(I/'runner.py'),'inside',mode,view,label]);return J(d/'receipt.json')
   go('original','cold')
   for i in range(1,5):
    r=go('original','warm-'+str(i))
    if r['fresh']==r['cargo_units'] and not any(r['jobs'].get(k,0) for k in ('rustc-full','rustc-link-only','wild')):break
   else:raise RuntimeError('baseline did not settle')
   for view,label in [('edited','edit'),('original','restore')]:
    go(view,label);r=go(view,label+'-fresh');assert r['fresh']==r['cargo_units'] and not any(r['jobs'].get(k,0) for k in ('rustc-full','rustc-link-only','wild'))
  dump(Q/'complete.json',{'available_after':disk(),'plan_sha256':pinh})
if __name__=='__main__':
 try:
  if sys.argv[1:] and sys.argv[1]=='inside':inside(*sys.argv[2:])
  else:main()
 except BaseException:
  if Q.exists():(Q/('failure-'+('-'.join(sys.argv[1:]) or 'outer')+'.txt')).write_text(traceback.format_exc())
  raise
