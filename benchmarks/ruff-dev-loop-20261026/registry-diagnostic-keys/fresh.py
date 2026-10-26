"""Count complete warm Cargo commands on Ruff in balanced four-run blocks."""
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
parser.add_argument('--package', help='Omit for the default workspace command')
parser.add_argument('--mode', choices=('check', 'build', 'test', 'all'), default='check')
parser.add_argument('--blocks', type=int, choices=range(1, 17), default=8)
parser.add_argument('--design', choices=('four-run', 'paired'), default='four-run')
parser.add_argument('--pairs', type=int, choices=range(1, 21), default=12)
parser.add_argument('--artifact-messages', action='store_true', help='Also request Cargo JSON in the timed samples')
parser.add_argument('--cpu', required=True, help='CPU affinity such as 2 or 0-3')
parser.add_argument('--seed', type=int, default=101821)
parser.add_argument('--state', type=Path, required=True)
parser.add_argument('--sequence', nargs='+', choices=('check','build','test'), required=True)
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
ruff, target, shared = (p.resolve() for p in (args.ruff, args.target, args.shared))
assert target != shared and target not in shared.parents and shared not in target.parents
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ruff, text=True).strip() == '93526150df078af7dd8fc4226cdcc469539d2001'
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ruff)
state = args.state.resolve()
tool = state / 'rustup/toolchains/ohm'
assert tool.is_dir()
for arm in ('parent', 'candidate'):
    shutil.copy2(getattr(args, arm), out / arm)
real = state / 'runtime/bin/cargo'
assert real.is_file() and str(real) in (tool / 'bin/cargo').read_text()
env = dict(os.environ, RUSTUP_HOME=str(state / 'rustup'), RUSTUP_AUTO_INSTALL='0',
           CARGO_TARGET_DIR=str(target), CARGO_BUILD_BUILD_DIR=str(shared), CARGO_BUILD_JOBS='6',
           CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all', CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',
           CARGO_TERM_COLOR='never', LC_ALL='C.UTF-8')
env.setdefault('SSL_CERT_FILE', '/etc/ssl/certs/ca-certificates.crt')
env.setdefault('SSL_CERT_DIR', '/etc/ssl/certs')


def benchmark_mode(mode, seed):
    run_root = out
    if len(args.sequence)>1:
        run_root = out / mode
        run_root.mkdir()
    command = ['taskset', '-c', args.cpu, 'cargo', '+ohm', mode]
    if mode == 'test':
        command.append('--no-run')
    command += ['--locked', '--offline']
    if args.package:
        command += ['-p', args.package]


    def run(arm, tag, prime=False, validate=False):
        work = run_root / tag
        work.mkdir()
        if not real.exists() or not real.samefile(out / arm):
            temp = real.with_name('next')
            os.link(out / arm, temp)
            temp.replace(real)
        argv = command + (['--message-format=json'] if prime or validate or args.artifact_messages else [])
        with (work / 'stderr').open('wb') as stderr:
            stdout = subprocess.check_output(argv, cwd=ruff, stderr=stderr,
                env=dict(env, CG_OUT=str(work), CG_CHILDREN='no' if prime else 'yes'))
        assert 'Blocking waiting' not in (work/'stderr').read_text(), (tag, 'lock contention')
        if prime:
            return
        profiles = list(work.glob('cg.*'))
        assert len(profiles) == 1, (tag, profiles)
        data = profiles[0].read_bytes()
        assert Path(re.search(rb'^cmd:\s+(\S+)', data, re.M)[1].decode()).name == 'cargo'
        if validate or args.artifact_messages:
            units = []
            for line in stdout.splitlines():
                row = json.loads(line)
                if row['reason'] == 'compiler-artifact':
                    assert row['fresh'], row['target']['name']
                    units.append((row['package_id'], row['target']['name'], row['target']['kind'], row['profile']['test']))
            assert units
            if validate:
                return sorted(units)
            assert sorted(units) == expected_units
        return int(re.search(rb'^summary: (\d+)$', data, re.M)[1])


    run('parent', 'prime', prime=True)
    expected_units = run('parent', 'verify-parent', validate=True)
    assert expected_units == run('candidate', 'verify-candidate', validate=True)
    def records():
        home = Path(env['CARGO_HOME'])
        return {version: {f.name: (f.stat().st_ino, f.stat().st_size, f.stat().st_mtime_ns)
                for f in (home / ('.ohm-registry-json-' + version)).iterdir()}
                for version in ('v1', 'v2')}
    initial = records()
    rng = random.Random(seed)
    rows = []
    schedule = []
    if args.design == 'four-run':
        for block in range(args.blocks):
            order = ['parent', 'candidate']
            rng.shuffle(order)
            schedule.extend([(block, 0, order), (block, 1, list(reversed(order)))])
    else:
        flips = list(range(args.pairs))
        rng.shuffle(flips)
        for block, flip in enumerate(flips):
            order = ['candidate', 'parent'] if flip % 2 else ['parent', 'candidate']
            schedule.append((block, 0, order))
    for block, pair, order in schedule:
        counts = {arm: run(arm, f'{block:02}-{pair}-{arm}') for arm in order}
        row = (block, pair, order[0], counts['parent'], counts['candidate'])
        rows.append(row)
        print(*row, flush=True)
    assert expected_units == run('parent', 'verify-final', validate=True)
    final = records()
    (run_root / 'cache-records.json').write_text(json.dumps({
        'counts': {v:len(fs) for v,fs in initial.items()}, 'identical': final == initial,
        'changes': {v:sorted(k for k in fs.keys() | final[v].keys() if fs.get(k) != final[v].get(k)) for v,fs in initial.items()},
    }, indent=2) + '\n')
    assert initial == final, 'cache records changed during scored runs'
    with (run_root / 'pairs.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['block', 'pair', 'first_arm', 'parent_ir', 'candidate_ir'])
        writer.writerows(rows)
    savings = [100 * (1 - candidate / parent) for _, _, _, parent, candidate in rows]
    diffs = [r[3] - r[4] for r in rows]
    observed = abs(sum(diffs))
    if args.design == 'four-run':
        block_diffs = [sum(diffs[i:i+2]) for i in range(0, len(diffs), 2)]
        extreme = sum(abs(sum(s*d for s, d in zip(signs, block_diffs))) >= observed
                      for signs in itertools.product((-1, 1), repeat=len(block_diffs)))
        p = extreme / 2**len(block_diffs)
    else:
        slots = [-d if r[2] == 'candidate' else d for d, r in zip(diffs, rows)]
        n_first = sum(r[2] == 'candidate' for r in rows)
        extreme = sum(abs(sum(slots) - 2 * sum(slots[i] for i in swap)) >= observed
                      for swap in itertools.combinations(range(len(rows)), n_first))
        p = extreme / math.comb(len(rows), n_first)
    print(f'Median paired reduction {statistics.median(savings):.3f}%, '
          f'two-sided randomization p={p:.5g}, {len(expected_units)} fresh units')


modes = args.sequence
for index, mode in enumerate(modes):
    benchmark_mode(mode, args.seed + index)
