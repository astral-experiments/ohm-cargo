#!/usr/bin/env python3
"""Review one terminal inheritance phase locally, with explicit statistics opt-in."""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import math
from pathlib import Path
import random
import re
import statistics
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from evidence import CORE, EXPECTED, FREEZE, HOST, REPEATED, ROOT, SEAL, STAGES, Evidence, need, read, relative, sha
from statistics_review import counts, equal, gate, paired

ADDITIVE = ('wall_ns', 'user_seconds', 'system_seconds', 'minor_faults', 'major_faults',
            'voluntary_context_switches', 'involuntary_context_switches')
SAMPLE_FIELDS = ('stage', 'pair', 'order', 'position', 'variant', 'started_at', 'returncode',
                 *ADDITIVE, 'stdout', 'stderr')
SUBRUN_FIELDS = ('stage', 'pair', 'order', 'position', 'variant', 'repetition', 'started_at',
                 'returncode', *ADDITIVE, 'stdout', 'stderr')
COMPILATION = re.compile(r'^\s*(?:Compiling|Checking|Running)\s|^error:', re.M)
GROUPING = {'repetitions_per_variant': 8, 'aggregation': 'sum of individually timed native subprocesses',
            'statistical_unit': 'one baseline/candidate group pair', 'prepare_executions_per_variant_group': 1,
            'workload': 'noop'}


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def timestamp(value):
    parsed = datetime.datetime.fromisoformat(value)
    need(parsed.utcoffset() == datetime.timedelta(), 'timestamp must use UTC')
    return parsed


def machine(value):
    need(value['uname'][1] == HOST and value['uid'] == value['effective_uid'] == 1000
         and value['root_directory_owner_uid'] == 0
         and set(range(8)) <= set(value['affinity']), 'host identity/affinity differs')


