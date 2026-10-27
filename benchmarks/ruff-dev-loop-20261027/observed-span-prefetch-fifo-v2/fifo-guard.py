"""Bound and trace one full Cargo command across a real regular-to-FIFO transition. No FIFO writer."""
import argparse,ctypes,hashlib,json,os,re,shutil,signal,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--cargo',type=Path,required=True);p.add_argument('--expect',choices=('blocked','rejected'),required=True);p.add_argument('--out',type=Path,required=True)
p.add_argument('--cpus',default='26,27');p.add_argument('--downgrade',type=Path);p.add_argument('--runtime',type=Path,default=Path.home()/'.cache/ohm-build-cutoff-20261027/unused-link-audit-20261027/candidate-runtime')
p.add_argument('--fixture',type=Path,default=Path.home()/'.cache/ohm-ruff-cargo-link-skip-20261027/native-span-observer/heldout-fixture')
a=p.parse_args();src=Path(__file__).resolve().parent;root=a.out.resolve();root.mkdir(exist_ok=False);subject=a.cargo.resolve();rt=a.runtime.resolve()
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def emit(name,data):(root/name).write_text(json.dumps(data,indent=2)+'\n')
def swap(first,second):
    libc=ctypes.CDLL(None,use_errno=True);assert libc.renameat2(-100,os.fsencode(first),-100,os.fsencode(second),2)==0,ctypes.get_errno()
def make_link(path,target):
    temp=path.with_suffix('.switching');temp.symlink_to(target);os.replace(temp,path)
tc=root/'sys';(tc/'bin').mkdir(parents=True);make_link(tc/'bin/cargo',subject);(tc/'bin/rustc').symlink_to(rt/'bin/rustc');(tc/'lib').symlink_to(rt/'lib')
h=root/'rustup';(h/'toolchains').mkdir(parents=True);(h/'toolchains/ohm').symlink_to(tc);(h/'settings.toml').write_text('version = "12"\ndefault_toolchain = "ohm"\n')
for n in ('target','shared','data'):(root/n).mkdir()
shutil.copytree(a.fixture,root/'src')
env={k:v for k,v in os.environ.items() if not k.startswith(('CARGO_','RUSTC','RUSTUP_')) and k not in ('RUSTFLAGS','LD_PRELOAD','LD_LIBRARY_PATH','MAKEFLAGS','BASH_ENV')}
env.update(RUSTUP_HOME=str(h),RUSTUP_TOOLCHAIN='ohm',RUSTUP_AUTO_INSTALL='0',RUSTC=str(rt/'bin/rustc'),CARGO_HOME=str(root/'data'),CARGO_TARGET_DIR=str(root/'target'),CARGO_BUILD_BUILD_DIR=str(root/'shared'),CARGO_BUILD_JOBS='1',CARGO_TERM_COLOR='never')
subject_sha=sha(subject);driver=next((rt/'lib').glob('librustc_driver-*.so'));assert sha(driver)=='dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f'
assert str(driver.resolve())==str(Path(next(l for l in subprocess.check_output(['/usr/bin/ldd',rt/'bin/rustc'],text=True).splitlines() if 'librustc_driver' in l).split('=>')[1].split()[0]).resolve())
prefix=['taskset','-c',a.cpus,str(Path.home()/'.cargo/bin/cargo'),'+ohm']
subprocess.run([*prefix,'generate-lockfile','--offline'],cwd=root/'src',env=env,check=True,capture_output=True)
cmd=[*prefix,'build','-p','hold_direct','--offline','--locked','-j1','-vv','--message-format=json']
compile_shim=['cc','-shared','-fPIC','-O2','-Wall','-o',root/'flip.so',src/'flip-stat.c','-ldl']
subprocess.run(compile_shim,capture_output=True,check=True)
def collect(text):
    return [('full' if 'link-only' not in l else 'link',l.split('--crate-name ',1)[1].split(' ',1)[0]) for l in text.splitlines() if 'Running ' in l and '--crate-name ' in l]
def run(name):
    z=subprocess.run(cmd,env=env,cwd=root/'src',capture_output=True,timeout=65);(root/(name+'.err')).write_bytes(z.stderr);(root/(name+'.out')).write_bytes(z.stdout);assert z.returncode==0,z.stderr.decode(errors='replace')[-450:]
    return collect(z.stderr.decode())
