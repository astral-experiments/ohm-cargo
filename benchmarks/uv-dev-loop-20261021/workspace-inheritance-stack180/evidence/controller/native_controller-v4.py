#!/usr/bin/env python3
"""Seal both allocator workflows, run fixed batches, then inspect effects."""
import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import statistics
import subprocess
import sys

SELF = Path(__file__).resolve()
ROOT = SELF.parents[1]
ASSETS = SELF.parent / 'assets.json'
SEAL = SELF.parent / 'native-seal.json'
STATUS = ROOT / 'allocator-native-status.json'
CORE = ROOT / 'benchmark/frozen/paired.py'
RUNNER = ROOT / 'benchmark/frozen/paired_repeated.py'
CORE_SHA = '50d0cb2d4f595ccfa72d463fedb3ff4dadf9dfc1446c749d482d9ede8418c7cf'
RUNNER_SHA = '50547460e030aa73e1f48121bf477cf8f4a4538bf1bb577851af54176750b6d3'
UV_COMMIT = '3d82a6ad5a7eab8c68236553b7846517767c4b61'
EXPECTED = {
    'baseline': '67e1a528c11ebaf7cd166cba18eff834ff993a5518a7afdbb2892b6876d19d0c',
    'candidate': '8451b647d254661858ad4ad90b760b6d754688f33f53ddd6324612931d504388',
}
NAMES = {'baseline': 'allocator-baseline', 'candidate': 'allocator-jemalloc'}
TREES = {'baseline': 'f4ce59f92aa17461fe3c8b68923c88539136045a',
         'candidate': 'b4561c66951de3c6717b8ce6a99d0ea45ff73b41'}
PROTOCOLS = {
    'protocol.md': 'be8ece4ef74e35bbde7b9e1525f328596d75eee5e4757dc163550ea21d32c2d7',
    'protocol-amendment-build-inputs.md': '121954bc79be8edbfa3cd420d69b249dc6097a2ee485ce41469b12fbb2ce2d59',
    'protocol-amendment-replication-host.md': '1ca5da32825759bfb8c8ef5c3a6ef55dcd15fefd9ed53b76cc3b08bbd832c2bc',
}
STAGES = {
    'screen': {'host': 'charlie-oss-5', 'pairs': 12, 'phase': 'exploratory',
               'plan': [('check', 2026102191), ('test', 2026102192)],
               'warming_order': ['baseline', 'candidate']},
    'confirmation': {'host': 'charlie-oss-3', 'pairs': 30, 'phase': 'confirmation',
                     'plan': [('check', 2026102193), ('test', 2026102194)],
                     'warming_order': ['candidate', 'baseline']},
}
FORBIDDEN_PREFIXES = ('LD_', 'DYLD_', 'MALLOC', '_RJEM_', 'JEMALLOC')
SYSTEM_ALLOCATOR_CONFIGS = ('/etc/_rjem_malloc.conf', '/etc/malloc.conf')

