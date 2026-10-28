#!/usr/bin/env python3
"""Check nested counting, known work per role, thread aggregation, fork isolation and fd inheritance."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
COUNTER = HERE.parent / "edit-link-profile/native-instrument/count.py"
WRAP = HERE / "wrap.py"


def main():
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        exe = str(Path(tmp) / "fixture")
        subprocess.run(["cc", "-O2", "-pthread", str(HERE / "calibrate.c"), "-o", exe], check=True)
        rfd, wfd = os.pipe()
        try:
            tests = [("native", 100000, 100000), ("count-low", 100000, 100000),
                     ("count-high", 900000, 100000), ("count-outside", 100000, 900000)]
            values = {}
            for name, n, outside in tests:
                log = out / name
                log.mkdir()
                env = dict(os.environ, OHM_ROLE_MODE="native" if name == "native" else "count",
                           OHM_ROLE_LOG=str(log), OHM_SINGLE_COUNTER=str(COUNTER),
                           OHM_CAL_WRAPPER=str(WRAP), OHM_CAL_FD=str(rfd))
                subprocess.run([str(WRAP), "cargo", exe, "cargo", str(n), str(outside)],
                               env=env, check=True, pass_fds=(rfd,))
                records = [json.loads(p.read_text()) for p in log.glob("*.json")]
                if sorted(r["role"] for r in records) != ["cargo", "rustc", "wild"]:
                    raise ValueError(f"missing calibration process: {records}")
                if name == "native":
                    continue
                values[name] = {r["role"]: r["instructions"] for r in records}
                if {r["role"]: len(r["threads"]) for r in records} != {"cargo": 1, "rustc": 1, "wild": 2}:
                    raise ValueError(f"missing calibration thread: {records}")
            for role, loops in (("cargo", 1), ("rustc", 1), ("wild", 2)):
                delta = values["count-high"][role] - values["count-low"][role]
                outside = values["count-outside"][role] - values["count-low"][role]
                if abs(delta - loops * 1600000) > 4096 or abs(outside) > 4096:
                    raise ValueError(f"bad {role} delta: {delta}, pre-exec child: {outside}")
            (out / "PASS.json").write_text(json.dumps(values, indent=2) + "\n")
            print("Calibrated all three roles, four threads, descriptor inheritance, and pre-exec isolation.")
        finally:
            os.close(rfd)
            os.close(wfd)


if __name__ == "__main__":
    main()
