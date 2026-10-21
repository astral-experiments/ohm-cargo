#!/usr/bin/env python3
"""Seal all four fixed inheritance workflows; execute only an explicit phase."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

SELF = Path(__file__).resolve()
ROOT = SELF.parents[1]
EXPECTED_ROOT = Path('/tmp/ohm-hillclimb-20261021-inheritance-measurement')
ASSETS = SELF.parent / 'assets.json'
SEAL = SELF.parent / 'measurement-seal.json'
CORE = ROOT / 'benchmark/frozen/paired.py'
RUNNER = ROOT / 'benchmark/frozen/paired_repeated.py'
REFERENCE = SELF.parent / 'reference-native-controller.py'
CORE_SHA = '50d0cb2d4f595ccfa72d463fedb3ff4dadf9dfc1446c749d482d9ede8418c7cf'
RUNNER_SHA = '50547460e030aa73e1f48121bf477cf8f4a4538bf1bb577851af54176750b6d3'
REFERENCE_SHA = '75206df60ff0a3305dd41410bf72a8f738cd1ab3a7f04adb5c2d12b8aa8c1573'
PROTOCOL_SHA = '5a78491c347b2f8749fe6da44002c863679062e5e3c7393e9508671e813af2da'
BUILD_MANIFEST_SHA = 'ff3455f081f9b08c06f26fbe029fcfcdbe243b0e905a96f7237181ea5d6806cd'
BUILD_DRIVER_SHA = '21707e2fbcecb710adddf24c4776b0e2995a91051672f1e026b43982da68a882'
UV_COMMIT = '3d82a6ad5a7eab8c68236553b7846517767c4b61'
NAMES = {'baseline': 'inheritance-stack180-baseline', 'candidate': 'inheritance-stack180-shared'}
TREES = {'baseline': '0a392258c801cff734d223a3f9af73d5b5a4e3c0',
         'candidate': 'c4178b67e0b3a64a12b9b58f84b97323b99d734e'}
STAGES = {
    'ir': {'pairs': 12, 'phase': 'confirmation', 'warming_order': ['baseline', 'candidate'],
           'plan': [('check', 20261021111), ('test', 20261021112)]},
    'native': {'pairs': 30, 'phase': 'confirmation', 'warming_order': ['baseline', 'candidate'],
               'plan': [('check', 20261021113), ('test', 20261021114)]},
}
SAMPLE_FIELDS = ('stage', 'pair', 'order', 'position', 'variant', 'started_at', 'returncode',
                 'wall_ns', 'user_seconds', 'system_seconds', 'minor_faults', 'major_faults',
                 'voluntary_context_switches', 'involuntary_context_switches', 'stdout', 'stderr')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_module(name, path, expected):
    assert sha(path) == expected, path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def paths(phase, workflow):
    label = phase + '-' + workflow
    return {'config': ROOT / 'benchmark' / (label + '.json'),
            'preflight': ROOT / 'metadata' / (label + '-preflight'),
            'output': ROOT / 'results' / label,
            'log': ROOT / 'logs' / (label + '-runner.log')}


def phase_status(phase):
    return ROOT / 'results' / (phase + '-status.json')


def reference(phase):
    """Reuse the reviewed preflight and grouped audit without modifying their code."""
    module = load_module('inheritance_reference_' + phase, REFERENCE, REFERENCE_SHA)
    module.ROOT = ROOT
    module.SELF = SELF
    module.CORE = CORE
    module.RUNNER = RUNNER
    module.EXPECTED = read(ASSETS)['variants']
    module.stage = lambda: STAGES[phase]
    module.paths = lambda workflow: paths(phase, workflow)
    occupancy = load_module('inheritance_occupancy', SELF.parent / 'occupancy.py',
                            read(ASSETS)['files']['controller/occupancy.py'])
    module.quiet = occupancy.require_quiet
    return module


def configuration_catalog():
    return reference('ir').configuration_presence()


def verify_assets():
    assert ROOT == EXPECTED_ROOT and ROOT.resolve() == ROOT
    assert socket.gethostname() == 'charlie-oss-2'
    assert os.getuid() == ROOT.stat().st_uid == 1000 and Path('/').stat().st_uid == 0
    assets = read(ASSETS)
    assert assets['root'] == str(ROOT) and assets['host'] == socket.gethostname()
    assert assets['source_trees'] == TREES and set(assets['variants']) == set(NAMES)
    for relative, digest in assets['files'].items():
        path = ROOT / relative
        assert not Path(relative).is_absolute() and '..' not in Path(relative).parts
        assert path.is_file() and sha(path) == digest, path
    assert sha(SELF.parent / 'protocol.json') == PROTOCOL_SHA
    protocol = read(SELF.parent / 'protocol.json')
    assert protocol['base_tree'] == TREES['baseline'] and protocol['candidate_tree'] == TREES['candidate']
    assert protocol['uv_commit'] == UV_COMMIT
    assert protocol['ir']['pairs'] == 12 and protocol['native']['pairs'] == 30
    assert protocol['native']['calls_per_group'] == 8
    assert protocol['ir']['seeds'] == dict(STAGES['ir']['plan'])
    assert protocol['native']['seeds'] == dict(STAGES['native']['plan'])
    amendment = read(SELF.parent / 'warming-amendment-v3.json')
    amendment_review = read(SELF.parent / 'root-warming-v3-review.json')
    assert sha(SELF.parent / 'warming-amendment-v3.json') == '823d8448f15f09b5aafba4eb078132f66509e24760e95d4442761f952762975a'
    assert amendment['controller_sha256'] == amendment_review['controller_sha256'] == '318d05c1112e73625015461ff6c1000fab3cafb573c8e3e3963b16cd9ec64e6c'
    assert amendment['fixed_untimed_warm_commands_per_variant'] == 3
    assert amendment_review['status'] == 'passed' and amendment_review['strict_zero_child_trace_and_cross_switch_preserved']
    assert amendment_review['amendment_sha256'] == sha(SELF.parent / 'warming-amendment-v3.json')
    occupancy_amendment = read(SELF.parent / 'occupancy-amendment-v4.json')
    occupancy_review = read(SELF.parent / 'root-occupancy-v4-review.json')
    assert sha(SELF.parent / 'occupancy-amendment-v4.json') == '0774e8fb6e6981d06fb7b205e1d4574e24d486d86c0adfa905ce5950d5a9ff83'
    assert occupancy_amendment['previous_controller_sha256'] == occupancy_review['previous_controller_sha256'] == amendment['controller_sha256']
    assert occupancy_amendment['controller_sha256'] == occupancy_review['controller_sha256'] == REFERENCE_SHA
    assert occupancy_review['status'] == 'passed'
    assert occupancy_review['amendment_sha256'] == sha(SELF.parent / 'occupancy-amendment-v4.json')
    assert occupancy_amendment['only_quiet_ast_changed'] and occupancy_amendment['all_workload_and_statistical_settings_unchanged']
    cohort = SELF.parent / 'cohort'
    manifest = read(cohort / 'frozen/manifest.json')
    assert sha(cohort / 'frozen/manifest.json') == BUILD_MANIFEST_SHA
    assert sha(cohort / 'frozen/build_driver_host2_inheritance_stack180.py') == BUILD_DRIVER_SHA
    audit = read(cohort / 'results/audit-pair.json')
    assert sha(cohort / 'results/audit-pair.json') == '00fee70efe3e5f94ee55e7a76ac1baf921659f1e1895606577b55506316f105e'
    pair_review = read(cohort / 'results/root-pair-review.json')
    assert pair_review['status'] == 'passed' and all(pair_review['checks'].values())
    assert pair_review['pair_audit_sha256'] == sha(cohort / 'results/audit-pair.json')
    assert pair_review['binaries'] == {name: assets['variants'][variant] for variant, name in NAMES.items()}
    provenance = read(cohort / 'results/provenance.json')
    assert audit['cohort'] == provenance['cohort'] == 'host2-inheritance-stack180'
    assert audit['frozen_input_manifest_sha256'] == BUILD_MANIFEST_SHA
    assert audit['build_driver_sha256'] == provenance['driver_sha256'] == BUILD_DRIVER_SHA
    assert audit['provenance_sha256'] == sha(cohort / 'results/provenance.json')
    assert audit['common_build_inputs_sha256'] == provenance['common_build_inputs_sha256']
    assert audit['common_build_inputs_sha256'] == 'd3c153d203c6a933add9ce89a6b496ae8fcb4b9039376d877854359d9209caeb'
    assert audit['host7_reference_fields_match_after_explicit_root_relocation']
    assert set(row['variant'] for row in audit['records']) == set(NAMES.values())
    for variant, name in NAMES.items():
        build = read(cohort / 'results' / ('cargo-' + name + '.build.json'))
        strip = read(cohort / 'results' / ('cargo-' + name + '.strip.json'))
        row = next(item for item in audit['records'] if item['variant'] == name)
        expected = manifest['expected_variants'][name]
        assert build['observed_source_tree'] == build['expected_source_tree_from_patches'] == row['source_tree'] == expected['tree'] == TREES[variant]
        assert build['embedded_source_commit'] == '5e5d271d763d7beb38b48755e22bd59e93f02b97'
        assert build['common_build_inputs_sha256'] == row['common_build_inputs_sha256'] == audit['common_build_inputs_sha256']
        assert build['original_linker_output_sha256'] == strip['source_sha256'] == row['original_linker_output_sha256']
        assert sha(SELF.parent / 'binaries' / ('cargo-' + name)) == strip['stripped_sha256'] == row['stripped_sha256'] == assets['variants'][variant]
        assert sha(cohort / 'results' / (name + '.source.patch')) == build['observed_diff_sha256'] == expected['canonical_diff_sha256']
        for suffix in ('stdout', 'stderr'):
            assert sha(cohort / 'results' / (name + '.' + suffix)) == build[suffix + '_sha256']
        for filename, digest in expected['patch_sha256'].items():
            assert sha(cohort / 'frozen' / filename) == digest
    assert len(set(assets['variants'].values())) == 2
    assert assets['variants']['baseline'] == '3164f9287711f122fa9636a7816ed8749598706ac5076d66051a036dcef51037'
    assert assets['variants']['candidate'] == '3b1a2e4e3654b7b23816fbb54c51072cb356486c36052a5bcd6c4d3d2e6a07e9'
    ci = read(SELF.parent / 'source-ci.json')
    assert ci['status'] == 'completed' and ci['conclusion'] == 'success' and ci['required_jobs_succeeded']
    assert ci['head_sha'] == 'd81a093becb4321a975522624c2a383970f0d164'
    reviewed = read(SELF.parent / 'correctness/root-correctness-review.json')
    assert reviewed['status'] == 'passed' and reviewed['source_tree'] == TREES['candidate']
    assert reviewed['correctness_seal_sha256'] == sha(SELF.parent / 'correctness/correctness-seal.json')
    correctness = read(SELF.parent / 'correctness/correctness-seal.json')
    assert correctness['validation_passed'] and correctness['tests'] == 28
    assert correctness['failed'] == correctness['ignored'] == 0 and correctness['source_tree'] == TREES['candidate']
    for filename, digest in correctness['files'].items():
        assert sha(SELF.parent / 'correctness' / filename) == digest
    setup = read(ROOT / 'metadata/setup.json')
    assert setup['root'] == str(ROOT) and setup['uv_commit'] == UV_COMMIT
    assert setup['configuration_catalog'] == configuration_catalog()
    assert setup['known_global_configuration'] == {'path': '/.cargo/config.toml',
        'sha256': '24095bd6315880162c8f660917100ac36638cb73778dd9ec6f1c9026ea87b178',
        'evidence_copy': 'metadata/ancestor-root-config.toml'}
    assert sha(ROOT / 'metadata/ancestor-root-config.toml') == setup['known_global_configuration']['sha256']
    assert setup['configuration_catalog']['/.cargo/config.toml'] == {'lexists': True,
        'sha256': setup['known_global_configuration']['sha256'], 'symlink': None}
    assert setup['configuration_catalog'][str(ROOT / 'cargo-home/config')]['lexists'] is False
    assert setup['configuration_catalog'][str(ROOT / 'cargo-home/config.toml')]['lexists'] is False
    reference('ir').allocator_guard()
    reference('ir').uv_identity()
    return assets


def derive(phase, workflow, assets):
    original = read(SELF.parent / 'base-configs' / (phase + '-' + workflow + '.json'))
    config = json.loads(json.dumps(original))
    assert config['cwd'] == str(ROOT / 'uv')
    assert config['canonical_executable'] == str(ROOT / 'active/bin/cargo')
    assert config['variants'] == {key: str(SELF.parent / 'binaries' / ('cargo-' + name)) for key, name in NAMES.items()}
    assert config['env']['CARGO_HOME'] == str(ROOT / 'cargo-home')
    assert config['env']['CARGO_TARGET_DIR'] == str(ROOT / 'targets' / (phase + '-' + workflow))
    assert config['env']['CARGO_BUILD_BUILD_DIR'] == str(ROOT / 'shared-cache' / (phase + '-' + workflow))
    command = ['/usr/bin/taskset', '-c', '0-7', '{cargo}', '-Zohm-defaults=yes', workflow]
    if workflow == 'test':
        command.append('--no-run')
    command.extend(['--locked', '--offline', '-j', '8'])
    assert config['prepare_command'] == command
    if phase == 'native':
        assert config['command'] == command and config['repetitions'] == 8 and config['repeatable_workload'] == 'noop'
        assert 'metric_files' not in config
    else:
        prefix = ['/usr/bin/taskset', '-c', '0-7', '/usr/bin/env',
                  'LD_PRELOAD=' + str(ROOT / 'profiling-tools/ohm-valgrind-env.so'),
                  'OHM_BENCH_NORMALIZE_VALGRIND_ENV=1',
                  str(ROOT / 'profiling-tools/valgrind/usr/bin/valgrind'),
                  '--tool=callgrind', '--trace-children=no',
                  '--extra-debuginfo-path=' + str(ROOT / 'profiling-tools/valgrind/usr/lib/debug'),
                  '--callgrind-out-file={output}/callgrind-{stage}-{pair}-{variant}.out']
        assert config['command'] == prefix + command[3:]
        assert config['metric_files'] == {'cargo_ir': {'format': 'callgrind', 'event': 'Ir',
                'path': '{output}/callgrind-{stage}-{pair}-{variant}.out'}}
        assert 'repetitions' not in config
    for name, value in config['env'].items():
        if name.startswith(('LD_', 'DYLD_', 'MALLOC', '_RJEM_', 'JEMALLOC')) or name == 'GLIBC_TUNABLES':
            assert value is None, name
    extra = [ROOT / name for name in assets['files']]
    extra += [ASSETS, SEAL, paths(phase, workflow)['config'], paths(phase, workflow)['preflight'] / 'report.json']
    if phase == 'native':
        extra.append(ROOT / 'metadata/native-prerequisite.json')
    config['record_files'] = list(dict.fromkeys([*config['record_files'], *map(str, extra)]))
    return config


def audit_sample_tables(output, samples, phase):
    assert samples == [json.loads(line) for line in (output / 'samples.jsonl').read_text().splitlines()]
    with (output / 'samples.csv').open(newline='') as stream:
        reader = csv.DictReader(stream)
        fields = SAMPLE_FIELDS + (('metric_cargo_ir',) if phase == 'ir' else ())
        assert tuple(reader.fieldnames) == fields
        rows = list(reader)
    assert len(rows) == len(samples)
    for csv_row, sample in zip(rows, samples):
        assert all(csv_row[key] == str(sample[key]) for key in fields)


def prepare(core):
    assets = verify_assets()
    assert not SEAL.exists() and not any(phase_status(phase).exists() for phase in STAGES)
    encoded, records, future = {}, set(), {str(ROOT / 'metadata/native-prerequisite.json')}
    for phase in STAGES:
        for workflow, _ in STAGES[phase]['plan']:
            destination = paths(phase, workflow)
            assert all(not path.exists() for path in destination.values())
            config = derive(phase, workflow, assets)
            for name in ('CARGO_TARGET_DIR', 'CARGO_BUILD_BUILD_DIR'):
                assert not os.path.lexists(config['env'][name]), config['env'][name]
            encoded[destination['config']] = (json.dumps(config, indent=2) + '\n').encode()
            records.update(config['record_files'])
            future.add(str(destination['preflight'] / 'report.json'))
    hashes = {name: sha(name) for name in sorted(records - future - {str(SEAL)} - {str(path) for path in encoded})}
    hashes.update({str(path): hashlib.sha256(data).hexdigest() for path, data in encoded.items()})
    for path, data in encoded.items():
        with path.open('xb') as stream:
            stream.write(data)
    value = {'prepared_at': core.utc_now(), 'stages': STAGES, 'variants': assets['variants'], 'source_trees': TREES,
             'file_sha256': hashes, 'future_reports': sorted(future), 'uv': reference('ir').uv_identity(),
             'configuration_catalog': configuration_catalog(), 'environment_guard': reference('ir').allocator_guard(),
             'scope': 'All four fixed configurations sealed before any fixture warming or performance measurement.'}
    with SEAL.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'event': 'inputs_sealed', 'sha256': sha(SEAL), 'variants': assets['variants']}), flush=True)


def verify_seal(expected):
    assert expected and sha(SEAL) == expected
    value = read(SEAL)
    assert value['stages'] == json.loads(json.dumps(STAGES))
    assert value['variants'] == read(ASSETS)['variants'] and value['source_trees'] == TREES
    for path, digest in value['file_sha256'].items():
        assert sha(path) == digest, path
    assert value['configuration_catalog'] == configuration_catalog()
    assert value['environment_guard'] == reference('ir').allocator_guard()
    for phase in STAGES:
        for workflow, _ in STAGES[phase]['plan']:
            config = read(paths(phase, workflow)['config'])
            assert config == derive(phase, workflow, read(ASSETS))
            observed = {name for name in os.environ if name.startswith(('CARGO_', 'RUST', '__CARGO_', 'LD_', 'DYLD_',
                        'MALLOC', '_RJEM_', 'JEMALLOC', 'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS', 'PKG_CONFIG'))}
            assert observed <= set(config['env']), sorted(observed - set(config['env']))


def audit_ir(core, workflow, seed):
    output = paths('ir', workflow)['output']
    manifest, samples = read(output / 'manifest.json'), read(output / 'samples.json')
    expected = read(ASSETS)['variants']
    assert manifest['state'] == 'complete' and manifest['phase'] == 'confirmation'
    assert (manifest['pairs'], manifest['warmup_pairs'], manifest['seed']) == (12, 2, seed)
    assert manifest['variant_sha256'] == manifest['variant_sha256_after'] == expected
    assert manifest['recorded_file_sha256'] == manifest['recorded_file_sha256_after']
    assert manifest['configuration'] == read(paths('ir', workflow)['config'])
    assert sha(paths('ir', workflow)['config']) == manifest['configuration_sha256']
    for path, digest in manifest['recorded_file_sha256'].items():
        assert sha(path) == digest, path
    plans = {'warmup': [list(order) for order in core.make_plan(2, seed ^ 0x5A17)],
             'measurement': [list(order) for order in core.make_plan(12, seed)]}
    assert manifest['plans'] == plans
    identities = [(stage, pair, position, variant, 'AB' if order[0] == 'baseline' else 'BA')
                  for stage, plan in plans.items() for pair, order in enumerate(plan)
                  for position, variant in enumerate(order)]
    assert [(row['stage'], row['pair'], row['position'], row['variant'], row['order']) for row in samples] == identities
    assert len(samples) == 28 and plans['measurement'].count(['baseline', 'candidate']) == 6
    audit_sample_tables(output, samples, 'ir')
    ref = reference('ir')
    for row in samples:
        assert row['returncode'] == 0 and row['executable_unchanged']
        assert row['installed_sha256'] == expected[row['variant']]
        assert row['prepare']['returncode'] == 0 and '--trace-children=no' in row['command']
        if workflow == 'test':
            assert '--no-run' in row['command']
        ref.fresh(row['stderr'])
        ref.fresh(row['prepare']['stderr'])
        assert set(row['metric_files']) == set(row['metrics']) == {'cargo_ir'}
        metric = row['metric_files']['cargo_ir']
        assert sha(metric['path']) == metric['sha256']
        assert core.read_callgrind_summary(metric['path'], 'Ir') == row['metrics']['cargo_ir'] == row['metric_cargo_ir']
        assert row['metrics']['cargo_ir'] > 0
    return {'state': 'passed', 'completed_at': core.utc_now(), 'pairs': 12, 'warmup_pairs': 2,
            'invocations_verified': 28, 'profile_hashes_verified': 28, 'uv_after': ref.uv_identity()}


def gate(phase, output):
    analysis = read(output / 'analysis.json')
    assert analysis['confidence'] == 0.99 and analysis['bootstrap_resamples'] == 20000 and analysis['bootstrap_seed'] == 1701
    if phase == 'ir':
        stats = analysis['metrics']['cargo_ir']['statistics']
        reduction = stats['paired_geometric_mean_count_reduction']
        interval = stats['bootstrap_count_reduction_interval']
        order_key = 'geometric_mean_ratio'
    else:
        stats = analysis
        assert stats['grouping']['repetitions_per_variant'] == 8
        reduction = stats['paired_geometric_mean_time_reduction']
        interval = stats['bootstrap_time_reduction_interval']
        order_key = 'geometric_mean_speedup'
    checks = {'fixed_pairs': stats['pairs'] == STAGES[phase]['pairs'], 'at_least_one_percent': reduction >= 0.01,
              'positive_99_percent_lower_bound': interval[0] > 0,
              'two_sided_sign_p_at_most_0_01': stats['exact_two_sided_sign_p'] <= 0.01,
              'both_orders_positive': set(stats['order']) == {'AB', 'BA'} and all(row[order_key] > 1 for row in stats['order'].values())}
    return {'passes_gate': all(checks.values()), 'checks': checks, 'reduction': reduction,
            'interval_99': interval, 'sign_p': stats['exact_two_sided_sign_p'],
            'significant_native_regression': phase == 'native' and interval[1] < 0 and stats['exact_two_sided_sign_p'] <= 0.01,
            'scope': 'Fixed independent pairs; no exclusions, extensions, pooling or interim effect inspection.'}


def native_prerequisite(core, expected_seal):
    status = read(phase_status('ir'))
    assert status['state'] == 'complete' and status['both_workflows_pass']
    assert status['seal_sha256'] == expected_seal and status['integrity_complete'] == ['check', 'test']
    assert [row['workflow'] for row in status['completed']] == ['check', 'test']
    hashes = {str(phase_status('ir')): sha(phase_status('ir'))}
    for workflow, seed in STAGES['ir']['plan']:
        audit_ir(core, workflow, seed)
        output = paths('ir', workflow)['output']
        result = gate('ir', output)
        assert result['passes_gate'] and result == read(output / 'gate.json')
        for filename in ('manifest.json', 'samples.json', 'samples.jsonl', 'samples.csv', 'integrity.json', 'analysis.json', 'gate.json'):
            hashes[str(output / filename)] = sha(output / filename)
    path = ROOT / 'metadata/native-prerequisite.json'
    assert not path.exists()
    with path.open('x') as stream:
        json.dump({'state': 'passed', 'seal_sha256': expected_seal, 'verified_at': core.utc_now(), 'files': hashes}, stream, indent=2)
        stream.write('\n')


def run_phase(core, phase, expected_seal):
    assets = verify_assets()
    verify_seal(expected_seal)
    ref = reference(phase)
    ref.quiet()
    assert not phase_status(phase).exists()
    if phase == 'native':
        native_prerequisite(core, expected_seal)
    status = {'state': 'starting', 'started_at': core.utc_now(), 'phase': phase,
              'seal_sha256': expected_seal, 'variants': assets['variants'], 'integrity_complete': [], 'completed': []}
    core.atomic_json(phase_status(phase), status)
    try:
        for workflow, seed in STAGES[phase]['plan']:
            verify_seal(expected_seal)
            status.update(state='preflight', workflow=workflow, quiet=ref.quiet())
            core.atomic_json(phase_status(phase), status)
            ref.preflight(core, workflow)
            verify_seal(expected_seal)
            destination = paths(phase, workflow)
            assert not destination['output'].exists()
            status.update(state='running fixed batch', workflow=workflow, seed=seed, quiet=ref.quiet())
            core.atomic_json(phase_status(phase), status)
            runner = CORE if phase == 'ir' else RUNNER
            with destination['log'].open('x') as stream:
                subprocess.run([sys.executable, '-I', '-B', str(runner), 'run', '--config', str(destination['config']),
                                '--output', str(destination['output']), '--phase', 'confirmation',
                                '--pairs', str(STAGES[phase]['pairs']), '--warmup-pairs', '2', '--seed', str(seed)],
                               stdout=stream, stderr=subprocess.STDOUT, check=True)
            shutil.copyfile(destination['log'], destination['output'] / 'runner.log')
            audit = audit_ir(core, workflow, seed) if phase == 'ir' else ref.audit_complete(core, workflow, seed)
            if phase == 'native':
                audit_sample_tables(destination['output'], read(destination['output'] / 'samples.json'), phase)
            core.atomic_json(destination['output'] / 'integrity.json', audit)
            verify_seal(expected_seal)
            status['integrity_complete'].append(workflow)
            core.atomic_json(phase_status(phase), status)
        assert status['integrity_complete'] == ['check', 'test']
        status.update(state='both workflows passed integrity', quiet=ref.quiet())
        core.atomic_json(phase_status(phase), status)
        for workflow, _ in STAGES[phase]['plan']:
            output = paths(phase, workflow)['output']
            with (output / 'analysis-stdout.json').open('x') as stream:
                subprocess.run([sys.executable, '-I', '-B', str(runner), 'analyze', str(output), '--confidence', '.99',
                                '--resamples', '20000', '--seed', '1701', '--minimum-pairs', str(STAGES[phase]['pairs'])],
                               stdout=stream, check=True)
            result = gate(phase, output)
            core.atomic_json(output / 'gate.json', result)
            status['completed'].append({'workflow': workflow, 'directory': str(output), **result})
            core.atomic_json(phase_status(phase), status)
        verify_seal(expected_seal)
        status.update(state='complete', completed_at=core.utc_now(), quiet=ref.quiet(), uv=ref.uv_identity(),
                      both_workflows_pass=all(row['passes_gate'] for row in status['completed']),
                      significant_native_regression=any(row['significant_native_regression'] for row in status['completed']))
        core.atomic_json(phase_status(phase), status)
    except BaseException as error:
        status.update(state='failed', failed_at=core.utc_now(), error=repr(error))
        core.atomic_json(phase_status(phase), status)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--run-phase', choices=STAGES)
    parser.add_argument('--sealed-inputs-sha256')
    args = parser.parse_args()
    core = load_module('paired', CORE, CORE_SHA)
    assert sha(RUNNER) == RUNNER_SHA
    if args.prepare:
        prepare(core)
    else:
        run_phase(core, args.run_phase, args.sealed_inputs_sha256)


if __name__ == '__main__':
    main()
