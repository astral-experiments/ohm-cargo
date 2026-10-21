#!/usr/bin/env python3
"""Package completed original-PR175 composition evidence on a non-benchmark CPU."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'work/pr-evidence/cumulative-177-178'
REMOTE = ROOT / 'work/remote-native-8/remote'
PRODUCTION = ROOT / 'work/production-build/results'
BASELINE = '63495905e7b0b11ad99fa4c2c2674e43657b9902a2e3142ef735fd83efa44cf8'
CANDIDATE = 'a60f7c6ccb37c582263a02b462673de9b7d5e7a68127258d150be49f1b1721be'
TREE = '4117e012ab1e082867dcb5a4b2a227e7f5200ff6'
VARIANT = 'pr175-build-output-remap-loader-v2'
files, raw = {}, {}
assert not (set(os.sched_getaffinity(0)) & set(range(8)))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def add(source, destination, archive=False):
    path = ROOT / source
    assert path.is_file() and not path.is_symlink(), path
    data = path.read_bytes()
    collection = raw if archive else files
    if not archive:
        data.decode('utf-8')
    if destination in collection:
        assert collection[destination] == data
    collection[destination] = data
    return data


OUT.mkdir(exist_ok=True)
for name in ['README.md', 'REPRODUCE.md', 'VALIDATION.md']:
    files[name] = (OUT / name).read_bytes()
for name in ['paired.py', 'paired_repeated.py']:
    add('work/benchmark/frozen/' + name, 'harness/' + name)
for name in ['test_paired.py', 'test_paired_repeated.py', 'strip_binaries.py', 'audit_cumulative_batches.py']:
    add('work/benchmark/' + name, 'harness/' + name)
add('work/profiling-tools/ohm-valgrind-env.c', 'harness/ohm-valgrind-env.c')
for name in ['run_cumulative_ir-122eff40292d.py', 'run_followon_ir-d78f4b06a398.py']:
    add('work/benchmark/frozen/' + name, 'historical/harness/' + name)
for name in ['protocol.md', 'protocol-instruction-restored.md', 'protocol-upstream-175.md',
             'protocol-native-host8.md', 'protocol-cumulative-177-178.md']:
    add('work/benchmark/' + name, 'protocols/' + name)
add('work/remote-native-8/remote/benchmark/protocol-native-groups.md', 'protocols/protocol-native-groups.md')
add('work/benchmark/cumulative-177-178-production-ir-seal.json', 'validation/static-ir-seal.json')
add('work/benchmark/results/cumulative-177-178-batch-audit.json', 'validation/batch-audit.json')
add('work/benchmark/results/cumulative-177-178-production-ir-summary.json', 'validation/ir-summary.json')
add('work/remote-native-8/remote/metadata/build-output-remap-loader-v2-warm-execve-evidence.json', 'validation/native-execve.json')
for workflow in ['check', 'test']:
    add(f'work/benchmark/{workflow}-build-output-remap-loader-v2-pr175-production-ir.json', f'configs/{workflow}-ir-original.json')
    add(f'work/remote-native-8/remote/benchmark/{workflow}-build-output-remap-loader-v2-production.json', f'configs/{workflow}-native-original.json')
    add(f'work/benchmark/{workflow}-build-output-pr175-production-ir.json', f'historical/configs/{workflow}-ir-derivation-source.json')
    preflight = ROOT / f'work/benchmark/results/{workflow}-build-output-remap-loader-v2-pr175-production-ir-preflight'
    add(str(preflight.relative_to(ROOT) / 'report.json'), f'validation/{workflow}-ir-preflight.json')
    for path in sorted(preflight.iterdir()):
        if path.is_file():
            add(str(path.relative_to(ROOT)), f'validation/{workflow}-ir-preflight/{path.name}', True)
for variant in ['pr175', VARIANT]:
    for suffix in ['build.json', 'strip.json']:
        add(f'work/production-build/results/cargo-{variant}.{suffix}', f'build/cargo-{variant}.{suffix}')
    add(f'work/production-build/results/{variant}.source.patch', f'build/{variant}.source.patch')
    for suffix in ['stdout', 'stderr', 'occupancy.json']:
        add(f'work/production-build/results/{variant}.{suffix}', f'build/logs/{variant}.{suffix}', True)
for name in ['provenance-pr175.json', f'provenance-{VARIANT}.json', f'audit-{VARIANT}.json']:
    add('work/production-build/results/' + name, 'build/' + name)
add('work/production-build/build_driver_pr175.py', 'build/build_driver_pr175.py')
for path in sorted((ROOT / 'work/production-build/frozen/accepted-sbom').iterdir()):
    if path.is_file() and not path.name.startswith('manifest-draft-'):
        add(str(path.relative_to(ROOT)), 'build/frozen/' + path.name)
for label, source in [('pr175', 'work/production-build/pr175.patch'),
                      ('build-output-remap', 'work/patches/build-output-remap.patch'),
                      ('loader-path-v2-final', 'work/patches/loader-path-v2-final.patch')]:
    add(source, 'build/patches/' + label + '.patch')

for name in ['combined-results-transfer-sha256.json', 'combined-metadata-transfer-sha256.json',
             'combined-preflight-transfer-sha256.json']:
    data = add('work/remote-native-8/' + name, 'native/' + name)
    for relative, digest in json.loads(data).items():
        value = add(str((REMOTE / relative).relative_to(ROOT)), 'native/' + relative, True)
        assert sha(value) == digest, relative

audit = json.loads(files['validation/batch-audit.json'])
assert audit['status'] == 'passed'
assert sha(files['harness/audit_cumulative_batches.py']) == audit['script_sha256']
for name, value in audit['transfers'].items():
    assert sha(files['native/' + name]) == value['sha256']
for variant, expected in [('pr175', BASELINE), (VARIANT, CANDIDATE)]:
    build = json.loads(files[f'build/cargo-{variant}.build.json'])
    stripped = json.loads(files[f'build/cargo-{variant}.strip.json'])
    assert stripped['stripped_sha256'] == sha((PRODUCTION / f'cargo-{variant}').read_bytes()) == expected
    assert build['original_linker_output_sha256'] == stripped['source_sha256']
    assert sha(files[f'build/{variant}.source.patch']) == build['observed_diff_sha256']
    for suffix in ['stdout', 'stderr']:
        assert sha(raw[f'build/logs/{variant}.{suffix}']) == build[suffix + '_sha256']
build = json.loads(files[f'build/cargo-{VARIANT}.build.json'])
assert build['observed_source_tree'] == build['expected_source_tree_from_patches'] == TREE
provenance = json.loads(files[f'build/provenance-{VARIANT}.json'])
assert sha(files['build/frozen/build_driver_accepted_sbom.py']) == provenance['driver_sha256']
assert sha(files['build/frozen/manifest.json']) == provenance['frozen_input_manifest_sha256']
assert sha(files[f'build/provenance-{VARIANT}.json']) == '635c0296edb306049a3040e3bd90d52553557a19f6c9bc6097c9a2c6350df3b2'

extracts, inventory, manifests = [], {}, {}
for batch in audit['batches']:
    directory = Path(batch['directory'])
    label = batch['workflow'] + '-' + batch['kind'] + '-confirmation'
    prefix = 'results/' + label if batch['kind'] == 'ir' else 'native/results/' + directory.name
    manifest = json.loads((directory / 'manifest.json').read_text())
    samples = json.loads((directory / 'samples.json').read_text())
    assert manifest['state'] == 'complete'
    assert manifest['variant_sha256'] == manifest['variant_sha256_after'] == {'baseline': BASELINE, 'candidate': CANDIDATE}
    assert manifest['recorded_file_sha256'] == manifest['recorded_file_sha256_after']
    for name in ['analysis.json', 'manifest.json', 'samples.csv']:
        add(str((directory / name).relative_to(ROOT)), f'results/{label}/{name}')
    profiles = {Path(row['metric_files']['cargo_ir']['path']).name: row for row in samples if row.get('metric_files')}
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
            data = add(str(path.relative_to(ROOT)), prefix + '/' + relative, True)
            if path.name in ['integrity.json', 'instruction-gate.json']:
                files[f'results/{label}/{path.name}'] = data
    inventory[label] = {'source_directory': str(directory), 'source_files': count,
                        'raw_archive_prefix': prefix, 'profiles_extracted': len(profiles), 'samples': len(samples)}
    manifests[label] = manifest
assert len(extracts) == 56
files['results/summary.json'] = encoded(audit['batches'])
files['callgrind-counter-extracts.jsonl'] = b''.join((json.dumps(row, sort_keys=True) + '\n').encode() for row in extracts)
files['RAW-MANIFEST.json'] = encoded({name: {'sha256': sha(data), 'bytes': len(data)} for name, data in sorted(raw.items())})
add(str(Path(__file__).relative_to(ROOT)), 'historical/prepare_cumulative_177_178.py')
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
    'scope': 'Original PR175 plus output remapping and loader handling only; independent current-stack validation is separate.'})
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
package = {name: {'sha256': sha(data), 'bytes': len(data)} for name, data in sorted(files.items())}
package['raw-results.tar.gz'] = {'sha256': sha(archive.read_bytes()), 'bytes': archive.stat().st_size}
(OUT / 'SHA256SUMS').write_text(''.join(value['sha256'] + '  ' + name + '\n' for name, value in sorted(package.items())))
manifest_path = OUT.parent / 'cumulative-177-178-manifest.json'
manifest_path.write_bytes(encoded(package))
print(json.dumps({'text_files': len(files), 'raw_files': len(raw), 'profile_extracts': len(extracts),
                  'archive': package['raw-results.tar.gz'], 'manifest_sha256': sha(manifest_path.read_bytes())}, indent=2))
