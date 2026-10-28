from pathlib import Path
import fcntl,hashlib,json,os,shutil,signal,subprocess as sp,time
H=Path('/home/dev-user/.cache/ohm-output-path-pgo-20261028');Y=Path('/mnt/devbox-scratch/dev-user/ohm-producer-attestation-pinned-20261028')
orig=(Y/'build.py').read_text();lib=orig[:orig.index("assert (X/'complete.json').is_file()")];envpart=orig[orig.index('env=dict(os.environ'):orig.index("with (D.parent/'ohm-spaced-ruff-20261027")]
g={};exec(lib,g);exec(envpart,g);g['STATE']=H/'state';X,D,S,CAN,src0,env=(g[k] for k in ('X','D','S','CAN','src0','env'));lock=D.parent/'ohm-spaced-ruff-20261027/matched-qualify.lock'
sha,save,data,compile_rows,commonrows=(g[k] for k in ('sha','save','data','compile_rows','commonrows'))
with lock.open('a') as f:
 fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);assert shutil.disk_usage(H).free>100*2**30
 frozen=data(H/'source.json');base=data(X/'inputs/A.json');assert base['commit']==frozen['base']=='a0c7d08c898d3fdff992f2f431dec57d2486add2'
 assert sha(D/'assets/rustc-pgo.profdata')=='481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7'
 assert sha(H/'product.patch')==frozen['patch']
 for n,m,oid in base['files']:
  p=src0/n;buf=os.fsencode(os.readlink(p)) if m=='120000' else p.read_bytes()
  assert hashlib.sha1(f'blob {len(buf)}\0'.encode()+buf).hexdigest()==oid,n
 for n,h in frozen['source_sha256'].items():assert sha(H/'new'/n)==h
 ns=g['STATE']
 assert (H/'parent/actual-inputs.json').exists() and not (H/'parent/receipt.json').exists()
 seeded=commonrows(data(H/'parent/actual-inputs.json'));ref=None
 for arm in ('parent','candidate'):
  w=H/('qualified-'+arm);w.mkdir();saved=w/'retained-prior';saved.mkdir();units=set()
  for lab in ('lib-cargo','bin-cargo'):
   for p in (ns/'target/release/build/workspaces').rglob(lab):
    assert p.parent.name=='fingerprint' and p.parent.parent.parent.name=='cargo';units.add(p.parent.parent)
  assert len(units)==2
  for j,p in enumerate(sorted(units)):p.rename(saved/(str(j)+'-'+p.name))
  cmd=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',src0,CAN]
  if arm=='candidate':
   for n in frozen['source_sha256']:cmd+=['--ro-bind',H/'new'/n,CAN/n]
  for name in ('target','shared','cargo-home'):cmd+=['--bind',ns/name,S/name]
  cmd+=['--chdir',CAN,'--','taskset','-c','8-23','/home/dev-user/.cargo/bin/cargo','+ohm','build','--release','--offline','--locked','-p','cargo','--bin','cargo','--features','ohm-defaults','-j12']
  with (w/'build.log').open('wb') as output:
   proc=sp.Popen(['strace','-f','-qq','-s','65535','-e','trace=execve,execveat','-o',w/'compiler.exec',*cmd],env=env,stdout=output,stderr=sp.STDOUT,start_new_session=True)
   while proc.poll() is None:
    if shutil.disk_usage(H).free<80*2**30:os.killpg(proc.pid,signal.SIGTERM);proc.wait();raise RuntimeError('storage floor')
    time.sleep(.5)
  assert proc.returncode==0,(arm,(w/'build.log').read_text()[-1900:])
  rows,jobs=compile_rows(w,arm);save(w/'actual-inputs.json',rows)
  assert jobs==[('cargo','bin'),('cargo','lib')],(jobs,arm)
  if ref is None:ref=commonrows(rows)
  assert commonrows(rows)==ref,(arm,'common inputs differ')
  assert commonrows(rows)==seeded,(arm,'non-subject input changed after private seed')
  shutil.copy2(ns/'target/release/cargo',w/'cargo')
  vv=sp.check_output([w/'cargo','-Vv'],text=True);assert vv==data(Y/'A/receipt.json')['version']
  info=dict(arm=arm,sha256=sha(w/'cargo'),jobs=jobs,profile=sha(D/'assets/rustc-pgo.profdata'),compiler=sha(D/'assets/stock16-sdk/bin/rustc'),common_inputs=hashlib.sha256(json.dumps(ref,sort_keys=True,separators=(',',':')).encode()).hexdigest(),source=frozen['source_sha256'] if arm=='candidate' else {},source_baseline=frozen['base'],version=vv,inputs=sha(w/'actual-inputs.json'),command=list(map(str,cmd)),log=sha(w/'build.log'),compiler_exec=sha(w/'compiler.exec'))
  save(w/'receipt.json',info);print(arm,info['sha256'],flush=True)
 save(H/'qualified-pair.json',{a:data(H/('qualified-'+a)/'receipt.json') for a in ('parent','candidate')})
