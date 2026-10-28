#!/usr/bin/env python3
"""Instrument one Cargo, rustc or Wild PID. Keep the program's stdout, stderr and jobserver."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import sys


def main():
    env = os.environ
    args = sys.argv[1:]
    name = Path(sys.argv[0]).name
    if name == "cc":
        old, new = env["OHM_RELEASE_WILD_DIR"], env["OHM_WRAPPED_WILD_DIR"]
        args = [new if a == old else "-B" + new if a == "-B" + old else a for a in args]
        os.execv("/usr/bin/cc", ["/usr/bin/cc", *args])
    if name == "ld.bfd":
        if "--fork" in args or "-o" not in args:
            raise RuntimeError(f"unexpected Wild invocation: {args}")
        role, tool, key = "wild", env["OHM_ACTUAL_WILD"], args[args.index("-o") + 1]
        args = ["--no-fork", *args]
    elif name == "rustc-wrapper":
        tool, *args = args
        if Path(tool).resolve() != Path(env["RUSTC"]).resolve():
            raise RuntimeError(f"unexpected compiler: {tool}")
        role, key = "rustc", args  # Exact argv, including every probe and crate type.
    else:
        role, tool, *args = args  # Explicitly selected Cargo or a calibration role.
        key = args

    record = {"role": role, "executable": tool, "argv": args, "key": key}
    log = Path(env["OHM_ROLE_LOG"]) / f"{role}-{os.getpid()}.json"
    if env["OHM_ROLE_MODE"] == "native":
        log.write_text(json.dumps(record) + "\n")
        os.execv(tool, [tool, *args])

    # redirect_stderr captures the Python counter's JSON. The measured program inherits
    # the original OS-level stderr, including rustc's machine-readable diagnostics.
    marker = io.StringIO()
    counter = runpy.run_path(env["OHM_SINGLE_COUNTER"])["main"]
    with contextlib.redirect_stderr(marker):
        rc = counter([tool, *args])
    if rc:
        return rc
    lines = marker.getvalue().strip().splitlines()
    if len(lines) != 1 or not lines[0].startswith("DynamoRIO "):
        raise RuntimeError(f"missing single-process counter for {role}: {lines}")
    record.update(json.loads(lines[0].removeprefix("DynamoRIO ")))
    log.write_text(json.dumps(record) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
