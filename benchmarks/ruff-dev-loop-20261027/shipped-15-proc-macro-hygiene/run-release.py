"""Exercise zero-parse hygiene context controls on the authenticated shipping installation."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

here = Path(__file__).resolve().parent
host = 'charlie-ohm-relink-perf-1024'
top = '/dev/shm/ohm-packaged-15-macro-20261027'
fixture = (here / 'hygiene-sites.py').read_bytes()
digest = hashlib.sha256(fixture).hexdigest()
assert digest == '605856ac0d151978f46100a0cec3de93625cad73c3d9557fcdd7432bbab648a2'
mode, = sys.argv[1:]
remote = '''
import hashlib, json, os, shutil, socket, subprocess, sys
from pathlib import Path
t = Path(sys.argv[1]); expected = sys.argv[2]
assert socket.gethostname() == 'charlie-ohm-relink-perf-1024'
os.sched_setaffinity(0, {28, 29}); os.nice(12)
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def load(p): return json.loads(p.read_bytes())
assert shutil.disk_usage(t).free > 8 << 30
sdk = t/'installed-sdk'; installation = load(t/'installed.json')
tcargo = sdk/'bin/cargo'; td, = (sdk/'lib').glob('librustc_driver-*.so')
assert sha(tcargo) == installation['cargo'] and sha(td) == installation['driver']
r = t/'no-parse-hygiene-sites-v1'
'''
command = ['dbox', 'ssh', host, '--no-tmux', '--', '/usr/bin/python3', '-B', '-c']
if mode == 'run':
    code = remote + '''
r.mkdir(mode=0o700)
f = r/'hygiene-sites.py'; f.write_bytes(sys.stdin.buffer.read()); assert sha(f) == expected
env = {'HOME':str(Path.home()),'PATH':str(Path.home()/'.cargo/bin')+':/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','RUSTUP_AUTO_INSTALL':'0'}
args = [sys.executable, '-B', str(f), '--report-old-semantics', '--out', str(r/'run'), '--rustup', str(t/'rustup'), '--sysroot', str(sdk), '--cargo', str(tcargo), '--driver', str(td), '--driver-soname', td.name]
with (r/'stdout').open('xb') as so, (r/'stderr').open('xb') as se:
    cmd=subprocess.run(args, stdout=so, stderr=se, env=env)
(r/'exit').write_text(str(cmd.returncode))
if cmd.returncode:
    print((r/'stderr').read_text()[-2400:]);sys.exit(cmd.returncode)
data=load(r/'run/evidence/results.json')
print(json.dumps({k: {name: [v['compiler_status'], v['runtime']] for name, v in g['readers'].items()} for k,g in data.items()}))
'''
    out = subprocess.run([*command, code, top, digest], input=fixture, capture_output=True)
    (here/'release-stdout').write_bytes(out.stdout)
    (here/'release-stderr').write_bytes(out.stderr)
    print(out.stdout.decode()[-2500:], out.stderr.decode()[-500:], flush=True)
    sys.exit(out.returncode)
elif mode == 'collect':
    code = remote + '''
import gzip, io, tarfile
assert (r/'exit').read_text() == '0' and sha(r/'hygiene-sites.py') == expected
ev=r/'run/evidence'
with gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',mtime=0) as z, tarfile.open(fileobj=z,mode='w|') as tar:
    for p in sorted(ev.rglob('*')):
        if p.is_file() and p.name not in ('app','libbridge.rlib'):
            tar.add(p,arcname=str(p.relative_to(ev)),recursive=False)
'''
    data = subprocess.check_output([*command, code, top, digest])
    (here/'release-evidence.tar.gz').write_bytes(data)
    import tarfile
    out = here/'shipping-baseline'
    out.mkdir(mode=0o700)
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tar:
        assert all(m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in tar)
        tar.extractall(out,filter='data')
    print('Shipping zero-parse hygiene control', len(data), hashlib.sha256(data).hexdigest())
else:
    raise ValueError(mode)
