"""Conservative accounting of the pinned writer's per-PID syscall records.

One cache-mutating PID is required. No cross-PID order is inferred. Unsupported
cache mutations, missing fd paths or undecodable records refuse exact accounting.
"""
from pathlib import Path
import hashlib
import re

WRITE = {'write', 'writev', 'pwrite64', 'pwritev', 'pwritev2'}
KNOWN = WRITE | {'execve', 'execveat', 'open', 'openat', 'openat2', 'close',
    'rename', 'renameat', 'renameat2', 'unlink', 'unlinkat', 'ftruncate', 'truncate',
    'lseek', 'mmap', 'msync', 'copy_file_range', 'sendfile', 'splice'}


def split_arguments(text):
    result, start, stack = [], 0, []
    quoted = escaped = False
    pairs = {')': '(', ']': '[', '}': '{', '>': '<'}
    for index, char in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char in '([{<':
            stack.append(char)
        elif (char == '>' and stack[-2:] == ['<', '[']
              and re.search(r'<UNIX:\[[0-9]+-$', text[:index])
              and re.match(r'[0-9]+\]>', text[index + 1:])):
            continue
        elif char in ')]}>':
            assert stack and stack.pop() == pairs[char], 'unbalanced syscall arguments'
        elif char == ',' and not stack:
            result.append(text[start:index].strip())
            start = index + 1
    assert not quoted and not stack and not escaped
    result.append(text[start:].strip())
    return result


def cbytes(text):
    assert text.startswith('"')
    index, result = 1, bytearray()
    escapes = {'a': 7, 'b': 8, 'f': 12, 'n': 10, 'r': 13,
               't': 9, 'v': 11, '\\': 92, '"': 34}
    while index < len(text) and text[index] != '"':
        char = text[index]
        index += 1
        if char != '\\':
            result.extend(char.encode('utf-8'))
            continue
        assert index < len(text)
        char = text[index]
        index += 1
        if char in escapes:
            result.append(escapes[char])
        elif char in '01234567':
            digits = char
            while index < len(text) and len(digits) < 3 and text[index] in '01234567':
                digits += text[index]
                index += 1
            assert int(digits, 8) <= 255
            result.append(int(digits, 8))
        elif char == 'x':
            digits = text[index:index + 2]
            assert re.fullmatch('[0-9a-fA-F]{2}', digits)
            result.append(int(digits, 16))
            index += 2
        else:
            raise AssertionError('unknown C string escape')
    assert index == len(text) - 1 and text[index] == '"', 'truncated or trailing string'
    return bytes(result)


def fd_path(text):
    match = re.fullmatch(r'(?:-?\d+|AT_FDCWD)<([^<>]*)(?:<(?:char|block) [0-9]+:[0-9]+>)?>', text)
    assert match, 'missing or ambiguous decoded fd path'
    return match[1]


def path_argument(text, directory=None):
    value = cbytes(text).decode('utf-8')
    assert '\0' not in value
    if not value.startswith('/'):
        assert directory is not None, 'unresolved relative path'
        parent = fd_path(directory)
        assert parent.startswith('/')
        value = str(Path(parent) / value)
    assert '..' not in Path(value).parts
    return value


def records(text):
    pending = None
    for ordinal, line in enumerate(text.splitlines(), 1):
        assert line
        if re.fullmatch(r'--- SIG[A-Z0-9_]+ \{.*\} ---|\+\+\+ exited with 0 \+\+\+', line):
            continue
        if line.endswith('<unfinished ...>'):
            match = re.match(r'^([a-zA-Z0-9_]+)\(', line)
            assert pending is None and match and match[1] in KNOWN
            pending = (match[1], line[:-len('<unfinished ...>')], ordinal)
            continue
        resumed = re.match(r'^<\.\.\. ([a-zA-Z0-9_]+) resumed>(.*)$', line)
        if resumed:
            assert pending and pending[0] == resumed[1]
            line, ordinal = pending[1] + resumed[2], pending[2]
            pending = None
        else:
            assert pending is None, 'new syscall before unfinished record resumes'
        match = re.fullmatch(r'([a-zA-Z0-9_]+)\((.*)\) += (.*)', line)
        assert match and match[1] in KNOWN, 'unidentified syscall record'
        result = re.fullmatch(r'(-?(?:0x[0-9a-f]+|[0-9]+))(?:<([^<>]*)(?:<(?:char|block) [0-9]+:[0-9]+>)?>)?(?: ([A-Z0-9_]+) \([^\n]*\))?', match[3])
        assert result, 'undecodable syscall return'
        yield {'ordinal': ordinal, 'kind': match[1], 'args': split_arguments(match[2]),
               'returned': int(result[1], 0), 'result_path': result[2],
               'error': result[3], 'raw': line}
    assert pending is None, 'unfinished record remains'


