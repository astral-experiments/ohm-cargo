"""Isolated genuine full Rust workspace discovery following the preregistered three-build-script input."""
from pathlib import Path
import collections,fcntl,hashlib,json,os,re,shutil,signal,stat,subprocess,sys,traceback
H=Path(__file__).resolve().parent; X=H.parent;Q=X/'build-script-targets-study-v2';RAM=Path('/dev/shm/ohm-build-script-targets-v2')
PRE=X/'first-occurrence-worker-v2';OLD=X/'nonparser-whole-inputs-impl-v1';sys.path[:0]=[str(PRE),str(OLD)]
from common import P,RUFF,FROZEN,SONAME,TARGET,SHARED,CARGO_HOME,env,git,sha
from namespace import skeleton,spawn_args
from process_scan import parse
def load(p):return json.loads(p.read_bytes())
def put(p,z):p.write_text(json.dumps(z,sort_keys=True,indent=1)+'\n')
plan=load(H/'plan.json');sel=load(H/'selection.json');ref=plan['reference'];files=list(sel['files']);crates={Path(f).parts[1] for f in files};PRIOR=X/'cfg-library-first-v1-campaign';cargo=X/'cargo-observer-fifo-qualification/guardv3';driver=X/'drivers'/('driver-'+ref['rustc_driver']);pinh='11bd588f6471cc8009d884e590a96a038dc46eb383f49ecd5408a450c0685e3c'
def disk():return {'home':shutil.disk_usage(X).free,'ram':shutil.disk_usage('/dev/shm').free}
def floor():
 s=disk();assert s['home']>=25*2**30 and s['ram']>=10*2**30,s;return s
def actual_git():
 return {'head':git('rev-parse','HEAD'),'common':git('rev-parse','--path-format=absolute','--git-common-dir'),'gitdir':git('rev-parse','--path-format=absolute','--git-dir'),'dotgit_sha256':sha(RUFF/'.git')}
def file_state(p,cache,old):
 if not p.is_file():return {'missing':True}
 s=p.stat();stamp=[s.st_dev,s.st_ino,s.st_size,s.st_ctime_ns,s.st_mtime_ns];key=str(p);prev=old.get(key,{})
 with p.open('rb') as f:elf=f.read(4)==b'\x7fELF'
 out={'fingerprint':stamp,'bytes':s.st_size,'sha256':prev['sha256'] if prev.get('fingerprint')==stamp else sha(p),'elf':elf};cache[key]=out;return out
def package(pkgid):return (pkgid.split('#',1)[0].rsplit('/',1)[-1],pkgid.startswith('path+file:'))
def tree(path):
 items={}
 if not path.is_dir():return {'missing_directory':True}
 for root,dirs,fn in os.walk(path,followlinks=False):
  for name in sorted(dirs+fn):
   p=Path(root)/name;s=p.lstat();rel=str(p.relative_to(path))
   if stat.S_ISLNK(s.st_mode):items[rel]=['symlink',os.readlink(p)]
   elif stat.S_ISDIR(s.st_mode):items[rel]=['dir']
   elif stat.S_ISREG(s.st_mode):items[rel]=['regular',s.st_size,sha(p)]
   else:items[rel]=['other',s.st_mode]
 return {'entries':items}
def scr(j):
 od=Path(j['out_dir']);cand=[d/name for d in (od.parent,od.parent/'run') for name in ('output','stdout')];p=next((p for p in cand if p.is_file()),None)
 r={'cargo':j,'raw':None,'out_tree':tree(od)}
 if p is None:return r
 raw=p.read_bytes();r['raw']={'path':str(p),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'lines':raw.decode().splitlines(),'stderr':(p.parent/'stderr').read_text(errors='replace'),'root_output':(p.parent/'root-output').read_text() if (p.parent/'root-output').is_file() else None}
 return r
