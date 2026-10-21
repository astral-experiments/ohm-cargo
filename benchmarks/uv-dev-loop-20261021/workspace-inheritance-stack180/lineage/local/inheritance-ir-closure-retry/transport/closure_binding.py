"""Verify the operational failure lineage without inspecting performance effects."""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
import tarfile

import closure_contract as contract
import transport_contract as transport


def utc(value):
    result = datetime.datetime.fromisoformat(value)
    assert result.utcoffset() == datetime.timedelta()
    return result


def verify_failed_capture(controls):
    directory = Path(controls) / 'collections/ir-failed-postguard'
    assert contract.sha(directory / 'transfer-manifest.json') == contract.FAILED_CAPTURE
    expected = Path(__file__).resolve().parents[1] / 'failed-capture'
    for name in ('transfer-manifest.json', 'receipt.json', 'transport.json'):
        assert contract.sha(directory / name) == contract.sha(expected / name)
    manifest = contract.read(directory / 'transfer-manifest.json')
    receipt, transport = (contract.read(directory / name) for name in ('receipt.json', 'transport.json'))
    assert receipt['status'] == 'preserved' and receipt['qualifies'] is False
    assert receipt['files'] == len(manifest['files']) == 477
    assert receipt['transfer_manifest_sha256'] == contract.FAILED_CAPTURE
    assert receipt['measurement_seal_sha256'] == manifest['seal_sha256'] == contract.SEAL
    assert manifest['phase'] == receipt['phase'] == 'ir' and manifest['root'] == str(contract.ROOT)
    assert manifest['terminal_state'] == 'failed' and manifest['qualifies'] is False
    assert transport['returncode'] == 0
    assert contract.sha(directory / 'payload.tar') == transport['archive_sha256']
    assert contract.sha(directory / 'transfer.stderr') == transport['stderr_sha256']
    seen = set()
    with tarfile.open(directory / 'payload.tar', 'r:') as archive:
        for member in archive:
            contract.relative(member.name)
            assert member.isfile() and not member.issym() and not member.islnk() and member.name not in seen
            seen.add(member.name)
            if member.name == 'transfer-manifest.json':
                assert archive.extractfile(member).read() == (directory / member.name).read_bytes()
                continue
            assert member.name.startswith('remote/')
            name = member.name[len('remote/'):]
            assert name in manifest['files']
            with archive.extractfile(member) as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            path = contract.regular(directory / 'remote', name)
            assert digest == manifest['files'][name] == contract.sha(path)
            assert member.size == path.stat().st_size
    assert seen == {'transfer-manifest.json'} | {'remote/' + name for name in manifest['files']}
    actual = set()
    for path in (directory / 'remote').rglob('*'):
        assert not path.is_symlink()
        if path.is_file():
            actual.add(str(path.relative_to(directory / 'remote')))
    assert actual == set(manifest['files'])
    assert manifest['files'][contract.STATUS_PATH] == contract.FAILED_STATUS
    return manifest


