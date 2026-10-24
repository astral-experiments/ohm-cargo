"""Replay the existing native block's raw joins before statistical analysis."""
import csv
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'confirmation-collection-01'
REMOTE = Path('/home/dev-user/ohm-loader-restack-20261024')
os.sched_setaffinity(0, set(range(24, 32)))
sys.path.insert(0, str(ROOT / 'controls'))
import loader_fixture_delta as fixture
import maintenance_02 as maintenance
import paired
import restack_control_02 as control

verification = json.loads((ROOT / 'confirmation-collection-01-local-verification.json').read_bytes())
assert verification['all_hashes_sizes_modes_pass']
operational = verification['archive']['operational']
assert operational['owner_state'] == operational['native_state'] == 'complete'
assert operational['owner_failure'] is operational['native_failure'] is None
assert operational['baseline_native_snapshot_restored'] is True
manifest_bytes = (DATA / 'records/confirmation-collection-01.manifest.json').read_bytes()
assert hashlib.sha256(manifest_bytes).hexdigest() == verification['archive']['manifest_sha256']
members = {row['path']: row for row in json.loads(manifest_bytes)['files']}


def local(path):
    return DATA / Path(path).relative_to(REMOTE)


def authenticated(path):
    relative = str(path.relative_to(DATA))
    data = path.read_bytes()
    assert len(data) == members[relative]['bytes']
    assert hashlib.sha256(data).hexdigest() == members[relative]['sha256']
    return data


def read(path):
    return json.loads(authenticated(path))


for path in (DATA / 'work/benchmark').glob('*.py'):
    assert authenticated(path) == (ROOT / 'controls' / path.name).read_bytes()
terminal = read(DATA / 'records/confirmation-01.terminal.json')
assert terminal['state'] == 'complete' and terminal['failure'] is None
assert terminal['inputs']['sha256'] == '42047feeedcf531631c0517875aad739f6be944ba306dfaef2ec51209e9e78f4'
assert terminal['authority']['sha256'] == '2f9460944e0e3e2d6be672da986592929683ac2b8ae5ae5458bcf77a1018d463'
assert terminal['effects_analyzed'] is terminal['tests_executed'] is False
inputs = read(local(terminal['inputs']['path']))
authority = read(local(terminal['authority']['path']))
protocol = read(local(inputs['protocol']['path']))
configuration = read(local(inputs['configuration']['path']))
assert authority['status'] == 'approved'
assert authority['inputs_sha256'] == terminal['inputs']['sha256']
assert hashlib.sha256(authenticated(local(terminal['inputs']['path']))).hexdigest() == terminal['inputs']['sha256']
assert hashlib.sha256(authenticated(local(terminal['authority']['path']))).hexdigest() == terminal['authority']['sha256']
assert hashlib.sha256(authenticated(local(inputs['configuration']['path']))).hexdigest() == inputs['configuration']['sha256']
assert hashlib.sha256(authenticated(local(inputs['protocol']['path']))).hexdigest() == inputs['protocol']['sha256']
assert protocol['acceptance'] == inputs['original_acceptance']
output = local(terminal['output'])
assert terminal['output'] == authority['output']
run = read(output / 'manifest.json')
assert run['state'] == 'complete' and run['phase'] == 'confirmation'
assert (run['pairs'], run['warmup_pairs'], run['sample_count'], run['seed']) == (12, 0, 24, 2026102126)
assert run['configuration'] == configuration
assert run['configuration_sha256'] == inputs['configuration']['sha256']
assert not configuration.get('metric_files')
assert run['variant_sha256'] == run['variant_sha256_after']
assert run['recorded_file_sha256'] == run['recorded_file_sha256_after']
plan = [list(row) for row in paired.make_plan(12, 2026102126)]
assert run['plans'] == {'warmup': [], 'measurement': plan}
assert plan == protocol['balanced_order_plan']
fixture_root = DATA / 'work/loader-fixtures/uv-loader-restack'
fixture_manifest = read(fixture_root / 'fixture.json')
snapshots = {arm: read(fixture_root / 'snapshots' / arm / 'manifest.json') for arm in ('baseline', 'candidate')}
for arm, snapshot in snapshots.items():
    assert hashlib.sha256(authenticated(fixture_root / 'snapshots' / arm / 'inventory.jsonl')).hexdigest() == snapshot['inventory_sha256']
    assert run['variant_sha256'][arm] == snapshot['cargo_sha256']
restoration = terminal['restoration']
assert restoration['variant'] == 'baseline' and restoration['full_content_verification'] is True
assert restoration['inventory_sha256'] == snapshots['baseline']['inventory_sha256']
assert restoration['cargo_sha256'] == snapshots['baseline']['cargo_sha256']
assert restoration['snapshot_manifest_sha256'] == paired.sha256(fixture_root / 'snapshots/baseline/manifest.json')
samples = read(output / 'samples.json')
assert len(samples) == 24
assert [json.loads(line) for line in authenticated(output / 'samples.jsonl').splitlines()] == samples
csv_rows = list(csv.DictReader(authenticated(output / 'samples.csv').decode().splitlines()))
assert len(csv_rows) == 24
journal = [json.loads(line) for line in authenticated(fixture_root / 'journal.jsonl').splitlines()]
prepared = {}
for entry in journal:
    if entry['operation'] == 'prepare' and entry['batch'] == terminal['output']:
        key = (entry['stage'], entry['pair'], entry['position'], entry['variant'])
        assert key not in prepared
        prepared[key] = entry
