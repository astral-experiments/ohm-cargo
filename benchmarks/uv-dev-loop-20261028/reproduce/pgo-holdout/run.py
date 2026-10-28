#!/usr/bin/env python3
"""Build self-trained, matched Cargo PGO variants. Run only in a newly allocated scratch directory."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time

HOST = "x86_64-unknown-linux-gnu"
CARGO = "a0c7d08c898d3fdff992f2f431dec57d2486add2"
STACK = "94c95d6b8ef97b0e63e04b250bc88d1a388a31af"
RUST = "bfa236f639034f61ec884c15bd1f4e0b75e508ac"
PATCH = "ff2dcc74dfc56fb366422c29de08dc1baae4ec4efc91171069358b838177b795"
CASES = ["bitmaps-3.2.1", "diesel-2.2.10"]
INTERMEDIATES = {
    "unit": (
        264,
        "567b7d201b325e745d2dadd1553363b5c85f30d7",
        "03c3a2a7ba038effb33f88e77b2ff2103bf89b7e",
    ),
    "warnings": (
        267,
        "4246bb695caa5f713c7234b037512c5262b6891f",
        "a35a8fb01aad6b843e3122a9ec3a7c09bab6d41f",
    ),
    "feature": (
        268,
        "a3c13409c1d98f3e1072d86c1d968368feb90f9c",
        "2b0a957da1aec53b85884bd2b28f8b0a154b839c",
    ),
    "depfile": (
        269,
        "9256d6a21da8e6c0a2ba9502999d74544ed850cd",
        "adc3bcb2beef007159b7f1f12578dee0d24853a3",
    ),
    "semver": (270, STACK, "c9bc2498e72cba046f6d6c75996be717b37f7c57"),
}
ARM_COMMITS = {
    "base": CARGO,
    "guard": CARGO,
    "stack": STACK,
    "guard-stack": STACK,
    **{arm: data[1] for arm, data in INTERMEDIATES.items()},
}
parser = argparse.ArgumentParser(description=__doc__)
for flag in (
    "scratch",
    "materials",
    "cargo-repo",
    "toolchain",
    "std-patch",
    "seed-home",
):
    parser.add_argument("--" + flag, required=True, type=lambda p: Path(p).resolve())
parser.add_argument(
    "--arms",
    nargs="+",
    choices=ARM_COMMITS,
    default=["base", "guard-stack"],
)
parser.add_argument("--jobs", type=int, default=8)
parser.add_argument(
    "--training-seed",
    type=lambda p: Path(p).resolve(),
    help="reuse a complete pinned registry seed and verify offline",
)
parser.add_argument(
    "--intermediate-output",
    type=lambda p: Path(p).resolve(),
    help="append new clean source arms at the verified endpoint run's build paths, storing receipts separately",
)
a = parser.parse_args()
lab = a.scratch
assert 1 <= a.jobs <= 8 and len(set(a.arms)) == len(a.arms)
suite = a.intermediate_output or lab
if a.intermediate_output:
    assert (
        a.arms == list(INTERMEDIATES)
        and set(os.sched_getaffinity(0)) == set(range(16))
        and a.jobs == 8
    )
    endpoints = json.loads((lab / "audit.json").read_text())["arms"]
    assert set(endpoints) == {"base", "guard-stack"}
    for arm, result in endpoints.items():
        assert (
            sha256((lab / "bin" / arm).read_bytes()).hexdigest()
            == result["cargo_sha256"]
        )
    for transient in (
        "target",
        "cargo-src",
        "raw",
        "merged.profdata",
        "train-home",
        "training-src",
        "training-target",
    ):
        assert not (lab / transient).exists(), transient
    assert (lab / "library/std/src/path.rs").read_bytes() == (
        a.toolchain / "lib/rustlib/src/rust/library/std/src/path.rs"
    ).read_bytes()
    for pr, commit, tree in INTERMEDIATES.values():
        assert (
            subprocess.check_output(
                ["git", "-C", a.cargo_repo, "rev-parse", commit + "^{tree}"], text=True
            ).strip()
            == tree
        )
suite.mkdir(parents=True, exist_ok=bool(a.intermediate_output))
assert not any(
    (suite / name).exists()
    for name in ("records", "bin", "recipe", "provenance.json", "commands.jsonl")
)
records = suite / "records"
records.mkdir()
bins = suite / "bin"
bins.mkdir()
tool = a.toolchain / "bin"
prof = a.materials / "llvm-profdata"
wrapper = Path(__file__).with_name("wrap-rustc.py").resolve()
assert sha256(a.std_patch.read_bytes()).hexdigest() == PATCH
assert CARGO in subprocess.check_output(
    [tool / "cargo", "-Vv"], text=True
) and RUST in subprocess.check_output([tool / "rustc", "-Vv"], text=True)
assert "23.1.1" in subprocess.check_output([prof, "--version"], text=True)
(profiler,) = list(
    (a.toolchain / "lib/rustlib" / HOST / "lib").glob("libprofiler_builtins-*.rlib")
)
provenance = json.loads((a.materials / "provenance.json").read_text())
assert provenance["rustc_perf_commit"] == "0a054b0ead56e41a4584bfab6fdc1a5fad2aedc3"
(suite / "provenance.json").write_text(
    json.dumps(
        dict(
            provenance,
            arms=a.arms,
            jobs=a.jobs,
            cargo=CARGO,
            stack=STACK,
            rust=RUST,
            std_patch=PATCH,
            profiler=str(profiler),
            materials=str(a.materials),
            stable_build_paths=str(lab),
            cpu_affinity=sorted(os.sched_getaffinity(0)),
            source_commits={arm: ARM_COMMITS[arm] for arm in a.arms},
            reference_run=str(lab) if a.intermediate_output else None,
            argv=os.sys.argv,
        ),
        indent=2,
    )
    + "\n"
)

# Deliberately give both builds and both training hosts the same stable absolute
# paths, and reconstruct the latter's cache once per arm from the same seed.
common = {
    k: v
    for k, v in os.environ.items()
    if k
    not in {
        "RUSTC_WRAPPER",
        "RUSTC_WORKSPACE_WRAPPER",
        "RUSTFLAGS",
        "CARGO_ENCODED_RUSTFLAGS",
        "LLVM_PROFILE_FILE",
        "CARGO_BUILD_RUSTFLAGS",
        "CARGO_BUILD_TARGET",
        "CARGO_INCREMENTAL",
        "RUSTDOCFLAGS",
        "CARGO_ENCODED_RUSTDOCFLAGS",
    }
    and not k.startswith(("CARGO_PROFILE_", "CARGO_TARGET_", "CARGO_UNSTABLE_", "OHM_"))
}
common.update(
    RUSTC=str(tool / "rustc"),
    RUSTDOC=str(tool / "rustdoc"),
    PATH=str(tool) + ":" + common["PATH"],
    CARGO_TERM_COLOR="never",
)


def run(cmd, log, *, env=common, cwd=lab, stdin=None):
    cmd = list(map(str, cmd))
    start = time.time()
    with (suite / "commands.jsonl").open("a") as f:
        f.write(
            json.dumps(
                {
                    "start": start,
                    "cwd": str(cwd),
                    "command": shlex.join(cmd),
                    "log": str(log),
                }
            )
            + "\n"
        )
    with Path(log).open("ab") as f:
        p = subprocess.run(
            cmd, cwd=cwd, env=env, stdin=stdin, stdout=f, stderr=subprocess.STDOUT
        )
    with (suite / "commands.jsonl").open("a") as f:
        f.write(
            json.dumps(
                {
                    "finish": time.time(),
                    "elapsed_s": round(time.time() - start, 2),
                    "status": p.returncode,
                    "log": str(log),
                }
            )
            + "\n"
        )
    if p.returncode:
        raise SystemExit(f"command failed ({p.returncode}), see {log}")


def copytree(src, dst):
    assert not dst.exists()
    subprocess.run(["cp", "-a", "--reflink=auto", src, dst], check=True)


def export_cargo(commit):
    assert not (lab / "cargo-src").exists()
    (lab / "cargo-src").mkdir()
    with subprocess.Popen(
        ["git", "-C", a.cargo_repo, "archive", commit], stdout=subprocess.PIPE
    ) as git:
        subprocess.run(
            ["tar", "-xf", "-", "-C", lab / "cargo-src"], stdin=git.stdout, check=True
        )
        assert git.wait() == 0
    # Keep user-visible version strings identical, as in the previous matched builds.
    metadata = subprocess.check_output(
        [
            "git",
            "-C",
            a.cargo_repo,
            "show",
            "-s",
            "--abbrev=9",
            "--format=%H%n%h%n%cs",
            CARGO,
        ]
    )
    (lab / "cargo-src/git-commit-info").write_bytes(metadata)


def cargo_env(phase, trace):
    if a.intermediate_output:
        assert wrapper.read_bytes() == (suite / "recipe/wrap-rustc.py").read_bytes()
    return dict(
        common,
        CARGO_HOME=str(lab / "build-home"),
        CARGO_TARGET_DIR=str(lab / "target"),
        __CARGO_TESTS_ONLY_SRC_ROOT=str(lab / "library"),
        RUSTC_WRAPPER=str(wrapper),
        OHM_HOLDOUT_ROOT=str(lab),
        OHM_HOLDOUT_PHASE=phase,
        OHM_HOLDOUT_TRACE=str(trace),
        OHM_HOLDOUT_PROFILER=str(profiler),
        CARGO_PROFILE_RELEASE_LTO="thin",
        CARGO_PROFILE_RELEASE_CODEGEN_UNITS="1",
        CARGO_PROFILE_RELEASE_OPT_LEVEL="3",
        CARGO_PROFILE_RELEASE_INCREMENTAL="false",
        CARGO_PROFILE_RELEASE_DEBUG="false",
        CARGO_PROFILE_RELEASE_DEBUG_ASSERTIONS="false",
        CARGO_PROFILE_RELEASE_OVERFLOW_CHECKS="false",
        LIBZ_SYS_STATIC="1",
        CFG_RELEASE="1.99.0-dev",
        CFG_RELEASE_CHANNEL="dev",
        CFG_VER_DESCRIPTION="ohm-1.99.0-17",
    )


def build(src, dest, phase, crate, extra):
    assert not (lab / "target").exists()
    trace = dest / (phase + ".units.jsonl")
    env = cargo_env(phase, trace)
    run(
        [
            tool / "cargo",
            "-Zohm-defaults=no",
            "-Zbuild-std",
            "build",
            "--target",
            HOST,
            "--release",
            "--offline",
            "--locked",
            "-j",
            a.jobs,
            *extra,
        ],
        dest / (phase + ".build.log"),
        env=env,
        cwd=src,
    )
    units = [json.loads(line) for line in trace.read_text().splitlines()]
    assert any(u[0] == crate and u[2] for u in units), units[-5:]
    assert any(u[0] == "std" and u[1] == HOST and not u[2] for u in units)
    assert all(
        not u[2]
        for u in units
        if u[0] in {"std", "core", "alloc", "profiler_builtins", "compiler_builtins"}
        or u[1] is None
    )
    target = lab / "target"
    binary = dest / (phase + ".bin")
    shutil.copy2(target / HOST / "release" / crate.replace("_", "-"), binary)
    # Fresh target needed because Cargo excludes std source paths from freshness.
    target.rename(dest / (phase + ".target"))
    return binary


def merge(dest, needle):
    raw = list((lab / "raw").glob("*.profraw"))
    assert raw, "instrumented training wrote no profiles"
    run([prof, "merge", "-o", lab / "merged.profdata", lab / "raw"], dest / "merge.log")
    run([prof, "show", "--covered", lab / "merged.profdata"], dest / "covered.txt")
    with (dest / "covered.txt").open() as f:
        count = sum(needle in l for l in f)
    assert count > 0, (needle, "has zero covered functions")
    (dest / "profile-info.json").write_text(
        json.dumps(
            {
                "raw_files": len(raw),
                "bytes": sum(p.stat().st_size for p in raw),
                "covered_symbol_matches": count,
                "profdata_sha256": sha256(
                    (lab / "merged.profdata").read_bytes()
                ).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )


def training(driver, dest):
    copytree(lab / "seed-home", lab / "train-home")
    copytree(a.materials / "corpus", lab / "training-src")
    for case in CASES:
        src = lab / "training-src" / case
        for label, args in [
            ("check", ["check"]),
            ("debug", ["build"]),
            ("opt", ["build", "--release"]),
        ]:
            env = dict(
                common,
                CARGO_HOME=str(lab / "train-home"),
                CARGO_UNSTABLE_OHM_LINKER="lld",
                LLVM_PROFILE_FILE=str(lab / "raw/%m_%p.profraw"),
            )

            def trial(stage, incremental):
                target = (
                    lab
                    / "training-target"
                    / case
                    / label
                    / ("incr" if incremental else "full")
                )
                run(
                    [driver, *args, "--lib", "--locked", "--offline", "-j", a.jobs],
                    dest / (f"train.{case}.{label}.{stage}.log"),
                    env=dict(
                        env,
                        CARGO_TARGET_DIR=str(target),
                        CARGO_INCREMENTAL=str(int(incremental)),
                    ),
                    cwd=src,
                )

            trial("full", False)
            trial("incr-full", True)
            trial("warm", True)
            with (src / "0-println.patch").open("rb") as inp:
                run(
                    ["patch", "--forward", "--fuzz=0", "-p1"],
                    dest / "training-patches.log",
                    stdin=inp,
                    cwd=src,
                )
            trial("incr-patched", True)
            with (src / "0-println.patch").open("rb") as inp:
                run(
                    ["patch", "--reverse", "--fuzz=0", "-p1"],
                    dest / "training-patches.log",
                    stdin=inp,
                    cwd=src,
                )
    for name in ("train-home", "training-src", "training-target"):
        (lab / name).rename(dest / name)


if a.intermediate_output:
    # All app/std targets are clean for each phase, just like the completed
    # endpoints. Reuse verified source, smoke receipts and registry snapshots.
    assert (lab / "records/probe/ran-use.log").read_bytes() == b"19\n"
    assert (lab / "seed-home/registry").is_dir() and (
        lab / "build-home/registry"
    ).is_dir()
    frozen = suite / "recipe"
    frozen.mkdir()
    for filename in (
        "run.py",
        "wrap-rustc.py",
        "audit.py",
        "start-intermediates.sh",
        "INTERMEDIATES.md",
    ):
        shutil.copy2(Path(__file__).with_name(filename), frozen / filename)
    (frozen / "SHA256SUMS").write_text(
        "".join(
            sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n"
            for p in sorted(frozen.iterdir())
        )
    )
else:
    copytree(a.seed_home, lab / "build-home")
    copytree(a.toolchain / "lib/rustlib/src/rust/library", lab / "library")
    # Fetch with the uninstrumented release before snapshotting either training cache.
    if a.training_seed:
        copytree(a.training_seed, lab / "seed-home")
    else:
        (lab / "seed-home").mkdir()
    prep = dict(common, CARGO_HOME=str(lab / "seed-home"))
    for case in CASES:
        run(
            [
                tool / "cargo",
                "fetch",
                "--locked",
                "--target",
                HOST,
                *(["--offline"] if a.training_seed else []),
            ],
            lab / "prefetch.log",
            env=prep,
            cwd=a.materials / "corpus" / case,
        )
    # Verify raw format, standard-graph exclusion, profiling runtime, real covered
    # symbols and final profile consumption before paying for Cargo's ThinLTO.
    probe = lab / "probe"
    (probe / "src").mkdir(parents=True)
    (probe / "Cargo.toml").write_text(
        '[package]\nname="pgo-probe"\nversion="0.0.0"\nedition="2024"\n'
    )
    (probe / "src/main.rs").write_text(
        'fn main() { println!("{}", std::hint::black_box(19)); }\n'
    )
    (probe / "Cargo.lock").write_text(
        'version = 4\n[[package]]\nname = "pgo-probe"\nversion="0.0.0"\n'
    )
    (lab / "raw").mkdir()
    smoke = records / "probe"
    smoke.mkdir()
    g = build(probe, smoke, "generate", "pgo_probe", [])
    run(
        [g],
        smoke / "ran-probe.log",
        env=dict(common, LLVM_PROFILE_FILE=str(lab / "raw/%m_%p.profraw")),
    )
    merge(smoke, "pgo_probe")
    u = build(probe, smoke, "use", "pgo_probe", [])
    run([u], smoke / "ran-use.log")
    for name in ("raw", "merged.profdata"):
        (lab / name).rename(smoke / name)
for arm in a.arms:
    dest = records / arm
    dest.mkdir()
    (lab / "raw").mkdir()
    commit = ARM_COMMITS[arm]
    export_cargo(commit)
    guarded = arm in {"guard", "guard-stack"}
    if guarded:
        with a.std_patch.open("rb") as inp:
            run(
                ["patch", "--forward", "--fuzz=0", "-p1"],
                dest / "std-patch.log",
                stdin=inp,
            )
    (dest / "source.txt").write_text(
        f'Cargo {commit}\nStd {RUST}\nGuard patch {PATCH if guarded else "none"}\n'
    )
    flags = ["--bin", "cargo", "--features", "ohm-defaults,all-static"]
    g = build(lab / "cargo-src", dest, "generate", "cargo", flags)
    training(g, dest)
    merge(dest, "_5cargo")
    profile_path = lab / "merged.profdata"
    profile_hash = sha256(profile_path.read_bytes()).hexdigest()
    assert (
        profile_hash
        == json.loads((dest / "profile-info.json").read_text())["profdata_sha256"]
    )
    (dest / "use-profile-input.json").write_text(
        json.dumps(
            {
                "path": str(profile_path),
                "sha256": profile_hash,
                "source_commit": commit,
            },
            indent=2,
        )
        + "\n"
    )
    u = build(lab / "cargo-src", dest, "use", "cargo", flags)
    assert sha256(profile_path.read_bytes()).hexdigest() == profile_hash
    pending = bins / ("." + arm + ".pending")
    shutil.copy2(u, pending)
    version = subprocess.check_output([u, "-Vv"], env=common, text=True)
    assert CARGO in version
    (dest / "driver.txt").write_text(
        version
        + "\n"
        + sha256(u.read_bytes()).hexdigest()
        + "  "
        + arm
        + "\n"
        + subprocess.check_output(["ldd", u], text=True)
    )
    for name in ("raw", "merged.profdata", "cargo-src"):
        (lab / name).rename(dest / name)
    if guarded:
        with a.std_patch.open("rb") as inp:
            run(
                ["patch", "--reverse", "--fuzz=0", "-p1"],
                dest / "std-patch.log",
                stdin=inp,
            )
    if a.intermediate_output:
        # The consumer sees this executable only after checking its source,
        # profile, std, unit graph, 24 training invocations, and content hash.
        checked = subprocess.check_output(
            [
                os.sys.executable,
                suite / "recipe/audit.py",
                suite,
                a.cargo_repo,
                "--pending",
                "--arms",
                arm,
            ],
            text=True,
        )
        (dest / "audit.json").write_text(checked)
        ready = json.loads(checked)["arms"][arm]
        ready.update(
            arm=arm,
            pull_request=INTERMEDIATES[arm][0],
            cargo_tree=INTERMEDIATES[arm][2],
            rust_commit=RUST,
            std_patch=None,
            jobs=a.jobs,
            cpus=sorted(os.sched_getaffinity(0)),
            binary=str(bins / arm),
        )
        (dest / "ready.pending.json").write_text(json.dumps(ready, indent=2) + "\n")
        pending.replace(bins / arm)
        (dest / "ready.pending.json").replace(dest / "ready.json")
    else:
        pending.replace(bins / arm)
    print("finished", arm, dest / "driver.txt", flush=True)
