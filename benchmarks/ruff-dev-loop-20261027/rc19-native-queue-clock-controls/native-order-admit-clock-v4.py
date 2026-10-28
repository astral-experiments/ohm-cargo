"""Bind a completed C5 clean comparison and independent H8 inputs before admitting clocks."""
from pathlib import Path
import fcntl
import hashlib
import json
import sys


def sha(path):
    with path.open('rb') as data:
        return hashlib.file_digest(data, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


expected_h8, = sys.argv[1:]
assert len(expected_h8) == 64 and all(c in '0123456789abcdef' for c in expected_h8)
root = Path.home() / '.cache/ohm-18-ty-e2e-link-20261028'
study = root / 'native-ready-order19'
reports = study / 'reports'
ops = root / 'ops'
source = {'A': '235f9228651b74c591e6f62cae4c9b761448dd2d', 'B': '4b0751af97bfa22204a013d0d1f0707382b0df52'}
lock = (root / 'measure.lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
admission_path = reports / 'functional-admission-v4.json'
admission = read(admission_path)
assert admission['eligible'] and len(admission['receipts']) == 12 and len(admission['comparisons']) == 14
assert admission['plan_sha256'] == '467090560adc9c413466e40f2b80770ab781245f0fa8af3ad7839a94829b10a6'
for relative, digest in admission['receipts'].items():
    assert sha(reports / relative / 'result.json') == digest
rechecks = {}
for arm, revision in source.items():
    builder = study / 'images' / (arm + '-build.json')
    image = read(builder)
    assert (image['base'], image['tree'], image['binary']) == (source['A'], revision, admission['images'][arm])
    assert image['pgo'] == '481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7'
    assert sha(study / 'images' / arm) == image['binary'] and sha(builder) == admission['binding_sha256'][arm]
    cold = reports / ('clean-' + arm + '-raw-reopened-v6.json')
    guard = read(cold)
    assert guard['result_sha256'] == admission['receipts']['gate-v4-' + arm + '-cold-edit']
    assert guard['full_e2e_matches_warm'] and len(guard['actual_complete_products']) == 52
    rechecks[arm] = sha(cold)

caps = ops / 'native-order-h8-caps-v4.json'
assert sha(caps) == 'ecb94f95e49b43db0474bb55977f41b129d65db4dbc518332e0a0659991b9d4f'
pressure = read(caps)
assert pressure['eligible'] and not pressure['gib_with_treated_only_failure']
assert set(pressure['runs']) == {f'{arm}-{g}g' for arm in 'ab' for g in (2, 3, 4)}
for run in pressure['runs'].values():
    events = dict(line.split() for line in run['events'].splitlines())
    assert run['status'] == run['swap'] == 0 and events['oom'] == events['oom_kill'] == '0'
physical = ops / 'native-order-h8-physical-v4.json'
assert sha(physical) == expected_h8
controller = ops / 'native-order-clock-v4.py'
assert sha(controller) == 'bf46e005b3bfa877abf8d26e8f15e2413ffd1f41c74865cb1ab8cb167633b719'
evidence = {'eligible': True, 'source': source, 'images': admission['images'], 'functional_sha256': sha(admission_path), 'clean_output_readback_sha256': rechecks, 'h8_caps_sha256': sha(caps), 'h8_anchor_sha256': sha(physical), 'controller_sha256': sha(controller), 'plan_sha256': admission['plan_sha256'], 'order_sha256': sha(ops / 'native-order-random-order.json')}
result = reports / 'clock-release-v4.json'
with result.open('x') as out:
    json.dump(evidence, out, sort_keys=True, indent=2)
    out.write('\n')
print(sha(result), flush=True)
