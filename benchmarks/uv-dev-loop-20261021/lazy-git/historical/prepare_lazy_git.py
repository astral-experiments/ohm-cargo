#!/usr/bin/env python3
"""Package completed lazy-Git evidence; run pinned outside benchmark CPUs."""
import datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'work/pr-evidence/lazy-git'
BASELINE = '63495905e7b0b11ad99fa4c2c2674e43657b9902a2e3142ef735fd83efa44cf8'
CANDIDATE = 'b54037b8f4041b7add52dcc9ad86357e7d8a86953a35c64e3d76718b0fed7cfd'
TREE = 'c692e3c07d295e596b9f10eb4b1c89bb498caf68'
files = {}
raw = {}
source_map = {}


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


assert not (set(os.sched_getaffinity(0)) & set(range(8))), 'Pin packaging outside benchmark CPUs 0-7'
OUT.mkdir(exist_ok=True)
for name in ['REPRODUCE.md', 'VALIDATION.md']:
    files[name] = (OUT / name).read_bytes()
for name in ['paired.py', 'paired_repeated.py']:
    add('work/benchmark/frozen/' + name, 'harness/' + name)
for name in ['test_paired.py', 'test_paired_repeated.py', 'strip_binaries.py', 'validate_ssl_environment.py']:
    add('work/benchmark/' + name, 'harness/' + name)
add('work/profiling-tools/ohm-valgrind-env.c', 'harness/ohm-valgrind-env.c')
add('work/benchmark/frozen/run_followon_ir-d78f4b06a398.py', 'historical/harness/run_followon_ir-d78f4b06a398.py')
for name in ['validate_lazy_git-d7e6dc04baa9.py', 'resume_lazy_git_validation-05fa679f62c4.py',
             'build_normal_followups-f66fb232d293.py', 'build_normal_followups-daf3b6fffef1.py']:
    add('work/benchmark/frozen/' + name, 'historical/harness/' + name)
add('work/benchmark/validate_lazy_git.py', 'historical/harness/validate_lazy_git-corrected-runner.py')
for name in ['protocol.md', 'protocol-instruction-restored.md', 'protocol-upstream-175.md',
             'protocol-native-host8.md', 'protocol-followon-candidates.md']:
    add('work/benchmark/' + name, 'protocols/' + name)
add('work/remote-native-8/remote/benchmark/protocol-native-groups.md', 'protocols/protocol-native-groups.md')
for workflow in ['check', 'test']:
    add(f'work/benchmark/{workflow}-lazy-git-pr175-production-ir.json', f'configs/{workflow}-ir-original.json')
    add(f'work/remote-native-8/remote/benchmark/{workflow}-lazy-git-production.json', f'configs/{workflow}-native-original.json')
    add(f'work/benchmark/{workflow}-build-output-pr175-production-ir.json', f'historical/configs/{workflow}-ir-derivation-source.json')
for name in ['cargo-pr175.build.json', 'cargo-pr175.strip.json', 'cargo-pr175-lazy-git.build.json',
             'cargo-pr175-lazy-git.strip.json', 'provenance-pr175.json', 'provenance-pr175-lazy-git.json',
             'pr175.source.patch', 'pr175-lazy-git.source.patch']:
    add('work/production-build/results/' + name, 'build/' + name)
for name in ['build_driver_pr175.py', 'build_driver_pr175_lazy_git.py', 'pr175.patch']:
    add('work/production-build/' + name, 'build/' + name)
add('work/benchmark/patches/lazy-git-final-3707975b6b13.patch', 'build/candidate.patch')
add('work/benchmark/patches/lazy-git-final-3707975b6b13.json', 'build/candidate-frozen-source.json')
for suffix in ['patch', 'json']:
    add(f'work/benchmark/patches/lazy-git-final-2e0a634725a7.{suffix}', f'historical/invalid-once-default.{suffix}')
for name in ['lazy-git-implementation.md', 'lazy-git-policy.md', 'lazy-git-independent-review.md', 'lazy-git-validation.md']:
    add('work/benchmark/profile-analysis/' + name, 'historical/source-review/' + name)
