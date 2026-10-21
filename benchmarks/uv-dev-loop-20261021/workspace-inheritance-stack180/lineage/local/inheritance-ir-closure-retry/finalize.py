#!/usr/bin/env python3
"""Finish the existing IR phase using only its frozen post-audit metadata tail."""
from __future__ import annotations

import argparse
import ast
import copy
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import types

SELF = Path(__file__).resolve()
HERE = SELF.parent
# The launcher verifies the full staged manifest before this interpreter starts.
spec = importlib.util.spec_from_file_location('inheritance_closure_contract', HERE / 'closure_contract.py')
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def legacy_files():
    root = contract.ROOT
    paths = [root / name for name in ('delivery.json', 'ownership.json', 'delivery-occupancy.json')]
    for directory in ('controller', 'metadata', 'logs', 'benchmark', 'results'):
        for path in (root / directory).rglob('*'):
            assert not path.is_symlink(), path
            if path.is_dir():
                continue
            assert path.is_file() and path.resolve() == path, path
            if path.is_relative_to(root / 'controller/binaries'):
                continue
            paths.append(path)
    return {str(path.relative_to(root)) for path in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--closure-manifest-sha256', required=True)
    parser.add_argument('--source-freeze-sha256', required=True)
    args = parser.parse_args()
    assert socket.gethostname() == contract.HOST and os.getuid() == 1000
    assert contract.ROOT.resolve() == contract.ROOT and contract.ROOT.stat().st_uid == 1000
    assert Path('/').stat().st_uid == 0 and HERE == contract.ROOT / contract.PREFIX
    assert HERE.resolve() == HERE and HERE.stat().st_uid == 1000 and not SELF.is_symlink()
    manifest, capture = contract.verify_manifest(HERE, args.closure_manifest_sha256)
    assert contract.sha(HERE / 'source-freeze.json') == args.source_freeze_sha256
    source_freeze = contract.read(HERE / 'source-freeze.json')
    assert source_freeze['files']['closure-manifest.json'] == args.closure_manifest_sha256
    assert all(source_freeze['files'][name] == digest for name, digest in manifest['files'].items())
    for name in ('started.json', 'finalization.json'):
        assert not (HERE / name).exists(), 'This closure is single use; retain any prior attempt.'
    assert not (contract.ROOT / 'results/native-status.json').exists()
    assert legacy_files() == set(capture['files'])
    before = contract.original_hashes(contract.ROOT, capture)
    assert contract.sha(contract.ROOT / 'delivery.json') == contract.DELIVERY
    assert contract.read(contract.ROOT / 'ownership.json')['delivery_sha256'] == contract.DELIVERY
    script = contract.ROOT / 'controller/driver.py'
    assert contract.sha(script) == contract.DRIVER == contract.sha(HERE / 'original/driver.py')
    spec = importlib.util.spec_from_file_location('inheritance_closure_driver', script)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    assert contract.sha(driver.CORE) == driver.CORE_SHA and contract.sha(driver.RUNNER) == driver.RUNNER_SHA
    assert len(driver.read(driver.SEAL)['file_sha256']) == 900
    driver.verify_assets()
    driver.verify_seal(contract.SEAL)
    core = driver.load_module('paired', driver.CORE, driver.CORE_SHA)
    ref = driver.reference('ir')
    # This is the unchanged guard, including its exact original occupancy policy.
    quiet_before = ref.quiet()
    audits = {}
    for workflow, seed in driver.STAGES['ir']['plan']:
        audits[workflow] = driver.audit_ir(core, workflow, seed)
        assert audits[workflow]['state'] == 'passed'
    assert contract.original_hashes(contract.ROOT, capture) == before
    assert not any((contract.ROOT / name).exists() for name in contract.ANALYSES)
    tail = contract.original_tail(script.read_text())
    assert ast.dump(ast.parse((HERE / 'original/analysis-tail.py').read_text()), include_attributes=False) == ast.dump(tail, include_attributes=False)
    receipt = {'state': 'starting', 'phase': 'ir', 'kind': 'metadata-only-ir-postguard-closure',
               'started_at': now(), 'root': str(contract.ROOT), 'host': contract.HOST,
               'closure_manifest_sha256': args.closure_manifest_sha256,
               'source_freeze_sha256': args.source_freeze_sha256,
               'measurement_seal_sha256': contract.SEAL, 'original_driver_sha256': contract.DRIVER,
               'failed_capture_sha256': contract.FAILED_CAPTURE, 'failed_launch_sha256': contract.FAILED_LAUNCH,
               'failed_status_sha256': contract.FAILED_STATUS, 'analysis_tail_ast_sha256': contract.TAIL_AST,
               'original_input_file_count': 900, 'original_sample_count': 56,
               'original_files_sha256_before': before, 'quiet_before': quiet_before,
               'repeated_raw_audits': audits, 'workload_invocations': 0, 'analysis_commands': []}
    write_new(HERE / 'started.json', receipt)
    receipt['started_receipt_sha256'] = contract.sha(HERE / 'started.json')
    status = copy.deepcopy(driver.read(driver.phase_status('ir')))
    assert status == contract.read(HERE / 'failed-capture/ir-status.json')
    # The failed document remains byte-for-byte preserved. Only its ordinary
    # status path resumes the original state machine; original launch1 is never written.
    status.pop('failed_at')
    status.pop('error')
    status['operational_closure'] = {'manifest_sha256': args.closure_manifest_sha256,
        'failed_capture_sha256': contract.FAILED_CAPTURE,
        'failed_status_sha256': contract.FAILED_STATUS, 'failed_launch_sha256': contract.FAILED_LAUNCH,
        'retained_failed_status_path': str(HERE / 'failed-capture/ir-status.json')}
    allowed = iter(('check', 'test'))

    def analyze_only(command, **kwargs):
        workflow = next(allowed)
        contract.validate_analyze_call(command, kwargs, sys.executable, workflow)
        receipt['analysis_commands'].append(command)
        return subprocess.run(command, **kwargs)

    namespace = dict(vars(driver))
    namespace.update(core=core, phase='ir', expected_seal=contract.SEAL, ref=ref,
                     runner=driver.CORE, status=status, subprocess=types.SimpleNamespace(run=analyze_only))
    failure = None
    try:
        # AST-identical statements from the original driver immediately after
        # both raw audits. This contains both original quiet checks, fixed
        # analyses, original gate(), input verification, and final status write.
        exec(compile(tail, str(script), 'exec'), namespace)
        assert next(allowed, None) is None and len(receipt['analysis_commands']) == 2
        assert status['state'] == 'complete'
        assert legacy_files() == set(capture['files']) | contract.ANALYSES
        receipt['state'] = 'complete'
    except BaseException as error:
        # Preserve the original driver's failure semantics without discarding
        # the first failure or any newly written metadata from this attempt.
        status.update(state='failed', failed_at=core.utc_now(), error=repr(error))
        core.atomic_json(driver.phase_status('ir'), status)
        receipt.update(state='failed', error=repr(error))
        failure = error
    finally:
        try:
            after = contract.original_hashes(contract.ROOT, capture, allow_status_update=True)
            driver.verify_assets()
            driver.verify_seal(contract.SEAL)
            contract.verify_manifest(HERE, args.closure_manifest_sha256)
            assert contract.sha(HERE / 'source-freeze.json') == args.source_freeze_sha256
            receipt.update(original_files_sha256_after=after, original_raw_bytes_preserved=True,
                           final_status_sha256=contract.sha(driver.phase_status('ir')),
                           analysis_files_sha256={name: contract.sha(contract.ROOT / name)
                               for name in sorted(contract.ANALYSES) if (contract.ROOT / name).exists()})
        except BaseException as error:
            receipt.update(state='failed', preservation_error=repr(error), original_raw_bytes_preserved=False)
            status.update(state='failed', failed_at=core.utc_now(), error='Closure preservation check failed: ' + repr(error))
            core.atomic_json(driver.phase_status('ir'), status)
            failure = failure or error
        receipt['finished_at'] = now()
        write_new(HERE / 'finalization.json', receipt)
    if failure is not None:
        raise failure
    print(json.dumps({'state': 'complete', 'metadata_only': True, 'sample_count_unchanged': 56,
                      'finalization_sha256': contract.sha(HERE / 'finalization.json')}))


if __name__ == '__main__':
    main()
