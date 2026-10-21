#!/usr/bin/env python3
"""Independent root reproduction from the complete, already-audited fixed IR data."""
from pathlib import Path
import datetime
import hashlib
import json
import math
import random

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
COLLECTION = HERE / 'collections/ir'
REMOTE = COLLECTION / 'remote'
ROOT = '/tmp/ohm-hillclimb-20261021/scheduler-bitsets-stack181'

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def read(path):
    return json.loads(path.read_text())

def close(left, right):
    assert math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-12), (left, right)

def quantile(values, probability):
    index = (len(values) - 1) * probability
    low = math.floor(index)
    high = math.ceil(index)
    return values[low] + (values[high] - values[low]) * (index - low)

started = datetime.datetime.now(datetime.timezone.utc).isoformat()
review_path = HERE / 'independent-ir-review/review.json'
assert sha(review_path) == '755e5c5e7ca6a303aeb03842b821e86e7d79c089956e3c86a3f14b12eaa66ec1'
review = read(review_path)
assert review['status'] == 'passed' and review['integrity_status'] == 'passed'
assert review['phase'] == 'ir' and review['qualifies'] is True
assert review['measurement_seal_sha256'] == 'ce79b88c2f2fe7cf9c2217fa84c982c6ad9473f1c38406bf5075d6d6c26f1dcf'
assert sha(HERE / 'source-freeze.json') == '25965d3a2a4d087ac773727ddd600707c5fd3cb13a189d62cb8fe991ed7445fa'
assert sha(HERE / 'reviewer/source-freeze.json') == 'da5ea42afc7f49a4bc4298fc1b9e965d80bc7413bcfb75baa551bfe2240f458d'
source = read(HERE / 'source-freeze.json')
inputs = {HERE / name: digest for name, digest in source['files'].items()}
inputs.update({WORK / name: digest for name, digest in source['external_inputs'].items()})
for path, digest in inputs.items():
    assert sha(path) == digest, str(path)
transfer = read(COLLECTION / 'transfer-manifest.json')
assert sha(COLLECTION / 'transfer-manifest.json') == review['transfer_manifest_sha256'] == '92d0d73e38fc67dcd95f23820bd25119b4c423b04102bdd9dc74ea716269f455'
assert transfer['files'] == review['raw_file_sha256']
actual = {str(path.relative_to(REMOTE)) for path in REMOTE.rglob('*') if path.is_file()}
assert actual == set(transfer['files']) and len(actual) == 568
for name, digest in transfer['files'].items():
    path = REMOTE / name
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    assert not path.is_symlink() and sha(path) == digest, name
assert sha(COLLECTION / 'payload.tar') == '9c5df495f48f19ffce3312a22adc0d94f6b8bdfdef604dd6c522f90f3b78172b'
assert sha(HERE / 'launch-ir.json') == review['launch_receipt_sha256'] == '332af2633fe65043ea021d23244481a73acaa90cd977b09f44d0038ea3d6b340'
assert sha(REMOTE / 'results/ir-status.json') == review['terminal_status_sha256']
assert read(HERE / 'independent-ir-review/raw-integrity.json')['statistics_computed'] is False