def phase(mode,label,view):
 d=Q/mode/label;pr=Q/mode/'previous.txt';prev=load(Path(pr.read_text())/'artifacts.json') if pr.is_file() else {};assert sha(FROZEN/'lib'/SONAME)==ref['rustc_driver'] and sha(FROZEN/'bin/cargo')==ref['Cargo'] and sha(FROZEN/'bin/rustc')==ref['rustc_frontend'];source={f:sha(RUFF/f) for f in files};assert all(v==sel['files'][f][view+'_sha256'] for f,v in source.items());gt=actual_git();assert gt['head']==sel['ruff'];c=['cargo','+ohm',*(['test','--no-run'] if mode=='test' else [mode]),'--locked','--offline','--message-format=json','-j8']
 put(d/'identity.json',{'source':source,'command':c,'git':gt,'toolchain':ref,'view':view,'storage':floor()})
 with (d/'cargo.stdout').open('wb') as out,(d/'cargo.stderr').open('wb') as err:
  run=subprocess.run(['strace','-qq','-ff','-s','1048576','-e','trace=execve,execveat','-o',str(d/'exec'),*c],cwd=RUFF,env=env(),stdout=out,stderr=err,stdin=subprocess.DEVNULL)
 parse(d,'cold');procs=load(d/'processes.json');scripts=[]
 for pid,img in procs['exec-images']:
  p=Path(img)
  if p.name.startswith(('build-script-','build_script_')) and p.is_file():
   target=p.parent.name;pkg=target.rsplit('-',1)[0]
   scripts.append({'pid':pid,'image':img,'package':pkg,'own':pkg in crates,'sha256':sha(p)})
 rows=[json.loads(x) for x in (d/'cargo.stdout').read_bytes().splitlines() if x.strip()];art=[q for q in rows if q['reason']=='compiler-artifact'];msg=[q for q in rows if q['reason']=='compiler-message'];sc=[scr(q) for q in rows if q['reason']=='build-script-executed' and package(q['package_id'])[0] in crates and package(q['package_id'])[1]]
 outs={};workspace={};saved={}
 for q in art:
  pkg,ws=package(q['package_id']);key=tuple(q['target']['kind'])
  for f in q['filenames']+([q['executable']] if q.get('executable') else []):
   p=Path(f);v=file_state(p,outs,prev)
   if ws:workspace[f]={'kind':key,'name':q['target']['name'],'crate':pkg,'fresh':q['fresh'],'result':v}
  if ws and pkg in crates:
   saved[pkg+':'+q['target']['name']+':'+str(q['profile']['test'])+':'+str(key)]=q
 versions={}
 for n in ('ruff','ty'):
  pp=TARGET/'debug'/n
  if pp.is_file():
   for args in (['--version'],['version','--output-format','json']):
    z=subprocess.run([str(pp),*args],cwd=RUFF,capture_output=True,timeout=8);versions[n+' '+' '.join(args)]={'exit':z.returncode,'stdout':z.stdout.decode(errors='replace'),'stderr':z.stderr.decode(errors='replace'),'exe_sha256':sha(pp)}
 cli={k:v for k,v in versions.items() if k.endswith('--version')};assert all(v['exit']==0 for v in cli.values())
 typed=[{k:j.get(k) for k in ('kind','crate','pid','exec_sha256','img','argv','image_sha256','test','link_output')} for j in procs['typed']]
 summary={'mode':mode,'view':view,'label':label,'exit':run.returncode,'totals':procs['typed_invocations'],'unclassified':procs['unclassified'],'executed_build_scripts':scripts,'cargo_units':len(art),'fresh':sum(q['fresh'] for q in art),'workspace_terminal_elf_count':sum(v['result'].get('elf',False) and 'custom-build' not in v['kind'] for v in workspace.values()),'workspace_files':len(workspace),'changed_workspace_files':[p for p,v in workspace.items() if prev.get(p,{}).get('sha256')!=v['result'].get('sha256')],'cargo_diagnostics':len(msg),'exec_trace_sha256':sha(d/'exec-traces.tar.zst'),'stdout_sha256':sha(d/'cargo.stdout'),'stderr_sha256':sha(d/'cargo.stderr'),'disk':disk()}
 for name,data in [('receipt',summary),('versions',versions),('artifacts',outs),('workspace',workspace),('three-package-artifacts',saved),('script-output',sc),('diagnostics',msg),('typed-argv',typed)]:put(d/(name+'.json'),data)
 pr.write_text(str(d));print('RECEIPT',mode,label,summary['exit'],summary['cargo_units'],summary['fresh'],summary['totals'],[(x['package'],x['pid']) for x in scripts if x['own']],len(summary['changed_workspace_files']),flush=True)
 assert run.returncode==0,(d,(d/'cargo.stderr').read_text()[-1800:]);assert len(sc)>=3,(len(sc),mode);assert all(s['raw'] for s in sc),[s['cargo']['out_dir'] for s in sc if not s['raw']]
