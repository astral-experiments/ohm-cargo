#!/usr/bin/env python3
"""Package already accepted local evidence. No subprocesses, hosts or statistics."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import tarfile

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PUBLICATION_SOURCE = WORKSPACE / 'work/sbom-current179-publication'
OUTPUT = WORKSPACE / 'work/pr-evidence/lazy-sbom-stack179'
COMMIT = '4e5d21f61600cf333adbe5a96f51d74ea14b3060'
PARENT = '19718e6d1637244ffbb193334f50bae3ffca1be5'
TREES = {'baseline': 'f4ce59f92aa17461fe3c8b68923c88539136045a',
         'candidate': 'c377ade816d378aa75f629313ac7b116da10c6da'}
BINARIES = {'baseline': 'a25d7c3e1678a4076b7006b1ca3880da116de8ba43b93f5b1c45c8fc260c8e47',
            'candidate': '060043e733873dfd9a27e29cdb526713479cc90079609b23df92ff088d469e90'}
REVIEWER = '97cdbcc36928777579b1b3c6e5b8adf7bdae37d97a2b0f2200a57cdd0ec4f067'
IR_REVIEW = '242bc12bdd883f25a56baf59f5e6a16666e8f8f8b7d5819dbcaa21ad8e907d17'
IR_ACCEPTANCE = 'ea8534a47e53adc5a667484a14779894741b45a8a12424e38164994e5f928641'
IR_TRANSFER = 'd61c7d5b9f2002079c265533bb400e9ba9f24316a761abf2eceb0ebd84c2ba0b'
COHORT = 'f3fbfa9830933ad0be5860422363aeecb89e30e6e0388172771e664987f70736'
FINAL = 'f95f68347284b265f3dbbcf7d93c30905be921ee1f98cab8e67db551efca16ad'
PROTOCOL = '47330c842872b309dd187203c679cfdeb0b94f18e6f29c3a27e8a1d938e1335f'
CHUNK_SIZE = 90_000_000


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def relative(value):
    need(isinstance(value, str), 'relative path must be text')
    path = PurePosixPath(value)
    need(value and value != '.' and not path.is_absolute() and '..' not in path.parts
         and '\\' not in value and str(path) == value, 'unsafe/noncanonical relative path')
    return path


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def item(path):
    path = Path(path)
    info = path.lstat()
    need(path.resolve() == path and stat.S_ISREG(info.st_mode), 'noncanonical/nonregular input: ' + str(path))
    return {'sha256': sha(path), 'bytes': info.st_size, 'mode': stat.S_IMODE(info.st_mode)}


def read(path):
    return json.loads(Path(path).read_text())


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def frozen_source(expected):
    path = HERE / 'source-freeze.json'
    need(sha(path) == expected, 'packaging source freeze differs')
    for name, row in read(path)['files'].items():
        need(item(HERE / relative(name)) == row, 'packaging source changed: ' + name)
    for name, row in read(path)['external_files'].items():
        need(item(WORKSPACE / relative(name)) == row, 'external packaging source changed: ' + name)


def verify_capture(spec):
    """Check extracted bytes and every original archive member, without analysis."""
    directory = WORKSPACE / relative(spec['directory'])
    archive_path = WORKSPACE / relative(spec['archive'])
    receipt_path = WORKSPACE / relative(spec['receipt'])
    need(item(archive_path) == spec['archive_record'] and item(receipt_path) == spec['receipt_record'], 'capture envelope differs')
    manifest_path = directory / 'transfer-manifest.json'
    need(item(manifest_path) == spec['manifest_record'], 'capture manifest differs')
    receipt, manifest = read(receipt_path), read(manifest_path)
    need(receipt['valid'] is True and receipt['cohort_sha256'] == COHORT
         and receipt['archive_sha256'] == spec['archive_record']['sha256']
         and receipt['transfer_manifest_sha256'] == spec['manifest_record']['sha256'], 'capture receipt join differs')
    records = dict(manifest['files'])
    need('transfer-manifest.json' not in records, 'self-referential capture manifest')
    records['transfer-manifest.json'] = spec['manifest_record']
    observed = {}
    for path in directory.rglob('*'):
        need(not path.is_symlink(), 'symlink in extracted capture')
        if path.is_file():
            observed[str(path.relative_to(directory))] = item(path)
        else:
            need(path.is_dir(), 'special file in extracted capture')
    need(observed == records, 'captured file set/bytes/modes differ')
    archived = {}
    with tarfile.open(archive_path, 'r|gz') as archive:
        for member in archive:
            relative(member.name)
            need(member.isfile() and member.name not in archived, 'unsafe/duplicate archive member')
            with archive.extractfile(member) as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            archived[member.name] = {'sha256': digest, 'bytes': member.size, 'mode': member.mode}
    need(archived == records, 'original archive differs from complete capture')
    return {'directory': directory, 'manifest': manifest, 'receipt': receipt,
            'manifest_record': spec['manifest_record'], 'receipt_record': spec['receipt_record'], 'members': records}


def validate_raw(review, raw, phase):
    pairs, samples = (12, 28) if phase == 'ir-confirmation' else (30, 64)
    need(review['valid'] is True and review['phase'] == phase and review['source_freeze_sha256'] == REVIEWER
         and review['raw_integrity_before_effects'] is True and review['variant_sha256'] == BINARIES
         and review['cohort_sha256'] == COHORT and review['finalized_sha256'] == FINAL
         and review['protocol_sha256'] == PROTOCOL, 'phase review identity/validity differs')
    need(raw['valid'] is True and raw['phase'] == phase and raw['source_freeze_sha256'] == REVIEWER
         and raw['both_workflows_complete_before_effects'] is True
         and raw['transfer_manifest_sha256'] == review['transfer_manifest_sha256']
         and set(raw['workloads']) == {'test', 'check'}, 'both raw audits are required before effects')
    for workload, row in raw['workloads'].items():
        need(row['valid'] is True and row['workload'] == workload and row['measurement_pairs'] == pairs
             and row['samples'] == samples and row['warmup_pairs'] == 2
             and row['invocations_per_variant_per_pair'] == 1 and row['native_test_executions'] == 0
             and row['compiler_invocations_per_sample'] == (6 if workload == 'test' else 1)
             and row['expected_stage_counts'] == ({'rlink': 4, 'source': 2} if workload == 'test' else {'source': 1}),
             'fixed dirty-workload raw integrity differs: ' + workload)
    if phase == 'ir-confirmation':
        need(review['primary_passes'] is True and review['secondary_passes'] is False, 'accepted IR claim scope differs')
    else:
        need(review['accepted_ir']['review_sha256'] == IR_REVIEW
             and review['accepted_ir']['transfer_manifest_sha256'] == IR_TRANSFER
             and raw['accepted_ir'] == review['accepted_ir'], 'native phase does not bind the accepted IR')


def validate_effects(review, effects, phase):
    """Consume independently accepted summaries; never resample or recalculate them."""
    need(effects['phase'] == phase and set(effects['workloads']) == {'test', 'check'}
         and effects['fixed_method'] == {'confidence': 0.99, 'bootstrap_resamples': 20000,
             'bootstrap_seed': 1701, 'minimum_reduction': 0.01, 'maximum_sign_p': 0.01}, 'effect method differs')
    for workload, row in effects['workloads'].items():
        need(row['gate']['passes_gate'] is review['primary_passes' if workload == 'test' else 'secondary_passes'], 'summary gate differs')
        if phase == 'native-confirmation':
            need(row['gate']['significant_native_regression'] is False, 'established native regression blocks publication')
    if phase == 'ir-confirmation':
        need(effects['workloads']['test']['gate']['passes_gate'] is True, 'primary IR gate must qualify')


def phase_review(spec, capture, phase):
    directory = WORKSPACE / relative(spec['directory'])
    seal = read(directory / 'seal.json')
    need(set(seal) == {'review.json', 'raw-integrity.json', 'effects.json'}, 'review seal member set differs')
    for name, expected in seal.items():
        need(item(directory / name)['sha256'] == expected, 'review bytes changed')
    need(sha(directory / 'review.json') == spec['review_sha256'], 'review input pin differs')
    review, raw = read(directory / 'review.json'), read(directory / 'raw-integrity.json')
    validate_raw(review, raw, phase)
    need(review['raw_integrity_sha256'] == seal['raw-integrity.json']
         and review['effects_sha256'] == seal['effects.json']
         and review['transfer_manifest_sha256'] == capture['manifest_record']['sha256']
         and review['collection_receipt_sha256'] == capture['receipt_record']['sha256']
         and review['archive_sha256'] == capture['receipt']['archive_sha256'], 'phase review/capture join differs')
    state_name = 'results/ir-completion-01/status.json' if phase == 'ir-confirmation' else 'results/native-confirmation.json'
    state = read(capture['directory'] / state_name)
    need(state['state'] == 'complete' and state['group'] == phase and state['completed_workloads'] == ['test', 'check']
         and state['source_restored'] is True and state['protocol_sha256'] == PROTOCOL
         and state['config_manifest_sha256'] == FINAL, 'fixed phase is not complete')
    for workload, proof in raw['workloads'].items():
        directory_name = 'results/ir-completion-01/check' if (phase, workload) == ('ir-confirmation', 'check') else 'results/' + workload + '-' + phase
        for name, key in [('manifest.json', 'manifest_sha256'), ('samples.json', 'samples_sha256')]:
            need(capture['members'][directory_name + '/' + name]['sha256'] == proof[key], 'raw review/table identity differs')
        manifest = read(capture['directory'] / directory_name / 'manifest.json')
        expected_seed = (20261021101 if phase == 'ir-confirmation' else 20261021103) + (workload == 'check')
        need(manifest['seed'] == expected_seed and manifest['pairs'] == proof['measurement_pairs']
             and manifest['warmup_pairs'] == 2 and manifest['state'] == 'complete'
             and manifest['configuration_sha256'] == proof['configuration_sha256'], 'fixed seed/configuration differs')
    # Both raw workflow proofs have been validated before opening the effects file.
    effects = read(directory / 'effects.json')
    validate_effects(review, effects, phase)
    return review, effects


def source_and_acceptance(inputs, native_review):
    publication = read(PUBLICATION_SOURCE / 'code-publication.json')
    ci = read(PUBLICATION_SOURCE / 'ci-validation.json')
    need(publication['commit'] == ci['head_sha'] == COMMIT and publication['base_commit'] == PARENT
         and publication['tree'] == ci['head_commit']['tree_id'] == TREES['candidate']
         and ci['id'] == 39607088231 and ci['status'] == 'completed' and ci['conclusion'] == 'success',
         'exact source/parent/CI proof differs')
    ir_path = WORKSPACE / 'work/sbom-current179-ir-continuation/root-ir-profiler-alias-v2-acceptance.json'
    need(sha(ir_path) == IR_ACCEPTANCE, 'root IR acceptance differs')
    ir = read(ir_path)
    need(ir['valid'] is True and ir['accepted_ir_review_sha256'] == IR_REVIEW, 'IR not accepted')
    approval_path = WORKSPACE / relative(inputs['native_acceptance']['path'])
    need(item(approval_path) == inputs['native_acceptance']['record'], 'native acceptance input differs')
    approval = read(approval_path)
    need(approval['valid'] is True and approval['authorized_operation'] == 'accept-current179-native-review-for-publication'
         and approval['accepted_native_review_sha256'] == inputs['reviews']['native']['review_sha256']
         and approval['accepted_ir_review_sha256'] == IR_REVIEW
         and approval['native_transfer_manifest_sha256'] == native_review['transfer_manifest_sha256']
         and approval['both_native_raw_audits_passed'] is True
         and approval['no_established_native_regression'] is True
         and approval['candidate_commit'] == COMMIT and approval['candidate_tree'] == TREES['candidate'],
         'root has not accepted this exact native review for publication')
    pair = read(WORKSPACE / 'work/production-build/host3-sbom-stack179/results/audit-pair.json')
    records = pair['records']
    need(len(records) == 2 and [r['source_tree'] for r in records] == list(TREES.values())
         and [r['stripped_sha256'] for r in records] == list(BINARIES.values())
         and all(r['verified_allocated_sections'] == 31 for r in records)
         and records[0]['actual_rustc_settings'] == records[1]['actual_rustc_settings']
         and records[0]['common_build_inputs_sha256'] == records[1]['common_build_inputs_sha256'] == pair['common_build_inputs_sha256'],
         'matched production pair proof differs')


def copy_lossless(source, destination, limit=CHUNK_SIZE):
    """Retain original archive bytes, splitting only at a fixed byte boundary."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected = item(source)
    chunks, digest = [], hashlib.sha256()
    remaining, index = expected['bytes'], 0
    with source.open('rb') as stream:
        while remaining or not chunks:
            count = min(remaining, limit)
            path = destination if expected['bytes'] <= limit else destination.with_name(destination.name + f'.part{index:04d}')
            with path.open('xb') as output:
                outstanding = count
                while outstanding:
                    data = stream.read(min(outstanding, 1024 * 1024))
                    need(data, 'archive truncated during copy')
                    output.write(data); digest.update(data); outstanding -= len(data)
            chunks.append({'name': path.name, **item(path)})
            remaining -= count; index += 1
        need(not stream.read(1) and digest.hexdigest() == expected['sha256'], 'archive changed during lossless copy')
    return {'original': expected, 'chunks_in_concatenation_order': chunks}


