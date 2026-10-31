"""Same host / upstream 1.99.0 paired runs of the real ready-test, including its own 15s rendezvous."""
import concurrent.futures, gzip, hashlib, importlib.util, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
P="010b760433999227e39a26b3d86e0db2f9bc2375"; C="4591cf45cc10abb19d2456c40b99606e08167f29"
T={P:"be5719ea48dbfbb24cd696dc74eabd4ecc76e754",C:"a2c9a62722e1ef849cb68874e79617c92d165a8b"}
NAME="ohm_ready_tests::uses_current_runtime_inputs_and_ignores_disabled_binaries"
F="tests/testsuite/ohm_ready_tests.rs"; HASH="03d2fa196a80c0af1c67ece2fb2cf952e15c60caae0419e115fd5a2459fd2aa5"
SRC=Path(os.environ["GITHUB_WORKSPACE"]); ROOT=Path(os.environ["QA_AREA"]); OUT=Path(os.environ["RUNNER_TEMP"])/"ready-receipts";OUT.mkdir()
assert sys.platform=="darwin" and os.uname().machine=="arm64" and os.environ["QA_STORAGE"]=="apfs"
spec=importlib.util.spec_from_file_location("diag",SRC/"ci/rc22-ready-stack.py");diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)
h=lambda b:hashlib.sha256(b).hexdigest()
def ph(p):
 with open(p,'rb') as f:
  digest=hashlib.sha256()
  for c in iter(lambda:f.read(1024*1024),b""):digest.update(c)
  return digest.hexdigest()
def git(*a,cwd=SRC):return subprocess.check_output(["git",*a],cwd=cwd).decode().strip()
def save(p,x):p.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")
def gz(p,b):p.write_bytes(gzip.compress(b,mtime=0))
assert git("rev-parse",C+"^1")==P and git("rev-parse","HEAD^")==C
assert git("diff","--name-only",P,C).splitlines()==["src/compiler/fingerprint/dep_info.rs","src/compiler/fingerprint/mod.rs","tests/testsuite/freshness.rs"]
binding={}
for rev in (P,C):
 assert git("rev-parse",rev+"^{tree}")==T[rev]
 binding[rev]={k:git("rev-parse",rev+":"+k) for k in (F,"src/ops/cargo_test","src/compiler/job_queue","src/compiler/build_runner")}
assert binding[P]==binding[C]
ready_src=subprocess.check_output(["git","show",C+":"+F],cwd=SRC);assert h(ready_src)==HASH
for needle in [b"Instant::now() + Duration::from_secs(15)",b'control.join(marker).exists()',b'cargo("test --workspace --lib -j2 -Zohm-defaults=no -Zohm-ready-tests")',b'assert_run(&p, "during")',b'control/current-binary',b'compile_error!(\\"disabled binary must not be built',b'assert_eq!(output.stdout, b"new")']:
 assert needle in ready_src,needle
tool={};env=dict(os.environ);env["RUSTUP_TOOLCHAIN"]="1.99.0"
for x in ("cargo","rustc"):
 exe=subprocess.check_output(["rustup","which","--toolchain","1.99.0",x],text=True).strip();tool[x]={'file':exe,'sha256':ph(exe),'vv':subprocess.check_output([exe,"-vV"],text=True)}
assert 'b940084d7eb6a299eb4bfeb8e34901bc051e7ac4' in tool['rustc']['vv']
env["PATH"]=str(Path(tool["rustc"]["file"]).parent)+os.pathsep+env["PATH"]
save(OUT/"registration.json",{"source_and_scheduler":binding,"test_sha":HASH,"physical_stock":tool,"host":list(os.uname()),"run":os.environ["GITHUB_RUN_ID"],"qa":os.environ["GITHUB_SHA"],"paired_order":[list("PC" if i%2==0 else "CP") for i in range(12)],"apfs":os.environ["QA_STORAGE"],"poll_after":2.15,"trigger":"same live edited wrapper PID and no a-timing","fixture_deadline_seconds":15})
roles={}
for role,rev in (("P",P),("C",C)):
 tree=ROOT/("source-"+role);tdir=ROOT/("build-"+role);d=OUT/role;d.mkdir()
 subprocess.check_call(["git","worktree","add","--detach",str(tree),rev],cwd=SRC)
 assert git("rev-parse","HEAD",cwd=tree)==rev and git("status","--porcelain",cwd=tree)==""
 assert ph(tree/F)==HASH
 environ=dict(env,CARGO_TARGET_DIR=str(tdir))
 args=["cargo","+1.99.0","test","--locked","-p","cargo","--test","testsuite","--no-run","--message-format=json"]
 p=subprocess.run(args,cwd=tree,env=environ,capture_output=True)
 gz(d/"build.stdout.gz",p.stdout);gz(d/"build.stderr.gz",p.stderr)
 if p.returncode:
  print(p.stderr.decode(errors="replace")[-2000:]);raise SystemExit(p.returncode)
 msgs=[json.loads(l) for l in p.stdout.splitlines() if l.startswith(b'{')];assert msgs[-1]=={'reason':'build-finished','success':True}
 suite,=[Path(m['executable']) for m in msgs if m.get('reason')=='compiler-artifact' and m['target']['name']=='testsuite' and m['target']['kind']==['test'] and m['profile']['test']]
 exe=tdir/'debug/cargo';vv=subprocess.check_output([exe,'-Vv'],env=environ,text=True);assert 'commit-hash: '+rev in vv
 inv=subprocess.check_output([suite,NAME,'--exact','--list'],env=environ,text=True)
 assert inv.splitlines()==[NAME+': test','','1 test, 0 benchmarks'];(d/'inventory.txt').write_text(inv)
 save(d/'identity.json',{'rev':rev,'tree':T[rev],'source_sha':ph(tree/F),'suite':str(suite),'suite_sha':ph(suite),'cargo':str(exe),'cargo_sha':ph(exe),'vv':vv})
 fixture=tdir/'tmp/cit/testsuite/ohm_ready_tests'/NAME.split("::")[-1]
 roles[role]=(tree,tdir,suite,exe,fixture,environ)
