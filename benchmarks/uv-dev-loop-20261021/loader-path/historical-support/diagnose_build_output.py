#!/usr/bin/env python3
"""Untimed, isolated freshness diagnostics for both staged Cargo variants."""
from pathlib import Path
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage
ROOT = stage.ROOT
sys.path.insert(0, str(ROOT / 'benchmark/frozen'))
import paired

BUILDERS = {'cargo', 'rustc', 'rustdoc', 'rust-lld', 'ld.lld', 'cc', 'cc1', 'cc1plus', 'clang', 'gcc', 'ninja', 'make', 'cmake', 'valgrind', 'perf'}

def quiet_snapshot():
    rows = subprocess.check_output(['ps', '-eo', 'pid=,comm=,pcpu=,pmem=', '--sort=-pcpu'], text=True).splitlines()
    competing = [row for row in rows if row.split()[1] in BUILDERS]
    if competing:
        raise RuntimeError(f'Competing build/profiler processes: {competing}')
    return {'process_snapshot': rows[:20], 'load_average': list(os.getloadavg()), 'memory': [line for line in Path('/proc/meminfo').read_text().splitlines() if line.split(':', 1)[0] in ('MemAvailable', 'Dirty', 'Writeback')]}

def main():
    output = ROOT / 'metadata/build-output-warm-execve-evidence.json'
    assert not output.exists(), 'Retain prior diagnostic evidence'
    setup = json.loads((ROOT / 'metadata/setup.json').read_text())
    staged = json.loads((ROOT / 'metadata/build-output-staged.json').read_text())
    assets = {**setup['asset_sha256'], **staged['asset_sha256']}
    for name, expected in assets.items():
        assert stage.digest(ROOT / name) == expected, f'Changed immutable input: {name}'
    evidence = {'started_at': stage.now(), 'root': str(ROOT), 'uid': os.getuid(), 'diagnostic_sha256': stage.digest(__file__), 'before': quiet_snapshot(), 'workloads': {}}
    for kind in ('check', 'test'):
        assert json.loads((ROOT / f'metadata/{kind}-seed.json').read_text())['state'] == 'complete'
        path = ROOT / f'benchmark/{kind}-build-output-grouped.remote.json'
        cfg = json.loads(path.read_text())
        destination = Path(cfg['canonical_executable'])
        argv = [part.replace('{cargo}', str(destination)) for part in cfg['command']]
        assert kind != 'test' or '--no-run' in argv
        env = stage.environment(cfg)
        evidence['workloads'][kind] = {}
        for variant in ('baseline', 'candidate'):
            paired.install_variant(Path(cfg['variants'][variant]), destination)
            prefix = f'build-output-{kind}-{variant}'
            trace_path = ROOT / f'logs/{prefix}-execve.log'
            traced = ['strace', '-f', '-qq', '-e', 'trace=execve,execveat', '-s', '4096', '-o', str(trace_path), *argv]
            for label, invocation in (('warm', argv), ('trace', traced)):
                stem = ROOT / f'logs/{prefix}-{label}'
                with stem.with_suffix('.stdout').open('wb') as stdout, stem.with_suffix('.stderr').open('wb') as stderr:
                    completed = subprocess.run(invocation, cwd=cfg['cwd'], env=env, stdout=stdout, stderr=stderr)
                assert completed.returncode == 0, f'{prefix}-{label} failed'
                stderr_text = stem.with_suffix('.stderr').read_text()
                assert not re.search(r'^\s*(?:Checking|Compiling)\s', stderr_text, re.MULTILINE), f'{prefix}-{label} compiled'
            successes = [line for line in trace_path.read_text().splitlines() if re.search(r'= 0\s*$', line)]
            paths = []
            for line in successes:
                match = re.search(r'execve\("([^"]+)"', line) or re.search(r'execveat\([^,]+, "([^"]+)"', line)
                assert match, f'Unparsed successful exec: {line}'
                paths.append(match[1])
            assert set(paths) == {'/usr/bin/taskset', str(destination)}, f'Unexpected child process: {paths}'
            evidence['workloads'][kind][variant] = {'configuration_sha256': stage.digest(path), 'cargo_sha256': stage.digest(destination), 'successful_exec_paths': paths, 'trace_sha256': stage.digest(trace_path), 'trace_path': str(trace_path), 'warm_stderr': (ROOT / f'logs/{prefix}-warm.stderr').read_text(), 'trace_stderr': (ROOT / f'logs/{prefix}-trace.stderr').read_text()}
    evidence['uv_commit'] = subprocess.check_output(['git', '-C', str(ROOT / 'uv'), 'rev-parse', 'HEAD'], text=True).strip()
    evidence['uv_git_status'] = subprocess.check_output(['git', '-C', str(ROOT / 'uv'), 'status', '--porcelain'], text=True)
    assert evidence['uv_commit'] == stage.UV_COMMIT and not evidence['uv_git_status']
    for name, expected in assets.items():
        assert stage.digest(ROOT / name) == expected, f'Changed immutable input after diagnostics: {name}'
    evidence['after'] = quiet_snapshot()
    evidence['finished_at'] = stage.now()
    stage.record('metadata/build-output-warm-execve-evidence.json', evidence)
    print(json.dumps({'state': 'complete', 'metadata': str(output), 'metadata_sha256': stage.digest(output), 'workloads': {kind: list(variants) for kind, variants in evidence['workloads'].items()}, 'unexpected_compiler_or_test_execs': 0}))

if __name__ == '__main__':
    main()