BUILDERS = {'cargo', 'rustc', 'rustdoc', 'rust-lld', 'ld.lld', 'cc', 'cc1', 'cc1plus',
            'clang', 'gcc', 'ninja', 'make', 'cmake', 'valgrind', 'perf'}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_core():
    assert sha(CORE) == CORE_SHA and sha(RUNNER) == RUNNER_SHA
    spec = importlib.util.spec_from_file_location('paired', CORE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def quiet():
    probe = subprocess.Popen(['ps', '-eo', 'pid=,pcpu=,pmem=,comm=', '--sort=-pcpu'],
                             stdout=subprocess.PIPE, text=True)
    output, _ = probe.communicate()
    assert probe.returncode == 0, probe.returncode
    rows = output.splitlines()
    competing = []
    for row in rows:
        pid, cpu, _memory, name = row.split(None, 3)
        name = name.strip()
        if int(pid) in {os.getpid(), probe.pid}:
            continue
        if name in BUILDERS or name.startswith(('cargo-', 'callgrind-')) or float(cpu) >= 50:
            competing.append(row)
    assert not competing, competing
    return {'process_snapshot': rows[:20], 'load_average': list(os.getloadavg())}


def uv_identity():
    head = subprocess.check_output(['git', '-C', str(ROOT / 'uv'), 'rev-parse', 'HEAD'], text=True).strip()
    status = subprocess.check_output(['git', '-C', str(ROOT / 'uv'), 'status', '--porcelain'], text=True)
    assert head == UV_COMMIT and not status
    return {'commit': head, 'status': status, 'lock_sha256': sha(ROOT / 'uv/Cargo.lock')}


def stage():
    return STAGES[read(ASSETS)['stage']]


def allocator_guard():
    forbidden = sorted(name for name in os.environ
                       if name.startswith(FORBIDDEN_PREFIXES) or name == 'GLIBC_TUNABLES')
    assert not forbidden, forbidden
    for name in SYSTEM_ALLOCATOR_CONFIGS:
        assert not os.path.lexists(name), name
    return {'forbidden_environment_names': forbidden,
            'absent_system_configurations': list(SYSTEM_ALLOCATOR_CONFIGS)}


def configuration_presence():
    candidates = {ROOT / 'cargo-home' / name for name in ('config', 'config.toml')}
    for parent in (ROOT / 'uv', *(ROOT / 'uv').parents):
        candidates.update(parent / '.cargo' / name for name in ('config', 'config.toml'))
    return {str(path): {'lexists': os.path.lexists(path),
                       'sha256': sha(path) if path.is_file() else None,
                       'symlink': os.readlink(path) if path.is_symlink() else None}
            for path in sorted(candidates)}


def verify_assets():
    assert socket.gethostname() == stage()['host']
    assert os.getuid() == 1000 and ROOT.stat().st_uid == 1000 and ROOT.resolve() == ROOT
    assert Path('/').stat().st_uid == 0
    assets = read(ASSETS)
    for relative, digest in assets['files'].items():
        path = ROOT / relative
        assert path.resolve() == path and sha(path) == digest, relative
    for name, digest in PROTOCOLS.items():
        assert sha(SELF.parent / 'protocols' / name) == digest
    audit = read(SELF.parent / 'cohort/results/audit-cohort.json')
    assert audit['common_build_inputs_sha256'] == 'c0e22f44d3dd8d57670bc061d110627e63fb80970f145a8e64ed00d6f445cf99'
    assert {row['variant'] for row in audit['records']} == set(NAMES.values())
    for variant, name in NAMES.items():
        binary = SELF.parent / 'binaries' / ('cargo-' + name)
        strip = read(SELF.parent / 'cohort/results' / f'cargo-{name}.strip.json')
        build = read(SELF.parent / 'cohort/results' / f'cargo-{name}.build.json')
        row = next(row for row in audit['records'] if row['variant'] == name)
        assert sha(binary) == strip['stripped_sha256'] == row['stripped_sha256'] == EXPECTED[variant]
        assert build['observed_source_tree'] == row['source_tree'] == TREES[variant]
    native = read(SELF.parent / 'native-build-audit.json')
    assert native['status'] == 'passed'
    assert not any(native['probe_configuration'].values())
    assert {k: v['binary_sha256'] for k, v in native['binary_inspection'].items()} == {
        NAMES[key]: digest for key, digest in EXPECTED.items()}
    correctness = read(SELF.parent / 'correctness-prerequisite.json')
    assert correctness['status'] == 'passed' and correctness['enabled_production_cli']
    assert correctness['candidate_sha256'] == EXPECTED['candidate']
    assert set(correctness['coverage']) >= {'build-cache', 'git', 'http'}
    ci = read(SELF.parent / 'source-ci.json')
    assert ci['conclusion'] == 'success' and ci['status'] == 'completed'
    assert ci['head_sha'] == 'f046cc089f91c023f2c922bd74ebb33c98abe71e'
    if assets['stage'] == 'confirmation':
        proof = read(SELF.parent / 'screen-prerequisite.json')
        assert proof['state'] == 'complete' and proof['both_workflows_pass']
        assert proof['variants'] == EXPECTED and proof['pairs'] == 12
        assert {row['workflow'] for row in proof['completed']} == {'check', 'test'}
        assert all(row['passes_native_gate'] for row in proof['completed'])
    allocator_guard()
    return assets


def paths(workflow):
    label = workflow + '-allocator-' + read(ASSETS)['stage']
    return {'config': ROOT / 'benchmark' / (label + '-native.json'),
            'preflight': ROOT / 'metadata' / (label + '-native-preflight'),
            'output': ROOT / 'results' / (label + '-native'),
            'log': ROOT / 'logs' / (label + '-native-runner.log')}


def derive(workflow, assets):
    original_path = SELF.parent / 'base-configs' / (workflow + '.json')
    original = read(original_path)
    config = json.loads(json.dumps(original))
    assert config['cwd'] == str(ROOT / 'uv')
    assert config['canonical_executable'] == str(ROOT / 'active/bin/cargo')
    assert config['repetitions'] == 8 and config['repeatable_workload'] == 'noop'
    assert workflow != 'test' or '--no-run' in config['command']
    assert config['env']['CARGO_HOME'] == str(ROOT / 'cargo-home')
    assert config['env']['CARGO_TARGET_DIR'] == str(ROOT / 'targets' / workflow)
    assert config['env']['CARGO_BUILD_BUILD_DIR'] == str(ROOT / 'shared-cache' / workflow)
    assert config['command'] == config['prepare_command']
    for name in (*SYSTEM_ALLOCATOR_CONFIGS,):
        assert not os.path.lexists(name)
    for name, value in config['env'].items():
        if name.startswith(FORBIDDEN_PREFIXES) or name == 'GLIBC_TUNABLES':
            assert value is None
    config['variants'] = {key: str(SELF.parent / 'binaries' / ('cargo-' + name)) for key, name in NAMES.items()}
    config['record_files'] = list(original['record_files'])
    destination = paths(workflow)
    extra = [ROOT / name for name in assets['files']]
    extra.extend([ASSETS, SEAL, original_path, destination['config'], destination['preflight'] / 'report.json',
                  Path(sys.executable).resolve(), Path(shutil.which('taskset')).resolve(),
                  Path(shutil.which('strace')).resolve(), Path('/usr/bin/time').resolve()])
    config['record_files'] = list(dict.fromkeys([*config['record_files'], *map(str, extra)]))
    assert all(config[key] == original[key] for key in original if key not in {'variants', 'record_files'})
    return config


def prepare(core):
    assets = verify_assets()
    assert not SEAL.exists() and not STATUS.exists()
    encoded, future, records = {}, set(), set()
    for workflow, _ in stage()['plan']:
        destination = paths(workflow)
        assert all(not destination[key].exists() for key in ['config', 'preflight', 'output', 'log'])
        config = derive(workflow, assets)
        encoded[destination['config']] = (json.dumps(config, indent=2) + '\n').encode()
        records.update(config['record_files'])
        future.add(str(destination['preflight'] / 'report.json'))
    hashes = {name: sha(name) for name in sorted(records - future - {str(SEAL)} - {str(path) for path in encoded})}
    hashes.update({str(path): hashlib.sha256(data).hexdigest() for path, data in encoded.items()})
    for path, data in encoded.items():
        with path.open('xb') as stream:
            stream.write(data)
    value = {'prepared_at': core.utc_now(), 'stage': read(ASSETS)['stage'], 'plan': stage()['plan'], 'variants': EXPECTED, 'source_trees': TREES,
             'file_sha256': hashes, 'future_preflight_reports': sorted(future), 'uv': uv_identity(),
             'configuration_presence': configuration_presence(), 'allocator_guard': allocator_guard(),
             'scope': 'Both fixed native configurations sealed before fixture warming or acceptance timing on this host.'}
    with SEAL.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'event': 'native_inputs_sealed', 'sha256': sha(SEAL), 'variants': EXPECTED}), flush=True)


