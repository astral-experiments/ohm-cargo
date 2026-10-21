#!/usr/bin/env python3
"""Package the completed cumulative four-change IR and local native confirmations on CPU8."""
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'work/pr-evidence/four-changes-stack176'
DRIVER = ROOT / 'work/benchmark/frozen/run_restacked_ir-a5326e21625b.py'
SEAL_SHA = '9ff5aee1606282e928801701ac6a4fd7299ff12b15a748648ba256362c6140e9'
BASELINE = '59dc8bcef32b84a7ee2e84e02fbedfbcaa526783683af8cf19166723486ac27f'
CANDIDATE = '179f17531a2e9a3475c58965ad4a82248d8eb4af5ce8f1bbfe3d6be5632de86d'
TREE = '0a392258c801cff734d223a3f9af73d5b5a4e3c0'
COMPARISON = 'four-changes-stack176-5a16c750'
NATIVE_HOME = ROOT / 'work/benchmark/current_stack_native_local'
NATIVE_SEAL_SHA = 'cd62b627b91cd6ec8d2592040cf88490a39a65c889e86cf945729f9fd560d303'
NATIVE_DRIVER_SHA = '6cd1392609e49d9c2f08bf239d6b0b0f7e2f8c57a23d8399ac10d87c82a2502a'
files, raw = {}, {}
sys.dont_write_bytecode = True
assert not (set(os.sched_getaffinity(0)) & set(range(8)))
assert not (OUT / 'SHA256SUMS').exists(), 'Preserve an already sealed package'
assert json.loads((NATIVE_HOME / 'status.json').read_text())['state'] == 'complete'
assert json.loads((NATIVE_HOME / 'exit.json').read_text())['returncode'] == 0


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def add(source, destination, archive=False):
    path = ROOT / source
    assert path.is_file() and not path.is_symlink(), path
    data = path.read_bytes()
    collection = raw if archive else files
    assert destination not in collection, destination
    if not archive:
        data.decode('utf-8')
    collection[destination] = data
    return data


