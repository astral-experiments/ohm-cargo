#!/usr/bin/env python3
"""Require two clean five-second windows and no active compiler, linker, or counter."""
import csv
import datetime
import json
import os
from pathlib import Path
import re
import sys
import time

HERE = Path(__file__).resolve().parent
CPUS = {f'cpu{i}' for i in json.loads((HERE/'plan.json').read_text())['native_cpus']}
TOOLS = re.compile(r'(?:^|[-/])(?:cargo|rustc|rustdoc|cc|gcc|g\+\+|cc1|cc1plus|clang|clang\+\+|collect2|ld|ld\.bfd|ld\.lld|rust-lld|wild|v2-wild|drrun|valgrind|cachegrind|libdynamorio)(?:$|[-.][\w.-]+$)')


def counters():
    rows = [list(map(int,s.split()[1:9])) for s in Path('/proc/stat').read_text().splitlines() if s.split()[0] in CPUS]
    if len(rows)!=len(CPUS):
        raise ValueError(f'missing requested CPU from {CPUS}')
    return [sum(column) for column in zip(*rows)]


def foreign():
    found = []
    for p in Path('/proc').glob('[0-9]*'):
        try:
            exe = os.readlink(p/'exe')
            state = (p/'stat').read_text().rsplit(')',1)[1].split()[0]
        except (FileNotFoundError,PermissionError,ProcessLookupError):
            continue
        if state not in ('Z','X') and TOOLS.search(Path(exe).name):
            found.append((int(p.name),exe))
    return found


def main():
    cohort = sys.argv[1]
    observe = sys.argv[2:] == ['--observe']
    if cohort not in ('initial','replica') or os.environ.get('OHM_EIGHT_NATIVE_RELEASED')!='yes':
        raise ValueError('coordinator release and a registered cohort required')
    d = HERE/'quiet'
    d.mkdir(exist_ok=True)
    old = counters()
    streak = 0
    kind = 'host' if observe else 'preflight'
    with (d/f'{cohort}-{kind}.csv').open('x',newline='',buffering=1) as f:
        w = csv.writer(f)
        w.writerow(('utc','busy_fraction','iowait_fraction','dirty_kib','writeback_kib','foreign_tools','consecutive_quiet'))
        while observe or streak<2:
            time.sleep(5)
            new = counters()
            ticks = [n-o for n,o in zip(new,old)]
            old = new
            total = sum(ticks)
            busy,wait = (total-ticks[3]-ticks[4])/total,ticks[4]/total
            mem = {k:int(v) for k,v,*_ in (s.split() for s in Path('/proc/meminfo').read_text().splitlines())}
            other = [] if observe else foreign()
            quiet = busy<.05 and wait<.02 and mem['Dirty:']<65536 and mem['Writeback:']<8192 and not other
            streak = streak+1 if quiet else 0
            utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
            w.writerow((utc,busy,wait,mem['Dirty:'],mem['Writeback:'],json.dumps(other),streak))
    with (d/f'{cohort}-ready.json').open('x') as f:
        f.write(json.dumps(dict(quiet=True,utc=utc,streak=streak,threshold='five-second windows'))+'\n')


if __name__=='__main__':
    main()
