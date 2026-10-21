#!/usr/bin/env python3
"""Independent source/hash/synthetic review; never execute remote controls or real analysis."""
import ast
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

WORK = Path(__file__).resolve().parents[1]
PACKAGE = WORK / 'inheritance-ir-closure'
CONTROLS = WORK / 'inheritance-measurement'
OUTPUT = Path(__file__).resolve().parent / 'closure-source-review'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    assert path.name not in ('samples.json', 'subruns.json', 'analysis.json', 'gate.json')
    return json.loads(path.read_text())


def regular(root, name):
    relative = Path(name)
    assert name and not relative.is_absolute() and '..' not in relative.parts and str(relative) == name
    path = root / relative
    assert path.is_file() and not path.is_symlink() and path.resolve() == path
    return path


def functions(path, *, class_name=None, exclude=()):
    module = ast.parse(path.read_text())
    body = module.body if class_name is None else next(node.body for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == class_name)
    return {node.name: ast.dump(node, include_attributes=False) for node in body
            if isinstance(node, ast.FunctionDef) and node.name not in exclude}


def main():
    assert not OUTPUT.exists()
    OUTPUT.mkdir()
    freeze_sha = sha(PACKAGE / 'source-freeze.json')
    assert freeze_sha.startswith('befbcd80')
    freeze = read(PACKAGE / 'source-freeze.json')
    for name, digest in freeze['files'].items():
        assert sha(regular(PACKAGE, name)) == digest, name
    capsule_sha = sha(PACKAGE / 'closure-manifest.json')
    assert capsule_sha == '87271d54298ea323702ef858034bc82595717d3893e8de23a2a7b8e6c6f83642'
    reviewer_sha = sha(PACKAGE / 'reviewer/source-freeze.json')
    assert reviewer_sha == '6788a132f081cb510a8a3cbd0ffc1b62c3ebc29dad936d47520bf74052a6ec8e'
    for name, digest in read(PACKAGE / 'reviewer/source-freeze.json')['files'].items():
        assert sha(regular(PACKAGE / 'reviewer', name)) == digest
    assert (PACKAGE / 'original/driver.py').read_bytes() == (CONTROLS / 'driver.py').read_bytes()
    assert (PACKAGE / 'original/source-freeze.json').read_bytes() == (CONTROLS / 'source-freeze.json').read_bytes()
    original_reviewer = WORK / 'inheritance-raw-review'
    for name in ('evidence.py', 'review.py', 'review_setup.py', 'statistics_review.py'):
        assert (PACKAGE / 'original/reviewer' / name).read_bytes() == (original_reviewer / name).read_bytes()
    for name in ('statistics_review.py', 'review_setup.py'):
        assert (PACKAGE / 'original/reviewer' / name).read_bytes() == (PACKAGE / 'reviewer' / name).read_bytes()
    assert functions(PACKAGE / 'original/reviewer/review.py', exclude=('main',)) == functions(PACKAGE / 'reviewer/review.py', exclude=('main',))
    assert functions(PACKAGE / 'original/reviewer/evidence.py', class_name='Evidence', exclude=('__init__',)) == functions(PACKAGE / 'reviewer/evidence.py', class_name='Evidence', exclude=('__init__',))
    driver = ast.parse((PACKAGE / 'original/driver.py').read_text())
    run = next(node for node in driver.body if isinstance(node, ast.FunctionDef) and node.name == 'run_phase')
    attempt = next(node for node in run.body if isinstance(node, ast.Try))
    assert len(attempt.body) == 8 and isinstance(attempt.body[0], ast.For)
    tail = ast.Module(body=attempt.body[1:], type_ignores=[])
    tail_ast = ast.dump(tail, include_attributes=False)
    tail_sha = hashlib.sha256(tail_ast.encode()).hexdigest()
    assert tail_sha == '3d13d0538f41f3a26ec76547ba51d2db69019daad761d608bab39ed8c3220448'
    assert tail_ast == ast.dump(ast.parse((PACKAGE / 'original/analysis-tail.py').read_text()), include_attributes=False)
    calls = [node for node in ast.walk(tail) if isinstance(node, ast.Call)]
    assert sum(isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
               and node.func.value.id == 'ref' and node.func.attr == 'quiet' for node in calls) == 2
    assert not any(isinstance(node.func, ast.Name) and node.func.id in
                   ('preflight', 'run_phase', 'native_prerequisite', 'run_command', 'install_variant') for node in calls)
    parsed = 0
    for name in freeze['files']:
        if name.endswith('.py'):
            ast.parse((PACKAGE / name).read_text(), filename=name)
            parsed += 1
    # Authenticate raw timing/profile bytes strictly as opaque streams. Never
    # parse their values or call the finalizer, collector or statistical reviewer.
    capture = CONTROLS / 'collections/ir-failed-postguard'
    assert sha(capture / 'transfer-manifest.json') == 'b5a0b1edb496ffa0749ba6e2198606c32d83c22a8d79340ca9dc3d4b0ce95ba8'
    manifest = read(capture / 'transfer-manifest.json')
    assert len(manifest['files']) == 477 and manifest['terminal_state'] == 'failed'
    assert not any(name.endswith(('/analysis.json', '/analysis-stdout.json', '/gate.json')) for name in manifest['files'])
    for name, digest in manifest['files'].items():
        assert sha(regular(capture / 'remote', name)) == digest, name
    transport = read(capture / 'transport.json')
    assert transport['returncode'] == 0 and sha(capture / 'payload.tar') == transport['archive_sha256']
    assert sha(capture / 'transfer.stderr') == transport['stderr_sha256']
    seen = set()
    with tarfile.open(capture / 'payload.tar', 'r:') as archive:
        for item in archive:
            assert item.isfile() and not item.issym() and not item.islnk() and item.name not in seen
            seen.add(item.name)
            if item.name == 'transfer-manifest.json':
                assert archive.extractfile(item).read() == (capture / item.name).read_bytes()
            else:
                assert item.name.startswith('remote/') and item.name[7:] in manifest['files']
                with archive.extractfile(item) as stream:
                    assert hashlib.file_digest(stream, 'sha256').hexdigest() == manifest['files'][item.name[7:]]
                assert item.size == (capture / item.name).stat().st_size
    assert seen == {'transfer-manifest.json'} | {'remote/' + name for name in manifest['files']}
    launch = read(CONTROLS / 'launch-ir.json')
    assert launch['returncode'] == 1 and sha(CONTROLS / 'launch-ir.json') == '765266538d3c45b28fb0caa9bfbf3055bd0737ec5a52031ca69222813c64c7f8'
    for suffix in ('json', 'stdout', 'stderr'):
        assert (CONTROLS / ('launch-ir.' + suffix)).read_bytes() == (PACKAGE / ('failed-capture/launch-ir.' + suffix)).read_bytes()
    with (OUTPUT / 'synthetic.stdout').open('x') as stdout, (OUTPUT / 'synthetic.stderr').open('x') as stderr:
        result = subprocess.run(['/usr/bin/python3', '-I', '-B', str(PACKAGE / 'test_closure.py')], stdout=stdout, stderr=stderr)
    assert result.returncode == 0
    for name, digest in freeze['files'].items():
        assert sha(regular(PACKAGE, name)) == digest, 'source changed during review: ' + name
    assert sha(PACKAGE / 'source-freeze.json') == freeze_sha
    report = {
        'status': 'passed', 'reviewed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'review_source_sha256': sha(Path(__file__)), 'source_freeze_sha256': freeze_sha,
        'closure_manifest_sha256': capsule_sha, 'reviewer_source_freeze_sha256': reviewer_sha,
        'source_files_verified': len(freeze['files']), 'python_sources_parsed': parsed,
        'raw_capture_files_and_archive_members_verified': 477,
        'failed_capture_sha256': sha(capture / 'transfer-manifest.json'),
        'failed_archive_sha256': transport['archive_sha256'], 'original_failed_launch_sha256': sha(CONTROLS / 'launch-ir.json'),
        'original_launch_returncode': 1, 'analysis_tail_ast_sha256': tail_sha,
        'original_tail_statements': 7, 'unchanged_original_tail_quiet_calls': 2,
        'unchanged_raw_and_statistical_functions': True,
        'synthetic_tests': {'count': 16, 'returncode': result.returncode,
                            'stdout_sha256': sha(OUTPUT / 'synthetic.stdout'), 'stderr_sha256': sha(OUTPUT / 'synthetic.stderr')},
        'findings': [],
        'review_conclusions': [
            'Exact original seven-statement post-audit tail; sample/preflight loop is excluded and direct subprocess calls are restricted to the two unchanged analyses.',
            'Original driver, 900-input measurement seal, plans, counts, seeds, gates, occupancy guard and production pair remain unchanged.',
            'All 477 captured bytes are bound before and after, with only the ordinary IR status path allowed to change; original failed status and launch1 remain independently retained.',
            'Both raw workflows are re-audited before the unchanged effects; quiet failure still rejects completion and no automatic retry is added.',
            'Collector/reviewer adaptations join closure0 to launch1 and adjust collection/chronology/native lineage only; raw/metric/statistical implementation is unchanged.',
        ],
        'scope': 'Source, byte hashes and synthetic guards only. No host access, Cargo, real effects, finalizer or statistical reviewer execution.',
        'host_actions': 0, 'cargo_invocations': 0, 'real_statistics_computed': False, 'raw_timing_values_parsed': False,
    }
    with (OUTPUT / 'review.json').open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({key: report[key] for key in ('status', 'source_freeze_sha256', 'closure_manifest_sha256',
                      'reviewer_source_freeze_sha256', 'source_files_verified', 'raw_capture_files_and_archive_members_verified')}
                     | {'review_sha256': sha(OUTPUT / 'review.json')}, indent=2))


if __name__ == '__main__':
    main()
