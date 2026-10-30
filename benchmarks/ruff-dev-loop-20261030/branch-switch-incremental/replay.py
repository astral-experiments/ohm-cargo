#!/usr/bin/env python3
"""Replay real Ruff branch switches with two complete Ohm SDKs on x86-64 Linux."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import shutil
from statistics import median
import subprocess
import sys
import time

A = "b5dba861cc38e3f7fb4524c9ceba3e01a474ea13"
B = "7b13f01ba1569887a25670820764b24c206da8e5"
BRANCH = {A: "historical-parent", B: "historical-feature"}

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def run(program, *, cwd, env, out, expected=0):
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.monotonic_ns()
    proc = subprocess.run(program, cwd=cwd, env=env, capture_output=True)
    elapsed = time.monotonic_ns() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    out.with_suffix(".stdout").write_bytes(proc.stdout)
    out.with_suffix(".stderr").write_bytes(proc.stderr)
    if proc.returncode != expected:
        raise RuntimeError(f"{program!r}: exit {proc.returncode}, see {out.with_suffix('.stderr')}")
    result = {"argv": list(map(str, program)), "exit": proc.returncode,
              "wall_s": elapsed / 1e9, "user_s": after.ru_utime - before.ru_utime,
              "sys_s": after.ru_stime - before.ru_stime}
    out.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n")
    return proc, result

def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--parent-sdk", type=Path, required=True)
    args.add_argument("--candidate-sdk", type=Path, required=True)
    args.add_argument("--out", type=Path, required=True, help="New directory for raw evidence and scratch")
    args.add_argument("--pairs", type=int, default=12, help="Even, counterbalanced sample size")
    args.add_argument("--jobs", type=int, default=4)
    args.add_argument("--workflow", choices=("build", "check", "test-no-run"), default="build")
    args.add_argument("--compiler-instructions", action="store_true",
                      help="Use complete Callgrind instruction counts for the two returning rustcs")
    args.add_argument("--pack", type=Path, help="Optional complete Git pack for the historical Ruff refs")
    args.add_argument("--ruff-url", default="https://github.com/astral-sh/ruff.git")
    args.add_argument("--offline", action="store_true", help="Use an already populated CARGO_HOME")
    a = args.parse_args()
    if a.pairs < 2 or a.pairs % 2 or a.jobs < 1:
        args.error("Choose an even number of at least two pairs and positive jobs.")
    kits = {k: p.resolve(strict=True) for k, p in (("P", a.parent_sdk), ("Q", a.candidate_sdk))}
    identity = {}
    for role, kit in kits.items():
        driver, = (kit / "lib").glob("librustc_driver*.so")
        identity[role] = {"cargo": digest(kit / "bin/cargo"), "rustc": digest(kit / "bin/rustc"),
                          "driver": digest(driver)}
    if identity["P"]["cargo"] != identity["Q"]["cargo"] or identity["P"]["rustc"] != identity["Q"]["rustc"] or identity["P"]["driver"] == identity["Q"]["driver"]:
        args.error("Supply matched Cargo and rustc launchers with distinct compiler drivers.")
    out = a.out.resolve()
    out.mkdir(mode=0o700)
    tracer = None
    if a.compiler_instructions:
        # Isolated Python omits the script's own directory from module lookup.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import compiler_counts
        tracer = compiler_counts.prepare(out)
    source = out / "ruff"
    subprocess.run(["git", "init", "--quiet", source], check=True)
    def git(*argv):
        return subprocess.check_output(["git", "-C", source, *argv])
    if a.pack:
        with a.pack.open("rb") as stream:
            subprocess.run(["git", "-C", source, "index-pack", "--stdin"], stdin=stream, check=True, stdout=subprocess.DEVNULL)
        (source / ".git/shallow").write_text(A + "\n")
    else:
        git("fetch", "--quiet", "--depth=2", a.ruff_url, B)
    assert git("rev-parse", B + "^").decode().strip() == A
    for rev, branch in BRANCH.items():
        git("branch", branch, rev)
    git("switch", "--quiet", BRANCH[A])
    target, shared = out / "target", out / "build"
    rustup = out / "rustup"
    (rustup / "toolchains").mkdir(parents=True)
    sel = rustup / "toolchains/ohm"
    # Rust records its physical sysroot in compiled outputs. Expose both drivers
    # through the same real directory for byte comparisons against cold builds.
    stable_kit = out / "sdk"
    shutil.copytree(kits["P"], stable_kit, symlinks=True)
    sel.symlink_to(stable_kit)
    std = Path("lib/rustlib/x86_64-unknown-linux-gnu/lib")
    def std_files(kit):
        return {f.name: digest(f) for f in (kit / std).iterdir() if f.is_file()}
    if std_files(kits["P"]) != std_files(kits["Q"]):
        args.error("The two compiler SDKs must use identical standard libraries.")
    installed_driver, = (stable_kit / "lib").glob("librustc_driver*.so")
    if not installed_driver.parent.resolve().is_relative_to(stable_kit):
        args.error("The copied SDK's lib directory must reside inside the private SDK.")

    env = os.environ | {"CARGO_TARGET_DIR": str(target), "CARGO_BUILD_BUILD_DIR": str(shared),
                        "RUSTUP_HOME": str(rustup), "RUSTUP_AUTO_INSTALL": "0", "LC_ALL": "C"}
    for name in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER",
                 "RUSTC", "CARGO_INCREMENTAL", "CARGO_UNSTABLE_OHM_DEFAULTS"):
        env.pop(name, None)
    subcommand = "test" if a.workflow == "test-no-run" else a.workflow
    cargo = ["cargo", "+ohm", subcommand, "-p", "ruff_python_parser"]
    if subcommand == "test":
        cargo.extend(["--lib", "--no-run"])
    cargo.append("--locked")
    if a.offline:
        cargo.append("--offline")
    cargo += [f"-j{a.jobs}", "--message-format=json"]
    orders = ["PQ", "QP"] * (a.pairs // 2)
    random.Random(0xc0ffee43).shuffle(orders)
    (out / "plan.json").write_text(json.dumps({"orders": orders, "sdk": identity, "A": A, "B": B,
                                              "workflow": a.workflow, "cargo": cargo,
                                              "compiler_instructions": a.compiler_instructions}, indent=2))
    phase_outputs = {}
    observed = {}
    src = (Path(__file__).resolve().parent / "consumer.rs").resolve(strict=True)

    def verify_metadata(artifacts, directory, size):
        dependencies = []
        metadata = {}
        for name in ("ruff_python_ast", "ruff_python_parser"):
            unit, = [x for x in artifacts if x["target"]["name"] == name and "lib" in x["target"]["kind"]]
            rmeta, = [Path(p) for p in unit["filenames"] if p.endswith(".rmeta")]
            metadata[name] = digest(rmeta)
            dependencies.extend(["--extern", f"{name}={rmeta}"])
        paths = {f.parent for folder in (target, shared) for f in folder.rglob("*.rmeta")}
        paths.update(Path(p).parent for x in artifacts for p in x["filenames"])
        for path in sorted(paths):
            dependencies.extend(["-L", "dependency=" + str(path)])
        probe = out / "probe.rs"
        for claimed in (64, 56):
            probe.write_text(f"use ruff_python_ast::Expr;\nconst _: [(); {claimed}] = [(); std::mem::size_of::<Expr>()];\n"
                             'pub fn parse() { let _ = ruff_python_parser::parse_module("x = 1"); }\n')
            cmd = ["rustc", "+ohm", "--edition=2024", "--crate-type=lib", "--emit=metadata", "--error-format=json",
                   probe, *dependencies, "-o", out / "probe.rmeta"]
            proc, _ = run(cmd, cwd=source, env=env, out=directory / f"type-{claimed}", expected=int(claimed != size))
            if claimed != size:
                assert any(msg.get("code") and msg["code"]["code"] == "E0308"
                           for msg in map(json.loads, proc.stderr.splitlines()))
        return metadata

    def verify_test_binary(artifacts, directory):
        unit, = [x for x in artifacts if x["target"]["name"] == "ruff_python_parser" and x["profile"]["test"]
                 and x.get("executable")]
        exe = Path(unit["executable"])
        listing, _ = run([exe, "--list", "--format", "terse"], cwd=source, env=env, out=directory / "inventory")
        tests = {line[:-6] for line in listing.stdout.decode().splitlines() if line.endswith(": test")}
        assert len(tests) == 245
        names = ["parser::tests::test_modes", "parser::tests::test_expr_mode_invalid_syntax1",
                 "lexer::indentation::tests::indentation_try_compare"]
        for i, name in enumerate(names):
            assert name in tests
            proc, _ = run([exe, "--exact", name, "--test-threads=1"], cwd=source,
                          env=env | {"INSTA_UPDATE": "no", "RUSTUP_TOOLCHAIN": "ohm"}, out=directory / f"test-{i}")
            assert b"1 passed;" in proc.stdout
        return exe, hashlib.sha256(listing.stdout).hexdigest()

    def build(directory, phase, rev, invalid=False):
        d = directory / phase
        d.mkdir()
        _, sw = run(["git", "switch", "--quiet", BRANCH[rev]], cwd=source, env=env, out=d / "switch")
        assert git("rev-parse", "HEAD").decode().strip() == rev
        counted = tracer is not None and phase.startswith("return-")
        program = compiler_counts.command(tracer, stable_kit, d, cargo) if counted else cargo
        proc, score = run(program, cwd=source, env=env, out=d / "cargo", expected=101 if invalid else 0)
        if counted:
            score["compiler_Ir"] = compiler_counts.read(d, proc.stderr, subcommand)
        rows = list(map(json.loads, proc.stdout.splitlines()))
        assert rows[-1] == {"reason": "build-finished", "success": not invalid}
        if invalid:
            assert any(x.get("message", {}).get("code") and x["message"]["code"]["code"] == "E0308"
                       and any("ohm_branch_switch_invalid" in y["text"] for span in x["message"]["spans"] for y in span["text"])
                       for x in rows)
            return
        artifacts = [x for x in rows if x["reason"] == "compiler-artifact"]
        dirty = sorted(x["target"]["name"] for x in artifacts if not x["fresh"])
        if phase.startswith("return-"):
            assert dirty == ["ruff_python_ast", "ruff_python_parser"], dirty
        if phase == "unchanged-B":
            assert not dirty, dirty
        size = 64 if rev == A else 56
        score.update(git_s=sw["wall_s"], dirty=dirty)
        if subcommand == "check":
            score["metadata"] = verify_metadata(artifacts, d, size)
            assert phase_outputs.setdefault(rev, size) == size
            score["expected_expr_size"] = size
            return score
        if subcommand == "test":
            exe, inventory = verify_test_binary(artifacts, d)
            product = (digest(exe), inventory)
            if rev not in phase_outputs:
                phase_outputs[rev] = product
                shutil.copy2(exe, out / ("clean-" + rev[:8] + ".elf"))
            assert phase_outputs[rev] == product, (phase, rev, phase_outputs[rev], product)
            score.update(ELF=product[0], inventory=inventory)
            return score
        argv = ["rustc", "+ohm", "--edition=2024", "--crate-name", "ohm_branch_reader", src]
        for name in ("ruff_python_ast", "ruff_python_parser"):
            unit, = [x for x in artifacts if x["target"]["name"] == name and "lib" in x["target"]["kind"]]
            lib, = [p for p in unit["filenames"] if p.endswith(".rlib")]
            argv.extend(["--extern", name + "=" + lib])
        dirs = {Path(name).parent for x in artifacts for name in x["filenames"]}
        for folder in (target, shared):
            for ext in ("*.rlib", "*.so"):
                dirs.update(f.parent for f in folder.rglob(ext))
        for path in sorted(dirs):
            argv.extend(["-L", "dependency=" + str(path)])
        for path in sorted({x["out_dir"] for x in rows if x.get("reason") == "build-script-executed" and x.get("out_dir")}):
            argv.extend(["-L", "native=" + path])
        elf = out / "reader"
        run([*argv, "-o", elf], cwd=source, env=env, out=d / "link-reader")
        reader, _ = run([elf], cwd=source, env=env, out=d / "run-reader")
        assert reader.stdout.decode().strip() == f"Expr={size} valid=1 rejected"
        h = digest(elf)
        if rev in phase_outputs:
            assert h == phase_outputs[rev], (phase, rev, h, phase_outputs[rev])
        else:
            phase_outputs[rev] = h
            shutil.copy2(elf, out / ("clean-" + rev[:8] + ".elf"))
        score["ELF"] = h
        return score
    def independent(role):
        source_driver, = (kits[role] / "lib").glob("librustc_driver*.so")
        temporary_driver = out / "driver.next"
        shutil.copy2(source_driver, temporary_driver)
        os.replace(temporary_driver, installed_driver)
        assert digest(installed_driver) == identity[role]["driver"]
        for name in ("cargo", "rustc"):
            p = subprocess.check_output(["rustup", "which", "--toolchain", "ohm", name], env=env, text=True).strip()
            assert Path(p).samefile(stable_kit / "bin" / name)
        for path in (target, shared):
            if path.exists():
                assert path.parent == out and not path.is_symlink()
                shutil.rmtree(path)
            path.mkdir()
    # Independent cold references provide separate, branch-specific correct outputs.
    for rev in (A, B):
        independent("P")
        d = out / ("reference-" + rev[:8])
        d.mkdir()
        build(d, "empty", rev)
    assert phase_outputs[A] != phase_outputs[B]
    for i, order in enumerate(orders, 1):
        for role in order:
            independent(role)
            d = out / f"pair-{i:02}-{role}"
            d.mkdir()
            result = {phase: build(d, phase, rev) for phase, rev in
                      [("empty-A", A), ("first-B", B), ("return-A", A), ("return-B", B), ("unchanged-B", B)]}
            if i == 1:
                f = source / "crates/ruff_python_parser/src/lib.rs"
                with f.open("ab") as stream:
                    stream.write(b"\nconst ohm_branch_switch_invalid: () = 1u32;\n")
                build(d, "invalid", B, invalid=True)
                git("restore", "--", str(f.relative_to(source)))
                build(d, "recovery", B)
            observed[(i, role)] = result
            (d / "results.json").write_text(json.dumps(result, indent=2) + "\n")
            print(f"Finished {i}/{a.pairs} {role}", flush=True)
    summary = {}
    for phase in ("return-A", "return-B"):
        def primary_score(pair, role):
            row = observed[pair, role][phase]
            return sum(row["compiler_Ir"].values()) if a.compiler_instructions else row["wall_s"]
        ratios = [primary_score(i, "P") / primary_score(i, "Q") for i in range(1, a.pairs + 1)]
        summary[phase] = {"paired_ratios": ratios, "median_speedup": median(ratios),
                          "metric": "summed rustc instructions" if a.compiler_instructions else "whole Cargo seconds"}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
if __name__ == "__main__":
    main()
