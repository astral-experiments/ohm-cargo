#!/usr/bin/env python3
"""Seal and run the prospective host8 current-stack native confirmation."""
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
import subprocess
import sys

SELF = Path(__file__).resolve()
ROOT = SELF.parents[1]
ASSETS = SELF.parent / 'assets.json'
SEAL = SELF.parent / 'native-seal.json'
STATUS = ROOT / 'native-current-stack-status.json'
CORE = ROOT / 'benchmark/frozen/paired.py'
RUNNER = ROOT / 'benchmark/frozen/paired_repeated.py'
CORE_SHA = '50d0cb2d4f595ccfa72d463fedb3ff4dadf9dfc1446c749d482d9ede8418c7cf'
RUNNER_SHA = '50547460e030aa73e1f48121bf477cf8f4a4538bf1bb577851af54176750b6d3'
IR_SEAL_SHA = '9ff5aee1606282e928801701ac6a4fd7299ff12b15a748648ba256362c6140e9'
UV_COMMIT = '3d82a6ad5a7eab8c68236553b7846517767c4b61'
EXPECTED = {
    'baseline': '59dc8bcef32b84a7ee2e84e02fbedfbcaa526783683af8cf19166723486ac27f',
    'candidate': '179f17531a2e9a3475c58965ad4a82248d8eb4af5ce8f1bbfe3d6be5632de86d',
}
NAMES = {'baseline': 'stack176-current', 'candidate': 'stack179-path-cache'}
TREES = {'baseline': '06123b7a4dfa10de0abf3b5ccd520e34172bc208',
         'candidate': '0a392258c801cff734d223a3f9af73d5b5a4e3c0'}
PLAN = [('check', 2026102173), ('test', 2026102174)]
PROTOCOLS = {
    'protocol-path-cache-stack179-19718e6d.md': '468bc3a8e4dc93f6c5dab3b27d48ee461d43d4be6f0f957d9a3eb14e84c324b1',
    'protocol-four-changes-stack176-5a16c750.md': '7e89b6ae08712cb5ec6ad36c1caf05bb1cff3ba6b7737bb6f917195dd3513f03',
    'protocol-four-changes-stack176-native-amendment.md': '5a5e48101c549dbeded3594cee8b916fc7b07f2567ca1bf5f9c9cbbda025f3c3',
}
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
    rows = subprocess.check_output(['ps', '-eo', 'pid=,comm=,pcpu=,pmem=', '--sort=-pcpu'], text=True).splitlines()
    competing = [row for row in rows if row.split()[1] in BUILDERS
                 or row.split()[1].startswith(('cargo-', 'callgrind-'))]
    assert not competing, competing
    return {'process_snapshot': rows[:20], 'load_average': list(os.getloadavg())}


def uv_identity():
    head = subprocess.check_output(['git', '-C', str(ROOT / 'uv'), 'rev-parse', 'HEAD'], text=True).strip()
    status = subprocess.check_output(['git', '-C', str(ROOT / 'uv'), 'status', '--porcelain'], text=True)
    assert head == UV_COMMIT and not status
    return {'commit': head, 'status': status, 'lock_sha256': sha(ROOT / 'uv/Cargo.lock')}


def verify_assets():
    assert socket.gethostname() == 'charlie-oss-8'
    assert os.getuid() == 1000 and ROOT.stat().st_uid == 1000 and Path('/').stat().st_uid == 0
    assets = read(ASSETS)
    for relative, digest in assets['files'].items():
        path = ROOT / relative
        assert path.resolve() == path and sha(path) == digest, relative
    assert assets['local_ir_seal_sha256'] == IR_SEAL_SHA
    proof = read(SELF.parent / 'ir-prerequisites.json')
    assert proof['seal_sha256'] == IR_SEAL_SHA and proof['all_four_gates_and_integrity_pass']
    expected_pairs = {(comparison, workflow) for comparison in ('path-cache-stack179-19718e6d', 'four-changes-stack176-5a16c750') for workflow in ('check', 'test')}
    assert {(row['comparison'], row['workflow']) for row in proof['batches']} == expected_pairs
    assert len(proof['batches']) == 4
    for row in proof['batches']:
        assert row['integrity_state'] == 'passed' and row['gate']['passes_instruction_gate']
        assert all(row['gate']['gate_checks'].values()) and row['gate']['statistics']['pairs'] == 12
    for name, digest in PROTOCOLS.items():
        assert sha(SELF.parent / 'protocols' / name) == digest
    audit = read(SELF.parent / 'cohort/results/audit-cohort.json')
    assert audit['common_build_inputs_sha256'] == '97f093ede30583b1db05c2d1e5d1d26caf70e3fb1588fb507c7871a2a3458726'
    for variant, name in NAMES.items():
        binary = SELF.parent / 'binaries' / ('cargo-' + name)
        strip = read(SELF.parent / 'cohort/results' / f'cargo-{name}.strip.json')
        build = read(SELF.parent / 'cohort/results' / f'cargo-{name}.build.json')
        row = next(row for row in audit['records'] if row['variant'] == name)
        assert sha(binary) == strip['stripped_sha256'] == row['stripped_sha256'] == EXPECTED[variant]
        assert build['observed_source_tree'] == row['source_tree'] == TREES[variant]
    return assets


