#!/usr/bin/env python3
"""Apply component PGO to Cargo target crates while leaving the in-tree std profile alone."""
import json
import os
from pathlib import Path
import sys

rustc, *args = sys.argv[1:]
if "--crate-name" in args and any(
    arg == "--emit" or arg.startswith("--emit=") for arg in args
):
    crate = args[args.index("--crate-name") + 1]
    target = args[args.index("--target") + 1] if "--target" in args else None
    # Cargo attaches these synthetic std edges to every non-host target crate
    # *before* adding the separate std unit graph. See unit_dependencies.rs:240.
    component = target == "x86_64-unknown-linux-gnu" and any(
        a.startswith("noprelude,nounused:std=") for a in args
    )
    phase = os.environ["OHM_HOLDOUT_PHASE"]
    if component:
        root = Path(os.environ["OHM_HOLDOUT_ROOT"])
        depth = len((root / "cargo-src").parts)
        args.append("-Cllvm-args=-static-func-strip-dirname-prefix=" + str(depth))
        if phase == "generate":
            args.extend(
                [
                    "-Cprofile-generate=" + str(root / "raw"),
                    "-Cllvm-args=-vp-counters-per-site=4",
                ]
            )
            # The release splits metadata from the rlib. Cargo passes both
            # artifacts for linkable extern crates under -Zembed-metadata=no.
            runtime = Path(os.environ["OHM_HOLDOUT_PROFILER"])
            for artifact in (runtime, runtime.with_suffix(".rmeta")):
                assert artifact.is_file(), artifact
                args.extend(
                    ["--extern", f"noprelude,nounused:profiler_builtins={artifact}"]
                )
        elif phase == "use":
            args.append("-Cprofile-use=" + str(root / "merged.profdata"))
        else:
            raise ValueError(phase)
    fd = os.open(
        os.environ["OHM_HOLDOUT_TRACE"], os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600
    )
    os.write(fd, (json.dumps([crate, target, component, phase]) + "\n").encode())
    os.close(fd)
os.execv(rustc, [rustc, *args])
