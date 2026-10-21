#!/usr/bin/env python3
"""Package fixed path-cache results and retained earlier attempts on CPU 8."""
import datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'work/pr-evidence/path-cache'
BASELINE = '63495905e7b0b11ad99fa4c2c2674e43657b9902a2e3142ef735fd83efa44cf8'
CANDIDATE = 'c060facdbaae756453968d6eaef1c5ab71c127d15c329a8453e260ef3064c583'
TREE = 'b0dfb3fe2cfd8d310efa04a345f58886296f712a'
files, raw, source_map = {}, {}, {}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def add(source, destination, *, archive=False):
    path = ROOT / source
    assert path.is_file() and not path.is_symlink(), path
    data = path.read_bytes()
    if not archive:
        data.decode('utf-8')
    collection = raw if archive else files
    assert destination not in collection, destination
    collection[destination] = data
    source_map.setdefault(str(path), []).append(destination)
    return data


assert not set(os.sched_getaffinity(0)) & set(range(8)), 'Pin packaging outside benchmark CPUs 0-7'
OUT.mkdir(exist_ok=True)
for name in ['README.md', 'REPRODUCE.md', 'VALIDATION.md', 'HISTORY.md']:
    files[name] = (OUT / name).read_bytes()
for name in ['paired.py', 'paired_repeated.py']:
    add('work/benchmark/frozen/' + name, 'harness/' + name)
for name in ['test_paired.py', 'test_paired_repeated.py', 'strip_binaries.py']:
    add('work/benchmark/' + name, 'harness/' + name)
add('work/profiling-tools/ohm-valgrind-env.c', 'harness/ohm-valgrind-env.c')
add('work/benchmark/frozen/run_followon_ir-d78f4b06a398.py', 'historical/harness/run_followon_ir-d78f4b06a398.py')
for name in ['protocol.md', 'protocol-instruction-restored.md', 'protocol-upstream-175.md',
             'protocol-native-host8.md', 'protocol-followon-candidates.md']:
    add('work/benchmark/' + name, 'protocols/' + name)
add('work/remote-native-8/remote/benchmark/protocol-native-groups.md', 'protocols/protocol-native-groups.md')
for workflow in ['check', 'test']:
    add(f'work/benchmark/{workflow}-path-cache-pr175-production-ir.json', f'configs/{workflow}-ir-original.json')
    add(f'work/remote-native-8/remote/benchmark/{workflow}-path-cache-production.json', f'configs/{workflow}-native-original.json')
    add(f'work/benchmark/{workflow}-build-output-pr175-production-ir.json', f'historical/configs/{workflow}-ir-derivation-source.json')
for name in ['cargo-pr175.build.json', 'cargo-pr175.strip.json', 'cargo-pr175-path-cache.build.json',
             'cargo-pr175-path-cache.strip.json', 'provenance-pr175.json', 'provenance-pr175-path-cache.json',
             'pr175.source.patch', 'pr175-path-cache.source.patch']:
    add('work/production-build/results/' + name, 'build/' + name)
for name in ['build_driver_pr175.py', 'build_driver_pr175_path_cache.py', 'pr175.patch']:
    add('work/production-build/' + name, 'build/' + name)
add('work/patches/path-cache.patch', 'build/candidate.patch')
add('work/binaries/manifest.json', 'historical/normal-binary-manifest.json')
for name in ['cargo-baseline', 'cargo-path-cache', 'cargo-pr175-baseline-normal', 'cargo-pr175-path-cache-normal']:
    add(f'work/binaries/stripped/{name}.json', f'historical/normal-builds/{name}.strip.json')
    source = ROOT / f'work/binaries/{name}.build.json'
    if source.exists():
        add(str(source.relative_to(ROOT)), f'historical/normal-builds/{name}.build.json')
add('work/build-normal-pr175.py', 'historical/harness/build-normal-pr175.py')
for path in sorted((ROOT / 'work/benchmark').glob('*path-cache*.json')):
    if 'production' not in path.name:
        add(str(path.relative_to(ROOT)), 'historical/configs/' + path.name)
for name in ['check-path-cache-grouped.remote.json', 'test-path-cache-grouped.remote.json']:
    add('work/remote-confirmation/remote/benchmark/' + name, 'historical/configs/' + name)