initial=[run('prime1'),run('prime2'),run('prime3')];assert initial[-1]==[],initial
proof=next(f for f in (root/'target').rglob('dep-bin-hold_direct') if b'OBS1' in f.read_bytes())
record=proof.read_bytes();assert record[-41:-37]==b'OBS1' and record[-33]==1
rfile=next(f for f in (root/'target').rglob('libhold_shapes-*.rlib') if os.fsencode(f) in record);archive_sha=sha(rfile)
regular=rfile.with_suffix('.rlib.known-regular');rfile.rename(regular);rfile.symlink_to(regular.name)
symlink_roster=[run('symlink1'),run('symlink2')];assert not symlink_roster[-1] and sha(rfile)==archive_sha,symlink_roster
app=root/'target/debug/hold_direct';expected=subprocess.check_output([app]).decode().strip()
events=root/'events';events.touch();fifo=root/'fifo-replacement';os.mkfifo(fifo);extra=env|dict(LD_PRELOAD=str(root/'flip.so'),OBS_FIFO_PATH=str(rfile),OBS_FIFO_CARGO=str(subject),OBS_FIFO_READY=str(fifo),OBS_FIFO_LOG=str(events),OBS_FIFO_AT_STAT='2')
witness=None;hit=None;t0=time.monotonic();timed_out=False;exception=None
with (root/'race.err').open('wb') as err,(root/'race.out').open('wb') as out:
    proc=subprocess.Popen(cmd,cwd=root/'src',env=extra,stdout=out,stderr=err,start_new_session=True)
    try:
        while proc.poll() is None and time.monotonic()-t0<8:
            txt=events.read_text();mm=re.search(r'^switch pid=(\d+)',txt,re.M)
            if mm:
                pid=int(mm[1]);hit=hit if hit is not None else time.monotonic()
                if time.monotonic()-hit>.30 and witness is None:
                    linux=Path('/proc')/str(pid)
                    if linux.is_dir():
                        try:witness={'exe':str((linux/'exe').resolve()),'wchan':(linux/'wchan').read_text().strip(),'syscall':(linux/'syscall').read_text().split()[:4],'fifo':rfile.is_fifo()}
                        except (PermissionError,FileNotFoundError):pass
                if time.monotonic()-hit>1.6:
                    timed_out=True;os.killpg(proc.pid,signal.SIGKILL);break
            time.sleep(.01)
        if proc.poll() is None and not timed_out:
            exception='eight-second preflight bound';os.killpg(proc.pid,signal.SIGKILL)
        code=proc.wait(timeout=4)
    finally:
        # No code in the watcher ever opens the FIFO for writing.
        if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        if rfile.is_fifo():swap(rfile,fifo)
assert exception is None,exception
assert rfile.is_symlink() and (rfile.parent/os.readlink(rfile)).resolve()==regular and sha(rfile)==archive_sha
txt=events.read_text();flags=[int(v,16) for v in re.findall(r'^opening pid=\d+ status=\d+ flags=(0x[0-9a-f]+)',txt,re.M)]
msgs=[json.loads(l)['message']['message'] for l in (root/'race.out').read_text().splitlines() if l.startswith('{') and json.loads(l).get('reason')=='compiler-message']
assert '^switch' not in txt and re.search(r'^switch ',txt,re.M)
if a.expect=='blocked':
    assert timed_out and witness and witness['wchan']=='wait_for_partner' and witness['exe']==str(subject) and flags and not(flags[0]&os.O_NONBLOCK), (timed_out,witness,flags,code)
else:
    assert not timed_out and flags and flags[0]&os.O_NONBLOCK and flags[0]&os.O_NOCTTY,(timed_out,witness,flags)
    assert code!=0 and any('extern location for hold_shapes is not a file' in m for m in msgs),(code,msgs)
recovery=run('recovery');assert subprocess.check_output([app]).decode().strip()==expected
downgrade=None
if a.downgrade:
    legacy=a.downgrade.resolve();make_link(tc/'bin/cargo',legacy)
    legacy_roster=[run('legacy1'),run('legacy2')];assert ('full','hold_direct') in legacy_roster[-1]
    assert subprocess.check_output([app]).decode().strip()==expected
    make_link(tc/'bin/cargo',subject)
    return_roster=[run('upgrade1'),run('upgrade2'),run('upgrade3')];assert not return_roster[-1] and subprocess.check_output([app]).decode().strip()==expected
    downgrade={'cargo_sha':sha(legacy),'old':legacy_roster,'return':return_roster,'output':expected}
frames=[]
for addr in re.findall(r'/cargo\(\+(0x[0-9a-f]+)\)',txt):
    frames.append(subprocess.run(['addr2line','-Cfpe',str(subject),addr],text=True,capture_output=True).stdout.strip())
summary={'cargo_sha256':subject_sha,'driver_sha256':sha(driver),'subject':str(subject),'prior_proof_sha':sha(proof),'initial_complete':True,'input':str(rfile),'input_sha256':archive_sha,'initial':initial,'symlink':symlink_roster,'no_writer_ever':True,'timed_out_in_open':timed_out,'kernel_witness':witness,'open_flags':flags,'command_returncode':code,'diagnostics':msgs,'roster':collect((root/'race.err').read_text()),'recovery_roster':recovery,'programs_equal':True,'program_stdout':expected,'downgrade':downgrade,'stack':frames}
emit('summary.json',summary)
print('gate',a.expect,subject_sha[:10],'accepted','flags',flags,'downgrade',bool(downgrade),flush=True)
