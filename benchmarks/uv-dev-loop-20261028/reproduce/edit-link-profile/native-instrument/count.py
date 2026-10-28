#!/usr/bin/env python3
"""Count the invoked x86-64 Linux process across its threads with DynamoRIO 11.3.0."""

import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parents[2] / "dynamorio"
DRRUN = HERE / "DynamoRIO-Linux-11.3.0-1/bin64/drrun"
# Release-pinned offline_entry_t and trace_marker_type_t, trace_entry.h.
PAYLOAD_48 = (1 << 48) - 1
PAYLOAD_61 = (1 << 61) - 1
HEADER_V8 = 0xC408
COUNT_MARKER = 0xC20B
SPLIT_MARKER = 0xC208
FOOTER = 0xC100000000000000


def thread_count(path, pid):
    records = [item[0] for item in struct.iter_unpack("<Q", path.read_bytes())]
    if (len(records) < 5 or records[0] >> 48 != HEADER_V8
            or records[1] >> 61 != 2 or records[2] >> 61 != 3
            or records[2] & PAYLOAD_61 != pid or records[-1] != FOOTER
            or records[-2] >> 48 != COUNT_MARKER):
        raise ValueError(f"unexpected thread trace {path.name}")
    count = records[-2] & PAYLOAD_48
    if records[-3] >> 48 == SPLIT_MARKER:
        count |= (records[-3] & PAYLOAD_48) << 32
    return records[1] & PAYLOAD_61, count


def main(argv):
    if argv[:1] == ["--"]:
        argv = argv[1:]
    if not argv:
        sys.exit("usage: count.py -- EXECUTABLE [ARG ...]")
    with tempfile.TemporaryDirectory(prefix="ohm-dr-") as tmp:
        env = dict(os.environ, DYNAMORIO_CONFIGDIR=tmp)
        cmd = [str(DRRUN), "-no_follow_children", "-t", "drcachesim", "-offline",
               "-raw_compress", "none", "-outdir", tmp, "-L0I_filter", "-L0I_size", "0",
               "-L0D_filter", "-L0D_size", "0", "--", *argv]
        proc = subprocess.Popen(cmd, env=env, close_fds=False)
        if (rc := proc.wait()):
            return rc if rc > 0 else 128 - rc
        # drrun and the offline launcher exec in place on Linux. A child that
        # forks can open its own trace even when following exec is disabled.
        # Read the original process directory only.
        roots = list(Path(tmp).glob(f"drmemtrace.*.{proc.pid:05d}.*.dir/raw"))
        if len(roots) != 1:
            raise ValueError(f"expected one trace directory for pid {proc.pid}, got {roots}")
        counts = {}
        for path in sorted(roots[0].glob("*.raw")):
            tid, value = thread_count(path, proc.pid)
            if tid in counts:
                raise ValueError(f"duplicate trace for tid {tid}")
            counts[tid] = value
        if proc.pid not in counts:
            raise ValueError(f"missing main thread {proc.pid}")
        result = {"pid": proc.pid, "threads": counts, "instructions": sum(counts.values())}
        print("DynamoRIO " + json.dumps(result, separators=(",", ":")), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
