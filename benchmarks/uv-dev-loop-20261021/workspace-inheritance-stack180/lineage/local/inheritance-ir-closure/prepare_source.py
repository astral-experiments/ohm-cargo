#!/usr/bin/env python3
"""Freeze this local closure package without host work or performance analysis."""
import ast
import datetime
import difflib
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'reviewer'))
import closure_contract as contract
from closure_binding import verify_failed_capture


def write(name, value):
    with (HERE / name).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False);stream.write('\n')


def main():
    assert not (HERE / 'source-freeze.json').exists()
    assert not (HERE / 'launch-finalize.json').exists()
    assert contract.sha(HERE / 'closure_contract.py') == contract.sha(HERE / 'reviewer/closure_contract.py')
    assert contract.sha(HERE / 'original/driver.py') == contract.DRIVER
    assert contract.sha(HERE / 'original/source-freeze.json') == contract.FREEZE
    capture = verify_failed_capture(HERE.parent / 'inheritance-measurement')
    assert capture['files'][contract.STATUS_PATH] == contract.FAILED_STATUS
    tail = contract.original_tail((HERE / 'original/driver.py').read_text())
    assert ast.dump(tail, include_attributes=False) == ast.dump(ast.parse((HERE / 'original/analysis-tail.py').read_text()), include_attributes=False)
    py_files = sorted(p for p in HERE.rglob('*.py') if p.is_file())
    for path in py_files:ast.parse(path.read_text(), filename=str(path))
    for name in ('run_finalize.py', 'collect_final.py'):
        tree = ast.parse((HERE / name).read_text())
        remote = [node.value.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == 'remote' for target in node.targets)
                  and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)]
        assert len(remote) == 1
        ast.parse(remote[0], filename=name + ':embedded')
    test_text = (HERE / 'pure-tests.stderr').read_text()
    assert 'Ran 16 tests' in test_text and test_text.endswith('OK\n')
    assert not (HERE / 'pure-tests.stdout').read_bytes()
    write('pure-checks.json', {'status': 'passed', 'tests': 16,
          'test_source_sha256': contract.sha(HERE / 'test_closure.py'),
          'contract_sha256': contract.sha(HERE / 'closure_contract.py'),
          'stdout_sha256': contract.sha(HERE / 'pure-tests.stdout'),
          'stderr_sha256': contract.sha(HERE / 'pure-tests.stderr'),
          'python_sources_parsed': len(py_files), 'embedded_sources_parsed': 2,
          'failed_capture_files_verified': 477, 'source_only': True,
          'host_actions': 0, 'cargo_invocations': 0, 'real_statistics_computed': False})
    write('tail-identity.json', {'original_driver_sha256': contract.DRIVER,
          'tail_ast_sha256': contract.TAIL_AST, 'statement_count': 7,
          'retained_original_quiet_checks': 2,
          'analysis_commands': [contract.analyze_command('/usr/bin/python3', name) for name in ('check', 'test')],
          'raw_audits_repeated_before_analysis': ['check', 'test'],
          'original_metric_and_gate_functions_unchanged': True})
    for name, previous, current in (
        ('collector.diff', HERE / 'original/collect.py', HERE / 'collect_final.py'),
        ('reviewer.diff', None, None)):
        if previous:
            diff = difflib.unified_diff(previous.read_text().splitlines(True), current.read_text().splitlines(True),
                    fromfile='original/collect.py', tofile='collect_final.py')
            (HERE / name).write_text(''.join(diff))
        else:
            parts = []
            for filename in ('evidence.py', 'review.py'):
                parts.extend(difflib.unified_diff((HERE / 'original/reviewer' / filename).read_text().splitlines(True),
                    (HERE / 'reviewer' / filename).read_text().splitlines(True), fromfile='original/' + filename, tofile='reviewer/' + filename))
            (HERE / name).write_text(''.join(parts))
    payload = ['finalize.py', 'closure_contract.py', 'original/driver.py', 'original/analysis-tail.py', 'original/source-freeze.json']
    payload += ['failed-capture/' + name for name in ('transfer-manifest.json', 'receipt.json', 'transport.json',
                'ir-status.json', 'launch-ir.json', 'launch-ir.stdout', 'launch-ir.stderr', 'measurement-seal.json')]
    write('closure-manifest.json', {'schema': 1, 'kind': 'metadata-only-ir-postguard-closure',
          'root': str(contract.ROOT), 'host': contract.HOST, 'remote_directory': contract.PREFIX,
          'measurement_seal_sha256': contract.SEAL, 'original_input_files': 900,
          'original_driver_sha256': contract.DRIVER, 'original_source_freeze_sha256': contract.FREEZE,
          'failed_capture_sha256': contract.FAILED_CAPTURE, 'failed_capture_files': 477,
          'original_sample_count': 56, 'analysis_tail_ast_sha256': contract.TAIL_AST,
          'only_mutable_original_path': contract.STATUS_PATH, 'new_analysis_files': sorted(contract.ANALYSES),
          'files': {name: contract.sha(HERE / name) for name in sorted(payload)},
          'scope': 'Close only the original post-audit metadata tail; no Cargo, warmup, sampling, sample changes, or metric/gate changes.'})
    closure_sha = contract.sha(HERE / 'closure-manifest.json')
    contract.verify_manifest(HERE, closure_sha)
    write('reviewer/closure-binding.json', {'closure_manifest_sha256': closure_sha,
          'failed_capture_sha256': contract.FAILED_CAPTURE, 'original_reviewer_source_freeze_sha256': contract.sha(HERE / 'original/reviewer-source-freeze.json'),
          'collection': 'ir-closed-postguard', 'failed_collection': 'ir-failed-postguard'})
    reviewer_files = sorted(p for p in (HERE / 'reviewer').iterdir() if p.is_file())
    write('reviewer/source-freeze.json', {'files': {p.name: contract.sha(p) for p in reviewer_files},
          'original_reviewer_source_freeze_sha256': contract.sha(HERE / 'original/reviewer-source-freeze.json'),
          'closure_manifest_sha256': closure_sha,
          'scope': 'Exact operational closure lineage and chronology adaptation; unchanged raw/metric/statistical implementation.'})
    all_files = sorted(p for p in HERE.rglob('*') if p.is_file())
    assert all(not p.is_symlink() and '__pycache__' not in p.parts for p in all_files)
    write('source-freeze.json', {'schema': 1, 'prepared_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'status': 'frozen-for-review-unexecuted', 'files': {str(p.relative_to(HERE)): contract.sha(p) for p in all_files},
          'measurement_seal_sha256': contract.SEAL, 'failed_capture_sha256': contract.FAILED_CAPTURE,
          'closure_manifest_sha256': closure_sha, 'pure_tests': 16,
          'host_actions_at_freeze': 0, 'real_statistics_computed_at_freeze': False})
    print(json.dumps({'source_freeze_sha256': contract.sha(HERE / 'source-freeze.json'),
          'closure_manifest_sha256': closure_sha,
          'reviewer_source_freeze_sha256': contract.sha(HERE / 'reviewer/source-freeze.json'),
          'files': len(all_files), 'capsule_files': len(payload), 'pure_tests': 16}, indent=2))


if __name__ == '__main__':main()
