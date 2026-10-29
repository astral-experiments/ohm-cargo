"""Project completed fixture traces onto three literal paths and successful execs."""

import ast
import hashlib
import json
from pathlib import Path
import re
import sys


def sha(data):
    return hashlib.sha256(data).hexdigest()


def joined(raw):
    pending = {}
    events = []
    for line_no, line in enumerate(raw.decode().splitlines(), 1):
        matched = re.fullmatch(r'(\d+)\s+\d+\.\d+ (.*)', line)
        if not matched:
            continue
        pid, call = matched.groups()
        start = line_no
        if call.endswith('<unfinished ...>'):
            pending[pid] = (start, call.split('<unfinished ...>')[0].rstrip())
            continue
        if call.startswith('<... ') and ' resumed>' in call:
            if pid not in pending:
                continue
            start, prefix = pending.pop(pid)
            call = prefix + call.split(' resumed>', 1)[1]
        events.append((start, line_no, pid, call))
    return sorted(events)


def scope(raw, root, sdk):
    roles = {str(root / spelling): name for name, spelling in (
        ('lock', 'ws/Cargo.lock'), ('manifest', 'late/Cargo.toml'),
        ('marker', 'target/.cargo-resolve-cache-v1'))}
    events = []
    procs = []
    pids = {}
    for line, end, pid, call in joined(raw):
        if call.startswith('execve(') and call.endswith('= 0'):
            match = re.match(r'execve\("([^"]+)", (\[.*?\]), ', call)
            assert match, call
            executable, raw_argv = match.groups()
            if executable == str(sdk / 'bin/cargo'):
                name = 'cargo'
            elif executable == str(sdk / 'bin/rustc'):
                name = 'rustc'
            else:
                assert Path(executable).name == 'cargo' and not procs, executable
                name = 'rustup-cargo-proxy'
            args = ast.literal_eval(raw_argv)[1:]
            assert all(not arg.startswith('/') for arg in args), args
            procs.append([line, name, args])
        event = None
        unlinked = False
        opened = re.match(r'openat\([^,]+, "([^"]+)", (O_[^,)]*)', call)
        if opened and opened[1] in roles:
            result = re.search(r' = (-?\d+)(?:<[^>]+>)?(?: ([A-Z][A-Z0-9_]+))?', call)
            assert result, call
            event = [roles[opened[1]], 'open', opened[2], int(result[1]), result[2]]
        other = re.match(r'(read|flock|close)\((\d+)<([^>]+)>', call)
        if other and (path := other[3].removesuffix(' (deleted)')) in roles:
            role, op, fd = roles[path], other[1], int(other[2])
            tail = call[other.end():]
            unlinked = tail.startswith('(deleted)') or other[3].endswith(' (deleted)')
            tail = tail.removeprefix('(deleted)')
            if op == 'read':
                read = re.fullmatch(r', ("(?:[^"\\]|\\.)*"), (\d+)\) = (\d+)', tail)
                assert read, call
                body = ast.literal_eval('b' + read[1])
                assert len(body) == int(read[3])
                event = [role, op, fd, int(read[2]), body.hex()]
            elif op == 'flock':
                lock = re.fullmatch(r', ([A-Z_|]+)\) = (\d+)', tail)
                assert lock, call
                event = [role, op, fd, lock[1], int(lock[2])]
            else:
                assert tail == ') = 0', call
                event = [role, op, fd, 0]
        if event:
            events.append([line, end, pids.setdefault(pid, len(pids)), unlinked, *event])
    return {'raw_trace_sha256': sha(raw), 'processes': procs, 'events': events}


def arm(nine, changed):
    nine, changed = Path(nine).resolve(), Path(changed).resolve()
    sdk = nine / 'ru/toolchains/ohm'
    terminal = json.loads((nine / 'terminal.json').read_text())
    assert sha((sdk / 'bin/cargo').read_bytes()) == terminal['image']
    data = {}
    for name in terminal['stages']:
        stage = nine / name
        row = json.loads((stage / 'row.json').read_text())
        raw = (stage / 'kernel.trace').read_bytes()
        assert sha(raw) == row['kernel_sha256']
        result = scope(raw, nine, sdk)
        error = row['diagnostic']
        if error:
            error = error.replace(str(nine / 'ws/Cargo.lock'), 'Cargo.lock')
        result.update(exit=row['exit'], edges=row.get('edges'), error=error,
                      row_sha256=sha((stage / 'row.json').read_bytes()),
                      stdout_sha256=sha((stage / 'stdout').read_bytes()),
                      stderr_sha256=sha((stage / 'stderr').read_bytes()),
                      cache_hit='reusing the cached workspace resolution' in (stage / 'stderr').read_text())
        assert result['stdout_sha256'] == row['stdout_sha256']
        assert result['stderr_sha256'] == row['stderr_sha256']
        if (stage / 'actor.json').is_file():
            actor = json.loads((stage / 'actor.json').read_text())
            assert row['lock_before'] == row['lock_after'] == actor['lock']
            result['actor'] = {'receipt_sha256': sha((stage / 'actor.json').read_bytes()),
                               'lock_identity_unchanged': True, 'lock_sha256': actor['lock'][-1],
                               'manifest_sha256': actor['manifest_at_release'][-1]}
        data[name] = result
    other = json.loads((changed / 'terminal.json').read_text())
    assert other['image'] == terminal['image']
    for name in ['raced', 'static']:
        raw = (changed / (name + '.trace')).read_bytes()
        assert sha(raw) == other[name]['trace_sha256']
        result = scope(raw, changed, sdk)
        error = (changed / (name + '.err')).read_text()
        result.update(exit=other[name]['exit'], edges=None, error=error.replace(str(changed / 'ws/Cargo.lock'), 'Cargo.lock'),
                      stdout_sha256=sha((changed / (name + '.out')).read_bytes()),
                      stderr_sha256=sha(error.encode()))
        data['replaced-' + name] = result
    writer = other['writer']
    return {'cargo_sha256': terminal['image'], 'rustc_sha256': sha((sdk / 'bin/rustc').read_bytes()),
            'version_output_sha256': sha((nine / 'cargo-version').read_bytes()), 'phases': data,
            'native_terminal_sha256': sha((nine / 'terminal.json').read_bytes()),
            'replacement_terminal_sha256': sha((changed / 'terminal.json').read_bytes()),
            'replacement': {'old_sha256': writer['old_sha256'], 'new_sha256': writer['new_sha256'],
                            'size': writer['size'], 'new_inode': writer['new_inode'] != writer['old_inode'],
                            'mtime_ns_identical': True, 'actor_sha256': sha((changed / 'writer.json').read_bytes())}}


if __name__ == '__main__':
    print(json.dumps(arm(*sys.argv[1:]), indent=2, sort_keys=True))
