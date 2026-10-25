"""Fixed waits outside complete pairs; no service or per-sample guard changes."""
import datetime
from decimal import Decimal
import json
import subprocess
import re
import time
import packages
HEAVY = ('maintenance-reconcile-1', 'maintenance-reconcile-2', 'maintenance-reconcile-3')
MAX_WAIT_SECONDS = 1200

def span_us(text):
    factors = {'w': 604800000000, 'd': 86400000000, 'h': 3600000000, 'min': 60000000, 's': 1000000, 'ms': 1000, 'us': 1}
    parts = re.findall(r'([0-9]+(?:\.[0-9]+)?)(min|ms|us|w|d|h|s)', text)
    assert parts and ''.join(number + unit for number, unit in parts) == ''.join(text.split())
    value = sum(Decimal(number) * factors[unit] for number, unit in parts)
    assert value == int(value)
    return int(value)

def observe():
    rows = {}
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TZ': 'UTC'}
    for name in HEAVY:
        rows[name] = {}
        for suffix, properties in [('timer', ['Id', 'ActiveState', 'NextElapseUSecMonotonic', 'LastTriggerUSecMonotonic']), ('service', ['Id', 'ActiveState', 'SubState', 'CPUUsageNSec', 'ExecMainStartTimestampMonotonic', 'ExecMainExitTimestampMonotonic', 'ExecMainStatus'])]:
            command = ['/usr/bin/systemctl', 'show', name + '.' + suffix, *['--property=' + key for key in properties]]
            result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env, timeout=20)
            assert result.returncode == 0 and not result.stderr
            pairs = [line.split('=', 1) for line in result.stdout.splitlines()]
            assert len(pairs) == len(properties) and {key for key, _ in pairs} == set(properties)
            rows[name][suffix] = dict(pairs)
    return {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'monotonic_us': time.monotonic_ns() // 1000, 'services': rows}


def calibrated_margin(aggregate_pair_ns):
    assert type(aggregate_pair_ns) is int and aggregate_pair_ns > 0
    finish = 10 * ((3 * aggregate_pair_ns + 20000000000 - 1) // 20000000000)
    entry = finish + 30
    assert entry <= 240, 'excluded aggregate pair exceeds the frozen feasibility limit'
    return {'aggregate_pair_ns': aggregate_pair_ns, 'finish_budget_seconds': finish,
            'entry_window_seconds': entry}


def ready(row, margin_seconds):
    assert type(margin_seconds) is int and 40 <= margin_seconds <= 270
    assert set(row['services']) == set(HEAVY)
    for name, data in row['services'].items():
        timer, service = data['timer'], data['service']
        assert timer['Id'] == name + '.timer' and service['Id'] == name + '.service'
        if timer['ActiveState'] != 'active' or service['ActiveState'] != 'inactive' or service['SubState'] != 'dead' or service['ExecMainStatus'] != '0':
            return False
        if timer['NextElapseUSecMonotonic'] in ('', '-', 'n/a', 'infinity', '0', '0us'):
            return False
        if span_us(timer['NextElapseUSecMonotonic']) - row['monotonic_us'] < margin_seconds * 1000000:
            return False
    return packages.quiet(row['packages'])


def wait_for_pair(path, margin_seconds):
    begin = time.monotonic()
    with path.open('x') as stream:
        while True:
            row = observe(); row['packages'] = packages.observe()
            row['ready'] = ready(row, margin_seconds)
            row['wait_elapsed_seconds'] = time.monotonic() - begin
            stream.write(json.dumps(row, sort_keys=True) + '\n'); stream.flush()
            assert row['wait_elapsed_seconds'] <= MAX_WAIT_SECONDS, 'no prospective maintenance window'
            if row['ready']:
                return row
            time.sleep(5)


def finish(entry, pair_start, finish_budget_seconds, destination):
    end = observe(); end['packages'] = packages.observe()
    with destination.open('x') as stream:
        json.dump(end, stream, indent=2, sort_keys=True); stream.write('\n')
    assert packages.quiet(end['packages'])
    delta_mono = end['monotonic_us'] * 1000 - pair_start['monotonic_ns']
    end_utc = datetime.datetime.fromisoformat(end['utc'])
    begin_utc = datetime.datetime.fromisoformat(pair_start['utc'])
    delta_utc_ns = int((end_utc - begin_utc).total_seconds() * 1000000000)
    if finish_budget_seconds is not None:
        assert 0 <= delta_mono <= finish_budget_seconds * 1000000000
        assert 0 <= delta_utc_ns <= finish_budget_seconds * 1000000000
    for name in HEAVY:
        before, after = entry['services'][name], end['services'][name]
        assert after['service']['ActiveState'] == 'inactive' and after['service']['SubState'] == 'dead'
        assert after['service']['ExecMainStatus'] == '0'
        assert after['timer']['LastTriggerUSecMonotonic'] == before['timer']['LastTriggerUSecMonotonic']
        assert after['service']['ExecMainStartTimestampMonotonic'] == before['service']['ExecMainStartTimestampMonotonic']
        deadline = span_us(before['timer']['NextElapseUSecMonotonic'])
        assert end['monotonic_us'] < deadline
        utc_deadline = datetime.datetime.fromisoformat(entry['utc']) + datetime.timedelta(microseconds=deadline - entry['monotonic_us'])
        assert end_utc < utc_deadline
    for name in packages.NAMES:
        assert end['packages']['services'][name]['ExecMainStartTimestampMonotonic'] == entry['packages']['services'][name]['ExecMainStartTimestampMonotonic']
    return end
