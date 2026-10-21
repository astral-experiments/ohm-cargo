#!/usr/bin/env python3
"""Seal, then run the fixed cumulative PR177+PR178 instruction validations."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

SELF = Path(__file__).resolve()
BENCH = SELF.parent.parent if SELF.parent.name == 'frozen' else SELF.parent
ROOT = BENCH.parents[1]
PRODUCTION = ROOT / 'work/production-build/results'
HELPER = BENCH / 'frozen/run_followon_ir-d78f4b06a398.py'
assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == 'd78f4b06a398ac8632324b9440531090c022abacec24b295fa5b0566e0029e25'
spec = importlib.util.spec_from_file_location('frozen_followon', HELPER)
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
core = previous.core
PROTOCOL = BENCH / 'protocol-cumulative-177-178.md'
PROTOCOL_SHA = 'a3eea99c4278b25baf8062bed0a76009f5b605aad76c686cd599202feddf7a67'
CANDIDATE = 'build-output-remap-loader-v2'
CANDIDATE_SHA = 'a60f7c6ccb37c582263a02b462673de9b7d5e7a68127258d150be49f1b1721be'
TREE = '4117e012ab1e082867dcb5a4b2a227e7f5200ff6'
PROVENANCE = PRODUCTION / f'provenance-pr175-{CANDIDATE}.json'
PROVENANCE_SHA = '635c0296edb306049a3040e3bd90d52553557a19f6c9bc6097c9a2c6350df3b2'
AUDIT = PRODUCTION / f'audit-pr175-{CANDIDATE}.json'
FROZEN_BUILD = ROOT / 'work/production-build/frozen/accepted-sbom'
SEAL = BENCH / 'cumulative-177-178-production-ir-seal.json'
PLAN = [('check', 2026102141), ('test', 2026102142)]
PATCHES = {
    ROOT / 'work/production-build/pr175.patch': '30332415e2fdc6735719868cddeeb717cc856415f8cd1731ab5696c109f697dc',
    ROOT / 'work/patches/build-output-remap.patch': 'a967d4353a4dc3dc252a45231dada1a3f01b27d7f206c0c16f69c61e9796d265',
    ROOT / 'work/patches/loader-path-v2-final.patch': 'be2146042f257eb1e36f3d5de804a2ff991f87676b5fe38fe4a5d6a30c4ea1e9',
}


def verify_inputs():
    assert core.sha256(previous.CORE_PATH) == '50d0cb2d4f595ccfa72d463fedb3ff4dadf9dfc1446c749d482d9ede8418c7cf'
    assert core.sha256(PROTOCOL) == PROTOCOL_SHA
    assert core.sha256(PROVENANCE) == PROVENANCE_SHA
    assert core.sha256(PRODUCTION / 'cargo-pr175') == previous.BASELINE_SHA
    assert core.sha256(PRODUCTION / f'cargo-pr175-{CANDIDATE}') == CANDIDATE_SHA
    for path, digest in PATCHES.items():
        assert core.sha256(path) == digest, path
    metadata = previous.read_json(PRODUCTION / f'cargo-pr175-{CANDIDATE}.build.json')
    assert metadata['observed_source_tree'] == metadata['expected_source_tree_from_patches'] == TREE
    assert metadata['embedded_source_commit'] == '5e5d271d763d7beb38b48755e22bd59e93f02b97'
    assert metadata['patch_sha256'] == {path.name: digest for path, digest in PATCHES.items()}
    assert core.sha256(PRODUCTION / f'pr175-{CANDIDATE}.source.patch') == metadata['observed_diff_sha256']
    strip = previous.read_json(PRODUCTION / f'cargo-pr175-{CANDIDATE}.strip.json')
    assert strip['stripped_sha256'] == CANDIDATE_SHA
    assert strip['source_sha256'] == metadata['original_linker_output_sha256']
    audit = previous.read_json(AUDIT)
    assert audit['all_common_inputs_match'] and audit['provenance_sha256'] == PROVENANCE_SHA
    assert len(audit['records']) == 1
    record = audit['records'][0]
    assert record['source_tree'] == TREE and record['stripped_sha256'] == CANDIDATE_SHA
    assert record['verified_allocated_sections'] == len(strip['allocated_sections'])
    provenance = previous.read_json(PROVENANCE)
    baseline = previous.read_json(PRODUCTION / 'provenance-pr175.json')
    for key in audit['common_input_fields']:
        assert provenance[key] == baseline[key], key
    assert core.sha256(FROZEN_BUILD / 'build_driver_accepted_sbom.py') == provenance['driver_sha256']
    assert core.sha256(FROZEN_BUILD / 'manifest.json') == provenance['frozen_input_manifest_sha256']


def paths(workflow):
    label = f'{workflow}-{CANDIDATE}-pr175-production-ir'
    return {
        'label': label,
        'config': BENCH / f'{label}.json',
        'preflight': BENCH / 'results' / f'{label}-preflight',
        'output': BENCH / 'results' / f'{label}-confirmation',
    }


def derive(workflow):
    original_path = BENCH / f'{workflow}-build-output-pr175-production-ir.json'
    original = previous.read_json(original_path)
    config = json.loads(json.dumps(original))
    config['variants']['candidate'] = str(PRODUCTION / f'cargo-pr175-{CANDIDATE}')
    config['record_files'] = [path for path in config['record_files'] if 'build-output-remap' not in path]
    destination = paths(workflow)
    extra = [*PATCHES, PROTOCOL, HELPER, SELF, SEAL, original_path, destination['config'],
             destination['preflight'] / 'report.json', PROVENANCE, AUDIT,
             PRODUCTION / f'cargo-pr175-{CANDIDATE}.build.json',
             PRODUCTION / f'cargo-pr175-{CANDIDATE}.strip.json',
             PRODUCTION / f'pr175-{CANDIDATE}.source.patch',
             FROZEN_BUILD / 'build_driver_accepted_sbom.py', FROZEN_BUILD / 'manifest.json',
             FROZEN_BUILD / 'audit_accepted_sbom.py', FROZEN_BUILD / 'verification-scripts.json',
             Path(sys.executable).resolve(), Path(shutil.which('taskset')).resolve(),
             Path(shutil.which('env')).resolve(), Path(shutil.which('strace')).resolve(),
             ROOT / 'work/profiling-tools/valgrind/usr/bin/valgrind',
             ROOT / 'work/profiling-tools/valgrind/usr/libexec/valgrind/callgrind-amd64-linux',
             ROOT / 'work/profiling-tools/valgrind/usr/libexec/valgrind/vgpreload_core-amd64-linux.so']
    config['record_files'] = list(dict.fromkeys([*config['record_files'], *map(str, extra)]))
    for key in original:
        if key not in {'variants', 'record_files'}:
            assert config[key] == original[key], key
    return config


def prepare():
    verify_inputs()
    for workflow, seed in PLAN:
        assert str(seed) in PROTOCOL.read_text()
        destination = paths(workflow)
        assert not destination['config'].exists()
        assert not destination['output'].exists()
        assert not destination['preflight'].exists()
    assert not SEAL.exists()
    records = set()
    configs = {}
    for workflow, seed in PLAN:
        config = derive(workflow)
        path = paths(workflow)['config']
        with path.open('x') as stream:
            json.dump(config, stream, indent=2)
            stream.write('\n')
        configs[workflow] = {'path': str(path), 'sha256': core.sha256(path), 'seed': seed}
        records.update(config['record_files'])
    future = {str(paths(workflow)['preflight'] / 'report.json') for workflow, _ in PLAN}
    snapshots = {path: core.sha256(path) for path in sorted(records - future - {str(SEAL)})}
    value = {'prepared_at': core.utc_now(), 'protocol_sha256': PROTOCOL_SHA, 'plan': PLAN,
             'variant_sha256': {'baseline': previous.BASELINE_SHA, 'candidate': CANDIDATE_SHA},
             'candidate_source_tree': TREE, 'configurations': configs, 'file_sha256': snapshots,
             'future_preflight_reports': sorted(future),
             'scope': 'Static inputs sealed before any cumulative Cargo execution. Native preflight reports will be added by the unchanged core record_files mechanism before timing.'}
    with SEAL.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    previous.emit('cumulative_inputs_sealed', seal=str(SEAL), sha256=core.sha256(SEAL), configurations=configs)


def verify_seal(expected):
    assert expected and core.sha256(SEAL) == expected
    seal = previous.read_json(SEAL)
    assert seal['plan'] == [list(row) for row in PLAN]
    for path, digest in seal['file_sha256'].items():
        assert core.sha256(path) == digest, path
    for workflow, _ in PLAN:
        assert previous.read_json(paths(workflow)['config']) == derive(workflow)


def run(expected_seal):
    if Path('/').stat().st_uid == 65534:
        raise RuntimeError('Use the authorized ordinary host; sandbox remapping disables the shared cache')
    verify_inputs()
    verify_seal(expected_seal)
    previous.require_quiet()
    prior = previous.read_json(BENCH / 'results/followon-production-ir-summary.json')
    assert len(prior) == 4
    for result in prior:
        directory = Path(result['directory'])
        assert previous.read_json(directory / 'manifest.json')['state'] == 'complete'
        assert previous.read_json(directory / 'integrity.json')['state'] == 'passed'
    summaries = []
    for workflow, seed in PLAN:
        verify_seal(expected_seal)
        destination = paths(workflow)
        config = previous.read_json(destination['config'])
        assert not destination['output'].exists()
        previous.emit('preflight_started', candidate=CANDIDATE, workflow=workflow)
        previous.preflight(config, destination['preflight'])
        previous.emit('fixed_batch_started', candidate=CANDIDATE, workflow=workflow,
                      pairs=12, warmup_pairs=2, seed=seed, seal_sha256=expected_seal,
                      configuration_sha256=core.sha256(destination['config']), output=str(destination['output']))
        log = BENCH / 'results' / f"{destination['label']}-runner.log"
        with log.open('x') as stream:
            subprocess.run([sys.executable, str(previous.CORE_PATH), 'run', '--config', str(destination['config']),
                            '--output', str(destination['output']), '--phase', 'confirmation', '--pairs', '12',
                            '--warmup-pairs', '2', '--seed', str(seed)], stdout=stream, stderr=subprocess.STDOUT, check=True)
        shutil.copyfile(log, destination['output'] / 'runner.log')
        integrity = previous.audit_complete(destination['output'], seed)
        core.atomic_json(destination['output'] / 'integrity.json', integrity)
        verify_seal(expected_seal)
        with (destination['output'] / 'analysis-stdout.json').open('w') as stream:
            subprocess.run([sys.executable, str(previous.CORE_PATH), 'analyze', str(destination['output']),
                            '--confidence', '0.99', '--resamples', '20000', '--seed', '1701'], stdout=stream, check=True)
        gate = previous.result_gate(destination['output'])
        core.atomic_json(destination['output'] / 'instruction-gate.json', gate)
        summaries.append({'candidate': CANDIDATE, 'workflow': workflow, 'directory': str(destination['output']), **gate})
        core.atomic_json(BENCH / 'results/cumulative-177-178-production-ir-summary.json', summaries)
        previous.emit('fixed_batch_complete', **summaries[-1])
    previous.require_quiet()
    previous.emit('all_batches_complete', batches=len(summaries), uv=previous.uv_identity())


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
        print(json.dumps({'plan': PLAN, 'status': 'Prepare static inputs, then execute only after prior queue completion and the granted lease.'}))


if __name__ == '__main__':
    main()
