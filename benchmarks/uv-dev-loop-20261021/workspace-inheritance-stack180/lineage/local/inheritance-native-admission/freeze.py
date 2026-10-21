#!/usr/bin/env python3
"""Run five pure checks and seal the source-only capture package once."""
import ast
import copy
import datetime
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common
from review_boundary import source_boundary


def main():
    common.need(not (HERE / 'source-freeze.json').exists() and not (HERE / 'source-checks.json').exists(), 'freeze is single-use')
    status = {'state': 'failed', 'phase': 'native', 'seal_sha256': common.SEAL, 'variants': common.VARIANTS,
              'integrity_complete': [], 'completed': [], 'error': repr(AssertionError(common.BUSY)),
              'started_at': '2026-10-21T16:18:14+00:00', 'failed_at': '2026-10-21T16:18:15+00:00'}
    files = {name: ('a' * 64) for name in common.prerequisite_paths()}
    files[common.ROOT + '/results/ir-status.json'] = common.IR_STATUS
    prerequisite = {'state': 'passed', 'seal_sha256': common.SEAL, 'verified_at': '2026-10-21T16:18:13+00:00', 'files': files}
    closed = {'files': {name.removeprefix(common.ROOT + '/'): digest for name, digest in files.items()}}
    absent = {name: {'lexists': False, 'symlink': None} for name in common.absent_paths()}
    common.boundary(status, prerequisite, absent, closed)
    results = ['accepts exact synthetic zero-work boundary']
    for mutation, label in (
        (lambda value: value[0].update(workflow='check'), 'rejects an entered workflow'),
        (lambda value: value[0].update(completed=[{}]), 'rejects any completed observation'),
        (lambda value: value[2]['targets/native-check'].update(lexists=True), 'rejects even an existing empty native target'),
    ):
        values = copy.deepcopy([status, prerequisite, absent, closed])
        mutation(values)
        try:
            common.boundary(*values)
        except ValueError:
            results.append(label)
        else:
            raise ValueError(label + ' did not fail closed')
    proof = source_boundary()
    results.append('actual frozen driver/traceback/preflight AST boundary matches')
    for path in HERE.rglob('*.py'):
        ast.parse(path.read_text(), filename=str(path))
    ast.parse((HERE / 'common.py').read_text() + '\n' + (HERE / 'capture_remote.py').read_text())
    common.write(HERE / 'source-checks.json', {'status': 'passed', 'checks': results, 'source_boundary': proof,
                 'host_actions': False, 'cargo_calls': 0, 'statistics_computed': False})
    common.write(HERE / 'source-freeze.json', {
        'operation': 'read-only-capture-and-review-native-zero-work-admission',
        'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'files': {str(path.relative_to(HERE)): common.record(path) for path in sorted(HERE.rglob('*')) if path.is_file()},
        'scope': 'Bounded capture and non-statistical boundary proof only; no recovery or benchmark driver change.'})
    digest = common.sha(HERE / 'source-freeze.json')
    frozen = common.verify_sources(HERE, digest)
    print(__import__('json').dumps({'source_freeze_sha256': digest, 'files': len(frozen['files']), 'pure_checks': len(results)}, indent=2))


if __name__ == '__main__':
    main()
