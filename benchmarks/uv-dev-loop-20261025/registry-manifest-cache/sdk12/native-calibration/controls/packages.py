"""Read-only package-manager/lock observation; no service changes."""
import os
from pathlib import Path
import subprocess

NAMES = ('apt-daily', 'apt-daily-upgrade')
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TZ': 'UTC'}


def observe():
    services = {}
    for name in NAMES:
        properties = ('Id', 'LoadState', 'ActiveState', 'SubState', 'Result', 'ExecMainStartTimestampMonotonic', 'ExecMainStatus')
        result = subprocess.run(['/usr/bin/systemctl', 'show', name + '.service', '--no-pager',
                                 *['--property=' + key for key in properties]],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, env=ENV, timeout=20)
        assert result.returncode == 0 and not result.stderr
        values = dict(line.split('=', 1) for line in result.stdout.splitlines())
        assert set(values) == set(properties) and values['Id'] == name + '.service' and values['LoadState'] == 'loaded'
        services[name] = values
    processes, idle_shutdown_waiters = [], []
    expected_waiter = ['/usr/bin/python3', '/usr/share/unattended-upgrades/unattended-upgrade-shutdown', '--wait-for-signal']
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            text = path.read_text(); end = text.rindex(')')
            name, state = text[text.index('(') + 1:end], text[end + 2:].split()[0]
            if state == 'Z' or not name.startswith(('apt', 'apt-get', 'dpkg', 'unattended-upgr')):
                continue
            argv = [os.fsdecode(value) for value in path.with_name('cmdline').read_bytes().split(b'\0') if value]
            row = {'pid': int(path.parent.name), 'name': name, 'state': state, 'argv': argv}
            if state == 'S' and argv == expected_waiter:
                idle_shutdown_waiters.append(row)
            else:
                processes.append(row)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    locks = []
    lock_lines = Path('/proc/locks').read_text().splitlines()
    for filename in ('/var/lib/dpkg/lock', '/var/lib/dpkg/lock-frontend', '/var/lib/apt/lists/lock', '/var/cache/apt/archives/lock'):
        path = Path(filename)
        if not path.exists():
            continue
        info = path.stat()
        for line in lock_lines:
            for token in line.split():
                parts = token.split(':')
                if len(parts) == 3:
                    try:
                        actual = int(parts[0], 16), int(parts[1], 16), int(parts[2])
                    except ValueError:
                        continue
                    if actual == (os.major(info.st_dev), os.minor(info.st_dev), info.st_ino):
                        locks.append({'path': filename, 'record': line})
    return {'services': services, 'active_processes': processes, 'locks': locks,
            'idle_shutdown_waiters': idle_shutdown_waiters}


def quiet(row):
    return not row['active_processes'] and not row['locks'] and all(
        value['ActiveState'] == 'inactive' and value['SubState'] == 'dead'
        and value['Result'] == 'success' and value['ExecMainStatus'] == '0'
        for value in row['services'].values())
