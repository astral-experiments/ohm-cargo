#!/usr/bin/env python3
"""Bind the finished matched pair to reviewed controls; package locally only."""
import datetime
import hashlib
import json
from pathlib import Path
import tarfile

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
COHORT = WORK / 'production-build/host2-inheritance-stack180'
ROOT = '/tmp/ohm-hillclimb-20261021-inheritance-measurement'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


source = json.loads((HERE / 'source-freeze.json').read_text())
for filename, digest in source['files'].items():
    assert sha(HERE / filename) == digest, filename
for filename, digest in source['external_inputs'].items():
    assert sha(WORK / filename) == digest, filename
review = json.loads((HERE / 'source-review.json').read_text())
assert review['status'] == 'passed' and review['source_freeze_sha256'] == sha(HERE / 'source-freeze.json')
audit = json.loads((COHORT / 'results/audit-pair.json').read_text())
assert sha(COHORT / 'results/audit-pair.json') == '00fee70efe3e5f94ee55e7a76ac1baf921659f1e1895606577b55506316f105e'
pair_review = json.loads((COHORT / 'results/root-pair-review.json').read_text())
assert pair_review['status'] == 'passed' and all(pair_review['checks'].values())
assert pair_review['pair_audit_sha256'] == sha(COHORT / 'results/audit-pair.json')
assert audit['cohort'] == 'host2-inheritance-stack180'
assert audit['common_build_inputs_sha256'] == 'd3c153d203c6a933add9ce89a6b496ae8fcb4b9039376d877854359d9209caeb'
assert audit['frozen_input_manifest_sha256'] == sha(COHORT / 'frozen/manifest.json') == 'ff3455f081f9b08c06f26fbe029fcfcdbe243b0e905a96f7237181ea5d6806cd'
assert audit['provenance_sha256'] == sha(COHORT / 'results/provenance.json')
assert audit['audit_script_sha256'] == sha(COHORT / 'audit.py')
assert audit['collector_sha256'] == sha(COHORT / 'collect_variant.py')
names = {'baseline': 'inheritance-stack180-baseline', 'candidate': 'inheritance-stack180-shared'}
trees = {'baseline': '0a392258c801cff734d223a3f9af73d5b5a4e3c0', 'candidate': 'c4178b67e0b3a64a12b9b58f84b97323b99d734e'}
assert {row['variant'] for row in audit['records']} == set(names.values())
variants = {}
files = {'controller/' + name: HERE / name for name in source['files']}
files.update({'controller/source-freeze.json': HERE / 'source-freeze.json',
              'controller/source-review.json': HERE / 'source-review.json',
              'controller/protocol.json': WORK / 'workspace-inheritance-candidate/protocol.json',
              'controller/source-ci.json': WORK / 'workspace-inheritance-publication/ci-validation.json',
              'controller/reference-native-controller.py': WORK / 'allocator-native/native_controller-v3.py',
              'benchmark/frozen/paired.py': WORK / 'benchmark/frozen/paired.py',
              'benchmark/frozen/paired_repeated.py': WORK / 'benchmark/frozen/paired_repeated.py',
              'profiling-tools/ohm-valgrind-env.c': WORK / 'profiling-tools/ohm-valgrind-env.c',
              'profiling-tools/ohm-valgrind-env.so': WORK / 'profiling-tools/ohm-valgrind-env.so',
              'assets/ohm-1.99.0-6-x86_64-unknown-linux-gnu.tar.gz': WORK / 'ohm-1.99.0-6-x86_64-unknown-linux-gnu.tar.gz'})
for name in ('valgrind_1%3a3.22.0-0ubuntu3_amd64.deb', 'libc6-dbg_2.39-0ubuntu8.9_amd64.deb'):
    files['assets/' + name] = WORK / 'profiling-tools' / name
