"""Admission and pair-boundary maintenance around the original native collector."""
import argparse
import json
import os
from pathlib import Path
import stat
import sys
import traceback
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loader_fixture_delta as fixture
import maintenance_02 as maintenance
import paired

def read_ref(row):
    path = Path(row['path'])
    assert paired.sha256(path) == row['sha256'], str(path)
    return json.loads(path.read_bytes())

def load_entry(path):
    entry = json.loads(Path(path).read_bytes())
    inputs = read_ref(entry['inputs'])
    authority = read_ref(entry['authority'])
    assert authority['status'] == 'approved'
    assert authority['inputs_sha256'] == entry['inputs']['sha256']
    assert authority['output'] == entry['output']
    assert authority['pairs'] == 12 and authority['seed'] == 2026102126
    assert authority['warmup_pairs'] == 0
    protocol = read_ref(inputs['protocol'])
    assert protocol['pairs'] == 12 and protocol['warmup_pairs'] == 0
    assert protocol['randomization_seed'] == 2026102126
    assert protocol['balanced_order_plan'] == [list(v) for v in paired.make_plan(12, 2026102126)]
    assert protocol['acceptance'] == inputs['original_acceptance']
    assert protocol['pair_reservation_seconds'] > 0
    return entry, inputs, protocol

def verify_files(inputs):
    for row in inputs['files']:
        path = Path(row['path'])
        assert paired.sha256(path) == row['sha256'], str(path)
        assert path.stat().st_size == row['bytes'], str(path)
        if 'mode' in row:
            assert stat.S_IMODE(path.stat().st_mode) == row['mode'], str(path)
        if 'identity' in row:
            observed = path.stat()
            assert {key: getattr(observed, key) for key in row['identity']} == row['identity'], str(path)
    for row in inputs.get('symlinks', []):
        path = Path(row['path'])
        assert path.is_symlink() and os.readlink(path) == row['target'], str(path)
        assert str(path.resolve()) == row['resolved'], str(path)

def same_service_cycle(before, after):
    assert set(before['services']) == set(after['services']) == set(maintenance.HEAVY)
    for name in maintenance.HEAVY:
        first, last = before['services'][name], after['services'][name]
        assert last['timer']['Id'] == name + '.timer'
        assert last['service']['Id'] == name + '.service'
        assert last['timer']['LoadState'] == last['service']['LoadState'] == 'loaded'
        assert last['timer']['ActiveState'] == 'active'
        assert last['service']['ActiveState'] == 'inactive' and last['service']['SubState'] == 'dead', name
        for category, key in (('timer', 'LastTriggerUSecMonotonic'), ('service', 'ExecMainStartTimestampMonotonic'), ('service', 'ExecMainExitTimestampMonotonic')):
            assert first[category][key] == last[category][key], (name, key)
        assert first['timer']['TimersMonotonic'] == last['timer']['TimersMonotonic'], name

def prepare(args):
    entry, inputs, protocol = load_entry(args.entry)
    assert str(Path(args.batch).resolve()) == entry['output']
    assert args.stage == 'measurement' and 0 <= args.pair < 12 and args.position in (0, 1)
    assert protocol['balanced_order_plan'][args.pair][args.position] == args.variant
    output = Path(entry['output'])
    pair_file = output / f'pair-entry-{args.pair:02d}.json'
    if args.position == 0:
        assert not pair_file.exists()
        ready = maintenance.wait_for_pair(output / f'pair-wait-{args.pair:02d}.jsonl', protocol['pair_reservation_seconds'])
        paired.atomic_json(pair_file, {'pair': args.pair, 'order': protocol['balanced_order_plan'][args.pair], 'admitted': ready})
    else:
        pair = json.loads(pair_file.read_bytes())
        assert pair['pair'] == args.pair and pair['order'] == protocol['balanced_order_plan'][args.pair]
        same_service_cycle(pair['admitted'], maintenance.observe())
    # The original restore and every content/mode/mtime/link guard run unchanged.
    result = fixture.prepare(args.name, args.variant, args.batch, args.stage, args.pair, args.position)
    print(json.dumps(result, indent=2))

