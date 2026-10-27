"""Randomize complete workspaces with independent mutable directories and frozen Ohm driver files."""
import argparse
from contextlib import contextmanager
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys

P = Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027")
RUFF = Path("/home/dev-user/code/oss/ruff-ohm-whole-native-20261027")
PIN = "93526150df078af7dd8fc4226cdcc469539d2001"
PATCH_SHA = "08bb20f14fde4db57dd12ec3de3855021ddf6284b4a1957b54f4d06fb3c8f9ff"
PARENT_SHA = "051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518"
CARGO_SHA = "13396fe1c6886f41155ac24f507210c7a5f655e5b3279a28f45bf3a5e6bcaf08"
FROZEN = P / "frozen-toolchain"
HERE = Path(__file__).resolve().parent


def sha(path):
    with path.open("rb") as src:
        return hashlib.file_digest(src, "sha256").hexdigest()


def git(*args):
    return subprocess.check_output(["git", "--no-optional-locks", "-C", RUFF, *args], text=True).strip()


def write(path, data):
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")


@contextmanager
def edit(patch, files, index, index_sha):
    assert not git("status", "--porcelain") and sha(index) == index_sha
    git("apply", "--reverse", "--check", patch)
    git("apply", "--reverse", "--whitespace=nowarn", patch)
    try:
        yield
    finally:
        for name, (content, st) in files.items():
            path = RUFF / name
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_bytes(content)
            path.chmod(st.st_mode & 0o777)
            os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
        assert not git("status", "--porcelain") and sha(index) == index_sha


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("name")
    cli.add_argument("candidate", type=Path)
    cli.add_argument("expected_driver")
    args = cli.parse_args()
    assert re.fullmatch(r"revision-[a-z0-9-]+", args.name) and re.fullmatch(r"[0-9a-f]{64}", args.expected_driver)
    candidate = args.candidate.resolve()
    assert sha(candidate) == args.expected_driver != PARENT_SHA
    parent = FROZEN / ".bench-components" / ("driver-" + PARENT_SHA)
    assert sha(parent) == PARENT_SHA and sha(P / "subjects/parent") == CARGO_SHA
    patch = P / "parser-assets/patches/parser-tstring.patch"
    assert sha(patch) == PATCH_SHA and git("rev-parse", "HEAD") == PIN
    with (P / "native-measure.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        assert not git("status", "--porcelain")
        index = Path(git("rev-parse", "--path-format=absolute", "--git-path", "index"))
        index_sha = sha(index)
        names = [row.split("\t", 2)[2] for row in git("apply", "--numstat", patch).splitlines()]
        assert all(n.startswith("crates/") and ".." not in Path(n).parts for n in names)
        files = {n: ((RUFF/n).read_bytes(), (RUFF/n).stat()) for n in names}
        cold = P / "reference-parser-v3"
        assert json.loads((cold / "complete.json").read_bytes())["source_clean"]
        parent_target, parent_shared = cold / "parent-cold-target", cold / "parent-cold-shared"
        assert parent_target.is_dir() and parent_shared.is_dir()
        state = P / (args.name + "-private-state")
        state.mkdir()
        candidate_target, candidate_shared = state / "target-candidate", state / "shared-candidate"
        candidate_target.mkdir()
        candidate_shared.mkdir()
        subjects = dict(parent=(parent, PARENT_SHA, parent_target, parent_shared),
                        candidate=(candidate, args.expected_driver, candidate_target, candidate_shared))
        for mode, seed in (("build", 1953201), ("test", 1953202)):
            out = P / ("results-" + args.name + "-" + mode)
            out.mkdir()
            orders = [["parent", "candidate"] for _ in range(6)] + [["candidate", "parent"] for _ in range(6)]
            random.Random(seed).shuffle(orders)
            write(out / "plan.json", dict(mode=mode, command=["cargo", "+ohm", mode, *(["--no-run"] if mode == "test" else []), "--locked", "--offline"],
                    pin=PIN, edit_sha=PATCH_SHA, seed=seed, planned_pairs=len(orders), orders=orders,
                    subjects={"cargo": {"parent": CARGO_SHA, "candidate": CARGO_SHA},
                              "driver": {arm: s[1] for arm,s in subjects.items()}}))
            def call(arm, edited, *actions):
                binary,digest,target,shared = subjects[arm]
                assert shutil.disk_usage(P).free > 14 * 1024**3, "dedicated scratch headroom"
                run = ["bwrap", "--ro-bind", "/", "/", "--proc", "/proc", "--dev-bind", "/dev", "/dev",
                       "--bind", "/tmp", "/tmp", "--bind", str(out), str(out),
                       "--bind", str(P/"registry-home"), str(P/"registry-home"), "--bind", str(P/"rustup"), str(P/"rustup"),
                       "--bind", str(target), str(P/"native-target"), "--bind", str(shared), str(P/"shared"),
                       "--ro-bind", str(P/"subjects/parent"), str(FROZEN/"bin/cargo"),
                       "--ro-bind", str(binary), str(FROZEN/"lib/librustc_driver-774a793a844d5500.so"), "--",
                       "taskset", "-c", "0-23", sys.executable, str(HERE/"revision-worker.py"), str(out), arm, digest, mode,
                       "edited" if edited else "original", *actions]
                subprocess.run(run, check=True)
            for arm in subjects:
                call(arm, False, "settle=normal", "before=reference")
                with edit(patch, files, index, index_sha):
                    call(arm, True, "verify-edit=trace", "after-edit-fresh=fresh")
                call(arm, False, "restore-discovery=normal", "restore-discovery-fresh=fresh")
            with (out/"observations.csv").open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["pair", "order", "arm", "elapsed_ns"])
                for i, order in enumerate(orders, 1):
                    for arm in order:
                        with edit(patch, files, index, index_sha):
                            call(arm, True, f"pair-{i:02}=normal", f"pair-{i:02}-edit-fresh=fresh")
                        call(arm, False, f"restore-{i:02}=normal", f"restore-{i:02}-fresh=fresh")
                        elapsed = json.loads((out/f"{arm}-pair-{i:02}"/"receipt.json").read_bytes())["ns"]
                        writer.writerow([i, "/".join(order), arm, elapsed])
                        f.flush()
                    print(mode, i, "/".join(order), flush=True)
            for arm in subjects:
                with edit(patch, files, index, index_sha):
                    call(arm, True, "verify-final-edit=trace", "final-edit-fresh=fresh")
                call(arm, False, "final-restore=normal", "final-fresh=reference")
            assert not git("status", "--porcelain") and sha(index) == index_sha
            write(out/"complete.json", dict(source_clean=True, index_sha256=index_sha, pin=PIN))


if __name__ == "__main__":
    main()
