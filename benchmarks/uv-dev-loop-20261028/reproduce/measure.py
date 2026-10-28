"""Paired, balanced comparisons of warmed Cargo commands on a pinned workspace."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import statistics
import subprocess
import time


WORK = Path(os.environ.get("OHM_BENCH_WORK", Path(__file__).resolve().parent)).resolve()
BENCH = (Path(os.environ["OHM_BENCH_ROOT"]) if "OHM_BENCH_ROOT" in os.environ
         else Path((WORK / "bench-home.path").read_text().strip()))
RUST = Path(os.environ.get("OHM_TOOLCHAIN_BIN", WORK / "toolchain/bin"))
VALGRIND = Path(os.environ.get("OHM_VALGRIND", WORK / "profiler/usr/bin/valgrind"))
COMMANDS = {"check": ["check"], "build": ["build"], "test": ["test", "--no-run"]}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def binom_tail(n, wins):
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(wins, n + 1)) / 2 ** n)


def report(rows):
    names = dict.fromkeys(r["endpoint"] for r in rows)
    for name in names:
        pairs = {}
        for row in rows:
            if row["endpoint"] == name:
                pairs.setdefault(row["pair"], {})[row["arm"]] = row["value"]
        gains = sorted(1 - p["candidate"] / p["base"] for p in pairs.values())
        n = len(gains)
        wins = sum(g > 0 for g in gains)
        lo = max((k for k in range(1, n // 2 + 1)
                  if 2 * sum(math.comb(n, j) for j in range(k)) / 2 ** n <= 0.05), default=0)
        confidence = 1 - 2 * sum(math.comb(n, j) for j in range(lo)) / 2 ** n
        ci = f"[{gains[lo-1]:.3%}, {gains[-lo]:.3%}] ({confidence:.2%})" if lo else "unbounded"
        nonzero = sum(g != 0 for g in gains)
        pvalue = binom_tail(nonzero, max(wins, nonzero - wins))
        print(f"{name}: {n} pairs, {wins} faster, median saving {statistics.median(gains):.3%}, "
              f"median interval {ci}, two-sided sign p={pvalue:.6g}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--target", default="main")
    parser.add_argument("--source", type=Path, default=WORK / "uv")
    parser.add_argument("--cargo-home", type=Path, default=BENCH / "cargo")
    parser.add_argument("--mode", choices=("instructions", "dynamorio", "wall", "rss"), required=True)
    parser.add_argument("--endpoints", nargs="+", choices=COMMANDS, default=list(COMMANDS))
    parser.add_argument("--pairs", type=int, default=12)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--package")
    parser.add_argument("--jobs", type=int, default=16)
    parser.add_argument("--ordinary", action="store_true", help="use the Cargo subcommand's default job and lock settings")
    parser.add_argument("--settle-counter", action="store_true", help="also warm each arm under the selected instruction counter")
    args = parser.parse_args()
    if args.pairs < 2 or args.pairs % 2:
        parser.error("--pairs must be even")
    bins = {s: getattr(args, s).resolve(strict=True) for s in ("base", "candidate")}
    out = args.result.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = args.source.resolve()
    if args.ordinary and (args.package or args.jobs != 16):
        parser.error("--ordinary requires the default workspace invocation")
    lock_before = digest(source / 'Cargo.lock') if args.ordinary else None
    slot = WORK / f"bin/measured-{args.target}/cargo"
    slot.parent.mkdir(parents=True, exist_ok=True)
    target = BENCH / f"target-{args.target}"
    cargo_home = args.cargo_home.resolve(strict=True)
    env = dict(os.environ, PATH=f"{RUST}:{os.environ['PATH']}", CARGO_HOME=str(cargo_home),
               CARGO_NET_OFFLINE="true", CARGO_TARGET_DIR=str(target), CARGO_TERM_COLOR="never",
               RUSTC=str(RUST / "rustc"), RUSTDOC=str(RUST / "rustdoc"), SSL_CERT_DIR="/etc/ssl/certs")
    valgrind_lib = WORK / "profiler/usr/libexec/valgrind"
    if valgrind_lib.is_dir():
        env.setdefault("VALGRIND_LIB", str(valgrind_lib))
    meta = {"mode": args.mode, "cargo_sha256": {k: digest(v) for k, v in bins.items()},
            "source": str(source), "target": str(target), "cargo_home": str(cargo_home),
            "seed": args.seed, "jobs": args.jobs,
            "affinity": sorted(os.sched_getaffinity(0)), "pairs": args.pairs, "package": args.package}
    if args.settle_counter:
        if args.mode not in ("instructions", "dynamorio"):
            parser.error("--settle-counter requires an instruction counter")
        meta["settle_counter"] = True
    if args.ordinary:
        env.pop('CARGO_BUILD_JOBS', None)
        meta.update(jobs=None, argv={ep: COMMANDS[ep] for ep in args.endpoints}, lock_sha256=lock_before)
    (out / "protocol.json").write_text(json.dumps(meta, indent=2) + "\n")

    def select(arm):
        temp = slot.with_suffix(".next")
        os.link(bins[arm], temp)
        os.replace(temp, slot)
        # rename() is a no-op when both names already refer to the same inode.
        temp.unlink(missing_ok=True)

    def run(ep, arm, label, measured, instrument_warmup=False):
        select(arm)
        cmd = [str(slot), *COMMANDS[ep]]
        if not args.ordinary:
            cmd.extend(["--locked", "--offline", f"-j{args.jobs}"])
        if args.package:
            cmd.extend(["-p", args.package])
        if (measured or instrument_warmup) and args.mode == "instructions":
            cmd = [str(VALGRIND), "--tool=cachegrind", "--trace-children=no",
                   "--cachegrind-out-file=/dev/null", *cmd]
        if (measured or instrument_warmup) and args.mode == "dynamorio":
            cmd = ["python3", "-B", str(WORK / "dynamorio/count.py"), "--", *cmd]
        log = out / f"{ep}-{label}-{arm}.log"
        if measured and args.mode == "rss":
            cmd = ["/usr/bin/time", "-f", "%M", "-o", str(log.with_suffix(".rss")), *cmd]
        with log.open("wb") as stream:
            start = time.perf_counter_ns()
            p = subprocess.run(cmd, cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT)
            elapsed = (time.perf_counter_ns() - start) / 1e9
        body = log.read_text(errors="replace")
        if p.returncode != 0 or "Finished " not in body:
            raise RuntimeError(f"{log}: exit {p.returncode}\n" + body[-2000:])
        if measured and re.search(r"^\s*(Compiling|Checking|Downloading|Updating) ", body, re.M):
            raise RuntimeError(f"non-fresh work during {log}")
        if measured and args.mode == "wall" and "Blocking waiting for file lock" in body:
            raise RuntimeError(f"contended lock during wall-time run {log}")
        if measured and args.mode == "instructions":
            return int(re.findall(r"I refs:\s+([\d,]+)", body)[-1].replace(",", ""))
        if measured and args.mode == "dynamorio":
            return json.loads(re.findall(r"^DynamoRIO (.+)$", body, re.M)[-1])["instructions"]
        if measured and args.mode == "rss":
            return int(log.with_suffix(".rss").read_text())
        return elapsed

    rng = random.Random(args.seed)
    orders = {}
    for ep in args.endpoints:
        orders[ep] = [("base", "candidate"), ("candidate", "base")] * (args.pairs // 2)
        rng.shuffle(orders[ep])
    # Keep each command on its settled artifact graph throughout its own cohort.
    rows = []
    with (out / "pairs.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, ["endpoint", "pair", "order", "arm", "value"])
        writer.writeheader()
        for ep in args.endpoints:
            for arm in ["base", "candidate", "base", "candidate"]:
                run(ep, arm, f"warm-{len(list(out.glob(ep+'-warm*')))}", False)
            if args.settle_counter:
                for i, arm in enumerate(("base", "candidate", "base", "candidate")):
                    run(ep, arm, f"counter-warm-{i}", i >= 2, instrument_warmup=True)
            for pair, order in enumerate(orders[ep]):
                for rank, arm in enumerate(order):
                    value = run(ep, arm, str(pair), True)
                    row = dict(endpoint=ep, pair=pair, order=rank, arm=arm, value=value)
                    writer.writerow(row)
                    f.flush()
                    rows.append(row)
            report([r for r in rows if r["endpoint"] == ep])
    if args.ordinary and digest(source / 'Cargo.lock') != lock_before:
        raise ValueError('Cargo.lock changed during a default-command comparison')


if __name__ == "__main__":
    main()
