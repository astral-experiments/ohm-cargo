"""Time ordinary warm Ruff commands with a private toolchain created by fresh.py."""
import argparse
import csv
import fcntl
import json
import os
from pathlib import Path
import random
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import time

parser = argparse.ArgumentParser(description=__doc__)
for name in ('rustup', 'runtime-cargo', 'parent', 'candidate', 'ruff', 'target', 'shared', 'output'):
    parser.add_argument('--' + name, type=Path, required=True)
parser.add_argument('--seed', type=int, required=True)
parser.add_argument('--blocks', type=int, default=16)
args = parser.parse_args()
ruff = args.ruff.resolve()
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ruff, text=True).strip() == '93526150df078af7dd8fc4226cdcc469539d2001'
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ruff)
private = args.rustup.resolve()
wrapper = private / 'toolchains/ohm/bin/cargo'
real = args.runtime_cargo.resolve()
target, shared = args.target.resolve(), args.shared.resolve()
assert target != shared and shared not in target.parents and target not in shared.parents
assert wrapper.stat().st_size < 4096 and str(real) in wrapper.read_text() and real.is_file()
env = dict(os.environ, RUSTUP_HOME=str(private), RUSTUP_AUTO_INSTALL='0',
           CARGO_TARGET_DIR=str(target), CARGO_BUILD_BUILD_DIR=str(shared), CARGO_BUILD_JOBS='6',
           CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all', CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',
           CARGO_TERM_COLOR='never', LC_ALL='C.UTF-8')
modes = {'check': ['check'], 'build': ['build'], 'test': ['test', '--no-run']}
count = {'check': 520, 'build': 501, 'test': 619}


def run(mode, validate=False):
    command = ['cargo', '+ohm', *modes[mode], '--locked', '--offline']
    if validate:
        command.append('--message-format=json')
    if not validate:
        begin = time.perf_counter_ns()
        result = subprocess.run(command, cwd=ruff, env=env, capture_output=True, check=True)
        elapsed = time.perf_counter_ns() - begin
        assert b'Finished' in result.stderr and not re.search(rb'^\s*(?:Compiling|Checking)\b', result.stderr, re.M), result.stderr
        return elapsed, int(b'Blocking waiting' in result.stderr)
    with tempfile.TemporaryFile() as stdout, subprocess.Popen(command, cwd=ruff, env=env, stdout=stdout, stderr=subprocess.PIPE) as proc:
        for line in proc.stderr:
            if re.match(rb'^\s*(?:Compiling|Checking)\b', line):
                proc.send_signal(signal.SIGINT)
                proc.communicate()
                raise RuntimeError('Preflight found dirty work: ' + line.decode().strip())
        assert proc.wait() == 0
        stdout.seek(0)
        lines = stdout.readlines()
    units = [unit for line in lines
             if (unit := json.loads(line))['reason'] == 'compiler-artifact']
    assert len(units) == count[mode] and all(unit['fresh'] for unit in units)
    return sorted((unit['package_id'], unit['target']['name'], unit['target']['kind'], unit['profile']['test']) for unit in units)


args.output.mkdir(exist_ok=False, parents=True)
rng = random.Random(args.seed)
with (private / 'native-benchmark.lock').open('a') as lock, tempfile.TemporaryDirectory(dir=real.parent) as tmp:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    tmp = Path(tmp)
    for arm in ('parent', 'candidate'):
        shutil.copy2(getattr(args, arm), tmp / arm)
    backup = wrapper.with_name('original-native-benchmark-wrapper')
    os.link(wrapper, backup)
    os.link(real, tmp / 'original-cargo')

    def select(arm):
        if not os.path.samefile(real, tmp / arm):
            os.link(tmp / arm, tmp / 'next')
            (tmp / 'next').replace(real)

    try:
        shim = wrapper.with_name('next-native-benchmark-wrapper')
        shim.write_text('#!/bin/sh\nexec '+shlex.quote(str(real))+' "$@"\n')
        shim.chmod(0o755)
        shim.replace(wrapper)
        rosters = {}
        for arm in ('parent', 'candidate', 'parent', 'candidate'):
            select(arm)
            for mode in modes:
                roster = run(mode, validate=True)
                assert roster == rosters.setdefault(mode, roster)
        with (args.output / 'wall.csv').open('x', newline='') as output:
            writer = csv.writer(output)
            writer.writerow(['seed', 'block', 'mode', 'position', 'arm', 'elapsed_ns', 'reported_lock_wait'])
            for block in range(args.blocks):
                commands = list(modes)
                rng.shuffle(commands)
                for mode in commands:
                    order = ['parent', 'candidate', 'candidate', 'parent']
                    if rng.getrandbits(1):
                        order = ['candidate' if arm == 'parent' else 'parent' for arm in order]
                    for position, arm in enumerate(order):
                        select(arm)
                        writer.writerow([args.seed, block, mode, position, arm, *run(mode)])
                output.flush()
                print('finished block', block, flush=True)
        for arm in ('candidate', 'parent'):
            select(arm)
            for mode in modes:
                assert rosters[mode] == run(mode, validate=True)
        (args.output / 'verified').write_text(f'{count}\n')
    finally:
        backup.replace(wrapper)
        (tmp / 'original-cargo').replace(real)