for name in ['cargo-pr175-baseline-normal', 'cargo-pr175-lazy-git-normal']:
    add(f'work/binaries/{name}.build.json', f'validation/normal-builds/{name}.build.json')
    add(f'work/binaries/stripped/{name}.json', f'validation/normal-builds/{name}.strip.json')
add('work/binaries/cargo-pr175-lazy-git-normal.source.patch',
    'validation/normal-builds/cargo-pr175-lazy-git-normal.source.patch')
add('work/binaries/failed-builds/lazy-git-derive-default/cargo-pr175-lazy-git-normal.build.json',
    'validation/failed-normal-build.json')
add('work/benchmark/results/lazy-git-validation-summary.json', 'validation/summary.json')
for name in ['lazy-git-warm-execve-evidence.json', 'lazy-git-staged.json', 'setup.json',
             'check-fetch.json', 'check-seed.json', 'test-fetch.json', 'test-seed.json']:
    add('work/remote-native-8/remote/metadata/' + name, 'validation/native/' + name)
for name in ['build-cargo-pr175-lazy-git-normal.log', 'build-cargo-pr175-lazy-git-normal-derive-default-failure.log']:
    add('work/logs/' + name, 'validation/normal-builds/' + name, archive=True)
for variant in ['pr175', 'pr175-lazy-git']:
    for suffix in ['stdout', 'stderr', 'occupancy.json']:
        add(f'work/production-build/results/{variant}.{suffix}', f'build/logs/{variant}.{suffix}', archive=True)
for workflow in ['check', 'test']:
    directory = ROOT / f'work/benchmark/results/{workflow}-lazy-git-pr175-production-ir-preflight'
    add(str(directory.relative_to(ROOT) / 'report.json'), f'validation/{workflow}-ir-preflight.json')
    for path in sorted(directory.iterdir()):
        if path.is_file():
            add(str(path.relative_to(ROOT)), f'validation/{workflow}-ir-preflight/{path.name}', archive=True)
for path in sorted((ROOT / 'work/remote-native-8/remote/logs').glob('lazy-git-*')):
    if path.is_file():
        add(str(path.relative_to(ROOT)), 'validation/native-execve/' + path.name, archive=True)
for name in ['lazy-git-validation', 'lazy-git-validation-resumed']:
    directory = ROOT / 'work/benchmark/results' / name
    add(str(directory.relative_to(ROOT) / 'report.json'), f'validation/{name}.json')
    for path in sorted(directory.iterdir()):
        if path.is_file():
            add(str(path.relative_to(ROOT)), f'validation/{name}/{path.name}', archive=True)
ssl = ROOT / 'work/benchmark/results/lazy-git-validation/ssl-environments'
add(str(ssl.relative_to(ROOT) / 'report.json'), 'validation/ssl-environments.json')
for name in ['logs', 'captures', 'fixture', 'bin', 'certificates']:
    for path in sorted((ssl / name).rglob('*')):
        if path.is_file():
            add(str(path.relative_to(ROOT)), 'validation/ssl-environments/' + str(path.relative_to(ssl)), archive=True)
for name in ['report.json', 'git-config', 'cargo-home/config.toml']:
    add(str(ssl.relative_to(ROOT) / name), 'validation/ssl-environments/' + name, archive=True)

