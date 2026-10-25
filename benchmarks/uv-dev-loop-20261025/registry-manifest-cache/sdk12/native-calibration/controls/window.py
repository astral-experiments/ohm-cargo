"""K's fixed service checks plus the actual calendar deadlines of both apt timers."""
import datetime
import json
import time
import activity
import maintenance
import packages
import timer_properties
from common import save


def observe():
    row = maintenance.observe()
    row['apt_timers'] = {name: timer_properties.timer_properties(name + '.timer', name + '.service')
                         for name in packages.NAMES}
    row['packages'] = packages.observe()
    row['clock_ns'] = {'realtime': time.time_ns(), 'monotonic': time.monotonic_ns()}
    return row


def ready(row, margin):
    if not maintenance.ready(row, margin):
        return False
    remaining = [timer_properties.remaining_seconds(timer, row['clock_ns'])
                 for timer in row['apt_timers'].values()]
    return all(value is not None and value >= margin for value in remaining)


def admit(log, margin):
    start = time.monotonic()
    with (log / 'window-observations.jsonl').open('x') as stream:
        attempt = 0
        while True:
            row = observe()
            row['ready'] = ready(row, margin)
            row['wait_elapsed_seconds'] = time.monotonic() - start
            stream.write(json.dumps(row, sort_keys=True) + '\n'); stream.flush()
            assert row['wait_elapsed_seconds'] <= maintenance.MAX_WAIT_SECONDS
            if row['ready']:
                samples = [activity.host_sample()]
                for _ in range(3):
                    time.sleep(1); samples.append(activity.host_sample())
                save(log / ('quiet-%03d.json' % attempt), samples)
                okay = True
                for a, b in zip(samples, samples[1:]):
                    assert len(a['cpu']) == len(b['cpu']) == 8
                    assert a['host'] == b['host'] == activity.PROTOCOL['host']
                    total = sum(b['cpu'][key][0] - a['cpu'][key][0] for key in a['cpu'])
                    idle = sum(b['cpu'][key][1] - a['cpu'][key][1] for key in a['cpu'])
                    assert total > 0 and 0 <= idle <= total
                    okay &= not a['competing_jobs'] and not b['competing_jobs'] and (total-idle)/total <= .10
                if okay:
                    strict = activity.sample()
                    save(log / ('strict-admission-%03d.json' % attempt), strict)
                    after = observe()
                    if not strict['other_workloads'] and ready(after, margin):
                        save(log / 'window-entry.json', after)
                        return after
            attempt += 1
            time.sleep(5)


def finish(entry, start, budget, destination):
    end = maintenance.finish(entry, start, budget, destination)
    now = {'realtime': time.time_ns(), 'monotonic': time.monotonic_ns()}
    save(destination.with_suffix('.apt.json'), {'clock_ns': now, 'apt_timers': entry['apt_timers']})
    for timer in entry['apt_timers'].values():
        remaining = timer_properties.remaining_seconds(timer, now)
        assert remaining is not None and remaining > 0
    return end
