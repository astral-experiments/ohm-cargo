"""Bind local retry lineage to the unchanged remote collection, without effects."""
import hashlib
import shutil
import tarfile

import contract


def directory(phase):
    contract.require(phase in ('ir', 'native'), 'unexpected phase')
    return contract.CONTROLS / 'collections' / ('ir-closed-postguard' if phase == 'ir' else 'native')


def selected(phase):
    names = set(contract.read(contract.PACKAGE / 'source-freeze.json')['files']) | {'source-freeze.json'}
    names |= set(contract.read(contract.HERE / 'source-freeze.json')['files']) | {'retry/source-freeze.json'}
    names |= set(contract.read(contract.HERE / 'attempt.json')['retained_files']) | {'retry/attempt.json'}
    for retained_phase in (('ir',) if phase == 'ir' else ('ir', 'native')):
        names |= {'retry/collect-' + retained_phase + '.' + suffix for suffix in ('json', 'stdout', 'stderr')}
    return sorted(names)


def attach(phase, expected_retry_freeze):
    contract.verify_attempt(expected_retry_freeze, complete=True)
    destination = directory(phase)
    receipt = contract.read(destination / 'receipt.json')
    contract.require(receipt['status'] == 'passed', 'original collection did not pass')
    target = destination / 'local-operational-retry'
    target.mkdir(exist_ok=False)
    files = {}
    for name in selected(phase):
        source = contract.regular(contract.PACKAGE, name)
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with source.open('rb') as before, path.open('xb') as after:
            shutil.copyfileobj(before, after)
        files[name] = contract.record(source)
        contract.require(contract.record(path) == files[name], 'local retry copy differs')
    manifest = {
        'operation': 'bind-one-prestaging-retry-to-original-collection', 'state': 'passed', 'phase': phase,
        'retry_source_freeze_sha256': expected_retry_freeze,
        'original_closure_source_freeze_sha256': contract.ORIGINAL_FREEZE,
        'original_capsule_sha256': contract.CAPSULE,
        'failed_closure_launch_sha256': contract.FAILED_LAUNCH['launch-finalize.json'],
        'successful_closure_launch_sha256': contract.sha(contract.PACKAGE / 'launch-finalize.json'),
        'retry_attempt_sha256': contract.sha(contract.HERE / 'attempt.json'),
        'absence_proof_sha256': contract.sha(contract.HERE / 'absence.stdout'),
        'remote_transfer_manifest_sha256': contract.sha(destination / 'transfer-manifest.json'),
        'original_collection_receipt_sha256': contract.sha(destination / 'receipt.json'),
        'original_collection_transport_sha256': contract.sha(destination / 'transport.json'),
        'original_remote_archive_sha256': contract.sha(destination / 'payload.tar'),
        'files': files,
        'scope': 'Original raw transport and collection receipt remain byte-identical; this separate local archive adds the failed closure launch, one absence proof, new launch and frozen controls. No sampling or analysis.'}
    contract.write_new(destination / 'operational-retry-manifest.json', manifest)
    with tarfile.open(destination / 'operational-retry.tar', 'x:') as archive:
        archive.add(destination / 'operational-retry-manifest.json', arcname='manifest.json', recursive=False)
        for name in files:
            archive.add(target / name, arcname='files/' + name, recursive=False)
    contract.write_new(destination / 'operational-retry-archive.json', {
        'archive': contract.record(destination / 'operational-retry.tar'),
        'manifest': contract.record(destination / 'operational-retry-manifest.json')})
    return verify(phase, expected_retry_freeze)