runs = {
    'check-ir-confirmation': 'work/benchmark/results/check-lazy-git-pr175-production-ir-confirmation',
    'test-ir-confirmation': 'work/benchmark/results/test-lazy-git-pr175-production-ir-confirmation',
    'check-native-confirmation': 'work/remote-native-8/remote/results/check-lazy-git-pr175-native-confirmation',
    'test-native-confirmation': 'work/remote-native-8/remote/results/test-lazy-git-pr175-native-confirmation',
}
profile_extracts = []
run_inventory = {}
for label, folder in runs.items():
    directory = ROOT / folder
    manifest = json.loads((directory / 'manifest.json').read_text())
    samples = json.loads((directory / 'samples.json').read_text())
    assert manifest['state'] == 'complete', label
    assert manifest['variant_sha256'] == {'baseline': BASELINE, 'candidate': CANDIDATE}, label
    assert manifest['variant_sha256_after'] == manifest['variant_sha256'], label
    assert manifest['recorded_file_sha256_after'] == manifest['recorded_file_sha256'], label
    for name in ['analysis.json', 'manifest.json', 'samples.csv']:
        add(folder + '/' + name, 'results/' + label + '/' + name)
    profiles = {Path(s['metric_files']['cargo_ir']['path']).name: s for s in samples if s.get('metric_files')}
    count = 0
    for path in sorted(directory.rglob('*')):
        if not path.is_file():
            continue
        assert not path.is_symlink(), path
        data = path.read_bytes()
        relative = str(path.relative_to(directory))
        count += 1
        if path.name.startswith('callgrind-') and path.suffix == '.out':
            sample = profiles[path.name]
            assert sha(data) == sample['metric_files']['cargo_ir']['sha256'], path
            lines = [line for line in data.decode().splitlines() if line.startswith(('events:', 'summary:', 'totals:'))]
            events = next(line.split(':', 1)[1].split() for line in lines if line.startswith('events:'))
            counts = next(line.split(':', 1)[1].split() for line in lines if line.startswith('summary:'))
            assert int(counts[events.index('Ir')]) == sample['metrics']['cargo_ir'], path
            profile_extracts.append({'run': label, 'file': relative, 'sha256': sha(data), 'bytes': len(data),
                                     'counter_lines': lines, 'sample': {key: sample[key] for key in ['stage', 'pair', 'order', 'position', 'variant']},
                                     'cargo_ir': sample['metrics']['cargo_ir']})
        else:
            add(str(path.relative_to(ROOT)), 'results/' + label + '/' + relative, archive=True)
    run_inventory[label] = {'source_directory': str(directory), 'source_files': count,
                            'profiles_extracted': len(profiles), 'raw_files': count - len(profiles),
                            'manifest': manifest}

assert len(profile_extracts) == 56
for variant in ['pr175', 'pr175-lazy-git']:
    provenance = json.loads(files[f'build/provenance-{variant}.json'])
    driver = f'build/build_driver_{variant.replace("-", "_")}.py'
    assert sha(files[driver]) == provenance['driver_sha256'], driver
assert json.loads(files['build/cargo-pr175-lazy-git.build.json'])['observed_source_tree'] == TREE
assert json.loads(files['validation/summary.json'])['source_tree'] == TREE
assert sha(files['harness/validate_ssl_environment.py']) == json.loads(files['validation/ssl-environments.json'])['script_sha256']

statistics = {}
for label in runs:
    analysis = json.loads(files[f'results/{label}/analysis.json'])
    if '-ir-' in label:
        value = analysis['metrics']['cargo_ir']['statistics']
        gate = json.loads(raw[f'results/{label}/instruction-gate.json'])
        integrity = json.loads(raw[f'results/{label}/integrity.json'])
        assert gate['passes_instruction_gate'] and all(gate['gate_checks'].values()), label
        assert integrity['state'] == 'passed' and integrity['invocations_verified'] == 28, label
        assert value['pairs'] == 12 and value['wins'] == 12 and value['confidence'] == 0.99
        reduction = value['paired_geometric_mean_count_reduction']
        interval = value['bootstrap_count_reduction_interval']
        for name in ['integrity.json', 'instruction-gate.json']:
            files[f'results/{label}/{name}'] = raw[f'results/{label}/{name}']
    else:
        value = analysis
        assert value['pairs'] == 30 and not value['screen']['passes'], label
        assert value['grouping']['repetitions_per_variant'] == 8
        reduction = value['paired_geometric_mean_time_reduction']
        interval = value['bootstrap_time_reduction_interval']
    statistics[label] = {'reduction_percent': 100 * reduction,
                         'interval_99_percent': [100 * x for x in interval],
                         'pairs': value['pairs'], 'wins': value['wins'], 'losses': value['losses'],
                         'sign_p': value['exact_two_sided_sign_p'],
                         'passes_claimed_gate': '-ir-' in label}

