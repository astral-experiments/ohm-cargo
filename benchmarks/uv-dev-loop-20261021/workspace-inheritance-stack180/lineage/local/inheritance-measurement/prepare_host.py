#!/usr/bin/env python3
"""Prepare and seal fresh inheritance inputs; never warm or measure a workload."""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tarfile

ROOT = Path('/tmp/ohm-hillclimb-20261021-inheritance-measurement')
CONTROL = ROOT / 'controller'
UV_COMMIT = '3d82a6ad5a7eab8c68236553b7846517767c4b61'
ARCHIVE_SHA = '98a4f4f99ea1ff36e10209258724426496afbbcab14d746294fe53a2fedad37c'
GLOBAL_CONFIG_SHA = '24095bd6315880162c8f660917100ac36638cb73778dd9ec6f1c9026ea87b178'
RUNTIME = {
    'ohm/bin/rustc': '6109cff145371a50c4f62b61908d2ffbf6d259b180c8effde07baa426aab682a',
    'ohm/bin/rustdoc': '0b7d9ded49eb9ecc73097a7bb3bb286e1722ac7143d7ca7d2d7c524c55d5684e',
    'ohm/lib/librustc_driver-b03bf00bec23bb9a.so': 'a3a5d8cc86af464504170220d142c4ea1129434e2d5e741755feec6f9f35a436',
    'uv/Cargo.lock': '747296375bb1889689f3bbb1e0303bddd071d6a65117c00be50856448260d014',
}
NAMES = {'baseline': 'inheritance-stack180-baseline', 'candidate': 'inheritance-stack180-shared'}
PREFIXES = ('CARGO_', 'RUST', '__CARGO_', 'LD_', 'DYLD_', 'MALLOC', '_RJEM_', 'JEMALLOC',
            'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS', 'PKG_CONFIG')
KNOWN_ENV = ('CC', 'CXX', 'AR', 'RANLIB', 'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS',
             'GLIBC_TUNABLES', 'MALLOC_CONF', 'MALLOC_CONF_2', '_RJEM_MALLOC_CONF', 'MALLOC_CHECK_',
             'MALLOC_PERTURB_', 'MALLOC_ARENA_MAX', 'MALLOC_ARENA_TEST', 'MALLOC_MMAP_THRESHOLD_',
             'MALLOC_TRIM_THRESHOLD_', 'MALLOC_TOP_PAD_', 'MALLOC_MMAP_MAX_', 'LD_PRELOAD',
             'LD_LIBRARY_PATH', 'LD_AUDIT', 'DYLD_LIBRARY_PATH', 'DYLD_FALLBACK_LIBRARY_PATH',
             'DYLD_INSERT_LIBRARIES', 'RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER', 'RUSTFLAGS',
             'RUSTDOCFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_ENCODED_RUSTDOCFLAGS',
             'CARGO_LOG', 'CARGO_LOG_PROFILE', 'CARGO_TARGET_DIR', 'CARGO_BUILD_BUILD_DIR')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def command(label, argv, cwd=ROOT, env=None):
    stdout, stderr = ROOT / 'logs' / (label + '.stdout'), ROOT / 'logs' / (label + '.stderr')
    with stdout.open('xb') as out, stderr.open('xb') as err:
        result = subprocess.run(argv, cwd=cwd, env=env, stdout=out, stderr=err)
    write(ROOT / 'metadata' / (label + '.json'), {'command': argv, 'returncode': result.returncode,
          'stdout_sha256': sha(stdout), 'stderr_sha256': sha(stderr)})
    assert result.returncode == 0, (label, result.returncode)


assert Path(__file__).resolve() == CONTROL / 'prepare_host.py'
assert socket.gethostname() == 'charlie-oss-2'
assert ROOT.resolve() == ROOT and ROOT.stat().st_uid == os.getuid() == 1000 and Path('/').stat().st_uid == 0
delivery = json.loads((ROOT / 'delivery.json').read_text())
assert delivery['root'] == str(ROOT) and delivery['host'] == socket.gethostname()
assert json.loads((ROOT / 'ownership.json').read_text())['delivery_sha256'] == sha(ROOT / 'delivery.json')
for relative, digest in delivery['files'].items():
    assert sha(ROOT / relative) == digest, relative
