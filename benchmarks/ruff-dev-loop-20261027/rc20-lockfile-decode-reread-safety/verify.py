"""Verify the address-free syscall projection independently of the fixture driver."""

import gzip
import hashlib
import json
from pathlib import Path
import re
import sys


def need(condition, reason):
    if not condition:
        raise ValueError(str(reason))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def locked_streams(events):
    active = {}
    completed = []
    for start, end, task, removed, role, op, *args in events:
        if role != 'lock' or op == 'open':
            continue
        fd, *rest = args
        key = (task, fd)
        if op == 'flock':
            flag, ret = rest
            need(ret == 0, args)
            if flag.startswith('LOCK_SH'):
                need(key not in active, args)
                active[key] = [start, None, bytearray(), False]
            elif flag == 'LOCK_UN' and key in active:
                need(active[key][3], 'unlock before EOF')
                active[key][1] = end
            continue
        if key not in active:
            continue
        batch = active[key]
        if op == 'read':
            count, literal = rest
            body = bytes.fromhex(literal)
            need(batch[1] is None and not batch[3] and len(body) <= count, args)
            batch[2].extend(body)
            batch[3] = not body
        elif op == 'close':
            need(batch[1] is not None and rest == [0], args)
            completed.append((batch[0], batch[1], bytes(batch[2])))
            del active[key]
    need(not active, 'unclosed shared reads')
    return completed


def during(events, interval, role, status):
    lo, hi, _ = interval
    return [event[0] for event in events
            if lo < event[0] <= event[1] < hi and event[4:6] == [role, 'open']
            and event[-1] == status and (event[-2] < 0) == (status is not None)]


def check_arm(arm):
    phases = arm['phases']
    good = {'seed', 'valid-appears', 'valid-present-control', 'recovered', 'unchanged'}
    bad = {'semantic-appears', 'semantic-present-control', 'malformed-first-no-writer',
           'malformed-static-control', 'replaced-raced', 'replaced-static'}
    need(set(phases) == good | bad, 'unexpected command roster')
    expected_edges = [['bridge', 'late'], ['member', 'bridge']]
    normalized = {}
    streams = {}
    for stage, data in phases.items():
        need(re.fullmatch('[0-9a-f]{64}', data['raw_trace_sha256']), stage)
        processes = [(role, args) for _, role, args in data['processes']]
        args = ['metadata', '--format-version', '1', '--offline']
        if stage != 'seed':
            args.append('--locked')
        need(processes[:2] == [('rustup-cargo-proxy', ['+ohm', *args]), ('cargo', args)], stage)
        for role, tail in processes[2:]:
            need(role == 'rustc' and (tail == ['-vV'] or '--print=file-names' in tail), stage)
        events = data['events']
        need(events == sorted(events, key=lambda e: e[0]), stage)
        ss = streams[stage] = locked_streams(events)
        need(ss, stage)
        if stage in good:
            need(data['exit'] == 0 and data['error'] is None and data['edges'] == expected_edges, stage)
        else:
            need(data['exit'] == 101 and data['edges'] is None, stage)
            need(data['error'].startswith('error: failed to parse lock file at: Cargo.lock\n'), stage)
        normalized[stage] = [data['exit'], data['edges'], data['error'], [sha(raw) for _, _, raw in ss], processes]
    gold = streams['unchanged'][0][2]
    need(len(gold) == 300 and len(streams['unchanged']) == 1 and phases['unchanged']['cache_hit'], 'settled hit')
    for name in good:
        need(all(raw == gold for _, _, raw in streams[name]), name)
    for name in ['valid-appears', 'semantic-appears']:
        events, actor = phases[name]['events'], phases[name]['actor']
        first, second = streams[name][:2]
        need(first[1] < second[0] and first[2] == second[2], name)
        need(actor['lock_identity_unchanged'] and actor['lock_sha256'] == sha(first[2]), name)
        missing = during(events, first, 'manifest', 'ENOENT')
        marker = during(events, first, 'marker', None)
        present = during(events, second, 'manifest', None)
        need(len(missing) == len(marker) == len(present) == 1 and missing[0] < marker[0], name)
        content = b''.join(bytes.fromhex(x[-1]) for x in events
                           if second[0] < x[0] < second[1] and x[4:6] == ['manifest', 'read'])
        need(content and sha(content) == actor['manifest_sha256'], name)
    corrupt = streams['semantic-appears'][0][2]
    need(len(streams['semantic-appears']) == 2 and corrupt == gold.replace(
        b'name = "late"\nversion = "0.1.0"', b'name = "late"\nversion = "not-a-version"'), 'semantic input')
    need(phases['semantic-appears']['error'] == phases['semantic-present-control']['error']
         and "unexpected character 'n' while parsing major version number" in phases['semantic-appears']['error'],
         'semantic diagnostic')
    broken = b'version = [\n'
    for name in ['malformed-first-no-writer', 'malformed-static-control']:
        need(len(streams[name]) == 1 and streams[name][0][2] == broken, name)
        need(not any(event[4] in ['manifest', 'marker'] for event in phases[name]['events']), name)
    need(phases['malformed-first-no-writer']['error'] == phases['malformed-static-control']['error']
         and 'TOML parse error at line 1, column 12' in phases['malformed-static-control']['error'], 'TOML diagnostic')
    first, second = streams['replaced-raced']
    changed = broken.ljust(len(gold), b' ')
    need(first[2] == gold and second[2] == changed and first[1] < second[0], 'second locked generation')
    need(len(during(phases['replaced-raced']['events'], first, 'marker', None)) == 1, 'replacement ordering')
    need(len(streams['replaced-static']) == 1 and streams['replaced-static'][0][2] == changed, 'static replacement')
    stamp = arm['replacement']
    need(stamp['old_sha256'] == sha(gold) and stamp['new_sha256'] == sha(changed)
         and stamp['size'] == len(gold) and stamp['mtime_ns_identical'] and stamp['new_inode'], 'backdated replacement')
    need(phases['replaced-raced']['error'] == phases['replaced-static']['error']
         and 'unclosed array' in phases['replaced-static']['error'], 'replaced diagnostic')
    return normalized


if __name__ == '__main__':
    if len(sys.argv) > 1:
        data = json.loads(Path(sys.argv[1]).read_bytes())
        check_arm(data)
        print('Verified 11 fresh native commands, including both FIFO rendezvous and the replacement.')
    else:
        directory = Path(__file__).resolve().parent
        bundle = json.loads(gzip.decompress((directory / 'observations.json.gz').read_bytes()))
        sources = json.loads((directory / 'subjects.json').read_text())
        repeats = json.loads((directory / 'fresh-replays.json').read_text())
        for name, arm in bundle.items():
            need(arm['cargo_sha256'] == sources[name]['cargo_sha256'] and
                 arm['rustc_sha256'] == sources['test_rustc']['sha256'], name)
            repeat = repeats[name]
            need(repeat['exit'] == 0 and repeat['commands'] == 11 and
                 repeat['cargo_sha256'] == arm['cargo_sha256'] and
                 set(repeat['raw_trace_sha256']) == set(arm['phases']) and
                 repeat['ordered_native_rosters_locked_payloads_graphs_and_diagnostics_match_original'],
                 'fresh reproduction ' + name)
        need(check_arm(bundle['parent']) == check_arm(bundle['candidate']), 'parent/candidate mismatch')
        need(bundle['parent']['version_output_sha256'] == bundle['candidate']['version_output_sha256'], 'version stamp')
        print('Verified 22 native commands. Diagnostics, graphs and complete shared-locked byte streams agree between arms.')
