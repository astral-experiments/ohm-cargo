"""Untimed worker identities and returned jobserver tokens on the exact FIFO-safe subject."""
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paired import Study, getargs, log_json

study = Study(getargs())
real_run = subprocess.run

def with_thread_names(cmd, *args, **kwargs):
    if 'trace=execve' in cmd:
        cmd = list(cmd)
        cmd[cmd.index('trace=execve')] = 'trace=execve,prctl'
    return real_run(cmd, *args, **kwargs)

subprocess.run = with_thread_names
gold = study.run(study.init('independent-empty'), 'P', 'independent-empty', trace=True)
rows = {}

def observe(store, phase, env, same_elf=True):
    row = study.run(store, 'C', phase, trace=True, envadd=env)
    study.equivalent(row, gold, require_elf=same_elf)
    trace = gzip.decompress((study.logs / phase / 'exec.gz').read_bytes()).decode()
    helpers = sum('PR_SET_NAME, "cargo-checksum"' in line for line in trace.splitlines())
    rows[phase] = {'helpers': helpers, 'roster': row['roster'], 'products': row['native_products'],
                   'complete': [record['complete'] for _, record in sorted(row['readers'].items())]}
    return rows[phase]

store = study.init('four-jobs')
for i in range(4):
    last = observe(store, f'four-jobs-{i}', {})
assert not last['roster'] and last['helpers'] > 0 and last['complete'] == [True, True]

fifo = study.root / 'make-jobserver'
os.mkfifo(fifo)
fd = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
try:
    flags = f' -j --jobserver-auth=fifo:{fifo}'
    env = {'CARGO_MAKEFLAGS': flags, 'MAKEFLAGS': flags}
    for token in (False, True):
        if token:
            os.write(fd, b'+')
        result = observe(store, f'fifo-{int(token)}', env)
        assert (result['helpers'] > 0) == token and not result['roster']
        if token:
            assert os.read(fd, 1) == b'+'
finally:
    os.close(fd)

single = study.init('one-job')
for i in range(4):
    last = observe(single, f'one-job-{i}', {'CARGO_BUILD_JOBS': '1'}, same_elf=False)
    assert last['helpers'] == 0
assert not last['roster'] and last['complete'] == [True, True]

log_json(study.logs / 'jobserver.json', {'subjects': study.digest, 'fifo_token_returned': True,
                                         'fresh_four_job_compares_raw_elf': True,
                                         'single_job_compares_runtime': True, 'observations': rows})
print(json.dumps({'helpers': {key: row['helpers'] for key, row in rows.items()}}))
