"""Exact transport-255 lineage; this module never runs a workload or analysis."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
CONTROLS = PACKAGE.parent / 'inheritance-measurement'
RETRY_FREEZE = 'bd4a8a3cac7792b7db3feeccac1a0a5e4b609a011411d5277cb5c944c8729bb6'
ATTEMPT = 'c9309db4f705090c963515651af049c3a4683e22f395566ed1d6415d51205174'
LAUNCH = '17e73463fbc508debd8f1cdaefdc889d2c1a1cecc35dcb1a729d41b9e4d47a16'
INSPECTION = 'e67d84f257f66c1c95c1ffaaa9969389cda0f2b771da5a0805c51ca124151c1d'
FINALIZATION = '23553c50f247b3a7b92335bed300d78d187329ac0ff61f0ceb5c48abf0b9242d'
FINAL_STATUS = '733cc2e9c98bf07956726b3f9d46cb781ee71b19de1c3380611d6d46feac46ec'
ERROR = '7259ab47de8b3cacb6db3f7b58269e5c592d6fcbb045f3dcc39451c919b75516'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def record(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.resolve() == path, 'noncanonical retained file')
    return {'sha256': sha(path), 'size': path.stat().st_size}


def relative(name):
    value = PurePosixPath(name)
    require(bool(name) and name != '.' and not value.is_absolute() and '..' not in value.parts
            and '\\' not in name and str(value) == name, 'unsafe relative path')
    return value


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False);stream.write('\n')


def retry_contract():
    path = PACKAGE / 'retry/contract.py'
    require(sha(path) == 'a024bc64371ddc8d0403201202b7f96549e040c31944acaeaa3970310c040a60', 'retry contract changed')
    spec = importlib.util.spec_from_file_location('inheritance_retained_retry_contract', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_sources(expected):
    require(sha(HERE / 'source-freeze.json') == expected, 'transport-resolution freeze differs')
    frozen = read(HERE / 'source-freeze.json')
    require(frozen['operation'] == 'collect-and-review-completed-closure-after-transport255'
            and frozen['launch_sha256'] == LAUNCH and frozen['inspection_sha256'] == INSPECTION,
            'transport-resolution scope differs')
    for name, digest in frozen['files'].items():
        require(record(PACKAGE / relative(name))['sha256'] == digest, 'transport-resolution input changed: ' + name)
    verify_local_failure()
    return frozen


def verify_local_failure():
    old = retry_contract()
    old.verify_attempt(RETRY_FREEZE, complete=False)
    require(sha(PACKAGE / 'retry/attempt.json') == ATTEMPT
            and sha(PACKAGE / 'launch-finalize.json') == LAUNCH
            and sha(PACKAGE / 'retry/root-after-transport-inspection.json') == INSPECTION, 'exact transport history differs')
    attempt, launch = read(PACKAGE / 'retry/attempt.json'), read(PACKAGE / 'launch-finalize.json')
    require(attempt['state'] == 'failed' and attempt['returncode'] == 255
            and attempt['absence_probe_returncode'] == 0 and attempt['original_sources_failure_and_raw_capture_preserved'] is True,
            'not the recorded failed transport attempt')
    require(launch['returncode'] == 255 and launch['operation'] == 'finalize-ir-postguard'
            and launch['host'] == old.HOST and launch['root'] == old.ROOT
            and launch['source_freeze_sha256'] == old.ORIGINAL_FREEZE
            and launch['closure_manifest_sha256'] == old.CAPSULE
            and launch['measurement_seal_sha256'] == old.MEASUREMENT_SEAL, 'transport launch identity differs')
    require((PACKAGE / 'launch-finalize.stdout').read_bytes() == b''
            and sha(PACKAGE / 'launch-finalize.stderr') == ERROR
            and launch['stderr_sha256'] == ERROR, 'transport error/empty stdout differs')
    proof = read(PACKAGE / 'retry/absence.stdout')
    old.verify_absence_proof(proof)
    inspection = read(PACKAGE / 'retry/root-after-transport-inspection.json')
    require(inspection['returncode'] == 0 and inspection['stderr'] == '', 'read-only completion inspection failed')
    observed = json.loads(inspection['stdout'])
    require(observed['host'] == old.HOST, 'inspection host differs')
    expected_paths = {'closures/ir-postguard', 'closures/ir-postguard/started.json',
                      'closures/ir-postguard/finalization.json', 'results/ir-status.json'}
    expected_paths |= {name for name in old.ABSENT if name.startswith('results/')}
    require(set(observed['paths']) == expected_paths, 'inspection output path set differs')
    for name, row in observed['paths'].items():
        require(row['lexists'] is True and row['is_file'] is (name != 'closures/ir-postguard'), 'inspection path was missing/nonregular')
    final = observed['paths']['closures/ir-postguard/finalization.json']
    status = observed['paths']['results/ir-status.json']
    require(final['sha256'] == FINALIZATION and final['metadata']['state'] == 'complete'
            and status['sha256'] == FINAL_STATUS and status['metadata']['state'] == 'complete',
            'inspection did not authenticate completed closure/status')
    require(attempt['started_at'] <= proof['observed_at'] <= launch['started_at']
            <= final['metadata']['started_at'] <= final['metadata']['finished_at'] <= observed['observed_at'], 'remote completion chronology differs')
    require(launch['started_at'] <= launch['finished_at'] <= attempt['finished_at'] <= observed['observed_at'], 'local failed transport chronology differs')
    return observed


def verify_remote_completion(package, remote, files, receipt, status):
    require(Path(package).resolve() == PACKAGE, 'unexpected retained closure package')
    observed = verify_local_failure()
    for name, row in observed['paths'].items():
        if not row['is_file']:
            continue
        require(files[name] == sha(Path(remote) / name) == row['sha256'], 'remote result differs from read-only inspection: ' + name)
    require(receipt['state'] == status['state'] == 'complete'
            and receipt['started_at'] == observed['paths']['closures/ir-postguard/finalization.json']['metadata']['started_at']
            and receipt['finished_at'] == observed['paths']['closures/ir-postguard/finalization.json']['metadata']['finished_at'],
            'remote finalization metadata differs')
    return observed


def directory(phase):
    require(phase in ('ir', 'native'), 'unknown phase')
    return CONTROLS / 'collections' / ('ir-closed-postguard' if phase == 'ir' else 'native')


def attach_evidence(phase, expected):
    frozen = verify_sources(expected)
    destination = directory(phase)
    require(read(destination / 'receipt.json')['status'] == 'passed', 'ordinary collection did not complete')
    target = destination / 'local-transport-resolution'
    target.mkdir(exist_ok=False)
    names = set(frozen['files']) | {'transport/source-freeze.json'}
    records = {}
    for name in sorted(names):
        source, output = PACKAGE / relative(name), target / relative(name)
        output.parent.mkdir(parents=True, exist_ok=True)
        with source.open('rb') as incoming, output.open('xb') as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        records[name] = record(source)
        require(record(output) == records[name], 'transport history copy differs')
    manifest = {'state': 'passed', 'phase': phase, 'transport_source_freeze_sha256': expected,
                'failed_local_launch_sha256': LAUNCH, 'failed_wrapper_attempt_sha256': ATTEMPT,
                'successful_read_only_inspection_sha256': INSPECTION,
                'remote_finalization_sha256': FINALIZATION, 'remote_ir_status_sha256': FINAL_STATUS,
                'local_transport_returncode': 255, 'remote_process_exit_code': None,
                'collection_receipt_sha256': sha(destination / 'receipt.json'),
                'remote_transfer_manifest_sha256': sha(destination / 'transfer-manifest.json'),
                'remote_archive_sha256': sha(destination / 'payload.tar'), 'files': records,
                'scope': 'The remote metadata closure completed; its SSH transport failed. Original failed receipts remain unchanged. No execution or analysis is repeated.'}
    write(destination / 'transport-resolution-manifest.json', manifest)
    with tarfile.open(destination / 'transport-resolution.tar', 'x:') as archive:
        archive.add(destination / 'transport-resolution-manifest.json', arcname='manifest.json', recursive=False)
        for name in records:
            archive.add(target / name, arcname='files/' + name, recursive=False)
    write(destination / 'transport-resolution-archive.json', {
        'archive': record(destination / 'transport-resolution.tar'),
        'manifest': record(destination / 'transport-resolution-manifest.json')})
    return verify_collection(phase, expected)


def verify_collection(phase, expected):
    frozen = verify_sources(expected)
    destination = directory(phase)
    manifest = read(destination / 'transport-resolution-manifest.json')
    require(manifest['state'] == 'passed' and manifest['phase'] == phase
            and manifest['transport_source_freeze_sha256'] == expected
            and manifest['failed_local_launch_sha256'] == LAUNCH
            and manifest['failed_wrapper_attempt_sha256'] == ATTEMPT
            and manifest['successful_read_only_inspection_sha256'] == INSPECTION
            and manifest['remote_finalization_sha256'] == FINALIZATION
            and manifest['remote_ir_status_sha256'] == FINAL_STATUS
            and manifest['local_transport_returncode'] == 255 and manifest['remote_process_exit_code'] is None,
            'transport history join differs')
    for key, name in {'collection_receipt_sha256': 'receipt.json', 'remote_transfer_manifest_sha256': 'transfer-manifest.json',
                      'remote_archive_sha256': 'payload.tar'}.items():
        require(manifest[key] == sha(destination / name), 'ordinary collection changed')
    require(set(manifest['files']) == set(frozen['files']) | {'transport/source-freeze.json'}, 'history file set differs')
    for name, expected_file in manifest['files'].items():
        require(record(destination / 'local-transport-resolution' / relative(name))
                == record(PACKAGE / relative(name)) == expected_file, 'history file bytes differ')
    actual = set()
    for path in (destination / 'local-transport-resolution').rglob('*'):
        require(not path.is_symlink(), 'unexpected history symlink')
        if path.is_file():
            actual.add(str(path.relative_to(destination / 'local-transport-resolution')))
        else:
            require(path.is_dir(), 'unexpected history entry type')
    require(actual == set(manifest['files']), 'history directory member set differs')
    descriptor = read(destination / 'transport-resolution-archive.json')
    require(descriptor['archive'] == record(destination / 'transport-resolution.tar')
            and descriptor['manifest'] == record(destination / 'transport-resolution-manifest.json'), 'history archive binding differs')
    members = {'manifest.json': record(destination / 'transport-resolution-manifest.json')}
    members.update({'files/' + name: value for name, value in manifest['files'].items()})
    seen = set()
    with tarfile.open(destination / 'transport-resolution.tar', 'r:') as archive:
        for member in archive:
            relative(member.name)
            require(member.isfile() and not member.issym() and not member.islnk()
                    and member.name in members and member.name not in seen, 'unsafe history archive member')
            with archive.extractfile(member) as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            require({'sha256': digest, 'size': member.size} == members[member.name], 'history archive bytes differ')
            seen.add(member.name)
    require(seen == set(members), 'history archive is incomplete')
    return {'state': 'passed', 'phase': phase, 'source_freeze_sha256': expected,
            'manifest_sha256': sha(destination / 'transport-resolution-manifest.json'),
            'archive_sha256': sha(destination / 'transport-resolution.tar'),
            'remote_finalization_sha256': FINALIZATION, 'local_transport_returncode': 255,
            'remote_process_exit_code': None, 'execution_or_analysis_repeated': False}