def plan(count, seed):
    orders = [['baseline', 'candidate'] for _ in range(count // 2)]
    orders += [['candidate', 'baseline'] for _ in range(count // 2)]
    random.Random(seed).shuffle(orders)
    return orders


def substitute(text, context):
    for key, value in context.items():
        text = text.replace('{' + key + '}', str(value))
    return text


def fresh(evidence, filename):
    text = evidence.file(filename).read_text(errors='replace')
    need('Finished' in text and not COMPILATION.search(text), 'compilation/test/error signature: ' + filename)


def success(evidence, row, require_fresh=False):
    need(row['returncode'] == 0 and type(row['wall_ns']) is int and row['wall_ns'] > 0, 'unsuccessful invocation')
    for key in ADDITIVE:
        need(isinstance(row[key], (int, float)) and not isinstance(row[key], bool)
             and math.isfinite(row[key]) and row[key] >= 0, 'invalid additive value: ' + key)
        if key not in ('user_seconds', 'system_seconds'):
            need(type(row[key]) is int, 'noninteger counter: ' + key)
    evidence.file(row['stdout'])
    evidence.file(row['stderr'])
    if require_fresh:
        fresh(evidence, row['stderr'])


def tables(evidence, root, name, rows, fields):
    need(rows == [json.loads(line) for line in evidence.file(root + '/' + name + '.jsonl').read_text().splitlines()], name + ' JSONL differs')
    with evidence.file(root + '/' + name + '.csv').open(newline='') as stream:
        reader = csv.DictReader(stream)
        need(tuple(reader.fieldnames) == fields, name + ' CSV columns differ')
        csv_rows = list(reader)
    need(len(csv_rows) == len(rows) and all(all(value[key] == str(row[key]) for key in fields)
          for value, row in zip(csv_rows, rows)), name + ' CSV values differ')


def profile_count(path):
    events, summaries = [], []
    with path.open() as stream:
        for line in stream:
            if line.startswith('events:'):
                events.append(line.partition(':')[2].split())
            elif line.startswith('summary:'):
                summaries.append(line.partition(':')[2].split())
    need(len(events) == len(summaries) == 1, 'Callgrind requires one events row and one summary')
    event, summary = events[0], summaries[0]
    need(len(set(event)) == len(event) == len(summary) and 'Ir' in event, 'ambiguous/missing instruction event')
    values = [int(value) for value in summary]
    need(all(value >= 0 for value in values), 'negative Callgrind count')
    return values[event.index('Ir')]


def preflight(evidence, phase, workflow):
    prefix = ROOT + '/metadata/' + phase + '-' + workflow + '-preflight'
    value = read(evidence.file(prefix + '/report.json'))
    need(value['state'] == 'passed' and value['uv_before'] == value['uv_after'] == evidence.seal['uv'], 'preflight identity differs')
    machine(value['machine'])
    need([row['variant'] for row in value['records']] == ['baseline', 'candidate']
         and [row['variant'] for row in value['cross_switch']] == ['baseline', 'candidate'], 'preflight order differs')
    files = {'report.json'}
    for row in value['records']:
        variant = row['variant']
        need(row['binary_sha256'] == EXPECTED[variant] and len(row['warming_runs']) == 3
             and row['warm'] == row['warming_runs'][-1], 'fixed three-call warming differs')
        for index, warm in enumerate(row['warming_runs'], 1):
            success(evidence, warm)
            for field in ('stdout', 'stderr'):
                name = f'{variant}.warm-{index}.{field}'
                need(warm[field] == prefix + '/' + name, 'warming filename differs')
                files.add(name)
        success(evidence, row['trace'], True)
        for field in ('stdout', 'stderr'):
            name = variant + '.trace.' + field
            need(row['trace'][field] == prefix + '/' + name, 'trace filename differs')
            files.add(name)
        name = variant + '.execve.log'
        need(row['trace_path'] == prefix + '/' + name and sha(evidence.file(row['trace_path'])) == row['trace_sha256'], 'trace hash/path differs')
        files.add(name)
        paths = []
        for line in evidence.file(row['trace_path']).read_text().splitlines():
            if re.search(r'= 0\s*$', line):
                match = re.search(r'execve\("([^"]+)"', line) or re.search(r'execveat\([^,]+, "([^"]+)"', line)
                need(match is not None, 'unparsed successful exec trace')
                paths.append(match[1])
        need(paths == row['successful_execve_paths'] == ['/usr/bin/taskset', ROOT + '/active/bin/cargo'], 'preflight executed a compiler/build-script/test child')
    for row in value['cross_switch']:
        success(evidence, row, True)
        for field in ('stdout', 'stderr'):
            name = row['variant'] + '.cross-switch.' + field
            need(row[field] == prefix + '/' + name, 'cross-switch filename differs')
            files.add(name)
    relative_prefix = prefix[len(ROOT) + 1:] + '/'
    need({name[len(relative_prefix):] for name in evidence.files if name.startswith(relative_prefix)} == files, 'extra/missing preflight observations')
    return value


def immutable_inputs(evidence, config, manifest):
    expected = {}
    for name in config['record_files']:
        if name == ROOT + '/controller/measurement-seal.json':
            digest = SEAL
        elif name in evidence.seal['file_sha256']:
            digest = evidence.seal['file_sha256'][name]
        else:
            need(name in evidence.seal['future_reports'], 'unsealed recorded input: ' + name)
            digest = sha(evidence.file(name))
        expected[name] = digest
    # Setup expands runtime/tool symlinks to canonical paths when constructing
    # these record lists. No local workspace-prefix translation is permitted.
    need(manifest['recorded_file_sha256'] == manifest['recorded_file_sha256_after'] == expected,
         'recorded input identities differ from the original seal/current prerequisite')


def raw_workflow(evidence, phase, workflow, seed):
    config = evidence.config(phase, workflow)
    root = ROOT + '/results/' + phase + '-' + workflow
    preflight_value = preflight(evidence, phase, workflow)
    manifest = read(evidence.file(root + '/manifest.json'))
    count = STAGES[phase]['pairs']
    need(manifest['state'] == 'complete' and manifest['phase'] == 'confirmation'
         and (manifest['pairs'], manifest['warmup_pairs'], manifest['seed']) == (count, 2, seed), 'incomplete/wrong fixed workflow')
    need(manifest['variant_sha256'] == manifest['variant_sha256_after'] == EXPECTED, 'non-fresh/changed binary pair')
    need(manifest['configuration'] == config
         and manifest['configuration_path'] == ROOT + '/benchmark/' + phase + '-' + workflow + '.json'
         and manifest['configuration_sha256'] == sha(evidence.file(manifest['configuration_path'])), 'configuration binding differs')
    need(manifest['canonical_executable'] == config['canonical_executable'] and manifest['variant_paths'] == config['variants']
         and manifest['machine']['uname'][1] == HOST, 'canonical paths/host differ')
    machine(manifest['machine'])
    immutable_inputs(evidence, config, manifest)
    plans = {'warmup': plan(2, seed ^ 0x5A17), 'measurement': plan(count, seed)}
    need(manifest['plans'] == plans, 'fixed randomization plan differs')
    identities = [(stage, pair, position, variant, 'AB' if order[0] == 'baseline' else 'BA')
                  for stage, orders in plans.items() for pair, order in enumerate(orders)
                  for position, variant in enumerate(order)]
    keys = ('stage', 'pair', 'position', 'variant', 'order')
    samples = read(evidence.file(root + '/samples.json'))
    need([tuple(row[key] for key in keys) for row in samples] == identities
         and len(samples) == manifest['sample_count'] == 2 * (count + 2), 'raw sample order/count differs')
    tables(evidence, root, 'samples', samples, SAMPLE_FIELDS + (('metric_cargo_ir',) if phase == 'ir' else ()))
    files = {'manifest.json', 'samples.json', 'samples.jsonl', 'samples.csv', 'runner.log',
             'integrity.json', 'analysis.json', 'analysis-stdout.json', 'gate.json'}
    if phase == 'native':
        subruns = read(evidence.file(root + '/subruns.json'))
        need(len(subruns) == 2 * (count + 2) * 8 and subruns == [row for sample in samples for row in sample['repetitions']], 'nested/independent subruns differ')
        tables(evidence, root, 'subruns', subruns, SUBRUN_FIELDS)
        files.update(('subruns.json', 'subruns.jsonl', 'subruns.csv'))
        need(manifest['grouping'] == {**GROUPING, 'subrun_count': len(subruns)}, 'grouping metadata differs')
        harness = {ROOT + '/benchmark/frozen/paired.py': CORE, ROOT + '/benchmark/frozen/paired_repeated.py': REPEATED}
        need(manifest['repeated_harness_sha256'] == manifest['repeated_harness_sha256_after'] == harness, 'grouped harness changed')
    else:
        subruns = []
        need('grouping' not in manifest, 'IR unexpectedly grouped')
    runner_lines, profiles = [], {}
    for sample in samples:
        variant = sample['variant']
        context = {'cargo': config['canonical_executable'], 'variant': variant, 'pair': sample['pair'],
                   'stage': sample['stage'], 'phase': 'confirmation', 'output': root, 'position': sample['position']}
        command = [substitute(part, context) for part in config['command']]
        environment = {key: None if value is None else substitute(str(value), context) for key, value in config['env'].items()}
        need(sample['command'] == command and sample['configured_environment'] == environment, 'sample command/environment differs')
        need(sample['installed_sha256'] == EXPECTED[variant] and sample['executable_unchanged'] is True, 'installed Cargo identity changed')
        success(evidence, sample, phase == 'ir')
        success(evidence, sample['prepare'], True)
        prefix = f"{sample['stage']}-{sample['pair']:04d}-{sample['position']}-{variant}"
        runner_lines.append(f"{prefix}: {sample['wall_ns'] / 1e9:.6f} s\n")
        for field in ('stdout', 'stderr'):
            need(sample[field] == root + '/logs/' + prefix + '.' + field
                 and sample['prepare'][field] == root + '/logs/' + prefix + '.prepare.' + field, 'sample/prepare log path differs')
            files.update(('logs/' + prefix + '.' + field, 'logs/' + prefix + '.prepare.' + field))
        if phase == 'ir':
            need(set(sample['metric_files']) == set(sample['metrics']) == {'cargo_ir'}
                 and 'metric_errors' not in sample, 'instruction metric missing/ambiguous')
            metric = sample['metric_files']['cargo_ir']
            filename = f"callgrind-{sample['stage']}-{sample['pair']}-{variant}.out"
            need(metric['path'] == root + '/' + filename and sha(evidence.file(metric['path'])) == metric['sha256'], 'profile path/hash differs')
            value = profile_count(evidence.file(metric['path']))
            need(type(value) is type(sample['metrics']['cargo_ir']) is type(sample['metric_cargo_ir']) is int
                 and value > 0 and value == sample['metrics']['cargo_ir'] == sample['metric_cargo_ir'], 'raw profile Ir differs')
            profiles[metric['path']] = {'sha256': metric['sha256'], 'Ir': value}
            files.add(filename)
        else:
            need(sample['metrics'] == sample['metric_files'] == {} and 'metric_errors' not in sample, 'native instrumentation present')
            need(sample['repetitions_requested'] == sample['repetitions_completed'] == len(sample['repetitions']) == 8, 'group repetition count differs')
            for index, row in enumerate(sample['repetitions'], 1):
                need(row['phase'] == 'confirmation' and row['repetition'] == index
                     and all(row[key] == sample[key] for key in keys), 'repetition identity differs')
                need(row['command'] == command and row['compiled_packages'] == [], 'native repetition command/compilation differs')
                success(evidence, row, True)
                for field in ('stdout', 'stderr'):
                    filename = 'logs/' + prefix + f'.rep-{index:03d}.' + field
                    need(row[field] == root + '/' + filename, 'repetition log path differs')
                    files.add(filename)
            for field in ADDITIVE:
                total = sum(row[field] for row in sample['repetitions'])
                if field in ('user_seconds', 'system_seconds'):
                    equal(sample[field], float(total), 'group sum ' + field)
                else:
                    need(type(total) is int and type(sample[field]) is int and sample[field] == total, 'integer group sum differs')
            for field in ('stdout', 'stderr'):
                joined = b''.join(f"--- repetition {row['repetition']} ---\n".encode()
                                  + evidence.file(row[field]).read_bytes() + b'\n' for row in sample['repetitions'])
                need(evidence.file(sample[field]).read_bytes() == joined, 'aggregate/raw log bytes differ')
    runner = ''.join(runner_lines).encode()
    need(evidence.file(root + '/runner.log').read_bytes() == runner
         == evidence.file(ROOT + '/logs/' + phase + '-' + workflow + '-runner.log').read_bytes(), 'runner group log differs')
    relative_prefix = root[len(ROOT) + 1:] + '/'
    need({name[len(relative_prefix):] for name in evidence.files if name.startswith(relative_prefix)} == files,
         'extra/missing workflow result files or observations')
    integrity = read(evidence.file(root + '/integrity.json'))
    need(integrity['state'] == 'passed' and integrity['uv_after'] == evidence.seal['uv'], 'controller raw-integrity receipt differs')
    if phase == 'ir':
        need(integrity['pairs'] == 12 and integrity['warmup_pairs'] == 2
             and integrity['invocations_verified'] == integrity['profile_hashes_verified'] == 28, 'IR integrity counts differ')
    else:
        need(integrity['group_pairs'] == 30 and integrity['warmup_group_pairs'] == 2
             and integrity['invocations_verified'] == 512, 'native integrity counts differ')
    need(timestamp(preflight_value['completed_at']) <= timestamp(manifest['started_at'])
         <= timestamp(manifest['finished_at']) <= timestamp(integrity['completed_at']), 'workflow chronology differs')
    starts = [timestamp(row['started_at']) for row in samples]
    need(starts == sorted(starts) and timestamp(manifest['started_at']) <= starts[0]
         <= starts[-1] <= timestamp(manifest['finished_at']), 'sample chronology differs')
    return {'workflow': workflow, 'root': root, 'manifest': manifest, 'samples': samples, 'subruns': subruns,
            'profiles': profiles, 'integrity': integrity,
            'review': {'status': 'passed', 'workflow': workflow, 'pairs': count, 'warmup_pairs': 2,
                       'samples': len(samples), 'subruns': len(subruns), 'profiles': len(profiles), 'seed': seed,
                       'all_tables_logs_plans_sums_and_identities_match': True, 'unwanted_compilation_signatures': 0}}


def analyze(evidence, phase, workload):
    count = STAGES[phase]['pairs']
    wall, cpu, instructions = ([{'order': ''} for _ in range(count)] for _ in range(3))
    for row in workload['samples']:
        if row['stage'] == 'measurement':
            wall[row['pair']].update(order=row['order'], **{row['variant']: row['wall_ns'] / 1e9})
            cpu[row['pair']].update(order=row['order'], **{row['variant']: row['user_seconds'] + row['system_seconds']})
            if phase == 'ir':
                instructions[row['pair']].update(order=row['order'], **{row['variant']: row['metrics']['cargo_ir']})
    expected = paired(wall)
    expected['child_cpu_seconds'] = paired(cpu) if all(row[key] > 0 for row in cpu for key in EXPECTED) else {
        'note': 'At least one sample has zero recorded child CPU time; ratio statistics omitted.'}
    expected['phase'] = 'confirmation'
    expected['variant_sha256'] = EXPECTED
    note = 'This screens one workload only. Require an independently run confirmation batch, correctness validation, and regression checks before a PR performance claim. Repeated candidate selection invalidates treating exploratory p-values as confirmatory evidence.'
    expected['screen'] = {'minimum_pairs': count, 'minimum_time_reduction': 0.01, 'alpha': 1 - 0.99,
                          'passes': expected['bootstrap_speedup_interval'][0] > 1
                              and expected['exact_two_sided_sign_p'] <= 1 - 0.99
                              and expected['paired_geometric_mean_time_reduction'] >= 0.01
                              and all(row['geometric_mean_speedup'] > 1 for row in expected['order'].values()),
                          'note': note}
    if phase == 'ir':
        metric = counts(instructions)
        expected['metrics'] = {'cargo_ir': {
            'format': 'callgrind', 'event': 'Ir',
            'scope': 'Instrumented Cargo process only; child rustc, linker, build-script, and test processes are excluded (--trace-children=no).',
            'statistics': metric,
            'acceptance': 'No acceptance decision. Instruction comparisons screen candidates; confirm native wall time and correctness independently.',
        }}
        expected['screen']['measurement_kind'] = 'instrumented wall time'
        expected['screen']['note'] += ' Callgrind elapsed times are instrumented costs, not native dev-loop timings; this screen cannot establish a native wall-time improvement.'
        decision = gate(phase, metric)
    else:
        expected['grouping'] = {**workload['manifest']['grouping'], 'measurement_group_pairs': count,
                               'measurement_subruns': count * 2 * 8,
                               'inference': 'Bootstrap and exact paired sign test use group aggregates; individual repetitions are not independent samples.'}
        expected['per_invocation_seconds'] = {name: expected[name] / 8 for name in (
            'baseline_median_seconds', 'candidate_median_seconds', 'baseline_mean_seconds', 'candidate_mean_seconds')}
        expected['per_invocation_seconds']['basis'] = 'Group sums divided by the fixed repetition count; medians are across group means.'
        expected['repetition_position_seconds'] = [{
            'repetition': index, **{variant + '_median': statistics.median(row['wall_ns'] / 1e9 for row in workload['subruns']
                                    if row['stage'] == 'measurement' and row['variant'] == variant and row['repetition'] == index)
                                  for variant in EXPECTED}} for index in range(1, 9)]
        expected['screen']['note'] += ' Repetition-position summaries are descriptive only. A passing group screen does not establish a dirty-build speedup.'
        decision = gate(phase, expected)
    actual = read(evidence.file(workload['root'] + '/analysis.json'))
    equal(actual, expected, phase + '/' + workload['workflow'] + ' analysis')
    need(read(evidence.file(workload['root'] + '/analysis-stdout.json')) == actual, 'printed analysis differs')
    equal(read(evidence.file(workload['root'] + '/gate.json')), decision, 'retained gate')
    return expected, {'workflow': workload['workflow'], 'directory': workload['root'], **decision}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controls', type=Path, required=True)
    parser.add_argument('--phase', choices=STAGES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--analyze-after-terminal', action='store_true', help='Use only after root confirms this fixed phase terminal.')
    parser.add_argument('--ir-review', type=Path, help='Required for native; the accepted independent IR review.')
    args = parser.parse_args()
    freeze = read(HERE / 'source-freeze.json')
    for name, digest in freeze['files'].items():
        need(sha(HERE / relative(name)) == digest, 'local review source changed after freeze')
    need(not args.output.exists(), 'review output must be new')
    args.output.mkdir()
    report = {'status': 'invalid', 'phase': args.phase, 'qualifies': False, 'statistics_computed': False,
              'review_started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'review_source_freeze_sha256': sha(HERE / 'source-freeze.json'),
              'scope': 'One fresh-pair phase only; no pooling, sample changes, host access or workload execution.'}
    try:
        evidence = Evidence(args.controls, args.phase)
        evidence.bind()
        report.update(source_freeze_sha256=FREEZE, measurement_seal_sha256=SEAL, variants=EXPECTED,
                      transfer_manifest_sha256=sha(evidence.directory / 'transfer-manifest.json'))
        launch = read(evidence.controls / ('launch-' + args.phase + '.json'))
        need(launch['returncode'] == 0 and launch['operation'] == 'launch-' + args.phase
             and launch['host'] == HOST and launch['root'] == ROOT and launch['sealed_inputs_sha256'] == SEAL,
             'phase launch is not complete/bound')
        report['launch_receipt_sha256'] = sha(evidence.controls / ('launch-' + args.phase + '.json'))
        for suffix in ('stdout', 'stderr'):
            need(sha(evidence.controls / ('launch-' + args.phase + '.' + suffix)) == launch[suffix + '_sha256'], 'launch stream differs')
        status_path = ROOT + '/results/' + args.phase + '-status.json'
        status = read(evidence.file(status_path))
        need(status['state'] == 'complete' and status['phase'] == args.phase and status['seal_sha256'] == SEAL
             and status['variants'] == EXPECTED and status['integrity_complete'] == ['check', 'test'], 'phase is not complete with both integrity receipts')
        report['terminal_status_sha256'] = sha(evidence.file(status_path))
        if args.phase == 'native':
            need(args.ir_review is not None, 'native requires the accepted independent IR review')
            ir = read(args.ir_review)
            need(ir['status'] == 'passed' and ir['qualifies'] is True and ir['phase'] == 'ir'
                 and ir['variants'] == EXPECTED and ir['measurement_seal_sha256'] == SEAL, 'IR review did not qualify this fresh pair')
            need(ir['transfer_manifest_sha256'] == sha(evidence.controls / 'collections/ir/transfer-manifest.json'), 'IR collection binding differs')
            for name, digest in ir['raw_file_sha256'].items():
                need(evidence.files[name] == digest, 'IR evidence changed before native: ' + name)
            prerequisite = evidence.json('metadata/native-prerequisite.json')
            need(prerequisite['state'] == 'passed' and prerequisite['seal_sha256'] == SEAL, 'native prerequisite missing')
            expected_prerequisites = {ROOT + '/results/ir-status.json'} | {
                ROOT + '/results/ir-' + workflow + '/' + name for workflow in ('check', 'test')
                for name in ('manifest.json', 'samples.json', 'samples.jsonl', 'samples.csv', 'integrity.json', 'analysis.json', 'gate.json')}
            need(set(prerequisite['files']) == expected_prerequisites, 'native prerequisite set differs')
            for name, digest in prerequisite['files'].items():
                need(sha(evidence.file(name)) == digest, 'native prerequisite bytes differ')
            need(prerequisite['files'][ROOT + '/results/ir-status.json'] == ir['terminal_status_sha256'], 'native prerequisite/IR status join differs')
            report['ir_review_sha256'] = sha(args.ir_review)
        workloads = [raw_workflow(evidence, args.phase, workflow, seed) for workflow, seed in STAGES[args.phase]['plan']]
        need(timestamp(status['started_at']) <= timestamp(workloads[0]['manifest']['started_at'])
             and timestamp(workloads[0]['integrity']['completed_at']) <= timestamp(workloads[1]['manifest']['started_at'])
             and timestamp(workloads[1]['integrity']['completed_at']) <= timestamp(status['completed_at'])
             <= timestamp(launch['finished_at']), 'serial workflow/phase chronology differs')
        report['workflows'] = [workload['review'] for workload in workloads]
        report['integrity_status'] = 'passed'
        report['raw_file_sha256'] = evidence.files
        report['profiles'] = {name: value for workload in workloads for name, value in workload['profiles'].items()}
        write(args.output / 'raw-integrity.json', {'status': 'passed', 'phase': args.phase,
              'workflows': report['workflows'], 'transfer_manifest_sha256': report['transfer_manifest_sha256'],
              'analysis_files_parsed': False, 'statistics_computed': False})
        if not args.analyze_after_terminal:
            report.update(status='raw-verified', decision='Both workflows verified; statistical opt-in was absent.')
            return 0
        report['statistics_computed'] = True
        completed = []
        for workload in workloads:
            reproduced, decision = analyze(evidence, args.phase, workload)
            write(args.output / (workload['workflow'] + '-reproduced-analysis.json'), reproduced)
            completed.append(decision)
        equal(status['completed'], completed, 'terminal workflow receipts')
        qualifies = all(row['passes_gate'] for row in completed)
        regression = any(row['significant_native_regression'] for row in completed)
        need(status['both_workflows_pass'] is qualifies and status['significant_native_regression'] is regression
             and status['uv'] == evidence.seal['uv'], 'terminal decision or uv differs')
        report.update(status='passed' if qualifies else 'valid-negative', qualifies=qualifies,
                      completed=completed, significant_native_regression=regression,
                      statistical_unit='One paired Cargo invocation' if args.phase == 'ir' else 'One paired aggregate of eight Cargo invocations',
                      bootstrap={'confidence': 0.99, 'resamples': 20000, 'seed': 1701},
                      decision='Both phase gates qualify.' if qualifies else 'Valid fixed phase; one or both gates do not qualify. '
                          + ('No native wall-time claim.' if args.phase == 'native' else 'No instruction-count claim for this phase.'))
        for name, digest in evidence.files.items():
            need(sha(evidence.remote / name) == digest, 'evidence changed during review: ' + name)
        need(sha(evidence.directory / 'transfer-manifest.json') == report['transfer_manifest_sha256']
             and sha(evidence.controls / ('launch-' + args.phase + '.json')) == report['launch_receipt_sha256'], 'transport/launch receipt changed during review')
        for name, digest in freeze['files'].items():
            need(sha(HERE / relative(name)) == digest, 'local reviewer changed during review')
        report['final_evidence_and_review_source_rehash'] = 'passed'
        return 0
    except Exception as error:
        report.update(status='invalid', qualifies=False, error=repr(error))
        return 2
    finally:
        report['review_finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write(args.output / 'review.json', report)
        print(json.dumps({key: value for key, value in report.items() if key not in {'raw_file_sha256', 'profiles'}}, indent=2))


if __name__ == '__main__':
    sys.exit(main())
