"""Compare two counter implementations on the fixture's known assembly loop."""

import csv
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time


HERE = Path(__file__).resolve().parent
VALGRIND = Path(os.environ.get("OHM_VALGRIND", HERE.parent / "profiler/usr/bin/valgrind"))
VG_LIB = HERE.parent / "profiler/usr/libexec/valgrind"
FIXTURE = str(HERE / "fixture")
LOW, HIGH = 100000, 900000


def measure(tool, app):
    if tool == "dr":
        cmd = ["python3", "-B", str(HERE / "count.py"), "--", *app]
    else:
        cmd = [str(VALGRIND), "--tool=cachegrind", "--trace-children=no",
               "--cachegrind-out-file=/dev/null", *app]
    start = time.perf_counter()
    env = os.environ.copy()
    if VG_LIB.is_dir():
        env.setdefault("VALGRIND_LIB", str(VG_LIB))
    with subprocess.Popen(cmd, env=env,
                          stderr=subprocess.PIPE, text=True) as proc:
        _, log = proc.communicate()
    elapsed = time.perf_counter() - start
    if proc.returncode:
        raise ValueError(log)
    if tool == "cg":
        match = re.findall(rf"^=={proc.pid}== I refs:\s+([\d,]+)$", log, re.M)
        if len(match) != 1:
            raise ValueError(log)
        return int(match[0].replace(",", "")), "", elapsed
    result = json.loads(re.search(r"^DynamoRIO (.+)$", log, re.M)[1])
    worker_counts = dict(result["threads"])
    del worker_counts[str(result["pid"])]
    return result["instructions"], json.dumps(sorted(worker_counts.values())), elapsed


output = Path(os.environ.get("OHM_CALIBRATION_CSV", HERE / "calibration.csv"))
with output.open("w", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow(["tool", "mode", "workers", "iterations", "rep", "instructions",
                     "worker_counts", "fixture_seconds"])
    for tool in ("dr", "cg"):
        count, details, elapsed = measure(tool, ["/bin/true"])
        writer.writerow([tool, "true", 0, "", 0, count, details, elapsed])
        print(f"{tool} true {count}", flush=True)
    for mode, workers in (("spin", 1), ("spin", 4), ("exec", 4)):
        for tool in ("dr", "cg"):
            deltas = []
            for rep in range(4):
                counts = {}
                for n in ((LOW, HIGH) if rep % 2 == 0 else (HIGH, LOW)):
                    count, details, elapsed = measure(tool, [FIXTURE, str(n), str(workers), mode])
                    writer.writerow([tool, mode, workers, n, rep, count, details, elapsed])
                    stream.flush()
                    if tool == "dr":
                        per_thread = json.loads(details)
                        assert len(per_thread) == (workers if mode == "spin" else 0)
                        assert all(2 * n <= x <= 2 * n + 10000 for x in per_thread)
                    counts[n] = count
                deltas.append(counts[HIGH] - counts[LOW])
            expected = (HIGH - LOW) * 2 * workers if mode == "spin" else 0
            if abs(statistics.median(deltas) - expected) > 5000:
                raise ValueError(f"wrong instruction delta for {tool}: {deltas}")
            print(tool, mode, workers, "expected", expected, "observed", deltas, flush=True)
