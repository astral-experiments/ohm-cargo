"""Excluded per-PID syscall witness using the original Cargo command/environment."""
from pathlib import Path
import hashlib
import os
import re
import shutil
import stat

SYSCALLS = ('execve,execveat,open,openat,openat2,close,write,writev,pwrite64,pwritev,pwritev2,'
            'rename,renameat,renameat2,unlink,unlinkat,ftruncate,truncate,lseek,mmap,msync,'
            'copy_file_range,sendfile,splice')


def diagnostics(text):
    text = re.sub(r'^==\d+==.*\n?', '', text, flags=re.M)
    return re.sub(r'^\s*Finished .* in .*$', '', text, flags=re.M)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def traced(engine, decoder, witness, home, arm, label, argv):
    assert label == 'native' and arm in ('baseline', 'candidate')
    prefix = engine.OUT / (label + '.syscalls')
    assert not list(engine.OUT.glob(prefix.name + '*'))
    tracer = engine.ROOT / 'aux/strace-capture'
    assert sha(tracer) == '7088ab983a19122541e3c5cac906bc275808ab6c9a2b3fafbcca6db65062dd18'
    command = [str(tracer), '-ff', '-qq', '--seccomp-bpf', '-yy', '-v', '-s', '65536',
               '-e', 'trace=' + SYSCALLS, '-o', str(prefix)] + argv
    engine.run(label, command, engine.ENV, timeout=150)
    paths = sorted(engine.OUT.glob(prefix.name + '*'))
    assert 0 < len(paths) <= 1024
    assert all(re.fullmatch(re.escape(prefix.name) + r'\.[0-9]+', path.name) for path in paths)
    assert all(path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1 for path in paths)
    assert sum(path.stat().st_size for path in paths) <= 512 * 1024**2
    identities = [{'path': str(path), 'bytes': path.stat().st_size,
                   'mode': stat.S_IMODE(path.stat().st_mode), 'sha256': sha(path)} for path in paths]
    engine.write(label + '.numeric-pid-files.json', {'state': 'all-numeric-pid-files-bound',
                 'files': identities, 'global_order_inferred': False})
    after = witness.observe(home, arm)
    cache = Path(home) / witness.DIRECTORY
    snapshot = engine.OUT / (label + '-committed-cache')
    snapshot.mkdir(mode=0o700)
    final = {}
    for row in after['entries']:
        source, target = cache / row['name'], snapshot / row['name']
        shutil.copyfile(source, target)
        target.chmod(0o400)
        assert not target.samefile(source) and target.stat().st_nlink == 1
        assert sha(source) == sha(target) == row['sha256']
        final[row['name']] = target
    engine.write(label + '.cache-after.json', after)
    exec_lines, joins = [], []
    for path in paths:
        pid = int(path.name.rsplit('.', 1)[1])
        for record in decoder.records(path.read_text()):
            if record['kind'] in ('execve', 'execveat'):
                exec_lines.append(str(pid) + ' ' + record['raw'] + '\n')
                joins.append({'pid_file': str(path), 'local_ordinal': record['ordinal'],
                              'completed_exec_sha256': hashlib.sha256(record['raw'].encode()).hexdigest()})
    trace = engine.OUT / (label + '.trace')
    trace.open('x').write(''.join(exec_lines))
    events = engine.parser.trace_records(trace.read_text())
    successful = [event for event in events if event['successful']]
    assert not any(event['executable'] == engine.ENV['RUSTDOC'] for event in successful)
    compiler = [event for event in successful if event['executable'] == engine.ENV['RUSTC']]
    engine.write(label + '.exec.json', {'events': events, 'compiler': compiler,
                 'trace_sha256': sha(trace), 'per_pid_exec_joins': joins,
                 'cross_pid_event_order_claimed': False})
    result = decoder.decode(paths, cache, final)
    assert result['final_slots'] == {row['name']: {'bytes': row['bytes'], 'sha256': row['sha256']}
                                     for row in after['entries']}
    if arm == 'baseline':
        assert result['successful_logical_write_bytes'] == result['successful_commits'] == 0
    engine.write(label + '.write-accounting.json', result)
    return compiler
