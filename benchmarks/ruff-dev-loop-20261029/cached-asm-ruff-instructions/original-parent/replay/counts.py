"""Reconcile Callgrind's process summary, its log, and every self-cost row."""
import gzip
import re

def actual_ir(directory):
    native_log, = directory.glob("valgrind.*.gz")
    reported, = re.findall(rb"^==\d+== Collected\s+:\s+([\d,]+)\s*$",
                           gzip.decompress(native_log.read_bytes()), re.M)
    expected = int(reported.replace(b",", b""))
    totals, events, cost, edge = [], [], 0, False
    with gzip.open(directory / "full-rustc.callgrind.gz", "rb") as file:
        for line in file:
            if line.startswith(b"events: "):
                events.append(line.split()[1:])
            elif line.startswith(b"totals: "):
                totals.append(int(line.split()[1]))
            elif line.startswith(b"calls="):
                if edge:
                    raise ValueError("unfinished call edge")
                edge = True
            elif line[:1] in b"0123456789+-*" and line.strip():
                if edge:
                    edge = False
                else:
                    cost += int(line.split()[-1])
    if edge or events != [[b"Ir"]] or totals != [expected] or cost != expected or expected <= 0:
        raise ValueError("inconsistent or empty complete compiler profile")
    return expected
