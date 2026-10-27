"""Add a destination-verified, allowlisted account of real commands to the reviewable endpoint data."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

h = Path(__file__).resolve().parent
source, out = map(Path, sys.argv[1:3])
raw = source / 'source-receipts'
review = source / 'destination-replay'
out.mkdir()

def get(path):
    return json.loads(path.read_bytes())

def write(p, value):
    p.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def compact(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode() + b'\n'

for p in review.iterdir():
    if p.name != 'training.json':
        shutil.copyfile(p, out / p.name)
training = get(review / 'training.json')
for mode in ('build', 'test'):
    for row in training[mode + '-prior'].values():
        row['linkers'] = [Path(p).name for p in row['linkers']]
        row['dirty'] = [[(q if not q.startswith('path+') else 'workspace:' + q.rsplit('/', 1)[-1]), target, kind, test]
                        for q, target, kind, test in (json.loads(s) for s in row['dirty'])]
for arm in 'VC':
    for row in training.get(arm, []):
        process = row['physical']
        row['physical'] = {'executions': [Path(p).name for _, p in process['executions']],
                           'rustc': process['rustc'], 'linkers': [Path(p).name for p in process['linkers']],
                           'rustc_queries': len(process['rustc_queries']), 'target_execs': [Path(p).name for p in process['target_execs']]}
        for r in row['proofs']:
            r['encoded'] = Path(r['encoded']).name
write(out / 'training.json', training)

details = {}
for mode in ('test', 'build'):
    a = get(raw / f'anchor-{mode}-V/anchor.json')
    fields = ['roster', 'messages', 'stamps', 'raw_sha256', 'proofs', 'passive_proofs', 'active_artifact', 'reader_metadata', 'executables', 'diagnostics',
              'exec_open_calibration', 'cargo_home_ancestors', 'cache_inventory']
    details[mode] = {k: a[k] for k in fields}
(out / 'structural-witnesses.json.gz').write_bytes(gzip.compress(compact(details), compresslevel=7, mtime=0))

with (out / 'wall.csv').open() as f:
    rows = list(csv.DictReader(f))
commands = []
for r in rows:
    block = int(r['block']); arm = r['arm']; mode = r['mode']
    tag = f'{block:02d}-{mode}-{arm}'
    t, a = raw / ('timed-' + tag), raw / ('audit-' + tag)
    n, i, q = get(t / 'receipt.json'), get(t / 'invocation.json'), get(a / 'receipt.json')
    physical = q['processes']
    trace_ids = {p.name: k for k, p in enumerate(sorted(a.glob('exec.*')), 1)}
    assert n['ns'] == i['ns'] == int(r['elapsed_ns']) and n['status'] == i['status'] == q['status'] == 0
    commands.append({'block': block, 'mode': mode, 'arm': arm, 'native_ns': i['ns'], 'cargo': i['cargo_sha256'],
                     'native_argv': i['argv'], 'watched_images': [Path(s).name for s in i['watched_image_paths']], 'observed_native_opens': i['executable_open_events'],
                     'full_rustc': physical['rustc'], 'rustc_queries': physical['rustc_queries'], 'linkers': physical['linkers'],
                     'target_processes': physical['target_execs'], 'successful_execs': [
                         [trace_ids[label], 'cargo-proxy-or-installed' if image.endswith('/bin/cargo') else Path(image).name,
                          hashlib.sha256(image.encode()).hexdigest()] for label, image in physical['executions']],
                     'raw_exec_files': {trace_ids[p.name]: sha(p) for p in sorted(a.glob('exec.*'))},
                     'native_receipt_sha256': sha(t / 'receipt.json'), 'exec_receipt_sha256': sha(a / 'receipt.json')})
write(out / 'command-witnesses.json', commands)
for name in ('complete.json', 'anchors-complete.json', 'measured.json', 'subjects.json', 'training-limit.json'):
    if (raw / name).is_file():
        shutil.copyfile(raw / name, out / name)
shutil.copyfile(h / 'portable-witness.py', out / 'verify-witness.py')
# This is the full eligible harness as run, including its original source-check manifest.
runner = out / 'runner'
runner.mkdir()
for line in (h / 'SHA256SUMS').read_text().splitlines():
    expected, name = line.split('  ', 1)
    assert sha(h / name) == expected
    (runner / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(h / name, runner / name)
shutil.copyfile(h / 'SHA256SUMS', runner / 'SHA256SUMS')
controls = out / 'controls'
controls.mkdir()
for name in ('jobserver.json', 'extra-controls.json', 'jobserver-control.py', 'local_true_edit.py'):
    shutil.copyfile(h / name, controls / name)
for name in ('paired.py', 'controls.py', 'flipped.py', 'simultaneous.py', 'sdk-span-control.py',
             'cooperating-plan.json', 'heldout-fixture-sha256.json'):
    shutil.copyfile(h.parent / name, controls / name)
shutil.copytree(h.parent / 'heldout-fixture', controls / 'heldout-fixture')
subprocess.run([sys.executable, '-B', out / 'verify-witness.py', out], check=True)
subprocess.run([sys.executable, '-B', runner / 'analyze.py', '--public', out], check=True)
