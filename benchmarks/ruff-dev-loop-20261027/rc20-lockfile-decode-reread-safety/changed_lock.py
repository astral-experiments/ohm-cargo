"""Force a different, equally long lockfile between Cargo's two shared reads."""

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(str(message))


def actor(directory):
    lock = directory / 'ws/Cargo.lock'
    replacement = lock.with_suffix('.next')
    marker = directory / 'target/.cargo-resolve-cache-v1'
    original = lock.stat()
    old = lock.read_bytes()
    new = replacement.read_bytes()
    require(len(old) == len(new) and old != new, 'same-size distinct input')
    os.utime(replacement, ns=(original.st_atime_ns, original.st_mtime_ns))
    with marker.open('wb', buffering=0) as out:
        os.replace(replacement, lock)
        current = lock.stat()
        require((original.st_dev, original.st_size, original.st_mtime_ns) ==
                (current.st_dev, current.st_size, current.st_mtime_ns), 'replacement metadata')
        require(current.st_ino != original.st_ino, 'unchanged inode')
        out.write(b'intentional-cache-miss\n')
    return {'size': len(old), 'mtime_ns': current.st_mtime_ns, 'old_inode': original.st_ino,
            'new_inode': current.st_ino, 'device': current.st_dev,
            'old_sha256': digest(old), 'new_sha256': digest(new)}


if sys.argv[1] == '--actor':
    print(json.dumps(actor(Path(sys.argv[2]))))
    sys.exit(0)

source, directory = (Path(arg).resolve() for arg in sys.argv[1:])
require(shutil.disk_usage(directory.parent).free > 16 << 20, 'insufficient fixture space')
directory.mkdir(mode=0o700)
for name in ['ws', 'late']:
    shutil.copytree(source / name, directory / name)
(directory / 'target').mkdir()

lock = directory / 'ws/Cargo.lock'
old = lock.read_bytes()
new = b'version = [\n'.ljust(len(old), b' ')
lock.with_suffix('.next').write_bytes(new)
marker = directory / 'target/.cargo-resolve-cache-v1'
os.mkfifo(marker, 0o600)
cargo = (source / 'ru/toolchains/ohm/bin/cargo').resolve()
approved = json.loads((source / 'terminal.json').read_text())['image']
require(digest(cargo.read_bytes()) == approved, 'physical Cargo digest')
environment = {'HOME': str(Path.home()), 'PATH': os.environ.get('RUSTUP_PROXY_DIR', str(Path.home() / '.cargo/bin')) + ':/usr/bin:/bin',
               'LC_ALL': 'C', 'RUSTUP_HOME': str(source / 'ru'), 'RUSTUP_AUTO_INSTALL': '0',
               'CARGO_HOME': str(directory / 'cargo-home'), 'CARGO_TARGET_DIR': str(directory / 'target'),
               'CARGO_BUILD_BUILD_DIR': str(directory / 'build'), 'CARGO_NET_OFFLINE': 'true',
               'CARGO_TERM_COLOR': 'never', 'CARGO_EXPERIMENTAL_RESOLVE_CACHE': '1'}
cmd = ['cargo', '+ohm', 'metadata', '--format-version', '1', '--offline', '--locked']

def met(label):
    trace = directory / (label + '.trace')
    with (directory / (label + '.out')).open('wb') as so, (directory / (label + '.err')).open('wb') as se:
        process = subprocess.Popen(['strace', '-f', '-qq', '-ttt', '-yy', '-s', '2048',
                                    '-e', 'trace=openat,read,flock,close,execve', '-o', trace, *cmd],
                                   env=environment, cwd=lock.parent, stdout=so, stderr=se, start_new_session=True)
        try:
            code = process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise
    require(code == 101, (label, code))
    text = trace.read_text()
    require('execve("' + str(cargo) + '"' in text or 'execve("' + str(source / 'ru/toolchains/ohm/bin/cargo') + '"' in text,
            'physical Cargo invocation through private +ohm')
    streams = []
    tokens = []
    for line in text.splitlines():
        if str(lock) not in line:
            if 'openat(' in line and str(marker) in line:
                tokens.append('marker')
            continue
        if 'flock(' in line and 'LOCK_SH' in line:
            tokens.append('shared')
            streams.append(bytearray())
        elif 'flock(' in line and 'LOCK_UN' in line:
            tokens.append('unlock')
        elif 'read(' in line and (match := re.search(r', ("(?:[^"\\]|\\.)*"), \d+\) = (\d+)$', line)):
            chunk = ast.literal_eval('b' + match[1])
            require(len(chunk) == int(match[2]), line)
            streams[-1].extend(chunk)
    return {'exit': code, 'tokens': tokens, 'reads': [digest(s) for s in streams],
            'trace_sha256': digest(trace.read_bytes())}

with (directory / 'writer.json').open('wb') as output:
    writer = subprocess.Popen([sys.executable, '-IB', __file__, '--actor', directory], stdout=output)
    try:
        raced = met('raced')
        require(writer.wait(timeout=3) == 0, 'writer failed')
    finally:
        if writer.poll() is None:
            writer.kill()
            writer.wait()
require(raced['tokens'] == ['shared', 'marker', 'unlock', 'shared', 'unlock'], raced)
require(raced['reads'] == [digest(old), digest(new)], raced)
require(marker.is_fifo(), 'missing witness')
marker.unlink()
environment['CARGO_EXPERIMENTAL_RESOLVE_CACHE'] = '0'
static = met('static')
require(static['tokens'] == ['shared', 'unlock'] and static['reads'] == [digest(new)], static)
diagnostic = (directory / 'raced.err').read_bytes()
require(diagnostic == (directory / 'static.err').read_bytes() and b'unclosed array' in diagnostic, diagnostic)
receipt = {'image': approved, 'raced': raced, 'static': static, 'diagnostic_sha256': digest(diagnostic),
           'writer': json.loads((directory / 'writer.json').read_text())}
(directory / 'terminal.json').write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
print('Verified different same-size, same-mtime lockfile. Both actual Cargo reads and syntax error match.')
