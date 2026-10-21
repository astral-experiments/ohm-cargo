#!/usr/bin/env python3
"""Seal and execute four fixed current-stack instruction confirmations."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

SELF = Path(__file__).resolve()
BENCH = SELF.parent.parent if SELF.parent.name == 'frozen' else SELF.parent
ROOT = BENCH.parents[1]
COHORT = ROOT / 'work/production-build/host2-current-stack'
RESULTS = COHORT / 'results'
FROZEN = COHORT / 'frozen'
FROZEN_FILES = ('launch.py', 'stack179-current.source.patch', 'strip_binaries.py',
                'stack179-path-cache.source.patch', 'audit.py', 'manifest.json',
                'path-cache-stack179.incremental.patch', 'collect_variant.py',
                'stack176-current.patch', 'verification-scripts.json', 'stack179-path-cache.patch',
                'stack176-current.source.patch', 'stack179-current.patch',
                'reference-host7-provenance.json', 'prepare_host2_current_stack.py',
                'launcher.json', 'build_driver_host2_current_stack.py')
SOURCE_COPIES = BENCH / 'frozen/restacked-source-records'
HELPER = BENCH / 'frozen/run_followon_ir-d78f4b06a398.py'
assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == 'd78f4b06a398ac8632324b9440531090c022abacec24b295fa5b0566e0029e25'
spec = importlib.util.spec_from_file_location('frozen_followon', HELPER)
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
core = previous.core
TREES = {
    'stack179-current': 'f4ce59f92aa17461fe3c8b68923c88539136045a',
    'stack179-path-cache': '0a392258c801cff734d223a3f9af73d5b5a4e3c0',
    'stack176-current': '06123b7a4dfa10de0abf3b5ccd520e34172bc208',
}
CANDIDATE = 'stack179-path-cache'
BASELINES = {'path-cache-stack179-19718e6d': 'stack179-current',
             'four-changes-stack176-5a16c750': 'stack176-current'}
PLAN = [('path-cache-stack179-19718e6d', 'check', 2026102161),
        ('path-cache-stack179-19718e6d', 'test', 2026102162),
        ('four-changes-stack176-5a16c750', 'check', 2026102171),
        ('four-changes-stack176-5a16c750', 'test', 2026102172)]
PROTOCOLS = {
    BENCH / 'protocol-path-cache-stack179-19718e6d.md': '468bc3a8e4dc93f6c5dab3b27d48ee461d43d4be6f0f957d9a3eb14e84c324b1',
    BENCH / 'protocol-four-changes-stack176-5a16c750.md': '7e89b6ae08712cb5ec6ad36c1caf05bb1cff3ba6b7737bb6f917195dd3513f03',
    BENCH / 'protocol-four-changes-stack176-native-amendment.md': '5a5e48101c549dbeded3594cee8b916fc7b07f2567ca1bf5f9c9cbbda025f3c3',
}
SOURCES = BENCH / 'restacked-path-sources.json'
SOURCE_SHA = 'e4ec48d243de866620c3cdad45bb6823ee7c24c5449c816716a167b62cfd578a'
MANIFEST_SHA = '3ec2696f6a4c0c1e3bf9ee5ef1f16660c10d68c260a3ab6760f2a8e894b292cc'
DRIVER_SHA = 'd11167d435955731069bf365e5e93f6a678798797139488bf590b658117caae0'
PROVENANCE_SHA = 'c4a2486c12bcbf136d7cc05a8af643e60a91ba2cf12e0796fdfef72ab7019124'
COMMON_SHA = '97f093ede30583b1db05c2d1e5d1d26caf70e3fb1588fb507c7871a2a3458726'
SEAL = BENCH / 'restacked-current-stack-production-ir-seal.json'
SUMMARY = BENCH / 'results/restacked-current-stack-production-ir-summary.json'


def verify_inputs():
    assert core.sha256(previous.CORE_PATH) == '50d0cb2d4f595ccfa72d463fedb3ff4dadf9dfc1446c749d482d9ede8418c7cf'
    for path, digest in PROTOCOLS.items():
        assert core.sha256(path) == digest, path
    assert core.sha256(SOURCES) == SOURCE_SHA
    source_records = previous.read_json(SOURCES)
    for name in ['stack179-port.json', 'current-stack-build-patches.json']:
        original = ROOT / 'work/path-cache-publication' / name
        assert core.sha256(SOURCE_COPIES / name) == source_records['files'][str(original)]
    assert core.sha256(FROZEN / 'manifest.json') == MANIFEST_SHA
    assert core.sha256(FROZEN / 'build_driver_host2_current_stack.py') == DRIVER_SHA
    assert core.sha256(RESULTS / 'provenance.json') == PROVENANCE_SHA
    inputs = previous.read_json(FROZEN / 'manifest.json')
    provenance = previous.read_json(RESULTS / 'provenance.json')
    audit = previous.read_json(RESULTS / 'audit-cohort.json')
    assert provenance['common_build_inputs_sha256'] == audit['common_build_inputs_sha256'] == COMMON_SHA
    assert provenance['driver_sha256'] == audit['build_driver_sha256'] == DRIVER_SHA
    assert provenance['frozen_input_manifest_sha256'] == audit['frozen_input_manifest_sha256'] == MANIFEST_SHA
    assert audit['provenance_sha256'] == PROVENANCE_SHA and audit['host7_reference_fields_match']
    assert audit['cohort'] == provenance['cohort'] == inputs['cohort'] == 'host2-current-stack'
    assert core.sha256(FROZEN / 'audit.py') == audit['audit_script_sha256']
    assert core.sha256(FROZEN / 'collect_variant.py') == audit['collector_sha256']
    assert {name: value['tree'] for name, value in inputs['expected_variants'].items()} == TREES
    assert {row['variant'] for row in audit['records']} == set(TREES)
    assert core.sha256(ROOT / 'work/patches/path-cache-stack179.patch') == inputs['incremental_path_patch_sha256'] == '0706ae28f7cfb62774755aec611689eda86c5080846e1e37b33e5bfc60163aa9'
    binaries = {}
    for variant, tree in TREES.items():
        expected = inputs['expected_variants'][variant]
        build = previous.read_json(RESULTS / f'cargo-{variant}.build.json')
        strip = previous.read_json(RESULTS / f'cargo-{variant}.strip.json')
        record = next(row for row in audit['records'] if row['variant'] == variant)
        digest = core.sha256(RESULTS / f'cargo-{variant}')
        assert build['observed_source_tree'] == build['expected_source_tree_from_patches'] == record['source_tree'] == tree
        assert build['embedded_source_commit'] == '5e5d271d763d7beb38b48755e22bd59e93f02b97'
        assert build['source_content_ref'] == expected['source_content_ref']
        assert build['patch_sha256'] == expected['patch_sha256']
        for name, patch_hash in expected['patch_sha256'].items():
            assert core.sha256(FROZEN / name) == patch_hash
        assert core.sha256(RESULTS / f'{variant}.source.patch') == build['observed_diff_sha256'] == expected['canonical_diff_sha256']
        assert digest == strip['stripped_sha256'] == record['stripped_sha256']
        assert build['original_linker_output_sha256'] == strip['source_sha256'] == record['original_linker_output_sha256']
        assert record['verified_allocated_sections'] == len(strip['allocated_sections'])
        assert build['common_build_inputs_sha256'] == record['common_build_inputs_sha256'] == COMMON_SHA
        for suffix in ['stdout', 'stderr']:
            assert core.sha256(RESULTS / f'{variant}.{suffix}') == build[suffix + '_sha256']
        binaries[variant] = digest
    assert binaries['stack179-current'] == 'c165e35dcd0233b6b6e15d81c2bbd6ba19cd07de1352ca63614f27240edcd3c2'
    assert binaries['stack179-path-cache'] == '179f17531a2e9a3475c58965ad4a82248d8eb4af5ce8f1bbfe3d6be5632de86d'
    assert len(set(binaries.values())) == 3
    return binaries


def paths(comparison, workflow):
    label = f'{workflow}-{comparison}-production-ir'
    return {'label': label, 'config': BENCH / f'{label}.json',
            'preflight': BENCH / 'results' / f'{label}-preflight',
            'output': BENCH / 'results' / f'{label}-confirmation'}


def derive(comparison, workflow):
    original_path = BENCH / f'{workflow}-build-output-pr175-production-ir.json'
    original = previous.read_json(original_path)
    config = json.loads(json.dumps(original))
    config['variants'] = {'baseline': str(RESULTS / f'cargo-{BASELINES[comparison]}'),
                          'candidate': str(RESULTS / f'cargo-{CANDIDATE}')}
    config['record_files'] = [path for path in original['record_files']
                              if '/work/production-build/' not in path
                              and '/work/patches/' not in path
                              and not path.endswith('/protocol-upstream-175.md')]
    destination = paths(comparison, workflow)
    extra = [*PROTOCOLS, SOURCES, HELPER, SELF, SEAL, original_path, destination['config'],
             destination['preflight'] / 'report.json', RESULTS / 'provenance.json', RESULTS / 'audit-cohort.json',
             ROOT / 'work/patches/path-cache-stack179.patch',
             SOURCE_COPIES / 'stack179-port.json', SOURCE_COPIES / 'current-stack-build-patches.json',
             Path(sys.executable).resolve(), Path(shutil.which('taskset')).resolve(),
             Path(shutil.which('env')).resolve(), Path(shutil.which('strace')).resolve(),
             ROOT / 'work/profiling-tools/valgrind/usr/bin/valgrind',
             ROOT / 'work/profiling-tools/valgrind/usr/libexec/valgrind/callgrind-amd64-linux',
             ROOT / 'work/profiling-tools/valgrind/usr/libexec/valgrind/vgpreload_core-amd64-linux.so']
    extra.extend(FROZEN / name for name in FROZEN_FILES)
    for variant in TREES:
        extra.extend([RESULTS / f'cargo-{variant}', RESULTS / f'cargo-{variant}.build.json',
                      RESULTS / f'cargo-{variant}.strip.json', RESULTS / f'{variant}.source.patch',
                      RESULTS / f'{variant}.stdout', RESULTS / f'{variant}.stderr',
                      RESULTS / f'{variant}.occupancy.json', RESULTS / f'{variant}.batch-status.json'])
    config['record_files'] = list(dict.fromkeys([*config['record_files'], *map(str, extra)]))
    for key in original:
        if key not in {'variants', 'record_files'}:
            assert config[key] == original[key], key
    return config


def prepare():
    binaries = verify_inputs()
    assert not SEAL.exists() and not SUMMARY.exists()
    configs, records, future, encoded_configs = {}, set(), set(), {}
    for comparison, workflow, seed in PLAN:
        destination = paths(comparison, workflow)
        assert all(not destination[key].exists() for key in ['config', 'preflight', 'output'])
        config = derive(comparison, workflow)
        data = (json.dumps(config, indent=2) + '\n').encode()
        encoded_configs[destination['config']] = data
        configs[destination['label']] = {'path': str(destination['config']), 'sha256': hashlib.sha256(data).hexdigest(),
                                          'comparison': comparison, 'workflow': workflow, 'seed': seed}
        records.update(config['record_files'])
        future.add(str(destination['preflight'] / 'report.json'))
    config_paths = {str(path) for path in encoded_configs}
    snapshots = {path: core.sha256(path) for path in sorted(records - future - config_paths - {str(SEAL)})}
    snapshots.update({str(path): hashlib.sha256(data).hexdigest() for path, data in encoded_configs.items()})
    for path, data in encoded_configs.items():
        with path.open('xb') as stream:
            stream.write(data)
    value = {'prepared_at': core.utc_now(), 'plan': PLAN, 'protocol_sha256': {str(path): digest for path, digest in PROTOCOLS.items()},
             'cohort_variant_sha256': binaries, 'source_trees': TREES, 'configurations': configs,
             'file_sha256': snapshots, 'future_preflight_reports': sorted(future),
             'scope': 'All four configurations and complete matched cohort sealed before current-stack Cargo execution. Future native preflight reports are recorded by the unchanged core before each fixed batch.'}
    with SEAL.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    previous.emit('restacked_inputs_sealed', seal=str(SEAL), sha256=core.sha256(SEAL), variants=binaries, configurations=configs)


def verify_seal(expected):
    assert expected and core.sha256(SEAL) == expected
    seal = previous.read_json(SEAL)
    assert seal['plan'] == [list(row) for row in PLAN]
    for path, digest in seal['file_sha256'].items():
        assert core.sha256(path) == digest, path
    for comparison, workflow, _ in PLAN:
        assert previous.read_json(paths(comparison, workflow)['config']) == derive(comparison, workflow)


def run(expected_seal):
    if Path('/').stat().st_uid == 65534:
        raise RuntimeError('Use the authorized ordinary host; sandbox remapping disables the shared cache')
    verify_inputs()
    verify_seal(expected_seal)
    previous.require_quiet()
    prior = previous.read_json(BENCH / 'results/cumulative-177-178-production-ir-summary.json')
    assert len(prior) == 2 and all(previous.read_json(Path(row['directory']) / 'integrity.json')['state'] == 'passed' for row in prior)
    assert not SUMMARY.exists()
    summaries = []
    for comparison, workflow, seed in PLAN:
        verify_seal(expected_seal)
        previous.require_quiet()
        destination = paths(comparison, workflow)
        config = previous.read_json(destination['config'])
        assert not destination['output'].exists()
        previous.emit('preflight_started', comparison=comparison, workflow=workflow)
        previous.preflight(config, destination['preflight'])
        previous.emit('fixed_batch_started', comparison=comparison, workflow=workflow, pairs=12, warmup_pairs=2,
                      seed=seed, seal_sha256=expected_seal, configuration_sha256=core.sha256(destination['config']), output=str(destination['output']))
        log = BENCH / 'results' / f"{destination['label']}-runner.log"
        with log.open('x') as stream:
            subprocess.run([sys.executable, str(previous.CORE_PATH), 'run', '--config', str(destination['config']),
                            '--output', str(destination['output']), '--phase', 'confirmation', '--pairs', '12',
                            '--warmup-pairs', '2', '--seed', str(seed)], stdout=stream, stderr=subprocess.STDOUT, check=True)
        shutil.copyfile(log, destination['output'] / 'runner.log')
        integrity = previous.audit_complete(destination['output'], seed)
        core.atomic_json(destination['output'] / 'integrity.json', integrity)
        verify_seal(expected_seal)
        with (destination['output'] / 'analysis-stdout.json').open('x') as stream:
            subprocess.run([sys.executable, str(previous.CORE_PATH), 'analyze', str(destination['output']),
                            '--confidence', '.99', '--resamples', '20000', '--seed', '1701'], stdout=stream, check=True)
        gate = previous.result_gate(destination['output'])
        core.atomic_json(destination['output'] / 'instruction-gate.json', gate)
        summaries.append({'comparison': comparison, 'workflow': workflow, 'directory': str(destination['output']), **gate})
        core.atomic_json(SUMMARY, summaries)
        previous.emit('fixed_batch_complete', **summaries[-1])
    previous.require_quiet()
    previous.emit('all_batches_complete', batches=len(summaries), native_amendment_prerequisites_met=all(row['passes_instruction_gate'] for row in summaries), uv=previous.uv_identity())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--lease-granted', action='store_true')
    parser.add_argument('--sealed-inputs-sha256')
    args = parser.parse_args()
    if args.prepare:
        prepare()
    elif args.lease_granted:
        run(args.sealed_inputs_sha256)
    else:
        print(json.dumps({'plan': PLAN, 'status': 'Await complete audited cohort, prepare immutable inputs, then use the granted local measurement lease.'}))


if __name__ == '__main__':
    main()