for name in ['external-pr175-priority-change.json', 'config-equivalence.json']:
    add('work/remote-confirmation/' + name, 'historical/' + name)
for name in ['preflight.json', 'setup.json', 'warm-execve-evidence.json',
             'check-fetch.json', 'check-seed.json', 'test-fetch.json', 'test-seed.json']:
    add('work/remote-confirmation/remote/metadata/' + name, 'historical/native-preflight/' + name)
for path in sorted((ROOT / 'work/remote-confirmation/remote/logs').iterdir()):
    if path.is_file() and 'build-output' not in path.name and 'loader' not in path.name:
        add(str(path.relative_to(ROOT)), 'historical/native-logs/' + path.name, archive=True)
for name in ['path-cache-warm-execve-evidence.json', 'path-cache-staged.json', 'setup.json',
             'check-fetch.json', 'check-seed.json', 'test-fetch.json', 'test-seed.json']:
    add('work/remote-native-8/remote/metadata/' + name, 'validation/native/' + name)
for path in sorted((ROOT / 'work/remote-native-8/remote/logs').glob('path-cache-*')):
    if path.is_file():
        add(str(path.relative_to(ROOT)), 'validation/native-execve/' + path.name, archive=True)
for variant in ['pr175', 'pr175-path-cache']:
    for suffix in ['stdout', 'stderr', 'occupancy.json']:
        add(f'work/production-build/results/{variant}.{suffix}', f'build/logs/{variant}.{suffix}', archive=True)
for path in sorted((ROOT / 'work/logs').iterdir()):
    if path.is_file() and ('path-cache' in path.name or 'baseline-build-dir-failure-' in path.name):
        add(str(path.relative_to(ROOT)), 'historical/logs/' + path.name, archive=True)
add('work/logs/final-candidate-correctness.json', 'validation/historical-correctness.json')
for workflow in ['check', 'test']:
    folder = f'work/benchmark/results/{workflow}-path-cache-pr175-production-ir-preflight'
    add(folder + '/report.json', f'validation/{workflow}-ir-preflight.json')
    for path in sorted((ROOT / folder).iterdir()):
        if path.is_file():
            add(str(path.relative_to(ROOT)), f'validation/{workflow}-ir-preflight/{path.name}', archive=True)

# Additional exact-production correctness is collected separately when available.
# An explicit inventory keeps its provenance visible rather than sweeping targets.
extra_inventory = OUT.parent / 'path-cache-extra-validation.json'
if extra_inventory.exists():
    inventory = json.loads(extra_inventory.read_text())
    for entry in inventory['files']:
        add(entry['source'], entry['destination'], archive=entry.get('archive', False))
    add(str(extra_inventory.relative_to(ROOT)), 'validation/additional-inventory.json')
    report = json.loads(files['validation/production/report.json'])
    assert report['status'] == 'passed' and report['binary_sha256'] == CANDIDATE
    assert report['after_sha256']['binary'] == CANDIDATE
    assert report['harness_sha256'] == report['after_sha256']['harness'] == '6415ee68be80518f701a6e4d0b45c1ef76bab599af203625f06b7fa4ac696182'
    assert report['listed_test_count'] == 97 and report['summaries'][0][:3] == ['93', '0', '4']
    assert report['failed_tests'] == []
    assert report['test_log_sha256'] == sha(raw['validation/production/evidence/attempt-candidate/tests.log'])
    assert report['runner_sha256'] == sha(files['validation/production/run_remote.py'])