assert len(prepared) == 24
expected_command = [configuration['canonical_executable'] if value == '{cargo}' else value for value in configuration['command']]
assert configuration['command'] == protocol['command']
expected_summaries = []
for index, sample in enumerate(samples):
    pair, position = divmod(index, 2)
    arm = plan[pair][position]
    key = ('measurement', pair, position, arm)
    assert tuple(sample[name] for name in ('stage', 'pair', 'position', 'variant')) == key
    assert sample['order'] == ('AB' if plan[pair][0] == 'baseline' else 'BA')
    assert sample['returncode'] == 0 and sample['executable_unchanged'] is True
    assert sample['command'] == expected_command
    assert sample['installed_sha256'] == run['variant_sha256'][arm]
    assert all(csv_rows[index][name] == str(sample[name]) for name in csv_rows[index])
    stdout, stderr = local(sample['stdout']), local(sample['stderr'])
    authenticated(stdout); authenticated(stderr)
    raw = read(stdout.with_name(stdout.name + '.command.json'))
    assert raw['command'] == sample['command'] and raw['cwd'] == configuration['cwd']
    assert all(sample[name] == value for name, value in raw['result'].items())
    prep = sample['prepare']
    assert prep['returncode'] == 0
    prep_stdout = local(prep['stdout'])
    prep_raw = read(prep_stdout.with_name(prep_stdout.name + '.command.json'))
    assert prep_raw['result'] == prep and prep_raw['cwd'] == configuration['cwd']
    assert prep_raw['environment_sha256'] == raw['environment_sha256']
    authenticated(local(prep['stderr']))
    entry = prepared[key]
    returned = json.loads(authenticated(prep_stdout))
    assert set(entry) == set(returned) | {'at'}
    assert {key: value for key, value in entry.items() if key != 'at'} == returned
    assert entry['full_content_verification'] is True
    assert entry['inventory_sha256'] == snapshots[arm]['inventory_sha256']
    assert entry['cargo_sha256'] == sample['installed_sha256']
    assert entry['snapshot_manifest_sha256'] == paired.sha256(fixture_root / 'snapshots' / arm / 'manifest.json')
    admission = read(output / f'pair-entry-{pair:02d}.json')
    assert admission['pair'] == pair and admission['order'] == plan[pair]
    assert maintenance.ready(admission['admitted'], protocol['pair_reservation_seconds'])
    waits = [json.loads(line) for line in authenticated(output / f'pair-wait-{pair:02d}.jsonl').splitlines()]
    assert waits[-1] == admission['admitted']
    assert all(row['ready'] == maintenance.ready(row, protocol['pair_reservation_seconds']) and row['wait_elapsed_seconds'] <= maintenance.MAX_WAIT_SECONDS for row in waits)
    control.same_service_cycle(admission['admitted'], read(stdout.with_suffix('.host-before.json')))
    control.same_service_cycle(admission['admitted'], read(stdout.with_suffix('.host-after.json')))
    runs = fixture.runlist(stdout, stderr)
    expected_summaries.append({'sample': list(key), 'checking_packages': runs['checking_packages'],
        'rustc_invocations': runs['rustc_invocations'], 'other_invocations': runs['other_invocations'],
        'build_script_outputs': runs['build_script_outputs'],
        'fresh_artifacts': sum(row['fresh'] for row in runs['artifacts']),
        'compiled_artifacts': sum(not row['fresh'] for row in runs['artifacts']),
        'inventory_sha256': entry['inventory_sha256'], 'restore_wall_ns_excluded': entry['restore_wall_ns']})
validation = read(output / 'loader-fixture-validation.json')
assert validation == {'valid': True, 'errors': [], 'samples': expected_summaries, 'source': fixture_manifest['source']}
report = {'state': 'passed', 'source_sha256': paired.sha256(Path(__file__)),
          'native_terminal_sha256': paired.sha256(DATA / 'records/confirmation-01.terminal.json'),
          'archive_sha256': verification['archive']['sha256'], 'files_authenticated': len(members),
          'pairs': 12, 'samples': 24, 'command_and_prepare_raw_receipts': 48,
          'host_before_after_records': 48, 'pair_admissions': 12,
          'source_inputs_restoration_order_streams_and_original_validation_match': True,
          'statistics_computed': False}
with (ROOT / 'raw-gates-01.json').open('x') as stream:
    json.dump(report, stream, indent=2)
    stream.write('\n')
print(json.dumps(report))
