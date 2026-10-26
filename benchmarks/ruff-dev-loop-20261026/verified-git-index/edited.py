"""Count a complete Ruff ty_vendored check after replaying the historical include path fix."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from callgrind_runtime import prepare, select
import random
import re
import shutil
import statistics
import subprocess
import time

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
parser.add_argument(
    "--cpu", required=True, help="Available CPU number or affinity mask"
)
parser.add_argument("--pairs", type=int, choices=range(1, 21), default=12)
parser.add_argument("--seed", type=int, default=844537)
parser.add_argument(
    "--state",
    type=Path,
    help="Reuse a private toolchain and instrumented Cargo path across cohorts",
)
args = parser.parse_args()
root, target, shared, ruff = (
    p.resolve() for p in (args.output, args.target, args.shared, args.ruff)
)
assert (
    target != shared and target not in shared.parents and shared not in target.parents
)
assert target != root and target not in root.parents and root not in target.parents
root.mkdir(parents=True, exist_ok=False)


def git(*args):
    return subprocess.check_output(
        ["git", *args], cwd=ruff, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    )


assert (
    git("rev-parse", "HEAD").decode().strip()
    == "93526150df078af7dd8fc4226cdcc469539d2001"
)
assert not git("status", "--porcelain")
index = Path(
    git("rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip()
)
index_digest = hashlib.sha256(index.read_bytes()).digest()
state, cargo, stages = prepare(args, root)
env = dict(
    os.environ,
    RUSTUP_HOME=str(state / "rustup"),
    RUSTUP_AUTO_INSTALL="0",
    CARGO_TARGET_DIR=str(target),
    CARGO_BUILD_BUILD_DIR=str(shared),
    CARGO_BUILD_JOBS="4",
    CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST="all",
    CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST="all",
    CARGO_TERM_COLOR="never",
    GIT_OPTIONAL_LOCKS="0",
    LC_ALL="C.UTF-8",
)
env.setdefault("SSL_CERT_FILE", "/etc/ssl/certs/ca-certificates.crt")
env.setdefault("SSL_CERT_DIR", "/etc/ssl/certs")


def sample(arm, tag, *, prime=False):
    assert hashlib.sha256(index.read_bytes()).digest() == index_digest
    directory = root / tag
    directory.mkdir()
    select(cargo, stages[arm])
    argv = [
        "taskset",
        "-c",
        args.cpu,
        "cargo",
        "+ohm",
        "check",
        "-p",
        "ty_vendored",
        "--locked",
        "--offline",
        "--message-format=json",
    ]
    with (directory / "stderr").open("wb") as err, (directory / "stdout").open(
        "wb"
    ) as out:
        subprocess.run(
            argv,
            cwd=ruff,
            env=dict(env, CG_OUT=str(directory), CG_CHILDREN="no" if prime else "yes"),
            stdout=out,
            stderr=err,
            check=True,
        )
    assert hashlib.sha256(index.read_bytes()).digest() == index_digest
    if prime:
        return
    units = []
    for line in (directory / "stdout").read_bytes().splitlines():
        row = json.loads(line)
        if row["reason"] == "compiler-artifact":
            units.append(
                (
                    row["package_id"],
                    row["target"]["name"],
                    tuple(row["target"]["kind"]),
                    row["profile"]["test"],
                    row["fresh"],
                )
            )
    counts = {}
    for profile in directory.glob("cg.*"):
        data = profile.read_bytes()
        name = Path(re.search(rb"^cmd:\s+(\S+)", data, re.MULTILINE)[1].decode()).name
        assert name not in counts, (tag, name)
        counts[name] = int(re.search(rb"^summary: (\d+)$", data, re.MULTILINE)[1])
    assert len(units) == 182, (tag, len(units))
    return sorted(units), counts


path = "crates/ty_vendored/src/lib.rs"
source = ruff / path
after = git("show", "HEAD:" + path)
original = source.stat()
historical = "66991ac20c23ab98d358fae54d35956451245885"
old = b'include_str!("../../../crates/ty_vendored/vendor/typeshed/source_commit.txt")'
new = b'include_str!("../vendor/typeshed/source_commit.txt")'
assert source.read_bytes() == after and after.count(new) == 1 and old not in after
assert git("show", historical + "^:" + path).count(old) == 1
assert git("show", historical + ":" + path).count(new) == 1
before = after.replace(new, old)
checkpoint = root / "checkpoint"
rows = []
try:
    source.write_bytes(before)
    sample("parent", "prime", prime=True)
    warm_units, counts = sample("parent", "verify-parent")
    assert all(u[-1] for u in warm_units) and counts.keys() == {"cargo"}
    assert sample("candidate", "verify-candidate")[0] == warm_units
    subprocess.run(["cp", "-a", "--reflink=auto", target, checkpoint], check=True)
    # Every run observes the same post-edit timestamp, later than the primes.
    modified = time.time_ns()
    flips = list(range(args.pairs))
    random.Random(args.seed).shuffle(flips)
    for pair, flip in enumerate(flips):
        order = ("candidate", "parent") if flip % 2 else ("parent", "candidate")
        values = {}
        for arm in order:
            subprocess.run(
                [
                    "rsync",
                    "-a",
                    "--delete",
                    "--modify-window=-1",
                    str(checkpoint) + "/",
                    str(target) + "/",
                ],
                check=True,
            )
            source.write_bytes(after)
            os.utime(source, ns=(original.st_atime_ns, modified))
            units, counts = sample(arm, f"{pair:02}-{arm}")
            assert [u[:-1] for u in units] == [u[:-1] for u in warm_units]
            assert [u[1:3] for u in units if not u[-1]] == [("ty_vendored", ("lib",))]
            assert counts.keys() == {"cargo", "rustc", "build_script_build"}
            values[arm] = counts
        row = (
            pair,
            order[0],
            sum(values["parent"].values()),
            sum(values["candidate"].values()),
            json.dumps(values["parent"], sort_keys=True),
            json.dumps(values["candidate"], sort_keys=True),
        )
        rows.append(row)
        print(*row, flush=True)
finally:
    source.write_bytes(after)
    os.utime(source, ns=(original.st_atime_ns, original.st_mtime_ns))
    assert not git("status", "--porcelain")
with (root / "pairs.csv").open("w", newline="") as out:
    writer = csv.writer(out)
    writer.writerow(
        [
            "pair",
            "first_arm",
            "parent_ir",
            "candidate_ir",
            "parent_by_exe",
            "candidate_by_exe",
        ]
    )
    writer.writerows(rows)
savings = [100 * (1 - row[3] / row[2]) for row in rows]
print(f"Median paired reduction {statistics.median(savings):.3f}%")
