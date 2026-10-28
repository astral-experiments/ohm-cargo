#!/usr/bin/env python3
"""Replay one registered incremental profile-trained Cargo comparison."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys


here = Path(__file__).resolve().parent
work = Path(os.environ.get('OHM_BENCH_WORK', here.parent)).resolve()
bench = Path(os.environ['OHM_BENCH_ROOT']) if 'OHM_BENCH_ROOT' in os.environ else Path((work / 'bench-home.path').read_text().strip())
plan = json.loads((here / 'registration.json').read_text())
stages = {r['name']: r for r in plan['stages']}
cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument('stage', choices=stages)
cli.add_argument('--print', action='store_true', help='print the two frozen commands')
args = cli.parse_args()
row = stages[args.stage]


def binary(name):
    if name in {'base', 'guard-stack'}:
        directory = (work / 'pgo-final-path.txt').read_text().strip()
        return work / directory / 'bin' / name
    return work / 'pgo-intermediates/bin' / name


commands = []
for key, suffix, source, home, target in [('primary', 'confirm', bench / 'u', bench / 'cargo-native', 'native-wall'),
                                          ('repeat', 'replica', work / 'uv', bench / 'cargo', 'replica')]:
    name = f'pgo-{args.stage}-{suffix}'
    spec = plan[key]
    command = [sys.executable, '-B', work / 'measure.py', '--mode', spec['mode'], '--settle-counter',
               '--pairs', str(spec['pairs']), '--seed', str(row[key + '_seed']), '--base', binary(row['base']),
               '--candidate', binary(row['head']), '--source', source, '--cargo-home', home, '--target', target,
               '--result', work / name, '--endpoints', row['endpoint']]
    commands.append((name, command))
    if args.print:
        print(shlex.join(list(map(str, command))))
if not args.print:
    with (work / 'native-wall-measurement.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for name, command in commands:
            logfile = work / 'logs' / (name + '.log')
            with logfile.open('x') as log:
                subprocess.run(command, cwd=work.parent, stdout=log, stderr=subprocess.STDOUT, check=True)
            print(name, logfile.read_text().strip(), flush=True)
