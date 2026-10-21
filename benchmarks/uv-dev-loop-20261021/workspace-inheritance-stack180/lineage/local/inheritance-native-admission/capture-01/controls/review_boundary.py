#!/usr/bin/env python3
"""Independently prove the exact zero-work admission boundary, without effects."""
import argparse
import ast
import datetime
import hashlib
from pathlib import Path
import sys
import tarfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common


def source_boundary():
    common.need(common.sha(HERE / 'original/driver.py') == common.DRIVER, 'driver source differs')
    tree = ast.parse((HERE / 'original/driver.py').read_text())
    run = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'run_phase')
    guarded = next(node for node in run.body if isinstance(node, ast.Try))
    loop = guarded.body[0]
    common.need(isinstance(loop, ast.For) and ast.unparse(loop.target) == '(workflow, seed)', 'phase loop differs')
    update = loop.body[1].value
    common.need(ast.unparse(update.func) == 'status.update'
                and {value.arg: ast.unparse(value.value) for value in update.keywords}
                    == {'state': "'preflight'", 'workflow': 'workflow', 'quiet': 'ref.quiet()'}
                and ast.unparse(loop.body[3].value) == 'ref.preflight(core, workflow)', 'first guard/preflight boundary differs')
    reference = HERE / 'original/reference-native-controller.py'
    common.need(common.sha(reference) == '75206df60ff0a3305dd41410bf72a8f738cd1ab3a7f04adb5c2d12b8aa8c1573', 'reference source differs')
    preflight = next(node for node in ast.parse(reference.read_text()).body if isinstance(node, ast.FunctionDef) and node.name == 'preflight')
    common.need(ast.unparse(preflight.body[2].value) == 'output.mkdir(exist_ok=False)', 'preflight no longer starts with exclusive directory creation')
    stderr = (HERE / 'history/launch-native.stderr').read_text()
    common.need(f'line {update.lineno}, in run_phase' in stderr and 'quiet=ref.quiet()' in stderr
                and 'AssertionError: ' + repr(common.BUSY) in stderr, 'traceback differs from source boundary')
    return {'driver_guard_line': update.lineno, 'first_preflight_call_line': loop.body[3].lineno,
            'preflight_directory_creation_line': preflight.body[2].lineno,
            'basis': 'The quiet argument raised before status.update or the first preflight call. That preflight creates its exclusive directory before any Cargo install/run.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-freeze-sha256', required=True)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--capture-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    common.verify_sources(HERE, args.source_freeze_sha256)
    directory = args.capture.resolve()
    common.need(common.sha(directory / 'capture.json') == args.capture_sha256, 'capture receipt differs')
    capture = common.read(directory / 'capture.json')
    common.need(capture['status'] == 'captured' and capture['qualification'] == 'not evaluated', 'untrusted capture state')
    for name, expected in capture['files'].items():
        common.need(common.record(directory / common.relative(name)) == expected, 'captured byte differs')
    common.verify_sources(directory / 'controls', args.source_freeze_sha256)
    transfer = common.read(directory / 'transfer-manifest.json')
    common.need(transfer['source_freeze_sha256'] == capture['source_freeze_sha256'] == args.source_freeze_sha256
                and transfer['host'] == common.HOST and transfer['root'] == common.ROOT
                and transfer['seal_sha256'] == common.SEAL and transfer['qualification'] == 'not evaluated', 'transfer identity differs')
    common.need(set(transfer['files']) == {'remote/' + name for name in common.SELECTED} | {'observation.json'},
                'capture file scope differs')
    archive_seen = {}
    with tarfile.open(directory / 'payload.tar', 'r:') as archive:
        for member in archive:
            common.relative(member.name)
            common.need(member.isfile() and not member.issym() and not member.islnk() and member.name not in archive_seen,
                        'unsafe archive member')
            with archive.extractfile(member) as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            archive_seen[member.name] = {'sha256': digest, 'size': member.size}
    common.need(archive_seen == transfer['files'] | {'transfer-manifest.json': common.record(directory / 'transfer-manifest.json')},
                'archive and extracted inventory differ')
    transport = common.read(directory / 'transport.json')
    request = common.read(directory / 'request.json')
    common.need(transport['returncode'] == 0 and transport['archive'] == common.record(directory / 'payload.tar')
                and transport['stderr'] == common.record(directory / 'transfer.stderr')
                and transport['request_sha256'] == common.sha(directory / 'request.json'), 'transport receipt differs')
    expected_source = (HERE / 'common.py').read_text() + '\n' + (HERE / 'capture_remote.py').read_text()
    observation = common.read(directory / 'observation.json')
    common.need(observation['remote_source_sha256'] == request['remote_source_sha256']
                == hashlib.sha256(expected_source.encode()).hexdigest()
                and observation['source_freeze_sha256'] == request['source_freeze_sha256'] == args.source_freeze_sha256,
                'remote source binding differs')
    closed = common.read(HERE / 'inputs/closed-ir-transfer-manifest.json')
    common.need(hashlib.sha256(request['closed_ir_manifest'].encode()).hexdigest() == common.CLOSED_IR
                and observation['prior_500_file_hashes'] == closed['files'] and len(closed['files']) == 500,
                'original IR preservation differs')
    root = directory / 'remote'
    for name, digest in closed['files'].items():
        if name in common.SELECTED:
            common.need(common.sha(root / name) == digest, 'supporting metadata differs from accepted IR capture')
    status = common.read(root / common.MOVABLE[0])
    prerequisite = common.read(root / common.MOVABLE[1])
    common.boundary(status, prerequisite, observation['absence'], closed)
    source_proof = source_boundary()
    common.need(observation['boundary'] == {'status': 'passed exact zero-work boundary'}
                and observation['native_status_sha256'] == common.sha(root / common.MOVABLE[0])
                and observation['native_prerequisite_sha256'] == common.sha(root / common.MOVABLE[1])
                and observation['remaining_owned_processes'] == [] and observation['native_effects_inspected'] is False
                and observation['canonical_cargo']['sha256'] == common.VARIANTS['candidate'], 'boundary observation differs')
    common.need(observation['seal_sha256'] == common.SEAL and observation['driver_sha256'] == common.DRIVER
                and observation['original_source_freeze_sha256'] == common.ORIGINAL_SOURCE
                and observation['previous_closed_ir_manifest_sha256'] == common.CLOSED_IR
                and observation['host'] == common.HOST and observation['root'] == common.ROOT and observation['uid'] == 1000,
                'observation identity differs')
    common.verify_sources(HERE, args.source_freeze_sha256)
    for name, expected in capture['files'].items():
        common.need(common.record(directory / common.relative(name)) == expected, 'capture changed during review')
    report = {'status': 'passed zero-work native admission boundary', 'qualifies': False,
              'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source_freeze_sha256': args.source_freeze_sha256, 'review_source_sha256': common.sha(Path(__file__)),
              'capture_sha256': args.capture_sha256, 'capture_archive': common.record(directory / 'payload.tar'),
              'failed_local_launch_sha256': common.FAILED_LAUNCH,
              'failed_native_status_sha256': common.sha(root / common.MOVABLE[0]),
              'native_prerequisite_sha256': common.sha(root / common.MOVABLE[1]),
              'original_ir_500_files_preserved': True, 'all_10_native_workload_paths_absent': True,
              'retained_namespace_absent': True, 'native_cargo_calls': 0, 'native_measurements': 0,
              'count_basis': 'Authenticated control flow, failed-stage metadata, unchanged canonical candidate and exact absence proof; no process tracing was added.',
              'effects_inspected': False, 'statistics_computed': False, 'source_boundary': source_proof,
              'recovery_scope': 'After separate approval, retain/move only the two failed remote metadata files and three local launch receipts, then replay byte-identical original phase controls.'}
    common.write(args.output, report)
    print(__import__('json').dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