def children(top):
 raw=subprocess.check_output(['/bin/ps','-axo','pid=,ppid=,state=,command='],text=True,errors='replace');rows={}
 for line in raw.splitlines():
  x=line.split(None,3)
  if len(x)==4 and x[0].isdecimal() and x[1].isdecimal():rows[int(x[0])]=(int(x[1]),*x[2:])
 chain={top}
 while (more:={k for k,v in rows.items() if v[0] in chain}-chain):chain|=more
 return {k:v for k,v in rows.items() if k in chain}
def control(f):
 st={}
 for p in (f/'foo/control').glob('*'):
  try:
   if p.is_file():st[p.name]={'body':p.read_text(),'mtime_ns':p.stat().st_mtime_ns}
  except FileNotFoundError:pass
 return st
summary={"P":[],"C":[]}
for block in range(12):
 for role in ('PC' if block%2==0 else 'CP'):
  tree,tdir,suite,exe,fixture,environ=roles[role]
  d=OUT/role/f'visit-{block+1:02}';d.mkdir();beg=time.time_ns();sample=False;tag=None;clock=None
  with (d/'stdout').open('xb') as o,(d/'stderr').open('xb') as e:
   proc=subprocess.Popen([suite,NAME,'--exact','--include-ignored','--test-threads=1','--color','never'],cwd=tree,env=environ,stdout=o,stderr=e)
   observe_time=time.monotonic()
   while proc.poll() is None:
    if time.monotonic()-observe_time>150:
     before=children(proc.pid);save(d/'watchdog.json',before);proc.kill();raise RuntimeError('external watchdog; never a passing visit')
    try:
     ctl=fixture/'foo/control';f=ctl/'slow-active';st=f.stat();now_tag=f.read_text()
     if st.st_mtime_ns>=beg and not (ctl/'a-timing').exists() and 'print!("new")' in (fixture/'foo/a/src/main.rs').read_text():
      if now_tag!=tag:tag=now_tag;clock=time.monotonic()
      if not sample and time.monotonic()-clock>2.15:
       rows=children(proc.pid)
       if int(now_tag) in rows:
        report=diag.stacks(d,rows,fixture);save(d/'stall.json',report);sample=True
    except (FileNotFoundError,ValueError):pass
    time.sleep(.09)
  output=(d/'stdout').read_bytes();error=(d/'stderr').read_bytes();raw=(output+error).decode(errors='replace');ctl=control(fixture)
  assert (NAME+' ... ') in raw and 'running 1 test' in raw
  ok=proc.returncode==0 and '1 passed; 0 failed; 0 ignored;' in raw
  expected_timeout=proc.returncode==101 and 'ready test never started' in raw and 'could not compile `z`' in raw
  extra={};ft=fixture/'foo/target/debug'
  if ok:
   assert {k:ctl[k]['body'] for k in ('runs','a-timing','current-binary','slow-finished','z-ran')}=={'runs':'a\n','a-timing':'during','current-binary':'yes','slow-finished':'yes','z-ran':'yes'},ctl
   values=[p.read_text() for p in ft.glob('build/a-*/out/value')];assert values==['new']
   a=ft/'a';reader=subprocess.run([a],cwd=fixture/'foo',capture_output=True);assert (reader.returncode,reader.stdout,reader.stderr)==(0,b'new',b'')
   assert not (ft/'disabled').exists();extra={'new_program_sha':ph(a),'new_program_output':'new','value':values,'disabled_binary_absent':True}
  snapshot=diag.fixture_snapshot(fixture)
  save(d/'snapshot.json',snapshot)
  result={'role':role,'block':block+1,'exit':proc.returncode,'ok':ok,'same_15s_z_timeout':expected_timeout,'other_failure':not (ok or expected_timeout),'late_sample':sample,'control':ctl,'extra':extra,'stdout_sha':h(output),'stderr_sha':h(error)}
  save(d/'result.json',result);summary[role].append(result);print(role,block+1,proc.returncode,ok,expected_timeout,flush=True)
save(OUT/'complete.json',{'actual':summary,'test':NAME,'n':sum(map(len,summary.values())),'fixture_unmodified':all(ph(t[0]/F)==HASH for t in roles.values()),'unknown':sum(y['other_failure'] for values in summary.values() for y in values)})
assert not any(y['other_failure'] for values in summary.values() for y in values)
