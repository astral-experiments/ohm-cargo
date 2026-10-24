import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/home/dev-user/ohm-loader-restack-20261024')

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def save(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def run(name, argv, *, cwd=ROOT, env=None, input_path=None):
    prefix = ROOT / 'logs' / name
    prefix.parent.mkdir(parents=True, exist_ok=True)
    inp, out, err = (Path(str(prefix) + suffix) for suffix in ('.stdin', '.stdout', '.stderr'))
    if input_path is None:
        inp.write_bytes(b'')
    else:
        inp = Path(input_path)
    save(str(prefix) + '.command.json', {'argv': argv, 'cwd': str(cwd), 'stdin': str(inp), 'started_at': utc()})
    with inp.open('rb') as fi, out.open('xb') as fo, err.open('xb') as fe:
        start = time.monotonic_ns()
        p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=fi, stdout=fo, stderr=fe)
        code = p.wait()
        elapsed = time.monotonic_ns() - start
    receipt = {'argv': argv, 'cwd': str(cwd), 'pid': p.pid, 'returncode': code,
               'elapsed_ns': elapsed, 'ended_at': utc(), 'stdout': str(out), 'stderr': str(err)}
    # Retain exit and elapsed evidence before any parsing or post-command hashing.
    save(str(prefix) + '.receipt.json', receipt)
    assert code == 0, (name, code)
    return out.read_bytes()
