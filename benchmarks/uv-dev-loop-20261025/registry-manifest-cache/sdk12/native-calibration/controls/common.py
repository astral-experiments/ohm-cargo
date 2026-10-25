"""Registry native follow-up: fixed inputs and durable raw records."""
from pathlib import Path
import datetime
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess

ROOT = Path('/benchmark')
NATIVE = ROOT / 'native-study-01'
PLAN = {}
INPUT = OLD = PROTOCOL = ENV = None
SOURCE = ROOT / 'uv/crates/uv/src/lib.rs'
PARTS = ('target', 'shared', 'package-home')
ARMS = ('baseline', 'candidate')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def read_ref(row):
    path = Path(row['path'])
    assert path.is_file() and not path.is_symlink() and sha(path) == row['sha256']
    return json.loads(path.read_bytes())


def ref(path):
    return {'path': str(path), 'sha256': sha(path)}


def identity(path):
    path = Path(path)
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode)
    return {'path': str(path), 'bytes': info.st_size, 'mode': stat.S_IMODE(info.st_mode), 'sha256': sha(path)}


def verify_file(row):
    assert identity(row['path']) == row


def load(name, path, initial=None):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if initial:
        module.__dict__.update(initial)
    spec.loader.exec_module(module)
    return module


def configure(path, digest):
    global INPUT, OLD, PROTOCOL, ENV
    assert sha(path) == digest
    INPUT = json.loads(Path(path).read_bytes())
    assert INPUT['state'] == 'bound-registry-native-inputs'
    OLD = read_ref(INPUT['instruction_inputs'])
    PROTOCOL = read_ref(INPUT['protocol'])
    ENV = dict(OLD['cargo_environment'])
    assert INPUT['hostname'] == OLD['host']['hostname'] == os.uname().nodename
    assert sha('/etc/machine-id') == OLD['host']['machine_id_sha256']
    assert os.uname().release == OLD['host']['kernel'] and os.getuid() == OLD['host']['uid']
    assert str(ROOT) == OLD['root'] and str(NATIVE) == PROTOCOL['native_root']
    assert not {'LD_PRELOAD', 'RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER', 'CARGO_LOG'} & ENV.keys()
    assert PROTOCOL['command'] == [str(ROOT / 'bin/cargo'), '-Zohm-defaults=yes', 'check', '--locked', '--offline', '-j', '8']
    import admission
    admission.validate_bound_input(INPUT, OLD, PROTOCOL, read_ref)
    return INPUT


def fixed_guard():
    assert INPUT['hostname'] == os.uname().nodename
    assert sha('/etc/machine-id') == OLD['host']['machine_id_sha256']
    assert identity(SOURCE) == OLD['source']
    assert identity(ROOT/'bin/cargo') == OLD['original_cargo']
    for key in ('instruction_inputs','protocol','instruction_release'):
        read_ref(INPUT[key])
    assert sha(NATIVE/'source-original.rs') == OLD['source']['sha256']
    for values in INPUT['native_diagnostics'].values():
        for row in values.values():assert sha(row['path']) == row['sha256']
    git_env = {'PATH':'/usr/bin:/bin','HOME':'/benchmark-home','LANG':'C.UTF-8','GIT_OPTIONAL_LOCKS':'0'}
    head = subprocess.run(['/usr/bin/git','-C',str(ROOT/'uv'),'rev-parse','HEAD'],
                          capture_output=True,text=True,check=True,env=git_env)
    assert head.stdout.strip() == PROTOCOL['pins']['uv'] and not head.stderr
    diff = subprocess.run(['/usr/bin/git','-C',str(ROOT/'uv'),'diff','--name-only','HEAD','--'],
                          capture_output=True,text=True,check=True,env=git_env)
    assert not diff.stdout and not diff.stderr
    for relative, row in OLD['files'].items():
        verify_file(dict(row, path=str(ROOT / relative)))
    for relative, target in OLD['aliases'].items():
        path = ROOT / relative
        assert path.is_symlink() and os.readlink(path) == target
    for row in INPUT['controls'].values():
        assert sha(row['path']) == row['sha256']
    for row in INPUT['tools'].values():
        verify_file(row)
    for name, target in INPUT['tool_aliases'].items():
        assert Path(name).is_symlink() and os.readlink(name) == target
    for row in OLD['variants'].values():
        verify_file(row['artifact'])
    assert sha(ROOT / 'uv/Cargo.lock') == OLD['lock_sha256']
    for row in OLD['configuration_context']:
        path = Path(row['path'])
        assert os.path.lexists(path) == row['exists']
        if row['exists']:
            assert sha(path) == row['sha256'] and stat.S_IMODE(path.stat().st_mode) == row['mode']
    driver = Path(INPUT['driver']['path']).stat()
    assert [driver.st_dev, driver.st_ino, driver.st_ctime_ns] == INPUT['driver']['inode_identity']
    assert sha(INPUT['driver']['path']) == INPUT['driver']['sha256']


