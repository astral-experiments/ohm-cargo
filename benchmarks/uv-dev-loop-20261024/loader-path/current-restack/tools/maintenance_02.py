"""Prospective waits before complete pairs; service-cycle guards remain strict."""
import datetime
from decimal import Decimal
import json
import re
import subprocess
import time

HEAVY = ('applied-devbox-kube-proxy-reconcile', 'applied-devbox-azure-session', 'applied-devbox-teleport-reconcile')
MAX_WAIT_SECONDS = 1200


def span_us(text):
    factors = {'w': 604800000000, 'd': 86400000000, 'h': 3600000000, 'min': 60000000, 's': 1000000, 'ms': 1000, 'us': 1}
    parts = re.findall(r'([0-9]+(?:\.[0-9]+)?)(min|ms|us|w|d|h|s)', text)
    assert parts and ''.join(number + unit for number, unit in parts) == ''.join(text.split())
    value = sum(Decimal(number) * factors[unit] for number, unit in parts)
    assert value == int(value)
    return int(value)


def parse_properties(text, properties):
    pairs = [line.split('=', 1) for line in text.splitlines()]
    assert all(len(row) == 2 for row in pairs)
    assert {key for key, _ in pairs} == set(properties)
    result = {}
    for key in properties:
        values = [value for name, value in pairs if name == key]
        if key == 'TimersMonotonic':
            assert values
            result[key] = values
        else:
            assert len(values) == 1, key
            result[key] = values[0]
    return result


def observe():
    rows = {}
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TZ': 'UTC'}
    for name in HEAVY:
        rows[name] = {}
        for suffix, properties in [('timer', ['Id', 'LoadState', 'TimersMonotonic', 'ActiveState', 'NextElapseUSecMonotonic', 'LastTriggerUSecMonotonic']), ('service', ['Id', 'LoadState', 'ActiveState', 'SubState', 'CPUUsageNSec', 'ExecMainStartTimestampMonotonic', 'ExecMainExitTimestampMonotonic', 'ExecMainStatus'])]:
            command = ['/usr/bin/systemctl', 'show', name + '.' + suffix, *['--property=' + key for key in properties]]
            result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env, timeout=20)
            assert result.returncode == 0 and not result.stderr
            rows[name][suffix] = parse_properties(result.stdout, properties)
    return {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'monotonic_us': time.monotonic_ns() // 1000, 'services': rows}


def ready(row, margin_seconds):
    assert isinstance(margin_seconds, int) and margin_seconds > 0
    assert set(row['services']) == set(HEAVY)
    for name, data in row['services'].items():
        timer, service = data['timer'], data['service']
        assert timer['Id'] == name + '.timer' and service['Id'] == name + '.service'
        assert timer['LoadState'] == service['LoadState'] == 'loaded'
        if timer['ActiveState'] != 'active':
            return False
        if service['ActiveState'] != 'inactive' or service['SubState'] != 'dead':
            return False
        if timer['NextElapseUSecMonotonic'] in ('', '-', 'n/a', 'infinity', '0', '0us', '18446744073709551615', '18446744073709551615us'):
            return False
        if span_us(timer['NextElapseUSecMonotonic']) - row['monotonic_us'] < margin_seconds * 1000000:
            return False
    return True


def wait_for_pair(path, margin_seconds):
    begin = time.monotonic()
    with path.open('x') as stream:
        while True:
            row = observe()
            row['ready'] = ready(row, margin_seconds)
            row['wait_elapsed_seconds'] = time.monotonic() - begin
            stream.write(json.dumps(row, sort_keys=True) + '\n')
            stream.flush()
            assert row['wait_elapsed_seconds'] <= MAX_WAIT_SECONDS, 'no prospective maintenance window'
            if row['ready']:
                return row
            time.sleep(5)
