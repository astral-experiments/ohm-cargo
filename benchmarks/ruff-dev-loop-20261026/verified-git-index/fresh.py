"""Count complete warm Cargo commands on Ruff in balanced four-run blocks."""

import argparse
import hashlib
import csv
import itertools
import json
import math
import os
from pathlib import Path
from callgrind_runtime import prepare, select
from proof_inventory import record_inventory
import random
import re
import shutil
import statistics
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
for option in (
    "parent",
    "candidate",
    "toolchain",
    "ruff",
    "target",
    "shared",
    "output",
):
    parser.add_argument("--" + option, type=Path, required=True)
parser.add_argument("--package", help="Omit for the default workspace command")
parser.add_argument(
    "--mode", choices=("check", "build", "test", "all"), default="check"
)
parser.add_argument("--blocks", type=int, choices=range(1, 17), default=8)
parser.add_argument("--design", choices=("four-run", "paired"), default="four-run")
parser.add_argument("--pairs", type=int, choices=range(1, 21), default=12)
parser.add_argument(
    "--artifact-messages",
    action="store_true",
    help="Also request Cargo JSON in the timed samples",
)
parser.add_argument("--cpu", required=True, help="CPU affinity such as 2 or 0-3")
parser.add_argument("--seed", type=int, default=101821)
parser.add_argument("--jobs", choices=(4, 6), type=int, default=4)
parser.add_argument(
    "--cold",
    action="store_true",
    help="Require an otherwise empty private certificate directory and evict its one record before every run",
)
parser.add_argument(
    "--state",
    type=Path,
    help="Reuse a private toolchain and instrumented Cargo path across cohorts",
)
parser.add_argument(
    "--guard-proofs",
    action="store_true",
    help="Verify private proof inventories around each scored Cargo command",
)
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
ruff, target, shared = (p.resolve() for p in (args.ruff, args.target, args.shared))
assert (
    target != shared and target not in shared.parents and shared not in target.parents
)
assert (
    subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ruff, text=True).strip()
    == "93526150df078af7dd8fc4226cdcc469539d2001"
)
git_env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
assert not subprocess.check_output(
    ["git", "status", "--porcelain"], cwd=ruff, env=git_env
)
git_index = Path(
    subprocess.check_output(
        ["git", "rev-parse", "--path-format=absolute", "--git-path", "index"],
        cwd=ruff,
        env=git_env,
        text=True,
    ).strip()
)
index_digest = hashlib.sha256(git_index.read_bytes()).digest()
state, real, stages = prepare(args, out)
env = dict(
    os.environ,
    RUSTUP_HOME=str(state / "rustup"),
    RUSTUP_AUTO_INSTALL="0",
    CARGO_TARGET_DIR=str(target),
    CARGO_BUILD_BUILD_DIR=str(shared),
    CARGO_BUILD_JOBS=str(args.jobs),
    GIT_OPTIONAL_LOCKS="0",
    CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST="all",
    CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST="all",
    CARGO_TERM_COLOR="never",
    LC_ALL="C.UTF-8",
)
env.setdefault("SSL_CERT_FILE", "/etc/ssl/certs/ca-certificates.crt")
env.setdefault("SSL_CERT_DIR", "/etc/ssl/certs")


