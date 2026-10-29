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
plan=load(here/'protocol.json');t=plan['root'];sdk=args.sdk.resolve()
assert sha(args.parent_cargo)==t['A']and sha(args.candidate_cargo)==t['B']and sha(sdk/'bin/rustc')=='5694abe50767a22cebeccb767143f7404d5e81c4b1760cff4426466bf410e511'and sha(sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd')=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
p.mkdir(mode=0o700);lower=p/'template';empty=p/'empty-lower';view=p/'arena'
for d in (lower,empty,view):d.mkdir()
for k in ('study.py','timed_study.py','controller.py','controller-v3.py','analysis_lint.py','mechanics.py','member_archive.py','member_archive_base.py','gates.py','wall.py','reopen.py','protocol.json','source.json','source-files.json'):shutil.copyfile(here/k,p/k)
for n in ('source','ru','products','shared','tmp','cargo-home'): (lower/n).mkdir()
git=subprocess.Popen(['git','-C',args.ruff,'archive',plan['root']['ruff']],stdout=subprocess.PIPE)
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
save(p/'enrollment.json',{'env':cli_env})
save(p/'layout.json',dict(host=socket.gethostname(),view=str(view),old_lower=str(lower),old_common=str(empty),allocation=str(physical),prior_enrollment=str(p/'enrollment.json'),rustc=sha(sdk/'bin/rustc'),wild=sha(sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd')))
(p/'images').mkdir()
for role,src in (('A',args.parent_cargo),('B',args.candidate_cargo)):shutil.copyfile(src,p/'images'/role)
def run(label,command,expect=0):
 with (p/(label+'.stdout')).open('xb')as out,(p/(label+'.stderr')).open('xb')as err:
  rc=subprocess.run(['/usr/bin/timeout','--signal=TERM','--kill-after=10s','1800','/usr/bin/taskset','-c','29,30','/usr/bin/python3','-IB',*command],cwd=p,stdout=out,stderr=err).returncode
 (p/(label+'.exit')).write_text(str(rc)+'\n');assert rc==expect,(label,rc)
run('native',['study.py','discover'])
sys.path.insert(0,str(p));from gates import gate
for sel in ('check','build','serde'):
 v=gate(p/'runs',sel);save(p/('eligibility-'+sel+'.json'),v);assert v['passed']
# Exercise the original mixed-pass debug assertion, keeping the new physical timer's own digest.
run('wall-admit',['controller.py','admit'],1)
assert (p/'wall-timer.kernel').is_file() and (p/'wall-admit.stderr').read_text().find('AssertionError:')>=0
save(p/'diagnostic-amendment.json',dict(timer_kernel=sha(p/'wall-timer.kernel')))
run('wall-admit-v3',['controller-v3.py','admit'])
for sel in ('check','build','serde'):run('score-'+sel,['controller-v3.py','score',sel])
save(p/'series-closure.json',{s:0 for s in ('check','build','serde')});(p/'series.exit').write_text('0\n');run('reopen',['reopen.py'])
from analysis_lint import all_results
z={}
for sel in ('check','build','serde'):
 z[sel]=[]
 for row in plan['schedule'][sel]:
  arms={a:load(p/'runs'/sel/row['from_state']/(a+'-slot'+str(row['pair']).zfill(2))/'measured/result.json')for a in row['order']}
  z[sel].append(dict(**row,arms=arms))
save(p/'replay-statistics.json',all_results(z,plan));print(p/'replay-statistics.json')