def verify_seal(expected):
    assert expected and sha(SEAL) == expected
    value = read(SEAL)
    assert value['plan'] == [list(row) for row in stage()['plan']] and value['variants'] == EXPECTED
    for path, digest in value['file_sha256'].items():
        assert sha(path) == digest, path
    assert value['configuration_presence'] == configuration_presence()
    assert value['allocator_guard'] == allocator_guard()
    assets = read(ASSETS)
    for workflow, _ in stage()['plan']:
        assert read(paths(workflow)['config']) == derive(workflow, assets)


def fresh(path):
    text = Path(path).read_text()
    assert 'Finished' in text and not re.search(r'^\s*(?:Compiling|Checking|Running)\s|^error:', text, re.M), path


def preflight(core, workflow):
    destination = paths(workflow)
    output = destination['preflight']
    output.mkdir(exist_ok=False)
    config = read(destination['config'])
    environment = os.environ.copy()
    for key, value in config['env'].items():
        if value is None:
            environment.pop(key, None)
        else:
            environment[key] = str(value)
    records = []
    before = uv_identity()
    for key in ('CARGO_TARGET_DIR', 'CARGO_BUILD_BUILD_DIR'):
        fixture = Path(config['env'][key])
        assert not fixture.exists() and not fixture.is_symlink(), str(fixture)
    allocator_guard()
    for variant in stage()['warming_order']:
        quiet()
        canonical = Path(config['canonical_executable'])
        core.install_variant(Path(config['variants'][variant]), canonical)
        assert sha(canonical) == EXPECTED[variant]
        command = [part.replace('{cargo}', str(canonical)) for part in config['prepare_command']]
        warming_runs = []
        for warm_index in range(1, 4):
            label = variant + '.warm-' + str(warm_index)
            warm = core.run_command(command, config['cwd'], environment, output / (label + '.stdout'), output / (label + '.stderr'))
            assert warm['returncode'] == 0
            warming_runs.append(warm)
        trace_path = output / (variant + '.execve.log')
        traced = [shutil.which('strace'), '-f', '-qq', '-e', 'trace=execve,execveat', '-s', '4096', '-o', str(trace_path), '--', *command]
        trace = core.run_command(traced, config['cwd'], environment, output / (variant + '.trace.stdout'), output / (variant + '.trace.stderr'))
        assert trace['returncode'] == 0
        fresh(trace['stderr'])
        successes = [line for line in trace_path.read_text().splitlines() if re.search(r'= 0\s*$', line)]
        executable_paths = []
        for line in successes:
            match = re.search(r'execve\("([^"]+)"', line) or re.search(r'execveat\([^,]+, "([^"]+)"', line)
            assert match, line
            executable_paths.append(match[1])
        assert executable_paths == [str(Path(shutil.which('taskset')).resolve()), str(canonical)], executable_paths
        assert sha(canonical) == EXPECTED[variant]
        quiet()
        records.append({'variant': variant, 'binary_sha256': EXPECTED[variant], 'warm': warm, 'warming_runs': warming_runs, 'trace': trace,
                        'trace_path': str(trace_path), 'trace_sha256': sha(trace_path), 'successful_execve_paths': executable_paths})
    cross_switch = []
    for variant in stage()['warming_order']:
        canonical = Path(config['canonical_executable'])
        core.install_variant(Path(config['variants'][variant]), canonical)
        command = [part.replace('{cargo}', str(canonical)) for part in config['prepare_command']]
        result = core.run_command(command, config['cwd'], environment, output / (variant + '.cross-switch.stdout'), output / (variant + '.cross-switch.stderr'))
        assert result['returncode'] == 0 and sha(canonical) == EXPECTED[variant]
        fresh(result['stderr'])
        cross_switch.append({'variant': variant, **result})
    quiet()
    core.atomic_json(output / 'report.json', {'state': 'passed', 'completed_at': core.utc_now(), 'records': records, 'cross_switch': cross_switch,
                                             'uv_before': before, 'uv_after': uv_identity(), 'machine': core.machine_metadata()})