def run(args):
    input_ref = {'path': str(Path(args.inputs).resolve()), 'sha256': args.inputs_sha256}
    authority_ref = {'path': str(Path(args.authority).resolve()), 'sha256': args.authority_sha256}
    inputs, authority = read_ref(input_ref), read_ref(authority_ref)
    assert authority['status'] == 'approved' and authority['inputs_sha256'] == args.inputs_sha256
    output = Path(authority['output'])
    assert not output.exists()
    entry_path = Path(inputs['entry_path'])
    assert not entry_path.exists()
    paired.atomic_json(entry_path, {'inputs': input_ref, 'authority': authority_ref, 'output': str(output)})
    entry_hash = paired.sha256(entry_path)
    entry, inputs, protocol = load_entry(entry_path)
    verify_files(inputs)
    configuration = read_ref(inputs['configuration'])
    assert configuration['command'] == protocol['command'] and not configuration.get('metric_files')
    assert configuration['env']['LD_LIBRARY_PATH'] is None
    expected_command = [configuration['canonical_executable'] if x == '{cargo}' else x for x in configuration['command']]
    original_run_command = paired.run_command
    failure = None
    attempted = False
    restoration = None

    def guarded_command(command, cwd, environment, stdout_path, stderr_path):
        if command != expected_command:
            return original_run_command(command, cwd, environment, stdout_path, stderr_path)
        assert paired.sha256(entry_path) == entry_hash
        pair = int(environment['OHM_BENCH_PAIR'])
        position = int(environment['OHM_BENCH_POSITION'])
        assert environment['OHM_BENCH_STAGE'] == 'measurement'
        assert protocol['balanced_order_plan'][pair][position] == environment['OHM_BENCH_VARIANT']
        admission = json.loads((output / f'pair-entry-{pair:02d}.json').read_bytes())['admitted']
        before = maintenance.observe()
        paired.atomic_json(stdout_path.with_suffix('.host-before.json'), before)
        same_service_cycle(admission, before)
        result = original_run_command(command, cwd, environment, stdout_path, stderr_path)
        # The original helper has already persisted raw exit/elapsed/stdout/stderr.
        after = maintenance.observe()
        paired.atomic_json(stdout_path.with_suffix('.host-after.json'), after)
        same_service_cycle(admission, after)
        return result

    paired.run_command = guarded_command
    try:
        attempted = True
        paired.run(argparse.Namespace(config=inputs['configuration']['path'], output=str(output), phase='confirmation', pairs=12, warmup_pairs=0, seed=2026102126))
        fixture.verify(inputs['fixture_name'], output)
        verify_files(inputs)
    except BaseException as error:
        failure = {'type': type(error).__name__, 'message': str(error)}
        traceback.print_exc()
    finally:
        paired.run_command = original_run_command
        if attempted:
            try:
                root, manifest = fixture.load(inputs['fixture_name'])
                fixture.install_variant(Path(manifest['variants']['baseline']), Path(manifest['canonical_executable']))
                restoration = fixture.prepare(inputs['fixture_name'], 'baseline', str(output) + '-terminal-restoration', 'warmup', 0, 0, fixture.make_environment(manifest))
                fixture.check_inputs(manifest)
                verify_files(inputs)
            except BaseException as error:
                restoration = {'failure': {'type': type(error).__name__, 'message': str(error)}}
                failure = failure or restoration['failure']
                traceback.print_exc()
        terminal = {'state': 'complete' if failure is None else 'failed', 'failure': failure, 'inputs': input_ref, 'authority': authority_ref, 'output': str(output), 'restoration': restoration, 'effects_analyzed': False, 'tests_executed': False, 'finished_at': paired.utc_now()}
        paired.atomic_json(Path(inputs['terminal_path']), terminal)
    assert failure is None, failure

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='operation', required=True)
    p = sub.add_parser('run')
    for name in ('inputs', 'inputs-sha256', 'authority', 'authority-sha256'):
        p.add_argument('--' + name, required=True)
    p = sub.add_parser('prepare')
    for name in ('entry', 'name', 'variant', 'batch', 'stage'):
        p.add_argument('--' + name, required=True)
    for name in ('pair', 'position'):
        p.add_argument('--' + name, type=int, required=True)
    args = parser.parse_args()
    (run if args.operation == 'run' else prepare)(args)

if __name__ == '__main__':
    main()
