"""Run a local independent #286 A/B from the published protocol and local Cargo images."""
import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import runpy
import signal
import subprocess as sp
import sys

HERE = Path(__file__).resolve().parent
builder = runpy.run_path(str(HERE / "build_pair.py"))
CANDIDATE, PARENT, WILD, check, digest, save = (builder[k] for k in ("CANDIDATE", "PARENT", "WILD", "check", "digest", "save"))
TEMPLATE = HERE.with_name("rc20-profile-workspace-resolve-wall")
TEMPLATE_MANIFEST = "7b58abf3481bbd80fed8eee2d15ef22cbcf94ca6ee75b1913c7cb799d51c8a77"
MEMBERS = ("subjects.json", "analyze.py", "native_execs.py", "replay.py", "workload.py", "consumer.rs")


def enroll(template, dest, a, b, sdk):
    manifest = template / "SHA256SUMS"
    check(digest(manifest) == TEMPLATE_MANIFEST, "unexpected original replay manifest")
    members = {name: sha for sha, name in (line.split("  ", 1) for line in manifest.read_text().splitlines())}
    for name in MEMBERS:
        check(digest(template / name) == members[name], name)
    doc = json.loads((template / "subjects.json").read_bytes())
    old_base = doc["build"]["baseline_binary"]
    check((doc["build"]["baseline"], doc["build"]["source"]) == (PARENT, CANDIDATE), "unexpected source lineage")
    doc["build"] = dict(baseline=PARENT, source=CANDIDATE, baseline_binary=a, cargo_sha256=b)
    doc = {k: doc[k] for k in ("ruff", "historical", "original_manifest_sha256", "patch_sha256", "lock_sha256", "build")}
    code = (template / "workload.py").read_text()
    constants = {n.targets[0].id: n.value.value for n in ast.parse(code).body
                 if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Constant)}
    check(constants["BASE"] == old_base, "inconsistent registered parent")
    rust, wild = digest(sdk / "bin/rustc"), digest(sdk / WILD)
    substitutions = {"workload.py": [(old_base, a), (constants["RUST"], rust), (constants["WILD"], wild)],
                     "analyze.py": [(old_base, a)], "replay.py": [(constants["RUST"], rust), (constants["WILD"], wild)]}
    dest.mkdir()
    save(dest / "subjects.json", doc)
    for name in MEMBERS[1:]:
        data = (template / name).read_bytes()
        for old, new in substitutions.get(name, []):
            check(data.count(old.encode()) == 1, "ambiguous template binding: " + name)
            data = data.replace(old.encode(), new.encode())
        if name == "replay.py":
            old = b'shutil.copy2(node, lower / "sdk/bin" / node.name)'
            new = b'(lower / "sdk/bin" / node.name).symlink_to(node.resolve(strict=True))'
            check(data.count(old) == 1, "unexpected SDK staging")
            data = data.replace(old, new)
        if name == "workload.py":
            marker = b'    env = dict(HOME='
            ledger = b"""    runtime = {}
    for role in [sdk/"bin/rustc", sdk/"bin/rustdoc", next((sdk/"lib").glob("librustc_driver-*.so")), sdk/"lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd"]:
        info = role.stat()
        runtime[role.name] = [str(role.resolve()), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
    dump(output/"runtime-identity.json", runtime)
"""
            check(data.count(marker) == 1, "unexpected enrollment")
            data = data.replace(marker, ledger + marker)
        (dest / name).write_bytes(data)
    return {"original_manifest": TEMPLATE_MANIFEST, "runtime_rustc": rust, "runtime_wild": wild,
            "runner": {name: digest(dest / name) for name in MEMBERS}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("checkout", "control", "candidate", "sdk", "cargo-home", "out", "scratch"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--pair-receipt", type=Path, help="build_pair.py receipt or matching external production-build receipt")
    p.add_argument("--proxies", type=Path, default=Path.home() / ".cargo/bin")
    p.add_argument("--registry-config", type=Path, help="optional credentials-free registry mapping")
    p.add_argument("--cpus", required=True, help="four available logical CPU IDs, comma separated")
    p.add_argument("--reserve-gib", type=int, default=24)
    p.add_argument("--workload", choices=("build", "test", "both"), default="both")
    p.add_argument("--minimum-memory-gib", type=int, default=0, help="stop if Linux MemAvailable falls below this floor")
    p.add_argument("--protect", action="append", nargs=2, default=[], metavar=("FILESYSTEM_PATH", "GIB"), help="additional physical free-space floor")
    x = p.parse_args()

    def health():
        for path, gib in x.protect:
            check(int(gib) >= 0 and shutil.disk_usage(path).free > int(gib) * 2**30, "protected filesystem reserve: " + path)
        mem = next(row for row in Path("/proc/meminfo").read_text().splitlines() if row.startswith("MemAvailable:"))
        check(x.minimum_memory_gib >= 0 and int(mem.split()[1]) * 1024 > x.minimum_memory_gib * 2**30, "host memory reserve")

    health()
    os.umask(0o077)
    out, scratch = x.out.absolute(), x.scratch.absolute()
    check(all(not os.path.lexists(d) and d.parent == d.parent.resolve(strict=True) for d in (out, scratch))
          and not out.is_relative_to(scratch) and not scratch.is_relative_to(out), "two separate absent directories required")
    check(x.reserve_gib >= 24 and
          all(shutil.disk_usage(d).free > x.reserve_gib * 2**30 for d in (out.parent, scratch.parent, Path.home())), "disk reserve")
    control, candidate = [d.resolve(strict=True) for d in (x.control, x.candidate)]
    a, b = digest(control), digest(candidate)
    vv = [sp.check_output([str(d), "-Vv"]) for d in (control, candidate)]
    check(a != b and vv[0] == vv[1] and ("commit-hash: " + PARENT + "\n").encode() in vv[0], "two distinct images with the same full parent stamp required")
    sdk = x.sdk.resolve(strict=True)
    receipt = None
    if x.pair_receipt:
        r = json.loads(x.pair_receipt.read_bytes())
        check((r["baseline"], r["source"], r["baseline_binary"], r["cargo_sha256"]) == (PARENT, CANDIDATE, a, b), "source receipt disagrees")
        receipt = digest(x.pair_receipt)
    out.mkdir(mode=0o700)
    scratch.mkdir(mode=0o700)
    binding = enroll(TEMPLATE, out / "runner", a, b, sdk)
    driver, = (sdk / "lib").glob("librustc_driver-*.so")
    binding.update(kind="independent local replication", cargo_a=a, cargo_b=b,
                   full_cargo_version=vv[0].decode(), build_receipt=receipt, driver=digest(driver),
                   sdk_marker=(sdk / ".ohm-version").read_text().strip() if (sdk / ".ohm-version").is_file() else None,
                   cpus=x.cpus, workload=x.workload, reserve_gib=x.reserve_gib)
    save(out / "enrollment.json", binding)
    for mode in ("mechanism", "wall"):
        physical = scratch / mode
        cmd = [sys.executable, "-IB", str(out / "runner/replay.py"), "--scratch", str(physical),
               "--checkout", str(x.checkout.resolve(strict=True)), "--cargo-a", str(control), "--cargo-b", str(candidate),
               "--sdk", str(sdk), "--cargo-home", str(x.cargo_home.resolve(strict=True)), "--rustup-proxies", str(x.proxies.resolve(strict=True)),
               "--cpus", x.cpus, "--reserve-gib", str(x.reserve_gib), "--workload", x.workload]
        if x.registry_config:
            cmd += ["--registry-config", str(x.registry_config.resolve(strict=True))]
        if mode == "mechanism":
            cmd += ["--mechanism-only"]
        dest = out / mode
        dest.mkdir()
        with (dest / "stdout").open("xb") as stdout, (dest / "stderr").open("xb") as stderr:
            with sp.Popen(cmd, stdout=stdout, stderr=stderr) as r:
                try:
                    while r.poll() is None:
                        health()
                        try:
                            r.wait(timeout=1)
                        except sp.TimeoutExpired:
                            pass
                except BaseException:
                    r.send_signal(signal.SIGINT)
                    r.wait(timeout=30)
                    raise
        for name in ("results", "replay-config.json", "paired-wall.json"):
            t = physical / name
            if t.is_dir():
                shutil.copytree(t, dest / name)
            elif t.is_file():
                shutil.copy2(t, dest / name)
        save(dest / "exit.json", {"exit": r.returncode})
        check(r.returncode == 0, str(dest / "stderr"))
    save(out / "result.json", {"kind": binding["kind"], "workload": x.workload, "status": "passed",
         "data": digest(out / "wall/paired-wall.json"), "enrollment": digest(out / "enrollment.json")})
    print(out / "wall/paired-wall.json")


if __name__ == "__main__":
    main()
