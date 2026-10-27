"""Measure a complete Ruff edit with a fixed compiler, private target and private build directory."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

P = Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027")
RUFF = Path("/home/dev-user/code/oss/ruff-ohm-whole-native-20261027")
TARGET = P / "native-target"
CARGO_SHA = "13396fe1c6886f41155ac24f507210c7a5f655e5b3279a28f45bf3a5e6bcaf08"
PARENT = "051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518"
PIN = "93526150df078af7dd8fc4226cdcc469539d2001"
ORIGINAL = "Cannot mix t-string literals with string or bytes literals"
EDITED = "Bytes literal cannot be mixed with non-bytes literals"


def sha(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")


def trace_counts(directory):
    counts = Counter()
    crates = []
    for file in directory.glob("exec.*"):
        for line in file.read_text(errors="replace").splitlines():
            exe = re.search(r'execve\("([^"]+)"', line)
            if not exe or not line.rstrip().endswith("= 0"):
                continue
            binary = Path(exe[1])
            crate = re.search(r'"--crate-name", "([^" ]+)"', line)
            if binary.name == "rustc" and crate and crate[1] != "___":
                kind = "rustc_link_only" if re.search(r'"(?:-Z)?link-only"', line) else "rustc_full"
                counts[kind] += 1
                crates.append([kind, crate[1]])
            if binary.name == "ld.bfd" and binary.parent.name == "wild-ld":
                counts["wild"] += 1
    return dict(processes=dict(counts), crates=sorted(crates))


def run(directory, label, mode, flavor, edited):
    directory.mkdir()
    assert not any(k.startswith("WILD_") for k in os.environ)
    env = dict(os.environ, RUSTUP_HOME=str(P / "rustup"), RUSTUP_AUTO_INSTALL="0", CARGO_HOME=str(P / "registry-home"),
               CARGO_TARGET_DIR=str(TARGET), CARGO_BUILD_BUILD_DIR=str(P / "shared"), CARGO_BUILD_JOBS="8",
               CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST="all", CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST="all",
               GIT_OPTIONAL_LOCKS="0", LC_ALL="C.UTF-8", CARGO_TERM_COLOR="never",
               SSL_CERT_FILE="/etc/ssl/certs/ca-certificates.crt", SSL_CERT_DIR="/etc/ssl/certs")
    command = ["cargo", "+ohm", mode]
    if mode == "test":
        command.append("--no-run")
    command += ["--locked", "--offline"]
    if flavor in {"fresh", "trace", "reference"}:
        command.append("--message-format=json")
    if flavor == "trace":
        command = ["strace", "-ff", "-qq", "-s", "2000", "-e", "trace=execve", "-o", str(directory / "exec"), *command]
    stdout = directory / "stdout"
    stderr = directory / "stderr"
    with stdout.open("wb") as out, stderr.open("wb") as err:
        start = time.monotonic_ns()
        result = subprocess.run(command, env=env, cwd=RUFF, stdout=out, stderr=err)
        elapsed = time.monotonic_ns() - start
    log = stderr.read_text()
    assert result.returncode == 0 and "Blocking waiting" not in log, (directory, log[-1700:])
    if label != "settle":
        assert not any(s.lstrip().startswith("Compiling ") and "/ruff-ohm-whole-native-" not in s for s in log.splitlines())
    receipt = {"ns": elapsed}
    if flavor in {"fresh", "trace", "reference"}:
        rows = [json.loads(s) for s in stdout.read_bytes().splitlines() if s.startswith(b"{")]
        artifacts = [r for r in rows if r["reason"] == "compiler-artifact"]
        assert rows[-1]["success"] and len(artifacts) == (501 if mode == "build" else 619)
        roster = sorted((r["package_id"], r["target"]["name"], ",".join(r["target"]["kind"]), r["profile"]["test"]) for r in artifacts)
        dirty = [[r["package_id"], r["target"]["name"], r["target"]["kind"]] for r in artifacts if not r["fresh"]]
        receipt.update(fresh=len(artifacts)-len(dirty), dirty=dirty, roster_sha=hashlib.sha256(json.dumps(roster).encode()).hexdigest())
        assert flavor == "trace" or not dirty, (label, dirty)
        (ruff,) = {r["executable"] for r in artifacts if r["target"]["name"] == "ruff" and
                   r["target"]["kind"] == ["bin"] and not r["profile"]["test"] and r["executable"]}
        oracle = subprocess.run([ruff, "check", "--isolated", "--no-cache", "--target-version", "py314", "--output-format", "json", "-"],
                                env=env, cwd=RUFF, input=b"t'first' b'second'\n", capture_output=True)
        diagnostics = json.loads(oracle.stdout)
        assert oracle.returncode == 1 and not oracle.stderr and [r["message"] for r in diagnostics] == [EDITED if edited else ORIGINAL]
        receipt["parser_diagnostics"] = diagnostics
        if flavor != "fresh":
            paths = {Path(p) for r in artifacts if r["package_id"].startswith("path+") for p in r["filenames"]}
            elfs = {}
            for path in sorted(paths):
                if path.suffix not in ("", ".so"):
                    continue
                with path.open("rb") as src:
                    if src.read(4) != b"\x7fELF":
                        continue
                elfs["/".join(path.parts[-4:])] = sha(path)
            assert len(elfs) == (15 if mode == "build" else 110)
            receipt["elf"] = elfs
    if flavor == "trace":
        receipt.update(trace_counts(directory))
    write(directory / "receipt.json", receipt)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("location", type=Path)
    cli.add_argument("arm")
    cli.add_argument("driver")
    cli.add_argument("mode", choices=["build", "test"])
    cli.add_argument("state", choices=["edited", "original"])
    cli.add_argument("actions", nargs="+")
    args = cli.parse_args()
    assert sha(P / "frozen-toolchain/bin/cargo") == CARGO_SHA
    assert sha(P / "frozen-toolchain/lib/librustc_driver-774a793a844d5500.so") == args.driver
    assert subprocess.check_output(["git", "-C", RUFF, "rev-parse", "HEAD"], text=True).strip() == PIN
    for action in args.actions:
        name, flavor = action.split("=")
        assert flavor in {"normal", "fresh", "trace", "reference"}
        run(args.location / (args.arm + "-" + name), name, args.mode, flavor, args.state == "edited")