for name in ('native_controller-v2.py', 'native_controller-v3.py',
             'warming-amendment-v3.json', 'root-warming-v3-review.json', 'WARMING-AMENDMENT-v3.md',
             'controller-warming-v3.diff', 'controller-warming-v3-ast-proof.json',
             'warming-amendment-v3-draft01.json', 'WARMING-AMENDMENT-v3-draft01.md',
             'controller-warming-v3-ast-proof-draft01.json'):
    files['controller/' + name] = WORK / 'allocator-native' / name
for path in sorted((COHORT / 'frozen').iterdir()):
    assert path.is_file() and not path.is_symlink()
    files['controller/cohort/frozen/' + path.name] = path
for name in ('audit.py', 'collect_variant.py', 'build_driver_host2_inheritance_stack180.py'):
    files['controller/cohort/' + name] = COHORT / name
for name in ('audit-pair.json', 'root-pair-review.json', 'provenance.json', 'ownership.json'):
    files['controller/cohort/results/' + name] = COHORT / 'results' / name
for variant, name in names.items():
    binary = COHORT / 'results' / ('cargo-' + name)
    row = next(row for row in audit['records'] if row['variant'] == name)
    assert row['source_tree'] == trees[variant]
    assert row['common_build_inputs_sha256'] == audit['common_build_inputs_sha256']
    variants[variant] = sha(binary)
    assert variants[variant] == row['stripped_sha256']
    files['controller/binaries/' + binary.name] = binary
    for suffix in ('.build.json', '.strip.json'):
        files['controller/cohort/results/' + binary.name + suffix] = COHORT / 'results' / (binary.name + suffix)
    for suffix in ('.stdout', '.stderr', '.source.patch', '.occupancy.json', '.batch-status.json'):
        files['controller/cohort/results/' + name + suffix] = COHORT / 'results' / (name + suffix)
assert variants['baseline'] == '3164f9287711f122fa9636a7816ed8749598706ac5076d66051a036dcef51037'
assert variants['candidate'] == '3b1a2e4e3654b7b23816fbb54c51072cb356486c36052a5bcd6c4d3d2e6a07e9'
correctness = WORK / 'workspace-inheritance-candidate'
proof = json.loads((correctness / 'correctness-seal.json').read_text())
for name, digest in proof['files'].items():
    assert sha(correctness / name) == digest
    files['controller/correctness/' + name] = correctness / name
for name in ('correctness-seal.json', 'root-correctness-review.json'):
    files['controller/correctness/' + name] = correctness / name
out = HERE / 'delivery'
out.mkdir(exist_ok=False)
record = {'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'root': ROOT, 'host': 'charlie-oss-2',
          'source_freeze_sha256': sha(HERE / 'source-freeze.json'), 'source_review_sha256': sha(HERE / 'source-review.json'),
          'variants': variants, 'source_trees': trees, 'files': {name: sha(path) for name, path in files.items()}}
assert record['files']['assets/ohm-1.99.0-6-x86_64-unknown-linux-gnu.tar.gz'] == '98a4f4f99ea1ff36e10209258724426496afbbcab14d746294fe53a2fedad37c'
(out / 'delivery.json').write_text(json.dumps(record, indent=2) + '\n')
files['delivery.json'] = out / 'delivery.json'
with tarfile.open(out / 'payload.tar', 'x:') as archive:
    for name, path in files.items():
        assert path.is_file() and not path.is_symlink()
        archive.add(path, arcname=name, recursive=False)
for name, digest in record['files'].items():
    assert sha(files[name]) == digest, name
binding = {'delivery_sha256': sha(out / 'delivery.json'), 'archive_sha256': sha(out / 'payload.tar'),
           'variants': variants, 'source_trees': trees, 'files': len(record['files']),
           'status': 'packaged-locally-not-staged', 'no_performance_execution': True}
(out / 'binding.json').write_text(json.dumps(binding, indent=2) + '\n')
print(json.dumps(binding, indent=2))
