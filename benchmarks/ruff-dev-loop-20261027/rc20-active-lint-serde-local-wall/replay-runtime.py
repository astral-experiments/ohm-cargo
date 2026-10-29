"""Guard local tmpfs study resources, run complete native admission, then all registered pairs."""
from pathlib import Path
import datetime,gzip,hashlib,io,json,os,pwd,shutil,socket,subprocess as sp,sys,tarfile,time,traceback
P=Path(os.environ['LINT_STUDY']).resolve();M=P/'mount';R=M/'runtime';D=Path(os.environ['LINT_ARCHIVE']).resolve();CFG=json.loads((P/'replay-config.json').read_bytes());plan=json.loads((P/'protocol.json').read_bytes())
def sha(p):
 with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(f,v):
 with f.open('x')as s:json.dump(v,s,sort_keys=True,indent=2);s.write('\n')
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def resource():
 mem=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines()if l.startswith('MemAvailable:'))
 free=[shutil.disk_usage(Path.home()).free,shutil.disk_usage(D).free,mem,shutil.disk_usage(M).free]
 assert all(x>f for x,f in zip(free,[45*2**30,40*2**30,16*2**30,40<<20])),free
 return free
def notice(k,v):
 save(P/(k+'.json'),dict(utc=stamp(),**v));print(k,flush=True)
def run(label,args,expect=0):
 guard=resource();out=R/(label+'.stdout');err=R/(label+'.stderr')
 with out.open('xb') as o,err.open('xb')as e:
  t=sp.run(['/usr/bin/timeout','--signal=TERM','--kill-after=10s','1500','/usr/bin/taskset','-c','28,29','/usr/bin/python3','-IB',*map(str,args)],cwd=R,stdout=o,stderr=e).returncode
 (R/(label+'.exit')).write_text(str(t)+'\n');assert t==expect,(label,t,err.read_text()[-1200:]);resource()
def setup():
 assert os.geteuid()==1000 and Path('/').stat().st_uid==0 and os.getuid()==1000
 allow=set(os.sched_getaffinity(0));assert set(plan['resource']['cpus']+plan['resource']['watchdog_cpus'])<=allow
 rootst=os.statvfs(M);assert rootst.f_frsize*rootst.f_blocks<=plan['resource']['private_mount_max'] and rootst.f_frsize*rootst.f_blocks>=plan['resource']['private_mount_max']-(4<<20)
 free=resource();R.mkdir(mode=0o700);view=P/'view';base=M/'template';empty=M/'empty-lower';empty.mkdir();base.mkdir()
 for name in ('sdk','sdk/bin','ru','ru/toolchains','source','cargo-home','products','shared','tmp'):(base/name).mkdir()
 target=Path(CFG['sdk']);wild=target/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd';rust=target/'bin/rustc';state=plan['images'];assert sha(rust)==state['rustc'] and sha(wild)==state['wild']
 (base/'sdk/lib').symlink_to(target/'lib',target_is_directory=True)
 for n in ('rustc','rustdoc','cargo'):(base/'sdk/bin'/n).symlink_to(target/'bin'/n)
 (base/'ru/toolchains/ohm').symlink_to(view/'sdk',target_is_directory=True);(base/'ru/settings.toml').write_text('version = "12"\nprofile = "minimal"\n\n[overrides]\n')
 (R/'images').mkdir()
 images={a:Path(CFG[a])for a in 'AB'}
 for a,image in images.items():
  assert sha(image)==state[a];(R/'images'/a).symlink_to(image)
 corpus=Path(CFG['ruff']);registry=Path(CFG['registry'])
 assert sp.check_output(['git','-C',corpus,'rev-parse','HEAD']).decode().strip()==plan['root']['ruff']
 assert all(sha(corpus/k)==v for k,v in json.loads((P/'source-files.json').read_bytes()).items()) and (registry/'registry/src').is_dir()
 for n in ('mechanics.py','member_archive.py','member_archive_base.py','local_study.py','controller.py','wall.py','protocol.json','source.json','source-files.json','gates.py','analysis_lint.py','reopen.py'):shutil.copyfile(P/n,R/n)
 shutil.copyfile(P/'caller.rs',base/'consumer.rs')
 home=Path.home();user=pwd.getpwuid(1000).pw_name
 env=dict(HOME=str(home),USER=user,LOGNAME=user,PATH=str(home/'.cargo/bin')+':/usr/bin:/bin',RUSTUP_HOME=str(view/'ru'),CARGO_TARGET_DIR=str(view/'products'),CARGO_BUILD_BUILD_DIR=str(view/'shared'),CARGO_HOME=str(view/'cargo-home'),TMPDIR=str(view/'tmp'),CARGO_NET_OFFLINE='true',RUSTUP_AUTO_INSTALL='0',CARGO_TERM_COLOR='never',CARGO_CACHE_AUTO_CLEAN_FREQUENCY='never',TZ='UTC',LC_ALL='C.UTF-8')
 save(R/'enrollment.json',{'env':env});save(R/'layout.json',dict(host=socket.gethostname(),view=str(view),allocation=str(M/'physical'),prior_enrollment=str(R/'enrollment.json'),archive_base=str(D),cpus=plan['resource']['cpus'],old_common=str(empty),old_lower=str(base),corpus=str(corpus),registry=str(registry),rustc=state['rustc'],wild=state['wild']))
 notice('prepared',dict(free=free,source=plan['root']['ruff'],protocol=sha(R/'protocol.json'),mount_bytes=rootst.f_frsize*rootst.f_blocks,uid=1000,compiler=state['rustc'],wild=state['wild']))