def paths(workflow):
    label = workflow + '-four-changes-stack176-5a16c750'
    return {'config': ROOT / 'benchmark' / (label + '-native.json'),
            'preflight': ROOT / 'metadata' / (label + '-native-preflight'),
            'output': ROOT / 'results' / (label + '-native-confirmation'),
            'log': ROOT / 'logs' / (label + '-native-runner.log')}


def derive(workflow, assets):
    original_path = SELF.parent / 'base-configs' / (workflow + '.json')
    original = read(original_path)
    config = json.loads(json.dumps(original))
    assert config['cwd'] == str(ROOT / 'uv')
    assert config['canonical_executable'] == str(ROOT / 'active/bin/cargo')
    assert config['repetitions'] == 8 and config['repeatable_workload'] == 'noop'
    assert workflow != 'test' or '--no-run' in config['command']
    config['variants'] = {key: str(SELF.parent / 'binaries' / ('cargo-' + name)) for key, name in NAMES.items()}
    config['record_files'] = [name for name in original['record_files']
                              if '/binaries/stripped/' not in name and '/patches/' not in name
                              and not name.endswith(('/protocol-upstream-175.md', '/protocol-cumulative-177-178.md',
                                                     '/diagnose-build-output-remap-loader-v2.py', '/native_combined_driver.py'))]
    destination = paths(workflow)
    extra = [ROOT / name for name in assets['files']]
    extra.extend([ASSETS, SEAL, original_path, destination['config'], destination['preflight'] / 'report.json',
                  Path(sys.executable).resolve(), Path(shutil.which('taskset')).resolve(), Path(shutil.which('strace')).resolve()])
    config['record_files'] = list(dict.fromkeys([*config['record_files'], *map(str, extra)]))
    assert all(config[key] == original[key] for key in original if key not in {'variants', 'record_files'})
    return config


def prepare(core):
    assets = verify_assets()
    assert not SEAL.exists() and not STATUS.exists()
    encoded, future, records = {}, set(), set()
    for workflow, _ in PLAN:
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
    value = {'prepared_at': core.utc_now(), 'plan': PLAN, 'variants': EXPECTED, 'source_trees': TREES,
             'file_sha256': hashes, 'future_preflight_reports': sorted(future), 'uv': uv_identity(),
             'scope': 'Both 30-group native configurations sealed before current-stack Cargo execution on this host.'}
    with SEAL.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'event': 'native_inputs_sealed', 'sha256': sha(SEAL), 'variants': EXPECTED}), flush=True)