spec = importlib.util.spec_from_file_location('reference', CONTROL / 'reference-native-controller.py')
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)
ref.ROOT = ROOT
sys.path.insert(0, str(CONTROL))
from occupancy import require_quiet
require_quiet()
for directory in ('tmp', 'logs', 'metadata', 'cargo-home', 'active/bin', 'targets', 'shared-cache', 'results', 'controller/base-configs'):
    (ROOT / directory).mkdir(parents=True, exist_ok=False)
archive = ROOT / 'assets/ohm-1.99.0-6-x86_64-unknown-linux-gnu.tar.gz'
assert sha(archive) == ARCHIVE_SHA
unpack = ROOT / 'toolchain-unpacked'
unpack.mkdir()
components = {'rustc', 'rust-std-x86_64-unknown-linux-gnu'}
with tarfile.open(archive, 'r|gz') as stream:
    for member in stream:
        parts = Path(member.name).parts
        if len(parts) > 1 and parts[1] in components:
            stream.extract(member, path=unpack, filter='data')
for component in sorted(components):
    source = unpack / 'rust-1.99.0-dev-x86_64-unknown-linux-gnu' / component
    for child in source.iterdir():
        if child.is_dir():
            shutil.copytree(child, ROOT / 'ohm' / child.name, symlinks=True, dirs_exist_ok=True)
for filename in ('valgrind_1%3a3.22.0-0ubuntu3_amd64.deb', 'libc6-dbg_2.39-0ubuntu8.9_amd64.deb'):
    command(filename.split('_')[0] + '-unpack', ['/usr/bin/dpkg-deb', '-x', str(ROOT / 'assets' / filename),
                                               str(ROOT / 'profiling-tools/valgrind')])
uv = ROOT / 'uv'
command('uv-init', ['git', 'init', '-q', str(uv)])
command('uv-origin', ['git', '-C', str(uv), 'remote', 'add', 'origin', 'https://github.com/astral-sh/uv.git'])
command('uv-fetch', ['git', '-c', 'credential.helper=', '-C', str(uv), 'fetch', '--depth=1', 'origin', UV_COMMIT])
command('uv-checkout', ['git', '-C', str(uv), 'checkout', '--detach', UV_COMMIT])
assert not subprocess.check_output(['git', '-C', str(uv), 'status', '--porcelain'])
for filename, digest in RUNTIME.items():
    assert sha(ROOT / filename) == digest, filename
catalog = ref.configuration_presence()
for path, state in catalog.items():
    if path == '/.cargo/config.toml':
        assert state == {'lexists': True, 'sha256': GLOBAL_CONFIG_SHA, 'symlink': None}, state
    elif not Path(path).is_relative_to(uv):
        assert not state['lexists'], path
global_config = Path('/.cargo/config.toml').read_bytes()
assert hashlib.sha256(global_config).hexdigest() == GLOBAL_CONFIG_SHA
with (ROOT / 'metadata/ancestor-root-config.toml').open('xb') as stream:
    stream.write(global_config)
copied = []
for kind in ('cache', 'index'):
    source_root = Path('/home/dev-user/.cargo/registry') / kind
    destination = ROOT / 'cargo-home/registry' / kind
    destination.mkdir(parents=True)
    for index, source in enumerate(sorted(source_root.glob('*'))):
        if source.name.startswith(('index.crates.io-', 'github.com-')) and source.is_dir() and not source.is_symlink():
            command(f'public-cache-{kind}-{index}', ['cp', '-a', '--reflink=auto', '--', str(source), str(destination)])
            copied.append({'kind': kind, 'source': str(source), 'destination': str(destination / source.name)})