def main():
 assert sha(H/'plan.json')==pinh and sha(H/'historical.patch')==sel['patch_sha256'] and git('rev-parse','HEAD')==sel['ruff'] and not git('status','--porcelain') and not Q.exists() and not RAM.exists();floor()
 with (P/'native-measure.lock').open('rb') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);Q.mkdir(mode=0o700);RAM.mkdir(mode=0o700);put(Q/'starting-space.json',disk());fixture=Q/'fixture'
  for view in ('original','edited'):
   raw=fixture/view
   for f in files:
    dst=raw/f;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(RUFF/f,dst)
   if view=='edited':subprocess.run(['git','apply','-R','--no-index','--whitespace=nowarn',str(H/'historical.patch')],cwd=raw,check=True)
   assert all(sha(raw/f)==sel['files'][f][view+'_sha256'] for f in files)
  root=skeleton(Q);completed=[]
  for mode in ('build','check','test'):
   sm=RAM/mode;donor=(Path('/dev/shm/ohm-cfg-library-first-v1') if mode=='test' else PRIOR)/'state'/mode
   b=int(subprocess.check_output(['du','-sb',str(donor)]).split()[0]);available=disk()['ram'];assert available>10*2**30+b+1*2**30,('copy admission',available,b,donor)
   assert not sm.exists();subprocess.run(['cp','-a','--reflink=auto','--',str(donor),str(sm)],check=True);floor();assert not (sm/'target').samefile(donor/'target') and not (sm/'shared').samefile(donor/'shared') and not (sm/'registry-home').samefile(donor/'registry-home')
   phasebase=Q/mode;phasebase.mkdir();active=phasebase/'active';active.mkdir()
   for f in files:(active/f).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(RUFF/f,active/f)
   def go(label,view):
    d=phasebase/label;d.mkdir();floor()
    for f in files:
     a=active/f;z=(fixture/view/f).read_bytes()
     if a.read_bytes()!=z:a.write_bytes(z)
    opts=spawn_args(root,Q,sm,sm/'registry-home',[],cargo,driver);ix=opts.index('--');mount=[v for f in files for v in ('--ro-bind',str(active/f),str(RUFF/f))]
    cmd=[*opts[:ix],*mount,*opts[ix:],sys.executable,'-B',str(H/'runner.py'),'inside',mode,label,view]
    p=subprocess.Popen(cmd,start_new_session=True)
    try:
     while p.poll() is None:
      try:p.wait(timeout=4)
      except subprocess.TimeoutExpired:floor()
     assert p.returncode==0,(mode,label,p.returncode)
    except BaseException:
     if p.poll() is None:
      os.killpg(p.pid,signal.SIGTERM)
      try:p.wait(timeout=6)
      except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
     raise
    return load(d/'receipt.json')
   for i in range(1,4):
    q=go('baseline-'+str(i),'original')
    if q['cargo_units']==q['fresh'] and not any(q['totals'].get(k,0) for k in ('rustc-full','rustc-link-only','wild')) and not q['executed_build_scripts']:break
   else:raise RuntimeError(('baseline failed to settle',mode))
   for l,v in [('edit','edited'),('unchanged-edit','edited'),('restore','original'),('unchanged-restore','original')]:go(l,v)
   completed.append(mode);put(Q/'completed-modes.json',completed);assert sm==RAM/mode and sm.is_dir();shutil.rmtree(sm)
  put(Q/'complete.json',{'modes':completed,'available':disk(),'plan':pinh,'H2_original_git':actual_git()})
if __name__=='__main__':
 try:
  if len(sys.argv)>1:phase(*sys.argv[2:])
  else:main()
 except BaseException:
  if Q.is_dir():(Q/('failure-'+('-'.join(sys.argv[1:]) or 'outer')+'.txt')).write_text(traceback.format_exc())
  raise
