"""Pure lineage checks for one retry after an authenticated pre-staging failure."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
ORIGINAL = PACKAGE.parent / 'inheritance-ir-closure'
CONTROLS = PACKAGE.parent / 'inheritance-measurement'
ROOT = '/tmp/ohm-hillclimb-20261021-inheritance-measurement'
HOST = 'charlie-oss-2'
ORIGINAL_FREEZE = 'befbcd80ecdbfa09a14a39faf11891a01b65cb544522417fbbc29b3aa4352d10'
CAPSULE = '87271d54298ea323702ef858034bc82595717d3893e8de23a2a7b8e6c6f83642'
MEASUREMENT_SEAL = 'b6e765057417644e62cf7cadc4994a05172077f8c9a26bfe6343e6ad377e48ff'
DRIVER = '1585116beaab26655de1e86459feb030ebdd31e636a613991241018ace5f3ef3'
IR_FAILED_STATUS = 'f3199c1c5ee27609f56874fda658e651e1bbe174d10ea194584c2d5426f5c868'
IR_FAILED_CAPTURE = 'b5a0b1edb496ffa0749ba6e2198606c32d83c22a8d79340ca9dc3d4b0ce95ba8'
FAILED_LAUNCH = {
    'launch-finalize.json': '49ae8af6b1e18d95b981c56b449cde794114d3bf1e97e1aab2b07933a2c4ee18',
    'launch-finalize.stdout': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'launch-finalize.stderr': '2b7360d0f2efd7828e5e281ad1ecef033a594f5bc6b2a40b9e7c13b996fad345',
}
ABSENT = ['closures/ir-postguard'] + [f'results/ir-{workflow}/{name}' for workflow in ('check', 'test')
          for name in ('analysis.json', 'analysis-stdout.json', 'gate.json')]
SSH = '/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def relative(name):
    path = PurePosixPath(name)
    require(bool(name) and name != '.' and not path.is_absolute() and '..' not in path.parts
            and '\\' not in name and str(path) == name, 'unsafe relative path')
    return path


def regular(root, name):
    path = Path(root) / relative(name)
    require(path.is_file() and not path.is_symlink() and path.resolve() == path, 'noncanonical file: ' + str(path))
    return path


def record(path):
    path = Path(path)
    return {'sha256': sha(path), 'size': path.stat().st_size}


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def verify_controls(expected_retry_freeze):
    require(sha(HERE / 'source-freeze.json') == expected_retry_freeze, 'retry source freeze differs')
    frozen = read(HERE / 'source-freeze.json')
    require(frozen['operation'] == 'single-prestaging-closure-retry'
            and frozen['original_closure_source_freeze_sha256'] == ORIGINAL_FREEZE
            and frozen['original_capsule_sha256'] == CAPSULE
            and frozen['failed_closure_launch_sha256'] == FAILED_LAUNCH['launch-finalize.json'], 'retry source identity differs')
    for name, digest in frozen['files'].items():
        require(sha(regular(PACKAGE, name)) == digest, 'retry source/history changed: ' + name)
    require(sha(PACKAGE / 'source-freeze.json') == sha(ORIGINAL / 'source-freeze.json') == ORIGINAL_FREEZE,
            'original closure source freeze changed')
    original = read(PACKAGE / 'source-freeze.json')
    for name, digest in original['files'].items():
        require(sha(regular(PACKAGE, name)) == sha(regular(ORIGINAL, name)) == digest,
                'original/copy closure source differs: ' + name)
    for name, digest in FAILED_LAUNCH.items():
        require(sha(regular(ORIGINAL, name)) == sha(regular(HERE / 'history', name)) == digest,
                'first failed closure launch changed: ' + name)
    failed = read(HERE / 'history/launch-finalize.json')
    require(failed['returncode'] == 1 and failed['operation'] == 'finalize-ir-postguard'
            and failed['source_freeze_sha256'] == ORIGINAL_FREEZE
            and failed['closure_manifest_sha256'] == CAPSULE
            and failed['measurement_seal_sha256'] == MEASUREMENT_SEAL
            and failed['host'] == HOST and failed['root'] == ROOT, 'different original closure failure')
    require(failed['stdout_sha256'] == FAILED_LAUNCH['launch-finalize.stdout']
            and failed['stderr_sha256'] == FAILED_LAUNCH['launch-finalize.stderr'], 'first failure streams differ')
    error = (HERE / 'history/launch-finalize.stderr').read_text()
    require('File "<string>", line 15, in <module>' in error
            and 'controller/occupancy.py", line 36, in require_quiet' in error
            and "'pid': 1058095" in error and "'name': 'uv-main'" in error
            and '/home/dev-user/Documents/Codex/uv-current-main-bench-20261021/bin/uv-main' in error,
            'failure was not the authenticated pre-staging quiet guard')
    return frozen


def verify_absence_proof(proof):
    require(proof['state'] == 'passed' and proof['scope'] == 'read-only pre-staging absence proof'
            and proof['host'] == HOST and proof['uid'] == 1000 and proof['root'] == ROOT
            and proof['measurement_seal_sha256'] == MEASUREMENT_SEAL
            and proof['driver_sha256'] == DRIVER and proof['ir_failed_status_sha256'] == IR_FAILED_STATUS,
            'absence proof identity differs')
    require(proof['paths_lexist'] == {name: False for name in ABSENT}
            and proof['native_status_lexists'] is False, 'capsule/analysis/native boundary was crossed')


def verify_attempt(expected_retry_freeze, *, complete):
    verify_controls(expected_retry_freeze)
    attempt = read(HERE / 'attempt.json')
    require(attempt['retry_source_freeze_sha256'] == expected_retry_freeze
            and attempt['original_closure_source_freeze_sha256'] == ORIGINAL_FREEZE
            and attempt['failed_closure_launch_sha256'] == FAILED_LAUNCH['launch-finalize.json']
            and attempt['operation'] == 'single-prestaging-closure-retry', 'retry attempt lineage differs')
    for name, expected in attempt['retained_files'].items():
        require(record(regular(PACKAGE, name)) == expected, 'retry attempt byte changed: ' + name)
    if complete:
        require(attempt['state'] == 'complete' and attempt['returncode'] == 0, 'retry did not complete')
        require(attempt['original_sources_failure_and_raw_capture_preserved'] is True, 'retry preservation did not pass')
        require(set(attempt['retained_files']) == {'retry/attempt-started.json', 'retry/absence.stdout', 'retry/absence.stderr',
                'retry/launcher.stdout', 'retry/launcher.stderr', 'launch-finalize.json',
                'launch-finalize.stdout', 'launch-finalize.stderr'}, 'retry attempt stream set differs')
        started = read(HERE / 'attempt-started.json')
        require(started['state'] == 'starting' and started['retained_files'] == {}
                and all(attempt[key] == value for key, value in started.items() if key not in ('state', 'retained_files')),
                'retry starting receipt differs')
        proof = read(HERE / 'absence.stdout')
        verify_absence_proof(proof)
        require(attempt['absence_probe_returncode'] == 0 and attempt['absence_proof_sha256'] == sha(HERE / 'absence.stdout'),
                'absence probe was not successful/bound')
        launch = read(PACKAGE / 'launch-finalize.json')
        require(launch['returncode'] == 0 and launch['source_freeze_sha256'] == ORIGINAL_FREEZE
                and launch['closure_manifest_sha256'] == CAPSULE
                and launch['measurement_seal_sha256'] == MEASUREMENT_SEAL
                and launch['host'] == HOST and launch['root'] == ROOT
                and launch['failed_capture_sha256'] == IR_FAILED_CAPTURE, 'new closure launch differs')
        for suffix in ('stdout', 'stderr'):
            require(launch[suffix + '_sha256'] == sha(PACKAGE / ('launch-finalize.' + suffix)), 'new launch stream differs')
        require(attempt['successful_closure_launch_sha256'] == sha(PACKAGE / 'launch-finalize.json'), 'new closure launch join differs')
        require(read(HERE / 'history/launch-finalize.json')['finished_at'] <= attempt['started_at']
                <= proof['observed_at'] <= launch['started_at'] <= launch['finished_at'] <= attempt['finished_at'], 'retry chronology differs')
    return attempt


def load_original_binding():
    sys.path.insert(0, str(PACKAGE / 'reviewer'))
    spec = importlib.util.spec_from_file_location('inheritance_original_closure_binding', PACKAGE / 'reviewer/closure_binding.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
