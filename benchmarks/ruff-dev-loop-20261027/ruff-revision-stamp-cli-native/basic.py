from pathlib import Path
import hashlib,json,os,shutil,signal,subprocess,time
h=Path.home();p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');q=p/'version-heads-build-v1';w=h/'code/oss/ruff-ohm-whole-native-20261027';old=p/'cli-switch-native609e-v1';t,s,r=[old/n for n in ('target','shared','registry-home')];seed=Path('/dev/shm/ohm-cli-switch-native609e-v1/seed');rp=p/'build-script-producer-reuse16-v1';sdk=rp/'sdk';up=rp/'rustup';ram=q/'ram';plan=json.loads((q/'ops/plan.json').read_bytes())
H=lambda b:hashlib.sha256(b).hexdigest()
def sha(f):
 with Path(f).open('rb')as out:return hashlib.file_digest(out,'sha256').hexdigest()
def put(f,obj):
 tmp=f.with_suffix(f.suffix+'.tmp');tmp.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n');os.replace(tmp,f)
def mem():
 m={k.split(':')[0]:int(k.split(':')[1].strip().split()[0])*1024 for k in Path('/proc/meminfo').read_text().splitlines()if k.startswith(('MemAvailable','MemTotal'))};cg=Path('/proc/self/cgroup').read_text().strip().splitlines();z=Path('/sys/fs/cgroup')
 for line in cg:
  a,id,pth=line.split(':',2)
  if a!='0':continue
  for d in [z/pth.lstrip('/'),z]:
   if (d/'memory.max').is_file():
    cap=(d/'memory.max').read_text().strip()
    if cap!='max':m['cgroup_remaining']=int(cap)-int((d/'memory.current').read_text())
 return m
def guard():
 g=2**30;free={str(z):shutil.disk_usage(z).free for z in(p,h,Path('/dev/shm'),Path('/run/user/1000'),ram,t,s,r,w)};m=mem()
 assert all(v>(750*2**20 if k=='/run/user/1000'else 25*g)for k,v in free.items()),free
 assert m['MemAvailable']>25*g and m.get('cgroup_remaining',26*g)>25*g,m
 return {'free':free,'memory':m}
env=dict(HOME=str(h),PATH=str(h/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',LC_ALL='C.UTF-8',RUSTUP_HOME=str(up),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(r),CARGO_TARGET_DIR=str(t),CARGO_BUILD_BUILD_DIR=str(s),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='6',GIT_OPTIONAL_LOCKS='0')
def go(a,**kw):return subprocess.run(list(map(str,a)),env=env,cwd=w,check=True,capture_output=True,**kw)
def monitor(a,stdout,stderr):
 guard()
 with stdout.open('xb') as so,stderr.open('xb')as se:
  prog=subprocess.Popen(list(map(str,a)),env=env,cwd=w,stdout=so,stderr=se,stdin=subprocess.DEVNULL,start_new_session=True)
  try:
   while True:
    try:status=prog.wait(timeout=1);break
    except subprocess.TimeoutExpired:guard()
  except BaseException:os.killpg(prog.pid,signal.SIGTERM);prog.wait();raise
 assert status==0,(status,stderr.read_bytes()[-700:])
def git(*a,cwd=None):return subprocess.check_output(['git','--no-optional-locks','-C',str(cwd or w),*a])
def view(label):
 assert git('rev-parse','HEAD').decode().strip()==plan['heads'][label] and git('rev-parse','HEAD^{tree}').decode().strip()==plan['trees'][label]
 assert not git('status','--porcelain','-z')
 for n,sig in plan['source'].items():assert sha(w/n)==sig
