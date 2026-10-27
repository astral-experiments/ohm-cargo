"""Run the sealed Cargo companion on the H2 workspace after the main native study."""

import argparse
import csv
import fcntl
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    CARGO_HOME,
    FROZEN,
    MATCH_FILE,
    NEEDLE,
    P,
    PIN,
    PLAN,
    REPLACEMENT,
    RUFF,
    SHARED,
    SONAME,
    TARGET,
    compare_elf,
    dump,
    git,
    load,
    need,
    sha,
)
from observer import setup

HERE = Path(__file__).resolve().parent
PARENT_SHA = "529813f90cdd7c369e347701f8c4497edc5dad8adcc44b58301661fd4b786c4a"
CANDIDATE_SHA = "dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1"
PLAN_SHA = "8d44341636a908d4cde32fc1e4f37a391aa67e879298516855bd85230447b8e0"


def guard_free(path):
    need(shutil.disk_usage(path).free >= 25 * 1024**3, ("below 25 GiB reserve", path))


def setup_registry(private):
    # Clone only Cargo inputs, keeping mutable SQLite, locks, compiled caches and fingerprints private.
    private.mkdir()
    names = []
    for name in ["config", "config.toml", "registry", "git"]:
        src = CARGO_HOME / name
        if src.exists():
            subprocess.run(["cp", "-a", "--reflink=auto", "--", src.resolve(), private / name], check=True)
            names.append(name)
    need("registry" in names, "offline registry absent")
    return names


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--driver-sha", required=True)
    cli.add_argument("--compiler-commit", required=True)
    cli.add_argument("--parent-cargo", type=Path, required=True)
    cli.add_argument("--candidate-cargo", type=Path, required=True)
    cli.add_argument("--driver", type=Path, required=True)
    cli.add_argument(
        "--run", type=Path, required=True, help="New H2 output and state directory, on the home filesystem"
    )
    args = cli.parse_args()
    driver_sha = args.driver_sha
    need(
        re.fullmatch("[a-f0-9]{64}", driver_sha) is not None
        and re.fullmatch("[a-f0-9]{40}", args.compiler_commit) is not None,
        "expected pinned SHA-256 driver and 40-digit compiler commit",
    )
    envbad = {
        k
        for k in os.environ
        if k
        in {
            "RUSTFLAGS",
            "RUSTC",
            "RUSTC_WRAPPER",
            "RUSTC_WORKSPACE_WRAPPER",
            "RUSTC_LOG",
            "RUSTC_BOOTSTRAP",
            "CARGO_ENCODED_RUSTFLAGS",
            "CARGO_INCREMENTAL",
            "CARGO_BUILD_RUSTFLAGS",
            "CARGO_BUILD_RUSTC_WRAPPER",
            "CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER",
            "CARGO_BUILD_RUSTC",
            "CARGO_BUILD_TARGET",
            "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER",
            "RUSTUP_TOOLCHAIN",
        }
        or k.startswith(("WILD_", "CARGO_PROFILE_"))
    }
    need(not envbad, ["unscheduled overrides", envbad])
    need(not sys.flags.optimize, "do not elide assertions")
    sources = {"parent": args.parent_cargo.resolve(), "candidate": args.candidate_cargo.resolve()}
    hashes = {"parent": PARENT_SHA, "candidate": CANDIDATE_SHA}
    driver = args.driver.resolve()
    where = args.run.resolve()
    need(
        where.parent.exists() and where.parent.stat().st_dev == Path.home().stat().st_dev,
        "use the independent H2 home filesystem",
    )
    need(sha(PLAN) == PLAN_SHA, "changed registered plan")
    plan = load(PLAN)
    spec = plan["cargo_companion_support"]
    need(args.compiler_commit == plan["compiler_commit"] and driver_sha == plan["compiler_driver"], "incorrect compiler")
    need(spec["control_cargo"] == PARENT_SHA and plan["pin"] == PIN, plan)

    def subjects():
        need(
            all(sha(sources[a]) == hashes[a] for a in sources) and sha(driver) == driver_sha,
            "subject sha256 mismatch",
        )

    def verify_source():
        for line in (HERE / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ", 1)
            need(Path(name).name == name and sha(HERE / name) == digest, ("harness checksum mismatch", name))

    def source_ok():
        return git("rev-parse", "HEAD") == PIN and not git("status", "--porcelain")

    def call(arm, mode, phase, *extra, observer=False):
        guard_free(where)
        st = where / "state" / mode / arm
        out = where / mode / arm / phase
        wrap = [
            "bwrap",
            "--ro-bind",
            "/",
            "/",
            "--proc",
            "/proc",
            "--dev-bind",
            "/dev",
            "/dev",
            "--bind",
            "/tmp",
            "/tmp",
            "--bind",
            str(where),
            str(where),
            "--bind",
            str(P / "rustup"),
            str(P / "rustup"),
        ]
        for src, dest in [
            (st / "target", TARGET),
            (st / "shared", SHARED),
            (st / "registry-home", CARGO_HOME),
        ]:
            wrap += ["--bind", str(src), str(dest)]
        for src, dest in [(sources[arm], FROZEN / "bin/cargo"), (driver, FROZEN / "lib" / SONAME)]:
            wrap += ["--ro-bind", str(src), str(dest)]
        if phase in {"edit", "restore", "restored-noop"}:
            version = st / ("helper.edited.rs" if phase == "edit" else "helper.restored.rs")
            if phase != "restored-noop":
                version.write_bytes(original.replace(NEEDLE, REPLACEMENT) if phase == "edit" else original)
                # New materialized files give Cargo ordinary filesystem edit/restore freshness.
            wrap += ["--ro-bind", str(version), str(MATCH_FILE)]
        script = [
            sys.executable,
            "-B",
            str(HERE / "worker.py"),
            str(out),
            mode,
            phase,
            arm,
            hashes[arm],
            driver_sha,
            *extra,
        ]
        if observer:
            script = [
                sys.executable,
                "-B",
                str(HERE / "observer.py"),
                str(where / "canonical-observer"),
                str(out),
                arm,
            ]
            wrap += ["--bind", str(st / "observer-source"), str(where / "canonical-observer")]
        subprocess.run([*wrap, "--", "taskset", "-c", "0-23", *script], check=True)

    lockpath = P / "native-measure.lock"
    with lockpath.open("a") as lock:
        print("Waiting for H2 native-measure.lock", flush=True)
        fcntl.flock(lock, fcntl.LOCK_EX)
        verify_source()
        subjects()
        guard_free(where.parent)
        need(source_ok(), "Ruff must be on the clean pinned commit")
        where.mkdir()
        (where / "canonical-observer").mkdir()
        index = Path(git("rev-parse", "--path-format=absolute", "--git-path", "index"))
        index_sha = sha(index)
        original = MATCH_FILE.read_bytes()
        need(original.count(NEEDLE) == 1 and len(NEEDLE) == len(REPLACEMENT), "unexpected matcher")
        receipt = dict(
            ruff=PIN,
            index=index_sha,
            plan=PLAN_SHA,
            compiler_commit=args.compiler_commit,
            preregistered_compiler_source=plan["compiler_commit"],
            cpu="0-23",
            jobs=8,
            lock=str(lockpath),
            subject_paths={k: str(p) for k, p in sources.items()},
            cargo=hashes,
            driver=driver_sha,
            driver_path=str(driver),
            helper=sha(MATCH_FILE),
            cargo_source=spec["candidate_cargo"],
            store_layout="empty per endpoint and arm; independent mutable registry, target, shared-build",
            canonical_roots=[str(RUFF), str(TARGET), str(SHARED), str(CARGO_HOME), str(FROZEN)],
            affinity=sorted(os.sched_getaffinity(0)),
            machine=os.uname()._asdict() if hasattr(os.uname(), "_asdict") else list(os.uname()),
            source_files={p.name: sha(p) for p in HERE.iterdir() if p.is_file()},
        )
        dump(where / "subjects.json", receipt)
        shutil.copyfile(PLAN, where / "plan.json")
        for mode, ep in ((k, spec[k]) for k in ("build", "test")):
            for arm in sources:
                st = where / "state" / mode / arm
                (st / "target").mkdir(parents=True)
                (st / "shared").mkdir()
                (where / mode / arm).mkdir(parents=True)
                guard_free(where)
                setup_registry(st / "registry-home")
                for phase in ("cold", "training", "preflight"):
                    call(arm, mode, phase)
                print(
                    mode,
                    arm,
                    "preflight",
                    load(where / mode / arm / "preflight/receipt.json")["rustc"],
                    flush=True,
                )
            before = {a: load(where / mode / a / "preflight/receipt.json") for a in sources}
            diffs = {}
            for arm in sources:
                c = load(where / mode / arm / "cold/receipt.json")
                need(
                    all(
                        c[k] == before[arm][k]
                        for k in ("roster", "executables", "diagnostics", "compiler_messages")
                    ),
                    ("cold/warm outputs", mode, arm),
                )
                diffs[arm + "-cold-preflight"] = compare_elf(c["elf"], before[arm]["elf"])
            need(
                all(
                    before["parent"][k] == before["candidate"][k]
                    for k in ("roster", "executables", "diagnostics", "compiler_messages")
                ),
                ("cross-arm products", mode),
            )
            diffs["between-arms-preflight"] = compare_elf(before["parent"]["elf"], before["candidate"]["elf"])
            dump(where / mode / "preflight-elf.json", diffs)
            with (where / mode / "observations.csv").open("x", newline="") as stream:
                rows = csv.writer(stream)
                rows.writerow(["pair", "slot", "arm", "elapsed_ns"])
                for pair, order in enumerate(ep["orders"], 1):
                    for slot, arm in enumerate(order, 1):
                        phase = f"pair-{pair:02}"
                        call(
                            arm,
                            mode,
                            phase,
                            "--reference",
                            str(where / mode / arm / "preflight/receipt.json"),
                        )
                        raw = load(where / mode / arm / phase / "receipt.json")
                        rows.writerow([pair, slot, arm, raw["elapsed_ns"]])
                        stream.flush()
                    print(mode, pair, "/".join(order), flush=True)
            for arm in sources:
                call(arm, mode, "final")
                raw = load(where / mode / arm / "final/receipt.json")
                need(
                    all(
                        raw[k] == before[arm][k]
                        for k in (
                            "roster",
                            "executables",
                            "diagnostics",
                            "compiler_messages",
                            "dirty",
                            "rustc",
                            "linkers",
                        )
                    ),
                    ("preflight/final witness changed", mode, arm),
                )
                diffs[arm + "-final"] = compare_elf(before[arm]["elf"], raw["elf"])
            dump(where / mode / "no-op-elf.json", diffs)
        for mode in ("build", "test"):
            result = {}
            for arm in sources:
                initial = load(where / mode / arm / "preflight/receipt.json")
                for phase in ("edit", "restore", "restored-noop"):
                    call(arm, mode, phase)
                    current = load(where / mode / arm / phase / "receipt.json")
                    need(
                        current["roster"] == initial["roster"]
                        and current["executables"] == initial["executables"],
                        ("functional roster", mode, arm, phase),
                    )
                    need(
                        current["compiler_messages"] == initial["compiler_messages"],
                        ("functional warnings", mode, arm, phase),
                    )
                    if phase == "edit":
                        need(
                            current["diagnostics"] != initial["diagnostics"]
                            and current["rustc"]
                            and current["linkers"]
                            and current["elf"][current["ruff"]]["raw"]
                            != initial["elf"][initial["ruff"]]["raw"],
                            ("genuine edit absorbed", mode, arm),
                        )
                    else:
                        need(
                            current["diagnostics"] == initial["diagnostics"],
                            ("restore diagnostics", mode, arm),
                        )
                        result[arm + "-" + phase] = compare_elf(initial["elf"], current["elf"])
            for phase in ("edit", "restore", "restored-noop"):
                a, b = [load(where / mode / k / phase / "receipt.json") for k in sources]
                need(a["diagnostics"] == b["diagnostics"], ("cross-arm behavior", mode, phase))
                result[phase + "-between-arms"] = compare_elf(a["elf"], b["elf"])
            dump(where / mode / "functional-elf.json", result)
        for arm in sources:
            setup(where / "state" / "build" / arm / "observer-source")
            call(arm, "build", "span-observer", observer=True)
        osum = {a: load(where / "build" / a / "span-observer/summary.json") for a in sources}
        need(
            {s: v["value"] for s, v in osum["parent"].items()}
            == {s: v["value"] for s, v in osum["candidate"].items()},
            "observed proc macro output differs between arms",
        )
        verify_source()
        subjects()
        need(
            source_ok() and sha(index) == index_sha and MATCH_FILE.read_bytes() == original,
            "source integrity failed",
        )
        dump(where / "complete.json", dict(source_clean=True, index_sha=index_sha, matched_subjects=True))
        subprocess.run([sys.executable, "-B", HERE / "analyze.py", where], check=True)


if __name__ == "__main__":
    main()
