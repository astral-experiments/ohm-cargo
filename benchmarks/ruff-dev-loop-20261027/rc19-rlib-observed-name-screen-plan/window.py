"""Bound delivery of a stock compiler's archive-create and publication events."""
import ctypes
import os
from pathlib import Path
import select
import struct
import subprocess
import sys
import tempfile
import time

CREATE, DELETE, MOVED_TO, ISDIR = 0x100, 0x200, 0x80, 0x40000000
OVERFLOW, IGNORED = 0x4000, 0x8000
HEADER = struct.Struct('iIII')
libc = ctypes.CDLL(None, use_errno=True)


def observe(output, argv, affinity=None, **kwargs):
    fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
    if fd < 0:
        raise OSError(ctypes.get_errno(), 'inotify_init1')
    events = []
    objects = []
    published = False
    other = 0
    command = None
    cpu_start = time.process_time_ns()
    try:
        wd = libc.inotify_add_watch(fd, os.fsencode(output.parent), CREATE | DELETE | MOVED_TO)
        if wd < 0:
            raise OSError(ctypes.get_errno(), 'inotify_add_watch')
        lower = time.monotonic_ns()
        try:
            os.read(fd, 65536)
        except BlockingIOError:
            pass
        else:
            raise RuntimeError('new archive watch already had a queued event')
        begin = time.monotonic_ns()
        command = subprocess.Popen(argv, preexec_fn=(lambda: os.sched_setaffinity(0, affinity)) if affinity is not None else None, **kwargs)
        ended = None
        while True:
            if ended is None and command.poll() is not None:
                ended = time.monotonic_ns()
            before = time.monotonic_ns()
            try:
                buf = os.read(fd, 65536)
            except BlockingIOError:
                lower = before
                if ended is not None:
                    break
                select.select([fd], [], [], 0.002)
                continue
            after = time.monotonic_ns()
            assert buf
            offset = 0
            while offset < len(buf):
                desc, mask, cookie, length = HEADER.unpack_from(buf, offset)
                assert not mask & (OVERFLOW | IGNORED) and desc == wd
                end = offset + HEADER.size + length
                name = os.fsdecode(buf[offset + HEADER.size:end].split(b'\0', 1)[0])
                role = None
                if name.endswith('.temp-archive') and mask & ISDIR:
                    if mask & CREATE:
                        role = 'create'
                    elif mask & DELETE:
                        role = 'remove'
                if name == output.name and mask & MOVED_TO and not mask & ISDIR:
                    role = 'publish'
                    published = True
                if name.startswith('ruff_linter-') and name.endswith('.rcgu.o') and mask & (CREATE | MOVED_TO):
                    assert not published and not mask & ISDIR
                    objects.append({'name': name, 'mask': mask, 'cookie': cookie})
                if role:
                    events.append({'role': role, 'lo': lower - begin, 'hi': after - begin,
                                   'name': name if role != 'publish' else '<archive>', 'cookie': cookie})
                else:
                    other += 1
                offset = end
            assert offset == len(buf)
        return {'events': events, 'objects': objects, 'other': other, 'command_ns': ended - begin,
                'observer_cpu_ns': time.process_time_ns() - cpu_start, 'returncode': command.returncode}
    finally:
        os.close(fd)
        if command is not None and command.poll() is None:
            command.terminate()
            command.wait()


def bounds(record, expect):
    events = record['events']
    assert record['returncode'] == 0
    if not expect:
        assert not events, events
        return None
    assert [e['role'] for e in events] == ['create', 'publish', 'remove'], events
    create, publish, remove = events
    assert create['name'] == remove['name'] and publish['cookie'] and not (create['cookie'] or remove['cookie'])
    assert all(e['lo'] <= e['hi'] for e in events)
    return {'lo': max(0, publish['lo'] - create['hi']), 'hi': publish['hi'] - create['lo'],
            'create_bracket': create['hi'] - create['lo'], 'publish_bracket': publish['hi'] - publish['lo']}


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as dest:
        out = Path(dest) / 'libfixture.rlib'
        code = """import os, pathlib, sys, time
p=pathlib.Path(sys.argv[1]); d=p.parent/'unit.temp-archive'
t0=time.monotonic_ns();d.mkdir();t1=time.monotonic_ns()
x=d/'tmp.a';x.write_bytes(b'archive');time.sleep(.03)
t2=time.monotonic_ns();x.rename(p);t3=time.monotonic_ns();d.rmdir()
print(t1-t0,t3-t2,t2-t1,t3-t0)
"""
        with tempfile.TemporaryFile() as log:
            w = observe(out, [sys.executable, '-IB', '-c', code, str(out)], stdout=log)
            b = bounds(w, True)
            log.seek(0)
            _, _, exact_lower, exact_upper = map(int, log.read().split())
            assert b['lo'] <= exact_upper and exact_lower <= b['hi'] and b['hi'] >= 30_000_000
        assert bounds(observe(out, ['/bin/true']), False) is None
    print('Observed one genuine creation, rename, and removal, and one unchanged command.')
