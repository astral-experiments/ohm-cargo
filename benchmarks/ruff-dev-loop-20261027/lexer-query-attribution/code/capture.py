"""Capture first-lexer incremental dep graphs and emitted session metadata through regular fds."""
from pathlib import Path
from datetime import datetime
import ast, concurrent.futures, hashlib, json, os, re, shutil, socket, stat, subprocess, sys, threading, time, traceback
from ids import stable_id,b36
assert socket.gethostname()=='charlie-ohm-loader-perf-1024' and os.sched_getaffinity(0)<= {30,31}
base=Path.home()/'.cache/ohm-233-position-qualified-20261027'
q=base/'first-occurrence-classic-pr233-h5-v2'
proto=base/'pr233-three-parser-protocol-h5-v2'
p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
out=p/'pr233-h5-lexer-graph-witness-v2a';logical=p/'native-target'
tag='lexer-pending-indentation'; src='crates/ruff_python_parser/src/lexer.rs'
version='1.99.0-dev (f1a7cf9d2 2026-10-25) (ohm-1.99.0-14)'
lock=threading.Lock();allocated=0;cap=20*2**30;minimum=25*2**30
def j(p):return json.loads(p.read_bytes())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,x):
 t=p.with_suffix('.part');t.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n');t.replace(p)
def birth(f):
 return int(datetime.fromisoformat(subprocess.check_output(['stat','-c','%w',f],text=True).strip()).timestamp()*1e6)
def wait(p):
 while not p.is_file():
  if (q/'failure.txt').exists():raise RuntimeError('benchmark stopped')
  if (q/'test-admission.json').exists() and '/test/' in str(p) and not j(q/'test-admission.json')['run_independent_test_arms']: raise RuntimeError('test endpoint not admitted')
  if (q/'complete.json').exists():raise RuntimeError('benchmark ended before witness')
  time.sleep(.4)
def source(st,expected):
 v=(st/'source-state').read_text();h=sha(st/'inputs'/src)
 return {'label':v,'lexer_rs_sha256':h,'expected':v==tag and h==expected}
