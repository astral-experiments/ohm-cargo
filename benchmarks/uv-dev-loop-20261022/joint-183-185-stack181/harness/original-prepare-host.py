#!/usr/bin/env python3
"""Prepare public inputs and seal both fresh IR fixtures; never warm a workload."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c
import fixture
import production
from occupancy import require_quiet
from common import ROOT, read, sha


def command(label, argv, cwd=ROOT, env=None):
    stdout, stderr = ROOT / 'logs' / (label + '.stdout'), ROOT / 'logs' / (label + '.stderr')
    with stdout.open('xb') as out, stderr.open('xb') as err:
        result = subprocess.run(argv, cwd=cwd, env=env, stdout=out, stderr=err)
    c.write_once(ROOT / 'metadata' / (label + '.json'), {'command': argv, 'returncode': result.returncode,
                 'stdout_sha256': sha(stdout), 'stderr_sha256': sha(stderr)})
    c.need(result.returncode == 0, 'setup command failed: ' + label)


def runtime_aliases(root):
    result = {}
    for prefix in ('ohm', 'profiling-tools'):
        for path in sorted((Path(root) / prefix).rglob('*')):
            if path.is_symlink():
                resolved = path.resolve()
                result[str(path)] = {'target': os.readlink(path), 'resolved': str(resolved),
                                     'sha256': sha(resolved) if resolved.is_file() else None}
    return result


def validate_template(config, template):
    c.need({k: v for k, v in config.items() if k not in ('env', 'record_files')} ==
           {k: v for k, v in template.items() if k not in ('env', 'record_files')}, 'workload command/path changed')
    c.need(set(template['env']) <= set(config['env']) and
           all(config['env'][k] == v for k, v in template['env'].items()), 'configured environment changed')
    c.need(all(v is None for k, v in config['env'].items() if k not in template['env']), 'new inherited setting was not cleared')
    c.need(config['record_files'] == sorted(set(config['record_files'])), 'nonunique input closure')


def prepare():
    c.runtime_identity()
    c.verify_source(local=False)
    delivery = read(ROOT / 'delivery.json')
    c.need(delivery['host'] == c.HOST and delivery['root'] == str(ROOT), 'wrong delivery')
    for relative, expected in delivery['files'].items():
        c.check_record(ROOT / c.safe_relative(relative), expected)
    binding = read(c.HERE / 'input-binding.json')
    c.need(binding['state'] == 'bound' and binding['controls_source_freeze_sha256'] == sha(c.HERE / 'source-freeze.json'), 'production/CI inputs unbound')
    documents = {role: read(c.HERE / 'provenance' / (role + '.data'))
                 if role not in {'driver', 'baseline_patch', 'candidate_patch'} else None for role in production.ROLES}
    hashes = {role: sha(c.HERE / 'provenance' / (role + '.data')) for role in production.ROLES}
    c.need(hashes == {role: ref['sha256'] for role, ref in binding['production'].items()}, 'production bindings changed')
    production.validate_documents(documents, hashes, binding['variants'])
    c.need(sha(c.HERE / 'provenance/ci.json') == binding['ci']['sha256'], 'CI binding changed')
    production.validate_ci(read(c.HERE / 'provenance/ci.json'))
    require_quiet()
    for directory in ('tmp', 'logs', 'metadata', 'cargo-home', 'active/bin', 'targets', 'shared-cache', 'results', 'benchmark', 'controller/base-configs'):
        (ROOT / directory).mkdir(parents=True, exist_ok=False)
    archive = ROOT / 'assets/ohm-1.99.0-6-x86_64-unknown-linux-gnu.tar.gz'
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
    command('uv-fetch', ['git', '-c', 'credential.helper=', '-C', str(uv), 'fetch', '--depth=1', 'origin', c.UV_COMMIT])
    command('uv-checkout', ['git', '-C', str(uv), 'checkout', '--detach', c.UV_COMMIT])
    for filename, expected in c.RUNTIME_HASHES.items():
        c.need(sha(ROOT / filename) == expected, 'runtime differs: ' + filename)
    c.need(sha(uv / 'Cargo.lock') == c.UV_LOCK, 'uv lock differs')
    identity = fixture.uv_identity()
    catalog = fixture.configuration_presence()
    for path, state in catalog.items():
        if path == '/.cargo/config.toml':
            c.need(state == {'lexists': True, 'sha256': c.ROOT_CONFIG_SHA, 'symlink': None}, 'ancestor root configuration differs')
        elif not Path(path).is_relative_to(uv):
            c.need(not state['lexists'], 'unexpected ancestor configuration: ' + path)
    with (ROOT / 'metadata/ancestor-root-config.toml').open('xb') as stream:
        stream.write(Path('/.cargo/config.toml').read_bytes())
    copied = []
    for kind in ('cache', 'index'):
        source_root = Path('/home/dev-user/.cargo/registry') / kind
        destination = ROOT / 'cargo-home/registry' / kind
        destination.mkdir(parents=True)
        for index, source in enumerate(sorted(source_root.glob('*'))):
            if source.name.startswith(('index.crates.io-', 'github.com-')) and source.is_dir() and not source.is_symlink():
                command(f'public-cache-{kind}-{index}', ['cp', '-a', '--reflink=auto', '--', str(source), str(destination)])
                copied.append({'kind': kind, 'source': str(source), 'destination': str(destination / source.name)})
    removed = sorted(name for name in os.environ if name.startswith(c.ENV_PREFIXES) or name in c.ENV_NAMES)
    common_env = read(c.HERE / 'templates/ir-check.json')['env']
    common_env = {**{name: None for name in removed}, **common_env}
    common_env.pop('CARGO_TARGET_DIR')
    common_env.pop('CARGO_BUILD_BUILD_DIR')
    environment = os.environ.copy()
    for key, value in common_env.items():
        if value is None:
            environment.pop(key, None)
        else:
            environment[key] = value
    fetch_env = dict(environment, CARGO_TARGET_DIR=str(ROOT / 'setup-build'), CARGO_BUILD_BUILD_DIR=str(ROOT / 'setup-shared'))
    command('uv-public-fetch', [str(c.binary_path('baseline')), '-Zohm-defaults=yes', 'fetch', '--locked'], cwd=uv, env=fetch_env)
    c.need(identity == fixture.uv_identity() and catalog == fixture.configuration_presence(), 'source/config changed during fetch')
    tools = {'python-controller': str(Path(sys.executable).resolve())}
    for name in ('taskset', 'env', 'strace', 'git', 'cc', 'c++', 'ld', 'ar', 'pkg-config', 'python3'):
        resolved = shutil.which(name, path=environment['PATH'])
        c.need(resolved, 'missing tool: ' + name)
        tools[name] = str(Path(resolved).resolve())
    for name in ('cc1', 'cc1plus', 'collect2', 'as', 'ld'):
        output = subprocess.check_output([tools['cc'], '-print-prog-name=' + name], env=environment, text=True).strip()
        path = Path(output) if Path(output).is_absolute() else Path(shutil.which(output, path=environment['PATH']) or output)
        c.need(path.is_file(), 'missing compiler helper')
        tools['compiler-' + name] = str(path.resolve())
    libraries, ldd = {}, {}
    for variant in c.VARIANTS:
        output = subprocess.check_output(['/usr/bin/ldd', str(c.binary_path(variant))], env=environment, text=True)
        libraries[variant] = sorted({str(Path(value).resolve()) for value in re.findall(r'/[^\s()]+', output)})
        ldd[variant] = output
    c.need(libraries['baseline'] == libraries['candidate'], 'runtime library inputs differ')
    runtime_files = [path for prefix in ('ohm', 'profiling-tools') for path in sorted((ROOT / prefix).rglob('*'))
                     if path.is_file() and not path.is_symlink()]
    aliases = runtime_aliases(ROOT)
    inputs = set(map(str, runtime_files)) | {row['resolved'] for row in aliases.values() if row['sha256'] is not None}
    inputs |= set(tools.values()) | set(libraries['baseline']) | {str(uv / 'Cargo.lock'), '/etc/ssl/certs/ca-certificates.crt'}
    inputs |= {name for name, state in catalog.items() if state['lexists']}
    configs = {}
    for workflow, _ in c.PLAN:
        template = read(c.HERE / 'templates' / ('ir-' + workflow + '.json'))
        config = {**template, 'env': {**common_env, 'CARGO_TARGET_DIR': str(ROOT / 'targets' / ('ir-' + workflow)),
                                     'CARGO_BUILD_BUILD_DIR': str(ROOT / 'shared-cache' / ('ir-' + workflow))},
                  'record_files': sorted(inputs)}
        validate_template(config, template)
        for key in ('CARGO_TARGET_DIR', 'CARGO_BUILD_BUILD_DIR'):
            c.need(not os.path.lexists(config['env'][key]), 'workflow fixture is not fresh')
        path = c.HERE / 'base-configs' / ('ir-' + workflow + '.json')
        c.write_once(path, config)
        configs[workflow] = sha(path)
    setup = {'state': 'prepared-without-warming', 'prepared_at': c.now(), 'root': str(ROOT), 'host': c.HOST,
             'uv': identity, 'runtime_sha256': c.RUNTIME_HASHES, 'runtime_aliases': aliases,
             'controller_path': c.CONTROLLER_PATH, 'controller_affinity': sorted(os.sched_getaffinity(0)),
             'delivery_sha256': sha(ROOT / 'delivery.json'), 'public_registry_cache_copies': copied,
             'configuration_catalog': catalog, 'cleared_environment_names': removed, 'configured_common_environment': common_env,
             'available_disk_bytes_at_setup': shutil.disk_usage(ROOT).free,
             'tools': tools, 'tool_sha256': {path: sha(path) for path in tools.values()}, 'ldd': ldd,
             'base_config_sha256': configs, 'scope': 'Source/dependency retrieval and sealing only; no uv test execution or workload warming.'}
    c.write_once(ROOT / 'metadata/setup.json', setup)
    inputs |= {str(ROOT / name) for name in delivery['files']}
    inputs |= {str(ROOT / name) for name in ('delivery.json', 'ownership.json', 'delivery-occupancy.json')}
    inputs |= {str(path) for path in [*sorted((ROOT / 'metadata').iterdir()), *sorted((ROOT / 'logs').iterdir()),
                                    *sorted((c.HERE / 'base-configs').glob('*.json'))]}
    assets = {'root': str(ROOT), 'host': c.HOST, 'variants': binding['variants'], 'trees': c.TREES,
              'file_sha256': {path: sha(path) for path in sorted(inputs)}, 'uv': identity,
              'configuration_presence': catalog}
    c.write_once(c.HERE / 'assets.json', assets)
    require_quiet()
    # Replace this setup process: the strict guard must not see an extra controller parent.
    os.execv('/usr/bin/python3', ['/usr/bin/python3', '-I', '-B', str(c.HERE / 'driver.py'), '--prepare'])


if __name__ == '__main__':
    try:
        prepare()
    except BaseException as error:
        if (ROOT / 'metadata').is_dir() and not (ROOT / 'metadata/setup-failed.json').exists():
            c.write_once(ROOT / 'metadata/setup-failed.json', {'state': 'failed', 'at': c.now(), 'error': repr(error), 'traceback': traceback.format_exc()})
        raise
