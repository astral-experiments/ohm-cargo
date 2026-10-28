"""Replay a recorded Cargo-instruction cohort from an unpacked evidence archive."""
import argparse
import csv
import json
import os
from pathlib import Path
import random
import shlex
import subprocess
import sys


def read(path):
    return json.loads(path.read_text())


def registered_order(raw, protocol):
    with raw.open() as f:
        rows = list(csv.DictReader(f))
    endpoints = list(dict.fromkeys(r["endpoint"] for r in rows))
    rng = random.Random(protocol["seed"])
    for endpoint in endpoints:
        orders = [("base", "candidate"), ("candidate", "base")] * (protocol["pairs"] // 2)
        rng.shuffle(orders)
        actual = [(int(r["pair"]), int(r["order"]), r["arm"]) for r in rows if r["endpoint"] == endpoint]
        expected = [(i, j, arm) for i, arms in enumerate(orders) for j, arm in enumerate(arms)]
        if actual != expected:
            raise ValueError(f"recorded schedule differs for {raw}: {endpoint}")
    return endpoints


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("cohort", help="for example unit-confirm, unit-replica, unit-release-like, cumulative-confirm or edit-holdout-cumulative")
    p.add_argument("--archive", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--build", action="store_true", help="build the recorded parent/head pair before replay")
    p.add_argument("--execute", action="store_true", help="execute the printed commands")
    p.add_argument("--settle-counter", action="store_true", help="add four instrumented warmups, checking freshness for the final two")
    args = p.parse_args()
    archive = args.archive.resolve()
    work = Path(os.environ.get("OHM_BENCH_WORK", archive / "reproduce")).resolve()
    if args.execute and ("OHM_BENCH_ROOT" not in os.environ or "OHM_TOOLCHAIN_BIN" not in os.environ):
        p.error("run the off-host setup first and export OHM_BENCH_ROOT and OHM_TOOLCHAIN_BIN")
    bench = Path(os.environ.get("OHM_BENCH_ROOT", archive / "replay-scratch")).resolve()
    variants = list(csv.DictReader((archive / "release-build/published-identities.tsv").read_text().splitlines(), delimiter="\t"))
    refs = {r["variant"]: r["head"] for r in variants}
    parents = dict(zip(list(refs)[1:], list(refs)[:-1]))
    edited = args.cohort.startswith("edit-holdout-")
    name = args.cohort.removeprefix("edit-holdout-") if edited else args.cohort.partition("-")[0]
    allowed = {"cumulative-confirm", "edit-holdout-cumulative", "edit-holdout-unit"}
    allowed.update(f"{stage}-{kind}" for stage in parents for kind in ("confirm", "replica", "release-like"))
    if args.cohort not in allowed:
        p.error(f"unknown first-five instruction cohort {args.cohort}")
    previous, current = ("base", "semver") if name == "cumulative" else (parents[name], name)
    release = args.cohort.endswith("-release-like")
    pairs_dir = work / "bin" / name
    release_bins = Path(os.environ.get("OHM_RELEASE_BINS", archive / "release-build/bin"))
    base, head = (release_bins / k for k in (previous, current)) if release else (
        pairs_dir / "parent", pairs_dir / "candidate")
    raw = archive / "runs" / args.cohort
    result = bench / "results" / args.cohort

    def run(*items):
        cmd = [str(x) for x in items]
        print(shlex.join(cmd), flush=True)
        if args.execute:
            subprocess.run(cmd, check=True)

    if args.build:
        if release:
            p.error("use the release-build instructions to prepare the separate Ohm-built binaries")
        run("bash", work / "build-drivers.sh", work / "ohm-cargo", refs[previous], refs[current], pairs_dir)
    if edited:
        if args.settle_counter:
            p.error("the instrumented warmup option is for unchanged workspace commands")
        for ep in ("check", "build", "test"):
            m = read(raw / ep / "protocol.json")
            extra = ["--workspace", "--cargo-home", bench / f"cargo-edit-{name}-{ep}"] if m.get("workspace") else []
            for phase in ("warm", "measure"):
                run(sys.executable, "-B", work / "edit_holdout.py", phase, ep, "--study", name, "--result", result,
                    "--base", base, "--candidate", head, "--pairs", m["pairs"], "--seed", m["seed"], *extra)
        run(sys.executable, "-B", work / "edit_holdout_summary.py", result)
    else:
        m = read(raw / "protocol.json")
        endpoints = registered_order(raw / "pairs.csv", m)
        source = {"uv": work / "uv", "u": bench / "u"}[Path(m["source"]).name]
        extra = ["--settle-counter"] if args.settle_counter or m.get("settle_counter") else []
        run(sys.executable, "-B", work / "measure.py", "--base", base, "--candidate", head,
            "--result", result, "--target", Path(m["target"]).name.removeprefix("target-"),
            "--source", source, "--cargo-home", bench / "cargo", "--mode", m["mode"],
            "--jobs", m["jobs"], "--endpoints", *endpoints, "--pairs", m["pairs"], "--seed", m["seed"], *extra)


if __name__ == "__main__":
    main()
