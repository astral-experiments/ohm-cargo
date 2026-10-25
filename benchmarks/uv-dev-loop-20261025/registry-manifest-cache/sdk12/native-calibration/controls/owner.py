import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path('/benchmark/native-study-01')
SOCKET = ROOT / 'control/tmux.sock'
os.umask(0o077)
os.sched_setaffinity(0, set(range(9, 16)))
job_path = Path(sys.argv[1])
job = json.loads(job_path.read_bytes())
name = job['name']
assert name.isascii() and name.replace('-', '').isalnum()
prefix = ROOT / 'records' / name
receipt = {'state': 'running', 'owner_pid': os.getpid(), 'job_sha256': hashlib.sha256(job_path.read_bytes()).hexdigest(), 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'commands': []}
failure = None
try:
    for row in job['files']:
        assert hashlib.sha256(Path(row['path']).read_bytes()).hexdigest() == row['sha256'], row['path']
    with Path(str(prefix) + '.started.json').open('x') as f:
        json.dump(receipt, f, indent=2)
        f.write('\n')
    subprocess.run(['/usr/bin/tmux', '-S', str(SOCKET), 'wait-for', '-S', name + '-started'], check=True)
    for index, argv in enumerate(job['commands']):
        log = ROOT / 'logs' / (name + '-' + str(index))
        Path(str(log) + '.stdin').write_bytes(b'')
        with Path(str(log) + '.stdin').open('rb') as inp, Path(str(log) + '.stdout').open('xb') as out, Path(str(log) + '.stderr').open('xb') as err:
            proc = subprocess.Popen(argv, cwd=ROOT, stdin=inp, stdout=out, stderr=err)
            receipt['commands'].append({'argv': argv, 'pid': proc.pid})
            code = proc.wait()
            receipt['commands'][-1]['returncode'] = code
            assert code == 0, (index, code)
except BaseException as error:
    failure = {'type': type(error).__name__, 'message': str(error)}
    traceback.print_exc()
finally:
    receipt.update(state='complete' if failure is None else 'failed', failure=failure,
                   ended_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    with Path(str(prefix) + '.terminal.json').open('x') as f:
        json.dump(receipt, f, indent=2)
        f.write('\n')
    subprocess.run(['/usr/bin/tmux', '-S', str(SOCKET), 'wait-for', '-S', name + '-complete'], check=True)
raise SystemExit(0 if failure is None else 1)
