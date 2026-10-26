"""Compare two release Cargo binaries on a pinned, disposable Ruff checkout."""

import argparse
import csv
import itertools
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import statistics
import subprocess


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('parent', 'candidate', 'toolchain', 'ruff', 'target', 'shared', 'output'):
        parser.add_argument('--' + option, required=True, type=Path)
    parser.add_argument('--kind', choices=('fresh', 'edited'), required=True)
    parser.add_argument('--pairs', type=int, choices=range(1, 21), default=16)
    parser.add_argument('--cpu', required=True, help='CPU number from the allowed affinity mask')
    parser.add_argument('--seed', type=int, default=3331)
    return parser.parse_args()


def main():
    args = arguments()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    target, shared, ruff = (p.resolve() for p in (args.target, args.shared, args.ruff))
    assert target != shared and target not in shared.parents and shared not in target.parents
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ruff, text=True).strip() == '93526150df078af7dd8fc4226cdcc469539d2001'
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ruff)
    toolchain = out / 'rustup/toolchains/ohm'
    (toolchain / 'bin').mkdir(parents=True)
    (toolchain / 'lib').symlink_to(args.toolchain.resolve() / 'lib', target_is_directory=True)
    for exe in (args.toolchain.resolve() / 'bin').iterdir():
        if exe.name != 'cargo':
            (toolchain / 'bin' / exe.name).symlink_to(exe)
    for label in ('parent', 'candidate'):
        shutil.copy2(getattr(args, label), out / label)
    env = dict(os.environ, RUSTUP_HOME=str(out / 'rustup'), RUSTUP_AUTO_INSTALL='0',
               CARGO_TARGET_DIR=str(target), CARGO_BUILD_BUILD_DIR=str(shared), CARGO_BUILD_JOBS='6',
               CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all', CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',
               CARGO_TERM_COLOR='never', LC_ALL='C.UTF-8')
    env.setdefault('SSL_CERT_FILE', '/etc/ssl/certs/ca-certificates.crt')
    env.setdefault('SSL_CERT_DIR', '/etc/ssl/certs')

    def run(label, trial, artifact_messages):
        directory = out / trial
        directory.mkdir()
        exe = toolchain / 'bin/cargo'
        if not exe.exists() or not exe.samefile(out / label):
            tmp = exe.with_suffix('.next')
            os.link(out / label, tmp)
            tmp.replace(exe)
        command = ['taskset', '-c', args.cpu, 'valgrind', '--tool=callgrind', '--trace-children=yes',
                   f'--log-file={directory}/log.%p', f'--callgrind-out-file={directory}/ir.%p',
                   'cargo', '+ohm', 'check', '--locked', '--offline', '-p', 'ruff_text_size']
        if artifact_messages:
            command.append('--message-format=json')
        with (directory / 'stderr').open('wb') as stderr:
            output = subprocess.check_output(command, cwd=ruff, env=env, stderr=stderr)
        artifacts = []
        if artifact_messages:
            for line in output.splitlines():
                message = json.loads(line)
                if message['reason'] == 'compiler-artifact':
                    artifacts.append((message['target']['name'], message['fresh']))
        processes = {}
        for profile in directory.glob('ir.*'):
            data = profile.read_bytes()
            name = Path(re.search(rb'^cmd:\s+(\S+)', data, re.MULTILINE)[1].decode()).name
            assert trial == 'prime' or name not in processes, (trial, name)
            count = int(re.search(rb'^summary: (\d+)$', data, re.MULTILINE)[1])
            processes[name] = processes.get(name, 0) + count
        assert 'cargo' in processes
        return artifacts, processes

    source = ruff / 'crates/ruff_text_size/src/size.rs'
    after = source.read_bytes()
    original_stat = source.stat()
    checkpoint = out / 'checkpoint'
    rows = []
    try:
        if args.kind == 'edited':
            subprocess.run(['git', 'apply', '--reverse', Path(__file__).with_name('ruff-edit.patch')], cwd=ruff, check=True)
        run('parent', 'prime', True)
        for label in ('parent', 'candidate', 'parent'):
            tag = f'verify-{label}'
            if (out / tag).exists():
                tag += '-again'
            artifacts, _ = run(label, tag, True)
            assert artifacts == [('ruff_text_size', True)], artifacts
        if args.kind == 'edited':
            subprocess.run(['cp', '-a', target, checkpoint], check=True)
        flips = list(range(args.pairs))
        random.Random(args.seed).shuffle(flips)
        for block, flip in enumerate(flips):
            pair = {}
            for label in (('candidate', 'parent') if flip % 2 else ('parent', 'candidate')):
                if args.kind == 'edited':
                    subprocess.run(['rsync', '-a', '--delete', '--ignore-times', str(checkpoint) + '/', str(target) + '/'], check=True)
                    source.write_bytes(after)
                artifacts, counts = run(label, f'{block:03}-{label}', args.kind == 'edited')
                if args.kind == 'edited':
                    assert artifacts == [('ruff_text_size', False)] and counts.keys() == {'cargo', 'rustc'}
                else:
                    assert counts.keys() == {'cargo'}
                pair[label] = sum(counts.values())
            rows.append((block, pair['parent'], pair['candidate']))
            print(*rows[-1], flush=True)
    finally:
        if args.kind == 'edited':
            source.write_bytes(after)
            os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    with (out / 'pairs.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['block', 'parent_ir', 'candidate_ir'])
        writer.writerows(rows)
    savings = [100 * (1 - b / a) for _, a, b in rows]
    differences = [a - b for _, a, b in rows]
    slots = [(-d if flip % 2 else d) for d, flip in zip(differences, flips)]
    candidate_first = sum(flip % 2 for flip in flips)
    total = sum(slots)
    extreme = sum(abs(total - 2 * sum(slots[i] for i in assignment)) >= abs(sum(differences))
                  for assignment in itertools.combinations(range(len(slots)), candidate_first))
    p = extreme / math.comb(len(slots), candidate_first)
    print(f'Median paired reduction {statistics.median(savings):.3f}%, two-sided randomization p={p:.5g}')


if __name__ == '__main__':
    main()
