"""Run exactly the frozen stock Wild binary while this caller still holds its real inputs."""
import fcntl
import hashlib
import json
import mmap
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

R = Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028/whole-wild-width-v1')
STOCK = R / 'stock-wild'
WILD = '0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
WIDTHS = (1, 8, 2, 4, 16, 3, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15)


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write(path, value):
    with path.open('x') as f:
        json.dump(value, f, sort_keys=True, separators=(',', ':'))


def save_body(path):
    """Use one independent physical copy per raw checksum across every caller and width."""
    h = sha(path)
    dest = R / 'bodies' / h
    if not dest.exists():
        temp = dest.with_name(h + '.' + str(os.getpid()))
        shutil.copyfile(path, temp)
        assert sha(temp) == h
        try:
            os.link(temp, dest)
        except FileExistsError:
            pass
        temp.unlink()
    return h


def run_native(argv, *, log=None):
    with subprocess.Popen(argv, executable=STOCK, close_fds=False, stdout=log, stderr=log) as child:
        try:
            status = child.wait(timeout=180)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
            raise
        assert status == 0, (status, argv[0], argv[-1])
        return child.pid


def dep_names(path, output):
    raw = path.read_text().splitlines()
    pre = str(output) + ': '
    assert raw[0].startswith(pre) and '\\' not in raw[0]
    names = raw[0][len(pre):].split()
    assert len(names) > 30 and len(names) == len(set(names))
    assert {n + ':' for n in names} == set(raw[1:]) - {''}
    return set(names)


def file_inputs(names):
    entries = {}
    for name in sorted(names):
        path = Path(name)
        st = path.stat()
        assert stat.S_ISREG(st.st_mode)
        entries[name] = {'path': str(path.resolve(strict=True)), 'bytes': st.st_size, 'sha256': sha(path)}
    return entries


def special(argv):
    resolutions = [a.split('=', 2)[-1] for a in argv if a.startswith('-plugin-opt=-fresolution=')]
    raw_dylibs = [a[2:] for a in argv if a.startswith('-L') and a.endswith('/raw-dylibs')]
    symbols = [a for a in argv if a.endswith('/symbols.o')]
    assert len(resolutions) == len(raw_dylibs) == len(symbols) == 1
    assert Path(symbols[0]).parent == Path(raw_dylibs[0]).parent
    raw = Path(raw_dylibs[0]); res = Path(resolutions[0])
    assert not raw.is_symlink() and (not raw.exists() or raw.is_dir() and not list(raw.iterdir()))
    assert not res.is_symlink() and (not res.exists() or res.is_file())
    return {'resolution': str(res), 'resolution_sha256': sha(res) if res.is_file() else None,
            'raw_dylibs': str(raw), 'raw_dylibs_empty_directory': raw.is_dir(),
            'symbols': symbols[0], 'symbols_sha256': sha(Path(symbols[0]))}


def operands(argv, out):
    files = set()
    for i, a in enumerate(argv[1:], 1):
        if argv[i-1] == '-o':
            assert a == str(out)
            continue
        assert not a.startswith('@'), 'non-expanded response file requires a new registration'
        assert not a.startswith(('--threads', '--dependency-file', '--experimental-', '--files-per-group'))
        if a.startswith('-plugin-opt=-fresolution='):
            p = Path(a.split('=', 2)[-1])
        elif a.startswith('-plugin-opt='):
            p = Path(a[len('-plugin-opt='):])
        elif a.startswith('-'):
            continue
        else:
            p = Path(a)
        if p.is_file():
            files.add(str(p))
    assert len(files) > 8
    return files


def capture(argv):
    if '-o' not in argv:
        os.execv(STOCK, argv)
    assert set(os.sched_getaffinity(0)) == set(range(16))
    assert sha(STOCK) == WILD and shutil.disk_usage(R).free > 38 * 2**30
    phase = os.environ['WILD_PHASE']
    assert not {k for k in os.environ if k.startswith('WILD_') and k!='WILD_PHASE'}
    assert 'RAYON_NUM_THREADS' not in os.environ
    out = Path(argv[argv.index('-o') + 1])
    assert str(out) in read(R/'targets.json')
    cube = R / 'captures' / phase / str(os.getpid())
    cube.mkdir()
    write(cube/'raw-argv.json', argv)
    before_extra = special(argv)
    literal = operands(argv, out)
    literal_before = file_inputs(literal)
    # In default mode the child inherits the actual GCC file descriptors, including
    # the jobserver. Preserve this file's inode and metadata for the calling rustc.
    default_pid = run_native(argv)
    raw_default = save_body(out)
    original = out.with_name('.ohm-wide-'+str(os.getpid())+'-default-elf')
    assert not original.exists() and not original.is_symlink()
    os.rename(out, original)
    original_stat = original.stat()
    first_inputs = None
    rows = []
    try:
        # The original spelling, output path and live Rust/GCC temporary files remain
        # available until we return to collect2. Private probes cannot consume those
        # files of another occurrence. No width or name is inferred.
        with (R/'gates'/str(int(hashlib.sha256(str(out).encode()).hexdigest(),16)%3)).open('r') as gate, (cube/'probe-output').open('xb') as log:
            fcntl.flock(gate, fcntl.LOCK_EX)
            for width in WIDTHS:
                report = cube / (str(width) + '.d')
                plain = [*argv, '--threads=' + str(width)]
                reporting = [*plain, '--dependency-file=' + str(report)]
                assert shutil.disk_usage(R).free > 38 * 2**30
                report_pid = run_native(reporting, log=log)
                names = dep_names(report, out) | literal
                if first_inputs is None:
                    first_inputs = file_inputs(names)
                    assert all(first_inputs[x] == v for x,v in literal_before.items())
                    assert any(Path(x).name.startswith('libc.so') for x in names)
                    assert any(Path(x).name.startswith('libgcc_s.so') for x in names)
                    write(cube/'positive-inputs.json', first_inputs)
                assert set(first_inputs) == names
                report_body = sha(out)
                plain_pid = run_native(plain, log=log)
                plain_body = save_body(out)
                assert plain_body == report_body, (str(out), width, plain_body, report_body)
                rows.append({'width':width, 'plain_sha256':plain_body, 'depfile_sha256':report_body,
                             'dependency_receipt':sha(report), 'plain_pid':plain_pid, 'depfile_pid':report_pid,
                             'plain_exit':0, 'depfile_exit':0, 'plain_argv_sha256':digest(plain),
                             'reported_argv_sha256':digest(reporting)})
            assert log.tell() < 2**20
            assert file_inputs(first_inputs) == first_inputs and special(argv) == before_extra
    finally:
        os.replace(original, out)
    assert out.stat().st_ino == original_stat.st_ino and out.stat().st_mtime_ns == original_stat.st_mtime_ns
    assert sha(out) == raw_default and raw_default in {r['plain_sha256'] for r in rows}
    entry={'phase':phase,'pid':os.getpid(),'default_pid':default_pid,'default_exit':0,'target':str(out),
           'raw_sha256':raw_default,'wild_sha256':WILD,'argv_sha256':digest(argv),
           'inputs_sha256':digest(first_inputs),'input_names':len(first_inputs),
           'input_bytes':sum(v['bytes'] for v in first_inputs.values()), 'literal_bytes_rechecked':True,
           'special_inputs':before_extra,'widths':rows}
    write(cube/'capture.json',entry)


if __name__ == '__main__':
    capture(sys.argv[1:])
