"""Byte-preservation contract for the one approved post-audit IR closure."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path('/tmp/ohm-hillclimb-20261021-inheritance-measurement')
HOST = 'charlie-oss-2'
PREFIX = 'closures/ir-postguard'
SEAL = 'b6e765057417644e62cf7cadc4994a05172077f8c9a26bfe6343e6ad377e48ff'
DRIVER = '1585116beaab26655de1e86459feb030ebdd31e636a613991241018ace5f3ef3'
FREEZE = 'f52a57b667b0708413cb353b2af4164f11fec6a9b8e0025bab4ab8330135ff98'
DELIVERY = '9cb40f6d074706a713b60c2c1b17e4ac44bf8294f1fc3ba3973f46912a2e15ec'
FAILED_CAPTURE = 'b5a0b1edb496ffa0749ba6e2198606c32d83c22a8d79340ca9dc3d4b0ce95ba8'
FAILED_STATUS = 'f3199c1c5ee27609f56874fda658e651e1bbe174d10ea194584c2d5426f5c868'
FAILED_LAUNCH = '765266538d3c45b28fb0caa9bfbf3055bd0737ec5a52031ca69222813c64c7f8'
TAIL_AST = '3d13d0538f41f3a26ec76547ba51d2db69019daad761d608bab39ed8c3220448'
STATUS_PATH = 'results/ir-status.json'
ANALYSES = {f'results/ir-{workflow}/{name}' for workflow in ('check', 'test')
            for name in ('analysis.json', 'analysis-stdout.json', 'gate.json')}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def relative(name):
    assert isinstance(name, str)
    path = PurePosixPath(name)
    assert name and name != '.' and not path.is_absolute() and '..' not in path.parts
    assert '\\' not in name and str(path) == name
    return Path(name)


def regular(root, name):
    root = Path(root)
    path = root / relative(name)
    assert path.is_file() and not path.is_symlink() and path.resolve() == path
    return path


def verify_manifest(directory, expected):
    path = regular(directory, 'closure-manifest.json')
    assert sha(path) == expected
    value = read(path)
    assert value['schema'] == 1 and value['kind'] == 'metadata-only-ir-postguard-closure'
    assert value['root'] == str(ROOT) and value['host'] == HOST and value['remote_directory'] == PREFIX
    assert value['measurement_seal_sha256'] == SEAL and value['original_input_files'] == 900
    assert value['original_driver_sha256'] == DRIVER and value['original_source_freeze_sha256'] == FREEZE
    assert value['failed_capture_sha256'] == FAILED_CAPTURE and value['failed_capture_files'] == 477
    assert value['original_sample_count'] == 56 and value['analysis_tail_ast_sha256'] == TAIL_AST
    assert value['only_mutable_original_path'] == STATUS_PATH
    assert set(value['new_analysis_files']) == ANALYSES
    payload = {'finalize.py', 'closure_contract.py', 'original/driver.py', 'original/analysis-tail.py', 'original/source-freeze.json'}
    payload |= {'failed-capture/' + name for name in ('transfer-manifest.json', 'receipt.json', 'transport.json',
                'ir-status.json', 'launch-ir.json', 'launch-ir.stdout', 'launch-ir.stderr', 'measurement-seal.json')}
    assert set(value['files']) == payload
    for name, digest in value['files'].items():
        assert sha(regular(directory, name)) == digest, name
    capture = read(regular(directory, 'failed-capture/transfer-manifest.json'))
    assert sha(Path(directory) / 'failed-capture/transfer-manifest.json') == FAILED_CAPTURE
    assert capture['root'] == str(ROOT) and capture['phase'] == 'ir'
    assert capture['seal_sha256'] == SEAL and capture['delivery_sha256'] == DELIVERY and capture['driver_sha256'] == DRIVER
    assert capture['terminal_state'] == 'failed' and capture['qualifies'] is False
    assert len(capture['files']) == 477 and capture['files'][STATUS_PATH] == FAILED_STATUS
    assert capture['files']['controller/driver.py'] == DRIVER
    assert capture['files']['controller/source-freeze.json'] == FREEZE
    assert capture['files']['controller/measurement-seal.json'] == SEAL
    assert sha(Path(directory) / 'original/driver.py') == DRIVER
    assert sha(Path(directory) / 'original/source-freeze.json') == FREEZE
    assert not ANALYSES.intersection(capture['files'])
    failed = read(regular(directory, 'failed-capture/ir-status.json'))
    assert sha(Path(directory) / 'failed-capture/ir-status.json') == FAILED_STATUS
    assert failed['state'] == 'failed' and failed['phase'] == 'ir' and failed['seal_sha256'] == SEAL
    assert failed['integrity_complete'] == ['check', 'test'] and failed['completed'] == []
    assert 'AnsiballZ_command.py' in failed['error']
    launch = read(regular(directory, 'failed-capture/launch-ir.json'))
    assert sha(Path(directory) / 'failed-capture/launch-ir.json') == FAILED_LAUNCH
    assert launch['returncode'] == 1 and launch['operation'] == 'launch-ir'
    assert launch['host'] == HOST and launch['root'] == str(ROOT) and launch['sealed_inputs_sha256'] == SEAL
    for suffix in ('stdout', 'stderr'):
        assert sha(Path(directory) / ('failed-capture/launch-ir.' + suffix)) == launch[suffix + '_sha256']
    assert 'line 411, in run_phase' in (Path(directory) / 'failed-capture/launch-ir.stderr').read_text()
    original_seal = read(regular(directory, 'failed-capture/measurement-seal.json'))
    assert sha(Path(directory) / 'failed-capture/measurement-seal.json') == SEAL
    assert len(original_seal['file_sha256']) == 900
    return value, capture


def original_hashes(root, capture, allow_status_update=False):
    """Hash every retained original; status is the sole explicit write exception."""
    observed = {}
    for name, digest in capture['files'].items():
        observed[name] = sha(regular(root, name))
        if name != STATUS_PATH or not allow_status_update:
            assert observed[name] == digest, name
    return observed


def original_tail(source):
    module = ast.parse(source)
    function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'run_phase')
    attempt = next(node for node in function.body if isinstance(node, ast.Try))
    assert len(attempt.body) == 8 and isinstance(attempt.body[0], ast.For) and isinstance(attempt.body[1], ast.Assert)
    tail = ast.Module(body=attempt.body[1:], type_ignores=[])
    assert hashlib.sha256(ast.dump(tail, include_attributes=False).encode()).hexdigest() == TAIL_AST
    return tail


def analyze_command(python, workflow):
    assert workflow in ('check', 'test')
    return [python, '-I', '-B', str(ROOT / 'benchmark/frozen/paired.py'), 'analyze',
            str(ROOT / ('results/ir-' + workflow)), '--confidence', '.99', '--resamples', '20000',
            '--seed', '1701', '--minimum-pairs', '12']


def validate_analyze_call(command, kwargs, python, workflow):
    assert command == analyze_command(python, workflow)
    assert set(kwargs) == {'stdout', 'check'} and kwargs['check'] is True
    assert Path(kwargs['stdout'].name) == ROOT / ('results/ir-' + workflow + '/analysis-stdout.json')
