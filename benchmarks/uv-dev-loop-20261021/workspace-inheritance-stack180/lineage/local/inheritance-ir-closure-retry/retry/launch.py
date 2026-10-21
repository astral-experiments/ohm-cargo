#!/usr/bin/env python3
"""One reviewed retry after proving the first closure attempt never staged."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contract


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


ABSENCE_PROBE = r'''
import datetime,hashlib,json,os,socket
from pathlib import Path
root=Path('/tmp/ohm-hillclimb-20261021-inheritance-measurement')
def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
assert socket.gethostname()=='charlie-oss-2' and os.getuid()==1000 and Path('/').stat().st_uid==0
assert root.resolve()==root and root.stat().st_uid==1000
assert sha(root/'controller/driver.py')=='1585116beaab26655de1e86459feb030ebdd31e636a613991241018ace5f3ef3'
assert sha(root/'controller/measurement-seal.json')=='b6e765057417644e62cf7cadc4994a05172077f8c9a26bfe6343e6ad377e48ff'
assert sha(root/'results/ir-status.json')=='f3199c1c5ee27609f56874fda658e651e1bbe174d10ea194584c2d5426f5c868'
names=['closures/ir-postguard']+[f'results/ir-{workflow}/{name}' for workflow in ('check','test')
 for name in ('analysis.json','analysis-stdout.json','gate.json')]
presence={name:os.path.lexists(root/name) for name in names}
assert not any(presence.values()),presence
assert not os.path.lexists(root/'results/native-status.json')
print(json.dumps({'state':'passed','scope':'read-only pre-staging absence proof',
 'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'host':socket.gethostname(),'uid':os.getuid(),'root':str(root),
 'measurement_seal_sha256':sha(root/'controller/measurement-seal.json'),
 'driver_sha256':sha(root/'controller/driver.py'),'ir_failed_status_sha256':sha(root/'results/ir-status.json'),
 'paths_lexist':presence,'native_status_lexists':False},sort_keys=True))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retry-source-freeze-sha256', required=True)
    args = parser.parse_args()
    contract.verify_controls(args.retry_source_freeze_sha256)
    contract.load_original_binding().verify_failed_capture(contract.CONTROLS)
    for path in ([HERE / name for name in ('attempt-started.json', 'attempt.json', 'absence.stdout', 'absence.stderr', 'launcher.stdout', 'launcher.stderr')]
                 + [contract.PACKAGE / ('launch-finalize.' + suffix) for suffix in ('json', 'stdout', 'stderr')]):
        contract.require(not path.exists() and not path.is_symlink(), 'single-use retry artifact already exists: ' + str(path))
    receipt = {'operation': 'single-prestaging-closure-retry', 'state': 'starting', 'started_at': now(),
               'retry_source_freeze_sha256': args.retry_source_freeze_sha256,
               'original_closure_source_freeze_sha256': contract.ORIGINAL_FREEZE,
               'failed_closure_launch_sha256': contract.FAILED_LAUNCH['launch-finalize.json'], 'retained_files': {}}
    # This exclusive file is the local one-shot lock; a competing invocation
    # stops before its try/finally and cannot replace this attempt's receipt.
    contract.write_new(HERE / 'attempt-started.json', receipt)
    try:
        command = [contract.SSH, contract.HOST, '--', '/usr/bin/env', '-u', 'PYTHONPATH', '-u', 'PYTHONHOME',
                   '-u', 'PYTHONUSERBASE', '-u', 'VIRTUAL_ENV', '/usr/bin/python3', '-I', '-B', '-c', ABSENCE_PROBE]
        with (HERE / 'absence.stdout').open('xb') as stdout, (HERE / 'absence.stderr').open('xb') as stderr:
            probe = subprocess.run(command, stdout=stdout, stderr=stderr)
        receipt['absence_probe_returncode'] = probe.returncode
        contract.require(probe.returncode == 0, 'absence proof failed; do not stage or retry automatically')
        contract.verify_absence_proof(contract.read(HERE / 'absence.stdout'))
        receipt['absence_proof_sha256'] = contract.sha(HERE / 'absence.stdout')
        contract.verify_controls(args.retry_source_freeze_sha256)
        # Byte-identical original launcher. Its unchanged remote quiet guard,
        # exclusive mkdir, full raw/input verification, and exact tail remain.
        with (HERE / 'launcher.stdout').open('xb') as stdout, (HERE / 'launcher.stderr').open('xb') as stderr:
            result = subprocess.run(['/usr/bin/python3', '-I', '-B', str(contract.PACKAGE / 'run_finalize.py'),
                                     '--source-freeze-sha256', contract.ORIGINAL_FREEZE], stdout=stdout, stderr=stderr)
        receipt['returncode'] = result.returncode
        contract.require(result.returncode == 0, 'original closure launcher failed; retain all bytes and stop')
        receipt['successful_closure_launch_sha256'] = contract.sha(contract.PACKAGE / 'launch-finalize.json')
        receipt['state'] = 'complete'
    except BaseException as error:
        receipt.update(state='failed', error=repr(error))
        raise
    finally:
        paths = [HERE / name for name in ('attempt-started.json', 'absence.stdout', 'absence.stderr', 'launcher.stdout', 'launcher.stderr')]
        paths += [contract.PACKAGE / ('launch-finalize.' + suffix) for suffix in ('json', 'stdout', 'stderr')]
        receipt['retained_files'] = {str(path.relative_to(contract.PACKAGE)): contract.record(path)
                                     for path in paths if path.is_file() and not path.is_symlink()}
        try:
            contract.verify_controls(args.retry_source_freeze_sha256)
            contract.load_original_binding().verify_failed_capture(contract.CONTROLS)
            receipt['original_sources_failure_and_raw_capture_preserved'] = True
        except BaseException as error:
            receipt.update(state='failed', preservation_error=repr(error), original_sources_failure_and_raw_capture_preserved=False)
        receipt['finished_at'] = now()
        contract.write_new(HERE / 'attempt.json', receipt)
    contract.verify_attempt(args.retry_source_freeze_sha256, complete=True)
    print(json.dumps({'state': 'complete', 'attempt_sha256': contract.sha(HERE / 'attempt.json'),
                      'original_failed_launch_preserved': True, 'new_sampling': False}, indent=2))


if __name__ == '__main__':
    main()
