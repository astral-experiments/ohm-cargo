#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Measure configuration-cache expiry on an archived real Cargo workspace."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import statistics
import subprocess
import sys
import tarfile
import time


MARKER = ".ohm-incremental-gc.json"
TASK_ROOT = Path("/private/tmp/codex-cargo-targets/cargo/isolated/incremental-gc")
FLAGS = ["-Zohm-incremental-gc", "-Zfine-grain-locking", "-Zohm-shared-registry-cache"]
ORDER = ["retained", "expired", "expired", "retained", "expired", "retained", "retained", "expired"]


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(root):
    """Count names and distinct inodes; neither count establishes physical APFS use."""
    result = {"files": 0, "logical_bytes": 0, "unique_inode_logical_bytes": 0,
              "unique_inode_allocated_bytes": 0, "hardlinked_files": 0}
    seen = set()
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"Unexpected symlink in generated cache: {path}")
        if not path.is_file():
            continue
        info = path.stat()
        result["files"] += 1
        result["logical_bytes"] += info.st_size
        result["hardlinked_files"] += info.st_nlink > 1
        inode = (info.st_dev, info.st_ino)
        if inode not in seen:
            seen.add(inode)
            result["unique_inode_logical_bytes"] += info.st_size
            result["unique_inode_allocated_bytes"] += info.st_blocks * 512
        # An expired tracking timestamp can refresh without changing the payload.
        if path.name != MARKER:
            digest.update(os.fsencode(path.relative_to(root)))
            digest.update(b"\0")
            digest.update(bytes.fromhex(sha256(path)))
    result["payload_sha256"] = digest.hexdigest()
    return result


def markers(root):
    found = {}
    for path in sorted(root.rglob(MARKER)):
        value = json.loads(path.read_text())
        if value["version"] not in {1, 2} or value["unit"] != path.parent.name:
            raise RuntimeError(f"Unrecognized prototype marker: {path}")
        found[path.parent] = value
    return found


def snapshot(root, destination):
    units = {str(path.relative_to(root)): {"marker": value, **inventory(path)}
             for path, value in markers(root).items()}
    result = {"root": str(root), "total": inventory(root), "units": units}
    save(destination, result)
    return result