def audit_complete(core, workflow, seed):
    output = paths(workflow)['output']
    manifest, samples = read(output / 'manifest.json'), read(output / 'samples.json')
    count = stage()['pairs']
    phase = stage()['phase']
    assert manifest['state'] == 'complete' and manifest['phase'] == phase
    assert (manifest['pairs'], manifest['warmup_pairs'], manifest['seed']) == (count, 2, seed)
    assert manifest['variant_sha256'] == manifest['variant_sha256_after'] == EXPECTED
    assert manifest['recorded_file_sha256'] == manifest['recorded_file_sha256_after']
    expected_harness = {str(RUNNER): RUNNER_SHA, str(CORE): CORE_SHA}
    assert manifest['repeated_harness_sha256'] == manifest['repeated_harness_sha256_after'] == expected_harness
    assert sha(paths(workflow)['config']) == manifest['configuration_sha256']
    assert manifest['configuration'] == read(paths(workflow)['config'])
    for path, digest in manifest['recorded_file_sha256'].items():
        assert sha(path) == digest, path
    expected_plans = {'warmup': [list(order) for order in core.make_plan(2, seed ^ 0x5A17)],
                      'measurement': [list(order) for order in core.make_plan(count, seed)]}
    assert manifest['plans'] == expected_plans
    expected_samples = [(stage, pair, position, variant, 'AB' if order[0] == 'baseline' else 'BA')
                        for stage, plan in expected_plans.items() for pair, order in enumerate(plan)
                        for position, variant in enumerate(order)]
    assert [(row['stage'], row['pair'], row['position'], row['variant'], row['order']) for row in samples] == expected_samples
    orders = manifest['plans']['measurement']
    assert orders.count(['baseline', 'candidate']) == orders.count(['candidate', 'baseline']) == count // 2
    assert len(samples) == 2 * (count + 2)
    subruns = read(output / 'subruns.json')
    spec = importlib.util.spec_from_file_location('frozen_repeated_integrity', RUNNER)
    repeated = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(repeated)
    assert repeated.validate_groups(manifest, samples, subruns) == 8
    assert subruns == [row for sample in samples for row in sample['repetitions']]
    assert subruns == [json.loads(line) for line in (output / 'subruns.jsonl').read_text().splitlines()]
    with (output / 'subruns.csv').open(newline='') as stream:
        reader = csv.DictReader(stream)
        assert tuple(reader.fieldnames) == repeated.CSV_FIELDS
        csv_rows = list(reader)
    assert len(csv_rows) == len(subruns)
    for csv_row, raw in zip(csv_rows, subruns):
        assert all(csv_row[key] == str(raw[key]) for key in repeated.CSV_FIELDS)
    invocations = 0
    for sample in samples:
        assert sample['returncode'] == 0 and sample['executable_unchanged']
        assert sample['installed_sha256'] == EXPECTED[sample['variant']]
        assert sample['prepare']['returncode'] == 0
        fresh(sample['prepare']['stderr'])
        assert sample['repetitions_requested'] == sample['repetitions_completed'] == 8
        repetitions = sample['repetitions']
        assert len(repetitions) == 8 and sum(row['wall_ns'] for row in repetitions) == sample['wall_ns']
        for field in ['user_seconds', 'system_seconds']:
            assert math.isclose(sum(row[field] for row in repetitions), sample[field], abs_tol=1e-9)
        for repetition, row in enumerate(repetitions, 1):
            assert row['phase'] == phase and row['repetition'] == repetition
            assert all(row[key] == sample[key] for key in ['stage', 'pair', 'position', 'variant', 'order'])
            assert row['returncode'] == 0 and row['wall_ns'] > 0 and row['compiled_packages'] == []
            assert manifest['canonical_executable'] in row['command']
            fresh(row['stderr'])
        invocations += len(repetitions)
    assert invocations == manifest['grouping']['subrun_count'] == 2 * (count + 2) * 8
    return {'state': 'passed', 'completed_at': core.utc_now(), 'group_pairs': count,
            'warmup_group_pairs': 2, 'invocations_verified': invocations, 'uv_after': uv_identity()}


