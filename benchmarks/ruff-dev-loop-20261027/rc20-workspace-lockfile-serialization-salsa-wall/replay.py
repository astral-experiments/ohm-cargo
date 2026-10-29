"""Recreate fresh wall-time lanes from separately supplied, authenticated local inputs."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,socket,subprocess,sys,tarfile
parser=argparse.ArgumentParser(description=__doc__)
for n in ('study','physical','ruff','sdk','registry','parent-cargo','candidate-cargo'):parser.add_argument('--'+n,type=Path,required=True)
parser.add_argument('--cargo-config',type=Path,help='Optional local Cargo registry mapping for the supplied offline index.')
args=parser.parse_args();here=Path(__file__).resolve().parent
def save(p,obj):
 with p.open('x')as f:json.dump(obj,f,sort_keys=True,indent=1);f.write('\n')
def sha(f):
 with f.open('rb')as s:return hashlib.file_digest(s,'sha256').hexdigest()
def load(f):return json.loads(f.read_bytes())
p=args.study.resolve();physical=args.physical.resolve();assert os.geteuid()==1000 and Path('/').stat().st_uid==0 and not p.exists()and not physical.exists()
assert set(range(4))|{29,30}<=set(os.sched_getaffinity(0)) and shutil.disk_usage(p.parent).free>24*2**30 and shutil.disk_usage(physical.parent).free>16*2**30
plan=load(here/'protocol.json');t=plan['toolchain'];sdk=args.sdk.resolve()
assert sha(args.parent_cargo)==t['baseline']and sha(args.candidate_cargo)==t['candidate']and sha(sdk/'bin/rustc')==t['rustc']and sha(sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd')==t['wild']
p.mkdir(mode=0o700);lower=p/'template';empty=p/'empty-lower';view=p/'arena'
for d in (lower,empty,view):d.mkdir()
for k in ('worker.py','after.py','analyze.py','protocol.json','source-files.json'):shutil.copyfile(here/k,p/k)
for n in ('source','ru','products','shared','tmp','cargo-home'): (lower/n).mkdir()
git=subprocess.Popen(['git','-C',args.ruff,'archive',plan['historical']['ruff']],stdout=subprocess.PIPE)
with tarfile.open(fileobj=git.stdout,mode='r|')as tf:tf.extractall(lower/'source',filter='data')
assert git.wait()==0
for k,v in load(here/'source-files.json').items():assert sha(lower/'source'/k)==v
shutil.copytree(sdk,lower/'sdk',symlinks=False);(lower/'ru/toolchains').mkdir();(lower/'ru/toolchains/ohm').symlink_to(view/'sdk',target_is_directory=True)
(lower/'ru/settings.toml').write_text('version = "12"\nprofile = "minimal"\n\n[overrides]\n')
for n in ('index','cache','src'):
 f=args.registry.resolve()/n
 if f.is_dir():shutil.copytree(f,lower/'cargo-home/registry'/n,symlinks=False)
if args.cargo_config:shutil.copyfile(args.cargo_config,lower/'cargo-home/config.toml')
shutil.copyfile(here/'caller.rs',lower/'consumer.rs')
home=Path.home();cli_env=dict(HOME=str(home),USER=os.environ['USER'],LOGNAME=os.environ['LOGNAME'],PATH=str(home/'.cargo/bin')+':/usr/bin:/bin',RUSTUP_HOME=str(view/'ru'),CARGO_TARGET_DIR=str(view/'products'),CARGO_BUILD_BUILD_DIR=str(view/'shared'),CARGO_HOME=str(view/'cargo-home'),TMPDIR=str(view/'tmp'),CARGO_NET_OFFLINE='true',RUSTUP_AUTO_INSTALL='0',CARGO_TERM_COLOR='never',CARGO_CACHE_AUTO_CLEAN_FREQUENCY='never',TZ='UTC',LC_ALL='C.UTF-8')
save(p/'enrollment.json',{'env':cli_env});save(p/'binding.json',dict(host=socket.gethostname(),view=str(view),lower=str(lower),old_common=str(empty),physical=str(physical),prior_enrollment=str(p/'enrollment.json'),images={'A':str(args.parent_cargo.resolve()),'B':str(args.candidate_cargo.resolve())},source_file_digest=sha(p/'source-files.json'),program_cpu=[0,1,2,3],supervisor_cpu=[29,30],timer_cal_cpu=[2]))
for tag in ('admit','score'):
 with (p/(tag+'.stdout')).open('xb') as out,(p/(tag+'.stderr')).open('xb')as err:
  rc=subprocess.run(['/usr/bin/timeout','--signal=TERM','--kill-after=5s','900','/usr/bin/python3','-IB',p/'worker.py',tag],cwd=p,stdout=out,stderr=err).returncode
 (p/(tag+'.exit')).write_text(str(rc)+'\n');assert rc==0,(tag,rc)
subprocess.run(['/usr/bin/python3','-IB',p/'after.py'],cwd=p,check=True)
sys.path.insert(0,str(p));from analyze import calculate
out=[]
for row in plan['schedule']:
 out.append({**row,'arms':{a:load(p/'runs'/a/f"s{row['pair']:02d}"/'result.json')for a in row['order']}})
save(p/'replay-statistics.json',calculate(out,plan));print(p/'replay-statistics.json')
