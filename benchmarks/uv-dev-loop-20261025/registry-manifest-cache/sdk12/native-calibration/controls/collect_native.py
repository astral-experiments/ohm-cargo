"""Finite registry native phase; effects are files, never controller output."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import time
import traceback
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C
import activity
import dirty_fixture
import env_trace
import inventory
import maintenance
import native_run
import output_admission
import quiescence
import states
import window
import registry_cache
import admission


def check_diagnostics(log, label, reference):
    for suffix in ('stdout', 'stderr'):
        actual = (log/(label+'.'+suffix)).read_text()
        row = reference[suffix]
        assert C.sha(row['path']) == row['sha256']
        expected = Path(row['path']).read_text()
        assert C.diagnostics(actual) == C.diagnostics(expected), 'ordinary Cargo diagnostics differ'


def fresh(log, label, descendants):
    group = native_run.run(log, label, descendants, timed=False, trace=True)
    descendants.drain(label, group=group, seconds=5)
    events = env_trace.trace_records((log/(label+'.trace')).read_text())
    successful = [row for row in events if row['successful']]
    compiler = [row for row in successful if row['executable'] in (C.ENV['RUSTC'], C.ENV['RUSTDOC'])]
    C.save(log/(label+'.fresh.json'), {'trace_sha256': C.sha(log/(label+'.trace')),
           'successful_execs': len(successful), 'compiler_calls': len(compiler)})
    assert not compiler, 'fresh-parent/child guard launched a compiler'
    assert len(successful) == 1 and successful[0]['executable'] == str(C.ROOT/'bin/cargo')
    assert successful[0]['argv'] == C.PROTOCOL['command']
    assert successful[0]['environment'] == [key+'='+value for key,value in C.ENV.items()]
    assert dirty_fixture.compile_packages((log/(label+'.stderr')).read_text()) == []


def retain_outputs(log, label, arm):
    blobs = C.NATIVE/'blobs'
    blobs.mkdir(exist_ok=True)
    rows = []
    for spec in C.INPUT['native_output_specs'][arm]:
        actual = C.identity(spec['path'])
        destination = blobs/actual['sha256']
        if not destination.exists():
            temporary = blobs/(actual['sha256']+'.writing')
            assert not temporary.exists()
            shutil.copyfile(actual['path'], temporary)
            os.chmod(temporary, 0o400)
            assert C.sha(temporary) == actual['sha256']
            with temporary.open('rb') as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        assert destination.stat().st_nlink == 1 and C.sha(destination) == actual['sha256']
        rows.append({'identity': actual, 'blob': C.ref(destination)})
    C.save(log/(label+'.raw-outputs.json'), rows)
    return rows


def check_outputs(log, label, arm, retained):
    specs = C.INPUT['native_output_specs'][arm]
    checked = [output_admission.inspect_output(spec) for spec in specs]
    assert [row['identity'] for row in checked] == [row['identity'] for row in retained]
    C.save(log/(label+'.outputs.json'), checked)
    return checked


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--inputs-sha256', required=True)
    p.add_argument('--mode', choices=('rehearsal', 'measure'), required=True)
    p.add_argument('--authority', type=Path, required=True)
    p.add_argument('--authority-sha256', required=True)
    args = p.parse_args()
    os.umask(0o077)
    os.environ['PATH']='/usr/bin:/bin'
    os.environ['LANG']=os.environ['LC_ALL']='C.UTF-8'
    authority = C.read_ref({'path': str(args.authority), 'sha256': args.authority_sha256})
    assert authority['status'] == 'approved' and authority['mode'] == args.mode
    packet = C.configure(args.inputs, args.inputs_sha256)
    os.sched_setaffinity(0, {8})
    assert authority['inputs_sha256'] == args.inputs_sha256 and authority['phase'] == packet['phase']
    phase = packet['phase']
    assert phase in ('aa', 'ab')
    assert args.mode != 'rehearsal' or phase == 'aa'
    if phase == 'ab':
        decision = C.read_ref(packet['aa_decision'])
        assert decision['both_passed'] is True and decision['phase'] == 'aa'
    if args.mode == 'measure':
        assert packet['margin'] is not None and packet['margin_acceptance'] is not None
        cohort = C.read_ref(authority['cohort'])
        assert cohort['state'] == 'fixed-registry-native-cohort' and cohort['phase'] == phase
        assert cohort['protocol_sha256'] == packet['protocol']['sha256']
        assert cohort['collector_sha256'] == C.sha(__file__)
        assert [row['hostname'] for row in cohort['members']] == C.PROTOCOL['hosts']
        member = cohort['members'][packet['host_index']]
        assert member['inputs_sha256'] == args.inputs_sha256 and member['output'] == authority['output']
    log = Path(authority['output'])
    assert log == C.NATIVE/'records'/(args.mode+'-'+phase+'-01') and not log.exists()
    log.mkdir(parents=True, mode=0o700)
    shutil.copyfile(args.inputs, log/'inputs.json')
    assert C.sha(log/'inputs.json') == args.inputs_sha256
    shutil.copyfile(args.authority, log/'authority.json')
    assert C.sha(log/'authority.json') == args.authority_sha256
    C.save(log/'execution.json', {'inputs_sha256': args.inputs_sha256,
           'authority_sha256': args.authority_sha256, 'mode': args.mode, 'phase': phase,
           'started_at': C.utc(), 'source_sha256': C.sha(__file__)})
    activity.PS_SHA256 = packet['tool_commands']['/usr/bin/ps']['sha256']
    original = (C.NATIVE/'source-original.rs').read_bytes()
    assert hashlib.sha256(original).hexdigest() == C.OLD['source']['sha256']
    allowed = {C.OLD['source']['sha256']}
    native_banks = {arm: {part: str(Path(packet['banks'][arm])/part) for part in C.PARTS} for arm in C.ARMS}
    state = states.States(C.OLD['active_paths'], native_banks, log/'bank-moves.jsonl')
    descendants = quiescence.Descendants(lambda number, row: C.save(log/('ownership-%04d.json'%number), row))
    samples = []
    failure = None
    cleanup_failure = None
    parent_fresh = {arm: False for arm in C.ARMS}
    started_native = []
    pair_log = None
    phase_started = time.monotonic()
    plan = C.PROTOCOL['phases'][phase]
    orders = ['AB'] if args.mode == 'rehearsal' else plan['orders'][str(packet['host_index'])]

    def cargo_for(arm):
        return 'baseline' if phase == 'aa' else arm

    def activate(arm, *, validate=True):
        descendants.assert_no_children()
        assert all(quiescence.group_absent(group) for group in descendants.groups)
        state.select(arm)
        C.install_cargo(cargo_for(arm))
        if validate:
            assert C.context() == packet['contexts'][arm]
        assert not list((C.ROOT/'tmp').iterdir())

    def cache_snapshot(arm):
        return registry_cache.observe(Path(C.ENV['CARGO_HOME']), cargo_for(arm))

    def park():
        descendants.assert_no_children()
        assert all(quiescence.group_absent(group) for group in descendants.groups)
        state.park()

    try:
        C.fixed_guard()
        for arm in C.ARMS:
            assert inventory.inventory(packet['banks'][arm]) == C.read_ref(packet['start_manifests'][arm])
        assert not (inventory.inode_set(packet['banks']['baseline']) & inventory.inode_set(packet['banks']['candidate']))
        for arm in C.ARMS:
            activate(arm)
            fresh(log, arm+'.initial-fresh', descendants)
            assert C.context() == packet['contexts'][arm]
            park()
        C.install_cargo('original')
        for pair_index, order in enumerate(orders):
            assert time.monotonic()-phase_started <= plan['maximum_owner_seconds']
            pair_log = log/('pair-%02d' % pair_index)
            pair_log.mkdir()
            free = shutil.disk_usage(C.NATIVE).free
            reserve = C.PROTOCOL['disk']['reserve_bytes'] + C.PROTOCOL['disk']['growth_bytes']
            remaining = 2*(len(orders)-pair_index)*packet['output_bytes']
            C.save(pair_log/'space.json', {'free_bytes': free, 'required_bytes': reserve+remaining})
            assert free >= reserve+remaining
            before = dirty_fixture.content(original, log, 'measurement', pair_index, 'before')
            after = dirty_fixture.content(original, log, 'measurement', pair_index, 'after_')
            assert len(before) == len(after) and sum(a != b for a, b in zip(before, after)) == 5
            allowed.update(hashlib.sha256(x).hexdigest() for x in (before, after))
            parent_fresh = {arm: False for arm in C.ARMS}
            C.source_write(before, allowed)
            ordered = [C.PROTOCOL['labels'][letter] for letter in order]
            for arm in ordered:
                activate(arm)
                C.save(pair_log/(arm+'.before-cache-initial.json'), cache_snapshot(arm))
                group = native_run.run(pair_log, arm+'.before', descendants, timed=False)
                descendants.drain(arm+'-before', group=group, seconds=5)
                assert dirty_fixture.compile_packages((pair_log/(arm+'.before.stderr')).read_text()) == ['uv']
                fresh(pair_log, arm+'.before-fresh', descendants)
                assert C.context() == packet['contexts'][arm]
                C.save(pair_log/(arm+'.prepared-cache.json'), cache_snapshot(arm))
                park()
            C.source_write(after, allowed)
            C.install_cargo('original')
            C.save(pair_log/'prepared.json', {'pair': pair_index, 'order': order,
                   'source_before_sha256': hashlib.sha256(before).hexdigest(),
                   'source_after_sha256': hashlib.sha256(after).hexdigest(),
                   'source_bytes': len(after), 'changed_bytes': 5, 'both_before_fresh': True,
                   'cargo_by_label': {arm: C.OLD['variants'][cargo_for(arm)]['artifact']['sha256'] for arm in C.ARMS}})
            C.sync_owned(C.NATIVE, pair_log/'pre-pair-sync.json')
            margin = C.PROTOCOL['rehearsal_margin'] if args.mode == 'rehearsal' else packet['margin']
            entry = window.admit(pair_log, margin['entry_window_seconds'])
            start = {'monotonic_ns': time.monotonic_ns(), 'utc': C.utc()}
            C.save(pair_log/'pair-start.json', start)
            started_native = []
            for position, arm in enumerate(ordered):
                activate(arm)
                C.save(pair_log/(arm+'.native-cache-before.json'), cache_snapshot(arm))
                activity.guard(pair_log, arm+'.before-activity')
                window.finish(entry, start, margin['finish_budget_seconds'], pair_log/(arm+'.before-window.json'))
                label = arm+'.native'
                started_native.append(arm)
                group = native_run.run(pair_log, label, descendants, timed=args.mode == 'measure')
                # Cargo exit is the endpoint; owned descendant cleanup is outside its clock.
                descendants.drain(arm+'-native', group=group, seconds=5)
                activity.guard(pair_log, arm+'.after-activity')
                window.finish(entry, start, margin['finish_budget_seconds'], pair_log/(arm+'.after-window.json'))
                C.save(pair_log/(arm+'.native-cache-after.json'), cache_snapshot(arm))
                park()
                samples.append({'pair': pair_index, 'position': position, 'variant': arm,
                                'label': str((pair_log/label).relative_to(log)), 'order': order})
            window.finish(entry, start, margin['finish_budget_seconds'], pair_log/'pair-finish.json')
            aggregate = time.monotonic_ns()-start['monotonic_ns']
            C.save(pair_log/'aggregate.json', {'aggregate_pair_ns': aggregate, 'not_a_comparison_sample': True})
            # Both actual child states are captured before diagnostics, decoding or restoration.
            retained = {}
            for arm in ordered:
                activate(arm, validate=False)
                retained[arm] = retain_outputs(pair_log, arm+'.native', arm)
                park()
            for arm in ordered:
                activate(arm)
                check_diagnostics(pair_log, arm+'.native', packet['native_diagnostics'][arm])
                assert C.sha(C.SOURCE) == hashlib.sha256(after).hexdigest()
                assert C.context() == packet['contexts'][arm]
                check_outputs(pair_log, arm+'.native', arm, retained[arm])
                fresh(pair_log, arm+'.after-fresh', descendants)
                park()
            C.source_write(original, allowed)
            for arm in ordered:
                activate(arm)
                group = native_run.run(pair_log, arm+'.restore', descendants, timed=False)
                descendants.drain(arm+'-restore', group=group, seconds=5)
                fresh(pair_log, arm+'.restored-fresh', descendants)
                assert C.context() == packet['contexts'][arm]
                restored = retain_outputs(pair_log, arm+'.restored', arm)
                check_outputs(pair_log, arm+'.restored', arm, restored)
                C.save(pair_log/(arm+'.restored-cache.json'), cache_snapshot(arm))
                parent_fresh[arm] = True
                park()
            C.install_cargo('original')
            C.save(pair_log/'complete.json', {'state': 'complete', 'pair': pair_index,
                   'order': order, 'parent_fresh': dict(parent_fresh), 'active_paths_absent': True})
            if args.mode == 'rehearsal':
                C.save(log/'margin.json', maintenance.calibrated_margin(aggregate))
        C.fixed_guard()
        for arm in C.ARMS:
            C.save(log/(arm+'.final-bank.json'), inventory.inventory(packet['banks'][arm]))
        for arm in C.ARMS:
            assert inventory.inventory(admission.instruction_bank(C.OLD,C.ROOT,arm)) == C.read_ref(packet['instruction_bank_manifests'][arm])
    except BaseException as error:
        failure = {'type': type(error).__name__, 'message': str(error)}
        traceback.print_exc()
        try:
            descendants.terminate_owned('failed-attempt-cleanup')
            park()
            # Preserve completed outputs even when the first fallible check refused them.
            if pair_log is not None:
                for arm in started_native:
                    if not (pair_log/(arm+'.native.raw-outputs.json')).exists():
                        activate(arm, validate=False)
                        retain_outputs(pair_log, arm+'.native', arm)
                        park()
        except BaseException as cleanup:
            cleanup_failure = {'type': type(cleanup).__name__, 'message': str(cleanup)}
    finally:
        try:
            descendants.assert_no_children()
            park()
            C.source_write(original, allowed)
            C.install_cargo('original')
            descendants.close()
        except BaseException as cleanup:
            cleanup_failure = {'type': type(cleanup).__name__, 'message': str(cleanup)}
        terminal = {'state': 'complete' if failure is None and cleanup_failure is None else 'invalid',
                    'failure': failure, 'cleanup_failure': cleanup_failure, 'phase': phase, 'mode': args.mode,
                    'schedule': orders, 'samples': samples, 'effects_analyzed': False,
                    'source_restored': C.sha(C.SOURCE) == C.OLD['source']['sha256'],
                    'cargo_restored': C.sha(C.ROOT/'bin/cargo') == C.OLD['original_cargo']['sha256'],
                    'active_paths_absent': all(not os.path.lexists(C.ROOT/part) for part in C.PARTS),
                    'banks_parked': all(Path(path).is_dir() for arm in native_banks.values() for path in arm.values()),
                    'parent_fresh': parent_fresh, 'finished_at': C.utc()}
        if (C.NATIVE/'runtime-moves.jsonl').exists():
            shutil.copyfile(C.NATIVE/'runtime-moves.jsonl', log/'runtime-moves.jsonl')
        C.save(log/'terminal.json', terminal)
        manifest = {str(path.relative_to(log)): C.identity(path) for path in sorted(log.rglob('*')) if path.is_file()}
        C.save(log/'manifest.json', manifest)
        C.save(log/'completion.json', {'state': terminal['state'], 'terminal_sha256': C.sha(log/'terminal.json'),
               'manifest_sha256': C.sha(log/'manifest.json'), 'inputs_sha256': args.inputs_sha256})
    return 0 if failure is None and cleanup_failure is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
