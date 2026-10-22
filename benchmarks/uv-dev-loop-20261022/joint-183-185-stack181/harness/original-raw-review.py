#!/usr/bin/env python3
"""Independently verify both complete raw workflows before reproducing any effect."""
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import Evidence, need, read, sha
import common as c
from statistics_review import counts, equal, paired, gate as original_gate

ROOT = str(c.ROOT)
HOST = c.HOST
STAGES = c.STAGES
EXPECTED = None
SEAL = None
ADDITIVE = ('wall_ns','user_seconds','system_seconds','minor_faults','major_faults','voluntary_context_switches','involuntary_context_switches')
SAMPLE_FIELDS = ('stage','pair','order','position','variant','started_at','returncode',*ADDITIVE,'stdout','stderr')
COMPILATION = re.compile(r'^\s*(?:Compiling|Checking|Running)\s|^error:', re.M)

def gate(phase, value):
    need(phase == 'ir', 'no native phase is planned')
    result = original_gate(phase, value)
    result.pop('significant_native_regression')
    result['native_speed_and_regressions'] = 'unverified'
    return result

def timestamp(value):
    parsed = datetime.datetime.fromisoformat(value)
    need(parsed.utcoffset() == datetime.timedelta(), 'timestamp must use UTC')
    return parsed

def machine(value):
    need(value['uname'][1] == HOST and value['uid'] == value['effective_uid'] == 1000
         and value['root_directory_owner_uid'] == 0
         and set(value['affinity']) == {8}, 'host identity/affinity differs')

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


def setup(evidence):
    value = read(evidence.file(ROOT + '/metadata/setup.json'))
    finished = read(evidence.file(ROOT + '/metadata/setup-complete.json'))
    need(value['state'] == 'prepared-without-warming' and finished['state'] == 'complete'
         and value['host'] == HOST and value['root'] == ROOT, 'setup not complete for assigned host/root')
    need(value['controller_path'] == c.CONTROLLER_PATH and value['controller_affinity'] == [8], 'setup environment differs')
    need(value['uv'] == evidence.seal['uv'] == {'commit': c.UV_COMMIT, 'status': '', 'lock_sha256': c.UV_LOCK}, 'uv identity differs')
    need(value['runtime_sha256'] == c.RUNTIME_HASHES and value['configuration_catalog'] == evidence.seal['configuration_presence'], 'runtime/configuration identities differ')
    need(finished['measurement_seal_sha256'] == SEAL and finished['configs'] == evidence.seal['configs'], 'setup completion seal/configs differ')
    need(timestamp(value['prepared_at']) <= timestamp(evidence.seal['created_at']) <= timestamp(finished['completed_at']), 'setup chronology differs')
    for alias, row in value['runtime_aliases'].items():
        need(alias.startswith((ROOT + '/ohm/', ROOT + '/profiling-tools/')), 'unexpected runtime alias')
        if row['sha256'] is not None:
            need(evidence.seal['file_sha256'][row['resolved']] == row['sha256'], 'runtime alias target omitted from input closure')
    for name, digest in value['tool_sha256'].items():
        need(evidence.seal['file_sha256'][name] == digest, 'tool hash omitted from input closure')
    for workflow, _ in c.PLAN:
        base_path = ROOT + '/controller/base-configs/ir-' + workflow + '.json'
        need(sha(evidence.file(base_path)) == value['base_config_sha256'][workflow], 'base config differs')
        config = evidence.config('ir', workflow)
        need(config['env']['CARGO_TARGET_DIR'] == ROOT + '/targets/ir-' + workflow
             and config['env']['CARGO_BUILD_BUILD_DIR'] == ROOT + '/shared-cache/ir-' + workflow, 'workflow caches are not separate')
    return {'status': 'passed', 'both_configs_sealed_before_warming': True, 'exact_unmodified_uv': True,
            'separate_check_and_test_target_and_cache': True, 'canonical_cargo_path_shared_within_pair': True}