def verify_closed_ir(controls, remote, files, package, collection_manifest):
    """Join raw preservation and completed remote closure to the exact failed SSH transport."""
    controls, remote, package = map(Path, (controls, remote, package))
    binding = contract.read(package / 'reviewer/closure-binding.json')
    manifest_sha = binding['closure_manifest_sha256']
    source_sha = contract.sha(package / 'source-freeze.json')
    source_freeze = contract.read(package / 'source-freeze.json')
    for name, digest in source_freeze['files'].items():
        assert contract.sha(contract.regular(package, name)) == digest, name
    assert source_freeze['files']['closure-manifest.json'] == manifest_sha
    assert binding['failed_capture_sha256'] == contract.FAILED_CAPTURE
    capsule = remote / contract.PREFIX
    manifest, retained = contract.verify_manifest(capsule, manifest_sha)
    assert contract.sha(capsule / 'source-freeze.json') == source_sha
    old = verify_failed_capture(controls)
    assert old == retained
    expected_capsule_files = {contract.PREFIX + '/' + name for name in manifest['files']}
    expected_capsule_files |= {contract.PREFIX + '/' + name for name in
                              ('closure-manifest.json', 'source-freeze.json', 'started.json', 'finalization.json')}
    assert {name for name in files if name.startswith(contract.PREFIX + '/')} == expected_capsule_files
    receipt = contract.read(capsule / 'finalization.json')
    started = contract.read(capsule / 'started.json')
    assert receipt['state'] == 'complete' and receipt['phase'] == 'ir'
    assert receipt['kind'] == 'metadata-only-ir-postguard-closure'
    assert receipt['root'] == str(contract.ROOT) and receipt['host'] == contract.HOST
    assert receipt['closure_manifest_sha256'] == manifest_sha and receipt['source_freeze_sha256'] == source_sha
    assert receipt['measurement_seal_sha256'] == contract.SEAL and receipt['original_driver_sha256'] == contract.DRIVER
    assert receipt['analysis_tail_ast_sha256'] == contract.TAIL_AST
    assert receipt['failed_capture_sha256'] == contract.FAILED_CAPTURE
    assert receipt['failed_status_sha256'] == contract.FAILED_STATUS and receipt['failed_launch_sha256'] == contract.FAILED_LAUNCH
    assert receipt['original_input_file_count'] == 900 and receipt['original_sample_count'] == 56
    assert receipt['workload_invocations'] == 0 and receipt['original_raw_bytes_preserved'] is True
    assert contract.sha(capsule / 'started.json') == receipt['started_receipt_sha256']
    assert started['state'] == 'starting' and started['analysis_commands'] == []
    assert all(receipt[key] == value for key, value in started.items() if key not in ('state', 'analysis_commands'))
    assert receipt['original_files_sha256_before'] == old['files']
    assert set(receipt['original_files_sha256_after']) == set(old['files'])
    for name, digest in old['files'].items():
        if name != contract.STATUS_PATH:
            assert files[name] == receipt['original_files_sha256_after'][name] == digest, name
        else:
            assert files[name] == receipt['original_files_sha256_after'][name] == receipt['final_status_sha256']
    assert set(receipt['analysis_files_sha256']) == contract.ANALYSES
    for name, digest in receipt['analysis_files_sha256'].items():
        assert files[name] == digest
    assert receipt['analysis_commands'] == [contract.analyze_command('/usr/bin/python3', name) for name in ('check', 'test')]
    assert set(receipt['repeated_raw_audits']) == {'check', 'test'}
    assert all(value['state'] == 'passed' and value['pairs'] == 12 and value['warmup_pairs'] == 2
               and value['invocations_verified'] == value['profile_hashes_verified'] == 28
               for value in receipt['repeated_raw_audits'].values())
    assert receipt['quiet_before']['other_workloads'] == []
    status = contract.read(remote / contract.STATUS_PATH)
    assert status['state'] == 'complete' and status['quiet']['other_workloads'] == []
    assert status['operational_closure'] == {'manifest_sha256': manifest_sha,
        'failed_capture_sha256': contract.FAILED_CAPTURE, 'failed_status_sha256': contract.FAILED_STATUS,
        'failed_launch_sha256': contract.FAILED_LAUNCH,
        'retained_failed_status_path': str(contract.ROOT / contract.PREFIX / 'failed-capture/ir-status.json')}
    failed = contract.read(capsule / 'failed-capture/ir-status.json')
    assert status['started_at'] == failed['started_at']
    assert contract.sha(controls / 'launch-ir.json') == contract.FAILED_LAUNCH
    old_launch = contract.read(controls / 'launch-ir.json')
    assert old_launch == contract.read(capsule / 'failed-capture/launch-ir.json')
    for suffix in ('stdout', 'stderr'):
        assert contract.sha(controls / ('launch-ir.' + suffix)) == old_launch[suffix + '_sha256']
    launch_path = package / 'launch-finalize.json'
    launch = contract.read(launch_path)
    assert launch['returncode'] == 255 and launch['operation'] == 'finalize-ir-postguard'
    assert launch['host'] == contract.HOST and launch['root'] == str(contract.ROOT)
    assert launch['source_freeze_sha256'] == source_sha and launch['closure_manifest_sha256'] == manifest_sha
    assert launch['failed_capture_sha256'] == contract.FAILED_CAPTURE and launch['measurement_seal_sha256'] == contract.SEAL
    for suffix in ('stdout', 'stderr'):
        assert contract.sha(package / ('launch-finalize.' + suffix)) == launch[suffix + '_sha256']
    # This exact SSH255 is authenticated by the retained failed launch and a
    # later independent read-only observation of the completed remote closure.
    inspection = transport.verify_remote_completion(package, remote, files, receipt, status)
    assert utc(failed['started_at']) <= utc(failed['failed_at']) <= utc(old_launch['finished_at'])
    assert utc(old_launch['finished_at']) <= utc(launch['started_at']) <= utc(receipt['started_at'])
    assert utc(receipt['started_at']) <= utc(status['completed_at']) <= utc(receipt['finished_at']) <= utc(inspection['observed_at'])
    assert utc(launch['started_at']) <= utc(launch['finished_at']) <= utc(inspection['observed_at'])
    for workflow in ('check', 'test'):
        integrity = contract.read(remote / ('results/ir-' + workflow + '/integrity.json'))
        assert utc(integrity['completed_at']) <= utc(failed['failed_at'])
        assert utc(receipt['repeated_raw_audits'][workflow]['completed_at']) <= utc(receipt['started_at'])
    expected_binding = {'closure_manifest_sha256': manifest_sha, 'source_freeze_sha256': source_sha,
                        'failed_capture_sha256': contract.FAILED_CAPTURE,
                        'finalization_sha256': contract.sha(capsule / 'finalization.json')}
    assert collection_manifest['operational_closure'] == expected_binding
    return {**receipt, 'receipt_sha256': expected_binding['finalization_sha256'],
            'launch_receipt_sha256': contract.sha(launch_path), 'failed_capture_retained': True}
