"""Independent local input/transport checks; never imports experiment controls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile

ROOT = '/tmp/ohm-hillclimb-20261021-inheritance-measurement'
HOST = 'charlie-oss-2'
FREEZE = 'f52a57b667b0708413cb353b2af4164f11fec6a9b8e0025bab4ab8330135ff98'
SEAL = 'b6e765057417644e62cf7cadc4994a05172077f8c9a26bfe6343e6ad377e48ff'
DELIVERY = '9cb40f6d074706a713b60c2c1b17e4ac44bf8294f1fc3ba3973f46912a2e15ec'
DRIVER = '1585116beaab26655de1e86459feb030ebdd31e636a613991241018ace5f3ef3'
CORE = '50d0cb2d4f595ccfa72d463fedb3ff4dadf9dfc1446c749d482d9ede8418c7cf'
REPEATED = '50547460e030aa73e1f48121bf477cf8f4a4538bf1bb577851af54176750b6d3'
PROTOCOL = '5a78491c347b2f8749fe6da44002c863679062e5e3c7393e9508671e813af2da'
UV = '3d82a6ad5a7eab8c68236553b7846517767c4b61'
EXPECTED = {'baseline': '3164f9287711f122fa9636a7816ed8749598706ac5076d66051a036dcef51037',
            'candidate': '3b1a2e4e3654b7b23816fbb54c51072cb356486c36052a5bcd6c4d3d2e6a07e9'}
TREES = {'baseline': '0a392258c801cff734d223a3f9af73d5b5a4e3c0',
         'candidate': 'c4178b67e0b3a64a12b9b58f84b97323b99d734e'}
NAMES = {'baseline': 'inheritance-stack180-baseline', 'candidate': 'inheritance-stack180-shared'}
STAGES = {
    'ir': {'pairs': 12, 'phase': 'confirmation', 'warming_order': ['baseline', 'candidate'],
           'plan': [['check', 20261021111], ['test', 20261021112]]},
    'native': {'pairs': 30, 'phase': 'confirmation', 'warming_order': ['baseline', 'candidate'],
               'plan': [['check', 20261021113], ['test', 20261021114]]},
}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def relative(name):
    need(isinstance(name, str), 'path is not a string')
    path = PurePosixPath(name)
    need(name and name != '.' and not path.is_absolute() and '..' not in path.parts
         and '\\' not in name and str(path) == name, 'unsafe path: ' + repr(name))
    return path


class Evidence:
    def __init__(self, controls, phase):
        self.controls = Path(controls).resolve()
        self.phase = phase
        self.directory = self.controls / 'collections' / phase
        self.remote = self.directory / 'remote'
        freeze_path = self.controls / 'source-freeze.json'
        need(sha(freeze_path) == FREEZE, 'inheritance source freeze changed')
        self.freeze = read(freeze_path)
        for name, digest in self.freeze['files'].items():
            need(sha(self.controls / relative(name)) == digest, 'local frozen control changed: ' + name)
        source_review = read(self.controls / 'source-review.json')
        need(source_review['status'] == 'passed' and source_review['source_freeze_sha256'] == FREEZE, 'source review binding differs')
        transport, receipt = read(self.directory / 'transport.json'), read(self.directory / 'receipt.json')
        self.manifest = read(self.directory / 'transfer-manifest.json')
        need(transport['returncode'] == 0 and receipt['status'] == 'passed', 'collection transport is incomplete')
        need(sha(self.directory / 'payload.tar') == transport['archive_sha256']
             and sha(self.directory / 'transfer.stderr') == transport['stderr_sha256'], 'transport bytes differ')
        need(sha(self.directory / 'transfer-manifest.json') == receipt['transfer_manifest_sha256'], 'transfer manifest differs')
        need(self.manifest['phase'] == receipt['phase'] == phase and self.manifest['root'] == ROOT, 'collection phase/root differs')
        need(self.manifest['seal_sha256'] == receipt['measurement_seal_sha256'] == SEAL
             and self.manifest['delivery_sha256'] == DELIVERY and self.manifest['driver_sha256'] == DRIVER, 'collection identities differ')
        self.files = self.manifest['files']
        seen = set()
        with tarfile.open(self.directory / 'payload.tar', 'r:') as archive:
            for member in archive:
                relative(member.name)
                need(member.isfile() and not member.issym() and not member.islnk()
                     and member.name not in seen, 'unsafe/duplicate archive member')
                seen.add(member.name)
                if member.name == 'transfer-manifest.json':
                    need(archive.extractfile(member).read() == (self.directory / member.name).read_bytes(), 'archived manifest differs')
                    continue
                need(member.name.startswith('remote/'), 'unexpected archive prefix')
                name = member.name[len('remote/'):]
                need(name in self.files, 'unexpected remote member')
                digest = hashlib.sha256()
                size = 0
                with archive.extractfile(member) as source:
                    while chunk := source.read(1024 * 1024):
                        digest.update(chunk)
                        size += len(chunk)
                path = self.remote / relative(name)
                need(path.is_file() and not path.is_symlink() and path.resolve() == path, 'noncanonical extracted file')
                need(digest.hexdigest() == self.files[name] == sha(path)
                     and size == member.size == path.stat().st_size, 'archive/extracted bytes differ: ' + name)
        need(seen == {'transfer-manifest.json'} | {'remote/' + name for name in self.files}, 'archive member set differs')
        actual = set()
        for path in self.remote.rglob('*'):
            need(not path.is_symlink(), 'symlink in extracted evidence')
            if path.is_file():
                actual.add(str(path.relative_to(self.remote)))
        need(actual == set(self.files) and len(actual) == receipt['files'], 'extracted member set/count differs')
        self.seal = self.json('controller/measurement-seal.json')
        self.assets = self.json('controller/assets.json')
        self.setup = self.json('metadata/setup.json')
        self.binding = read(self.controls / 'delivery/binding.json')

    def json(self, name):
        return read(self.remote / relative(name))

    def file(self, remote):
        need(isinstance(remote, str) and remote.startswith(ROOT + '/'), 'file path is outside fixed root')
        name = str(relative(remote[len(ROOT) + 1:]))
        need(name in self.files, 'missing collected raw file: ' + name)
        return self.remote / name

    def bind(self):
        need(sha(self.remote / 'controller/source-freeze.json') == FREEZE
             and sha(self.remote / 'controller/measurement-seal.json') == SEAL
             and sha(self.remote / 'delivery.json') == DELIVERY, 'copied control identity differs')
        need(self.binding['delivery_sha256'] == DELIVERY and self.binding['variants'] == EXPECTED
             and self.binding['source_trees'] == TREES, 'delivery binding differs')
        need(self.assets['root'] == ROOT and self.assets['host'] == HOST
             and self.assets['variants'] == self.seal['variants'] == EXPECTED
             and self.assets['source_trees'] == self.seal['source_trees'] == TREES
             and self.seal['stages'] == STAGES, 'fixed source/binary/stage identity differs')
        need(self.seal['uv']['commit'] == UV and not self.seal['uv']['status'], 'uv identity differs')
        need(self.setup['state'] == 'prepared-without-warming' and self.setup['host'] == HOST
             and self.setup['root'] == ROOT and self.setup['uv_commit'] == UV, 'setup identity differs')
        need(self.setup['configuration_catalog'] == self.seal['configuration_catalog'], 'configuration catalog differs')
        need(self.seal['environment_guard'] == {'forbidden_environment_names': [],
             'absent_system_configurations': ['/etc/_rjem_malloc.conf', '/etc/malloc.conf']}, 'allocator/loader policy differs')
        need(self.setup['known_global_configuration'] == {
            'path': '/.cargo/config.toml', 'sha256': '24095bd6315880162c8f660917100ac36638cb73778dd9ec6f1c9026ea87b178',
            'evidence_copy': 'metadata/ancestor-root-config.toml'}, 'global Cargo configuration differs')
        need(sha(self.remote / 'metadata/ancestor-root-config.toml') == self.setup['known_global_configuration']['sha256'], 'global config evidence bytes differ')
        for name, digest in self.assets['files'].items():
            if name in self.files:
                need(self.files[name] == digest, 'copied asset differs: ' + name)
        for name, digest in self.seal['file_sha256'].items():
            if name.startswith(ROOT + '/') and name[len(ROOT) + 1:] in self.files:
                need(self.files[name[len(ROOT) + 1:]] == digest, 'copied sealed input differs: ' + name)
        for name, digest in self.freeze['files'].items():
            need(self.files['controller/' + name] == digest, 'delivered frozen control differs')
        for name, digest in {'controller/driver.py': DRIVER, 'controller/protocol.json': PROTOCOL,
                             'benchmark/frozen/paired.py': CORE, 'benchmark/frozen/paired_repeated.py': REPEATED}.items():
            need(self.files[name] == digest, 'measurement control differs')
        protocol = self.json('controller/protocol.json')
        need(protocol['base_tree'] == TREES['baseline'] and protocol['candidate_tree'] == TREES['candidate']
             and protocol['uv_commit'] == UV and protocol['gate'] == {
                 'minimum_reduction': 0.01, 'confidence': 0.99, 'bootstrap_resamples': 20000,
                 'bootstrap_seed': 1701, 'exact_two_sided_sign_p_max': 0.01,
                 'both_order_point_effects_positive': True}, 'protocol identity/gates differ')
        audit = self.json('controller/cohort/results/audit-pair.json')
        need(self.files['controller/cohort/results/audit-pair.json']
             == '00fee70efe3e5f94ee55e7a76ac1baf921659f1e1895606577b55506316f105e', 'fresh production pair audit differs')
        need(audit['common_build_inputs_sha256'] == 'd3c153d203c6a933add9ce89a6b496ae8fcb4b9039376d877854359d9209caeb', 'build cohort changed')
        for variant, name in NAMES.items():
            row = next(row for row in audit['records'] if row['variant'] == name)
            build = self.json(f'controller/cohort/results/cargo-{name}.build.json')
            strip = self.json(f'controller/cohort/results/cargo-{name}.strip.json')
            need(row['source_tree'] == build['observed_source_tree'] == TREES[variant]
                 and row['stripped_sha256'] == strip['stripped_sha256'] == EXPECTED[variant]
                 and row['verified_allocated_sections'] == 31, 'production binary/source/strip identity differs')
            need(self.assets['files'][f'controller/binaries/cargo-{name}'] == EXPECTED[variant], 'delivered binary is not the fresh pair')
        need(audit['records'][0]['actual_rustc_settings'] == audit['records'][1]['actual_rustc_settings']
             and audit['records'][0]['direct_dependency_names'] == audit['records'][1]['direct_dependency_names'], 'production settings/dependencies differ')
        correctness = self.json('controller/correctness/correctness-seal.json')
        reviewed = self.json('controller/correctness/root-correctness-review.json')
        need(correctness['validation_passed'] and correctness['tests'] == 28
             and correctness['failed'] == correctness['ignored'] == 0
             and correctness['source_tree'] == reviewed['source_tree'] == TREES['candidate']
             and reviewed['status'] == 'passed'
             and reviewed['correctness_seal_sha256'] == self.files['controller/correctness/correctness-seal.json'], 'correctness prerequisite differs')
        for name, digest in correctness['files'].items():
            need(self.files['controller/correctness/' + name] == digest, 'correctness evidence differs')
        ci = self.json('controller/source-ci.json')
        need(ci['status'] == 'completed' and ci['conclusion'] == 'success' and ci['required_jobs_succeeded']
             and ci['head_sha'] == 'd81a093becb4321a975522624c2a383970f0d164', 'source CI prerequisite differs')

    def config(self, phase, workflow):
        label = phase + '-' + workflow
        config = self.json('benchmark/' + label + '.json')
        base = self.json('controller/base-configs/' + label + '.json')
        need({k: v for k, v in config.items() if k != 'record_files'}
             == {k: v for k, v in base.items() if k != 'record_files'}, 'base workload fields changed')
        extra = [ROOT + '/' + name for name in self.assets['files']]
        extra += [ROOT + '/controller/assets.json', ROOT + '/controller/measurement-seal.json',
                  ROOT + '/benchmark/' + label + '.json', ROOT + '/metadata/' + label + '-preflight/report.json']
        if phase == 'native':
            extra.append(ROOT + '/metadata/native-prerequisite.json')
        need(config['record_files'] == list(dict.fromkeys(base['record_files'] + extra)), 'record_files is not the exact base expansion')
        canonical = ROOT + '/active/bin/cargo'
        native_command = ['/usr/bin/taskset', '-c', '0-7', '{cargo}', '-Zohm-defaults=yes', workflow]
        if workflow == 'test':
            native_command.append('--no-run')
        native_command += ['--locked', '--offline', '-j', '8']
        need(config['cwd'] == ROOT + '/uv' and config['canonical_executable'] == canonical
             and config['prepare_command'] == native_command, 'canonical path or build-only workload differs')
        need(config['variants'] == {key: ROOT + '/controller/binaries/cargo-' + value for key, value in NAMES.items()}, 'variant paths differ')
        for key, suffix in [('CARGO_HOME', 'cargo-home'), ('CARGO_TARGET_DIR', 'targets/' + label),
                            ('CARGO_BUILD_BUILD_DIR', 'shared-cache/' + label)]:
            need(config['env'][key] == ROOT + '/' + suffix, 'fixture path differs')
        need(all(value is None for key, value in config['env'].items()
                 if key.startswith(('LD_', 'DYLD_', 'MALLOC', '_RJEM_', 'JEMALLOC')) or key == 'GLIBC_TUNABLES'), 'native loader/allocator override')
        if phase == 'native':
            need(config['command'] == native_command and config['repetitions'] == 8
                 and config['repeatable_workload'] == 'noop' and 'metric_files' not in config, 'native design differs')
        else:
            prefix = ['/usr/bin/taskset', '-c', '0-7', '/usr/bin/env',
                      'LD_PRELOAD=' + ROOT + '/profiling-tools/ohm-valgrind-env.so',
                      'OHM_BENCH_NORMALIZE_VALGRIND_ENV=1', ROOT + '/profiling-tools/valgrind/usr/bin/valgrind',
                      '--tool=callgrind', '--trace-children=no',
                      '--extra-debuginfo-path=' + ROOT + '/profiling-tools/valgrind/usr/lib/debug',
                      '--callgrind-out-file={output}/callgrind-{stage}-{pair}-{variant}.out']
            need(config['command'] == prefix + native_command[3:] and 'repetitions' not in config
                 and config['metric_files'] == {'cargo_ir': {'format': 'callgrind', 'event': 'Ir',
                      'path': '{output}/callgrind-{stage}-{pair}-{variant}.out'}}, 'Cargo-only instruction command differs')
        return config
