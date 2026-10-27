"""Trace an independent cold/first/settled history on the unmodified published release."""
from pathlib import Path
import fcntl,json,hashlib,os,shutil,subprocess,sys,time
p=Path('/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027');r=p/'ohm-current-16-qualification-v1'
sys.path.insert(0,str(p/'runner'));sys.path.insert(0,str(p/'ron-first-shipping-20261027/bound-runner-641fda0d'))
from shared import env,skeleton,CH,TARGET,BUILD,WT,FROZEN,floors,sha,git
import qualification as prior
from roster import audit_json
spec=json.loads((r/'installation.json').read_bytes());st=r/'state';out=r/'receipts'
def save(f,v):f.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
if len(sys.argv)==1:
 with (p/'bench.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);floors(16<<30);st.mkdir(mode=0o700);out.mkdir(mode=0o700)
  for n in ('target','build','home'):(st/n).mkdir(mode=0o700)
  shutil.copytree(p/'rustup',st/'rustup',symlinks=True);subprocess.run(['cp','-a','--reflink=auto','--',str(CH/'registry'),str(st/'home/registry')],check=True)
  for n in ('config','config.toml'):
   if (CH/n).is_file():shutil.copy2(CH/n,st/'home'/n)
  op=skeleton(st)
  for a,b in ((out,out),(st/'target',TARGET),(st/'build',BUILD),(st/'home',CH),(st/'rustup',p/'rustup')):op+=['--bind',str(a),str(b)]
  op+=['--ro-bind',str(r/spec['base_relative']),str(FROZEN)]
  e=env();del e['CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST'],e['CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST'];e['CARGO_LOG']='cargo::compiler::fingerprint=info'
  subprocess.run([*op,'--','taskset','-c','0-23',sys.executable,'-Bu',__file__,'inside'],cwd=WT,env=e,check=True)
 sys.exit()
assert sha(FROZEN/'bin/cargo')==spec['cargo'] and sha(FROZEN/'bin/rustc')==spec['rustc'] and sha(FROZEN/'lib'/spec['driver_name'])==spec['driver'] and sha(FROZEN/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd')==spec['wild']
assert not any(TARGET.iterdir()) and not any(BUILD.iterdir()) and git('rev-parse','HEAD').decode()=='93526150df078af7dd8fc4226cdcc469539d2001' and not git('status','--porcelain')
ver={k:subprocess.check_output(v,text=True).strip() for k,v in [('cargo',['cargo','+ohm','--version']),('rust',['rustc','+ohm','-vV'])]};assert ver['cargo']==spec['cargo_report'] and ver['rust']==spec['rustc_report'];save(out/'version.json',ver)
rows={}
for phase in ('cold','first','settled'):
 d=out/phase;d.mkdir();floors();start=time.monotonic_ns()
 with (d/'stdout').open('xb') as so,(d/'stderr').open('xb') as se:
  cp=subprocess.run(['strace','-ff','-qq','-s','262144','-e','trace=execve,execveat','-o',str(d/'exec'),'cargo','+ohm','test','--no-run','--locked','--offline','--message-format=json'],cwd=WT,stdout=so,stderr=se)
 dur=time.monotonic_ns()-start;save(d/'status.json',{'returncode':cp.returncode,'unscored_traced_ns':dur});assert cp.returncode==0
 j=audit_json(d/'stdout','test');procs=prior.parsed(d,j);save(d/'processes.json',procs);arts=[x for z in (d/'stdout').read_bytes().splitlines() if (x:=json.loads(z)).get('reason')=='compiler-artifact']
 files={prior.relocate(x):prior.elf(Path(x)) for x in j['elf']};save(d/'native.json',files)
 ron,=[x for x in arts if x['target']['name']=='ron'];rl,=[Path(x) for x in ron['filenames'] if x.endswith('.rlib')];di,=rl.parent.glob('ron-*.d');fp=rl.parent.parent/'fingerprint/dep-lib-ron';raw=fp.read_bytes() if fp.is_file() else b'';code=raw.rfind(b'OBS1')
 ps={'full':[x[1] for x in procs['rustc'] if x[2]=='full'],'relink':[x[1] for x in procs['rustc'] if x[2]=='link-only'],'wild':sum(v[2] for v in procs['native_links']),'system':sum(not v[2] for v in procs['native_links'])}
 row={'units':len(arts),'fresh':sum(x['fresh'] for x in arts),'executables':len(j['executables']),'native_files':len(files),'raw_native_sha256':sha(d/'native.json'),'processes':ps,'stdout_sha256':sha(d/'stdout'),'stderr_sha256':sha(d/'stderr'),'ron_checksums':sum(l.startswith('# checksum:') for l in di.read_text().splitlines()),'ron_marker':code!=-1,'ron_complete':None if code<0 or len(raw)-code!=41 else bool(raw[code+8]),'ron_elf_archive':sha(rl),'ron_metadata':sha(rl.with_suffix('.rmeta'))}
 rows[phase]=row;save(d/'summary.json',row);print(phase,row['fresh'],len(ps['full']),len(ps['relink']),ps['wild'],row['ron_marker'],row['ron_complete'],flush=True)
native=prior.probes_native(j,dict(os.environ));assert not git('status','--porcelain');save(out/'complete.json',{'release':spec,'cases':rows,'runtime':native})
