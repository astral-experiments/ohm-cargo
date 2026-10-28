#!/usr/bin/env python3
"""Independently replicate only endpoints qualifying in the completed first cohort."""
import argparse
import collections
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from edit_holdout import BEFORE, EDIT_PATH, REVISION
from measure import BENCH, COMMANDS, RUST, WORK, digest, report

COUNTER = WORK / "edit-link-profile/native-instrument/count.py"
WRAP = HERE / "wrap.py"

ORDERS = {"check": 9140093, "build": 9140113, "test": 9140127}
CELLS = [("native", "candidate"), ("count", "base"), ("native", "base"), ("count", "candidate")]
BINARIES = {
    "base": (WORK / "path-compare/build/bin/base", WORK / "bin/wild-baseline"),
    "candidate": (WORK / "path-compare/build/bin/guard-stack", WORK / "bin/wild-undefined"),
}


def audit_native(log, paths, records):
    ran = collections.Counter()
    for trace in log.glob("exec.*"):
        for line in trace.read_text().splitlines():
            if not re.search(r"= 0$", line):
                continue
            match = re.match(r'^execve\("([^"\\]+)",', line)
            if not match:
                raise ValueError(f"unresolved successful exec: {line[:200]}")
            ran[match[1]] += 1
    (log / "native-execs.json").write_text(json.dumps(ran, indent=2) + "\n")
    for role in ("cargo", "rustc", "wild"):
        if ran[str(paths[role])] != sum(r["role"] == role for r in records):
            raise ValueError(f"native {role} execs do not match wrapper roster: {ran}")
    allowed = {str(p) for p in paths.values()}
    for exe in ran:
        if Path(exe).name in {"cargo", "rustc", "wild", "wild-ld", "ld.bfd", "ld", "ld.lld", "rust-lld"} and exe not in allowed:
            raise ValueError(f"unwrapped compiler/cargo/linker in native run: {exe}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("pilot", "samples"))
    parser.add_argument("endpoint", choices=COMMANDS)
    args = parser.parse_args()
    ep = args.endpoint
    if not (HERE / "calibration/PASS.json").is_file():
        raise RuntimeError("calibrate nested independent counters first")
    # Read the other cohort only after all eight of its pairs are available.
    sys.path.insert(0, str(HERE / "replica"))
    from qualify import qualifies
    if not qualifies(HERE / "identical/results" / ep):
        raise RuntimeError(f"{ep} did not pass the first-cohort gate")
    prior = json.loads((WORK / f"edit-holdout-cumulative-wall-replica/{ep}/protocol.json").read_text())
    root = BENCH / f"edit-cumulative-wall-replica-{ep}"
    source, target = root / "source", root / "target"
    edit = source / EDIT_PATH
    original = subprocess.check_output(["git", "-C", str(WORK / "uv"), "show", f"{REVISION}:{EDIT_PATH}"])
    if (prior["uv"] != REVISION or Path(prior["source"]) != source or edit.read_bytes() != original
            or original.count(BEFORE.encode()) != 1 or os.path.lexists(target)):
        raise RuntimeError("retired fixture is not available/pristine")
    stat = edit.stat()
    tools = root / "role-sum-replica"
    out = HERE / "replica/results" / ep
    paths = dict(cargo=tools / "cargo", wild=tools / "wild", rustc=RUST / "rustc",
                 linker_wrapper=tools / "linker/ld.bfd")
    env = dict(os.environ, CARGO_HOME=prior["cargo_home"], CARGO_TARGET_DIR=str(target),
               RUSTC=str(paths["rustc"]), RUSTDOC=str(RUST / "rustdoc"), CARGO_NET_OFFLINE="true",
               PATH=f"{tools / 'bin'}:{RUST}:{os.environ['PATH']}", CARGO_TERM_COLOR="never",
               SSL_CERT_DIR="/etc/ssl/certs", RUSTC_WRAPPER=str(tools / "rustc-wrapper"),
               OHM_RELEASE_WILD_DIR=str(RUST.parent / "lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld"),
               OHM_WRAPPED_WILD_DIR=str(tools / "linker"), OHM_ACTUAL_WILD=str(paths["wild"]),
               OHM_SINGLE_COUNTER=str(COUNTER))
    arms = ("base", "candidate")
    orders = [arms, arms[::-1]] * 4
    random.Random(ORDERS[ep]).shuffle(orders)
    edits = list(range(20, 28))
    random.Random(ORDERS[ep] ^ 0x5245504c).shuffle(edits)
    protocol = dict(uv=REVISION, source=str(source), target=str(target), seed=ORDERS[ep], order=orders,
                    predecessor="R00", admission="R01 from four fresh R00 copies", cells=CELLS,
                    measured_edits=edits, pinned_cpus=sorted(os.sched_getaffinity(0)),
                    sha256={arm:[digest(p) for p in files] for arm,files in BINARIES.items()},
                    rustc_sha256=digest(paths["rustc"]), command=[*COMMANDS[ep], "--locked", "--offline", "-j8"],
                    expected="native strace + role argument rosters and actual uv compilation on every edit",
                    metric="sum of original Cargo, rustc, Wild process PID thread totals; Wild --no-fork in both modes")

    def select(arm):
        for role, path in zip(("cargo", "wild"), BINARIES[arm]):
            temp = paths[role].with_suffix(".next")
            os.link(path, temp)
            os.replace(temp, paths[role])
            temp.unlink(missing_ok=True)
            if not paths[role].samefile(path):
                raise RuntimeError(f"unexpected {role} binary")

    def run(arm, label, mode, *, warm=False):
        log = out / label
        log.mkdir()
        select(arm)
        argv = [str(WRAP), "cargo", str(paths["cargo"]), *protocol["command"]]
        if mode == "native" and not warm:
            argv = ["strace", "-ff", "-qq", "-s", "450", "-e", "trace=execve,execveat", "-o", str(log / "exec"), *argv]
        with (log / "cargo.log").open("x") as stream:
            result = subprocess.run(argv, cwd=source, env=dict(env, OHM_ROLE_MODE=mode, OHM_ROLE_LOG=str(log)),
                                    stdout=stream, stderr=subprocess.STDOUT)
        body = (log / "cargo.log").read_text(errors="replace")
        if result.returncode or not re.search(r"^\s*Finished ", body, re.M):
            raise RuntimeError(f"{label} failed: {body[-2000:]}")
        if re.search(r"^\s*(?:Running|Downloading|Updating) |^running \d+ tests?", body, re.M):
            raise ValueError(f"{label} ran a test or accessed the network")
        rebuilt = sorted(re.findall(r"^\s*(Checking|Compiling) (.+)$", body, re.M))
        if warm:
            return rebuilt
        if len(rebuilt) != 1 or not rebuilt[0][1].startswith("uv v"):
            raise ValueError(f"unexpected compilation in {label}: {rebuilt}")
        tests = sorted(re.findall(r"^\s*Executable (.+)$", body, re.M))
        if ep == "test" and not any(t.startswith("tests/it/") for t in tests):
            raise ValueError("missing integration-test artifacts")
        records = [json.loads(f.read_text()) for f in log.glob("*.json")]
        roles = collections.Counter(r["role"] for r in records)
        if roles["cargo"] != 1 or roles["rustc"] == 0 or (roles["wild"] == 0) != (ep == "check"):
            raise ValueError(f"unexpected {ep} role roster: {roles}")
        roster = dict(compiled=rebuilt, tests=tests, roles=sorted((r["role"], json.dumps(r["key"])) for r in records))
        if mode == "native":
            audit_native(log, paths, records)
        totals = {role:sum(r.get("instructions", 0) for r in records if r["role"] == role) for role in ("cargo", "rustc", "wild")}
        (log / "receipt.json").write_text(json.dumps(dict(roster=roster, totals=totals), indent=2) + "\n")
        return json.dumps(roster, sort_keys=True), totals

    def put(n):
        expr = ('{\n                component == cellar && (next == formula || next == OsStr::new('
                f'"uv-preview-R{n:02}"))\n            }}')
        content = original.replace(BEFORE.encode(), expr.encode())
        edit.write_bytes(content)
        return hashlib.sha256(content).hexdigest()

    def copy(src, dest):
        if os.path.lexists(dest):
            raise RuntimeError(f"destination already occupied: {dest}")
        subprocess.run(["cp", "-a", "--reflink=auto", str(src), str(dest)], check=True)

    controls = out / "admission.json"
    touched = False
    try:
        if args.phase == "pilot":
            out.mkdir(parents=True, exist_ok=False)
            tools.mkdir(mode=0o700)
            (tools / "bin").mkdir()
            (tools / "linker").mkdir()
            for wrapper in (tools / "bin/cc", tools / "rustc-wrapper", paths["linker_wrapper"]):
                wrapper.symlink_to(WRAP)
            (out / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
            copy(root / "seed-target", target)
            predecessor = tools / "common-predecessor"
            try:
                run("base", "warm", "native", warm=True)
                if run("base", "fresh", "native", warm=True):
                    raise RuntimeError("wrapper configuration failed to settle")
                touched = True
                put(0)
                run("base", "structural-R00", "native")
                if run("base", "structural-fresh", "native", warm=True):
                    raise RuntimeError("R00 predecessor failed to settle")
            finally:
                target.rename(predecessor)
            for mode, arm in CELLS:
                copy(predecessor, tools / f"target-{mode}-{arm}")
            jobs = [(1, CELLS)]
            expected = None
        else:
            if json.loads((out / "protocol.json").read_text()) != json.loads(json.dumps(protocol)):
                raise RuntimeError("frozen binary/configuration changed")
            expected = controls.read_text().strip()
            jobs = [(n, [("count", arm) for arm in order]) for n,order in zip(edits, orders)]

        with (out / f"{args.phase}.csv").open("x", newline="") as raw:
            writer = csv.DictWriter(raw, ["endpoint", "pair", "order", "arm", "mode", "source_sha256", "cargo", "rustc", "wild", "value"])
            writer.writeheader()
            rows = []
            for n, cells in jobs:
                touched = True
                source_hash = put(n)  # Exactly one write and timestamp across all cells.
                for rank, (mode, arm) in enumerate(cells):
                    parked = tools / f"target-{mode}-{arm}"
                    parked.rename(target)
                    try:
                        roster, totals = run(arm, f"{args.phase}-{n:02}-{rank}-{mode}-{arm}", mode)
                    finally:
                        target.rename(parked)
                    if expected is None:
                        expected = roster
                    if expected != roster:
                        raise RuntimeError(f"native/counter or arm workload mismatch: {args.phase}-{n}-{rank}-{mode}-{arm}")
                    row = dict(endpoint=ep, pair=n, order=rank, arm=arm, mode=mode,
                               source_sha256=source_hash, value=sum(totals.values()), **totals)
                    writer.writerow(row)
                    raw.flush()
                    rows.append(row)
                print(f"{ep} admitted {args.phase} R{n:02}", flush=True)
            if args.phase == "pilot":
                controls.write_text(expected + "\n")
            else:
                report(rows)
    except Exception as exc:
        if out.is_dir():
            (out / f"rejected-{args.phase}.json").write_text(json.dumps({"error": str(exc)}) + "\n")
        raise
    finally:
        if touched:
            edit.write_bytes(original)
            os.utime(edit, ns=(stat.st_atime_ns, stat.st_mtime_ns))


if __name__ == "__main__":
    main()