def context():
    workspaces = ROOT / 'target/debug/build/workspaces'
    registries = ROOT / 'shared/debug/build/registries'
    info = ROOT / 'target/.rustc_info.json'
    return {'workspace_roots': sorted(p.name for p in workspaces.iterdir()),
            'workspace_contexts': sorted(str(p.relative_to(workspaces)) for p in workspaces.glob('*/*') if p.is_dir()),
            'registry_contexts': sorted(p.name for p in registries.iterdir()) if registries.is_dir() else None,
            'rustc_info': {'sha256': sha(info), 'bytes': info.stat().st_size,
                           'mtime_ns': info.stat().st_mtime_ns, 'inode': info.stat().st_ino}}


def source_write(data, allowed):
    current=sha(SOURCE)
    assert current in allowed, 'source changed outside this owner'
    temporary = SOURCE.with_name(SOURCE.name + '.N-native-writing')
    assert not temporary.exists()
    if current==hashlib.sha256(data).hexdigest():return
    with temporary.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, OLD['source']['mode'])
    os.replace(temporary, SOURCE)
    assert sha(SOURCE) == hashlib.sha256(data).hexdigest()


def install_cargo(arm):
    assert arm in ('original', 'baseline', 'candidate')
    active = ROOT/'bin/cargo'
    slots = NATIVE/'runtime-copies'
    rows = INPUT['runtime_identities']
    def verify(which, path):
        row = rows[which]
        assert identity(path) == {k: v for k, v in dict(row, path=str(path)).items() if k not in ('dev', 'inode')}
        info = path.stat()
        assert [info.st_dev, info.st_ino] == [row['dev'], row['inode']]
    if not active.exists():
        # Recovery of a journaled interrupted rename can only restore the original.
        assert arm == 'original'
        verify(arm, slots/arm)
        os.rename(slots/arm, active)
        verify(arm, active)
        return
    active_digest = sha(active)
    matches = [name for name, row in rows.items() if active_digest == row['sha256']]
    assert len(matches) == 1
    current = matches[0]
    verify(current, active)
    if current == arm:
        return
    assert not (slots/current).exists()
    verify(arm, slots/arm)
    with (NATIVE/'runtime-moves.jsonl').open('a') as stream:
        stream.write(json.dumps({'from': current, 'to': arm, 'utc': utc(),
                                'source_inode': rows[arm]['inode']})+'\n')
        stream.flush(); os.fsync(stream.fileno())
    os.rename(active, slots/current)
    os.rename(slots/arm, active)
    verify(arm, active)


def diagnostics(text):
    # Same native diagnostic projection as the accepted instruction validator.
    return re.sub(r'^\s*Finished .* in .*$', '', text, flags=re.M)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sync_owned(path, log):
    assert Path(path).is_relative_to(NATIVE)
    result = subprocess.run(['/usr/bin/sync', '-f', str(path)], stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=300)
    save(log, {'argv': ['/usr/bin/sync', '-f', str(path)], 'returncode': result.returncode,
               'stdout': result.stdout.decode(), 'stderr': result.stderr.decode(),
               'device': Path(path).stat().st_dev, 'kernel': os.uname().release})
    assert result.returncode == 0 and not result.stdout and not result.stderr
