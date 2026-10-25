"""Unchanged C0 native CPU/job admission and strict retained activity classifier."""
import os
from pathlib import Path
import time
from common import ROOT, PLAN, save, sha
from occupancy_observation import sample
PROTOCOL = {"host": os.uname().nodename}
PS_SHA256 = None

def host_sample():
    cpu = {}
    for line in Path('/proc/stat').read_text().splitlines():
        cols = line.split()
        if cols[0] in {f'cpu{i}' for i in range(8)}:
            ticks = [int(x) for x in cols[1:9]]
            cpu[cols[0]] = [sum(ticks), ticks[3] + ticks[4]]
    jobs = []
    for f in Path('/proc').glob('[0-9]*/stat'):
        try:
            s = f.read_text()
            end = s.rindex(')')
            name = s[s.index('(') + 1:end]
            if s[end + 2:].split()[0] == 'Z':
                continue
            if name in ('cargo', 'rustc', 'clang', 'gcc', 'cc1', 'cc1plus', 'rust-lld', 'ld', 'ld.lld', 'wild', 'ninja', 'make', 'perf') or name.startswith(('valgrind', 'callgrind')):
                if set(os.sched_getaffinity(int(f.parent.name))) & set(range(8)):
                    jobs.append([int(f.parent.name), name])
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
    return {'host': os.uname().nodename, 'monotonic_ns': time.monotonic_ns(), 'cpu': cpu, 'competing_jobs': jobs}

def require_quiet_start(log):
    samples = [host_sample()]
    for _ in range(3):
        time.sleep(1)
        samples.append(host_sample())
    save(log / 'host-admission.json', samples)
    for a, b in zip(samples, samples[1:]):
        assert a['host'] == b['host'] == PROTOCOL['host'] and not a['competing_jobs'] and not b['competing_jobs']
        assert len(a['cpu']) == len(b['cpu']) == 8
        total = sum(b['cpu'][c][0] - a['cpu'][c][0] for c in a['cpu'])
        idle = sum(b['cpu'][c][1] - a['cpu'][c][1] for c in a['cpu'])
        assert total > 0 and (total - idle) / total <= 0.10

def guard(log, label):
    assert isinstance(PS_SHA256, str) and sha(Path('/usr/bin/ps')) == PS_SHA256
    row = {'native': host_sample(), 'strict': sample()}
    save(log / (label + '.json'), row)
    assert row['native']['host'] == PROTOCOL['host'] and not row['native']['competing_jobs']
    assert not row['strict']['other_workloads']
    return row
