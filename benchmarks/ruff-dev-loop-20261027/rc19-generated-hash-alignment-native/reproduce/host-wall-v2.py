"""Control plane for ordinary direct-host Cargo. No tracing, digests, or staging across a wall clock."""
import fcntl,hashlib,json,math,os,pathlib,re,shutil,socket,subprocess,sys,time,traceback
from pathlib import Path
H=Path.home();D=H/'.cache/ohm-script-hash-wall-rc19-v1';C=D/'current';project=D/'checkout';host=socket.gethostname();P=json.loads((D/'plan.json').read_bytes());assert host in P['domains'];images=json.loads((D/'images.json').read_bytes()); assert images['qualified'];traces=D/'reports';proxy=H/'.cargo/bin/cargo';args=[str(proxy),'+ohm','build','-p','ty_vendored'];rustc=H/'.cargo/bin/rustc';os.sched_setaffinity(0,set(range(8)))
env={k:v for k,v in os.environ.items() if not k.startswith(('CARGO_','RUSTC_','RUSTUP_')) and k not in ('RUSTFLAGS','RUSTDOCFLAGS','RUSTC','RUSTDOC','LD_PRELOAD','CARGO_LOG')};env.update(RUSTUP_HOME=str(D/'rustup'),CARGO_HOME=str(C/'home'),CARGO_TARGET_DIR=str(C/'target'),CARGO_BUILD_BUILD_DIR=str(C/'shared'),CARGO_BUILD_JOBS='8',CARGO_NET_OFFLINE='true',RUSTUP_AUTO_INSTALL='0',GIT_OPTIONAL_LOCKS='0');lock=(D/'runner.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
def sha(f):
 with f.open('rb')as fp:return hashlib.file_digest(fp,'sha256').hexdigest()
def dg(v):return hashlib.sha256(json.dumps(v,separators=(',',':'),sort_keys=True).encode()).hexdigest()
def save(f,v):f.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
def read(f):return json.loads(f.read_bytes())
def switch(arm):
 if C.exists():
  curr=(C/'marker').read_text();assert curr in 'AB'
  if curr!=arm:C.rename(D/'states'/curr)
 if not C.exists():(D/'states'/arm).rename(C)
 assert (C/'marker').read_text()==arm and os.getuid()==os.geteuid()==1000 and not (D/'states'/arm).exists();assert all((C/k).stat().st_dev==D.stat().st_dev for k in ('target','shared','home','sdk'))
def native_ownership():
 obj={};paths=[project,C/'target',C/'shared',C/'home/registry',D/'rustup',C/'sdk/bin/cargo',H/'.cargo/bin/rustup']; paths.extend(x for x in (C/'home').glob('.ohm-*-v*') if x.is_dir());
 for p in paths:
  for q in [*reversed(p.parents),p]:
   st=q.stat();obj[str(q)]={'uid':st.st_uid,'gid':st.st_gid,'mode':oct(st.st_mode&0o7777),'dev':st.st_dev,'ino':st.st_ino};assert st.st_uid in (0,os.geteuid()) and st.st_gid!=65534 and not st.st_mode&0o002,(q,st)
 return obj
def call(label,argv=None,observe=False,expect=0,extra_env=None):
 d=traces/label;d.mkdir();command=argv or args;ee={**env,**(extra_env or {})};rec={};
 with (d/'stdout').open('xb')as out,(d/'stderr').open('xb')as err:
  cp=subprocess.Popen(command,cwd=project,env=ee,stdin=subprocess.DEVNULL,stdout=out,stderr=err)
  if observe:
   target=(C/'sdk/bin/cargo').resolve();todo=[cp.pid];deadline=time.monotonic()+8
   while time.monotonic()<deadline and cp.poll() is None and not rec:
    population=[cp.pid];seen=set()
    while population and not rec:
     pid=population.pop();proc=Path('/proc')/str(pid)
     if pid in seen:continue
     seen.add(pid)
     try:
      population+=list(map(int,(proc/'task'/str(pid)/'children').read_text().split())); exe=Path(os.readlink(proc/'exe'))
      if exe.samefile(target):
       lines=(proc/'status').read_text().splitlines();uids=next(s.split()[1:]for s in lines if s.startswith('Uid:'));gids=next(s.split()[1:]for s in lines if s.startswith('Gid:'));mnt=os.readlink(proc/'ns/mnt');uidmap=(proc/'uid_map').read_text();assert set(uids)=={str(os.getuid())} and set(gids)=={str(os.getgid())} and mnt==os.readlink('/proc/self/ns/mnt') and uidmap==Path('/proc/self/uid_map').read_text();chain=native_ownership()
       for name,st in chain.items():
        peer=(proc/'root'/name.lstrip('/')).stat();assert (st['uid'],st['gid'],st['ino'],st['dev'])==(peer.st_uid,peer.st_gid,peer.st_ino,peer.st_dev)
       rec={'pid':pid,'exe':sha(proc/'exe'),'mount_ns':mnt,'uidmap':uidmap,'uid':uids,'gid':gids,'chain':chain,'affinity':sorted(os.sched_getaffinity(pid))};assert rec['affinity']==list(range(8));break
     except (FileNotFoundError,ProcessLookupError):pass
    if not rec:time.sleep(.0005)
  rc=cp.wait()
 if observe:assert rec and rec['exe']==images['arms'][(C/'marker').read_text()]['image'],(rc,rec)
 save(d/'command.json',{'rc':rc,'stdout':sha(d/'stdout'),'stderr':sha(d/'stderr'),'actual_exec':rec});assert rc==expect,(label,rc,(d/'stderr').read_text()[-850:]);return d
def products():
 out={}
 for p in sorted((C/'target').rglob('libty_vendored-*')):
  if p.suffix in ('.rlib','.rmeta') and p.is_file():out[str(p.relative_to(C))]=sha(p)
 assert {Path(p).suffix for p in out}=={'.rlib','.rmeta'};return out
def inventory(d,fresh):
 rows=list(map(json.loads,(d/'stdout').read_bytes().splitlines()));a=[x for x in rows if x['reason']=='compiler-artifact']; assert len(a)==182 and (not fresh or all(r['fresh']for r in a)); ids=sorted((x['package_id'],x['target']['name'],x['target']['kind'],x['filenames'])for x in a);lib=[r for r in a if r['target']['name']=='ty_vendored'];assert len(lib)==1;files={k:sha(Path(k))for k in lib[0]['filenames']}; assert all((C/'target') in Path(k).parents for k in files)
 dep=[r for r in rows if r['reason']=='build-script-executed'];zips={};checks={};generation={}
 for p in sorted((C/'target').rglob('out/*')):
  if p.name in ('zipped_typeshed.zip','generated.rs','generated_phf.rs')and p.is_file() and (p.name=='zipped_typeshed.zip' or 'unicode_names' in str(p)):
   assert p.name not in zips,p;zips[p.name]={'size':p.stat().st_size,'sha256':sha(p)}
 for p in sorted((C/'target').rglob('.ohm-worktree-result-v1')):generation[str(p.relative_to(C))]=p.read_text().strip()
 for p in sorted((C/'target').rglob('*.d')):
  if p.name.startswith(('ty_vendored-','unicode_names2-')):
   for line in p.read_text(errors='replace').splitlines():
    if line.startswith('# checksum:') and any(fn in line for fn in zips):checks.setdefault(p.name,[]).append(line)
 assert sorted(v['size']for v in zips.values())==[554093,1787150,5577690] and generation and sum(map(len,checks.values()))>=3,(zips,checks)
 record={'rows':len(a),'fresh':sum(x['fresh']for x in a),'ids':dg(ids),'products':files,'zips':zips,'checks':checks,'generations':generation};save(d/'artifacts.json',record);return record,rows
def caller(d,rows):
 a=[x for x in rows if x['reason']=='compiler-artifact'];ty,=[x for x in a if x['target']['name']=='ty_vendored'];lib,=[x for x in ty['filenames']if x.endswith('.rlib')];deps=sorted({str(Path(n).parent)for x in a for n in x['filenames']if Path(n).suffix in ('.rlib','.rmeta','.so')});native=sorted({p for x in rows if x['reason']=='build-script-executed' for p in x['linked_paths']});src=d/'reader.rs';src.write_text('fn main() { use std::io::Write; let stub=ty_vendored::file_system().read_to_string("stdlib/ty_extensions/pydantic.pyi").unwrap(); std::io::stdout().write_all(stub.as_bytes()).unwrap(); }\n');binary=d/'reader';cmd=[str(rustc),'+ohm','--edition=2024','--crate-name','consumer',str(src),'--extern','ty_vendored='+lib,'-o',str(binary)];
 actual,=list((C/'target/debug/build/workspaces').glob('*/*/ty_vendored/*/out/libty_vendored-*.rlib'));deps=sorted(set([*deps,str(actual.parent),str(C/'target/debug/deps')]))
 for p in deps:cmd+=['-L','dependency='+p]
 for p in native:cmd+=['-L',p]
 with (d/'reader.stderr').open('xb')as er:cp=subprocess.run(cmd,cwd=project,env=env,stdout=subprocess.DEVNULL,stderr=er);assert cp.returncode==0,(d/'reader.stderr').read_text()[-800:]
 with (d/'reader.out').open('xb') as out:subprocess.run([binary],cwd=project,env=env,stdout=out,check=True)
 assert (d/'reader.out').read_bytes()==(project/'crates/ty_vendored/ty_extensions/pydantic.pyi').read_bytes();return sha(d/'reader.out')
def fs_trace(d):
 files=list(d.glob('exec.*')); tools=[];cache={};bases={};selected={};binary=images['arms'][(C/'marker').read_text()]['image'];assert sha(C/'sdk/bin/cargo')==binary
 for f in files:
  for line in f.read_text(errors='replace').splitlines():
   if 'execve('in line and '= 0' in line:
    m=re.search(r'execve\("([^"]+)"',line)
    if m:tools.append(Path(m[1]).name)
   m=re.search(r'\bread\(\d+<([^>]+)>, [^,]+, (\d+)\)\s+= (\d+)',line)
   if not m:continue
   p=Path(m[1]);possible=[s for s in ('/.ohm-registry-json-v2/','/.ohm-git-index-sha1dc-v1/')if s in str(p)];n=int(m[3]);key=str(p)
   if possible and n>0:
    assert p.is_relative_to(C/'home');cache.setdefault(possible[0],set()).add(key)
   if n>0 and p.is_relative_to(C/'home/registry'):bases.setdefault('registry read paths',set()).add(key)
   if p.name in ('generated.rs','generated_phf.rs','zipped_typeshed.zip')and p.is_relative_to(C/'target')and (p.name=='zipped_typeshed.zip'or'unicode_names'in str(p)):
    selected.setdefault(p.name,[]).append([int(m[2]),n])
 assert len(files)>=2 and tools.count('cargo')>=2 and not any(x in ('rustc','cc','ld','ld.bfd','collect2','ld.lld','rust-lld','wild','as')for x in tools),(len(files),tools)
 assert cache and bases,(cache,bases);sizes={'generated.rs':1787150,'generated_phf.rs':554093,'zipped_typeshed.zip':5577690};assert set(sizes)==set(selected),selected.keys()
 for name,io in selected.items():
  groups=[];g=[]
  for req,n in io:
   if n:g.append([req,n])
   else:groups.append(g);g=[]
  assert not g and sorted(sum(n for _,n in a)for a in groups)==[sizes[name]]*2,(name,[(len(x),sum(z for _,z in x))for x in groups]);assert groups[1][0][0]==65536
  assert groups[0][1][0]==16384;arm=(C/'marker').read_text();assert (groups[0][0][0]==16384)==(arm=='A'),(arm,name,groups[0][0])
 return {'trace_files':{p.name:sha(p)for p in files},'tools':tools,'actual_registry_cache_reads':{k:len(v)for k,v in cache.items()},'actual_registry_prerequisites':{k:len(v)for k,v in bases.items()},'two_observations':{k:{'requests':len(v),'bytes':sum(n for _,n in v),'first':v[0]}for k,v in selected.items()}}
def qualify(arm,phase):
 switch(arm); assert sha(C/'sdk/bin/cargo')==images['arms'][arm]['image'];own=native_ownership(); assert sha(C/'sdk/bin/rustc')==read(D/'staged.json')['compiler'];status=subprocess.check_output(['git','-C',project,'status','--porcelain','--untracked-files=all'],env=env);assert not status,status[:100]; assert sha(project/'Cargo.lock')==P['cargo_lock']
 job=call(f'{phase}-cache-{arm}',[*args,'--message-format=json'],observe=True);q,rows=inventory(job,True);q['reader']=caller(job,rows)
 tdir=traces/f'{phase}-trace-{arm}';tracecmd=['strace','-ff','-qq','-yy','-s','0','-e','trace=execve,execveat,read,openat','-o',str(tdir/'exec'),*args];td=call(f'{phase}-trace-{arm}',tracecmd);q['physical']=fs_trace(td);q['native_ownership']=own;q['actual_exec']=read(job/'command.json')['actual_exec'];q['source']=subprocess.check_output(['git','-C',project,'rev-parse','HEAD'],text=True).strip();q['arm']=arm;q['native_outputs']=products(); assert q['source']==P['commit'];save(traces/f'{phase}-{arm}.json',q);return q

def pair_qual(phase):
 obs=[qualify(arm,phase) for arm in 'AB']; fields=('ids','products','zips','checks','generations','reader','source','native_outputs')
 for k in fields:assert obs[0][k]==obs[1][k],(phase,k,obs[0][k],obs[1][k])
 if phase=='post':
  for c in obs:
   pre=read(traces/('pre-'+c['arm']+'.json'))
   for k in fields:assert c[k]==pre[k],(phase,c['arm'],k)
 q={'terminal':True,'phase':phase,'physical':[dg(x['physical'])for x in obs],'native_outputs':obs[0]['native_outputs'],'product_sha256':dg(obs[0]['products']),'identities':obs[0]['ids'],'source':P['commit'],'program':obs[0]['reader'],'complete_phases':{q['arm']:sha(traces/f"{phase}-{q['arm']}.json")for q in obs}};save(traces/f'{phase}-binding.json',q);return q

def main(m):
 if m=='train':
  for arm in 'AB':
   switch(arm);assert sha(C/'sdk/bin/cargo')==images['arms'][arm]['image'];assert not any((C/'target').iterdir()) and not any((C/'shared').iterdir());d=call('empty-'+arm,[*args,'--message-format=json']);cold,rows=inventory(d,False);assert cold['fresh']==0,(arm,cold['fresh']);cold['reader']=caller(d,rows);save(d/'complete.json',cold)
   # Warm separately; post-cold revalidation is allowed here. The second ordinary command must be fully fresh.
   for j in (1,2):
    w=call(f'train-{arm}-{j}',[*args,'--message-format=json']);r,_=inventory(w,j==2)
   print('cold and settled',arm,cold['rows'],r['fresh'],flush=True)
 elif m=='pre':print('native',json.dumps(pair_qual('pre'),sort_keys=True),flush=True)
 elif m=='score':
  pub=read(D/'grant.json');pre=read(traces/'pre-binding.json');assert pub['host']==host and pub['source_plan_ref']=='2d40c0ba8f68ba2bfadc489db876b49f5c442de4' and pub['admission']==sha(traces/'pre-binding.json') and pub['plan']==sha(D/'plan.json') and pub['worker']==sha(Path(__file__)) and pub['images']==sha(D/'images.json') and pub['grant'] is True
  assert not (D/'score').exists() and pre['terminal'] and os.getloadavg()[0]<2.5 and shutil.disk_usage(D).free>(30 if 'loader-'in host else 10)*2**30;w=D/'score';w.mkdir();ledger=w/'slots.jsonl';state={'host':host,'plan':sha(D/'plan.json'),'grant':sha(D/'grant.json'),'pre_guards':sha(traces/'pre-binding.json'),'rows':[],'terminal':False,'begin_load':os.getloadavg()}
  for i,order in enumerate(P['domains'][host]['strata']):
   for j,arm in enumerate(order):
    switch(arm);assert os.getpid() and os.sched_getaffinity(0)==set(range(8));d=w/f'{i:02}-{j}-{arm}';d.mkdir();assert not any(k in env for k in ('RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUSTC','RUSTFLAGS','LD_PRELOAD'));cl=read(traces/f'pre-{arm}.json')['native_ownership'];assert C.stat().st_ino==cl[str(C)]['ino'] and (C/'sdk/bin/cargo').stat().st_ino==cl[str(C/'sdk/bin/cargo')]['ino'];ss={'arm':arm,'stratum':i,'position':j}
    with (d/'stdout').open('xb')as so,(d/'stderr').open('xb')as er:
     t=time.perf_counter_ns();rc=subprocess.run(args,cwd=project,env=env,stdin=subprocess.DEVNULL,stdout=so,stderr=er).returncode;end=time.perf_counter_ns()
    ss.update(start=t,end=end,elapsed_ns=end-t,rc=rc,stdout=sha(d/'stdout'),stderr=sha(d/'stderr'));txt=(d/'stderr').read_text();ss['fresh_text']=('Finished 'in txt and 'Compiling 'not in txt and 'error:'not in txt);save(d/'clock.json',ss)
    with ledger.open('a')as f:f.write(json.dumps(ss,sort_keys=True)+'\n');f.flush()
    assert rc==0 and end>t and (d/'stdout').stat().st_size==0 and ss['fresh_text'],(i,j,arm,txt[-650:]);state['rows'].append(ss)
   assert shutil.disk_usage(D).free>(25 if 'loader-'in host else 9)*2**30
  post=pair_qual('post');state['post_guards']=sha(traces/'post-binding.json');state['end_load']=os.getloadavg();state['terminal']=True;assert len(state['rows'])==P['commands_per_host'];save(w/'terminal.json',state);print('terminal',len(state['rows']),flush=True)
 else:raise ValueError(m)

if __name__=='__main__':
 try:main(sys.argv[1])
 except BaseException:
  x=D/('failure-'+sys.argv[1]+'-'+str(time.time_ns())+'.txt');x.write_text(traceback.format_exc());raise