def verify(phase, expected_retry_freeze):
    contract.verify_attempt(expected_retry_freeze, complete=True)
    destination = directory(phase)
    manifest = contract.read(destination / 'operational-retry-manifest.json')
    contract.require(manifest['state'] == 'passed' and manifest['phase'] == phase
        and manifest['retry_source_freeze_sha256'] == expected_retry_freeze
        and manifest['original_closure_source_freeze_sha256'] == contract.ORIGINAL_FREEZE
        and manifest['original_capsule_sha256'] == contract.CAPSULE
        and manifest['failed_closure_launch_sha256'] == contract.FAILED_LAUNCH['launch-finalize.json']
        and manifest['successful_closure_launch_sha256'] == contract.sha(contract.PACKAGE / 'launch-finalize.json')
        and manifest['retry_attempt_sha256'] == contract.sha(contract.HERE / 'attempt.json')
        and manifest['absence_proof_sha256'] == contract.sha(contract.HERE / 'absence.stdout'), 'retry collection lineage differs')
    joins = {'remote_transfer_manifest_sha256': 'transfer-manifest.json',
             'original_collection_receipt_sha256': 'receipt.json',
             'original_collection_transport_sha256': 'transport.json',
             'original_remote_archive_sha256': 'payload.tar'}
    for key, name in joins.items():
        contract.require(manifest[key] == contract.sha(destination / name), 'original collection receipt changed')
    contract.require(contract.read(destination / 'receipt.json')['status'] == 'passed', 'original collector was not successful')
    collection = contract.read(contract.HERE / ('collect-' + phase + '.json'))
    contract.require(collection['returncode'] == 0 and collection['phase'] == phase
                     and collection['retry_source_freeze_sha256'] == expected_retry_freeze
                     and collection['original_collection_receipt_sha256'] == contract.sha(destination / 'receipt.json')
                     and collection['stdout_sha256'] == contract.sha(contract.HERE / ('collect-' + phase + '.stdout'))
                     and collection['stderr_sha256'] == contract.sha(contract.HERE / ('collect-' + phase + '.stderr')),
                     'collector process/stream join differs')
    contract.require(set(manifest['files']) == set(selected(phase)), 'local retry evidence file set differs')
    for name, expected in manifest['files'].items():
        contract.require(contract.record(contract.regular(destination / 'local-operational-retry', name))
                         == contract.record(contract.regular(contract.PACKAGE, name)) == expected,
                         'local retry evidence bytes differ: ' + name)
    actual = set()
    for path in (destination / 'local-operational-retry').rglob('*'):
        contract.require(not path.is_symlink(), 'unexpected retry evidence symlink')
        if path.is_file():
            actual.add(str(path.relative_to(destination / 'local-operational-retry')))
        else:
            contract.require(path.is_dir(), 'unexpected retry evidence type')
    contract.require(actual == set(manifest['files']), 'local retry evidence directory set differs')
    descriptor = contract.read(destination / 'operational-retry-archive.json')
    contract.require(descriptor['archive'] == contract.record(destination / 'operational-retry.tar')
                     and descriptor['manifest'] == contract.record(destination / 'operational-retry-manifest.json'),
                     'local retry archive binding differs')
    expected = {'manifest.json': contract.record(destination / 'operational-retry-manifest.json')}
    expected.update({'files/' + name: row for name, row in manifest['files'].items()})
    seen = set()
    with tarfile.open(destination / 'operational-retry.tar', 'r:') as archive:
        for member in archive:
            contract.relative(member.name)
            contract.require(member.isfile() and not member.issym() and not member.islnk()
                             and member.name in expected and member.name not in seen, 'unsafe/extra retry archive member')
            data = archive.extractfile(member).read()
            contract.require({'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)} == expected[member.name],
                             'retry archive content differs')
            seen.add(member.name)
    contract.require(seen == set(expected), 'retry archive is incomplete')
    contract.verify_controls(expected_retry_freeze)
    return {'state': 'passed', 'phase': phase,
            'operational_retry_manifest_sha256': contract.sha(destination / 'operational-retry-manifest.json'),
            'operational_retry_archive_sha256': contract.sha(destination / 'operational-retry.tar'),
            'failed_closure_launch_sha256': contract.FAILED_LAUNCH['launch-finalize.json'],
            'successful_closure_launch_sha256': contract.sha(contract.PACKAGE / 'launch-finalize.json'),
            'absence_proof_sha256': contract.sha(contract.HERE / 'absence.stdout'),
            'files': len(manifest['files']), 'sampling_or_analysis': False}
