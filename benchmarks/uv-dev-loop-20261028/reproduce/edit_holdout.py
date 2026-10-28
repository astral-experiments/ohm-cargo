"""Measure warmed Cargo commands after paired private-body edits to an archived uv."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure import BENCH, COMMANDS as WORKSPACE_COMMANDS, RUST, WORK, digest, report


REVISION = "c22e6b71933443e9cd299d4b6ac8de035ed4825b"
EDIT_PATH = Path("crates/uv/src/install_source.rs")
BEFORE = "component == cellar && next == formula"
COMMANDS = {
    "check": ["check", "-p", "uv", "--lib"],
    "build": ["build", "-p", "uv"],
    "test": ["test", "-p", "uv", "--test", "it", "--no-run"],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("warm", "seal", "measure"))
    parser.add_argument("endpoint", choices=COMMANDS)
    parser.add_argument("--study", required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--pairs", type=int, default=8)
    parser.add_argument("--workspace", action="store_true", help="run the default full-workspace command")
    parser.add_argument("--cargo-home", type=Path, help="private Cargo home; warm creates it from the staged registry if absent")
    parser.add_argument("--mode", choices=("dynamorio", "wall"), default="dynamorio")
    parser.add_argument("--toolchain-plan", type=Path, help="freeze and audit a private paired linker")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.study) or args.pairs < 2 or args.pairs % 2:
        parser.error("supply a simple study name and an even number of paired trials")
    ep = args.endpoint
    root = BENCH / f"edit-{args.study}-{ep}"
    source = root / "source"
    target = root / "target"
    slot = root / "bin/cargo"
    out = args.result.resolve() / ep
    binaries = {arm: getattr(args, arm).resolve(strict=not (
        args.toolchain_plan and args.phase == "warm" and arm == "candidate")) for arm in ("base", "candidate")}
    paired = None
    rust = RUST
    if args.toolchain_plan:
        from edit_toolchain import MatchedToolchain
        paired = MatchedToolchain(args, root, out, binaries)
        rust = paired.sysroot / "bin"
    elif args.phase == "seal":
        parser.error("only a paired toolchain needs a pre-measurement seal")
    hashes = {arm: digest(path) if not paired or arm == "base" else None for arm, path in binaries.items()}
    orders = [("base", "candidate"), ("candidate", "base")] * (args.pairs // 2)
    random.Random(args.seed).shuffle(orders)
    cargo_home = (args.cargo_home or (BENCH / "cargo")).resolve()
    env = dict(os.environ, CARGO_HOME=str(cargo_home), CARGO_TARGET_DIR=str(target),
               PATH=f"{rust}:{os.environ['PATH']}", RUSTC=str(rust / "rustc"),
               RUSTDOC=str(rust / "rustdoc"), CARGO_NET_OFFLINE="true",
               CARGO_TERM_COLOR="never", SSL_CERT_DIR="/etc/ssl/certs")
    commands = WORKSPACE_COMMANDS if args.workspace else COMMANDS
    command = [str(slot), *commands[ep], "--locked", "--offline", "-j8"]
    protocol = {
        "uv": REVISION, "edit_path": str(EDIT_PATH), "study": args.study,
        "primary": "check", "endpoint": ep, "command": command, "pairs": args.pairs,
        "seed": args.seed, "order": orders, "source": str(source), "visible_target": str(target),
        "cargo_sha256": hashes,
        "metric": "DynamoRIO dynamic instructions, Cargo processes' main PID and all its threads; children excluded",
        "edit": "Ohm direct private-body edit with uv-preview-XX varied by zero-based pair",
        "admission": "both arms succeed, compile/check uv, match compiled/checking package multisets, execute no test",
        "initialization": "Both persistent arm targets are independent copies of a single untouched warmed snapshot.",
        "inference": "paired proportional saving (1 - candidate/base), two-sided exact sign test and median interval",
    }
    if args.workspace or args.cargo_home or args.mode != "dynamorio":
        protocol.update(mode=args.mode, workspace=args.workspace, cargo_home=str(cargo_home),
                        admission=protocol["admission"] + ", match sorted test-executable lists")
    if args.mode == "wall":
        protocol["metric"] = "native whole-command elapsed nanoseconds including children, time.perf_counter_ns"
    if paired:
        protocol.update(paired.protocol(args.toolchain_plan))
    protocol_path = out / "protocol.json"
    serialized = json.dumps(protocol, indent=2) + "\n"

    def select(arm):
        next_path = slot.with_suffix(".next")
        os.link(binaries[arm], next_path)
        os.replace(next_path, slot)
        next_path.unlink(missing_ok=True)
        if paired:
            return paired.selected(arm, slot, hashes[arm])

    def run(log, measured=False):
        instrument = measured and args.mode == "dynamorio"
        cmd = (["python3", "-B", str(WORK / "dynamorio/count.py"), "--"] if instrument else []) + command
        with log.open("xb") as stream:
            start = time.perf_counter_ns()
            p = subprocess.run(cmd, env=env, cwd=source, stdout=stream, stderr=subprocess.STDOUT)
            elapsed = time.perf_counter_ns() - start
        body = log.read_text(errors="replace")
        if p.returncode or not re.search(r"^\s*Finished ", body, re.M):
            raise RuntimeError(f"{log}: exit {p.returncode}\n{body[-2000:]}")
        if re.search(r"^\s*(?:Running|Downloading|Updating) |^running \d+ tests?", body, re.M):
            raise RuntimeError(f"Unexpected run/network access in {log}")
        if ep == "test" and "Executable tests/it" not in body:
            raise RuntimeError(f"Missing integration-test artifact in {log}")
        return body, elapsed

    if args.phase == "warm":
        root.mkdir(mode=0o700)
        out.mkdir(parents=True, exist_ok=False)
        protocol_path.write_text(serialized)
        if paired:
            paired.stage()
        if args.cargo_home and not cargo_home.exists():
            cargo_home.mkdir(mode=0o700)
            subprocess.run(["cp", "-a", "--reflink=auto", str(BENCH / "cargo/registry"),
                            str(cargo_home / "registry")], check=True)
        if args.cargo_home and (not cargo_home.is_dir() or cargo_home.stat().st_mode & 0o077):
            raise RuntimeError(f"Expected a private Cargo home: {cargo_home}")
        slot.parent.mkdir(mode=0o700)
        source.mkdir(mode=0o700)
        with subprocess.Popen(["git", "-C", str(WORK / "uv"), "archive", REVISION],
                              stdout=subprocess.PIPE) as archive:
            subprocess.run(["tar", "-x", "-C", str(source)], stdin=archive.stdout, check=True)
            if archive.wait() != 0:
                raise RuntimeError("failed to read pinned uv archive")
        select("base")
        run(out / "warm.log")
        body, _ = run(out / "settle.log")
        if re.search(r"^\s*(Checking|Compiling) ", body, re.M):
            raise RuntimeError("Pristine fixture failed to settle")
        target.rename(root / "seed-target")
        for arm in binaries:
            subprocess.run(["cp", "-a", "--reflink=auto", str(root / "seed-target"),
                            str(root / f"target-{arm}")], check=True)
        print(f"{ep}: warmed {root}", flush=True)
        return

    if protocol_path.read_text() != serialized or target.exists():
        raise RuntimeError("Protocol or target state does not match warmed fixture")
    if paired:
        hashes = paired.seal(env, slot, checking=args.phase == "measure")
        if args.phase == "seal":
            print(f"{ep}: verified both Cargo→rustc→Wild launches and sealed {hashes}", flush=True)
            return
    edit = source / EDIT_PATH
    original = subprocess.check_output(["git", "-C", str(WORK / "uv"), "show",
                                        f"{REVISION}:{EDIT_PATH}"]).decode()
    if edit.read_text() != original or original.count(BEFORE) != 1:
        raise RuntimeError("Fixture is not the expected pristine source")
    rows = []
    with (out / "pairs.csv").open("x", newline="") as samples:
        fields = ["endpoint","pair","order","arm","value","source_sha256","compiled","test_executables"]
        writer = csv.DictWriter(samples, fields + (["cargo_sha256", "wild_sha256"] if paired else []))
        writer.writeheader()
        samples.flush()
        for pair, order in enumerate(orders):
            after = ('{\n                component == cellar && (next == formula || next == OsStr::new('
                     f'"uv-preview-{pair:02}"))\n            }}')
            contents = original.replace(BEFORE, after)
            edit.write_text(contents)
            edit_hash = hashlib.sha256(contents.encode()).hexdigest()
            expected = None
            for rank, arm in enumerate(order):
                parked = root / f"target-{arm}"
                parked.rename(target)
                try:
                    selected_elfs = select(arm)
                    log = out / f"pair-{pair:02}-{rank}-{arm}.log"
                    body, value = run(log, measured=True)
                finally:
                    target.rename(parked)
                compiled = sorted(re.findall(r"^\s*(Checking|Compiling) (.+)$", body, re.M))
                executables = sorted(re.findall(r"^\s*Executable (.+)$", body, re.M))
                if not any(re.match(r"uv v\d", name) for _, name in compiled):
                    raise RuntimeError(f"Missing rebuilt uv package in {log}")
                work = (compiled, executables)
                if expected is not None and expected != work:
                    raise RuntimeError(f"Work mismatch for pair {pair}: {expected} vs {work}")
                expected = work
                if args.mode == "dynamorio":
                    traces = re.findall(r"^DynamoRIO (.+)$", body, re.M)
                    if len(traces) != 1:
                        raise RuntimeError(f"Expected one counter in {log}")
                    value = json.loads(traces[0])["instructions"]
                row = dict(endpoint=ep, pair=pair, order=rank, arm=arm, value=value,
                           source_sha256=edit_hash, compiled=json.dumps(compiled),
                           test_executables=json.dumps(executables))
                if paired:
                    row.update(selected_elfs)
                writer.writerow(row)
                samples.flush()
                rows.append(row)
            print(f"{ep}: admitted pair {pair}, {compiled}, {len(executables)} test executables", flush=True)
    edit.write_text(original)
    if paired:
        paired.verify_release()
    report(rows)


if __name__ == "__main__":
    main()
