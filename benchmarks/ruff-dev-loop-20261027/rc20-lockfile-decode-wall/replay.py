"""Replay the two whole-Cargo workloads locally using caller-supplied, authenticated inputs."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import pwd
import select
import shutil
import signal
import subprocess as sp
import sys

HERE = Path(__file__).resolve().parent
SUBJECTS = json.loads((HERE / "subjects.json").read_bytes())
PARENT = SUBJECTS["build"]["baseline_binary"]
CANDIDATE = SUBJECTS["build"]["cargo_sha256"]
RUST = "5694abe50767a22cebeccb767143f7404d5e81c4b1760cff4426466bf410e511"
WILD = "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
PROFILE = b'[profile.fast-test]\ninherits = "dev"\nopt-level = 1\n'
HUNK = b'debug = "line-tables-only"\n# Avoid the local ThinLTO that Cargo enables at nonzero optimization levels.\nlto = "off"\n'
MODES = ["build", "test"]


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n")


def source_gate(checkout):
    def blob(rev, name):
        return sp.check_output(["git", "-C", str(checkout), "show", rev + ":" + name])
    rev = SUBJECTS["ruff"]
    orig = blob(rev, "Cargo.toml")
    digest = lambda value: hashlib.sha256(value).hexdigest()
    require(digest(orig) == SUBJECTS["original_manifest_sha256"], "wrong original manifest")
    require(orig.count(PROFILE + HUNK) == 1 and
            digest(orig.replace(PROFILE + HUNK, PROFILE)) ==
            "cd6179ed534ae36214b5554461d767080c86a3dad2652f15f304ca31d4da77a2", "wrong historical edit")
    require(digest(blob(rev, "Cargo.lock")) == SUBJECTS["lock_sha256"], "wrong lockfile")
    patch = sp.check_output(["git", "-C", str(checkout), "show", "--format=",
                             SUBJECTS["historical"], "--", "Cargo.toml"])
    require(digest(patch) == SUBJECTS["patch_sha256"], "different historical patch")


def schedule():
    for pair in range(32):
        order = ("AB", "BA", "BA", "AB")[pair % 4]
        source = ("edit", "orig")[pair % 2]
        for arm in order:
            for phase in ("edit", "repeat"):
                yield pair, order, source, arm, phase


def cli():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkout", required=True, type=Path)
    p.add_argument("--check-source", action="store_true",
                   help="only validate the two Git inputs and fixed schedule, without creating a directory")
    for arg in ("scratch", "cargo-a", "cargo-b", "sdk", "cargo-home"):
        p.add_argument("--" + arg, type=Path)
    p.add_argument("--registry-config", type=Path,
                   help="optional credentials-free Cargo config for this offline registry seed")
    p.add_argument("--rustup-proxies", type=Path, default=Path.home() / ".cargo/bin")
    p.add_argument("--cpus", default="0,1,2,3", help="four allowed logical CPU numbers")
    p.add_argument("--reserve-gib", type=int, default=24)
    p.add_argument("--workload", choices=[*MODES, "both"], default="both")
    return p.parse_args()


def namespace_command(lower, common, upper, work, view, cpus, worker_argv):
    script = """set -eu
lower=$1; common=$2; upper=$3; work=$4; view=$5; uid=$6; gid=$7; cpus=$8; shift 8
mount --bind "$lower" "$lower"
mount -o remount,bind,ro "$lower"
lowers=$lower
if test "$common" != -; then
    mount --bind "$common" "$common"
    mount -o remount,bind,ro "$common"
    lowers=$common:$lower
fi
mount -t overlay overlay -o "lowerdir=$lowers,upperdir=$upper,workdir=$work" "$view"
mount -o remount,rw,exec,nosuid,nodev "$view"
exec setpriv --reuid="$uid" --regid="$gid" --init-groups --no-new-privs \
  --inh-caps=-all --ambient-caps=-all --bounding-set=-all -- taskset -c "$cpus" "$@"
