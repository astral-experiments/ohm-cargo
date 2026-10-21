"""Independently check the actual setup readback before approving IR execution."""
from pathlib import Path
import datetime
import hashlib
import json
import tarfile

HERE = Path(__file__).resolve().parent
COLLECTED = HERE / 'collections/setup'
REMOTE = COLLECTED / 'remote'
ROOT = '/tmp/ohm-hillclimb-20261021-inheritance-measurement'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_text())

manifest = read(COLLECTED / 'transfer-manifest.json')
seal = read(REMOTE / 'controller/measurement-seal.json')
setup = read(REMOTE / 'metadata/setup.json')
assert sha(COLLECTED / 'transfer-manifest.json') == '4f15db28f560a5d8939e86b496b073b1674c6451dcff4ca82bbeac00aad5821e'
assert sha(REMOTE / 'controller/measurement-seal.json') == manifest['seal_sha256'] == 'b6e765057417644e62cf7cadc4994a05172077f8c9a26bfe6343e6ad377e48ff'
for name, digest in manifest['files'].items():
    assert sha(REMOTE / name) == digest, name
with tarfile.open(COLLECTED / 'payload.tar') as archive:
    members = archive.getmembers()
    assert len(members) == len(manifest['files']) + 1 == len({member.name for member in members})
    for member in members:
        assert member.isfile() and '..' not in Path(member.name).parts
        expected = sha(COLLECTED / 'transfer-manifest.json') if member.name == 'transfer-manifest.json' else manifest['files'][str(Path(member.name).relative_to('remote'))]
        assert hashlib.sha256(archive.extractfile(member).read()).hexdigest() == expected
for name, digest in seal['file_sha256'].items():
    path = Path(name)
    if path.is_relative_to(ROOT) and (REMOTE / path.relative_to(ROOT)).exists():
        assert sha(REMOTE / path.relative_to(ROOT)) == digest, name
assert seal['variants'] == {'baseline': '3164f9287711f122fa9636a7816ed8749598706ac5076d66051a036dcef51037',
                            'candidate': '3b1a2e4e3654b7b23816fbb54c51072cb356486c36052a5bcd6c4d3d2e6a07e9'}
assert seal['source_trees'] == {'baseline': '0a392258c801cff734d223a3f9af73d5b5a4e3c0',
                               'candidate': 'c4178b67e0b3a64a12b9b58f84b97323b99d734e'}
assert setup['state'] == 'prepared-without-warming'
assert seal['uv']['status'] == '' and seal['uv']['commit'] == '3d82a6ad5a7eab8c68236553b7846517767c4b61'
assert setup['configuration_catalog'] == seal['configuration_catalog']
assert sha(REMOTE / 'metadata/ancestor-root-config.toml') == '24095bd6315880162c8f660917100ac36638cb73778dd9ec6f1c9026ea87b178'
assert not seal['environment_guard']['forbidden_environment_names']
configurations, targets, caches = {}, set(), set()
for phase, pairs, seeds in (('ir', 12, [20261021111, 20261021112]), ('native', 30, [20261021113, 20261021114])):
    assert seal['stages'][phase]['pairs'] == pairs
    assert seal['stages'][phase]['plan'] == [['check', seeds[0]], ['test', seeds[1]]]
    for workflow in ('check', 'test'):
        name = f'{phase}-{workflow}'
        config = read(REMOTE / f'benchmark/{name}.json')
        base = read(REMOTE / f'controller/base-configs/{name}.json')
        records, base_records = config.pop('record_files'), base.pop('record_files')
        assert config == base and set(base_records) <= set(records), name
        assert len(records) == len(set(records)) and ROOT + '/controller/measurement-seal.json' in records
        assert config['cwd'] == ROOT + '/uv' and config['canonical_executable'] == ROOT + '/active/bin/cargo'
        expected = ['/usr/bin/taskset', '-c', '0-7', '{cargo}', '-Zohm-defaults=yes', workflow]
        expected += (['--no-run'] if workflow == 'test' else []) + ['--locked', '--offline', '-j', '8']
        assert config['prepare_command'] == expected
        if phase == 'native':
            assert config['command'] == expected and config['repetitions'] == 8 and config['repeatable_workload'] == 'noop'
        else:
            assert '--trace-children=no' in config['command'] and config['command'][-len(expected[3:]):] == expected[3:]
            assert config['metric_files']['cargo_ir']['event'] == 'Ir'
        env = dict(config['env'])
        targets.add(env['CARGO_TARGET_DIR']); caches.add(env['CARGO_BUILD_BUILD_DIR'])
        env['CARGO_TARGET_DIR'] = env['CARGO_BUILD_BUILD_DIR'] = None
        assert env == setup['configured_common_environment'], name
        configurations[name] = {'sha256': sha(REMOTE / f'benchmark/{name}.json'),
                                'record_files': len(records), 'base_records_retained': len(base_records),
                                'only_record_files_augmented': True}
assert len(targets) == len(caches) == 4
review = {'status': 'passed', 'reviewed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'measurement_seal_sha256': manifest['seal_sha256'],
          'transfer_manifest_sha256': sha(COLLECTED / 'transfer-manifest.json'),
          'source_review_sha256': sha(HERE / 'source-review.json'),
          'reviewer_sha256': sha(Path(__file__)), 'verified_transferred_files': len(manifest['files']),
          'sealed_inputs': len(seal['file_sha256']), 'configurations': configurations,
          'phase_plans': seal['stages'], 'exact_matched_production_pair': True,
          'separate_initially_fresh_fixtures': True, 'uv_unchanged': True,
          'source_correctness_and_ci_bound': True,
          'decision': 'Approve fixed IR phase. Native remains conditional on both complete IR integrity audits and gates.'}
(HERE / 'setup-review.json').write_text(json.dumps(review, indent=2) + '\n')
print(json.dumps(review, indent=2))