tool_paths = [Path(sys.executable).resolve()]
tool_paths += [Path(shutil.which(name)).resolve() for name in ['taskset', 'env', 'strace', 'cc']]
tool_paths += [ROOT / 'work/profiling-tools' / name for name in [
    'ohm-valgrind-env.so', 'valgrind_1%3a3.22.0-0ubuntu3_amd64.deb',
    'libc6-dbg_2.39-0ubuntu8.9_amd64.deb', 'valgrind/usr/bin/valgrind',
    'valgrind/usr/libexec/valgrind/callgrind-amd64-linux',
    'valgrind/usr/libexec/valgrind/vgpreload_core-amd64-linux.so']]
files['validation/tool-identities-at-packaging.json'] = encoded({
    'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'scope': 'Post-run packaging inventory. These additional tool hashes were not all bound in the original pre-run record_files; do not describe them as pre/post immutable-input checks.',
    'files': {str(path): {'sha256': sha(path.read_bytes()), 'bytes': path.stat().st_size} for path in tool_paths},
})
files['callgrind-counter-extracts.jsonl'] = b''.join((json.dumps(value, sort_keys=True) + '\n').encode() for value in profile_extracts)
files['RAW-MANIFEST.json'] = encoded({name: {'sha256': sha(data), 'bytes': len(data)} for name, data in sorted(raw.items())})
files['results/summary.json'] = encoded(statistics)

rows = []
labels = {
    'check-ir-confirmation': 'Warm check, Cargo instructions, 12 pairs',
    'test-ir-confirmation': 'Warm test --no-run, Cargo instructions, 12 pairs',
    'check-native-confirmation': 'Warm check, native wall time, 30 groups',
    'test-native-confirmation': 'Warm test --no-run, native wall time, 30 groups',
}
for label, result in statistics.items():
    low, high = result['interval_99_percent']
    outcome = 'Pass; both orders positive' if result['passes_claimed_gate'] else 'Inconclusive; gate fails'
    rows.append(f"| {labels[label]} | {result['reduction_percent']:.4f}% | {low:.4f}% to {high:.4f}% | {result['sign_p']:.9f} | {result['wins']}/{result['pairs']} | {outcome} |")
