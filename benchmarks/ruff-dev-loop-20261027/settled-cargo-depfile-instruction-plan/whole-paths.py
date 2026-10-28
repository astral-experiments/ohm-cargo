"""Measure an ordinary no-job Cargo process after the recorded historical source edit."""
import fcntl,hashlib,importlib.util,json,os,platform,resource,shutil,subprocess,sys,time
from pathlib import Path
H=Path('/home/dev-user/.cache/ohm-output-path-ruff-20261028')
spec=importlib.util.spec_from_file_location('fixture',H/'prepare-path-fixture.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
host,phase=sys.argv[1:3];assert host in ('h7','h8') and phase in ('qualify','score')
plan=json.loads((H/'plan.json').read_bytes());out=H/'qualified-whole-v1';armfiles={a:H/'subjects'/('qualified-'+a)/'cargo' for a in ('parent','candidate')};binary=s.RT/'bin/cargo'
tools=(s.P/'ohm-early-completion-20261027/spaced-dirty-attribution-20261028/tools-v1') if host=='h7' else H/'counter'
def sha(p):return s.sha(p)
def dig(v):return hashlib.sha256(json.dumps(v,separators=(',',':'),sort_keys=True).encode()).hexdigest()
def write(p,val):s.save(p,val)
def switch(arm):
 tmp=binary.with_name('swap-private-cargo');shutil.copy2(armfiles[arm],tmp);os.replace(tmp,binary);assert sha(binary)==plan['subjects'][arm]
def depfiles(mode):
 d=H/mode/'target/debug';return sorted(set(d.glob('*.d'))|set((d/'examples').glob('*.d')))
def contents(paths):return {str(p):sha(p) for p in paths}
def stamps(paths):
 return {str(p):[v.st_dev,v.st_ino,v.st_size,v.st_mtime_ns] for p in paths for v in [p.stat()]}
def proofs():
 home=H/'cargo-home';fp={}
 for sub in ['.ohm-git-index-sha1dc-v1','.ohm-registry-json-v2']:
  d=home/sub;ids=contents([p for p in sorted(d.rglob('*')) if p.is_file()]);assert ids,sub
  fp[sub]=[len(ids),dig(ids)]
 return fp
def rustc_hashes():
 return {str(p):sha(p) for p in (s.S/'bin/rustc',s.S/'lib/librustc_driver-b03bf00bec23bb9a.so')}
def execs(d):
 return [l.split('execve("',1)[1].split('"',1)[0] for f in sorted(d.glob('exec.*')) for l in f.read_text().splitlines() if 'execve("' in l and l.endswith('= 0')]
def invoke(d,mode,kind):
 d.mkdir(parents=True);argv=s.cmds(mode);e=s.env(mode)
 if kind=='audit': argv=['strace','-ff','-qq','-s','8192','-e','trace=execve','-o',d/'exec',*argv,'--message-format=json']
 if kind=='ir':
  e.update(OHM_PRIVATE_DR_OUT=str(d),OHM_PRIVATE_DR_TOOL='cargo',OHM_PRIVATE_DR_ROOT=str(tools),OHM_PRIVATE_DR_MODULE=str(tools/'client/libpidcounter.so'),LD_PRELOAD=str(H/'dispatch.so'),SSL_CERT_FILE='/etc/ssl/certs/ca-certificates.crt',SSL_CERT_DIR='/usr/lib/ssl/certs')
 with (d/'stdout').open('wb') as so,(d/'stderr').open('wb') as se:
  start=time.perf_counter_ns();proc=subprocess.Popen(argv,cwd=s.cwd(mode),env=e,stdout=so,stderr=se)
  pid,status,usage=os.wait4(proc.pid,0);stop=time.perf_counter_ns();rc=os.waitstatus_to_exitcode(status);proc.returncode=rc
 stdout=(d/'stdout').read_bytes();stderr=(d/'stderr').read_bytes()
 record=dict(rc=rc,stdout=sha(d/'stdout'),stderr=sha(d/'stderr'),maxrss_kib=usage.ru_maxrss)
 if kind=='wall':record['elapsed_ns']=stop-start
 if kind not in ('seed','condition'):assert b'Compiling ' not in stderr and b'Checking ' not in stderr,(d,stderr[-500:])
 assert rc==0 and b'Finished' in stderr,(d,rc,stderr[-900:])
 if kind=='audit':
  rows=[json.loads(x) for x in stdout.splitlines()];units=[r for r in rows if r.get('reason')=='compiler-artifact'];assert all(r['fresh'] for r in units) and units,(d,[r['target']['name'] for r in units if not r['fresh']]);roster=execs(d);assert len(roster)==2 and Path(roster[0]).name=='cargo' and Path(roster[1]).resolve()==binary,(d,roster)
  prods=sorted({str(Path(f)) for r in units for f in r['filenames'] if Path(f).is_file()});record.update(units=len(units),physical=roster,products=prods,json_units=dig([(r['package_id'],r['target'],r['features'],r['filenames'],r['fresh']) for r in units]))
  assert record['units']=={'library':268,'workspace':501,'test':619}[mode]
 else:assert not stdout,(d,stdout[:120])
 if kind=='ir':
  f,=d.glob('profile-*');a,=d.glob('*-cargo.args');v=[q.split() for q in f.read_text().splitlines()];starts=[q[2] for q in v if q[0]=='T'];ends={q[2]:int(q[3]) for q in v if q[0]=='F'}
  assert len({q[1] for q in v if q[0] in ('B','T','F','P')})==1 and [q[0] for q in v].count('B')==[q[0] for q in v].count('P')==1 and v[-1][0]=='P' and len(starts)==len(ends)>=1 and set(starts)==set(ends),(d,v)
  actual=[os.fsdecode(x) for x in a.read_bytes().strip(b'\0').split(b'\0')];assert Path(actual[0]).resolve()==binary and actual[1:]==list(map(str,s.cmds(mode)[2:])),(d,actual)
  record.update(ir=sum(ends.values()),threads=ends,count_sha256=sha(f),argv=actual)
 write(d/'record.json',record);return record
def qualify_mode(mode):
 q=out/mode/'qual';q.mkdir(parents=True)
 for arm in ('parent','candidate'):
  switch(arm);invoke(q/('prepare-'+arm),mode,'seed')
 # No previous external sidecar is accepted as its own expected answer. Regenerate from missing files once with each arm.
 ref=None
 for arm in ('parent','candidate'):
  switch(arm)
  paths=depfiles(mode);saved=q/('saved-dotd-'+arm);saved.mkdir()
  for p in paths:
   copy=saved/p.relative_to(H/mode/'target/debug');copy.parent.mkdir(parents=True,exist_ok=True);p.rename(copy)
  invoke(q/('recreate-'+arm),mode,'condition')
  actual=contents(depfiles(mode));assert set(actual)==set(map(str,paths)),(mode,'new paths',set(actual)^set(map(str,paths)))
  same_paths=[str(p) for p in paths if sha(saved/p.relative_to(H/mode/'target/debug'))==actual[str(p)]]
  assert len(actual)==len(same_paths),(mode,'regeneration changed bytes')
  # Identify a pre-existing mixed-crate output rewrite equally in both arms.
  before=stamps(paths);record=invoke(q/('trace-'+arm),mode,'audit');after=stamps(paths)
  changed=sorted(k for k in before if before[k]!=after[k]);assert actual==contents(paths)
  products=[Path(p) for p in record['products']];product_hashes=contents(products)
  state=dict(units=record['units'],products=product_hashes,product_stamps=stamps(products),dot_d=actual,legacy_rewrites=changed,proofs=proofs(),command=list(map(str,s.cmds(mode))),cwd=str(s.cwd(mode)))
  write(q/(arm+'.json'),state)
  if ref is None:ref=state
  else:assert ref==state,(mode,{k for k in ref if ref[k]!=state[k]})
 assert all(Path(x).name in ('libruff_wasm.d','libty_wasm.d') for x in ref['legacy_rewrites']),(mode,ref['legacy_rewrites'])
 write(q/'anchor.json',ref);print('qualified',mode,ref['units'],len(ref['dot_d']),len(ref['products']),len(ref['legacy_rewrites']),flush=True)
def score_mode(mode):
 q=out/mode/'qual';A=json.loads((q/'anchor.json').read_bytes());paths=list(map(Path,A['dot_d']));products=list(map(Path,A['products']))
 def stable_whole():
  assert contents(paths)==A['dot_d'] and set(depfiles(mode))==set(paths) and stamps(products)==A['product_stamps'] and proofs()==A['proofs'],(mode,'anchor drift')
 stable_whole();assert contents(products)==A['products']
 for kind in ('ir','wall'):
  for i,order in enumerate(plan['orders'][mode][kind]):
   for j,arm in enumerate(order):
    switch(arm);before=stamps(paths);r=invoke(out/mode/kind/f'{i:02}-{j}-{arm}',mode,kind);after=stamps(paths);changed=sorted(n for n in before if before[n]!=after[n])
    assert changed==A['legacy_rewrites'],(mode,i,arm,changed,A['legacy_rewrites'])
    stable_whole()
  audit=invoke(out/mode/('post-'+kind),mode,'audit');assert audit['units']==A['units'] and set(audit['products'])==set(A['products'])
  assert contents(products)==A['products'];stable_whole()
 print('terminal',mode,flush=True)
def main():
 assert (H/'ready.json').is_file() and sha(H/'subjects/qualified-pair.json')==plan['matched_pair'] and {'parent':sha(armfiles['parent']),'candidate':sha(armfiles['candidate'])}==plan['subjects']
 assert [sha(p) for p in (tools/'sdk/bin64/drrun',tools/'sdk/lib64/release/libdynamorio.so',tools/'client/libpidcounter.so')]==plan['counter']
 assert rustc_hashes().values() and sorted(rustc_hashes().values())==sorted(plan['rust'].values())
 if phase=='qualify':
  out.mkdir();subprocess.run(['/usr/bin/cc','-shared','-O2','-fPIC',H/'dr-shim.c','-o',H/'dispatch.so'],check=True)
 else:
  assert (H/'scoring.grant').read_text().strip()==sha(H/'plan.json')
 modes=['library'] if host=='h7' else ['workspace','test']
 for mode in modes:
  if phase=='qualify':qualify_mode(mode)
  else:score_mode(mode)
 result=dict(source=sha(H/'source-state.json'),plan=sha(H/'plan.json'),helper=sha(H/'whole-paths.py'),host=platform.node(),kernel=platform.release(),modes=modes,anchors={m:sha(out/m/'qual/anchor.json') for m in modes},counter=plan['counter'])
 write(out/(phase+'.json'),result)
os.umask(0o077);os.sched_setaffinity(0,range(8))
with s.LOCK.open('a') as lock:fcntl.flock(lock,fcntl.LOCK_EX);main()