def decode(trace_files, cache_directory, final_files):
    cache = str(Path(cache_directory))
    temps, last, mutations, writes, commits, failed_commits = {}, {}, set(), [], [], []
    files = []

    def inside(path):
        return path == cache or path.startswith(cache + '/')

    def mutate(pid):
        mutations.add(pid)
        assert len(mutations) == 1, 'multiple cache-mutating PIDs; no order inference'

    trace_files = list(map(Path, trace_files))
    assert len({p.name.rsplit('.', 1)[1] for p in trace_files}) == len(trace_files)
    for path in sorted(trace_files, key=lambda p: int(p.name.rsplit('.', 1)[1])):
        assert re.fullmatch(r'[0-9]+', path.name.rsplit('.', 1)[1]) and path.is_file() and not path.is_symlink()
        pid = int(path.name.rsplit('.', 1)[1])
        raw = path.read_bytes()
        files.append({'name': path.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        for event in records(raw.decode('utf-8')):
            kind, args, returned = event['kind'], event['args'], event['returned']
            if kind in {'open', 'openat', 'openat2'}:
                target = event['result_path']
                if returned < 0 or target is None or not inside(target):
                    continue
                flags = args[1] if kind == 'open' else args[2]
                if 'O_WRONLY' not in flags and 'O_RDWR' not in flags:
                    continue
                mutate(pid)
                assert 'O_CREAT' in flags and 'O_EXCL' in flags and 'O_APPEND' not in flags
                assert Path(target).parent == Path(cache) and Path(target).name.startswith('.tmp')
                assert target not in temps, 'reused temporary name'
                temps[target] = {'pid': pid, 'fd': returned, 'data': bytearray(), 'cursor': 0, 'closed': False}
            elif kind in WRITE:
                target = fd_path(args[0])
                if not inside(target):
                    continue
                mutate(pid)
                assert target in temps, 'write to unknown or committed cache file'
                state = temps[target]
                assert state['pid'] == pid and not state['closed']
                assert int(args[0].split('<', 1)[0]) == state['fd'], 'unexpected writer fd'
                row = {'pid': pid, 'ordinal': event['ordinal'], 'kind': kind, 'path': target,
                       'returned': returned, 'error': event['error'], 'raw': event['raw']}
                if returned < 0:
                    writes.append(row)
                    continue
                if kind in {'write', 'pwrite64'}:
                    payload = cbytes(args[1]);requested = int(args[2])
                    assert len(payload) == requested
                else:
                    assert args[1].startswith('[') and args[1].endswith(']')
                    vectors = split_arguments(args[1][1:-1]);assert len(vectors) == int(args[2])
                    chunks = []
                    for vector in vectors:
                        assert vector.startswith('{') and vector.endswith('}')
                        base, length = split_arguments(vector[1:-1])
                        assert base.startswith('iov_base=') and length.startswith('iov_len=')
                        chunk = cbytes(base[len('iov_base='):]);assert len(chunk) == int(length[len('iov_len='):])
                        chunks.append(chunk)
                    payload = b''.join(chunks);requested = len(payload)
                assert 0 <= returned <= requested <= 65536
                positioned = kind.startswith('pwrite')
                offset = int(args[3]) if positioned else state['cursor']
                assert offset >= 0
                if kind == 'pwritev2':
                    assert len(args) == 5 and args[4] == '0'
                end = offset + returned
                assert end <= 65536
                if end > len(state['data']):state['data'].extend(b'\0' * (end - len(state['data'])))
                state['data'][offset:end] = payload[:returned]
                if not positioned:state['cursor'] = end
                row.update(requested=requested, short=returned < requested, offset=offset,
                           accepted_sha256=hashlib.sha256(payload[:returned]).hexdigest())
                writes.append(row)
            elif kind in {'rename', 'renameat', 'renameat2'}:
                if kind == 'rename':
                    source, target = path_argument(args[0]), path_argument(args[1])
                else:
                    source, target = path_argument(args[1], args[0]), path_argument(args[3], args[2])
                    if kind == 'renameat2':assert args[4] in ('0', 'RENAME_NOREPLACE')
                if not inside(source) and not inside(target):continue
                mutate(pid)
                row = {'pid': pid, 'ordinal': event['ordinal'], 'source': source, 'target': target,
                       'returned': returned, 'error': event['error']}
                if returned < 0:
                    failed_commits.append(row);continue
                assert returned == 0 and source in temps and temps[source]['pid'] == pid
                assert Path(target).parent == Path(cache) and re.fullmatch('[0-9a-f]{3}', Path(target).name)
                payload = bytes(temps[source]['data'])
                row.update(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
                commits.append(row);last[Path(target).name] = payload;temps[source]['closed'] = True
            elif kind in {'unlink', 'unlinkat'}:
                target = path_argument(args[0]) if kind == 'unlink' else path_argument(args[1], args[0])
                if inside(target) and returned == 0:
                    mutate(pid);assert target in temps and temps[target]['pid'] == pid
                    temps[target]['closed'] = True
            elif kind == 'lseek':
                target = fd_path(args[0])
                if target in temps and returned >= 0:
                    mutate(pid);state = temps[target];assert state['pid'] == pid
                    offset = int(args[1]);base = {'SEEK_SET': 0, 'SEEK_CUR': state['cursor'], 'SEEK_END': len(state['data'])}[args[2]]
                    assert returned == base + offset;state['cursor'] = returned
            elif kind in {'ftruncate', 'truncate'}:
                target = fd_path(args[0]) if kind == 'ftruncate' else path_argument(args[0])
                assert not inside(target) or returned < 0, 'unsupported cache truncation'
            elif kind in {'copy_file_range', 'sendfile', 'splice'} and returned > 0:
                target = fd_path(args[0] if kind == 'sendfile' else args[2])
                assert not inside(target), 'unsupported non-write cache transfer'
            elif kind == 'mmap' and returned >= 0 and 'PROT_WRITE' in args[2] and 'MAP_SHARED' in args[3] and args[4] != '-1':
                assert not inside(fd_path(args[4])), 'writable shared cache mapping'
    expected = {}
    for name, path in sorted(final_files.items()):
        assert re.fullmatch('[0-9a-f]{3}', name)
        assert Path(path).is_file() and not Path(path).is_symlink() and Path(path).stat().st_nlink == 1
        payload = Path(path).read_bytes()
        assert last.get(name) == payload, 'last committed payload differs from final slot'
        expected[name] = {'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
    assert set(last) == set(expected), 'missing or additional final slot'
    return {'state': 'exact-logical-cache-write-accounting', 'numeric_pid_files': files,
            'cache_mutating_pids': sorted(mutations), 'global_order_inferred': False,
            'successful_logical_write_bytes': sum(max(row['returned'], 0) for row in writes),
            'successful_write_calls': sum(row['returned'] >= 0 for row in writes),
            'short_writes': [row for row in writes if row.get('short')],
            'failed_writes': [row for row in writes if row['returned'] < 0],
            'successful_commits': len(commits), 'commits': commits, 'failed_commits': failed_commits,
            'writes': writes, 'final_slots': expected,
            'final_logical_bytes': sum(row['bytes'] for row in expected.values()),
            'physical_io_bytes_claimed': False}
