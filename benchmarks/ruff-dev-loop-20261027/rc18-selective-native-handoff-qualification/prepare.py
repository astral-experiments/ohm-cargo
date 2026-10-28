"""Prepare private Linux QA mounts for one previously qualified Ruff binary. No commands run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

GATE = "7a6c8c588068b3f49f94dcf52f383c8f6562c811cf258059902d2243e860a72e"
WILD = "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
NATIVE = Path("/run/ohm-native-handoff-v1")
GCC_LINKER = "lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd"
TARGET = "generate_inline_tests-7074d6b4fa9dfd32"

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def require(value, message):
    if not value:
        raise ValueError(message)

def authenticated(path, expected):
    require(re.fullmatch(r"[0-9a-f]{64}", expected), f"invalid digest for {path}")
    require(path.is_file() and digest(path) == expected, f"input identity mismatch: {path}")

def write(path, value):
    with path.open("x") as out:
        json.dump(value, out, indent=2, sort_keys=True)
        out.write("\n")

def assemble(a):
    target = Path(a.target)
    require(target.is_absolute() and target.name == TARGET and str(target) == a.target,
            "unexpected logical target")
    for path in (a.out, a.sdk, a.receiver, a.gate, a.stock, a.gcc, a.collect2, a.workers):
        require(path.is_absolute(), f"absolute path required: {path}")
    require(not a.out.exists(), "destination already exists")
    authenticated(a.gate, GATE)
    authenticated(a.stock, WILD)
    authenticated(a.receiver / "check", a.checker_sha256)
    authenticated(a.workers, a.workers_sha256)
    workers = json.loads(a.workers.read_bytes())
    if "workers" in workers:
        require(workers.get("target", a.target) == a.target, "policy names another target")
        workers = workers["workers"]
    require(set(workers) == {str(i) for i in range(1, 9)}, "missing or unexpected width")
    outputs = set()
    for row in workers.values():
        require(set(row) == {"training_sha256","output_blake3"}, "unrecognized width certificate")
        require(re.fullmatch(r"[0-9a-f]{64}", row["output_blake3"]), "bad output BLAKE3")
        proof = row["training_sha256"]
        require(re.fullmatch(r"[0-9a-f]{64}", proof), "bad recipe SHA")
        authenticated(a.receiver / "recipes" / (proof + ".json"), proof)
        outputs.add(row["output_blake3"])
    # Every trained width of this particular selected file reproduced one byte-for-byte output.
    require(len(outputs) == 1, "the width table contains different retained images")
    require(os.access(a.receiver/"check", os.X_OK) and os.access(a.stock, os.X_OK)
            and os.access(a.gate, os.X_OK), "non-executable transport, stock or checker")
    policy = {"schema":1, "target":a.target, "wild_sha256":WILD, "required_mode":0o775,
              "checker_sha256":a.checker_sha256, "gcc_sha256":digest(a.gcc),
              "collect2_sha256":digest(a.collect2), "workers":workers}
    # The caller authenticates the small receiver library closure against the training host.
    # Explicit paths permit relative SONAME symlinks. The digest binds the resolved ELF.
    authenticated(a.runtime, a.runtime_sha256)
    runtime = json.loads(a.runtime.read_bytes())
    require(isinstance(runtime, dict) and len(runtime) >= 4, "incomplete checker runtime")
    for name, expected in runtime.items():
        path = Path(name)
        require(path.is_absolute(), "runtime needs absolute resolved paths")
        authenticated(path, expected)
    need = ("ld-linux-x86-64.so.2","libjson-c.so","libcrypto.so","libc.so")
    require(all(any(Path(n).name.startswith(r) for n in runtime) for r in need),
            "missing checker shared library")
    a.out.mkdir(mode=0o700)
    transport = a.out/"transport"
    shutil.copyfile(a.gate, transport)
    transport.chmod(0o555)
    authenticated(transport,GATE)
    capsule = a.out/"capsule"
    capsule.mkdir(mode=0o700)
    (capsule/"recipes").mkdir()
    # Do not copy a mutable input tree or let an additional recipe file join the admission.
    for row in workers.values():
        name = row["training_sha256"]+".json"
        if not (capsule/"recipes"/name).exists():
            shutil.copyfile(a.receiver/"recipes"/name,capsule/"recipes"/name)
        authenticated(capsule/"recipes"/name, row["training_sha256"])
    shutil.copyfile(a.receiver/"check",capsule/"check")
    (capsule/"check").chmod(0o555)
    authenticated(capsule/"check",a.checker_sha256)
    write(capsule/"policy.json",policy)
    (capsule/"ld.stock").touch()
    (capsule/"audit").mkdir()
    audit = a.out/"audit"
    audit.mkdir(mode=0o700)
    mounts = ["--ro-bind",str(capsule),str(NATIVE),
              "--bind",str(audit),str(NATIVE/"audit"),
              "--ro-bind",str(a.stock.resolve()),str(NATIVE/"ld.stock"),
              "--ro-bind",str(transport),str(a.sdk/GCC_LINKER)]
    write(a.out/"bwrap-argv.json", mounts)
    write(a.out/"binding.json", {"schema":1, "transport_sha256":GATE, "stock_sha256":WILD,
          "receiver_sha256":a.checker_sha256, "workers_sha256":a.workers_sha256,
          "runtime_sha256":a.runtime_sha256, "policy_sha256":digest(capsule/"policy.json"),
          "mounts_sha256":digest(a.out/"bwrap-argv.json"), "argc":len(mounts),
          "target":a.target, "workers":sorted(map(int, workers)), "output_blake3":outputs.pop()})

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("out","sdk","receiver","gate","stock","gcc","collect2","workers","runtime"):
        p.add_argument("--"+k, required=True, type=Path)
    for k in ("target","checker-sha256","workers-sha256","runtime-sha256"):
        p.add_argument("--"+k, required=True)
    assemble(p.parse_args())
