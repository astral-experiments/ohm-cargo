#!/usr/bin/env python3
"""Measure one ordinary Cargo command, then retain its complete standard streams."""
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

CARGO = ["cargo", "+ohm", "build", "-p", "ruff", "--bin", "ruff",
         "--locked", "--offline", "-j4", "--message-format=json"]

def ordinary_cargo(source, env, temporary_directory, receipt_directory):
    source = Path(source)
    temporary_directory = Path(temporary_directory)
    receipt_directory = Path(receipt_directory)
    if source.stat().st_dev != temporary_directory.stat().st_dev:
        raise ValueError("temporary command output must use the source workspace filesystem")
    if temporary_directory.stat().st_dev == receipt_directory.stat().st_dev:
        raise ValueError("receipts must be on their separate enrolled filesystem")
    files = []
    with tempfile.TemporaryFile(dir=temporary_directory) as stdout, tempfile.TemporaryFile(dir=temporary_directory) as stderr:
        for stream in (stdout, stderr):
            if not (stat.S_ISREG(os.fstat(stream.fileno()).st_mode) and stream.seekable() and not stream.isatty()):
                raise ValueError("Cargo standard streams must be ordinary empty seekable files")
        started = time.monotonic_ns()
        proc = subprocess.Popen(CARGO, cwd=source, env=env, stdout=stdout, stderr=stderr)
        pid, status, usage = os.wait4(proc.pid, 0)
        ended = time.monotonic_ns()
        proc.returncode = os.waitstatus_to_exitcode(status)
        if pid != proc.pid:
            raise ValueError("wait4 did not return the measured Cargo process")
        for name, stream in (("stdout", stdout), ("stderr", stderr)):
            stream.seek(0)
            path = receipt_directory / ("cargo." + name)
            with path.open("xb") as target:
                shutil.copyfileobj(stream, target, 2**20)
            if path.stat().st_size != os.fstat(stream.fileno()).st_size:
                raise ValueError("incomplete raw Cargo stream")
            with path.open("rb") as fd:
                files.append(dict(stream=name, size=path.stat().st_size,
                                  sha256=hashlib.file_digest(fd, "sha256").hexdigest()))
    result = dict(argv=CARGO, exit=proc.returncode, wall_ns=ended-started, user_cpu_us=round(usage.ru_utime*1_000_000),
                  system_cpu_us=round(usage.ru_stime*1_000_000), stdout_and_stderr=files,
                  blocking_wait="wait4", input_setting=env.get("CARGO_ENCODED_RUSTFLAGS"))
    path = receipt_directory / "cargo.process.json"
    with path.open("x") as out:
        json.dump(result,out,sort_keys=True,indent=2)
        out.write("\n")
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, CARGO)
    return result