def verify_seal(expected):
    assert expected and sha(SEAL) == expected
    value = read(SEAL)
    assert value['plan'] == [list(row) for row in PLAN] and value['variants'] == EXPECTED
    for path, digest in value['file_sha256'].items():
        assert sha(path) == digest, path
    assets = read(ASSETS)
    for workflow, _ in PLAN:
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
    for variant in ('baseline', 'candidate'):
        quiet()
        canonical = Path(config['canonical_executable'])
        core.install_variant(Path(config['variants'][variant]), canonical)
        assert sha(canonical) == EXPECTED[variant]
        command = [part.replace('{cargo}', str(canonical)) for part in config['prepare_command']]
        warm = core.run_command(command, config['cwd'], environment, output / (variant + '.warm.stdout'), output / (variant + '.warm.stderr'))
        assert warm['returncode'] == 0
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
        records.append({'variant': variant, 'binary_sha256': EXPECTED[variant], 'warm': warm, 'trace': trace,
                        'trace_path': str(trace_path), 'trace_sha256': sha(trace_path), 'successful_execve_paths': executable_paths})
    cross_switch = []
    for variant in ('baseline', 'candidate'):
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
    assert manifest['state'] == 'complete' and manifest['phase'] == 'confirmation'
    assert (manifest['pairs'], manifest['warmup_pairs'], manifest['seed']) == (30, 2, seed)
    assert manifest['variant_sha256'] == manifest['variant_sha256_after'] == EXPECTED
    assert manifest['recorded_file_sha256'] == manifest['recorded_file_sha256_after']
    expected_harness = {str(RUNNER): RUNNER_SHA, str(CORE): CORE_SHA}
    assert manifest['repeated_harness_sha256'] == manifest['repeated_harness_sha256_after'] == expected_harness
    assert sha(paths(workflow)['config']) == manifest['configuration_sha256']
    assert manifest['configuration'] == read(paths(workflow)['config'])
    for path, digest in manifest['recorded_file_sha256'].items():
        assert sha(path) == digest, path
    expected_plans = {'warmup': [list(order) for order in core.make_plan(2, seed ^ 0x5A17)],
                      'measurement': [list(order) for order in core.make_plan(30, seed)]}
    assert manifest['plans'] == expected_plans
    expected_samples = [(stage, pair, position, variant, 'AB' if order[0] == 'baseline' else 'BA')
                        for stage, plan in expected_plans.items() for pair, order in enumerate(plan)
                        for position, variant in enumerate(order)]
    assert [(row['stage'], row['pair'], row['position'], row['variant'], row['order']) for row in samples] == expected_samples
    orders = manifest['plans']['measurement']
    assert orders.count(['baseline', 'candidate']) == orders.count(['candidate', 'baseline']) == 15
    assert len(samples) == 64
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
            assert row['phase'] == 'confirmation' and row['repetition'] == repetition
            assert all(row[key] == sample[key] for key in ['stage', 'pair', 'position', 'variant', 'order'])
            assert row['returncode'] == 0 and row['wall_ns'] > 0 and row['compiled_packages'] == []
            assert manifest['canonical_executable'] in row['command']
            fresh(row['stderr'])
        invocations += len(repetitions)
    assert invocations == manifest['grouping']['subrun_count'] == 512
    return {'state': 'passed', 'completed_at': core.utc_now(), 'group_pairs': 30,
            'warmup_group_pairs': 2, 'invocations_verified': invocations, 'uv_after': uv_identity()}


def gate(output):
    value = read(output / 'analysis.json')
    assert value['pairs'] == 30 and value['confidence'] == 0.99
    assert value['bootstrap_resamples'] == 20000 and value['bootstrap_seed'] == 1701
    assert value['grouping']['repetitions_per_variant'] == 8
    checks = {'fixed_30_group_pairs': value['pairs'] == 30,
              'at_least_one_percent': value['paired_geometric_mean_time_reduction'] >= 0.01,
              'positive_99_percent_lower_bound': value['bootstrap_time_reduction_interval'][0] > 0,
              'two_sided_sign_p_at_most_0_01': value['exact_two_sided_sign_p'] <= 0.01,
              'both_orders_positive': set(value['order']) == {'AB', 'BA'} and all(row['geometric_mean_speedup'] > 1 for row in value['order'].values())}
    return {'passes_native_gate': all(checks.values()), 'gate_checks': checks,
            'reduction': value['paired_geometric_mean_time_reduction'],
            'interval_99': value['bootstrap_time_reduction_interval'], 'sign_p': value['exact_two_sided_sign_p'],
            'scope': 'Independent 30 group pairs; eight repetitions are summed within each variant group, with no pooling or extension.'}


def run(core, expected_seal):
    verify_assets()
    verify_seal(expected_seal)
    assert read(ROOT / 'native-combined-status.json')['state'] == 'complete'
    assert not STATUS.exists()
    status = {'state': 'starting', 'started_at': core.utc_now(), 'seal_sha256': expected_seal, 'completed': []}
    core.atomic_json(STATUS, status)
    try:
        for workflow, seed in PLAN:
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
                                '--output', str(destination['output']), '--phase', 'confirmation', '--pairs', '30',
                                '--warmup-pairs', '2', '--seed', str(seed)], stdout=stream, stderr=subprocess.STDOUT, check=True)
            shutil.copyfile(destination['log'], destination['output'] / 'runner.log')
            core.atomic_json(destination['output'] / 'integrity.json', audit_complete(core, workflow, seed))
            verify_seal(expected_seal)
            with (destination['output'] / 'analysis-stdout.json').open('x') as stream:
                subprocess.run([sys.executable, str(RUNNER), 'analyze', str(destination['output']), '--confidence', '.99',
                                '--resamples', '20000', '--seed', '1701', '--minimum-pairs', '30'], stdout=stream, check=True)
            result = gate(destination['output'])
            core.atomic_json(destination['output'] / 'native-gate.json', result)
            status['completed'].append({'workflow': workflow, 'directory': str(destination['output']), **result})
            core.atomic_json(STATUS, status)
        status.update(state='complete', completed_at=core.utc_now(), quiet=quiet(), uv=uv_identity())
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