"""
    return ["sudo", "-n", "unshare", "--mount", "--propagation", "private", "--", "/bin/sh", "-ec",
            script, "private-replay", str(lower), str(common) if common else "-", str(upper), str(work), str(view),
            str(os.getuid()), str(os.getgid()), ",".join(map(str, cpus)), *map(str, worker_argv)]


def read_worker(proc):
    if not select.select([proc.stdout], [], [], 240)[0]:
        raise TimeoutError("worker exceeded the response limit")
    line = proc.stdout.readline()
    require(line, "worker exited; see the per-arm worker.stderr")
    return line.strip()


def campaign(mode, cfg, config, images):
    root = Path(cfg["scratch"])
    result = root / "results" / ("toml-" + mode + "-v1")
    result.mkdir()
    workers = {}

    def send(arm, tag, source, action):
        proc = workers[arm]
        proc.stdin.write(f"{tag} {source} {action}\n")
        proc.stdin.flush()
        reply = json.loads(read_worker(proc))
        require(reply == {"closed": True} if action == "finish" else reply["row"] == tag, "unexpected reply")
        return reply

    def identity(arm, tag):
        report = json.loads((result / arm / (tag + ".json")).read_bytes())
        return [report[k] for k in ("files", "roster", "oracle")]

    def close(arm):
        send(arm, "close", "orig", "finish")
        require(workers[arm].wait(timeout=10) == 0, "worker exit status")

    try:
        for arm in ("C", "A", "B"):
            lane = root / "lanes" / mode / arm
            (lane / "upper").mkdir(parents=True)
            (lane / "work").mkdir()
            out = result / arm
            out.mkdir()
            image, digest = images["A" if arm == "C" else arm]
            args = [sys.executable, "-IB", HERE / "workload.py", config, mode, arm, image, digest, out]
            common = None if arm == "C" else lane.parent / "C/upper"
            command = namespace_command(root / "lower", common, lane / "upper", lane / "work",
                                        root / "arena", cfg["cpus"], args)
            with (out / "worker.stderr").open("w") as err:
                workers[arm] = sp.Popen(command, stdin=sp.PIPE, stdout=sp.PIPE, stderr=err,
                                        text=True, start_new_session=True)
            require(read_worker(workers[arm]) == "READY", "missing admission")
            if arm == "C":
                send(arm, "00-prepare", "orig", "hydrate")
                send(arm, "00-frozen", "orig", "trace")
                close(arm)
            else:
                for tag, source in (("00-prepare", "orig"), ("01-edited", "edit"),
                                    ("02-restored", "orig"), ("03-settled", "orig")):
                    send(arm, tag, source, "trace")
        enrolled = identity("C", "00-frozen")
        require(all(identity(a, "03-settled") == enrolled for a in "AB"), "unequal preclock products")
        events = []
        for i, order, source, arm, phase in schedule():
            row = send(arm, f"{i:02}-{phase}", source, "wall")
            events.append(dict(pair=i, arm=arm, phase=phase, source=source, sequence=order, ns=row["ns"]))
        for arm in "BA":
            send(arm, "99-terminal", "orig", "trace")
            require(identity(arm, "99-terminal") == enrolled, "changed terminal products")
            close(arm)
        write_json(result / "terminal.json", dict(events=events, source=SUBJECTS["original_manifest_sha256"],
                   lock=SUBJECTS["lock_sha256"], base=PARENT, candidate=CANDIDATE, mode=mode))
    finally:
        for child in workers.values():
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=10)
            child.stdin.close()
            child.stdout.close()


def main():
    a = cli()
    source_gate(a.checkout)
    rows = list(schedule())
    require(len(rows) == 128 and set(Counter((s, o) for _, o, s, arm, step in rows
            if arm == "A" and step == "edit").values()) == {8}, "unbalanced schedule")
    if a.check_source:
        print("Verified pinned manifest, lockfile, historical edit and 32-pair schedule.")
        return
    require(all((a.scratch, a.cargo_a, a.cargo_b, a.sdk, a.cargo_home)), "supply all timing inputs")
    require(sys.platform.startswith("linux") and os.getuid() != 0, "run as a non-root Linux user")
    require(all(shutil.which(x) for x in ("strace", "git", "sudo", "unshare", "mount", "setpriv", "taskset", "cp")),
            "missing a Linux prerequisite")
    cpus = [int(n) for n in a.cpus.split(",")]
    require(len(cpus) == len(set(cpus)) == 4 and set(cpus) <= os.sched_getaffinity(0), "four available CPUs required")
    root = a.scratch.absolute()
    require(not os.path.lexists(root) and root.parent.resolve() == root.parent and
            not any(c in str(root) for c in (",", ":", "\\", "\n")), "scratch must be new on a literal path")
    images = {"A": (a.cargo_a.resolve(strict=True), PARENT), "B": (a.cargo_b.resolve(strict=True), CANDIDATE)}
    sdk = a.sdk.resolve(strict=True)
    registry = a.cargo_home.resolve(strict=True)
    proxies = a.rustup_proxies.resolve(strict=True)
    require(all(file_hash(f) == sha for f, sha in images.values()), "Cargo binary mismatch")
    require(file_hash(sdk / "bin/rustc") == RUST and
            file_hash(sdk / "lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd") == WILD, "toolchain mismatch")
    require(all((proxies / x).is_file() for x in ("cargo", "rustc")) and (registry / "registry").is_dir(),
            "missing rustup proxies or offline registry")
    floor = a.reserve_gib * 2**30
    require(a.reserve_gib >= 24 and shutil.disk_usage(Path.home()).free > floor, "home reserve")
    cache_parts = [registry / n for n in ("registry", "git") if (registry / n).is_dir()]
    rough_bytes = sum(int(sp.check_output(["du", "-sb", "--", str(d)]).split()[0]) for d in cache_parts)
    require(shutil.disk_usage(root.parent).free > floor + rough_bytes + 2**30, "insufficient scratch reserve")
    os.umask(0o077)
    root.mkdir()
    lower = root / "lower"
    for path in ("arena", "results", "lanes", "lower/sdk/bin", "lower/ru/toolchains", "lower/cargo-home",
                 "lower/products", "lower/shared", "lower/tmp"):
        (root / path).mkdir(parents=True, exist_ok=True)
    for d in cache_parts:
        sp.run(["cp", "-a", "--reflink=auto", "--", d, lower / "cargo-home"], check=True)
    if a.registry_config:
        shutil.copyfile(a.registry_config, lower / "cargo-home/config.toml")
    sp.run(["git", "-c", "core.hooksPath=/dev/null", "clone", "--quiet", "--no-checkout", "--local", "--shared",
            str(a.checkout.resolve()), str(lower / "source")], check=True)
    sp.run(["git", "-C", lower / "source", "-c", "core.hooksPath=/dev/null", "checkout", "--quiet", "--detach",
            SUBJECTS["ruff"]], check=True)
    (lower / "ru/toolchains/ohm").symlink_to(root / "arena/sdk", target_is_directory=True)
    # Preserve the SDK's runtime, rustdoc and tools. Only the private physical Cargo will be replaced.
    for node in sdk.iterdir():
        if node.name != "bin":
            (lower / "sdk" / node.name).symlink_to(node, target_is_directory=node.is_dir())
    for node in (sdk / "bin").iterdir():
        if node.name != "cargo":
            shutil.copy2(node, lower / "sdk/bin" / node.name)
    shutil.copy2(images["A"][0], lower / "sdk/bin/cargo")
    shutil.copyfile(HERE / "consumer.rs", lower / "consumer.rs")
    cfg = dict(scratch=str(root), home=str(Path.home()), uid=os.getuid(), username=pwd.getpwuid(os.getuid()).pw_name,
               reserve_bytes=floor, cpus=cpus, proxies=str(proxies))
    config = root / "replay-config.json"
    write_json(config, cfg)
    modes = MODES if a.workload == "both" else [a.workload]
    for mode in modes:
        campaign(mode, cfg, config, images)
    with (root / "paired-wall.json").open("x") as out:
        sp.run([sys.executable, "-IB", HERE / "analyze.py", root / "results", *modes], stdout=out, check=True)
    print(root / "paired-wall.json")


if __name__ == "__main__":
    main()