def observed(d,rec):
 f=d/rec['pid'];hit=[]
 for line in f.read_text(errors='replace').splitlines():
  if not line.startswith('execve(') or not line.endswith('= 0'):continue
  m=re.match(r'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line)
  if not m or Path(ast.literal_eval(m[1])).name!='rustc':continue
  a=[ast.literal_eval(x) for x in re.findall(r'"(?:[^"\\]|\\.)*"',m[2])]
  if '--crate-name'in a and a[a.index('--crate-name')+1]==rec['crate']:hit.append((line,a))
 (l,a),=hit
 opts=lambda k:[a[i+1] for i,v in enumerate(a) if v==k]
 ct=opts('--crate-type');c=opts('-C');md=[x[9:] for x in c if x.startswith('metadata=')];inc,=[x[12:] for x in c if x.startswith('incremental=')]
 sid=stable_id(rec['crate'],md,not ct or 'bin'in ct or '--test'in a,version)
 ex=[x.split('=',1)[0].split(':')[-1] for x in opts('--extern')]
 return Path(inc),dict(crate=rec['crate'],metadata=md,stable_crate_id=f'{sid:016x}',directory=rec['crate']+'-'+b36(sid),crate_types=ct,test='--test'in a,trace=rec['pid'],exec_line_sha256=hashlib.sha256(l.encode()).hexdigest(),trace_file_sha256=sha(f),explicit_parser='ruff_python_parser'in ex,workspace_externs=sorted(k for k in ex if k.startswith(('ruff','ty_')) or k=='ty'))
def facts(s):return dict(dev=s.st_dev,ino=s.st_ino,size=s.st_size,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)
def selected(inp,tar):
 global allocated
 fd=os.open(inp,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as srcf:
  first=os.fstat(fd);assert stat.S_ISREG(first.st_mode)
  with lock:
   assert allocated+first.st_size<cap and min(shutil.disk_usage(q).free,shutil.disk_usage(out).free)-first.st_size>minimum,('capacity',first.st_size,allocated)
   allocated+=first.st_size
  h=hashlib.sha256()
  with tar.open('xb') as dest:
   while data:=srcf.read(2**20):h.update(data);dest.write(data)
  assert facts(first)==facts(os.fstat(fd)) and tar.stat().st_size==first.st_size and not tar.samefile(inp)
 return dict(name=tar.name,bytes=first.st_size,sha256=h.hexdigest(),source=facts(first))
def collect(mode,arm):
 dest=out/mode/arm;dest.mkdir(parents=True);st=q/'state'/mode/arm;d=q/'receipts'/mode/arm/(tag+'-edit')
 try:
  wait(d/'receipt.json')
  r=j(d/'receipt.json');fixture=j(q/'fixture/manifest.json');expect=fixture[tag][src]
  prim=source(st,expect);assert prim['expected'] and r['source_view']==tag
  bounds=[birth(d/'stdout'),(d/'invocation.json').stat().st_mtime_ns//1000]
  jobs=[c for c in r['processes']['jobs'] if c['kind']=='full']
  x=dict(mode=mode,arm=arm,binding_sha256=sha(proto/'binding.json'),worker_manifest=sha(proto/'SHA256SUMS'),fixture_manifest=sha(q/'fixture/manifest.json'),source_before=prim,command_receipt_sha256=sha(d/'receipt.json'),command_bounds_us=bounds,job_count=len(jobs),observed_processes=r['process_totals'],units=r['unit_count'],jobs=[])
  for rec in jobs:
   inc,jb=observed(d,rec);f=st/'target'/inc.relative_to(logical)/jb['directory']; candidates=[]
   for s in f.glob('s-*'):
    if s.is_dir() and not s.name.endswith('-working'):
     timestamp=int(s.name.split('-')[1],36)
     if bounds[0]<=timestamp<=bounds[1]:candidates.append((s,timestamp))
   jb['candidate_sessions']=[s.name for s,t in candidates];jb['files']=[]
   if len(candidates)==1:
    ss,t=candidates[0];jb['session_start_us']=t;bed=dest/rec['pid'];bed.mkdir()
    jb['available_names']=sorted(k.name for k in ss.iterdir() if k.name.endswith(('.bin','.rmeta')))
    for name in ('dep-graph.bin','metadata.rmeta'):
     a=ss/name
     if a.is_file():
      try:jb['files'].append(selected(a,bed/name))
      except (FileNotFoundError,OSError,AssertionError) as exc:jb.setdefault('misses',[]).append([name,repr(exc)])
    if not jb['files']:jb['miss']='no captured generation'
   else:jb['miss']='no unique finalized directory in measured command interval'
   x['jobs'].append(jb)
  x['source_after_copy']=source(st,expect)
  fresh=d.with_name(d.name+'-fresh')/'receipt.json';wait(fresh);fr=j(fresh)
  assert fr['source_view']==tag and fr['fresh_units']==fr['unit_count']==r['unit_count'] and not fr['processes']['jobs'] and not any(fr['native_totals'].values())
  x['fresh_receipt_sha256']=sha(fresh);x['fresh_units']=fr['fresh_units']
  save(dest/'manifest.json',x);print('captured',mode,arm,len(jobs),sum(any(f['name']=='dep-graph.bin' for f in z['files'])for z in x['jobs']),sum(f['bytes']for z in x['jobs'] for f in z['files']),x['source_after_copy'],flush=True)
  return True
 except BaseException:
  (dest/'error.txt').write_text(traceback.format_exc());print('failure',mode,arm,traceback.format_exc(),flush=True);return False
if __name__=='__main__':
 assert sha(Path(__file__))==sys.argv[1] and sha(Path(__file__).with_name('ids.py'))==sys.argv[2]
 assert sha(proto/'binding.json')==sys.argv[3] and sha(proto/'SHA256SUMS')==sys.argv[4]
 save(out/'plan.json',dict(capture_sha256=sys.argv[1],stable_crate_id_sha256=sys.argv[2],binding_sha256=sys.argv[3],protocol_manifest_sha256=sys.argv[4],max_bytes=cap,min_free_bytes=minimum,clock_start_us=time.time_ns()//1000,cpus=sorted(os.sched_getaffinity(0)),only_source=tag,artifacts=['dep-graph.bin','metadata.rmeta']))
 with concurrent.futures.ThreadPoolExecutor(4) as pool:
  results=list(pool.map(lambda z:collect(*z),[(m,a) for m in ('build','test') for a in 'BC']))
 save(out/'complete.json',dict(all_cases=results,bytes=allocated))
