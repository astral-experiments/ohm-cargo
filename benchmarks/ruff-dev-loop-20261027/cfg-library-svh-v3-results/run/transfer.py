"""Copy one exact release driver between assigned devboxes. Only an authenticated and fsync'd stream can be installed."""
from pathlib import Path
import hashlib,json,subprocess,sys
D=Path(__file__).resolve().parent;sha='36d1fd142355c3ad9e0ce006c1e92b7e511cba70c431b09eb1e335f572d27d05';h3='charlie-ohm-trait-perf-1024';h2='charlie-ohm-relink-b-1024';common="""from pathlib import Path
import hashlib,json,os,shutil,sys,socket
want=sys.argv[1]
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
"""
snd=common+"""assert socket.gethostname()=='charlie-ohm-trait-perf-1024'
p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/parse-source-replay-v3/candidate-driver.so');st=p.stat();assert p.is_file() and not p.is_symlink() and 65_000_000<st.st_size<200_000_000
with p.open('rb') as f:
 h=hashlib.sha256(); total=0
 while b:=f.read(1<<20):h.update(b);sys.stdout.buffer.write(b);total+=len(b)
 sys.stdout.buffer.flush()
assert h.hexdigest()==want and total==st.st_size and (p.stat().st_ino,p.stat().st_mtime_ns)==(st.st_ino,st.st_mtime_ns)
print(json.dumps({'source':str(p),'sha256':h.hexdigest(),'bytes':total}),file=sys.stderr,flush=True)
"""
rcv=common+"""assert socket.gethostname()=='charlie-ohm-relink-b-1024'
d=Path.home()/'.cache/ohm-233-position-qualified-20261027/cfg-library-svh-v3-release';assert shutil.disk_usage(d.parent).free>25*(1<<30);d.mkdir(mode=0o700,exist_ok=True);p=d/'candidate-driver.so';tmp=d/('tmp-'+str(os.getpid()))
try:
 with tmp.open('xb') as f:
  h=hashlib.sha256();total=0
  while b:=sys.stdin.buffer.read(1<<20):
   h.update(b);total+=len(b);assert total<200_000_000;f.write(b)
  f.flush();os.fsync(f.fileno())
 assert h.hexdigest()==want and 65_000_000<total<200_000_000 and digest(tmp)==want
 if p.exists():assert p.is_file() and not p.is_symlink() and digest(p)==want
 else:tmp.chmod(0o500);tmp.rename(p)
 print(json.dumps({'destination':str(p),'sha256':digest(p),'bytes':p.stat().st_size,'host':socket.gethostname()}))
finally:
 if tmp.exists():tmp.unlink()
"""
def cmd(host,prog):return ['dbox','ssh',host,'--no-tmux','--','nice','-n','19','taskset','-c','30','/usr/bin/python3','-B','-c',prog,sha]
with (D/'h3-source.stderr').open('wb') as err:
 p=subprocess.Popen(cmd(h3,snd),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=err)
 try:
  q=subprocess.Popen(cmd(h2,rcv),stdin=p.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE);p.stdout.close();out,e=q.communicate(timeout=300);pc=p.wait(timeout=30);(D/'h2-destination.stderr').write_bytes(e);(D/'received.json').write_bytes(out);assert pc==q.returncode==0,(pc,q.returncode,e.decode(errors='replace')[-1000:],(D/'h3-source.stderr').read_text(errors='replace')[-800:])
  r=json.loads(out);assert r['sha256']==sha;print(json.dumps(r))
 finally:
  if p.poll() is None:p.terminate();p.wait()