def gate(output):
    value = read(output / 'analysis.json')
    count = stage()['pairs']
    assert value['pairs'] == count and value['confidence'] == 0.99
    assert value['bootstrap_resamples'] == 20000 and value['bootstrap_seed'] == 1701
    assert value['grouping']['repetitions_per_variant'] == 8
    checks = {'fixed_group_pairs': value['pairs'] == count,
              'at_least_one_percent': value['paired_geometric_mean_time_reduction'] >= 0.01,
              'positive_99_percent_lower_bound': value['bootstrap_time_reduction_interval'][0] > 0,
              'two_sided_sign_p_at_most_0_01': value['exact_two_sided_sign_p'] <= 0.01,
              'both_orders_positive': set(value['order']) == {'AB', 'BA'} and all(row['geometric_mean_speedup'] > 1 for row in value['order'].values())}
    return {'passes_native_gate': all(checks.values()), 'gate_checks': checks,
            'reduction': value['paired_geometric_mean_time_reduction'],
            'interval_99': value['bootstrap_time_reduction_interval'], 'sign_p': value['exact_two_sided_sign_p'],
            'scope': f'Independent {count} group pairs; eight repetitions are summed within each variant group, with no pooling or extension.'}


def descriptive_resources(core, workflow):
    """Three fixed RSS observations per variant, outside acceptance measurements."""
    config = read(paths(workflow)['config'])
    output = paths(workflow)['output'] / 'descriptive-rss'
    output.mkdir()
    environment = os.environ.copy()
    for key, value in config['env'].items():
        if value is None:
            environment.pop(key, None)
        else:
            environment[key] = str(value)
    records = []
    canonical = Path(config['canonical_executable'])
    for repetition in range(3):
        order = stage()['warming_order'][::1 if repetition % 2 == 0 else -1]
        for variant in order:
            allocator_guard()
            core.install_variant(Path(config['variants'][variant]), canonical)
            label = f'{repetition}-{variant}'
            rss = output / (label + '.json')
            command = [part.replace('{cargo}', str(canonical)) for part in config['command']]
            with (output / (label + '.stdout')).open('wb') as stdout, (output / (label + '.stderr')).open('wb') as stderr:
                result = subprocess.run(['/usr/bin/time', '-f', '{"max_rss_kib":%M}', '-o', str(rss),
                                         '--', *command], cwd=config['cwd'], env=environment,
                                        stdout=stdout, stderr=stderr)
            assert result.returncode == 0 and sha(canonical) == EXPECTED[variant]
            fresh(output / (label + '.stderr'))
            value = read(rss)
            assert value['max_rss_kib'] > 0
            records.append({'repetition': repetition, 'variant': variant, 'command': command,
                            'returncode': result.returncode, **value})
    samples = read(paths(workflow)['output'] / 'samples.json')
    resources = {}
    for variant in ('baseline', 'candidate'):
        cpu = [(row['user_seconds'] + row['system_seconds']) / 8 for row in samples
               if row['stage'] == 'measurement' and row['variant'] == variant]
        resources[variant] = {'binary_bytes': Path(config['variants'][variant]).stat().st_size,
                              'cpu_seconds_per_call_median': statistics.median(cpu),
                              'cpu_seconds_per_call_mean': statistics.mean(cpu),
                              'peak_rss_kib_median': statistics.median(row['max_rss_kib'] for row in records
                                                                     if row['variant'] == variant)}
    core.atomic_json(output / 'report.json', {
        'scope': 'Descriptive only. CPU uses fixed measurement groups. RSS uses three additional calls per variant, excluded from acceptance; no extra observations enter a gate.',
        'records': records, 'resources': resources})