assert sha(DRIVER.read_bytes()) == 'a5326e21625bb701e41c6571e843ff16677c49ad785776c1ab67419aeae5ad60'
spec = importlib.util.spec_from_file_location('frozen_ir_for_packaging', DRIVER)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
driver.verify_inputs()
driver.verify_seal(SEAL_SHA)
assert sha((NATIVE_HOME / 'native_driver.py').read_bytes()) == NATIVE_DRIVER_SHA
spec = importlib.util.spec_from_file_location('completed_local_native_for_packaging', NATIVE_HOME / 'native_driver.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
native.verify_assets()
native.verify_seal(NATIVE_SEAL_SHA)
core = native.load_core()
native_status = json.loads((NATIVE_HOME / 'status.json').read_text())
assert [row['workflow'] for row in native_status['completed']] == [workflow for workflow, _ in native.PLAN]
native_audits = {}
OUT.mkdir(exist_ok=True)
for name in ['README.md', 'REPRODUCE.md', 'VALIDATION.md']:
    files[name] = (OUT / name).read_bytes()
assert b'will be filled in' not in files['README.md'], 'Finalize the complete native outcomes before sealing'
for name in ['paired.py', 'paired_repeated.py']:
    add('work/benchmark/frozen/' + name, 'harness/' + name)
for name in ['test_paired.py', 'test_paired_repeated.py', 'strip_binaries.py']:
    add('work/benchmark/' + name, 'harness/' + name)
add('work/profiling-tools/ohm-valgrind-env.c', 'harness/ohm-valgrind-env.c')
for path in [DRIVER, driver.HELPER]:
    add(str(path.relative_to(ROOT)), 'historical/harness/' + path.name)
for path in driver.PROTOCOLS:
    add(str(path.relative_to(ROOT)), 'protocols/' + path.name)
for name in ['protocol.md', 'protocol-instruction-restored.md', 'protocol-upstream-175.md']:
    add('work/benchmark/' + name, 'protocols/historical/' + name)
add(str(driver.SEAL.relative_to(ROOT)), 'validation/current-stack-ir-input-seal.json')
add(str(driver.SOURCES.relative_to(ROOT)), 'build/restacked-path-sources.json')
for name in ['stack179-port.json', 'current-stack-build-patches.json']:
    add(str((driver.SOURCE_COPIES / name).relative_to(ROOT)), 'build/source-records/' + name)
add('work/patches/path-cache-stack179.patch', 'build/path-cache-stack179.patch')
add('work/path-cache-stack179-publication/code-publication.json', 'validation/code-publication.json')
for name in ['restacked-pass-snapshot.json', 'restacked-177-179-original-failures.json']:
    add('work/pr-evidence/ci/' + name, 'validation/ci/' + name)
publication = json.loads(files['validation/code-publication.json'])
assert publication['tree'] == TREE and publication['base_commit'] == '19718e6d1637244ffbb193334f50bae3ffca1be5'
ci = json.loads(files['validation/ci/restacked-pass-snapshot.json'])
assert any(row['head'] == publication['commit'] and row['status'] == 'completed' and row['conclusion'] == 'success' for row in ci['runs'])

# The immutable IR seal covers all four planned batches. The two cumulative
# confirmations are the primary data below; prerequisite results stay separate.
for comparison, workflow, _ in driver.PLAN:
    source = driver.paths(comparison, workflow)['config']
    add(str(source.relative_to(ROOT)), 'configs/' + source.name)
for workflow in ['check', 'test']:
    add(f'work/benchmark/{workflow}-build-output-pr175-production-ir.json', f'historical/configs/{workflow}-derivation-source.json')
for name in driver.FROZEN_FILES:
    add(str((driver.FROZEN / name).relative_to(ROOT)), 'build/frozen/' + name)
for name in ['provenance.json', 'audit-cohort.json']:
    add(str((driver.RESULTS / name).relative_to(ROOT)), 'build/results/' + name)
for variant in driver.TREES:
    for suffix in ['build.json', 'strip.json']:
        name = f'cargo-{variant}.{suffix}'
        add(str((driver.RESULTS / name).relative_to(ROOT)), 'build/results/' + name)
    for suffix in ['.source.patch', '.occupancy.json', '.batch-status.json']:
        name = variant + suffix
        add(str((driver.RESULTS / name).relative_to(ROOT)), 'build/results/' + name)
    for suffix in ['.stdout', '.stderr']:
        name = variant + suffix
        add(str((driver.RESULTS / name).relative_to(ROOT)), 'build/logs/' + name, True)

extracts, inventory, manifests, summaries = [], {}, {}, {}
for workflow, seed in [('check', 2026102171), ('test', 2026102172)]:
    destination = driver.paths(COMPARISON, workflow)
    directory = destination['output']
    label = workflow + '-ir-confirmation'
    manifest = json.loads((directory / 'manifest.json').read_text())
    samples = json.loads((directory / 'samples.json').read_text())
    integrity = json.loads((directory / 'integrity.json').read_text())
    gate = json.loads((directory / 'instruction-gate.json').read_text())
    assert manifest['state'] == 'complete' and manifest['phase'] == 'confirmation'
    assert (manifest['pairs'], manifest['warmup_pairs'], manifest['seed']) == (12, 2, seed)
    assert manifest['variant_sha256'] == manifest['variant_sha256_after'] == {'baseline': BASELINE, 'candidate': CANDIDATE}
    assert manifest['recorded_file_sha256'] == manifest['recorded_file_sha256_after']
    assert integrity['state'] == 'passed' and integrity['invocations_verified'] == integrity['profile_hashes_verified'] == 28
    assert gate == driver.previous.result_gate(directory) and gate['passes_instruction_gate']
    assert all(gate['gate_checks'].values())
    for name in ['analysis.json', 'manifest.json', 'samples.json', 'samples.csv', 'integrity.json', 'instruction-gate.json']:
        add(str((directory / name).relative_to(ROOT)), f'results/{label}/{name}')
    profiles = {Path(row['metric_files']['cargo_ir']['path']).name: row for row in samples}
    count = 0
    for path in sorted(directory.rglob('*')):
        if not path.is_file():
            continue
        assert not path.is_symlink()
        count += 1
        relative = str(path.relative_to(directory))
        if path.name.startswith('callgrind-') and path.suffix == '.out':
            data = path.read_bytes()
            sample = profiles[path.name]
            assert sha(data) == sample['metric_files']['cargo_ir']['sha256']
            lines = [line for line in data.decode().splitlines() if line.startswith(('events:', 'summary:', 'totals:'))]
            events = next(line.split(':', 1)[1].split() for line in lines if line.startswith('events:'))
            counts = next(line.split(':', 1)[1].split() for line in lines if line.startswith('summary:'))
            assert int(counts[events.index('Ir')]) == sample['metrics']['cargo_ir']
            extracts.append({'run': label, 'file': relative, 'sha256': sha(data), 'bytes': len(data),
                             'counter_lines': lines, 'cargo_ir': sample['metrics']['cargo_ir'],
                             'sample': {key: sample[key] for key in ['stage', 'pair', 'order', 'position', 'variant']}})
        else:
            add(str(path.relative_to(ROOT)), 'results/' + label + '/' + relative, True)
    for path in sorted(destination['preflight'].iterdir()):
        if path.is_file():
            add(str(path.relative_to(ROOT)), f'validation/{workflow}-preflight/' + path.name, True)
    add(str((destination['preflight'] / 'report.json').relative_to(ROOT)), f'validation/{workflow}-preflight.json')
    inventory[label] = {'source_directory': str(directory), 'source_files': count,
                        'raw_files': count - len(profiles), 'profiles_extracted': len(profiles), 'samples': len(samples)}
    manifests[label] = manifest
    stats = gate['statistics']
    summaries[label] = {'pairs': stats['pairs'], 'seed': seed, 'warmup_pairs': 2,
                        'reduction_percent': stats['paired_geometric_mean_count_reduction'] * 100,
                        'interval_99_percent': [value * 100 for value in stats['bootstrap_count_reduction_interval']],
                        'wins': stats['wins'], 'losses': stats['losses'], 'sign_p': stats['exact_two_sided_sign_p'],
                        'gate_checks': gate['gate_checks'], 'passes_instruction_gate': True}
assert len(extracts) == 56
events = []
for line in (ROOT / 'work/benchmark/results/restacked-current-stack-driver.log').read_text().splitlines():
    row = json.loads(line)
    if row.get('comparison') == COMPARISON:
        events.append(line)
assert sum(json.loads(line)['event'] == 'fixed_batch_complete' for line in events) == 2
files['validation/cumulative-only-driver-events.jsonl'] = ('\n'.join(events) + '\n').encode()
for path in sorted(NATIVE_HOME.rglob('*')):
    if not path.is_file() or '__pycache__' in path.parts:
        continue
    relative = path.relative_to(NATIVE_HOME)
    if relative.parts[0] == 'binaries':
        continue
    archive = path.suffix in {'.stdout', '.stderr', '.log'}
    add(str(path.relative_to(ROOT)), 'native/adaptation/' + str(relative), archive)
add('work/cargo-audit/current-stack-native-local-review.json', 'native/independent-source-review.json')
add('work/benchmark/protocol-four-changes-stack176-native-local-amendment.md', 'protocols/protocol-four-changes-stack176-native-local-amendment.md')
for index, (workflow, seed) in enumerate(native.PLAN):
    destination = native.paths(workflow)
    directory = destination['output']
    label = workflow + '-native-confirmation'
    native_audits[workflow] = native.audit_complete(core, workflow, seed)
    integrity = json.loads((directory / 'integrity.json').read_text())
    assert integrity['state'] == 'passed' and integrity['invocations_verified'] == 512
    gate = native.gate(directory)
    assert gate == json.loads((directory / 'native-gate.json').read_text())
    assert native_status['completed'][index] == {'workflow': workflow, 'directory': str(directory), **gate}
    manifest = json.loads((directory / 'manifest.json').read_text())
    analysis = json.loads((directory / 'analysis.json').read_text())
    assert manifest['variant_sha256'] == manifest['variant_sha256_after'] == {'baseline': BASELINE, 'candidate': CANDIDATE}
    count = 0
    for path in sorted(directory.rglob('*')):
        if not path.is_file():
            continue
        count += 1
        relative = path.relative_to(directory)
        add(str(path.relative_to(ROOT)), 'results/' + label + '/' + str(relative), True)
        if str(relative) in {'analysis.json', 'manifest.json', 'samples.json', 'samples.csv',
                             'subruns.json', 'subruns.csv', 'integrity.json', 'native-gate.json'}:
            add(str(path.relative_to(ROOT)), 'results/' + label + '/' + str(relative))
    for path in sorted(destination['preflight'].iterdir()):
        if path.is_file():
            add(str(path.relative_to(ROOT)), f'validation/{workflow}-native-preflight/' + path.name, True)
    add(str((destination['preflight'] / 'report.json').relative_to(ROOT)), f'validation/{workflow}-native-preflight.json')
    add(str(destination['config'].relative_to(ROOT)), f'configs/{workflow}-native-local-original.json')
    inventory[label] = {'source_directory': str(directory), 'source_files': count, 'raw_files': count,
                        'group_pairs': 30, 'warmup_group_pairs': 2, 'repetitions_per_variant': 8,
                        'invocations_including_warmup': 512}
    manifests[label] = manifest
    summaries[label] = {'group_pairs': 30, 'seed': seed, 'warmup_group_pairs': 2, 'repetitions_per_variant': 8,
                        'reduction_percent': gate['reduction'] * 100,
                        'interval_99_percent': [value * 100 for value in gate['interval_99']],
                        'wins': analysis['wins'], 'losses': analysis['losses'], 'sign_p': gate['sign_p'],
                        'gate_checks': gate['gate_checks'], 'passes_native_gate': gate['passes_native_gate']}
files['validation/native-raw-reaudit.json'] = encoded(native_audits)
files['results/summary.json'] = encoded(summaries)
files['callgrind-counter-extracts.jsonl'] = b''.join((json.dumps(row, sort_keys=True) + '\n').encode() for row in extracts)
files['RAW-MANIFEST.json'] = encoded({name: {'sha256': sha(data), 'bytes': len(data)} for name, data in sorted(raw.items())})
add(str(Path(__file__).relative_to(ROOT)), 'historical/prepare_four_changes_stack176.py')
by_hash = {}
for name, data in (files | raw).items():
    by_hash.setdefault(sha(data), []).append(name)
files['INPUTS.json'] = encoded({label: {'variant_sha256': manifest['variant_sha256'],
    'recorded_file_sha256': {name: {'sha256': digest, 'package_locations': sorted(by_hash.get(digest, [])),
        'availability': 'packaged' if digest in by_hash else 'external runtime or historical input; provision and hash for replication'}
        for name, digest in manifest['recorded_file_sha256'].items()}} for label, manifest in manifests.items()})
files['CONTENTS.json'] = encoded({'runs': inventory, 'profile_extracts': len(extracts),
    'raw_files': len(raw), 'raw_bytes': sum(map(len, raw.values())),
    'full_profiles': 'Retained in task workspace; exact counter lines and hashes packaged.',
    'scope': 'Independent current176 versus all four changes: two fixed IR and two fixed local native confirmations. No pooling with historical or incremental comparisons.'})
driver.verify_seal(SEAL_SHA)
native.verify_seal(NATIVE_SEAL_SHA)
archive = OUT / 'raw-results.tar.gz'
with archive.open('xb') as stream:
    with gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|') as tar:
            for name, data in sorted(raw.items()):
                entry = tarfile.TarInfo(name)
                entry.size, entry.mode, entry.mtime = len(data), 0o644, 0
                tar.addfile(entry, io.BytesIO(data))
for name, data in files.items():
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
package = {name: {'sha256': sha(data), 'bytes': len(data)} for name, data in sorted(files.items())}
package['raw-results.tar.gz'] = {'sha256': sha(archive.read_bytes()), 'bytes': archive.stat().st_size}
(OUT / 'SHA256SUMS').write_text(''.join(value['sha256'] + '  ' + name + '\n' for name, value in sorted(package.items())))
manifest_path = OUT.parent / 'four-changes-stack176-manifest.json'
manifest_path.write_bytes(encoded(package))
print(json.dumps({'text_files': len(files), 'raw_files': len(raw), 'profile_extracts': len(extracts),
                  'archive': package['raw-results.tar.gz'], 'manifest_sha256': sha(manifest_path.read_bytes()),
                  'statistics': summaries}, indent=2))
