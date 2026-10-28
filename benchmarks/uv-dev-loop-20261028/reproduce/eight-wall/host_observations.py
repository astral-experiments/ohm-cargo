#!/usr/bin/env python3
"""Report the quiet preflights and descriptive host observations after native timing."""
import csv
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent


def read(cohort, kind):
    with (HERE/'quiet'/f'{cohort}-{kind}.csv').open() as f:
        return list(csv.DictReader(f))


def main():
    selected = {}
    for cohort in ['initial','replica']:
        pres = read(cohort, 'preflight')
        live = read(cohort, 'host')
        if len(live) < 2 or len(pres) < 2 or [r['consecutive_quiet'] for r in pres[-2:]] != ['1','2']:
            raise ValueError(f'incomplete host records for {cohort}')
        foreign = [str(x[1]) for r in pres for x in json.loads(r['foreign_tools'])]
        failures = {
            'cpu_busy': sum(float(r['busy_fraction']) >= .05 for r in pres),
            'iowait': sum(float(r['iowait_fraction']) >= .02 for r in pres),
            'dirty': sum(int(r['dirty_kib']) >= 65536 for r in pres),
            'writeback': sum(int(r['writeback_kib']) >= 8192 for r in pres),
            'foreign_tools': sum(bool(json.loads(r['foreign_tools'])) for r in pres),
        }
        metrics = {k:[float(r[k]) for r in live] for k in ['busy_fraction','iowait_fraction','dirty_kib','writeback_kib']}
        selected[cohort] = dict(five_second_preflight_windows=len(pres), threshold_failures=failures,
                final_two_windows=pres[-2:], preflight_foreign_tools=foreign, in_window_samples=len(live),
                in_window={k:dict(median=statistics.median(v),maximum=max(v)) for k,v in metrics.items()})
    output = dict(cohorts=selected, scope='Busy and iowait cover the registered native CPUs. Dirty and writeback are system-wide. Foreign-process scans ran during preflight; the periodic in-window monitor collected aggregate host counters. No timing rows are removed by this descriptive summary.')
    (HERE/'host-observations.json').write_text(json.dumps(output,indent=2)+'\n')


if __name__ == '__main__':
    main()
