"""Record machine load alongside native timings without sampling the timed processes."""
import csv
from datetime import datetime, timezone
from pathlib import Path
import sys
import time


def counters():
    rows = Path("/proc/stat").read_text().splitlines()
    fields = [list(map(int, row.split()[1:9])) for row in rows if row.split()[0] in CPUS]
    return [sum(column) for column in zip(*fields)]


CPUS = {f"cpu{i}" for i in range(16)}
with Path(sys.argv[1]).open("x", buffering=1) as out:
    writer = csv.writer(out)
    writer.writerow(("utc", "cpu0_15_busy_fraction", "cpu0_15_iowait_fraction", "dirty_kib", "writeback_kib"))
    previous = counters()
    quiet_streak = 0
    while True:
        time.sleep(3)
        current = counters()
        delta = [after - before for after, before in zip(current, previous)]
        previous = current
        ticks = sum(delta)
        memory = dict(line.split()[:2] for line in Path("/proc/meminfo").read_text().splitlines())
        busy, waiting = (ticks - delta[3] - delta[4]) / ticks, delta[4] / ticks
        writer.writerow((datetime.now(timezone.utc).isoformat(), busy, waiting, memory["Dirty:"], memory["Writeback:"]))
        if sys.argv[2:] == ["--until-quiet"]:
            quiet = busy < 0.05 and waiting < 0.02 and int(memory['Dirty:']) < 65536 and int(memory['Writeback:']) < 8192
            quiet_streak = quiet_streak + 1 if quiet else 0
            if quiet_streak == 2:
                break
