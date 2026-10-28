#!/usr/bin/env python3
"""Run only qualified independent repeats, preserving original endpoint receipts."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from qualify import qualifies


def main():
    work = Path(os.environ.get('OHM_BENCH_WORK', HERE.parents[1])).resolve()
    rust = Path(os.environ.get('OHM_TOOLCHAIN_BIN', work / 'toolchain/bin')) / 'rustc'
    files = {'base': (work/'path-compare/build/bin/base', work/'bin/wild-baseline'),
             'candidate': (work/'path-compare/build/bin/guard-stack', work/'bin/wild-undefined')}
    def digest(p):
        with p.open('rb') as f:
            return hashlib.file_digest(f,'sha256').hexdigest()
    actual = {arm:[digest(p) for p in paths] for arm,paths in files.items()}
    actual_rust = digest(rust)
    eligibility = HERE/'eligibility'
    eligibility.mkdir(exist_ok=True)
    for ep in ('check','build','test'):
        first = HERE.parent/'identical/results'/ep
        ok = qualifies(first)
        (eligibility/f'{ep}.json').write_text(json.dumps({'passed_initial_gate':ok})+'\n')
        if not ok:
            print(f'{ep}: initial gate did not pass', flush=True)
            continue
        initial = json.loads((first/'protocol.json').read_text())
        if (initial['sha256'] != actual or initial['rustc_sha256'] != actual_rust
                or initial['pinned_cpus'] != sorted(os.sched_getaffinity(0))):
            raise ValueError(f'{ep}: binaries or affinity changed after initial cohort')
        for phase in ('pilot','samples'):
            result = HERE/'results'/ep
            if list(result.glob('rejected-*.json')):
                break
            if phase == 'pilot' and (result/'admission.json').exists():
                continue
            log = HERE/f'driver-{phase}-{ep}.log'
            if log.exists():
                raise RuntimeError(f'refusing to overwrite {log}')
            print(f'Starting independent {phase} {ep}',flush=True)
            with log.open('x') as f:
                rc = subprocess.run([sys.executable,'-B',str(HERE.parent/'replica.py'),phase,ep],stdout=f,stderr=subprocess.STDOUT).returncode
            print(log.read_text(),end='',flush=True)
            if rc:
                if not (result/f'rejected-{phase}.json').exists():
                    raise RuntimeError(f'{ep} infrastructure error during {phase}')
                break
    subprocess.run([sys.executable,'-B',str(HERE.parent/'identical/summarize.py')],check=True)


if __name__=='__main__':
    main()