def review(directory, phase, seal_sha, output, analyze_after_terminal):
    global EXPECTED, SEAL
    need(phase in ('setup', 'ir'), 'only setup and the fixed IR phase exist')
    SEAL = seal_sha
    output = Path(output)
    need(not output.exists(), 'new independent review output required')
    output.mkdir(parents=True, exist_ok=False)
    result = {'status': 'checking', 'phase': phase, 'started_at': c.now(),
              'collection': str(Path(directory).resolve()), 'measurement_seal_sha256': seal_sha,
              'protocol_sha256': c.PROTOCOL_SHA, 'controls_source_freeze_sha256': sha(c.HERE / 'source-freeze.json'),
              'native_speed_and_regressions': 'unverified'}
    try:
        evidence = Evidence(directory, phase, seal_sha)
        result['transfer_manifest_sha256'] = sha(Path(directory) / 'transfer-manifest.json')
        result['files_verified'] = len(evidence.files)
        if not evidence.complete:
            need(not analyze_after_terminal, 'failed/incomplete phase cannot enter statistics')
            result.update(status='retained-not-qualified', qualifies_instruction_only=False,
                          boundary=evidence.transfer['boundary'], no_effects_evaluated=True)
            return result
        EXPECTED = evidence.variants
        result['setup'] = setup(evidence)
        if phase == 'setup':
            need(not analyze_after_terminal, 'setup has no statistics')
            need(all(not row['lexists'] for row in evidence.transfer['workflow_footprint'].values()), 'setup fixtures/preflight/results are not untouched')
            result.update(status='passed', no_effects_evaluated=True, delivery_sha256=evidence.transfer['delivery_sha256'])
            return result
        status = read(evidence.file(ROOT + '/results/ir-status.json'))
        need(status['state'] == 'complete' and status['integrity_complete'] == ['check', 'test']
             and status['measurement_seal_sha256'] == SEAL, 'fixed cohort is not complete')
        # No analysis or gate JSON is decoded by either raw_workflow call.
        workloads = [raw_workflow(evidence, 'ir', workflow, seed) for workflow, seed in c.PLAN]
        need([w['workflow'] for w in workloads] == ['check', 'test'], 'both primary raw audits required')
        need(all(timestamp(w['integrity']['completed_at']) <= timestamp(status['raw_audits_completed_at'])
                 for w in workloads), 'analysis tail preceded both raw audits')
        c.write_once(output / 'raw-integrity.json', {'status': 'passed', 'completed_at': c.now(),
                     'workflows': [w['review'] for w in workloads], 'no_effects_evaluated': True})
        result['raw_integrity_sha256'] = sha(output / 'raw-integrity.json')
        need(analyze_after_terminal, 'explicit --analyze-after-terminal is required after both raw audits')
        decisions = []
        for workload in workloads:
            statistics_value, decision = analyze(evidence, 'ir', workload)
            c.write_once(output / (workload['workflow'] + '-independent-statistics.json'), statistics_value)
            decisions.append(decision)
        equal(status['completed'], decisions, 'terminal fixed decisions')
        qualifies = all(row['passes_gate'] for row in decisions)
        need(status['qualifies_instruction_only'] is qualifies and status['native_speed_and_regressions'] == 'unverified', 'terminal qualification differs')
        result.update(status='passed', decisions=decisions, qualifies_instruction_only=qualifies,
                      both_required_primary_endpoints=True, no_pooling_or_additive_claim=True,
                      raw_profiles_verified=sum(len(w['profiles']) for w in workloads))
        return result
    except BaseException as error:
        result.update(status='failed', error=repr(error), qualifies_instruction_only=False)
        raise
    finally:
        result['finished_at'] = c.now()
        c.write_once(output / 'review.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collection', required=True)
    parser.add_argument('--phase', choices=('setup', 'ir'), required=True)
    parser.add_argument('--sealed-inputs-sha256', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--analyze-after-terminal', action='store_true')
    args = parser.parse_args()
    value = review(args.collection, args.phase, args.sealed_inputs_sha256, args.output, args.analyze_after_terminal)
    print(json.dumps(value, indent=2, sort_keys=True))