removed = sorted(name for name in os.environ if name.startswith(PREFIXES) or name in KNOWN_ENV)
common = {name: None for name in {*removed, *KNOWN_ENV}}
common.update({'CARGO_HOME': str(ROOT / 'cargo-home'), 'RUSTC': str(ROOT / 'ohm/bin/rustc'),
               'RUSTDOC': str(ROOT / 'ohm/bin/rustdoc'), 'CARGO_BUILD_JOBS': '8', 'CARGO_TERM_COLOR': 'never',
               'PATH': str(ROOT / 'active/bin') + ':' + str(ROOT / 'ohm/bin') + ':/usr/bin:/bin',
               'SSL_CERT_FILE': '/etc/ssl/certs/ca-certificates.crt', 'SSL_CERT_DIR': '/usr/lib/ssl/certs',
               'TMPDIR': str(ROOT / 'tmp'),
               'VALGRIND_LIB': str(ROOT / 'profiling-tools/valgrind/usr/libexec/valgrind')})
environment = os.environ.copy()
for key, value in common.items():
    if value is None:
        environment.pop(key, None)
    else:
        environment[key] = value
for filename in NAMES.values():
    (CONTROL / 'binaries' / ('cargo-' + filename)).chmod(0o755)
baseline = CONTROL / 'binaries/cargo-inheritance-stack180-baseline'
fetch_env = dict(environment, CARGO_TARGET_DIR=str(ROOT / 'setup-build'), CARGO_BUILD_BUILD_DIR=str(ROOT / 'setup-shared'))
command('uv-public-fetch', [str(baseline), '-Zohm-defaults=yes', 'fetch', '--locked'], cwd=uv, env=fetch_env)
assert sha(uv / 'Cargo.lock') == RUNTIME['uv/Cargo.lock']
assert not subprocess.check_output(['git', '-C', str(uv), 'status', '--porcelain'])
assert catalog == ref.configuration_presence()
tools = {'python-controller': str(Path(sys.executable).resolve())}
for name in ('taskset', 'env', 'strace', 'git', 'cc', 'c++', 'ld', 'ar', 'pkg-config', 'python3'):
    resolved = shutil.which(name, path=environment['PATH'])
    assert resolved, name
    tools[name] = str(Path(resolved).resolve())
for name in ('cc1', 'cc1plus', 'collect2', 'as', 'ld'):
    output = subprocess.check_output([tools['cc'], '-print-prog-name=' + name], env=environment, text=True).strip()
    path = Path(output) if Path(output).is_absolute() else Path(shutil.which(output, path=environment['PATH']) or output)
    assert path.is_file(), (name, output)
    tools['compiler-' + name] = str(path.resolve())
libraries = {}
ldd = {}
for variant, name in NAMES.items():
    output = subprocess.check_output(['/usr/bin/ldd', str(CONTROL / 'binaries' / ('cargo-' + name))], env=environment, text=True)
    libraries[variant] = sorted({str(Path(value).resolve()) for value in re.findall(r'/[^\s()]+', output)})
    ldd[variant] = output
assert libraries['baseline'] == libraries['candidate']
runtime_files = [path for prefix in ('ohm', 'profiling-tools') for path in sorted((ROOT / prefix).rglob('*'))
                 if path.is_file() and not path.is_symlink()]
record_files = list(dict.fromkeys([*map(str, runtime_files), *tools.values(), *libraries['baseline'],
                                  str(uv / 'Cargo.lock'), '/etc/ssl/certs/ca-certificates.crt',
                                  *[name for name, state in catalog.items() if state['lexists']]]))
