#!/usr/bin/env python3
"""Assemble already reviewed evidence; never run tools, workloads or statistics.

--inputs points to a final locally reviewed JSON manifest, with keys:
  source_sha256: this script's hash;
  captures: {ir-failed, ir-closed, native}: {directory, manifest_sha256};
  reviews: {ir, native}: {path, sha256};
  lineage: [{source, destination, sha256, bytes}, ...].
All source paths are workspace-relative. Lineage must include the final native
admission/recovery review and complete local failed-launch/source-review history.
The fixed archived captures also retain their complete local transport envelopes.
The input manifest itself is copied and bound in the final output.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

WORKSPACE = Path(__file__).resolve().parents[2]
OUT = WORKSPACE / 'work/pr-evidence/workspace-inheritance-stack180'
OUT_MANIFEST = OUT.with_name(OUT.name + '-manifest.json')
REMOTE = '/tmp/ohm-hillclimb-20261021-inheritance-measurement'
SEAL = 'b6e765057417644e62cf7cadc4994a05172077f8c9a26bfe6343e6ad377e48ff'
SOURCE = 'f52a57b667b0708413cb353b2af4164f11fec6a9b8e0025bab4ab8330135ff98'
DRIVER = '1585116beaab26655de1e86459feb030ebdd31e636a613991241018ace5f3ef3'
EXPECTED = {'baseline': '3164f9287711f122fa9636a7816ed8749598706ac5076d66051a036dcef51037',
            'candidate': '3b1a2e4e3654b7b23816fbb54c51072cb356486c36052a5bcd6c4d3d2e6a07e9'}
IR_MANIFEST = '1eb96065ef89ab579f0aef22930bc945adcae762f28b39470c5c4b8ca9bea0dc'
FAILED_IR = 'b5a0b1edb496ffa0749ba6e2198606c32d83c22a8d79340ca9dc3d4b0ce95ba8'
IR_REVIEW = '0ea0f500d28c30d69fc679be7b191f108964b3464fd6dc2f20a486c8661a1834'
NATIVE_REVIEW_SOURCE = 'c47f8a475c9442ddafec725bb9a6db4b0e9b1eab7ea8d0e6227512ffb0152133'
TRANSPORT_REVIEW_SOURCE = '92db62095f5b381fff4062f9fb7a48d12039085d58e74f401417fc8770f037f6'


def need(value, reason):
    if not value:
        raise ValueError(reason)


def relative(value):
    path = PurePosixPath(value)
    need(value and value != '.' and not path.is_absolute() and '..' not in path.parts
         and '\\' not in value and str(path) == value, 'noncanonical relative path')
    return path


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def item(path):
    path = Path(path)
    need(path.is_file() and not path.is_symlink() and path.resolve() == path, 'noncanonical file: ' + str(path))
    return {'sha256': sha(path), 'bytes': path.stat().st_size}


def read(path):
    return json.loads(Path(path).read_text())


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def inventory_capture(directory, expected):
    need(sha(directory / 'transfer-manifest.json') == expected, 'collection manifest differs')
    manifest = read(directory / 'transfer-manifest.json')
    need(manifest['seal_sha256'] == SEAL and manifest['driver_sha256'] == DRIVER
         and manifest['root'] == REMOTE, 'collection identity differs')
    observed_remote = set()
    for path in (directory / 'remote').rglob('*'):
        need(not path.is_symlink(), 'symlink in extracted remote capture')
        if path.is_file():
            observed_remote.add(str(path.relative_to(directory / 'remote')))
        else:
            need(path.is_dir(), 'special file in extracted remote capture')
    need(observed_remote == set(manifest['files']), 'extra or missing extracted remote file')
    remote = {name: item(directory / 'remote' / relative(name)) for name in manifest['files']}
    need({name: row['sha256'] for name, row in remote.items()} == manifest['files'], 'remote captured bytes differ')
    expected_archive = {'remote/' + name: row for name, row in remote.items()}
    expected_archive['transfer-manifest.json'] = item(directory / 'transfer-manifest.json')
    actual = {}
    with tarfile.open(directory / 'payload.tar', 'r:') as archive:
        for member in archive:
            relative(member.name)
            need(member.isfile() and not member.issym() and not member.islnk() and member.name not in actual,
                 'unsafe/duplicate original archive member')
            with archive.extractfile(member) as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            actual[member.name] = {'sha256': digest, 'bytes': member.size}
    need(actual == expected_archive, 'original archive is not the exact captured file set')
    envelope = {}
    for path in sorted(directory.rglob('*')):
        need(not path.is_symlink(), 'symlink in capture envelope')
        if path.is_file() and not path.is_relative_to(directory / 'remote'):
            envelope[str(path.relative_to(directory))] = item(path)
        else:
            need(path.is_file() or path.is_dir(), 'special file in capture envelope')
    return manifest, {'original_payload': item(directory / 'payload.tar'), 'remote_members': remote, 'envelope_files': envelope}


def review_phase(phase, source, manifest, directory):
    review = read(source)
    need(review['phase'] == phase and review['status'] in ('passed', 'valid-negative')
         and review['integrity_status'] == review['final_evidence_and_review_source_rehash'] == 'passed'
         and review['statistics_computed'] is True and review['variants'] == EXPECTED
         and review['measurement_seal_sha256'] == SEAL and review['source_freeze_sha256'] == SOURCE
         and review['bootstrap'] == {'confidence': 0.99, 'resamples': 20000, 'seed': 1701}, 'final independent review incomplete')
    need(review['raw_file_sha256'] == manifest['files']
         and review['transfer_manifest_sha256'] == sha(directory / 'transfer-manifest.json'), 'review/raw collection join differs')
    status = read(directory / 'remote/results' / (phase + '-status.json'))
    need(status['state'] == 'complete' and status['phase'] == phase and status['seal_sha256'] == SEAL
         and status['variants'] == EXPECTED and status['integrity_complete'] == ['check', 'test']
         and status['completed'] == review['completed']
         and sha(directory / 'remote/results' / (phase + '-status.json')) == review['terminal_status_sha256'], 'terminal receipt differs')
    pairs, subruns, samples = (12, 0, 28) if phase == 'ir' else (30, 512, 64)
    seeds = (20261021111, 20261021112) if phase == 'ir' else (20261021113, 20261021114)
    need([row['workflow'] for row in review['workflows']] == ['check', 'test']
         and [row['workflow'] for row in review['completed']] == ['check', 'test'], 'workflow order differs')
    for row, seed in zip(review['workflows'], seeds):
        need(row['status'] == 'passed' and row['all_tables_logs_plans_sums_and_identities_match']
             and (row['pairs'], row['warmup_pairs'], row['seed'], row['subruns'], row['samples'])
                 == (pairs, 2, seed, subruns, samples) and row['unwanted_compilation_signatures'] == 0,
             'fixed independent workflow proof differs')
    if phase == 'ir':
        need(review['qualifies'] and all(row['passes_gate'] for row in review['completed']), 'IR gates did not qualify')
    else:
        need(not review['significant_native_regression']
             and not any(row['significant_native_regression'] for row in review['completed']), 'native regression blocks assembly')
        need(review['ir_review_sha256'] == IR_REVIEW, 'native did not bind the accepted fresh-pair IR review')
    return review


def summarize(review):
    return [{key: row[key] for key in ('workflow', 'reduction', 'interval_99', 'sign_p', 'passes_gate',
                                       'checks', 'significant_native_regression')} for row in review['completed']]


def verify_native_lineage(admission_bytes, binding, transport, native_review, native_review_sha, capture_sha):
    admission = json.loads(admission_bytes)
    need(admission['status'] == 'passed' and admission['zero_native_observations_replaced'] is True
         and admission['original_phase_controls_unchanged'] is True
         and admission['native_transfer_manifest_sha256'] == capture_sha
         and admission['source_freeze_sha256'] == NATIVE_REVIEW_SOURCE,
         'native admission/replay lineage not independently accepted')
    need(binding['status'] == 'passed' and binding['original_returncode'] == 0
         and binding['source_freeze_sha256'] == NATIVE_REVIEW_SOURCE
         and binding['lineage_before_effects_sha256'] == hashlib.sha256(admission_bytes).hexdigest()
         and binding['original_review_sha256'] == native_review_sha
         and binding['original_review_status'] == native_review['status']
         and binding['qualifies'] is native_review['qualifies']
         and binding['lineage_unchanged_after_review'] is True
         and binding['sampling_or_analysis_driver_changed'] is False,
         'native admission was not checked before and after this exact phase review')
    need(transport['state'] == 'passed' and transport['phase'] == 'native'
         and transport['original_review_sha256'] == native_review_sha
         and transport['original_review_status'] == native_review['status']
         and transport['qualifies'] is native_review['qualifies']
         and transport['transport_source_freeze_sha256'] == TRANSPORT_REVIEW_SOURCE,
         'native review does not retain the accepted IR transport closure')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--inputs-sha256', required=True)
    args = parser.parse_args()
    inputs_path = args.inputs.absolute()
    need(inputs_path.resolve() == inputs_path and inputs_path.is_relative_to(WORKSPACE), 'canonical workspace inputs required')
    need(sha(inputs_path) == args.inputs_sha256, 'assembly input manifest differs')
    inputs = read(inputs_path)
    need(inputs['source_sha256'] == sha(Path(__file__)) and inputs['status'] == 'reviewed-ready'
         and set(inputs['captures']) == {'ir-failed', 'ir-closed', 'native'}
         and set(inputs['reviews']) == {'ir', 'native'}, 'unreviewed/incomplete assembly inputs')
    need(not OUT.exists() and not OUT_MANIFEST.exists(), 'final evidence output must be new')
    protected, captures, inventories = {}, {}, {}
    for label, row in inputs['captures'].items():
        directory = WORKSPACE / relative(row['directory'])
        manifest, inventory = inventory_capture(directory, row['manifest_sha256'])
        captures[label] = (directory, manifest)
        inventories[label] = inventory
        for name, value in inventory['envelope_files'].items():
            protected[directory / name] = value
        for name, value in inventory['remote_members'].items():
            protected[directory / 'remote' / name] = value
    need(inputs['captures']['ir-failed']['manifest_sha256'] == FAILED_IR
         and inputs['captures']['ir-closed']['manifest_sha256'] == IR_MANIFEST, 'historical IR identity differs')
    need(captures['ir-failed'][1]['terminal_state'] == 'failed' and captures['ir-failed'][1]['qualifies'] is False,
         'historical failed phase is not retained honestly')
    reviews = {}
    for phase, row in inputs['reviews'].items():
        source = WORKSPACE / relative(row['path'])
        need(sha(source) == row['sha256'], 'review source differs')
        protected[source] = item(source)
        directory, manifest = captures['ir-closed' if phase == 'ir' else 'native']
        reviews[phase] = review_phase(phase, source, manifest, directory)
    need(inputs['reviews']['ir']['sha256'] == IR_REVIEW, 'accepted IR review differs')
    # Every accepted IR raw file must remain byte-identical in the final native capture.
    need(all(captures['native'][1]['files'].get(name) == digest
             for name, digest in captures['ir-closed'][1]['files'].items()), 'IR bytes changed before native collection')
    readable = {'assembly-inputs.json': inputs_path.read_bytes(), 'assembly-source.py': Path(__file__).read_bytes(),
                'summary.json': encoded({'scope': 'Fresh stack180 baseline versus shared inherited dependency map only',
                     'variants': EXPECTED, 'seal_sha256': SEAL, 'ir': summarize(reviews['ir']), 'native': summarize(reviews['native']),
                     'assembly_runs_statistics': False, 'full_original_profiles_retained': True})}
    raw = {}
    for label, (directory, manifest) in captures.items():
        for name in inventories[label]['envelope_files']:
            raw['captures/' + label + '/' + name] = directory / name
        readable['captures/' + label + '/transfer-manifest.json'] = (directory / 'transfer-manifest.json').read_bytes()
    for phase, row in inputs['reviews'].items():
        readable['reviews/' + phase + '.json'] = (WORKSPACE / row['path']).read_bytes()
    publication_path = WORKSPACE / 'work/workspace-inheritance-publication/code-publication.json'
    ci_path = WORKSPACE / 'work/workspace-inheritance-publication/ci-validation.json'
    publication, ci = read(publication_path), read(ci_path)
    need(publication['commit'] == ci['head_sha'] == 'd81a093becb4321a975522624c2a383970f0d164'
         and publication['base_commit'] == 'c40676e264501bc8a93095d3a273a1c300b80875'
         and publication['tree'] == 'c4178b67e0b3a64a12b9b58f84b97323b99d734e'
         and ci['status'] == 'completed' and ci['conclusion'] == 'success' and ci['required_jobs_succeeded'],
         'exact source publication/CI binding differs')
    for source, destination in ((publication_path, 'validation/code-publication.json'), (ci_path, 'validation/ci.json')):
        protected[source] = item(source)
        readable[destination] = source.read_bytes()
    for row in inputs['lineage']:
        source, destination = WORKSPACE / relative(row['source']), str(relative(row['destination']))
        need(item(source) == {key: row[key] for key in ('sha256', 'bytes')}, 'lineage input differs')
        need(destination not in readable and destination not in raw, 'duplicate lineage destination')
        protected[source] = item(source)
        need(row.get('storage', 'readable') in {'readable', 'raw'}, 'unknown lineage storage')
        if row.get('storage') == 'raw':
            raw[destination] = source
        else:
            readable[destination] = source.read_bytes()
    readable['RAW-MANIFEST.json'] = encoded({'captures': inventories,
        'outer_archive_members': {name: protected[source] for name, source in sorted(raw.items())},
        'local_lineage': inputs['lineage']})
    need({'README.md', 'REPRODUCE.md', 'VALIDATION.md', 'lineage/native-admission-final-review.json',
          'lineage/native-admission-review-binding.json', 'lineage/native-transport-resolution-review.json'} <= set(readable),
         'final documentation/admission lineage missing')
    binding = json.loads(readable['lineage/native-admission-review-binding.json'])
    transport = json.loads(readable['lineage/native-transport-resolution-review.json'])
    verify_native_lineage(readable['lineage/native-admission-final-review.json'], binding, transport,
        reviews['native'], inputs['reviews']['native']['sha256'], inputs['captures']['native']['manifest_sha256'])
    for filename in ('README.md', 'REPRODUCE.md', 'VALIDATION.md'):
        need('pending' not in readable[filename].decode().lower(), 'final documentation still pending')
    # Provide convenient readable views, while the original archives remain authoritative.
    native_directory = captures['native'][0]
    for name in captures['native'][1]['files']:
        if name.startswith(('controller/', 'benchmark/')) or (name.startswith('results/') and
            Path(name).name in {'analysis.json', 'gate.json', 'integrity.json', 'manifest.json', 'samples.json', 'samples.csv',
                                'subruns.json', 'subruns.csv', 'ir-status.json', 'native-status.json'}) or name.endswith('/report.json'):
            data = (native_directory / 'remote' / name).read_bytes()
            if len(data) < 10_000_000 and b'\0' not in data:
                need('evidence/' + name not in readable, 'duplicate readable evidence destination')
                readable['evidence/' + name] = data
    OUT.mkdir()
    with (OUT / 'raw-results.tar.gz').open('xb') as sink:
        with gzip.GzipFile(filename='', mode='wb', fileobj=sink, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w|') as archive:
                for name, source in sorted(raw.items()):
                    info = tarfile.TarInfo(name);info.size = source.stat().st_size;info.mode = 0o644;info.mtime = 0
                    with source.open('rb') as stream:
                        archive.addfile(info, stream)
    need((OUT / 'raw-results.tar.gz').stat().st_size < 100_000_000, 'lossless raw archive needs explicit splitting before publication')
    archived = {}
    with tarfile.open(OUT / 'raw-results.tar.gz', 'r|gz') as archive:
        for member in archive:
            relative(member.name)
            need(member.isfile() and member.name in raw and member.name not in archived, 'unexpected outer archive member')
            with archive.extractfile(member) as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            archived[member.name] = {'sha256': digest, 'bytes': member.size}
    need(archived == {name: protected[source] for name, source in raw.items()}, 'lossless outer archive bytes differ')
    for name, data in sorted(readable.items()):
        destination = OUT / relative(name);destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(data)
    for path, expected in protected.items():
        need(item(path) == expected, 'source evidence changed during assembly')
    need(sha(inputs_path) == args.inputs_sha256 and sha(Path(__file__)) == inputs['source_sha256'], 'assembler controls changed')
    inventory = {str(path.relative_to(OUT)): item(path) for path in sorted(OUT.rglob('*')) if path.is_file()}
    need(all(row['bytes'] < 100_000_000 for row in inventory.values()), 'oversized artifact needs lossless splitting')
    with (OUT / 'SHA256SUMS').open('x') as stream:
        stream.writelines(row['sha256'] + '  ' + name + '\n' for name, row in sorted(inventory.items()))
    with OUT_MANIFEST.open('xb') as stream:
        stream.write(encoded(inventory))
    print(json.dumps({'files': len(inventory) + 1, 'manifest_sha256': sha(OUT_MANIFEST),
                      'raw_archive': item(OUT / 'raw-results.tar.gz'), 'no_statistics_or_host_execution': True}, indent=2))


if __name__ == '__main__':
    main()