files['README.md'] = ('''# uv warm dev-loop: defer Git initialization

Cargo registers its existing executable-only Git policy at startup and applies
it once before repository access. Certificate environment probing remains at
startup, and initialization is forced before HTTP/fix workers. Library owner
validation, HTTPS support, conditional git2-curl transport, and security policy
remain intact. The curl workaround checks its cheap conditions before looking
up a Git proxy. This removes unnecessary libgit2/TLS setup on fresh offline
commands that do not need Git.

The measured candidate source tree is `c692e3c07d295e596b9f10eb4b1c89bb498caf68`.
Baseline is PR175 (`efc8b51502f8a8d1fe76997dc984481edde2740e`) on pinned Cargo
`5e5d271d763d7beb38b48755e22bd59e93f02b97`. uv is unchanged at
`3d82a6ad5a7eab8c68236553b7846517767c4b61`.

| Fixed validation | Reduction | 99% paired interval | Sign p | Wins | Result |
| --- | ---: | ---: | ---: | ---: | --- |
''' + '\n'.join(rows) + '''

Only the instruction reductions are claimed. Each instruction workflow passes
its own predeclared gate; neither was pooled with the other or with a screen.
Native groups contain eight calls and remain the statistical units. Native
test-build's small sign p does not override its below-threshold point estimate
and interval crossing zero. No native wall-time improvement or absence of
regression is established. No uv tests execute, and dirty rebuilds are outside
this workload.

The measured binaries use all-static/ohm-defaults, opt-level 3, ThinLTO, one
codegen unit and stock Rust 1.99.0. They have no PGO and are not the published
PGO toolchain. The workload compiler is pinned Ohm 1.99.0-6. Debug-only stripping
preserved allocated ELF sections. Callgrind 3.22 counts Cargo userspace
instructions only, excluding compiler, linker, build-script, test and kernel
work. Both variants encounter its brk/allocator fallback. Instrumented elapsed
time is not native time.

The final source passed 33 focused Rust tests and 12 SSL child-environment
cases, including library/CLI owner policy and existing HTTPS rejection/custom-CA
coverage. These correctness runs used normal/test-build binaries from the same
source, not the exact measured production CLI. The latter passed source,
build/strip, and fresh Ohm-enabled uv preflights. The initial invalid Once
Default derive and color-environment snapshot failure, their fixes and all
raw attempts remain visible. Cross-platform CI and a successful explicit proxy
CONNECT case are not covered. See [VALIDATION.md](VALIDATION.md).

Use [REPRODUCE.md](REPRODUCE.md), the frozen [protocols](protocols),
[runners](harness), [original configurations](configs), and
[build/source/strip provenance](build). Historical absolute paths are preserved;
seed new artifacts when reproducing at another prefix. [INPUTS.json](INPUTS.json)
maps recorded hashes to packaged metadata/source files and identifies external
runtime inputs. Executables are not included or made downloadable by their
historical local paths. Additional tool hashes collected while packaging are
explicitly labeled post-run.

[raw-results.tar.gz](raw-results.tar.gz) preserves every file from the four
completed result directories except the disclosed large Callgrind attribution
profiles, plus correctness logs/reports/captures, build logs and execve traces.
All raw samples, native subruns, warmups and preparations are included, including
both inconclusive native results. The profiles remain retained in the task
workspace; [counter extracts](callgrind-counter-extracts.jsonl) include every
profile's original hash, size and count, checked against the sample table.
[RAW-MANIFEST.json](RAW-MANIFEST.json) lists the archive contents exactly, and
[SHA256SUMS](SHA256SUMS) seals the package. Generated correctness-fixture targets
and cache databases are excluded. Historical review and freeze notes retain
their original pre-execution wording; completed validation reports supersede
their pending status.
''').encode()

add(str(Path(__file__).relative_to(ROOT)), 'historical/prepare_lazy_git.py')
by_hash = {}
for name, data in (files | raw).items():
    by_hash.setdefault(sha(data), []).append(name)
inputs = {}
for label, inventory in run_inventory.items():
    manifest = inventory.pop('manifest')
    inputs[label] = {
        'source_directory': inventory['source_directory'],
        'variant_sha256': manifest['variant_sha256'],
        'recorded_file_sha256': {
            original: {'sha256': digest, 'package_locations': sorted(by_hash.get(digest, [])),
                       'availability': 'packaged' if digest in by_hash else 'external runtime/input; provision and hash for replication'}
            for original, digest in manifest['recorded_file_sha256'].items()
        },
    }
files['INPUTS.json'] = encoded({'scope': 'Original recorded inputs mapped by hash. Historical paths are preserved; package_locations may refer to raw archive members. Runtime binaries are not packaged.', 'runs': inputs})
files['CONTENTS.json'] = encoded({'runs': run_inventory, 'profile_extracts': len(profile_extracts),
    'raw_files': len(raw), 'raw_bytes': sum(map(len, raw.values())),
    'correctness_exclusions': ['compiled SSL fixture targets', 'Cargo cache databases'],
    'full_profiles': 'Retained in task workspace; counter extracts and hashes packaged.'})

archive = OUT / 'raw-results.tar.gz'
with archive.open('wb') as stream:
    with gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|') as tar:
            for name, data in sorted(raw.items()):
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                entry.mode = 0o644
                entry.mtime = 0
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
(ROOT / 'work/pr-evidence/lazy-git-manifest.json').write_bytes(encoded(manifest))
print(json.dumps({'text_files': len(files), 'raw_files': len(raw), 'profile_extracts': len(profile_extracts),
                  'archive_bytes': archive.stat().st_size, 'archive_sha256': sha(archive.read_bytes()),
                  'package_manifest_sha256': sha((ROOT / 'work/pr-evidence/lazy-git-manifest.json').read_bytes())}, indent=2))
