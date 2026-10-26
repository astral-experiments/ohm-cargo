"""Prepare an isolated Ohm alias whose Cargo path is stable across both arms."""

import hashlib
import os
import shlex
import shutil
from pathlib import Path


def prepare(args, output):
    state = args.state.resolve() if args.state else output
    state.mkdir(parents=True, exist_ok=True)
    tool = state / "rustup/toolchains/ohm"
    cargo = state / "runtime/bin/cargo"
    wrapper = tool / "bin/cargo"
    if not wrapper.exists():
        (tool / "bin").mkdir(parents=True)
        shutil.copytree(args.toolchain / "lib", tool / "lib", symlinks=True)
        for entry in (args.toolchain / "bin").iterdir():
            if entry.name != "cargo":
                shutil.copy2(entry, tool / "bin" / entry.name)
        cargo.parent.mkdir(parents=True)
        wrapper.write_text(
            '#!/bin/sh\nexec valgrind --tool=callgrind --trace-children="$CG_CHILDREN" '
            '--log-file="$CG_OUT/log.%p" --callgrind-out-file="$CG_OUT/cg.%p" '
            + shlex.quote(str(cargo))
            + ' "$@"\n'
        )
        wrapper.chmod(0o755)
    assert str(cargo) in wrapper.read_text()
    stages = {}
    for arm in ("parent", "candidate"):
        subject = getattr(args, arm)
        digest = hashlib.sha256(subject.read_bytes()).hexdigest()
        stages[arm] = state / ("subject-" + digest)
        if not stages[arm].exists():
            shutil.copy2(subject, stages[arm])
        assert hashlib.sha256(stages[arm].read_bytes()).hexdigest() == digest
    return state, cargo, stages


def select(cargo, subject):
    if not cargo.exists() or not cargo.samefile(subject):
        temp = cargo.with_name("next")
        os.link(subject, temp)
        temp.replace(cargo)
