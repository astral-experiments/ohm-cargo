"""Measure the three fully fresh workspace commands with a frozen ten-draft Cargo."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
for key in ('parent', 'candidate', 'toolchain', 'ruff', 'target', 'shared', 'state', 'output', 'runner'):
    parser.add_argument('--' + key, type=Path, required=True)
args = parser.parse_args()
home = Path(os.environ['CARGO_HOME'])
proof_dir = home / '.ohm-git-index-sha1dc-v1'
index = Path(subprocess.check_output(['git', 'rev-parse', '--path-format=absolute', '--git-path', 'index'], cwd=args.ruff, text=True).strip())
args.output.mkdir(exist_ok=False)


def snapshot():
    files = sorted(proof_dir.iterdir())
    assert files and all(f.is_file() and f.stat().st_size == 32 for f in files)
    rows = {}
    for name, f in [('ruff-index', index), *(('proof-' + f.name, f) for f in files)]:
        st = f.stat()
        rows[name] = [st.st_ino, st.st_size, st.st_mtime_ns, hashlib.sha256(f.read_bytes()).hexdigest()]
    return rows


for i, (mode, count) in enumerate([('check', 520), ('build', 501), ('test', 619)]):
    initial = snapshot()
    output = args.output / mode
    log = args.output / (mode + '.log')
    command = [sys.executable, args.runner, '--cpu', '16-19', '--design', 'paired', '--pairs', '12',
               '--sequence', mode, '--mode', mode, '--seed', str(622901 + i), '--output', output]
    for key in ('parent', 'candidate', 'toolchain', 'ruff', 'target', 'shared', 'state'):
        command += ['--' + key, getattr(args, key)]
    with log.open('w') as stream:
        subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
    assert log.read_text().rstrip().endswith(f'{count} fresh units')
    final = snapshot()
    (output / 'git-records.json').write_text(json.dumps({'before': initial, 'after': final}, indent=2) + '\n')
    assert initial == final
    print(mode, log.read_text().splitlines()[-1], flush=True)