def validate_native_lineage(document, inputs, catalog):
    need(document['status'] == 'reviewed-complete' and document['phase'] == 'native-confirmation'
         and document['review_sha256'] == inputs['reviews']['native']['review_sha256']
         and document['native_acceptance_sha256'] == inputs['native_acceptance']['record']['sha256']
         and document['all_native_attempts_retained'] is True, 'final native lineage acceptance differs')
    need({'source_controls', 'preparation', 'stage', 'launch', 'collection', 'review', 'failed_admission'} <= set(document['coverage']),
         'final native lineage omits an operational stage')
    need(all(inputs['files'].get(name) == row for name, row in document['files'].items()), 'native lineage input omitted')
    need(set(catalog['required_native_failed_status_sha256']) <= {row['sha256'] for row in document['files'].values()},
         'known failed native admission status omitted')


def validate_recovery_lineage(document, inputs):
    # Imported only for accepted-input preparation/assembly; never runs a reviewer.
    import importlib.util
    spec = importlib.util.spec_from_file_location('frozen_recovery_binding', HERE / 'recovery_binding.py')
    recovery_binding = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recovery_binding)
    recovery_binding.validate(document, inputs, WORKSPACE, item, read, need, relative)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--inputs-sha256', required=True)
    args = parser.parse_args()
    inputs_path = args.inputs.absolute()
    need(inputs_path.resolve() == inputs_path and inputs_path.is_relative_to(HERE), 'owned canonical inputs required')
    need(sha(inputs_path) == args.inputs_sha256, 'input manifest differs')
    inputs = read(inputs_path)
    need(inputs['status'] == 'reviewed-ready' and inputs['assembler_sha256'] == sha(Path(__file__))
         and set(inputs['captures']) == {'ir-failed', 'ir', 'native'}
         and set(inputs['reviews']) == {'ir', 'native'}, 'native prerequisites/final inputs missing')
    frozen_source(inputs['packaging_source_freeze_sha256'])
    catalog = read(HERE / 'existing-inputs.json')
    need(all(inputs['files'].get(name) == row for name, row in catalog['files'].items()), 'existing lineage/archive omitted or changed')
    for name, row in inputs['files'].items():
        need(item(WORKSPACE / relative(name)) == row, 'frozen input changed: ' + name)
    native_lineage = WORKSPACE / relative(inputs['native_lineage_inventory']['path'])
    need(sha(native_lineage) == inputs['native_lineage_inventory']['sha256'], 'native lineage inventory changed')
    validate_native_lineage(read(native_lineage), inputs, catalog)
    validate_recovery_lineage(read(native_lineage), inputs)
    required = [inputs['native_acceptance']['path']]
    required.append(inputs['native_lineage_inventory']['path'])
    for spec in inputs['captures'].values():
        required.extend([spec['archive'], spec['receipt'], spec['directory'] + '/transfer-manifest.json'])
    for spec in inputs['reviews'].values():
        required.extend(spec['directory'] + '/' + name for name in ('review.json', 'raw-integrity.json', 'effects.json', 'seal.json'))
    need(all(name in inputs['files'] for name in required), 'final input inventory omits a consumed prerequisite')
    captures = {label: verify_capture(row) for label, row in inputs['captures'].items()}
    need(captures['ir-failed']['receipt']['phase'] == 'ir-failed-before-check'
         and captures['ir-failed']['receipt']['qualifies'] is False
         and captures['ir']['manifest_record']['sha256'] == IR_TRANSFER, 'failed/current IR lineage differs')
    continued_mutable = {'collection-identity.json', 'failure-boundary.json',
                         'fixtures/check-ir-confirmation/state.json', 'fixtures/check-ir-confirmation/journal.jsonl'}
    need(all(captures['ir']['manifest']['files'].get(name) == row
             for name, row in captures['ir-failed']['manifest']['files'].items() if name not in continued_mutable),
         'fixed completed test observations or failed history changed during IR continuation')
    reviews, effects = {}, {}
    for phase in ('ir', 'native'):
        reviews[phase], effects[phase] = phase_review(inputs['reviews'][phase], captures[phase], phase + '-confirmation')
    need(inputs['reviews']['ir']['review_sha256'] == IR_REVIEW, 'accepted IR review changed')
    mutable = {'collection-identity.json'} | {f'fixtures/{workload}-native-confirmation/{name}'
              for workload in ('test', 'check') for name in ('state.json', 'journal.jsonl')}
    need(all(captures['native']['manifest']['files'].get(name) == row
             for name, row in captures['ir']['manifest']['files'].items() if name not in mutable), 'native capture changed accepted IR bytes')
    source_and_acceptance(inputs, reviews['native'])
    manifest_path = OUTPUT.with_name(OUTPUT.name + '-manifest.json')
    need(not OUTPUT.exists() and not manifest_path.exists(), 'package output must be new')
    OUTPUT.mkdir(parents=True)
    archives = dict(catalog['archives'])
    archives['current179-native'] = {'path': inputs['captures']['native']['archive'], 'scope': 'current179'}
    retained = {}
    for label, row in sorted(archives.items()):
        source = WORKSPACE / relative(row['path'])
        need(str(source.relative_to(WORKSPACE)) in inputs['files'], 'archive is not frozen in final inputs')
        retained[label] = {'source': row['path'], 'scope': row['scope'], 'stored_directory': 'raw/' + label,
                           **copy_lossless(source, OUTPUT / 'raw' / label / source.name)}
    archive_paths = {row['path'] for row in archives.values()}
    lineage = {name: row for name, row in inputs['files'].items() if name not in archive_paths}
    with (OUTPUT / 'lineage.tar.gz').open('xb') as sink:
        with gzip.GzipFile(filename='', mode='wb', fileobj=sink, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w|') as archive:
                for name, row in sorted(lineage.items()):
                    member = tarfile.TarInfo(name); member.size = row['bytes']; member.mode = row['mode']; member.mtime = 0
                    with (WORKSPACE / name).open('rb') as stream:
                        archive.addfile(member, stream)
    observed = {}
    with tarfile.open(OUTPUT / 'lineage.tar.gz', 'r|gz') as archive:
        for member in archive:
            relative(member.name)
            need(member.isfile() and member.name not in observed, 'unsafe lineage archive')
            with archive.extractfile(member) as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            observed[member.name] = {'sha256': digest, 'bytes': member.size, 'mode': member.mode}
    need(observed == lineage, 'lossless lineage archive differs')
    summary = {'scope': 'Incremental current179 dirty uv builds; PR175 archives are historical only.',
               'commit': COMMIT, 'parent': PARENT, 'trees': TREES, 'binaries': BINARIES,
               'primary_ir_qualifies': True, 'secondary_check_ir_qualifies': False,
               'native_validation_complete': True, 'no_established_native_regression': True,
               'ir': {w: row['gate'] for w, row in effects['ir']['workloads'].items()},
               'native': {w: row['gate'] for w, row in effects['native']['workloads'].items()},
               'statistics_recomputed_by_packager': False}
    native_text = '\n'.join(f"{w}: reduction {row['gate']['reduction'] * 100:.6f}%; 99% interval "
        f"[{row['gate']['interval_99'][0] * 100:.6f}, {row['gate']['interval_99'][1] * 100:.6f}]%; "
        f"full wall-time gate {'passed' if row['gate']['passes_gate'] else 'not passed'}."
        for w, row in effects['native']['workloads'].items())
    readable = {'assembly-inputs.json': inputs_path.read_bytes(), 'assembly-source.py': Path(__file__).read_bytes(),
                'summary.json': encoded(summary), 'RAW-MANIFEST.json': encoded({'archives': retained,
                'captures': {label: {'manifest_record': row['manifest_record'], 'members': row['members']}
                             for label, row in captures.items()}, 'lineage_members': lineage}),
                'README.md': (HERE / 'EVIDENCE.md').read_text().replace('NATIVE_PENDING', native_text).encode(),
                'REPRODUCE.md': (HERE / 'REPRODUCE.md').read_bytes(), 'VALIDATION.md': (HERE / 'VALIDATION.md').read_bytes()}
    for phase, spec in inputs['reviews'].items():
        for name in ('review.json', 'raw-integrity.json', 'effects.json', 'seal.json'):
            readable[f'reviews/{phase}/{name}'] = (WORKSPACE / spec['directory'] / name).read_bytes()
    for name, data in readable.items():
        destination = OUTPUT / relative(name); destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(data)
    for name, row in inputs['files'].items():
        need(item(WORKSPACE / name) == row, 'input changed during packaging: ' + name)
    frozen_source(inputs['packaging_source_freeze_sha256'])
    need(sha(inputs_path) == args.inputs_sha256, 'final inputs changed during packaging')
    inventory = {str(path.relative_to(OUTPUT)): item(path) for path in sorted(OUTPUT.rglob('*')) if path.is_file()}
    need(all(row['bytes'] < 100_000_000 for row in inventory.values()), 'artifact needs explicit lossless splitting')
    with (OUTPUT / 'SHA256SUMS').open('x') as stream:
        stream.writelines(row['sha256'] + '  ' + name + '\n' for name, row in sorted(inventory.items()))
    with manifest_path.open('xb') as stream:
        stream.write(encoded(inventory))
    print(json.dumps({'status': 'assembled-not-published', 'manifest_sha256': sha(manifest_path), 'files': len(inventory) + 1}, indent=2))


if __name__ == '__main__':
    main()
