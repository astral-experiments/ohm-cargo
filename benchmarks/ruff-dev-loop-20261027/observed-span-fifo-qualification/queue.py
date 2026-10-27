"""Run the corrected observer qualification only after the preceding isolated H2 studies."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

here = Path(__file__).resolve().parent
base = here.parent
summary = json.loads((here / 'subjects.json').read_bytes())
proof = json.loads((here / 'fifo-gate.json').read_bytes())
assert proof['cargo_sha256'] == summary['candidate_cargo'] and proof['driver_sha256'] == summary['compiler_driver']
for witness in proof['repeats']:
    assert witness['no_writer_ever'] and not witness['timed_out_in_open'] and witness['programs_equal']
    assert witness['open_flags'] == [0x80900] and witness['command_returncode'] == 101
    assert witness['symlink'] == [[], []] and witness['downgrade']['return'][-1] == []

completed = (base / 'stdlib-holdout-v1' / 'queue.rc', base / 'queue-cargo-ruff-v2.rc')
while not all(rc.is_file() for rc in completed):
    if (base / 'qualification-posobs4fmt-c3' / 'failure.txt').is_file():
        raise SystemExit('Compiler qualification failed; preserve and diagnose it first.')
    for rc in completed:
        if rc.exists() and rc.read_text().strip() != '0':
            raise SystemExit(f'Previous study failed: {rc.name}')
    time.sleep(30)
assert all(rc.read_text().strip() == '0' for rc in completed)
for name in ('qualification-posobs4fmt-c3', 'cargo-observer-ruff-final', 'stdlib-holdout-exact-v1'):
    assert (base / name / 'complete.json').is_file(), name

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

assert sha(here / 'parent253') == summary['parent_cargo']
assert sha(here / 'guardv3') == summary['candidate_cargo']
harness = here / 'harness'
subprocess.run(['sha256sum', '--check', 'SHA256SUMS'], cwd=harness, check=True)
subprocess.run([sys.executable, '-B', harness / 'run.py',
                '--parent-cargo', here / 'parent253', '--candidate-cargo', here / 'guardv3',
                '--compiler-commit', summary['compiler_commit'], '--driver-sha', summary['compiler_driver'],
                '--driver', base / 'drivers' / ('driver-' + summary['compiler_driver']),
                '--run', base / 'cargo-observer-ruff-fifo-fixed'], check=True)
