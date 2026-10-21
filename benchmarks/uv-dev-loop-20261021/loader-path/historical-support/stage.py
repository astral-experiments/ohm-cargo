#!/usr/bin/env python3
"""Stage an isolated second-host confirmation; never runs a benchmark."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile

ROOT = Path('/tmp/ohm-hillclimb-20261021/confirmation-path-cache')
LOCAL_WORK = '/home/dev-user/Documents/Codex/2026-10-20/i-want-you-to-hillclimb-on/work'
UV_COMMIT = '3d82a6ad5a7eab8c68236553b7846517767c4b61'
ARCHIVE = ROOT.parent / 'ohm-1.99.0-6-x86_64-unknown-linux-gnu.tar.gz'
EXPECTED = {
    'binaries/stripped/cargo-baseline': '26bf4671e7fe34108029d7fdc27e9b23b47e37b158f19a1ca63bc92b1b6f7438',
    'binaries/stripped/cargo-path-cache': 'b7fc8fd4d52662ca0f6362de6b86452cd09f4868c069f416b6f71336c4396eba',
    'benchmark/frozen/paired.py': '50d0cb2d4f595ccfa72d463fedb3ff4dadf9dfc1446c749d482d9ede8418c7cf',
    'benchmark/frozen/paired_repeated.py': '50547460e030aa73e1f48121bf477cf8f4a4538bf1bb577851af54176750b6d3',
    'ohm/bin/rustc': '6109cff145371a50c4f62b61908d2ffbf6d259b180c8effde07baa426aab682a',
    'ohm/bin/rustdoc': '0b7d9ded49eb9ecc73097a7bb3bb286e1722ac7143d7ca7d2d7c524c55d5684e',
    'ohm/lib/librustc_driver-b03bf00bec23bb9a.so': 'a3a5d8cc86af464504170220d142c4ea1129434e2d5e741755feec6f9f35a436',
    'uv/Cargo.lock': '747296375bb1889689f3bbb1e0303bddd071d6a65117c00be50856448260d014',
}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record(name, value):
    path = ROOT / name
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def command(argv, *, cwd=ROOT, environment=None):
    print(json.dumps({'at': now(), 'command': [str(part) for part in argv]}), flush=True)
    return subprocess.run(argv, cwd=cwd, env=environment, check=True,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def environment(configuration=None):
    result = os.environ.copy()
    result['TMPDIR'] = str(ROOT / 'tmp')
    result['CARGO_HOME'] = str(ROOT / 'cargo-home')
    if configuration is not None:
        for key, value in configuration['env'].items():
            if value is None:
                result.pop(key, None)
            else:
                result[key] = str(value)
    return result


def setup():
    for directory in ('tmp', 'logs', 'metadata', 'cargo-home', 'active/bin', 'targets'):
        (ROOT / directory).mkdir(parents=True, exist_ok=True)
    if digest(ARCHIVE) != '98a4f4f99ea1ff36e10209258724426496afbbcab14d746294fe53a2fedad37c':
        raise RuntimeError('published toolchain archive SHA256 does not match')
    if not (ROOT / 'ohm/bin/rustc').exists():
        unpack = ROOT / 'toolchain-unpacked'
        unpack.mkdir(exist_ok=True)
        components = {'rustc', 'rust-std-x86_64-unknown-linux-gnu'}
        with tarfile.open(ARCHIVE, 'r|gz') as stream:
            for member in stream:
                parts = Path(member.name).parts
                if len(parts) > 1 and parts[1] in components:
                    stream.extract(member, path=unpack, filter='data')
        for component in sorted(components):
            source = unpack / 'rust-1.99.0-dev-x86_64-unknown-linux-gnu' / component
            for child in source.iterdir():
                if child.is_dir():
                    shutil.copytree(child, ROOT / 'ohm' / child.name,
                                    symlinks=True, dirs_exist_ok=True)
    uv = ROOT / 'uv'
    uv.mkdir(exist_ok=True)
    if not (uv / '.git').exists():
        command(['git', 'init', '-q', str(uv)])
        command(['git', '-C', str(uv), 'remote', 'add', 'origin', 'https://github.com/astral-sh/uv.git'])
    commit = subprocess.run(['git', '-C', str(uv), 'cat-file', '-e', UV_COMMIT + '^{commit}'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if commit.returncode:
        command(['git', '-c', 'credential.helper=', '-C', str(uv), 'fetch', '--depth=1', 'origin', UV_COMMIT],
                environment=environment())
    command(['git', '-C', str(uv), 'checkout', '--detach', UV_COMMIT])
    if command(['git', '-C', str(uv), 'status', '--porcelain']).stdout:
        raise RuntimeError('pinned uv checkout must be clean')
    copied = []
    # Copy public crate archives and indexes only. Cargo unpacks and validates the
    # archives itself; no user config, credentials, source edits, or GC DB is copied.
    for kind in ('cache', 'index'):
        source_root = Path('/home/dev-user/.cargo/registry') / kind
        destination = ROOT / 'cargo-home/registry' / kind
        destination.mkdir(parents=True, exist_ok=True)
        for source in sorted(source_root.glob('*')):
            if source.name.startswith(('index.crates.io-', 'github.com-')) and source.is_dir() and not source.is_symlink():
                if not (destination / source.name).exists():
                    command(['cp', '-a', '--reflink=auto', '--', str(source), str(destination)])
                copied.append({'kind': kind, 'source': str(source), 'destination': str(destination / source.name)})
    for kind in ('check', 'test'):
        template = ROOT / 'benchmark' / f'{kind}-path-cache-grouped.json'
        configuration = json.loads(template.read_text().replace(LOCAL_WORK, str(ROOT)))
        configuration['env']['CARGO_HOME'] = str(ROOT / 'cargo-home')
        # Host-local absolute executable-search paths; all benchmark options,
        # repetitions, CPU affinity, and environment policy are unchanged.
        configuration['env']['PATH'] = f'{ROOT}/ohm/bin:/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin'
        record(f'benchmark/{kind}-path-cache-grouped.remote.json', configuration)
    actual = {}
    for name, expected in EXPECTED.items():
        actual[name] = digest(ROOT / name)
        if actual[name] != expected:
            raise RuntimeError(f'asset mismatch: {name}')
    for source in (ROOT / 'benchmark').glob('*.md'):
        actual[str(source.relative_to(ROOT))] = digest(source)
    for source in (ROOT / 'binaries/stripped').glob('*.json'):
        actual[str(source.relative_to(ROOT))] = digest(source)
    for source in (ROOT / 'benchmark').glob('*.json'):
        actual[str(source.relative_to(ROOT))] = digest(source)
    actual['stage.py'] = digest(ROOT / 'stage.py')
    metadata = {
        'created_at': now(), 'root': str(ROOT), 'uv_commit': UV_COMMIT,
        'toolchain_archive': str(ARCHIVE), 'archive_sha256': digest(ARCHIVE),
        'asset_sha256': actual, 'public_cache_copies': copied,
        'uname': list(platform.uname()), 'python': sys.version,
        'affinity': sorted(os.sched_getaffinity(0)), 'load_average': list(os.getloadavg()),
        'disk_usage': dict(zip(('total', 'used', 'free'), shutil.disk_usage(ROOT))),
        'versions': {},
    }
    for name in ('/proc/cpuinfo', '/proc/meminfo', '/proc/sys/kernel/perf_event_paranoid'):
        metadata[name] = Path(name).read_text()
    for name, argv in {
        'rustc': [str(ROOT / 'ohm/bin/rustc'), '-vV'],
        'cargo_baseline': [str(ROOT / 'binaries/stripped/cargo-baseline'), '-Vv'],
        'cargo_candidate': [str(ROOT / 'binaries/stripped/cargo-path-cache'), '-Vv'],
        'glibc': ['getconf', 'GNU_LIBC_VERSION'],
        'cc': ['cc', '--version'], 'ld': ['ld', '--version'],
    }.items():
        metadata['versions'][name] = command(argv, environment=environment()).stdout.strip()
    if not set(range(8)).issubset(metadata['affinity']):
        raise RuntimeError('the fixed 0-7 CPU affinity is unavailable')
    if '6d4a7ee3200c5311112d433cb9d1da4a2630a66f' not in metadata['versions']['rustc']:
        raise RuntimeError('unexpected rustc commit')
    record('metadata/setup.json', metadata)
    print(json.dumps({'at': now(), 'setup': 'complete', 'metadata': str(ROOT / 'metadata/setup.json')}), flush=True)


def seed(kind):
    setup_metadata = json.loads((ROOT / 'metadata/setup.json').read_text())
    for relative, expected in setup_metadata['asset_sha256'].items():
        if digest(ROOT / relative) != expected:
            raise RuntimeError(f'frozen setup asset changed: {relative}')
    configuration = json.loads((ROOT / 'benchmark' / f'{kind}-path-cache-grouped.remote.json').read_text())
    sys.path.insert(0, str(ROOT / 'benchmark/frozen'))
    import paired
    destination = Path(configuration['canonical_executable'])
    paired.install_variant(Path(configuration['variants']['baseline']), destination)
    argv = [part.replace('{cargo}', str(destination)) for part in configuration['command']]
    # The copied public cache may be incomplete. Populate it once using the same
    # public registry; every subsequent warmup/measurement stays --offline.
    fetch_argv = [str(destination), '-Zohm-defaults=yes', 'fetch', '--locked']
    env = environment(configuration)
    for label, invocation in ((f'{kind}-fetch', fetch_argv), (f'{kind}-seed', argv)):
        status = {'state': 'running', 'started_at': now(), 'command': invocation,
                  'configuration_sha256': digest(ROOT / 'benchmark' / f'{kind}-path-cache-grouped.remote.json')}
        record(f'metadata/{label}.json', status)
        with (ROOT / f'logs/{label}.stdout').open('wb') as stdout, (ROOT / f'logs/{label}.stderr').open('wb') as stderr:
            result = subprocess.run(invocation, cwd=configuration['cwd'], env=env, stdout=stdout, stderr=stderr)
        status.update(state='complete' if result.returncode == 0 else 'failed',
                      finished_at=now(), returncode=result.returncode)
        record(f'metadata/{label}.json', status)
        if result.returncode:
            raise RuntimeError(f'{label} failed; see the task-owned logs')
    print(json.dumps({'at': now(), 'seed': kind, 'state': 'complete'}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('setup', 'seed-check', 'seed-test'))
    arguments = parser.parse_args()
    if ROOT.resolve() != ROOT or not ROOT.is_dir():
        raise RuntimeError('the fixed task-owned root must exist without symlink redirection')
    if arguments.action == 'setup':
        setup()
    else:
        seed(arguments.action.removeprefix('seed-'))


if __name__ == '__main__':
    main()
