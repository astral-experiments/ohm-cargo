"""Decode complete successful execve/execveat calls from strace -f, including resumed calls."""

import ast
import hashlib
import json
from pathlib import Path
import re


def argv_hash(args):
    return hashlib.sha256(json.dumps(args, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def native_execs(raw):
    if isinstance(raw, bytes):
        raw = raw.decode()
    pending = {}
    completed = []
    for end, line in enumerate(raw.splitlines(), 1):
        parsed = re.fullmatch(r'(\d+)\s+(?:(?:\d+\.\d+|\d\d:\d\d:\d\d\.\d+) )?(.*)', line)
        if not parsed:
            continue
        task, item = parsed.groups()
        start = end
        if item.startswith(('execve(', 'execveat(')) and item.endswith('<unfinished ...>'):
            if task in pending:
                raise ValueError('second unfinished exec on task ' + task)
            pending[task] = (start, item[:-len('<unfinished ...>')].rstrip())
            continue
        resumed = re.match(r'<\.\.\. (execveat|execve) resumed>(.*)', item)
        if resumed:
            start, prefix = pending.pop(task)
            item = prefix + resumed[2]
        if not item.startswith(('execve(', 'execveat(')) or not item.endswith('= 0'):
            continue
        # See strace's -s/-v options. Incomplete argv cannot certify the process.
        arguments = re.match(r'execve(?:at)?\((?:[^,]+, )?("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x|NULL|\[)', item)
        if not arguments:
            raise ValueError('undecodable successful exec at line ' + str(start))
        path, args = (ast.literal_eval(v) for v in arguments.groups())
        if not all(isinstance(s, str) for s in args):
            raise ValueError('truncated argv at line ' + str(start))
        program = Path(path).name or Path(args[0]).name
        src = [Path(arg).name for arg in args if arg.endswith('.rs')]
        if '--crate-name' in args:
            crate = args[args.index('--crate-name') + 1]
        else:
            crate = None
        completed.append((start, {
            'lines': [start, end], 'program': program, 'argc': len(args),
            'argv_sha256': argv_hash(args), 'crate': crate, 'rust_source_basenames': src,
            'output_argument': '-o' in args,
            'cargo_args': args[1:] if program == 'cargo' else None,
        }))
    if pending:
        raise ValueError('unterminated exec record')
    return [row for _, row in sorted(completed)]


def is_compile(row):
    return row['program'] == 'rustc' and row['crate'] is not None and bool(row['rust_source_basenames'])


def is_link(row):
    return row['program'] in ('ld.bfd', 'wild', 'ld.lld', 'rust-lld', 'lld') and row['output_argument']
