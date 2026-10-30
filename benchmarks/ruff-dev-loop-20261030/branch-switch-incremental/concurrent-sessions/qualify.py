from pathlib import Path
import errno,fcntl,gzip,hashlib,json,os,shutil,signal,subprocess,sys,time,traceback
B=Path(__file__).resolve().parent; cert=json.loads((B/'setup/qualified.json').read_bytes());ops=B/'ops'; src=B/'checkouts'; result=B/'observations';result.mkdir();events=[];jobs={};cur=[];labels={};oracles={};guards=[]
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(f,v):
 with f.open('x') as o:json.dump(v,o,sort_keys=True,indent=2);o.write('\n')
def guard():
 av=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
 v=[av,shutil.disk_usage(B).free,shutil.disk_usage(os.environ['QA_HOME_VOLUME']).free];assert v[0]>52*2**30 and v[1]>52*2**30 and v[2]>140*2**30,v
 guards.append(v)
def proj(d):
 p=d.stat();return [p.st_dev,p.st_ino,p.st_mode,p.st_nlink]
def lockfile(d):return d.with_name(d.name.rsplit('-',1)[0]+'.lock')
def label(d):
 p=d.name.split('-')[2]
 if not p.startswith('_'):return None
 parts=p.split('_');assert len(parts)==3 and len(parts[1])==16;return parts[1]
def sessions(tree):
 crates=list(tree.glob('lock_subject-*'));assert len(crates)==1,crates
 found=[]
 for d in sorted(crates[0].glob('s-*')):
  if not d.is_dir():continue
  l=lockfile(d);assert l.is_file(),str(l)
  found.append({'name':d.name,'dir_stat':proj(d),'lock_stat':proj(l),'working':d.name.endswith('-working'),'label':label(d),'micros':int(d.name.split('-')[1],36)})
 return {'crate_dir':crates[0].name,'entries':found}
def retained(s):return [x for x in s['entries'] if not x['working']]
def ready(j):
 end=time.monotonic()+40
 while not (j['gate']/'ready').is_file():
  if j['p'].poll() is not None:raise AssertionError((j['tag'],'exited before macro barrier',j['p'].returncode,(j['out']/'stderr').read_text()[-1500:]))
  assert time.monotonic()<end,(j['tag'],'macro readiness timeout')
  time.sleep(.02)
 p,l=(j['gate']/'ready').read_text().split();assert len(l)==16;pid=int(p);assert pid!=os.getpid()
 if j['branch'] in labels:assert labels[j['branch']]==l
 labels[j['branch']]=l;return pid,l
def held_job(j):
 pid,key=ready(j);pp=Path('/proc')/str(pid);k=cert['kits'][j['arm']];sdk=Path(k['sdk']);assert os.path.samefile(pp/'exe',sdk/'bin/rustc')
 driver,=list((sdk/'lib').glob('librustc_driver-*.so'));maps=[line for line in (pp/'maps').read_text().splitlines() if driver.name in line]
 assert maps and any(os.path.samefile(line.split()[-1],driver) for line in maps)
 pairs=[]
 for fd in (pp/'fd').iterdir():
  try:x=Path(os.readlink(fd))
  except (FileNotFoundError,PermissionError):continue
  if x.suffix=='.lock' and j['incr'] in x.parents:
   info=(pp/'fdinfo'/fd.name).read_text();s=x.stat();lines=[a for a in info.splitlines() if a.startswith('lock:')]
   if not any('FLOCK' in a and 'WRITE' in a and str(pid) in a.split() for a in lines):continue
   cand=list(x.parent.glob(x.name[:-5]+'-working'));assert len(cand)==1;d=cand[0];assert os.path.samefile(fd,x) and lockfile(d)==x
   f=os.open(x,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC);e=0
   try:
    try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError as ex:e=ex.errno
   finally:os.close(f)
   assert e in (errno.EWOULDBLOCK,errno.EAGAIN) and (label(d)==key if j['arm']=='G' else label(d) is None)
   pairs.append({'working':d.name,'dir':proj(d),'lock':proj(x),'fdinfo':lines,'contended_errno':e,'session_micros':int(d.name.split('-')[1],36),'checkout_label':key,'pid':pid,'driver':k['driver'],'actual_sdk_exe':proj(pp/'exe')})
 assert len(pairs)==1,(j['tag'],pairs);return pairs[0]
