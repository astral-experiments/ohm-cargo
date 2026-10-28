"""Rebuild #261 and its path-only port over exactly the same PGO library/native inputs."""
from pathlib import Path
import fcntl,hashlib,json,os,shutil,signal,subprocess as sp,time
H=Path(__file__).resolve().parent;F=Path('/home/dev-user/.cache/ohm-output-path-pgo-20261028');Y=Path('/mnt/devbox-scratch/dev-user/ohm-producer-attestation-pinned-20261028');original=(Y/'build.py').read_text();g={};exec(original[:original.index("assert (X/'complete.json').is_file()")],g);exec(original[original.index('env=dict(os.environ'):original.index("with (D.parent/'ohm-spaced-ruff-20261027")],g);g['STATE']=H/'state';X,D,S,CAN,src0,env=(g[k] for k in ('X','D','S','CAN','src0','env'));sha,store,load,compile_rows,common=(g[k] for k in ('sha','save','data','compile_rows','commonrows'));spec=load(H/'build-source.json');lock=D.parent/'ohm-spaced-ruff-20261027/matched-qualify.lock';private=H/'state'
with lock.open('a') as guard:
 fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB);assert shutil.disk_usage(H).free>100*2**30;assert sha(H/'base-objects.json')==spec['git_objects'] and sha(H/'port.patch')==spec['patch'] and spec['base']=='9a0170863f70d9a88a8b1d1f4c4e1fded4736a9c';assert sha(D/'assets/rustc-pgo.profdata')=='481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7'
 overlays=sorted(set(spec['base_changed_from_release'])|set(spec['port_sha256']));m=load(H/'base-objects.json');assert len(m)==spec['count'];assert {n:mode for n,mode,_ in m}=={n:mode for n,mode,_ in load(X/'inputs/A.json')['files']}
 for n,mode,oid in m:
  parent=H/'source-views/parent'/n if n in overlays else src0/n
  b=os.fsencode(os.readlink(parent)) if mode=='120000' else parent.read_bytes();assert hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()==oid and (mode=='120000' or bool(parent.stat().st_mode&0o100)==(mode=='100755')),n
  if n in overlays:
   c=H/'source-views/candidate'/n;assert sha(c)==spec['port_sha256'].get(n,sha(parent)),n
 for s in ('parent','candidate'):
  for n,v in (spec['base_sha256'] if s=='parent' else spec['port_sha256']).items():assert sha(H/'source-views'/s/n)==v
 private.mkdir()
 for k in ['target','shared','cargo-home']:sp.run(['cp','-a','--reflink=auto',F/'state'/k,private/k],check=True)
 assert (private/'target/release/cargo').stat().st_ino!=(F/'state/target/release/cargo').stat().st_ino;rows={};ref=None
 for stage,arm in [('seed','parent'),('parent','parent'),('candidate','candidate')]:
  w=H/stage;w.mkdir();saved=w/'previous-units';saved.mkdir();target=private/'target/release/build/workspaces';units={p.parent.parent for label in ('bin-cargo','lib-cargo') for p in target.rglob(label) if p.parent.name=='fingerprint' and p.parent.parent.parent.name=='cargo'};assert len(units)==2,(stage,units)
  for i,p in enumerate(sorted(units)):p.rename(saved/(str(i)+'-'+p.name))
  cmd=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',src0,CAN]
  for n in overlays:cmd+=['--ro-bind',H/'source-views'/arm/n,CAN/n]
  for k in ('target','shared','cargo-home'):cmd+=['--bind',private/k,S/k]
  cmd+=['--chdir',CAN,'--','taskset','-c','8-23','/home/dev-user/.cargo/bin/cargo','+ohm','build','--release','--offline','--locked','-p','cargo','--bin','cargo','--features','ohm-defaults','-j12']
  with (w/'build.log').open('xb') as out:
   proc=sp.Popen(['strace','-f','-qq','-s','65535','-e','trace=execve,execveat','-o',w/'compiler.exec',*cmd],env=env,stdout=out,stderr=sp.STDOUT,start_new_session=True)
   while proc.poll() is None:
    if shutil.disk_usage(H).free<80*2**30:os.killpg(proc.pid,signal.SIGTERM);proc.wait();raise RuntimeError('storage floor')
    time.sleep(.5)
  assert proc.returncode==0,(stage,(w/'build.log').read_text()[-1600:]);inputs,jobs=compile_rows(w,stage);store(w/'actual-inputs.json',inputs);stable=common(inputs);subj=w/'cargo';shutil.copy2(private/'target/release/cargo',subj);version=sp.check_output([subj,'-Vv'],text=True);assert version==load(F/'qualified-pair.json')['parent']['version'];common_sha=hashlib.sha256(json.dumps(stable,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  rows[stage]=dict(arm=arm,stage=stage,source=spec['base'],patch=None if arm=='parent' else spec['patch'],source_tree=spec['base_tree'],verified=spec['count'],source_objects=spec['git_objects'],source_views={n:sha(H/'source-views'/arm/n) for n in overlays},cargo=sha(subj),builder=sha(D/'assets/stock16-sdk/bin/rustc'),pgo=sha(D/'assets/rustc-pgo.profdata'),stamp=sha(D/'assets/git-commit-info-rc17'),version=version,common=common_sha,actual=sha(w/'actual-inputs.json'),trace=sha(w/'compiler.exec'),buildlog=sha(w/'build.log'),jobs=jobs,recipe=list(map(str,cmd)));store(w/'receipt.json',rows[stage]);print('built',stage,rows[stage]['cargo'],common_sha,len(jobs),flush=True)
  if stage=='seed':continue
  assert jobs==[('cargo','bin'),('cargo','lib')],jobs
  if ref is None:ref=stable
  else:assert stable==ref,'external inputs or compiler flags changed'
 assert rows['parent']['cargo']!=rows['candidate']['cargo'];store(H/'qualified-pair.json',rows);print('verified',sha(H/'qualified-pair.json'),flush=True)
