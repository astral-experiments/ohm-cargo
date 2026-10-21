#!/usr/bin/env python3
"""Validate frozen production CLIs using existing, byte-identical tests."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys

ROOT = Path('/tmp/ohm-hillclimb-20261021/path-cache-validation')
BAKED = Path('/home/dev-user/Documents/Codex/2026-10-20/i-want-you-to-hillclimb-on')
OHM = Path('/tmp/ohm-hillclimb-20261021/confirmation-path-cache/ohm')
CLI = BAKED / 'work/cargo-build/release/cargo'
HARNESS = BAKED / 'work/cargo-build/release/deps/testsuite-af6fdb42b18789ae'
HASHES = {'candidate': 'c060facdbaae756453968d6eaef1c5ab71c127d15c329a8453e260ef3064c583',
          'baseline': '63495905e7b0b11ad99fa4c2c2674e43657b9902a2e3142ef735fd83efa44cf8'}
EXCLUDED = {
    'build_dir::shared_registry_cache_preserves_explicit_empty_loader_paths',
    'build_dir::shared_registry_cache_reuses_built_dependencies_with_an_unset_loader_path',
    'build_dir::unset_loader_path_adds_procedural_macro_library_directories',
}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def main():
    variant = sys.argv[1]
    assert variant in HASHES
    assert ROOT.resolve() == ROOT and BAKED.resolve() == BAKED
    ownership = json.loads((BAKED / '.ohm-validation-owner.json').read_text())
    assert ownership['evidence_root'] == str(ROOT) and ownership['uid'] == os.getuid() == 1000
    output = ROOT / ('attempt-' + variant)
    output.mkdir(exist_ok=False)
    binary = ROOT / 'binaries' / ('cargo-' + variant)
    inputs = json.loads((ROOT / 'inputs.json').read_text())
    for name, expected in inputs['files'].items():
        assert sha(ROOT / name) == expected, name
    assert sha(binary) == HASHES[variant]
    assert sha(HARNESS) == '6415ee68be80518f701a6e4d0b45c1ef76bab599af203625f06b7fa4ac696182'
    tests = json.loads((ROOT / 'tests.json').read_text())
    assert len(tests) == len(set(tests)) == 97 and not EXCLUDED.intersection(tests)
    if variant == 'baseline':
        previous = json.loads((ROOT / 'attempt-candidate/report.json').read_text())
        tests = previous['failed_tests']
        assert tests, 'baseline diagnosis only runs after a candidate failure'
    environment = os.environ.copy()
    removed = [k for k in environment if k.startswith(('CARGO_', 'RUST', '__CARGO_', 'LD_', 'DYLD_'))]
    for key in removed:
        environment.pop(key, None)
    environment.pop('SNAPSHOTS', None)
    overrides = {
        'PATH': str(CLI.parent) + ':' + str(OHM / 'bin') + ':/usr/bin:/bin',
        'LD_LIBRARY_PATH': str(OHM / 'lib'),
        'CARGO_HOME': str(ROOT / 'cargo-home'),
        'CARGO_TARGET_DIR': str(BAKED / 'work/cargo-build'),
        'CARGO_MANIFEST_DIR': str(BAKED / 'work/ohm-cargo'),
        'CARGO_PROFILE_RELEASE_DEBUG': '1',
        'TMPDIR': str(ROOT / 'tmp'),
        'SSL_CERT_FILE': '/etc/ssl/certs/ca-certificates.crt',
        'SSL_CERT_DIR': '/usr/lib/ssl/certs',
        'PYTHONDONTWRITEBYTECODE': '1',
    }
    environment.update(overrides)
    launcher = ('#!/bin/sh\n'
        '# Preserve each test\'s explicit Ohm defaults and nightly channel.\n'
        'case "${__CARGO_TEST_CHANNEL_OVERRIDE_DO_NOT_USE_THIS-}" in\n'
        '  stable|beta|"") export __CARGO_TEST_CHANNEL_OVERRIDE_DO_NOT_USE_THIS=dev ;;\n'
        'esac\n'
        'if [ "${__CARGO_OHM_DEFAULTS+x}" != x ]; then\n'
        '  export __CARGO_OHM_DEFAULTS=no\n'
        'fi\n'
        f'exec {shlex.quote(str(binary))} "$@"\n')
    if CLI.exists():
        assert variant == 'baseline' and CLI.read_text().startswith('#!/bin/sh\n')
        previous = json.loads((ROOT / 'attempt-candidate/report.json').read_text())
        assert sha(CLI) == previous['launcher_sha256']
        (output / 'previous-launcher.sh').write_bytes(CLI.read_bytes())
    CLI.write_text(launcher)
    CLI.chmod(0o755)
    (output / 'launcher.sh').write_text(launcher)
    command = [str(HARNESS), *tests, '--exact', '--nocapture', '--test-threads=1']
    ldd = subprocess.check_output(['/usr/bin/ldd', str(HARNESS)], text=True, env=environment)
    runtime = {str(Path(p).resolve()) for p in re.findall(r'(/\S+)\s+\(0x[0-9a-f]+\)', ldd)}
    runtime.update(str(p) for p in (OHM / 'lib').glob('librustc_driver-*.so'))
    runtime.update([str(OHM / 'bin/rustc'), str(OHM / 'bin/rustdoc'), '/etc/ssl/certs/ca-certificates.crt'])
    record = {
        'started_at': now(), 'status': 'running', 'variant': variant,
        'scope': 'Historical PR175 path-cache production binary; unchanged preexisting build_dir tests.',
        'binary_sha256': sha(binary), 'harness_sha256': sha(HARNESS),
        'harness_compiled_source_tree': 'c692e3c07d295e596b9f10eb4b1c89bb498caf68',
        'runner_sha256': sha(__file__), 'input_manifest_sha256': sha(ROOT / 'inputs.json'),
        'launcher_sha256': sha(CLI), 'launcher': launcher,
        'classic_mode': 'Restore dev only for inherited stable/beta/unset channel; preserve explicit nightly and Ohm yes/no. Default unset Ohm defaults to no.',
        'runtime_sha256': {p: sha(p) for p in sorted(runtime)},
        'harness_ldd': ldd, 'uid': os.getuid(), 'gid': os.getgid(),
        'ownership': ownership, 'environment_overrides': overrides,
        'removed_environment_names': sorted(removed), 'command': command, 'tests': tests,
        'excluded_loader_only_tests': sorted(EXCLUDED), 'failures': [],
    }
    save(output / 'report.json', record)
    version_command = ['/usr/bin/strace', '-f', '-s', '200', '-e', 'trace=execve',
                       '-o', str(output / 'cli-execve.log'), str(CLI), '-Vv']
    version = subprocess.run(version_command, env=environment, text=True, capture_output=True, check=True)
    (output / 'cli-version.txt').write_text(version.stdout)
    trace = (output / 'cli-execve.log').read_text()
    assert f'execve("{binary}"' in trace
    record['cli_version'] = version.stdout
    record['cli_execve_sha256'] = sha(output / 'cli-execve.log')
    record['cli_execve_command'] = version_command
    save(output / 'report.json', record)
    listing = subprocess.run([str(HARNESS), 'build_dir::', '--list'], env=environment,
                             text=True, capture_output=True, check=True)
    (output / 'test-list.txt').write_text(listing.stdout)
    listed = {line.removesuffix(': test') for line in listing.stdout.splitlines() if line.endswith(': test')}
    assert set(tests).issubset(listed), set(tests) - listed
    if variant == 'candidate':
        assert listed - EXCLUDED == set(tests), sorted((listed - EXCLUDED) ^ set(tests))
    record['listed_test_count'] = len(listed)
    record['ownership_paths'] = [{'path': str(p), 'uid': p.stat().st_uid, 'gid': p.stat().st_gid,
                                  'mode': oct(p.stat().st_mode & 0o7777)}
                                 for p in (ROOT, BAKED, CLI, HARNESS, binary, OHM, OHM / 'lib')]
    save(output / 'report.json', record)
    try:
        with (output / 'tests.log').open('wb') as log:
            process = subprocess.Popen(command, cwd=BAKED / 'work/ohm-cargo', env=environment,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                result = process.wait(timeout=1200)
            except BaseException:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise
        text = (output / 'tests.log').read_text(errors='replace')
        record['returncode'] = result
        record['summaries'] = re.findall(r'test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out', text)
        record['failed_tests'] = re.findall(r'^    (build_dir::\S+)$', text, re.M)
        record['test_log_sha256'] = sha(output / 'tests.log')
        assert sha(binary) == record['binary_sha256']
        assert sha(HARNESS) == record['harness_sha256']
        assert sha(CLI) == record['launcher_sha256']
        assert {p: sha(p) for p in record['runtime_sha256']} == record['runtime_sha256']
        assert len(record['summaries']) == 1
        passed, failed, ignored, measured, filtered = map(int, record['summaries'][0])
        assert passed + failed + ignored == len(tests) and measured == 0
        assert failed == len(record['failed_tests'])
        record['status'] = 'passed' if result == 0 and failed == 0 else 'failed'
    except BaseException as error:
        record['status'] = 'operational-failure'
        record['failures'].append(repr(error))
        raise
    finally:
        record['finished_at'] = now()
        record['after_sha256'] = {'binary': sha(binary), 'harness': sha(HARNESS), 'launcher': sha(CLI)}
        save(output / 'report.json', record)
    print(json.dumps({k: record.get(k) for k in ('status', 'variant', 'summaries', 'failed_tests')}, indent=2))
    return 0 if record['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