runs = {
    'check-ir-confirmation': 'work/benchmark/results/check-path-cache-pr175-production-ir-confirmation',
    'test-ir-confirmation': 'work/benchmark/results/test-path-cache-pr175-production-ir-confirmation',
    'check-native-confirmation': 'work/remote-native-8/remote/results/check-path-cache-pr175-native-confirmation',
    'test-native-confirmation': 'work/remote-native-8/remote/results/test-path-cache-pr175-native-confirmation',
    'historical-check-native-exploratory': 'work/benchmark/results/check-path-cache-exploratory',
    'historical-check-native-confirmation': 'work/remote-confirmation/remote/results/check-path-cache-native-confirmation',
    'historical-check-ir-failed-smoke': 'work/benchmark/results/check-path-cache-ir-smoke',
    'historical-check-ir-ssl-smoke': 'work/benchmark/results/check-path-cache-ir-ssl-smoke',
    'historical-check-ir-exploratory': 'work/benchmark/results/check-path-cache-ir-exploratory',
    'historical-check-pr175-ir-diagnostic': 'work/benchmark/results/check-path-cache-pr175-ir-diagnostic',
}
profile_extracts, run_inventory = [], {}
for label, folder in runs.items():
    directory = ROOT / folder
    manifest = json.loads((directory / 'manifest.json').read_text())
    samples = json.loads((directory / 'samples.json').read_text())
    historical = label.startswith('historical-')
    expected_state = 'failed' if label.endswith('failed-smoke') else 'complete'
    assert manifest['state'] == expected_state, label
    if not historical:
        assert manifest['variant_sha256'] == {'baseline': BASELINE, 'candidate': CANDIDATE}, label
    assert manifest['variant_sha256_after'] == manifest['variant_sha256'], label
    assert manifest['recorded_file_sha256_after'] == manifest['recorded_file_sha256'], label
    for name in ['analysis.json', 'manifest.json', 'samples.csv']:
        if (directory / name).is_file():
            add(folder + '/' + name, 'results/' + label + '/' + name)
    profiles = {Path(s['metric_files']['cargo_ir']['path']).name: s for s in samples if s.get('metric_files')}
    count = 0
    for path in sorted(directory.rglob('*')):
        if not path.is_file():
            continue
        assert not path.is_symlink(), path
        relative = str(path.relative_to(directory))
        count += 1
        if path.name.startswith('callgrind-') and path.suffix == '.out':
            data = path.read_bytes()
            sample = profiles[path.name]
            assert sha(data) == sample['metric_files']['cargo_ir']['sha256'], path
            lines = [line for line in data.decode().splitlines() if line.startswith(('events:', 'summary:', 'totals:'))]
            events = next(line.split(':', 1)[1].split() for line in lines if line.startswith('events:'))
            counts = next(line.split(':', 1)[1].split() for line in lines if line.startswith('summary:'))
            assert int(counts[events.index('Ir')]) == sample['metrics']['cargo_ir'], path
            profile_extracts.append({'run': label, 'file': relative, 'sha256': sha(data), 'bytes': len(data),
                'counter_lines': lines, 'sample': {key: sample[key] for key in ['stage', 'pair', 'order', 'position', 'variant']},
                'returncode': sample['returncode'], 'run_state': manifest['state'],
                'cargo_ir': sample['metrics']['cargo_ir'], 'completed_invocation': sample['returncode'] == 0})
        else:
            add(str(path.relative_to(ROOT)), 'results/' + label + '/' + relative, archive=True)
    run_inventory[label] = {'source_directory': str(directory), 'source_files': count,
        'profiles_extracted': len(profiles), 'raw_files': count - len(profiles),
        'state': manifest['state'], 'samples': len(samples), 'historical': historical, 'manifest': manifest}
assert len(profile_extracts) == 85
for variant in ['pr175', 'pr175-path-cache']:
    provenance = json.loads(files[f'build/provenance-{variant}.json'])
    driver = f'build/build_driver_{variant.replace("-", "_")}.py'
    assert sha(files[driver]) == provenance['driver_sha256'], driver
    build = json.loads(files[f'build/cargo-{variant}.build.json'])
    stripped = json.loads(files[f'build/cargo-{variant}.strip.json'])
    assert build['original_linker_output_sha256'] == stripped['source_sha256']
    expected = BASELINE if variant == 'pr175' else CANDIDATE
    assert stripped['stripped_sha256'] == expected
    assert sha(files[f'build/{variant}.source.patch']) == build['observed_diff_sha256']
    assert sha(raw[f'build/logs/{variant}.stderr']) == build['stderr_sha256']
    assert sha(raw[f'build/logs/{variant}.stdout']) == build['stdout_sha256']
assert json.loads(files['build/cargo-pr175-path-cache.build.json'])['observed_source_tree'] == TREE
assert sha(files['build/candidate.patch']) == '0ad07b5922f9fdd60f772368e8621c679f1fb0163c245fdd484aee58cd599bb0'