configs = {}
for phase in ('ir', 'native'):
    for workflow in ('check', 'test'):
        label = phase + '-' + workflow
        native = ['/usr/bin/taskset', '-c', '0-7', '{cargo}', '-Zohm-defaults=yes', workflow]
        if workflow == 'test':
            native.append('--no-run')
        native.extend(['--locked', '--offline', '-j', '8'])
        config = {'cwd': str(uv), 'canonical_executable': str(ROOT / 'active/bin/cargo'),
                  'variants': {variant: str(CONTROL / 'binaries' / ('cargo-' + name)) for variant, name in NAMES.items()},
                  'record_files': record_files, 'command': native, 'prepare_command': native,
                  'env': {**common, 'CARGO_TARGET_DIR': str(ROOT / 'targets' / label),
                          'CARGO_BUILD_BUILD_DIR': str(ROOT / 'shared-cache' / label)}}
        if phase == 'ir':
            config['command'] = ['/usr/bin/taskset', '-c', '0-7', '/usr/bin/env',
                'LD_PRELOAD=' + str(ROOT / 'profiling-tools/ohm-valgrind-env.so'), 'OHM_BENCH_NORMALIZE_VALGRIND_ENV=1',
                str(ROOT / 'profiling-tools/valgrind/usr/bin/valgrind'), '--tool=callgrind', '--trace-children=no',
                '--extra-debuginfo-path=' + str(ROOT / 'profiling-tools/valgrind/usr/lib/debug'),
                '--callgrind-out-file={output}/callgrind-{stage}-{pair}-{variant}.out', *native[3:]]
            config['metric_files'] = {'cargo_ir': {'format': 'callgrind', 'event': 'Ir',
                                     'path': '{output}/callgrind-{stage}-{pair}-{variant}.out'}}
        else:
            config.update(repetitions=8, repeatable_workload='noop')
        for key in ('CARGO_TARGET_DIR', 'CARGO_BUILD_BUILD_DIR'):
            assert not os.path.lexists(config['env'][key])
        configs[label] = config
        write(CONTROL / 'base-configs' / (label + '.json'), config)
setup = {'state': 'prepared-without-warming', 'prepared_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'root': str(ROOT), 'host': socket.gethostname(), 'uv_commit': UV_COMMIT, 'runtime_sha256': RUNTIME,
         'available_disk_bytes_at_setup': shutil.disk_usage(ROOT).free,
         'delivery_sha256': sha(ROOT / 'delivery.json'), 'public_registry_cache_copies': copied,
         'configuration_catalog': catalog, 'cleared_environment_names': removed,
         'known_global_configuration': {'path': '/.cargo/config.toml', 'sha256': GLOBAL_CONFIG_SHA,
                                        'evidence_copy': 'metadata/ancestor-root-config.toml'},
         'configured_common_environment': common, 'tool_sha256': {path: sha(path) for path in tools.values()},
         'tools': tools, 'ldd': ldd, 'base_config_sha256': {name: sha(CONTROL / 'base-configs' / (name + '.json')) for name in configs},
         'scope': 'Only public source/dependency retrieval, tool inspection and sealing. No workload warmup, uv test execution or performance sample.'}
write(ROOT / 'metadata/setup.json', setup)
files = dict(delivery['files'])
for path in [ROOT / 'delivery.json', ROOT / 'ownership.json', ROOT / 'delivery-occupancy.json', *sorted((ROOT / 'metadata').iterdir()),
             *sorted((ROOT / 'logs').iterdir()), *sorted((CONTROL / 'base-configs').glob('*.json'))]:
    assert path.is_file() and not path.is_symlink()
    files[str(path.relative_to(ROOT))] = sha(path)
assets = {'root': str(ROOT), 'host': socket.gethostname(), 'variants': delivery['variants'],
          'source_trees': delivery['source_trees'], 'files': files}
write(CONTROL / 'assets.json', assets)
require_quiet()
subprocess.run([sys.executable, '-I', '-B', str(CONTROL / 'driver.py'), '--prepare'], check=True)
print(json.dumps({'setup': setup, 'seal_sha256': sha(CONTROL / 'measurement-seal.json'),
                  'assets_sha256': sha(CONTROL / 'assets.json')}, indent=2))