def start(arm,tag,branch,incr,drop=False,block=False):
 guard();k=cert['kits'][arm];out=result/arm/tag;out.mkdir(parents=True);g=out/'barrier';g.mkdir();tr=out/'trace';tr.mkdir();incr.mkdir(parents=True,exist_ok=True)
 if not block:(g/'release').touch()
 env={**k['env'],'CARGO_MANIFEST_DIR':str(src/branch),'LOCK_QA_BARRIER':str(g)}
 app=out/'program'
 argv=[str(B/'bin/rustc'),'+ohm','--crate-name','lock_subject','--edition=2021','--crate-type=bin','main.rs','--error-format=json','--check-cfg=cfg(lock_qa_invalid)','--extern','lock_qa_gate='+k['proc_macro'],'-C','metadata=lock-safety-v1','-C','incremental='+str(incr),'-Cdebuginfo=0','-Ccodegen-units=1',*k['guard'],*k['link_flags']]
 if drop:argv+=['--cfg','lock_qa_invalid']
 argv+=['-o',str(app)];cmd=['/usr/bin/strace','-ff','-qq','-yy','-s','131072','-e','trace=execve,execveat,exit_group,flock,rename,renameat,renameat2','-o',str(tr/'exec'),*argv]
 dump(out/'launch.json',{'argv':argv,'manifest':str(src/branch),'source_sha':sha(src/branch/'main.rs'),'head':cert['checkouts'][branch],'expected_fail':drop})
 with (out/'stdout').open('xb') as stdout,(out/'stderr').open('xb') as stderr:p=subprocess.Popen(cmd,cwd=src/branch,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
 j={'arm':arm,'tag':tag,'branch':branch,'gate':g,'out':out,'incr':incr,'p':p,'argv':argv,'bad':drop};cur.append(j);return j
def release(j):(j['gate']/'release').touch(exist_ok=False)
def diag(stderr):
 rows=[]
 for line in stderr.decode().splitlines():
  try:x=json.loads(line)
  except ValueError:continue
  code=(x.get('code') or {}).get('code')
  if x.get('level')=='error' and code:
   rows.append([code,x['message'],[[s['file_name'],s['line_start'],s['column_start'],s['line_end'],s['column_end'],s['is_primary']] for s in x['spans']]])
 return rows
def finish(j,pristine=False):
 k=cert['kits'][j['arm']];out=j['out'];p=j['p'];code=p.wait(timeout=55);err=(out/'stderr').read_bytes();sid=j['branch'];tree=sessions(j['incr'])
 sys.path.insert(0,str(ops));from trace_exec import collect_execs
 ex,trace,ct,_=collect_execs(out/'trace')
 native=[(path,a) for (path,a),n in ex.items() if '--crate-name' in a and 'lock_subject' in a and '-o' in a and os.path.isfile(path) and os.path.samefile(path,Path(k['sdk'])/'bin/rustc')]
 assert len(native)==1 and list(native[0][1][1:])==j['argv'][2:],(j['tag'],native[:1])
 links=[path for (path,a),n in ex.items() if path.endswith('/wild-ld/ld.bfd') and '--gc-sections' in a and '-o' in a]
 assert all(sha(Path(x))==k['stock_wild'] for x in links)
 flocks=[]
 for f in (out/'trace').glob('exec.*'):
  for l in f.read_text().splitlines():
   if l.startswith('flock(') and str(j['incr']) in l:
    flocks.append({'pid':f.name[5:],'entry':l.split(str(j['incr']),1)[1].split('>',1)[0],'result':l.split('>, ',1)[-1]})
 if j['bad']:
  d=diag(err); assert code==1 and len(d)==1 and d[0][0]=='E0308' and d[0][2] and not(out/'program').exists() and not links,(j['tag'],code,d,links,err[-700:])
  key=(j['arm'],'invalid')
  if pristine:oracles[key]=d
  else:assert d==oracles[key]
  oracle={'diagnostic':d}
 else:
  assert code==0 and len(links)==1,(j['tag'],code,links,err[-700:])
  f=out/'program'; assert f.is_file() and not f.is_symlink()
  executed=subprocess.run([str(f)],capture_output=True,timeout=5);assert executed.returncode==0 and not executed.stderr
  observed=executed.stdout.decode().strip();assert observed=='lock-oracle='+str({'A':17,'B':29,'C':41}[sid])
  key=(j['arm'],sid);oracle={'elf_sha256':sha(f),'len':f.stat().st_size,'verdict':observed}
  if pristine:oracles[key]=oracle
  else:assert oracle==oracles[key],(j['tag'],oracle,oracles[key])
 if (j['gate']/'ready').is_file():
  pid,labelvalue=(j['gate']/'ready').read_text().split()
  if sid in labels:assert labels[sid]==labelvalue
  labels[sid]=labelvalue
 item={'arm':j['arm'],'tag':j['tag'],'branch':sid,'exit':code,'oracle':oracle,'incremental':tree,'same_literal_core_argv':True,'kernel_exec_sha':trace,'physical_rustc':1,'physical_wild':len(links),'trace_files':ct,'flocks':flocks}
 dump(out/'result.json',item);jobs[j['arm']+'/'+j['tag']]=sha(out/'result.json')
 cur.remove(j);guard();return item
def run(arm,tag,b,incr,fail=False,clean=False):return finish(start(arm,tag,b,incr,fail),clean)
def overlap(arm,seq,bad,release_bad_last,aged):
 common=B/'shared-incremental'/arm
 a=start(arm,seq+'-A','A',common,False,True);ra=held_job(a)
 b=start(arm,seq+'-B','B',common,bad,True);rb=held_job(b)
 assert ra['pid']!=rb['pid'] and ra['dir']!=rb['dir'] and ra['lock']!=rb['lock']
 both=sessions(common);assert sum(v['working'] and v['name'] in (ra['working'],rb['working']) for v in both['entries'])==2
 assert both['crate_dir']==(common/next(iter(common.iterdir())).name).name
 if aged:
  while time.time_ns()//1000-min(ra['session_micros'],rb['session_micros'])<10_750_000:time.sleep(.07)
 first,live=(a,b) if release_bad_last else (b,a)
 expected_held=rb if release_bad_last else ra
 release(first);one=finish(first);still=held_job(live)
 assert still['dir']==expected_held['dir'] and still['lock']==expected_held['lock'] and still['pid']==expected_held['pid']
 minus=None
 if aged:
  minus=time.time_ns()//1000-still['session_micros'];assert minus>10_000_000
  assert any(x['entry'].endswith(still['working'].rsplit('-',1)[0]+'.lock') and 'LOCK_EX' in x['result'] and ('EAGAIN' in x['result'] or 'EWOULDBLOCK' in x['result']) for x in one['flocks']),(seq,'no actual failed collector lock',one['flocks'],still)
 release(live);two=finish(live)
 if release_bad_last:
  f=first['out']/'program';assert sha(f)==one['oracle']['elf_sha256'] and subprocess.check_output([str(f)]).decode().strip()==one['oracle']['verdict']
 events.append({'arm':arm,'phase':seq,'both':both,'live_first':ra,'live_second':rb,'survivor_after_peer_exit':still,'held_age_us_when_rechecked':minus,'first_exit':one['exit'],'second_exit':two['exit'],'successful_sibling_reopened_after_late_failure':bool(release_bad_last)})
def assertsettled(arm,s,expected):
 a=retained(s)
 if arm=='G':assert sorted(x['label'] for x in a)==sorted(labels[x] for x in expected),(expected,s)
 else:assert len(a)==1 and a[0]['label'] is None,(expected,s)
def report():
 vals={a:{k:oracles[a,k] for k in ('A','B','C','invalid')} for a in ('P','G')}
 all_stages=[json.loads((result/key/'result.json').read_bytes()) for key in jobs]
 summary={'source_packet':sha(B/'register.json'),'setup':sha(B/'setup/qualified.json'),'worker':sha(Path(__file__)),'source':{key:x['source'] for key,x in cert['kits'].items()},'drivers':{key:x['driver'] for key,x in cert['kits'].items()},'labels':labels,'jobs':jobs,'events':events,'independent_oracles':vals,'rustc_calls':sum(s['physical_rustc'] for s in all_stages),'wild_calls':sum(s['physical_wild'] for s in all_stages),'macro_and_cargo_probes_extra':True,'minimum_available_bytes':[min(q[i] for q in guards) for i in range(3)]}
 dump(B/'terminal.json',summary);print('PASS',len(jobs),summary['wild_calls'],len(events),sha(B/'terminal.json'),flush=True)
def main():
 assert set(os.sched_getaffinity(0))==set(range(4))
 for arm in ('P','G'):
  ring=B/'shared-incremental'/arm
  for b in 'ABC':run(arm,'independent-'+b,b,B/'empty'/arm/b,clean=True)
  run(arm,'independent-invalid','B',B/'empty'/arm/'invalid',True,True)
  run(arm,'seed-C','C',ring)
  overlap(arm,'overlap-success',False,False,True)
  overlap(arm,'overlap-fail-first',True,False,False)
  overlap(arm,'overlap-fail-late',True,True,False)
  last=[]
  for i,b in enumerate('ABCABC'):
   r=run(arm,'serial-'+str(i)+'-'+b,b,ring);last=([z for z in last if z!=b]+[b])[-2:]
   if i>=1:assertsettled(arm,r['incremental'],last)
  assert last==['B','C']
  s=sessions(ring);cr=ring/s['crate_dir'];old=[x for x in retained(s) if x['label']==labels['C']] if arm=='G' else retained(s)
  assert len(old)==1;old=old[0];loc=cr/old['name'];f=os.open(lockfile(loc),os.O_RDONLY|os.O_NOFOLLOW)
  try:
   fcntl.flock(f,fcntl.LOCK_SH|fcntl.LOCK_NB)
   for b in 'AB':r=run(arm,'shared-lock-protects-C-during-'+b,b,ring)
   q=r['incremental'];rl=retained(q);assert loc.is_dir() and proj(loc)==old['dir_stat'] and len(rl)==(3 if arm=='G' else 2)
   if arm=='G':assert {x['label'] for x in rl}==set(labels.values())
  finally:os.close(f)
  rr=run(arm,'shared-lock-released-A','A',ring);assertsettled(arm,rr['incremental'],['B','A']);assert not loc.exists()
  # Rust intentionally keeps young abandoned working directories for ten seconds.
  prior=[x for x in sessions(ring)['entries'] if x['working']]
  if prior:
   deadline=max(x['micros'] for x in prior)+10_400_000
   while time.time_ns()//1000<deadline:time.sleep(.1)
  final=run(arm,'final-quiescent-C','C',ring);assertsettled(arm,final['incremental'],['A','C']);assert not any(x['working'] for x in final['incremental']['entries'])
  events.append({'arm':arm,'phase':'reader-protected-extra','protected':old,'with_shared_reader':q,'after_unlock':rr['incremental'],'young_abandoned_sessions_before_sweep':prior,'quiescent':final['incremental']})
 assert len(set(labels.values()))==3;report()
try:main()
except BaseException:
 dump(B/'failure.json',{'finished':jobs,'captured_events':events,'error':traceback.format_exc()});raise
finally:
 for j in list(cur):
  try:
   (j['gate']/'release').touch(exist_ok=True)
   try:j['p'].wait(timeout=3)
   except subprocess.TimeoutExpired:os.killpg(j['p'].pid,signal.SIGTERM)
  except OSError:pass