prepared = []
for workflow, seed in [('test', 20261021131), ('check', 20261021132)]:
    directory = REMOTE / ('results/ir-' + workflow)
    samples = read(directory / 'samples.json')
    assert len(samples) == 28
    assert sum(row['stage'] == 'warmup' for row in samples) == 4
    assert sum(row['stage'] == 'measurement' for row in samples) == 24
    grouped = {}
    profiles = set()
    for row in samples:
        assert row['returncode'] == 0 and row['executable_unchanged'] is True
        assert row['installed_sha256'] == review['variants'][row['variant']]
        name = 'callgrind-{}-{}-{}.out'.format(row['stage'], row['pair'], row['variant'])
        profile = directory / name
        profiles.add(profile)
        events, summaries = [], []
        with profile.open() as stream:
            for line in stream:
                if line.startswith('events:'):
                    events.append(line.split(':', 1)[1].split())
                elif line.startswith('summary:'):
                    summaries.append(int(line.split(':', 1)[1].strip()))
        assert events == [['Ir']] and summaries == [row['metric_cargo_ir']]
        profile_record = review['profiles'][ROOT + '/results/ir-' + workflow + '/' + name]
        assert profile_record['Ir'] == row['metric_cargo_ir'] and profile_record['sha256'] == sha(profile)
        if row['stage'] == 'measurement':
            group = grouped.setdefault(row['pair'], {})
            assert row['variant'] not in group
            group[row['variant']] = row
    assert profiles == set(directory.glob('callgrind-*.out'))
    assert sorted(grouped) == list(range(12))
    logs, orders = [], {'AB': [], 'BA': []}
    for pair in range(12):
        group = grouped[pair]
        assert set(group) == {'baseline', 'candidate'}
        baseline, candidate = group['baseline'], group['candidate']
        assert baseline['order'] == candidate['order']
        ratio = baseline['metric_cargo_ir'] / candidate['metric_cargo_ir']
        value = math.log(ratio)
        logs.append(value)
        orders[baseline['order']].append(value)
    assert {key: len(values) for key, values in orders.items()} == {'AB': 6, 'BA': 6}
    assert next(item for item in review['workflows'] if item['workflow'] == workflow)['seed'] == seed
    prepared.append((workflow, seed, directory, profiles, logs, orders))

results = []
for workflow, seed, directory, profiles, logs, orders in prepared:
    mean = math.fsum(logs) / len(logs)
    rng = random.Random(1701)
    draws = sorted(math.fsum(rng.choices(logs, k=len(logs))) / len(logs) for _ in range(20000))
    reduction = 1 - math.exp(-mean)
    interval = [1 - math.exp(-quantile(draws, probability)) for probability in (0.005, 0.995)]
    wins, losses = sum(value > 0 for value in logs), sum(value < 0 for value in logs)
    count = wins + losses
    p_value = min(1.0, 2 * sum(math.comb(count, k) for k in range(min(wins, losses) + 1)) / 2 ** count)
    order_ratios = {key: math.exp(math.fsum(values) / len(values)) for key, values in orders.items()}
    expected = next(item for item in review['completed'] if item['workflow'] == workflow)
    close(reduction, expected['reduction'])
    for left, right in zip(interval, expected['interval_99']):
        close(left, right)
    close(p_value, expected['sign_p'])
    qualifies = reduction >= 0.01 and interval[0] > 0 and p_value <= 0.01 and all(value > 1 for value in order_ratios.values())
    assert qualifies == expected['passes_gate'] and qualifies
    results.append({'workflow': workflow, 'seed': seed, 'pairs': 12, 'warmup_pairs': 2,
                    'profiles_checked': len(profiles), 'reduction': reduction, 'interval_99': interval,
                    'sign_p': p_value, 'wins': wins, 'losses': losses, 'ties': 12 - count,
                    'order_ratios': order_ratios, 'passes_gate': qualifies,
                    'samples_sha256': sha(directory / 'samples.json')})

result = {'status': 'passed', 'phase': 'ir', 'qualifies': True, 'workflows': results,
          'started_at': started, 'finished_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'raw_files_rehashed': len(actual), 'frozen_inputs_rehashed': len(inputs),
          'source_freeze_sha256': sha(HERE / 'source-freeze.json'),
          'measurement_seal_sha256': review['measurement_seal_sha256'],
          'independent_review_sha256': sha(review_path), 'variants': review['variants'],
          'program_sha256': sha(Path(__file__)),
          'method': 'All raw files and each profile summary verified before independent fixed paired-log, 20000-draw seed-1701 bootstrap and exact sign-test reproduction.'}
output = HERE / 'root-ir-reproduction.json'
assert not output.exists()
output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
print(json.dumps(result, sort_keys=True))
