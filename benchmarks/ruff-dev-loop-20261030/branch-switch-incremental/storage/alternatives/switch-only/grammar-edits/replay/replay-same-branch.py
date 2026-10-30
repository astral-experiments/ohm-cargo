#!/usr/bin/env python3
"""Replay the Ruff grammar edit on a private checkout using two installed x86-64 Linux SDKs."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
A = "b5dba861cc38e3f7fb4524c9ceba3e01a474ea13"
B = "7b13f01ba1569887a25670820764b24c206da8e5"
GRAMMAR = "0ecff877901a0377ad966ffab528488ce872b50e"
PATTERN = "crates/ruff_python_parser/src/parser/pattern.rs"
TREES = {"A": "2b61306d708a211b3725c8d920e7590be6da41ad",
         "B": "97ca36909f1ae8fa028b2c1f48f452fbdcdbbd4c",
         "C": "a880a27e6d496af407411ba47a14279a631b40c3"}
PATTERN_SHA = {"B": "da5e9a4ce7e4d9e01c19d8b2797c666a8e7b87c41362937546abd10a46289ccc",
               "C": "8fdc43aca04b07c900a152349e2af4572a6d0f03850e432d816a22d772b2c799"}
LOCK = "839edc8250480bb523619b8d24bd57176a6e1f57c152cca85c5adc61ea5f94eb"
PATCH = "8834f59a8db47efd11997bd3599b08765ff14c9fc1f28a6d6241225d71952b13"
READER = "33fdd78ca9c5d963ea43bb33e5158248dc9eab3f45caa3838eade3c054252048"
PHASES = [("empty-A", "A"), ("first-B", "B"), ("first-return-A", "A"), ("trained-return-B", "B"),
          ("edit-B", "C"), ("restore-B", "B"), ("edit-B-2", "C"), ("restore-B-2", "B"),
          ("unchanged-B", "B")]
CRATES = ("ruff_python_ast", "ruff_python_parser")
TARGET = "x86_64-unknown-linux-gnu"
WILD = f"lib/rustlib/{TARGET}/bin/wild-ld/ld.bfd"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def sources(donor, out, sparse):
    src = out / "source"
    def git(*args):
        return subprocess.check_output(["git", "--no-optional-locks", "-C", src, *args]).decode().strip()
    # A private object database and index keep every branch/index write in out.
    subprocess.run(["git", "init", "-q", src], check=True)
    objects = subprocess.check_output(["git", "-C", donor, "rev-parse", "--path-format=absolute", "--git-path", "objects"], text=True).strip()
    (src / ".git/objects/info/alternates").write_text(objects + "\n")
    if sparse:
        git("sparse-checkout", "set", "--no-cone", "/" + PATTERN, "/Cargo.lock")
    assert git("rev-parse", B + "^") == A
    patch = HERE / "parser-validation.patch"
    history = subprocess.check_output(["git", "-C", src, "diff", "--no-ext-diff", "--full-index",
                                       GRAMMAR + "^", GRAMMAR, "--", PATTERN])
    assert history == patch.read_bytes() and sha(patch) == PATCH and sha(HERE / "consumer.rs") == READER
    git("branch", "historical-parent", A)
    git("branch", "historical-feature", B)
    git("switch", "--quiet", "historical-parent")
    current = "A"
    def select(state):
        nonlocal current
        if current == "C" and state != "C":
            git("apply", "--index", str(patch))
        branch = "historical-parent" if state == "A" else "historical-feature"
        if git("symbolic-ref", "--short", "HEAD") != branch:
            git("switch", "--quiet", branch)
        if state == "C" and current != "C":
            git("apply", "--reverse", "--index", str(patch))
        current = state
        assert git("write-tree") == TREES[state] and git("rev-parse", "HEAD") == (A if state == "A" else B)
        assert sha(src / PATTERN) == PATTERN_SHA["C" if state == "C" else "B"] and sha(src / "Cargo.lock") == LOCK
        assert git("diff", "--cached", "--name-only") == (PATTERN if state == "C" else "")
        return {"state": state, "branch": branch, "tree": TREES[state], "grammar": sha(src / PATTERN)}
    return src, select


def registry(donor, destination, lock):
    """Copy available locked archives and their sparse entries, without modifying the donor."""
    libs = [p for p in tomllib.loads(lock.read_text())["package"] if "checksum" in p]
    aliases = sorted(p for p in (donor / "index").iterdir()
                     if (p / ".cache").is_dir() and (donor / "cache" / p.name).is_dir())
    if not aliases:
        raise SystemExit("The offline registry must contain Cargo sparse index and archive cache directories.")
    canonical = "index.crates.io-1949cf8c6b5b557f"
    for index in aliases:
        src = donor / "cache" / index.name
        (destination / "index" / index.name).mkdir(parents=True)
        (destination / "cache" / index.name).mkdir(parents=True)
        shutil.copy2(index / "config.json", destination / "index" / index.name / "config.json")
        for lib in libs:
            n = lib["name"].lower()
            if len(n) <= 2:
                key = str(len(n)) + "/" + n
            elif len(n) == 3:
                key = "3/" + n[0] + "/" + n
            else:
                key = n[:2] + "/" + n[2:4] + "/" + n
            file = src / (lib["name"] + "-" + lib["version"] + ".crate")
            pairs = [(index / ".cache" / key, Path("index") / index.name / ".cache" / key)]
            if file.is_file():
                assert sha(file) == lib["checksum"], file.name
                pairs.append((file, Path("cache") / index.name / file.name))
            for source, relative in pairs:
                dest = destination / relative
                if source.is_file() and not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
    # Mirrors and normal crates.io aliases can serve the same crate checksums.
    if not (destination / "index" / canonical).exists() and len(aliases) == 1:
        for sub in ("index", "cache"):
            (destination / sub / canonical).symlink_to(aliases[0].name)


def toolchains(raw, switch, out):
    sdk, bank = out / "sdk", out / "compilers"
    sdk.mkdir()
    for item in raw.iterdir():
        if item.name not in ("lib", "bin"):
            (sdk / item.name).symlink_to(item)
    for sub in ("bin", "lib"):
        (sdk / sub).mkdir()
        for item in (raw / sub).iterdir():
            if item.name != "rustc" and not item.name.startswith("librustc_driver"):
                (sdk / sub / item.name).symlink_to(item)
    inventory = {}
    for role, base in (("R", raw), ("K", switch)):
        driver, = (base / "lib").glob("librustc_driver*.so")
        files = {"bin/rustc": base / "bin/rustc", "lib/" + driver.name: driver}
        role_dir = bank / role
        role_dir.mkdir(parents=True)
        for file in files.values():
            # Copy once. All installations of this role subsequently share the same private inode.
            shutil.copy2(file, role_dir / file.name)
            assert sha(file) == sha(role_dir / file.name)
        std = base / "lib/rustlib" / TARGET / "lib"
        inventory[role] = {"files": {key: sha(val) for key, val in files.items()},
                           "driver": driver.name, "cargo": sha(base / "bin/cargo"), "wild": sha(base / WILD),
                           "std": {p.name: sha(p) for p in sorted(std.iterdir()) if p.is_file()}}
    assert inventory["R"]["std"], "Missing target standard library"
    for key in ("cargo", "wild", "std"):
        assert inventory["R"][key] == inventory["K"][key], key
    assert inventory["R"]["files"] != inventory["K"]["files"]
    def use(role):
        for p in (sdk / "lib").glob("librustc_driver*.so"):
            p.unlink()
        (sdk / "bin/rustc").unlink(missing_ok=True)
        ids = {}
        for target in inventory[role]["files"]:
            src = bank / role / Path(target).name
            os.link(src, sdk / target)
            assert src.samefile(sdk / target)
            ids[target] = [src.stat().st_dev, src.stat().st_ino]
        assert inventory[role].setdefault("inodes", ids) == ids
    return sdk, inventory, use


def cargo_argv():
    return ["cargo", "+ohm", "build", "-p", "ruff_python_parser", "--locked", "--offline", "-j4", "--message-format=json"]


def clean_verdict(state):
    size = 64 if state == "A" else 56
    result = "accepted" if state == "C" else "rejected"
    return f"Expr={size} signed-expression={result}"


def reader_argv(artifacts, rows, dependency_dirs, reader, exe):
    cmd = ["rustc", "+ohm", "--edition=2024", "--crate-name", "ohm_branch_reader", str(reader)]
    for crate in CRATES:
        match, = [x for x in artifacts if x["target"]["name"] == crate and "lib" in x["target"]["kind"]]
        lib, = [n for n in match["filenames"] if n.endswith(".rlib")]
        cmd += ["--extern", crate + "=" + lib]
    deps = {Path(n).parent for x in artifacts for n in x["filenames"]}
    for path in sorted(deps | set(map(Path, dependency_dirs))):
        cmd += ["-L", "dependency=" + str(path)]
    for path in sorted({x["out_dir"] for x in rows if x["reason"] == "build-script-executed" and x.get("out_dir")}):
        cmd += ["-L", "native=" + path]
    return [*cmd, "-o", str(exe)]


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--ruff", type=Path, required=True, help="Existing Ruff Git object store/checkout containing both historical changes")
    args.add_argument("--out", type=Path, required=True, help="A new directory; all outputs are kept")
    args.add_argument("--raw-sdk", type=Path)
    args.add_argument("--switch-sdk", type=Path)
    args.add_argument("--registry", type=Path, help="Previously populated Cargo registry directory for offline replay")
    args.add_argument("--check-sources-only", action="store_true", help="Exercise the actual historic branch/grammar sequence without compilation")
    opts = args.parse_args()
    donor = opts.ruff.resolve(strict=True)
    out = opts.out.resolve()
    inputs = [donor] if opts.check_sources_only else [donor, opts.raw_sdk, opts.switch_sdk, opts.registry]
    if any(x is None for x in inputs):
        args.error("Both installed SDK paths and the populated sparse registry are required for builds.")
    roots = [x.resolve(strict=True) for x in inputs]
    if any(out.is_relative_to(x) for x in roots):
        args.error("Choose an output directory outside the source, SDK and registry donors.")
    out.mkdir(parents=True, mode=0o700)
    src, select = sources(donor, out, opts.check_sources_only)
    if opts.check_sources_only:
        write(out / "sources.json", {phase: select(state) for phase, state in PHASES})
        print("Verified all nine historical Git and grammar states in the private sparse checkout.")
        return
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        args.error("This native SDK replay requires Linux x86-64.")
    home, rustup, cache = out / "home", out / "rustup", out / "cargo-home"
    home.mkdir()
    (rustup / "toolchains").mkdir(parents=True)
    registry(roots[3], cache / "registry", src / "Cargo.lock")
    sdk, inventory, use = toolchains(roots[1], roots[2], out)
    (rustup / "toolchains/ohm").symlink_to(sdk)
    target, build = out / "target", out / "build"
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "RUSTUP_HOME": str(rustup),
           "RUSTUP_TOOLCHAIN": "ohm", "RUSTUP_AUTO_INSTALL": "0", "CARGO_HOME": str(cache),
           "CARGO_TARGET_DIR": str(target), "CARGO_BUILD_BUILD_DIR": str(build), "CARGO_NET_OFFLINE": "true",
           "CARGO_ENCODED_RUSTFLAGS": "-Zohm-branch-cache=yes", "LC_ALL": "C", "LANG": "C"}
    def call(args, d, tag):
        start = time.monotonic_ns()
        proc = subprocess.run(args, cwd=src, env=env, capture_output=True)
        elapsed = time.monotonic_ns() - start
        (d / (tag + ".stdout")).write_bytes(proc.stdout)
        (d / (tag + ".stderr")).write_bytes(proc.stderr)
        proc.check_returncode()
        return proc.stdout, elapsed
    references, results = {}, {}
    def install(slot, role, phases):
        use(role)
        target.mkdir()
        build.mkdir()
        run = out / "runs" / slot
        run.mkdir(parents=True)
        for binary in ("cargo", "rustc"):
            path, _ = call(["rustup", "which", "--toolchain", "ohm", binary], run, binary + "-which")
            assert Path(os.fsdecode(path).strip()).samefile(sdk / "bin" / binary)
            call([binary, "+ohm", "-Vv"], run, binary + "-version")
        results[slot] = {}
        for phase, state in phases:
            info = select(state)
            d = run / phase
            d.mkdir()
            stream, elapsed = call(cargo_argv(), d, "cargo")
            rows = [json.loads(s) for s in stream.splitlines()]
            assert rows[-1] == {"reason": "build-finished", "success": True}
            artifacts = [x for x in rows if x["reason"] == "compiler-artifact"]
            dirty = sorted(x["target"]["name"] for x in artifacts if not x["fresh"])
            assert len(artifacts) == 97
            if phase.startswith("empty"):
                assert len(dirty) == 97
            else:
                want = [] if phase == "unchanged-B" else [CRATES[1]] if phase.startswith(("edit-", "restore-")) else list(CRATES)
                assert dirty == want, (slot, phase, dirty)
            extra = {p.parent for folder in (target, build) for suffix in ("*.rlib", "*.so") for p in folder.rglob(suffix)}
            exe = out / "reader"
            call(reader_argv(artifacts, rows, extra, HERE / "consumer.rs", exe), d, "link")
            text, _ = call([exe], d, "reader")
            want = clean_verdict(state)
            assert text.decode().strip() == want
            h = sha(exe)
            if slot.startswith("reference-"):
                references[role, state] = h
                shutil.copy2(exe, run / "clean-reader")
            assert references[role, state] == h
            allocated = subprocess.check_output(["du", "-sx", "-B1", "--", target, build], text=True)
            results[slot][phase] = {**info, "ELF": h, "verdict": want, "typed": len(artifacts), "dirty": dirty,
                                    "cargo_ns": elapsed, "allocated_bytes": sum(int(s.split()[0]) for s in allocated.splitlines())}
        closed = out / "closed" / slot
        closed.mkdir(parents=True)
        target.rename(closed / "target")
        build.rename(closed / "build")
        write(run / "results.json", results[slot])
    for role in ("R", "K"):
        for state in "ABC":
            install("reference-" + role + "-" + state, role, [("empty", state)])
    for block, order in enumerate(("RK", "KR"), 1):
        for role in order:
            install(f"pair-{block}-{role}", role, PHASES)
    for role in ("R", "K"):
        for name, expected in inventory[role]["files"].items():
            assert sha(out / "compilers" / role / Path(name).name) == expected
    assert all(references["R", state] == references["K", state] for state in "ABC")
    write(out / "results.json", {"SDK": inventory, "clean": {"/".join(k): v for k, v in references.items()}, "visits": results})
    for block in (1, 2):
        for group, phases in [("first same-B edit", ["edit-B"]), ("later same-B edits", ["restore-B", "edit-B-2", "restore-B-2"])]:
            times = [sum(results[f"pair-{block}-{role}"][p]["cargo_ns"] for p in phases) / len(phases) / 1e9 for role in "RK"]
            print(f"Block {block}, {group}: raw={times[0]:.3f}s switch-only={times[1]:.3f}s difference={times[1]-times[0]:+.3f}s")


if __name__ == "__main__":
    main()