def native():
 run('native',['local_study.py','discover']);sys.path.insert(0,str(R));from gates import gate
 el=gate(R/'runs','serde');save(R/'eligibility-serde.json',el);assert el['passed'],str(el['errors'])[:500]
 run('admit',['controller.py','admit']);g=json.loads((R/'wall-admission.json').read_bytes());assert g['clock_count']==0 and g['gates']['serde']['eligible'];notice('admitted',dict(gates=el['passed'],raw=sha(R/'wall-admission.json'),evidence=g,eligibility=sha(R/'eligibility-serde.json'),score_count=0))
def score():
 allowed=P/'release-score.json';stop=time.monotonic()+1200
 while not allowed.exists():
  if time.monotonic()>stop:raise TimeoutError('local score authorization receipt')
  time.sleep(1)
 release=json.loads(allowed.read_bytes());assert release['admission']==sha(R/'wall-admission.json') and release['plan']==sha(R/'protocol.json');shutil.copyfile(allowed,R/'release-score.json')
 notice('scoring',{'plan':sha(R/'protocol.json'),'start_resource':resource()})
 run('score-serde',['controller.py','score','serde'])
 (R/'series.exit').write_text('0\n');save(R/'series-closure.json',{'serde':0})
 notice('scored',dict(free=resource(),terminal=sha(R/'wall-terminal-serde.json')))
 run('reopen',['reopen.py']);assert json.loads((R/'reopened/complete.json').read_bytes())['all_readonly']
def export(status):
 # Target is separate from all other campaign stores. The entire raw runtime directory (including all observations and reopened complete product bodies) is copied.
 files=[f for f in sorted(R.rglob('*'))if f.is_file()and not f.is_symlink()]if R.exists()else[]
 extra=[f for f in (P/'prepared.json',P/'admitted.json',P/'scoring.json',P/'scored.json')if f.exists()]
 data_size=sum(f.stat().st_size for f in files+extra);capacity=resource();forecast=data_size+(15<<20);assert capacity[1]>40*2**30+forecast and data_size<180<<20
 dest=D/'rc20-active-lint-local-replica-private';dest.mkdir(mode=0o700,exist_ok=True);archive=dest/('raw-'+P.name+'.tgz');assert not archive.exists()
 with archive.open('xb')as c:
  with tarfile.open(fileobj=c,mode='w:gz',compresslevel=4)as t:
   for f in files:t.add(f,arcname=str(f.relative_to(R)),recursive=False)
   for f in extra:t.add(f,arcname='host/'+f.name,recursive=False)
 with tarfile.open(archive,'r:gz')as t:
  refs={str(f.relative_to(R)):sha(f)for f in files};refs.update({'host/'+f.name:sha(f)for f in extra})
  assert len(t.getmembers())==len(refs)
  for m in t:assert hashlib.file_digest(t.extractfile(m),'sha256').hexdigest()==refs[m.name]
 receipt=dict(archive=str(archive),sha256=sha(archive),raw_files=len(files),expanded_bytes=data_size,archive_bytes=archive.stat().st_size,free_after=resource(),exit=status)
 notice('archived',receipt)
def main():
 status=1
 try:
  setup();native();data=json.loads((P/'admitted.json').read_bytes())
  save(P/'release-score.json',dict(plan=sha(R/'protocol.json'),admission=data['raw'],mode='new physical replay'))
  score();status=0
 except BaseException:
  err=traceback.format_exc();print(err,file=sys.stderr,flush=True)
  if R.is_dir():(R/'first-stop.txt').write_text(err)
 finally:
  if R.is_dir():export(status)
 return status
if __name__=='__main__':sys.exit(main())
