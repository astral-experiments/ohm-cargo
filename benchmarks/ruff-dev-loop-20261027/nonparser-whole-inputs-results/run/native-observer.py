"""Unscored asynchronous file-descriptor observer for one authorized Cargo campaign, best-effort coverage, no program injection."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,os,signal,stat,time,threading
X=Path.home()/'.cache/ohm-233-position-qualified-20261027';base=X/'nonparser-whole-inputs-campaign-v1';root=base/'native-live';root.mkdir(mode=0o700);P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');T=P/'native-target';S=P/'shared';start=time.monotonic();seen=set();pool=ThreadPoolExecutor(max_workers=1);cache={};lock=threading.Lock();pending=[];seq=0;rows={};stats={'seen_typed_wild':0,'captured_transient_or_objects':0,'unreadable_args':0}
def save(p,v):p.write_text(json.dumps(v,sort_keys=True,separators=(',',':'))+'\n')
def physical(path,mode,pid):
 for a,b in ((T,'target'),(S,'shared')):
  if path.is_relative_to(a):return ((base if mode=='build' else Path('/dev/shm/ohm-nonparser-whole-inputs-20261027'))/'state'/mode/b)/path.relative_to(a)
 if path.is_relative_to(P/'frozen-toolchain') or path.is_relative_to('/tmp') or path.is_relative_to('/usr') or path.is_relative_to('/lib') or path.is_relative_to('/lib64'):return path
 return Path('/proc')/str(pid)/'root'/str(path).lstrip('/')
def fct(s):return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def digest(fd,row):
 with os.fdopen(fd,'rb') as f:
  a=fct(os.fstat(fd));k=tuple(a)
  with lock: found=cache.get(k)
  if found is None:
   found=hashlib.file_digest(f,'sha256').hexdigest();b=fct(os.fstat(fd));
   if a!=b:row.update(error='modified during live file read',before=a,after=b);return
   with lock:cache[k]=found
  row.update(sha256=found,facts=a)
def maybe_job(pid):
 try:
  proc=Path('/proc')/str(pid);raw=(proc/'cmdline').read_bytes();argv=[os.fsdecode(x) for x in raw.rstrip(b'\0').split(b'\0')];exe=(proc/'exe').readlink();comm=(proc/'comm').read_text().strip()
  if not argv or (comm not in ('ld.bfd','wild','wild-linker') and 'wild' not in str(exe).lower()):return
  # Only the bound integration's actual GNU-default (GCC -B .../wild-ld) children.
  if not (any('wild-ld' in a for a in argv[:1]) or 'wild' in exe.name.lower()):return
  parents=[];pid2=pid
  for n in range(10):
   v=(Path('/proc')/str(pid2)/'stat').read_text();pid2=int(v.rsplit(')',1)[1].split()[1]);
   if not pid2:break
   f=Path('/proc')/str(pid2)/'cmdline';ar=f.read_bytes()
   if b'strace' in ar and str(base/'receipts').encode() in ar:parents.append(os.fsdecode(ar).split('\0'));break
  if not parents:return
  t=parents[0];idx=t.index('-o');loc=Path(t[idx+1]).parent;mode=loc.parent.name;label=loc.name;out=argv[argv.index('-o')+1] if '-o' in argv else None;row={'pid':pid,'mode':mode,'label':label,'img':str(exe),'argv':argv,'cmdline_sha256':hashlib.sha256(raw).hexdigest(),'output':out,'captures':{},'unresolved_flags':[v for v in argv if v.startswith(('@','-l','--script','-T','--plugin','-plugin','--sysroot'))]};seen.add(pid);rows[pid]=row;stats['seen_typed_wild']+=1
  for i,v in enumerate(argv[1:],1):
   if i and argv[i-1] in ('-o','--output') or v.startswith(('-L','--library-path')):continue
   if v.startswith('@'):v=v[1:]
   if not v.startswith('/'):continue
   a=Path(v);r=physical(a,mode,pid);c={};row['captures'][v]=c
   try:
    fd=os.open(r,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC);s=os.fstat(fd)
    if not stat.S_ISREG(s.st_mode):os.close(fd);c['error']='nonregular';continue
    if a.suffix=='.o' or a.is_relative_to('/tmp'):stats['captured_transient_or_objects']+=1
    c['captured_from_live_argv']=True;pending.append(pool.submit(digest,fd,c))
   except OSError as e:c['error']=e.errno;stats['unreadable_args']+=1
 except (OSError,ValueError,IndexError):return
last=time.monotonic();lastsave=0;sampled_phase=None
while time.monotonic()-start<7200:
 if (base/'complete.json').exists() or (base/'failure.txt').exists():break
 try:
  for e in os.scandir('/proc'):
   if not e.name.isdecimal():continue
   i=int(e.name)
   if i in seen:continue
   try:n=Path(e.path,'comm').read_text().strip()
   except OSError:continue
   if n in ('ld.bfd','wild','wild-linker','ld'):maybe_job(i)
 except OSError:pass
 if time.monotonic()-last>3:
  for f in pending:
   if f.done():f.result()
  if lastsave!=len(rows):save(root/'progress.json',stats);lastsave=len(rows)
  last=time.monotonic()
 time.sleep(.006)
pool.shutdown(wait=True);save(root/'progress.json',stats)
for pid,row in rows.items():save(root/(str(pid)+'.json'),row)
save(root/'complete.json',{'jobs':len(rows),'stats':stats,'coverage':'Asynchronous observational subset of actual Wild execs only. Individual missing files and start-after-cold cases are explicit. No link or input semantics inferred by collection.'})
