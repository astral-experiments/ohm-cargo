"""Small authentic registry ron first-observer probe; unscored, two completely disjoint targets."""
from pathlib import Path
import hashlib,json,os,re,shutil,signal,subprocess as s,sys,time,tomllib
N=Path(__file__).resolve().parent;D=N.parent; R=N/'ron-native-probe-v3';H=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/registry-home');WT=Path('/home/dev-user/code/oss/ruff-ohm-whole-native-20261027');sha=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
if sys.argv[1]=='inside':
 arm=sys.argv[2];x=R/arm;code=x/'code';e=dict(os.environ,PATH='/home/dev-user/.cargo/bin:'+os.environ['PATH'],CARGO_HOME=str(x/'home'),CARGO_BUILD_BUILD_DIR=str(x/'shared'),CARGO_TARGET_DIR=str(x/'target'),RUSTUP_HOME=str(N/({'A':'A-common','N':'N-common'}[arm])/'rustup'),CARGO_BUILD_JOBS='3',CARGO_NET_OFFLINE='true')
 for v in ('RUSTUP_TOOLCHAIN','RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST','CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST'):e.pop(v,None)
 m=s.run(['cargo','+ohm','metadata','--offline','--format-version','1'],cwd=code,env=e,capture_output=True);(x/'metadata.stdout').write_bytes(m.stdout);(x/'metadata.stderr').write_bytes(m.stderr);assert m.returncode==0,m.stderr[-1000:]
 meta=json.loads(m.stdout);ron,=[v for v in meta['packages'] if v['name']=='ron'];assert ron['version']=='0.12.0'
 fixed={};sdk=(Path(e['RUSTUP_HOME'])/'toolchains/ohm').resolve()
 for label in ('first','second','third'):
  o=x/label;o.mkdir();run=s.run(['strace','-f','-qq','-s','16000','-e','trace=execve','-o',str(o/'exec'),'cargo','+ohm','test','--no-run','--offline','--locked','--message-format=json'],cwd=code,env=e,capture_output=True);(o/'stdout.jsonl').write_bytes(run.stdout);(o/'stderr').write_bytes(run.stderr);assert run.returncode==0,run.stderr[-1500:]
  arts=[v for l in run.stdout.splitlines() if (v:=json.loads(l)).get('reason')=='compiler-artifact'];execs={x['target']['name']:Path(x['executable']) for x in arts if x.get('executable')}
  assert set(execs)=={'ron_guard_case','test_1','test_2','test_3','test_4'},execs
  programs={}
  for name,path in execs.items():
   rr=s.run([path,'--list'],capture_output=True,check=True); program={'sha256':sha(path),'tests':rr.stdout.decode()}
   if name.startswith('test_'):assert 'ordinary_ron_reader: test' in program['tests'];t=s.run([path,'--exact','ordinary_ron_reader'],capture_output=True,check=True);assert '1 passed' in t.stdout.decode();program['passes']=True
   programs[name]=program
  storage=[x/'shared',x/'target'];proofs=[f for a in storage for f in a.rglob('dep-lib-ron') if b'ohm-foreign-span-bytes' in f.read_bytes()];assert len(proofs)==1,[str(v) for v in proofs]
  fp=proofs[0].read_bytes();dep,=(proofs[0].parent.parent/'out').glob('ron*.d');body=dep.read_bytes();(o/'fingerprint.bin').write_bytes(fp);(o/'compiler.d').write_bytes(body)
  raw=(o/'exec').read_text();jobs=[];queries=0;links=[]
  for line in raw.splitlines():
   if 'execve(' not in line or not line.endswith('= 0'):continue
   proc=re.search(r'execve\("([^"]+)"',line)
   if not proc:continue
   executable=Path(proc.group(1))
   if executable.name=='rustc' and executable.is_absolute() and executable.is_file() and executable.samefile(sdk/'bin/rustc'):
    if '"-Zohm-observer-dep-info", "--print=sysroot"' in line:queries+=1
    m=re.search(r'"--crate-name", "([^"]+)"',line)
    if m and '"--print=' not in line:jobs.append((m.group(1),'relink' if '"-Zlink-only"' in line else 'full'))
   if executable.name in ('ld','ld.bfd','ld.lld','wild','rust-lld') and '"-o"' in line:links.append([str(executable),sha(executable)])
  fixed[label]={'units':len(arts),'fresh':sum(v['fresh'] for v in arts),'jobs':jobs,'links':links,'queries':queries,'complete':fp[-33],'optional':b'# ohm-observer-inputs-v1 ' in body,'ordinary_checksums':len([v for v in body.splitlines() if v.startswith(b'# checksum:')]),'programs':programs,'cargo':sha(sdk/'bin/cargo'),'driver':sha(sdk/'lib/librustc_driver-774a793a844d5500.so')}
  (x/'result.json').write_text(json.dumps(fixed,indent=2)+'\n');print(arm,label,fixed[label]['fresh'],len(arts),jobs,len(links),fp[-33],flush=True)
 assert fixed['first']['complete']==int(arm=='N') and fixed['first']['optional'] and fixed['second']['complete']==fixed['third']['complete']==1
 assert fixed['first']['queries']==fixed['second']['queries']==fixed['third']['queries']==0
 assert (not fixed['second']['jobs'])==(arm=='N') and not fixed['third']['jobs'] and not fixed['third']['links']
 sys.exit()
R.mkdir()
(R/'preflight.json').write_text(json.dumps({'ruff_commit':s.check_output(['git','-C',WT,'rev-parse','HEAD'],text=True).strip(),'source_lock':sha(WT/'Cargo.lock'),'floor':3*2**30,'initial_bytes_free':shutil.disk_usage(N).free,'classification':'unscored constructed registry fixture, real locked ron 0.12.0, no Ruff changes, separate Cargo processes and four test products'},indent=2)+'\n')
for arm in ('A','N'):
 x=R/arm;x.mkdir();code=x/'code';(code/'src').mkdir(parents=True);(code/'tests').mkdir();(x/'home').mkdir();(x/'target').mkdir();(x/'shared').mkdir()
 (code/'Cargo.toml').write_text('[package]\nname="ron_guard_case"\nversion="0.0.0"\nedition="2021"\n[dependencies]\nron="=0.12.0"\n[profile.dev]\nopt-level=1\ndebug="line-tables-only"\n')
 (code/'src/lib.rs').write_text('pub fn check(value:u32)->String{ron::to_string(&value).unwrap()}\n');shutil.copy2(WT/'Cargo.lock',code/'Cargo.lock')
 for t in range(1,5):(code/'tests'/f'test_{t}.rs').write_text(f'#[test] fn ordinary_ron_reader() {{assert_eq!(ron_guard_case::check({t}),"{t}");}}\n')
 args=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--ro-bind','/dev/shm','/dev/shm','--tmpfs','/tmp','--bind',str(x),str(x)]
 for area in ('index','cache'):
  real,=[a for a in (H/'registry'/area).iterdir() if a.is_dir()];dest=x/'home/registry'/area/real.name;dest.mkdir(parents=True); args+=['--ro-bind',str(real),str(dest)]
 args+=['--','taskset','-c','0-3','python3','-B',__file__,'inside',arm]
 job=s.Popen(args,start_new_session=True)
 while job.poll() is None:
  if shutil.disk_usage(N).free<3*2**30:os.killpg(job.pid,signal.SIGTERM);job.wait();raise RuntimeError('3GiB storage stop')
  time.sleep(.35)
 assert job.returncode==0,arm