def run(core, expected_seal):
    verify_assets()
    verify_seal(expected_seal)
    assert not STATUS.exists()
    status = {'state': 'starting', 'started_at': core.utc_now(), 'seal_sha256': expected_seal,
              'stage': read(ASSETS)['stage'], 'pairs': stage()['pairs'], 'variants': EXPECTED,
              'integrity_complete': [], 'completed': []}
    core.atomic_json(STATUS, status)
    try:
        # No analyzer or gate runs until BOTH fixed workflows have completed integrity.
        for workflow, seed in stage()['plan']:
            verify_seal(expected_seal)
            status.update(state='preflight', workflow=workflow, quiet=quiet())
            core.atomic_json(STATUS, status)
            preflight(core, workflow)
            verify_seal(expected_seal)
            destination = paths(workflow)
            assert not destination['output'].exists()
            status.update(state='running fixed batch', workflow=workflow, seed=seed, quiet=quiet())
            core.atomic_json(STATUS, status)
            with destination['log'].open('x') as stream:
                subprocess.run([sys.executable, str(RUNNER), 'run', '--config', str(destination['config']),
                                '--output', str(destination['output']), '--phase', stage()['phase'],
                                '--pairs', str(stage()['pairs']), '--warmup-pairs', '2', '--seed', str(seed)],
                               stdout=stream, stderr=subprocess.STDOUT, check=True)
            shutil.copyfile(destination['log'], destination['output'] / 'runner.log')
            core.atomic_json(destination['output'] / 'integrity.json', audit_complete(core, workflow, seed))
            verify_seal(expected_seal)
            status['integrity_complete'].append(workflow)
            core.atomic_json(STATUS, status)
        assert status['integrity_complete'] == ['check', 'test']
        status.update(state='both fixed workflows passed integrity', quiet=quiet())
        core.atomic_json(STATUS, status)
        for workflow, _ in stage()['plan']:
            descriptive_resources(core, workflow)
            verify_seal(expected_seal)
        for workflow, _ in stage()['plan']:
            destination = paths(workflow)
            with (destination['output'] / 'analysis-stdout.json').open('x') as stream:
                subprocess.run([sys.executable, str(RUNNER), 'analyze', str(destination['output']),
                                '--confidence', '.99', '--resamples', '20000', '--seed', '1701',
                                '--minimum-pairs', str(stage()['pairs'])], stdout=stream, check=True)
            result = gate(destination['output'])
            core.atomic_json(destination['output'] / 'native-gate.json', result)
            status['completed'].append({'workflow': workflow, 'directory': str(destination['output']), **result})
            core.atomic_json(STATUS, status)
        verify_seal(expected_seal)
        status.update(state='complete', completed_at=core.utc_now(), quiet=quiet(), uv=uv_identity(),
                      both_workflows_pass=all(row['passes_native_gate'] for row in status['completed']))
        core.atomic_json(STATUS, status)
    except BaseException as error:
        status.update(state='failed', failed_at=core.utc_now(), error=repr(error))
        core.atomic_json(STATUS, status)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--sealed-inputs-sha256')
    args = parser.parse_args()
    core = load_core()
    if args.prepare:
        prepare(core)
    else:
        run(core, args.sealed_inputs_sha256)


if __name__ == '__main__':
    main()