def benchmark_mode(mode, seed):
    run_root = out
    if args.mode == "all":
        run_root = out / mode
        run_root.mkdir()
    command = ["taskset", "-c", args.cpu, "cargo", "+ohm", mode]
    if mode == "test":
        command.append("--no-run")
    command += ["--locked", "--offline"]
    if args.package:
        command += ["-p", args.package]

    receipt = None
    digest = None
    inventory = None

    def run(arm, tag, prime=False, validate=False):
        assert hashlib.sha256(git_index.read_bytes()).digest() == index_digest
        if inventory is not None:
            record_inventory(
                run_root / "cache-inventory.jsonl",
                inventory,
                env["CARGO_HOME"],
                not args.cold,
                tag + ":before",
            )
        if receipt is not None and not prime and not validate:
            if receipt.exists():
                shutil.move(receipt, run_root / ("evicted-" + tag))
            assert not list(receipt.parent.iterdir())
        work = run_root / tag
        work.mkdir()
        select(real, stages[arm])
        argv = command + (
            ["--message-format=json"]
            if prime or validate or args.artifact_messages
            else []
        )
        with (work / "stderr").open("wb") as stderr:
            stdout = subprocess.check_output(
                argv,
                cwd=ruff,
                stderr=stderr,
                env=dict(env, CG_OUT=str(work), CG_CHILDREN="no" if prime else "yes"),
            )
        assert hashlib.sha256(git_index.read_bytes()).digest() == index_digest
        if inventory is not None:
            record_inventory(
                run_root / "cache-inventory.jsonl",
                inventory,
                env["CARGO_HOME"],
                not args.cold,
                tag + ":after",
            )
        if receipt is not None and not prime and not validate:
            if arm == "candidate":
                assert receipt.read_bytes() == digest
            else:
                assert not receipt.exists()
        if prime:
            return
        profiles = list(work.glob("cg.*"))
        assert len(profiles) == 1, (tag, profiles)
        data = profiles[0].read_bytes()
        assert (
            Path(re.search(rb"^cmd:\s+(\S+)", data, re.M)[1].decode()).name == "cargo"
        )
        if validate or args.artifact_messages:
            units = []
            for line in stdout.splitlines():
                row = json.loads(line)
                if row["reason"] == "compiler-artifact":
                    assert row["fresh"], row["target"]["name"]
                    units.append(
                        (
                            row["package_id"],
                            row["target"]["name"],
                            row["target"]["kind"],
                            row["profile"]["test"],
                        )
                    )
            assert units
            if validate:
                return sorted(units)
            assert sorted(units) == expected_units
        return int(re.search(rb"^summary: (\d+)$", data, re.M)[1])

    run("parent", "prime", prime=True)
    expected_units = run("parent", "verify-parent", validate=True)
    assert expected_units == run("candidate", "verify-candidate", validate=True)
    if args.guard_proofs:
        inventory = record_inventory(
            run_root / "cache-inventory.jsonl",
            None,
            env["CARGO_HOME"],
            not args.cold,
            "verified-roster",
        )
    if args.cold:
        assert args.mode == "check" and not args.package and args.design == "paired"
        private = Path(os.environ["CARGO_HOME"]) / ".ohm-git-index-sha1dc-v1"
        (receipt,) = private.iterdir()
        digest = receipt.read_bytes()
        assert len(digest) == 32
    rng = random.Random(seed)
    rows = []
    schedule = []
    if args.design == "four-run":
        for block in range(args.blocks):
            order = ["parent", "candidate"]
            rng.shuffle(order)
            schedule.extend([(block, 0, order), (block, 1, list(reversed(order)))])
    else:
        flips = list(range(args.pairs))
        rng.shuffle(flips)
        for block, flip in enumerate(flips):
            order = ["candidate", "parent"] if flip % 2 else ["parent", "candidate"]
            schedule.append((block, 0, order))
    for block, pair, order in schedule:
        counts = {arm: run(arm, f"{block:02}-{pair}-{arm}") for arm in order}
        row = (block, pair, order[0], counts["parent"], counts["candidate"])
        rows.append(row)
        print(*row, flush=True)
    assert expected_units == run("parent", "verify-final", validate=True)
    with (run_root / "pairs.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["block", "pair", "first_arm", "parent_ir", "candidate_ir"])
        writer.writerows(rows)
    savings = [100 * (1 - candidate / parent) for _, _, _, parent, candidate in rows]
    diffs = [r[3] - r[4] for r in rows]
    observed = abs(sum(diffs))
    if args.design == "four-run":
        block_diffs = [sum(diffs[i : i + 2]) for i in range(0, len(diffs), 2)]
        extreme = sum(
            abs(sum(s * d for s, d in zip(signs, block_diffs))) >= observed
            for signs in itertools.product((-1, 1), repeat=len(block_diffs))
        )
        p = extreme / 2 ** len(block_diffs)
    else:
        slots = [-d if r[2] == "candidate" else d for d, r in zip(diffs, rows)]
        n_first = sum(r[2] == "candidate" for r in rows)
        extreme = sum(
            abs(sum(slots) - 2 * sum(slots[i] for i in swap)) >= observed
            for swap in itertools.combinations(range(len(rows)), n_first)
        )
        p = extreme / math.comb(len(rows), n_first)
    print(
        f"Median paired reduction {statistics.median(savings):.3f}%, "
        f"two-sided randomization p={p:.5g}, {len(expected_units)} fresh units"
    )


modes = ("check", "build", "test") if args.mode == "all" else (args.mode,)
for index, mode in enumerate(modes):
    benchmark_mode(mode, args.seed + index)
