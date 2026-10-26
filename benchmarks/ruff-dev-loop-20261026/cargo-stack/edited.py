"""Count a complete default Ruff check after replaying a CLI source edit."""
import argparse
import csv
import itertools
import json
import math
import os
from pathlib import Path
import random
import re
import shlex
import shutil
import statistics
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
for option in ('parent', 'candidate', 'toolchain', 'ruff', 'target', 'shared', 'output'):
    parser.add_argument('--' + option, type=Path, required=True)
parser.add_argument('--cpu', required=True, help='Available CPU number or affinity mask')
parser.add_argument('--pairs', type=int, choices=range(1, 21), default=12)
parser.add_argument('--seed', type=int, default=57127)
args = parser.parse_args()
root, target, shared, ruff = (p.resolve() for p in (args.output, args.target, args.shared, args.ruff))
assert target != shared and target not in shared.parents and shared not in target.parents
assert target != root and target not in root.parents and root not in target.parents
root.mkdir(parents=True, exist_ok=False)
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ruff)
assert git('rev-parse', 'HEAD').decode().strip() == '93526150df078af7dd8fc4226cdcc469539d2001'
assert not git('status', '--porcelain')
tool = root / 'rustup/toolchains/ohm'
(tool / 'bin').mkdir(parents=True)
shutil.copytree(args.toolchain / 'lib', tool / 'lib', symlinks=True)
for entry in (args.toolchain / 'bin').iterdir():
    if entry.name != 'cargo':
        shutil.copy2(entry, tool / 'bin' / entry.name)
for arm in ('parent', 'candidate'):
    shutil.copy2(getattr(args, arm), root / arm)
cargo = root / 'runtime/bin/cargo'
cargo.parent.mkdir(parents=True)
wrapper = tool / 'bin/cargo'
wrapper.write_text('#!/bin/sh\nexec valgrind --tool=callgrind --trace-children="$TRACE_CHILDREN" '
    '--cache-sim=no --branch-sim=no --log-file="$SAMPLE/log.%p" '
    '--callgrind-out-file="$SAMPLE/count.%p" ' + shlex.quote(str(cargo)) + ' "$@"\n')
wrapper.chmod(0o755)
env = dict(os.environ, RUSTUP_HOME=str(root / 'rustup'), RUSTUP_AUTO_INSTALL='0',
    CARGO_TARGET_DIR=str(target), CARGO_BUILD_BUILD_DIR=str(shared), CARGO_BUILD_JOBS='6',
    CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all', CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',
    CARGO_TERM_COLOR='never', LC_ALL='C.UTF-8')
env.setdefault('SSL_CERT_FILE', '/etc/ssl/certs/ca-certificates.crt')
env.setdefault('SSL_CERT_DIR', '/etc/ssl/certs')
def sample(arm, tag, *, prime=False):
    directory = root / tag
    directory.mkdir()
    if not cargo.exists() or not cargo.samefile(root / arm):
        temp = cargo.with_name('next')
        os.link(root / arm, temp)
        temp.replace(cargo)
    argv = ['taskset', '-c', args.cpu, 'cargo', '+ohm', 'check', '--locked', '--offline', '--message-format=json']
    with (directory / 'stderr').open('wb') as err, (directory / 'stdout').open('wb') as out:
        subprocess.run(argv, cwd=ruff, env=dict(env, SAMPLE=str(directory), TRACE_CHILDREN='no' if prime else 'yes'),
            stdout=out, stderr=err, check=True)
    if prime:
        return
    units = []
    for line in (directory / 'stdout').read_bytes().splitlines():
        row = json.loads(line)
        if row['reason'] == 'compiler-artifact':
            units.append((row['package_id'], row['target']['name'], tuple(row['target']['kind']), row['profile']['test'], row['fresh']))
    counts = {}
    for profile in directory.glob('count.*'):
        data = profile.read_bytes()
        name = Path(re.search(rb'^cmd:\s+(\S+)', data, re.MULTILINE)[1].decode()).name
        assert name not in counts, (tag, name)
        counts[name] = int(re.search(rb'^summary: (\d+)$', data, re.MULTILINE)[1])
    assert len(units) == 520, (tag, len(units))
    return sorted(units), counts

path = 'crates/ruff/src/main.rs'
source = ruff / path
after = git('show', 'HEAD:' + path)
assert source.read_bytes() == after
original = source.stat()
marker = b'    let args = wild::args_os();'
before_historical = git('show', 'da8ee78491f784cdead4c69e83c58bc87fd0622c^:' + path)
block = before_historical[before_historical.index(b'    // support FORCE_COLOR env var'):before_historical.index(marker)]
assert len(block.splitlines()) == 7 and after.count(marker) == 1
checkpoint = root / 'checkpoint'
rows = []
try:
    source.write_bytes(after.replace(marker, block + marker))
    sample('parent', 'prime', prime=True)
    warm_units, counts = sample('parent', 'verify')
    assert all(u[-1] for u in warm_units) and counts.keys() == {'cargo'}
    # Copy the pre-edit target without sharing writable inodes with the live run.
    subprocess.run(['cp', '-a', target, checkpoint], check=True)
    flips = list(range(args.pairs))
    random.Random(args.seed).shuffle(flips)
    for pair, flip in enumerate(flips):
        order = ('candidate', 'parent') if flip % 2 else ('parent', 'candidate')
        values = {}
        for arm in order:
            subprocess.run(['rsync', '-a', '--delete', '--modify-window=-1', str(checkpoint) + '/', str(target) + '/'], check=True)
            source.write_bytes(after)
            units, counts = sample(arm, f'{pair:02}-{arm}')
            assert [u[:-1] for u in units] == [u[:-1] for u in warm_units]
            assert [u[1:3] for u in units if not u[-1]] == [('ruff', ('bin',))]
            assert counts.keys() == {'cargo', 'rustc'}
            values[arm] = counts
        row = (pair, order[0], values['parent']['cargo'], values['parent']['rustc'],
               values['candidate']['cargo'], values['candidate']['rustc'])
        rows.append(row)
        print(*row, flush=True)
finally:
    source.write_bytes(after)
    os.utime(source, ns=(original.st_atime_ns, original.st_mtime_ns))
with (root / 'pairs.csv').open('w', newline='') as out:
    writer = csv.writer(out)
    writer.writerow(['pair','first_arm','parent_cargo_ir','parent_rustc_ir','candidate_cargo_ir','candidate_rustc_ir'])
    writer.writerows(rows)
diffs = [pc + pr - cc - cr for _, _, pc, pr, cc, cr in rows]
savings = [100 * (1 - (cc + cr) / (pc + pr)) for _, _, pc, pr, cc, cr in rows]
slots = [-d if first == 'candidate' else d for d, (_, first, *_) in zip(diffs, rows)]
n_first = sum(first == 'candidate' for _, first, *_ in rows)
extreme = sum(abs(sum(slots) - 2 * sum(slots[i] for i in swap)) >= abs(sum(diffs))
    for swap in itertools.combinations(range(args.pairs), n_first))
print(f'Median paired reduction {statistics.median(savings):.3f}%, '
      f'two-sided randomization p={extreme / math.comb(args.pairs, n_first):.5g}')
