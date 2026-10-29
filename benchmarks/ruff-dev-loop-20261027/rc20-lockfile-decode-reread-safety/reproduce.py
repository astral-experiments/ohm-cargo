"""Run the 11 resolver commands with a caller-supplied Ohm Cargo and rustc SDK."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--cargo', type=Path, required=True, help='Ohm Cargo executable, not the rustup proxy')
parser.add_argument('--sdk', type=Path, required=True, help='matching Ohm Rust toolchain directory containing bin/rustc and lib/')
parser.add_argument('--output', type=Path, required=True, help='an absent local output directory')
parser.add_argument('--expect-sha256', help='optional published SHA-256 for the supplied Cargo executable')
args = parser.parse_args()
root = args.output.resolve()
root.mkdir(mode=0o700)
directory = Path(__file__).resolve().parent
with args.cargo.open('rb') as f:
    image = hashlib.file_digest(f, 'sha256').hexdigest()
if args.expect_sha256 and args.expect_sha256 != image:
    parser.error('Cargo hash differs from --expect-sha256')
if shutil.which('strace') is None:
    parser.error('strace is required')

def run(script, *argv):
    subprocess.run([sys.executable, '-IB', directory / script, *argv], check=True)

nine, changed = root / 'original', root / 'changed'
run('capture.py', '--image', args.cargo.resolve(), '--sha', image, '--sdk', args.sdk.resolve(),
    '--output', nine)
run('verify_native.py', nine, root / 'verified-raw.json')
run('changed_lock.py', nine, changed)
project = runpy.run_path(str(directory / 'project.py'))
report = root / 'projection.json'
report.write_text(json.dumps(project['arm'](nine, changed), sort_keys=True, indent=2) + '\n')
run('verify.py', report)
print('Private child traces, outputs, and the path-free projection are in', root)