statistics = {}
for label in runs:
    if label.startswith('historical-'):
        continue
    analysis = json.loads(files[f'results/{label}/analysis.json'])
    if '-ir-' in label:
        value = analysis['metrics']['cargo_ir']['statistics']
        gate = json.loads(raw[f'results/{label}/instruction-gate.json'])
        integrity = json.loads(raw[f'results/{label}/integrity.json'])
        assert gate['passes_instruction_gate'] and all(gate['gate_checks'].values()), label
        assert integrity['state'] == 'passed' and integrity['invocations_verified'] == 28, label
        assert value['pairs'] == 12 and value['wins'] == 12 and value['confidence'] == 0.99
        reduction, interval = value['paired_geometric_mean_count_reduction'], value['bootstrap_count_reduction_interval']
        for name in ['integrity.json', 'instruction-gate.json']:
            files[f'results/{label}/{name}'] = raw[f'results/{label}/{name}']
    else:
        value = analysis
        assert value['pairs'] == 30 and not value['screen']['passes'], label
        assert value['grouping']['repetitions_per_variant'] == 8
        reduction, interval = value['paired_geometric_mean_time_reduction'], value['bootstrap_time_reduction_interval']
    statistics[label] = {'reduction_percent': 100 * reduction,
        'interval_99_percent': [100 * x for x in interval], 'pairs': value['pairs'],
        'wins': value['wins'], 'losses': value['losses'], 'sign_p': value['exact_two_sided_sign_p'],
        'passes_claimed_gate': '-ir-' in label}
files['results/summary.json'] = encoded(statistics)
files['callgrind-counter-extracts.jsonl'] = b''.join((json.dumps(value, sort_keys=True) + '\n').encode() for value in profile_extracts)
files['RAW-MANIFEST.json'] = encoded({name: {'sha256': sha(data), 'bytes': len(data)} for name, data in sorted(raw.items())})
add(str(Path(__file__).relative_to(ROOT)), 'historical/prepare_path_cache.py')
by_hash = {}
for name, data in (files | raw).items():
    by_hash.setdefault(sha(data), []).append(name)
inputs = {}
for label, inventory in run_inventory.items():
    manifest = inventory.pop('manifest')
    inputs[label] = {'source_directory': inventory['source_directory'],
        'variant_sha256': manifest['variant_sha256'],
        'recorded_file_sha256': {
            original: {'sha256': digest, 'package_locations': sorted(by_hash.get(digest, [])),
                'availability': 'packaged' if digest in by_hash else 'external or historical input; provision and hash for replication'}
            for original, digest in manifest['recorded_file_sha256'].items()}}
files['INPUTS.json'] = encoded({'scope': 'Historical recorded inputs mapped by hash; paths preserved. Some package locations are raw archive members. Runtime binaries are not packaged. The earliest native exploratory run did not record its runner hash.', 'runs': inputs})
files['CONTENTS.json'] = encoded({'runs': run_inventory, 'profile_extracts': len(profile_extracts),
    'raw_files': len(raw), 'raw_bytes': sum(map(len, raw.values())),
    'full_profiles': 'Retained in task workspace; exact counter lines and hashes packaged, including the failed invocation.',
    'correctness_exclusions': ['compiled fixtures and test drivers', 'Cargo cache databases']})
archive = OUT / 'raw-results.tar.gz'
with archive.open('wb') as stream:
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
manifest = {name: {'sha256': sha(data), 'bytes': len(data)} for name, data in sorted(files.items())}
manifest['raw-results.tar.gz'] = {'sha256': sha(archive.read_bytes()), 'bytes': archive.stat().st_size}
(OUT / 'SHA256SUMS').write_text(''.join(value['sha256'] + '  ' + name + '\n' for name, value in manifest.items()))
actual = {str(path.relative_to(OUT)) for path in OUT.rglob('*') if path.is_file()}
assert actual == set(manifest) | {'SHA256SUMS'}, actual - set(manifest) - {'SHA256SUMS'}
(OUT.parent / 'path-cache-manifest.json').write_bytes(encoded(manifest))
print(json.dumps({'text_files': len(files), 'raw_files': len(raw), 'profile_extracts': len(profile_extracts),
    'archive_bytes': archive.stat().st_size, 'archive_sha256': sha(archive.read_bytes()),
    'package_manifest_sha256': sha((OUT.parent / 'path-cache-manifest.json').read_bytes())}, indent=2))
