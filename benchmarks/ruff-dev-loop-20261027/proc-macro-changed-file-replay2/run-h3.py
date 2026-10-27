"""Compare cache replay implementations at the same logical compiler and source paths on H3."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

here = Path(__file__).resolve().parent
source = (here/'changed-input.py').read_bytes()
expected = hashlib.sha256(source).hexdigest()
assert expected == 'e895739e87ee2f2481dc64ecd5237e39ad5772a3783a01dad62551c29e4f9da2'
mode, arm = sys.argv[1:]
assert arm in ('parent', 'replay1', 'replay2')
args = ['dbox','ssh','charlie-ohm-trait-perf-1024','--no-tmux','--','/usr/bin/python3','-B','-c']
common = '''
import fcntl, hashlib, io, json, os, shutil, socket, subprocess, sys
from pathlib import Path
assert socket.gethostname()=='charlie-ohm-trait-perf-1024'
os.sched_setaffinity(0,{28,29});os.nice(12)
arm,expected=sys.argv[1:]
p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
x=Path('/home/dev-user/.cache/ohm-233-position-qualified-20261027')
r=p/'macro-source-late-checkup-v2'; visible=r/'visible'; actual=r/arm
def digest(q):
    with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(q):return json.loads(q.read_bytes())
def dump(q,v):q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\\n')
parent='dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f'
sdk=p/'frozen-toolchain';rustup=p/'rustup'
cargo=x/'cargo-observer-fifo-qualification/guardv3'
cargo_hash='dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1'
candidate_dir={'replay1':'parse-source-replay-repeat1','replay2':'parse-source-replay-v2'}
'''
if mode == 'run':
    code = common + '''
assert shutil.disk_usage(p).free > 8<<30
if arm=='parent':
    fixture=sys.stdin.buffer.read()
    if not r.exists():
        r.mkdir(mode=0o700);visible.mkdir();(r/'changed-input.py').write_bytes(fixture)
    else:
        assert {f.name for f in r.iterdir()}=={'visible','changed-input.py'} and not list(visible.iterdir()) and (r/'changed-input.py').read_bytes()==fixture
    driver=x/'drivers'/('driver-'+parent);hashed=parent
else:
    import re
    sdkproof=p/candidate_dir[arm];marker=sdkproof/'verified.sha'
    assert marker.is_file() and (sdkproof/'receipt.json').is_file()
    hashed=marker.read_text().split()[0];assert re.fullmatch('[0-9a-f]{64}',hashed),hashed
    driver=sdkproof/'candidate-driver.so'
assert digest(r/'changed-input.py')==expected and digest(driver)==hashed
assert digest(cargo)==cargo_hash and digest(sdk/'bin/rustc')=='4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f'
soname,=[q.name for q in (sdk/'lib').glob('librustc_driver-*.so')]
lock=(r/'source-path.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert not (visible/'run').exists()
actual.mkdir(mode=0o700)
env={'HOME':str(Path.home()),'PATH':str(Path.home()/'.cargo/bin')+':/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','RUSTUP_AUTO_INSTALL':'0'}
cmd=[sys.executable,'-B',str(r/'changed-input.py'),'--out',str(visible/'run'),'--rustup',str(rustup),'--sysroot',str(sdk),'--cargo',str(cargo),'--driver',str(driver),'--driver-soname',soname]
dump(actual/'enrolled.json',{'driver_sha256':hashed,'fixture_sha256':expected,'cargo_sha256':digest(cargo),'argv':cmd,'affinity':sorted(os.sched_getaffinity(0))})
with (actual/'stdout').open('xb') as so,(actual/'stderr').open('xb') as se:
    proc=subprocess.run(cmd,stdout=so,stderr=se,env=env)
(visible/'run').rename(actual/'run')
(actual/'exit').write_text(str(proc.returncode))
if proc.returncode:
    print((actual/'stderr').read_text()[-2300:]);sys.exit(proc.returncode)
data=read(actual/'run/evidence/results.json')
print(json.dumps({k:{name:[v['compiler_status'],v['runtime']] for name,v in g['readers'].items()} for k,g in data.items()}))
'''
    proc = subprocess.run([*args,code,arm,expected],input=source,capture_output=True)
    (here/(arm+'-stdout')).write_bytes(proc.stdout)
    (here/(arm+'-stderr')).write_bytes(proc.stderr)
    print(proc.stdout.decode()[-2500:],proc.stderr.decode()[-500:],flush=True)
    sys.exit(proc.returncode)
elif mode == 'collect':
    code=common+'''
import gzip,tarfile
assert (actual/'exit').read_text()=='0' and digest(r/'changed-input.py')==expected
ev=actual/'run/evidence'
with gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',mtime=0) as z,tarfile.open(fileobj=z,mode='w|') as tf:
    for f in sorted(ev.rglob('*')):
        if f.is_file() and f.name not in ('app','libbridge.rlib'):tf.add(f,arcname=str(f.relative_to(ev)),recursive=False)
    tf.add(actual/'enrolled.json',arcname='enrolled.json',recursive=False)
'''
    data=subprocess.check_output([*args,code,arm,expected]);(here/(arm+'-evidence.tar.gz')).write_bytes(data)
    out=here/(arm+'-baseline');out.mkdir(mode=0o700)
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tf:
        assert all(m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in tf)
        tf.extractall(out,filter='data')
    print(arm,len(data),hashlib.sha256(data).hexdigest())
elif mode == 'ready':
    code=common+'''
sdkproof=p/candidate_dir[arm]
print(json.dumps({name:(sdkproof/name).is_file() for name in ('verified.sha','receipt.json','candidate-driver.so')}))
'''
    print(subprocess.check_output([*args,code,arm,expected],text=True),end='')
else:
    raise ValueError(mode)