class Experiment:
    def __init__(self, args):
        self.args = args
        self.root = args.output.resolve()
        if TASK_ROOT.resolve() not in self.root.parents:
            raise RuntimeError(f"--output must be a child directory of {TASK_ROOT}")
        if self.root.exists() and any(self.root.iterdir()):
            raise RuntimeError(f"Output is not empty; select another child directory: {self.root}")
        self.root.mkdir(parents=True, exist_ok=True)
        self.logs = self.root / "commands"
        self.logs.mkdir()
        self.workspace = self.root / "source"
        self.shared = self.root / "build"
        self.incremental = self.shared / "debug" / "incremental"
        self.env = os.environ.copy()
        # A personal wrapper, flag or profile override would change this experiment.
        for key in list(self.env):
            if key.startswith(("CARGO_PROFILE_", "CARGO_UNSTABLE_")) or key in {
                "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC", "RUSTC_WRAPPER",
                "RUSTC_WORKSPACE_WRAPPER", "CARGO_BUILD_RUSTC_WRAPPER",
                "CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER", "CARGO_BUILD_RUSTFLAGS",
                "CARGO_BUILD_TARGET", "CARGO_TARGET_DIR", "CARGO_BUILD_BUILD_DIR",
                "RUSTC_BOOTSTRAP",
            }:
                del self.env[key]
        self.overrides = {
            "CARGO_HOME": "/private/tmp/codex-cargo-home",
            "RUSTUP_TOOLCHAIN": "ohm",
            "CARGO_TARGET_DIR": str(self.root / "target"),
            "CARGO_BUILD_BUILD_DIR": str(self.shared),
            "CARGO_INCREMENTAL": "1",
            "CARGO_TERM_COLOR": "never",
            "CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST": "all",
            "CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST": "all",
        }
        self.env.update(self.overrides)
        self.records = []

    def run(self, name, argv, cwd=None, stdout=None):
        prefix = self.logs / name
        stdout = stdout or prefix.with_suffix(".stdout")
        stderr = prefix.with_suffix(".stderr")
        wrapper_log = prefix.with_suffix(".rustc.jsonl")
        environment = {**self.env, "OHM_GC_RUSTC_LOG": str(wrapper_log)}
        started = time.time()
        start_counter = time.perf_counter()
        print(f"[{name}] {shlex.join(map(str, argv))}", flush=True)
        with stdout.open("wb") as out, stderr.open("wb") as err:
            result = subprocess.run(list(map(str, argv)), cwd=cwd or self.workspace,
                                    env=environment, stdout=out, stderr=err)
        record = {"name": name, "argv": list(map(str, argv)),
                  "cwd": str(cwd or self.workspace), "environment": dict(self.overrides),
                  "started_unix": started, "wall_seconds": time.perf_counter() - start_counter,
                  "returncode": result.returncode, "stdout": str(stdout), "stderr": str(stderr)}
        if wrapper_log.exists():
            record["rustc"] = [json.loads(line) for line in wrapper_log.read_text().splitlines()]
        save(prefix.with_suffix(".json"), record)
        self.records.append(record)
        if result.returncode:
            raise RuntimeError(f"{name} failed; see {stderr}\n{stderr.read_text()[-4000:]}")
        return record

    def build(self, name, debug):
        record = self.run(name, [self.args.cargo, *FLAGS, "build", "--locked", "--lib",
                                "-p", self.args.package, "--jobs", self.args.jobs,
                                "--config", f"profile.dev.debug={debug}",
                                "--message-format=json"])
        artifacts = [item for line in Path(record["stdout"]).read_text().splitlines()
                     if line.startswith("{") and
                     (item := json.loads(line)).get("reason") == "compiler-artifact"]
        record["artifacts"] = artifacts
        record["compilations"] = [item for item in record.get("rustc", []) if item["compilation"]]
        save(self.logs / f"{name}.json", record)
        return record

    @staticmethod
    def assert_fresh(record):
        if not record["artifacts"] or record["compilations"] or any(
            not item["fresh"] for item in record["artifacts"]
        ):
            raise RuntimeError(f"Expected a completely fresh build: {record['name']}")

    def seed(self):
        revision = self.run("source-revision", ["git", "-C", self.args.source,
                            "rev-parse", "--verify", "--end-of-options",
                            f"{self.args.source_rev}^{{commit}}"], cwd=self.root)
        revision = Path(revision["stdout"]).read_text().strip()
        archive = self.root / "source.tar"
        self.run("source-archive", ["git", "-C", self.args.source, "archive", revision],
                 cwd=self.root, stdout=archive)
        self.workspace.mkdir()
        with tarfile.open(archive) as tar:
            tar.extractall(self.workspace, filter="data")
        archive.unlink()
        compiler = self.run("compiler-path", ["rustup", "which", "--toolchain", "ohm", "rustc"])
        compiler = Path(Path(compiler["stdout"]).read_text().strip()).resolve()
        self.overrides["RUSTC"] = str(compiler)
        self.env["RUSTC"] = str(compiler)
        compiler_version = self.run("compiler-version", [compiler, "--version", "--verbose"])
        cargo_version = self.run("cargo-version", [self.args.cargo, "--version", "--verbose"])
        cargo_source = Path(__file__).resolve().parents[2]
        base = self.run("cargo-source-revision", ["git", "rev-parse", "HEAD"], cwd=cargo_source)
        delta = self.run("cargo-source-diff", ["git", "diff", "--binary", "HEAD"], cwd=cargo_source)
        untracked = self.run("cargo-source-untracked", ["git", "ls-files", "--others",
                             "--exclude-standard", "-z"], cwd=cargo_source)
        source_delta = {
            "base_revision": Path(base["stdout"]).read_text().strip(),
            "tracked_diff_sha256": sha256(Path(delta["stdout"])),
            "untracked_file_sha256": {
                name: sha256(cargo_source / name)
                for name in Path(untracked["stdout"]).read_text().split("\0") if name
            },
        }
        wrapper = self.root / "rustc-wrapper.py"
        wrapper.write_text(f"#!{sys.executable}\n" + '''import json, os, subprocess, sys, time
args = sys.argv[1:]
started = time.perf_counter()
result = subprocess.run(args, close_fds=False)
record = {"argv": args, "wall_seconds": time.perf_counter() - started,
          "returncode": result.returncode,
          "compilation": "--crate-name" in args and "--print" not in args
              and not any(arg.startswith("--print=") for arg in args)}
fd = os.open(os.environ["OHM_GC_RUSTC_LOG"], os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
try:
    os.write(fd, (json.dumps(record) + "\\n").encode())
finally:
    os.close(fd)
sys.exit(result.returncode)
''')
        wrapper.chmod(0o755)
        # A global wrapper disables Ohm's immutable registry cache. Restrict
        # instrumentation to workspace units and retain inherited profile leases.
        self.overrides["RUSTC_WORKSPACE_WRAPPER"] = str(wrapper)
        self.env["RUSTC_WORKSPACE_WRAPPER"] = str(wrapper)
        self.provenance = {
            "source": str(self.args.source), "source_revision": revision,
            "package": self.args.package, "edit_file": self.args.edit_file,
            "configurations": [0, 1, 2], "jobs": self.args.jobs,
            "cargo": str(self.args.cargo), "cargo_sha256": sha256(self.args.cargo),
            "cargo_source": str(cargo_source), "cargo_source_delta": source_delta,
            "cargo_source_delta_sha256": hashlib.sha256(
                json.dumps(source_delta, sort_keys=True).encode()).hexdigest(),
            "cargo_version": Path(cargo_version["stdout"]).read_text(),
            "rustc": str(compiler), "rustc_sha256": sha256(compiler),
            "rustc_version": Path(compiler_version["stdout"]).read_text(),
            "harness_sha256": sha256(Path(__file__)), "python": sys.version,
            "platform": platform.platform(), "environment": self.overrides,
            "age_simulation": "Set all prototype last_used markers to 40 days ago, then run a fresh debug=2 build.",
        }
        save(self.root / "provenance.json", self.provenance)
        self.edit_path = (self.workspace / self.args.edit_file).resolve()
        if self.workspace not in self.edit_path.parents:
            raise RuntimeError("--edit-file must be inside the archived workspace")
        original = self.edit_path.read_bytes()
        self.original = original
        self.edit_path.write_bytes(original + b"\n#[doc(hidden)]\npub const OHM_GC_BENCH_EDIT: u8 = 0;\n")
        self.seed_records = [self.build(f"seed-debug-{debug}", debug) for debug in (0, 1, 2)]
        owned = markers(self.incremental)
        if not owned:
            raise RuntimeError("No prototype ownership markers were created")
        candidates = []
        crate_name = self.args.package.replace("-", "_")
        for invocation in self.seed_records[0]["compilations"]:
            argv = invocation["argv"]
            if argv[argv.index("--crate-name") + 1] != crate_name:
                continue
            for arg in argv:
                if arg.startswith("incremental="):
                    incremental = Path(arg.removeprefix("incremental=")).resolve()
                    candidates.extend(path for path in owned if path == incremental or path in incremental.parents)
        if len(candidates) != 1:
            raise RuntimeError(f"Expected one debug=0 package incremental cache, found {candidates}")
        self.sample_unit = candidates[0]
        self.baseline = self.root / "baseline-unit"
        shutil.copytree(self.sample_unit, self.baseline)

    def collect(self):
        seeded = snapshot(self.incremental, self.root / "01-seeded.json")
        aged_timestamp = int(time.time()) - 40 * 24 * 60 * 60
        for path, marker in markers(self.incremental).items():
            marker["last_used"] = aged_timestamp
            (path / MARKER).write_text(json.dumps(marker, separators=(",", ":")))
        fresh = self.build("refresh-debug-2", 2)
        self.assert_fresh(fresh)
        before = snapshot(self.incremental, self.root / "02-before-gc.json")
        expired = {path for path, unit in before["units"].items()
                   if unit["marker"]["last_used"] == aged_timestamp}
        retained = set(before["units"]) - expired
        if not expired or not retained or str(self.sample_unit.relative_to(self.incremental)) not in expired:
            raise RuntimeError("The debug configurations did not produce distinct disposable caches")
        command = [self.args.cargo, *FLAGS, "clean", "incremental", "--max-age", "30 days"]
        self.run("gc-dry-run", [*command, "--dry-run"])
        dry = snapshot(self.incremental, self.root / "03-after-dry-run.json")
        if before["units"] != dry["units"]:
            raise RuntimeError("Dry-run changed managed cache contents")
        self.run("gc", command)
        after = snapshot(self.incremental, self.root / "04-after-gc.json")
        if set(after["units"]) != retained:
            raise RuntimeError("GC did not remove exactly the expired unit caches")
        for path in retained:
            if before["units"][path] != after["units"][path]:
                raise RuntimeError(f"GC changed a retained unit: {path}")
        self.assert_fresh(self.build("retained-noop-after-gc", 2))
        self.assert_fresh(self.build("expired-noop-after-gc", 0))
        self.gc_result = {
            "seeded_units": len(seeded["units"]), "expired_units": sorted(expired),
            "retained_units": sorted(retained), "before": before["total"], "after": after["total"],
            "removed_logical_bytes": before["total"]["logical_bytes"] - after["total"]["logical_bytes"],
            "removed_unique_inode_allocated_bytes": before["total"]["unique_inode_allocated_bytes"]
                - after["total"]["unique_inode_allocated_bytes"],
            "dry_run_unchanged": True, "retained_payload_unchanged": True,
            "retained_noop_fresh": True, "expired_noop_fresh": True,
        }

    def measure(self):
        samples = []
        for index, state in enumerate(ORDER):
            # Ohm checks source contents, so touching an identical edited file is
            # insufficient. Restore baseline artifacts before each measured edit.
            self.edit_path.write_bytes(self.original + b"\n#[doc(hidden)]\npub const OHM_GC_BENCH_EDIT: u8 = 0;\n")
            self.build(f"reset-{index + 1}", 0)
            if self.sample_unit.exists():
                shutil.rmtree(self.sample_unit)
            if state == "retained":
                shutil.copytree(self.baseline, self.sample_unit)
            self.edit_path.write_bytes(self.original + b"\n#[doc(hidden)]\npub const OHM_GC_BENCH_EDIT: u8 = 1;\n")
            record = self.build(f"edit-{index + 1}-{state}", 0)
            compilations = record["compilations"]
            if len(compilations) != 1:
                raise RuntimeError(f"Expected exactly one rustc compilation in sample {index + 1}")
            argv = compilations[0]["argv"]
            if argv[argv.index("--crate-name") + 1] != self.args.package.replace("-", "_"):
                raise RuntimeError("The timing sample compiled an unexpected crate")
            dirty = [artifact for artifact in record["artifacts"] if not artifact["fresh"]]
            if len(dirty) != 1 or dirty[0]["target"]["name"] != self.args.package.replace("-", "_"):
                raise RuntimeError("The timing sample rebuilt unexpected artifacts")
            samples.append({"cache": state, "wall_seconds": record["wall_seconds"],
                            "rustc_seconds": compilations[0]["wall_seconds"], "command": record["name"]})
        medians = {state: statistics.median(sample["rustc_seconds"] for sample in samples
                                           if sample["cache"] == state)
                   for state in ("retained", "expired")}
        self.result = {"provenance": self.provenance, "gc": self.gc_result,
                       "next_edit": {"unit": str(self.sample_unit), "debug": 0, "samples": samples,
                                     "median_rustc_seconds": medians,
                                     "expired_over_retained": medians["expired"] / medians["retained"]},
                       "caveats": ["Retention ages are simulated, not observed over 40 days.",
                                   "The workload is one package from a pinned real workspace; it is not a fleet estimate.",
                                   "Allocated byte counts deduplicate hardlinks by inode; they do not account for shared APFS extents.",
                                   "An unmeasured build restores baseline source and artifacts before each trial, then its incremental cache is restored or removed.",
                                   "Deleting incremental state keeps fresh artifacts reusable but can slow the next source edit."]}
        save(self.root / "result.json", self.result)
        print(json.dumps({"result": str(self.root / "result.json"), "gc": self.gc_result,
                          "median_rustc_seconds": medians}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cargo", required=True, type=lambda value: Path(value).resolve())
    parser.add_argument("--source", required=True, type=lambda value: Path(value).resolve())
    parser.add_argument("--source-rev", default="HEAD")
    parser.add_argument("--package", default="ruff_python_parser")
    parser.add_argument("--edit-file", default="crates/ruff_python_parser/src/lib.rs")
    parser.add_argument("--output", type=Path, default=TASK_ROOT / "results")
    parser.add_argument("--jobs", type=int, default=8)
    experiment = Experiment(parser.parse_args())
    try:
        experiment.seed()
        experiment.collect()
        experiment.measure()
    finally:
        save(experiment.root / "commands.json", experiment.records)


if __name__ == "__main__":
    main()
