#!/usr/bin/env python3
"""Verify the retained compiler scope, frozen source trees and linked static std for each PGO arm."""
import argparse
from collections import Counter
import hashlib
import json
import re
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("run", type=Path)
parser.add_argument("cargo_repo", type=Path)
parser.add_argument(
    "--arms", nargs="+", help="audit already completed source arms only"
)
parser.add_argument(
    "--pending",
    action="store_true",
    help="verify a staged unsuffixed source arm before its final binary is published",
)
args = parser.parse_args()
root = args.run.resolve()
provenance = json.loads((root / "provenance.json").read_text())
base, stack = provenance["cargo"], provenance["stack"]
endpoint_root = Path(provenance.get("reference_run") or root)
endpoint_audit = (
    json.loads((endpoint_root / "audit.json").read_text())["arms"]["base"]
    if endpoint_root != root
    else None
)
changed = subprocess.check_output(
    ["git", "-C", args.cargo_repo, "diff", "--name-only", base, stack], text=True
).splitlines()
assert changed


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


summary = {
    "probe": json.loads(
        (endpoint_root / "records/probe/profile-info.json").read_text()
    ),
    "arms": {},
}
assert (
    (endpoint_root / "records/probe/ran-probe.log").read_bytes()
    == (endpoint_root / "records/probe/ran-use.log").read_bytes()
    == b"19\n"
)
reference = None
argv = provenance["argv"]
materials = Path(
    provenance.get("materials") or argv[argv.index("--materials") + 1]
).resolve()
corpus = materials / "corpus"
original = {p.relative_to(corpus): digest(p) for p in corpus.rglob("*") if p.is_file()}
assert len(original) == 270
outcomes = [json.loads(s) for s in (root / "commands.jsonl").open()]
training_backups = None
selected = args.arms or provenance["arms"]
assert set(selected) <= set(provenance["arms"])
for arm in selected:
    dest = root / "records" / arm
    commit = provenance.get("source_commits", {}).get(
        arm, stack if arm in {"stack", "guard-stack"} else base
    )
    binary = root / "bin" / (("." + arm + ".pending") if args.pending else arm)
    for path in changed:
        assert (dest / "cargo-src" / path).read_bytes() == subprocess.check_output(
            ["git", "-C", args.cargo_repo, "show", commit + ":" + path]
        ), (arm, path)
    arm_summary = json.loads((dest / "profile-info.json").read_text())
    arm_summary.update(
        cargo_commit=commit,
        cargo_files_verified=changed,
        cargo_sha256=digest(binary),
    )
    assert arm_summary["profdata_sha256"] == digest(dest / "merged.profdata")
    raw_files = sorted((dest / "raw").glob("*.profraw"))
    assert (
        len(raw_files) == arm_summary["raw_files"]
        and sum(f.stat().st_size for f in raw_files) == arm_summary["bytes"]
    )
    with tempfile.TemporaryDirectory() as temporary:
        reproduced = Path(temporary) / "remerged.profdata"
        subprocess.run(
            [materials / "llvm-profdata", "merge", "-o", reproduced, dest / "raw"],
            check=True,
        )
        assert digest(reproduced) == arm_summary["profdata_sha256"], (
            arm,
            "raw profiles do not reproduce the retained profile",
        )
    arm_summary["remerged_raw_profiles"] = len(raw_files)
    assert arm_summary["raw_files"] >= 24 and arm_summary["covered_symbol_matches"] > 0
    assert arm_summary["cargo_sha256"] == digest(dest / "use.bin")
    expected_logs = {
        f"train.{name}.{mode}.{scenario}.log"
        for name in provenance["training_trees"]
        for mode in ("check", "debug", "opt")
        for scenario in ("full", "incr-full", "warm", "incr-patched")
    }
    completed = [
        r
        for r in outcomes
        if "status" in r
        and Path(r["log"]).parent == dest
        and Path(r["log"]).name.startswith("train.")
    ]
    assert len(completed) == len(expected_logs) == 24
    assert all(r["status"] == 0 for r in completed)
    assert {Path(r["log"]).name for r in completed} == expected_logs
    restored = dest / "training-src"
    files = {
        p.relative_to(restored): digest(p) for p in restored.rglob("*") if p.is_file()
    }
    assert all(files.get(p) == checksum for p, checksum in original.items())
    # Applying the pinned bitmaps patch at its one-line offset makes GNU patch
    # save a backup. Verify exactly the same training inputs and backup in both arms.
    extras = {str(p): value for p, value in files.items() if p not in original}
    assert set(extras) == {"bitmaps-3.2.1/src/bitmap.rs.orig"}
    assert training_backups is None or extras == training_backups
    training_backups = extras
    arm_summary.update(
        training_commands_verified=len(completed),
        frozen_training_files_verified=len(original),
        patch_backups=extras,
    )
    lib_checksums = []
    for phase in ("generate", "use"):
        units = [json.loads(line) for line in (dest / (phase + ".units.jsonl")).open()]
        assert all(row[3] == phase for row in units)
        # autocfg 1.5.0 assigns a fresh random 16-hex UUID to its temporary
        # Rust language probes. Neither probe is a linkable product crate.
        graph = Counter(
            (
                re.sub(r"^autocfg_[0-9a-f]{16}_([01])$", r"autocfg_probe_\1", name),
                target,
                component,
            )
            for name, target, component, _phase in units
        )
        assert (
            reference is None or graph == reference
        ), f"component or host graph differs at {arm}/{phase}: {graph - reference}, {reference - graph}"
        reference = graph
        assert graph["cargo", "x86_64-unknown-linux-gnu", True] >= 2
        assert graph["std", "x86_64-unknown-linux-gnu", False] == 1
        assert all(
            not flag
            for name, target, flag in graph
            if target is None
            or name
            in {"core", "alloc", "std", "profiler_builtins", "compiler_builtins"}
        )
        archives = list(
            (dest / (phase + ".target") / "x86_64-unknown-linux-gnu/release").rglob(
                "libstd-*.rlib"
            )
        )
        assert archives and len({digest(p) for p in archives}) == 1, archives
        lib_checksums.append(digest(archives[0]))
    assert len(set(lib_checksums)) == 1, (
        arm,
        "std should be built identically in PGO generate and use",
        lib_checksums,
    )
    arm_summary.update(
        std_rlib_sha256=lib_checksums[0],
        profiled_target_units=sum(n for (_c, _t, p), n in reference.items() if p),
        unprofiled_std_target_units=sum(
            n
            for (c, t, p), n in reference.items()
            if t and not p and not c.startswith("autocfg_probe_")
        ),
        unprofiled_temporary_probes=sum(
            n
            for (c, t, p), n in reference.items()
            if t and not p and c.startswith("autocfg_probe_")
        ),
        unprofiled_host_units=sum(n for (_c, t, p), n in reference.items() if not t),
    )
    signature = sorted(
        (crate, target or "", flag, count)
        for (crate, target, flag), count in reference.items()
    )
    arm_summary["compiler_unit_graph_sha256"] = hashlib.sha256(
        json.dumps(signature, separators=(",", ":")).encode()
    ).hexdigest()
    if endpoint_audit:
        for key in (
            "std_rlib_sha256",
            "compiler_unit_graph_sha256",
            "training_commands_verified",
            "frozen_training_files_verified",
            "patch_backups",
        ):
            assert arm_summary[key] == endpoint_audit[key], (
                arm,
                key,
                arm_summary[key],
                endpoint_audit[key],
            )
    summary["arms"][arm] = arm_summary
if "base" in summary["arms"] and "guard-stack" in summary["arms"]:
    assert (
        summary["arms"]["base"]["std_rlib_sha256"]
        != summary["arms"]["guard-stack"]["std_rlib_sha256"]
    )
print(json.dumps(summary, indent=2))
