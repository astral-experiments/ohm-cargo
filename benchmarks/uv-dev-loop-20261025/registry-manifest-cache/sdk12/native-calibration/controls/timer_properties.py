"""Passive maintenance-window admission, only before entry and complete pairs."""
from pathlib import Path
import datetime
import json
import os
import subprocess
import time

SERVICES = (
    'maintenance-reconcile-1.service',
    'applied-devbox-azure-token.service',
    'maintenance-reconcile-2.service',
)
TIMERS = {name.removesuffix('.service') + '.timer': name for name in SERVICES}


def command(arguments):
    result = subprocess.run(
        ['/usr/bin/systemctl'] + arguments, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True,
        timeout=10, env=dict(os.environ, LC_ALL='C', TZ='UTC'),
    )
    return result.stdout


def timer_properties(timer, service):
    object_path = '/org/freedesktop/systemd1/unit/' + ''.join(
        char if char.isalnum() else '_' + format(ord(char), '02x') for char in timer)

    def get(interface, names, signatures):
        result = subprocess.run(
            ['/usr/bin/busctl', '--json=short', 'get-property', 'org.freedesktop.systemd1',
             object_path, 'org.freedesktop.systemd1.' + interface] + names,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=True, timeout=10,
        )
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        assert len(rows) == len(signatures)
        assert all(set(row) == {'type', 'data'} and row['type'] == signature
                   for row, signature in zip(rows, signatures))
        return [row['data'] for row in rows]

    identity, = get('Unit', ['Id'], ['s'])
    assert identity == timer
    activates, wake, realtime, monotonic = get(
        'Timer', ['Unit', 'WakeSystem', 'NextElapseUSecRealtime', 'NextElapseUSecMonotonic'],
        ['s', 'b', 't', 't'])
    assert activates == service and wake is False
    assert all(type(value) is int and 0 <= value <= (1 << 64) - 1
               for value in (realtime, monotonic))
    return {'id': identity, 'activates': activates, 'wake_system': wake,
            'next_realtime_usec': realtime, 'next_monotonic_usec': monotonic}


def remaining_seconds(timer, clocks):
    deadlines = [(timer['next_' + name + '_usec'] * 1000 - clocks[name]) / 1_000_000_000
                 for name in ('realtime', 'monotonic')
                 if timer['next_' + name + '_usec'] not in (0, (1 << 64) - 1)]
    return min(deadlines) if deadlines else None


def observe():
    timers = {timer: timer_properties(timer, service) for timer, service in TIMERS.items()}
    assert {row['id'] for row in timers.values()} == set(TIMERS)
    services = {}
    # Read service states after deadlines, closing the start-between-reads case.
    for name in SERVICES:
        rows = dict(line.split('=', 1) for line in command([
            'show', name, '--property=Id,ActiveState,SubState,ExecMainStatus',
        ]).splitlines())
        assert set(rows) == {'Id', 'ActiveState', 'SubState', 'ExecMainStatus'}
        assert rows['Id'] == name
        assert rows['ActiveState'] in {'inactive', 'active', 'activating', 'deactivating', 'reloading'}
        if rows['ActiveState'] == 'inactive':
            assert rows['ExecMainStatus'] == '0'
        services[name] = rows
    clocks = {'realtime': time.time_ns(), 'monotonic': time.monotonic_ns()}
    remaining = {name: remaining_seconds(row, clocks) for name, row in timers.items()}
    for name, row in timers.items():
        row['deadline_state'] = 'unavailable' if remaining[name] is None else 'available'
    active = any(row['ActiveState'] != 'inactive' for row in services.values())
    missing = any(value is None for value in remaining.values())
    ready = not active and not missing and min(remaining.values()) >= 120
    reason = ('service-active' if active else 'timer-deadline-unavailable' if missing
              else 'window-ready' if ready else 'waiting-for-window')
    return {'services': services, 'timers': timers, 'clock_ns': clocks,
            'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'remaining_seconds': remaining, 'ready': ready, 'reason': reason}


def wait(policy, path):
    assert policy['kind'] == 'prospective-complete-pair-maintenance-window'
    assert policy['services'] == list(SERVICES)
    assert policy['minimum_remaining_seconds'] == 120 and policy['poll_seconds'] == 5
    with Path(path).open('x') as stream:
        while True:
            row = observe()
            stream.write(json.dumps(row, sort_keys=True) + '\n')
            stream.flush()
            if row['ready']:
                return
            time.sleep(5)
