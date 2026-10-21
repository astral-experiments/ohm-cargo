#!/usr/bin/env python3
"""Audit completed original-PR175 composition data without re-analysis or Cargo."""
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
REMOTE = ROOT / 'work/remote-native-8/remote'
EXPECTED = {
    'baseline': '63495905e7b0b11ad99fa4c2c2674e43657b9902a2e3142ef735fd83efa44cf8',
    'candidate': 'a60f7c6ccb37c582263a02b462673de9b7d5e7a68127258d150be49f1b1721be',
}
assert not (set(os.sched_getaffinity(0)) & set(range(8)))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def saved_log(directory, saved):
    parts = Path(saved).parts
    index = parts.index(directory.name)
    relative = Path(*parts[index + 1:])
    assert not relative.is_absolute() and '..' not in relative.parts
    return directory / relative


def fresh(path):
    text = path.read_text()
    assert 'Finished' in text, path
    assert not re.search(r'^\s*(?:Compiling|Checking|Running)\s|^error:', text, re.M), path


transfers = {}
for name, expected, count in [
    ('combined-results-transfer-sha256.json', '95f9041b2a0f2ace08698c81351c9edbf311a24e0ef0ca009a0917bac4c62ad4', 2582),
    ('combined-metadata-transfer-sha256.json', 'bac203bb9d4d52e0877fbd7d36f33fbf8b25b643cb82c40024ef37e59353c84b', 18),
    ('combined-preflight-transfer-sha256.json', '60dd4ea96861ded2608e73a9965679f388b8fac86d85c506d8b4324b26d93987', 20),
]:
    path = REMOTE.parent / name
    assert sha(path) == expected
    inventory = read(path)
    assert len(inventory) == count
    for relative, digest in inventory.items():
        assert sha(REMOTE / relative) == digest, relative
    transfers[name] = {'sha256': expected, 'files_verified': count}

reports = []
for workflow, ir_seed, native_seed in [('check', 2026102141, 2026102143), ('test', 2026102142, 2026102144)]:
    for kind, seed, pairs in [('ir', ir_seed, 12), ('native', native_seed, 30)]:
        parent = ROOT / 'work/benchmark/results' if kind == 'ir' else REMOTE / 'results'
        suffix = 'production-ir' if kind == 'ir' else 'native'
        directory = parent / f'{workflow}-build-output-remap-loader-v2-pr175-{suffix}-confirmation'
        manifest, samples, analysis = [read(directory / name) for name in ['manifest.json', 'samples.json', 'analysis.json']]
        assert manifest['state'] == 'complete' and manifest['phase'] == 'confirmation'
        assert manifest['pairs'] == pairs and manifest['warmup_pairs'] == 2 and manifest['seed'] == seed
        assert manifest['variant_sha256'] == manifest['variant_sha256_after'] == EXPECTED
        assert manifest['recorded_file_sha256'] == manifest['recorded_file_sha256_after']
        assert len(samples) == 2 * (pairs + 2)
        orders = manifest['plans']['measurement']
        assert orders.count(['baseline', 'candidate']) == orders.count(['candidate', 'baseline']) == pairs // 2
        command = manifest['configuration']['command']
        assert '-Zohm-defaults=yes' in command and '--locked' in command and '--offline' in command
        if workflow == 'test':
            assert '--no-run' in command
        invocations = 0
        for sample in samples:
            assert sample['returncode'] == 0 and sample['executable_unchanged']
            assert sample['installed_sha256'] == EXPECTED[sample['variant']]
            assert sample['prepare']['returncode'] == 0
            fresh(saved_log(directory, sample['prepare']['stderr']))
            if kind == 'native':
                assert sample['repetitions_requested'] == sample['repetitions_completed'] == 8
                repetitions = sample['repetitions']
                assert len(repetitions) == 8
                assert sum(r['wall_ns'] for r in repetitions) == sample['wall_ns']
                for field in ['user_seconds', 'system_seconds']:
                    assert math.isclose(sum(r[field] for r in repetitions), sample[field], abs_tol=1e-9)
                for run in repetitions:
                    assert run['returncode'] == 0 and run['compiled_packages'] == []
                    assert run['wall_ns'] > 0
                    assert manifest['canonical_executable'] in run['command']
                    fresh(saved_log(directory, run['stderr']))
                invocations += len(repetitions)
            else:
                assert sample['metrics']['cargo_ir'] > 0 and '--trace-children=no' in sample['command']
                fresh(saved_log(directory, sample['stderr']))
                invocations += 1
        if kind == 'ir':
            integrity, gate = read(directory / 'integrity.json'), read(directory / 'instruction-gate.json')
            assert integrity['state'] == 'passed' and integrity['invocations_verified'] == 28
            assert gate['passes_instruction_gate'] and all(gate['gate_checks'].values())
            value = analysis['metrics']['cargo_ir']['statistics']
            reduction = value['paired_geometric_mean_count_reduction']
            interval = value['bootstrap_count_reduction_interval']
            interpretation = 'Passes the predeclared Cargo-process instruction gate.'
            passes = True
        else:
            assert manifest['repeated_harness_sha256'] == manifest['repeated_harness_sha256_after']
            assert manifest['grouping']['subrun_count'] == invocations == 512
            assert analysis['grouping']['repetitions_per_variant'] == 8
            assert not analysis['screen']['passes']
            value = analysis
            reduction = value['paired_geometric_mean_time_reduction']
            interval = value['bootstrap_time_reduction_interval']
            passes = False
            if workflow == 'test':
                assert 0 < interval[0] and reduction < 0.01 and value['exact_two_sided_sign_p'] <= 0.01
                interpretation = 'Positive statistical signal, below the predeclared 1% minimum; full native gate fails.'
            else:
                assert interval[0] < 0 < interval[1]
                interpretation = 'Native interval crosses zero; full native gate fails.'
        assert value['pairs'] == pairs and value['confidence'] == 0.99
        assert value['bootstrap_resamples'] == 20000 and value['bootstrap_seed'] == 1701
        reports.append({'workflow': workflow, 'kind': kind, 'directory': str(directory),
                        'seed': seed, 'pairs': pairs, 'warmup_pairs': 2, 'invocations_verified': invocations,
                        'reduction_percent': 100 * reduction, 'interval_99_percent': [100 * x for x in interval],
                        'sign_p': value['exact_two_sided_sign_p'], 'gate_passes': passes,
                        'interpretation': interpretation})

evidence = read(REMOTE / 'metadata/build-output-remap-loader-v2-warm-execve-evidence.json')
assert evidence['uv_git_status'] == ''
assert evidence['uv_commit'] == '3d82a6ad5a7eab8c68236553b7846517767c4b61'
for workflow, variants in evidence['workloads'].items():
    for variant, data in variants.items():
        assert data['cargo_sha256'] == EXPECTED[variant]
        assert len(data['successful_exec_paths']) == 2
        assert data['successful_exec_paths'][0] == '/usr/bin/taskset'
        assert data['successful_exec_paths'][1].endswith('/active/bin/cargo')
        assert sha(REMOTE / 'logs' / Path(data['trace_path']).name) == data['trace_sha256']

report = {'audited_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'status': 'passed', 'scope': 'Completed original-PR175 output+loader batch integrity only; no statistical re-analysis, Cargo execution, or current-stack inference.',
          'script_sha256': sha(Path(__file__)), 'transfers': transfers, 'batches': reports}
destination = ROOT / 'work/benchmark/results/cumulative-177-178-batch-audit.json'
destination.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
