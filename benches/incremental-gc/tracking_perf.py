#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Compare opt-in bookkeeping on fresh builds with one pinned Cargo executable."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time


TASK_ROOT = Path("/private/tmp/codex-cargo-targets/cargo/isolated/incremental-gc")
MARKER = ".ohm-incremental-gc.json"
ORDER = "ABBABAAB" * 4


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_inventory(source):
    """Pin the existing source without changing it or depending on its Git state."""
    digest = hashlib.sha256()
    count = 0
    for directory, children, files in os.walk(source):
        children[:] = sorted(name for name in children if name not in {".git", "target"})
        links = [name for name in children if (Path(directory) / name).is_symlink()]
        for name in sorted(files + links):
            path = Path(directory) / name
            digest.update(os.fsencode(path.relative_to(source)))
            digest.update(b"\0")
            if path.is_symlink():
                digest.update(b"symlink\0" + os.fsencode(os.readlink(path)))
            else:
                digest.update(b"file\0" + bytes.fromhex(sha256(path)))
            count += 1
    return {"files": count, "sha256": digest.hexdigest()}


def marker_snapshot(shared):
    return {
        str(path.relative_to(shared)): {
            "record": json.loads(path.read_text()),
            "sha256": sha256(path),
            "mtime_ns": path.stat().st_mtime_ns,
            "inode": path.stat().st_ino,
        }
        for path in sorted(shared.rglob(MARKER))
    }


def marker_changes(before, after, selected):
    if before.keys() != after.keys():
        raise RuntimeError("A fresh measured build added or removed an ownership marker")
    return {
        "count": len(selected),
        "content_changed": sum(before[key]["sha256"] != after[key]["sha256"]
                               for key in selected),
        "mtime_changed": sum(before[key]["mtime_ns"] != after[key]["mtime_ns"]
                             for key in selected),
        "inode_changed": sum(before[key]["inode"] != after[key]["inode"]
                             for key in selected),
    }


def synthetic_workspace(source):
    """Create 101 independent incremental units without registry dependencies."""
    source.mkdir()
    members = []
    for index in range(100):
        name = f"tiny_{index:03}"
        crate = source / name
        (crate / "src").mkdir(parents=True)
        members.append(name)
        (crate / "Cargo.toml").write_text(
            f'[package]\nname = "{name}"\nversion = "0.1.0"\nedition = "2024"\n'
        )
        (crate / "src/lib.rs").write_text(f"pub fn value() -> usize {{ {index} }}\n")
    (source / "src").mkdir()
    (source / "Cargo.toml").write_text(
        '[package]\nname = "synthetic_root"\nversion = "0.1.0"\nedition = "2024"\n'
        '[workspace]\nresolver = "3"\nmembers = ' + json.dumps(members) + "\n"
        '[dependencies]\n' + "".join(f'{name} = {{ path = "{name}" }}\n' for name in members)
    )
    (source / "src/lib.rs").write_text(
        "pub fn value() -> usize { " + " + ".join(f"{name}::value()" for name in members) + " }\n"
    )


def summarize(rows):
    means = {mode: statistics.mean(row["wall_ms"] for row in rows if row["mode"] == mode)
             for mode in "AB"}
    medians = {mode: statistics.median(row["wall_ms"] for row in rows if row["mode"] == mode)
               for mode in "AB"}
    blocks = []
    for offset in range(0, len(rows), 4):
        block = rows[offset:offset + 4]
        times = {mode: statistics.mean(row["wall_ms"] for row in block if row["mode"] == mode)
                 for mode in "AB"}
        blocks.append({"order": "".join(row["mode"] for row in block),
                       "disabled_ms": times["A"], "enabled_ms": times["B"],
                       "difference_ms": times["B"] - times["A"],
                       "percent": 100 * (times["B"] / times["A"] - 1)})
    differences = [block["difference_ms"] for block in blocks]
    standard_error = statistics.stdev(differences) / len(differences) ** 0.5
    # Eight paired blocks: Student t(7), 97.5th percentile. A local noise estimate,
    # not a claim that serial measurements satisfy independent-sample assumptions.
    half_width = 2.364624251 * standard_error
    difference = statistics.mean(differences)
    return {
        "samples": [{key: row[key] for key in ("name", "mode", "wall_ms", "artifact_count",
                                               "local_artifact_count", "all_fresh")}
                    for row in rows],
        "means_ms": means, "medians_ms": medians,
        "mean_difference_ms": means["B"] - means["A"],
        "mean_percent": 100 * (means["B"] / means["A"] - 1),
        "blocks": blocks,
        "paired_block_difference_sd_ms": statistics.stdev(differences),
        "approximate_paired_block_95_percent_t_interval_ms": [difference - half_width,
                                                              difference + half_width],
        "all_artifacts_fresh": all(row["all_fresh"] for row in rows),
    }


class Experiment:
    def __init__(self, args):
        self.args = args
        self.root = args.output.resolve()
        self.source = args.source.resolve()
        self.cargo = args.cargo.resolve()
        if TASK_ROOT.resolve() not in self.root.parents:
            raise RuntimeError(f"--output must be a child directory of {TASK_ROOT}")
        if self.root.exists() and any(self.root.iterdir()):
            raise RuntimeError(f"Output is not empty: {self.root}")
        if self.root == self.source or self.root in self.source.parents or self.source in self.root.parents:
            raise RuntimeError("Source snapshot and output must not contain each other")
        self.root.mkdir(parents=True, exist_ok=True)
        self.logs = self.root / "commands"
        self.logs.mkdir()
        self.shared = self.root / "build"
        self.synthetic = self.root / "synthetic"
        self.rustc = Path(subprocess.check_output(
            ["rustup", "which", "--toolchain", "ohm", "rustc"], text=True
        ).strip()).resolve()
        # Keep the registry cache, but remove wrappers, target/profile overrides,
        # and other inherited experimental options before adding this run's inputs.
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("CARGO", "RUST", "OHM"))}
        self.overrides = {
            "CARGO_HOME": "/private/tmp/codex-cargo-home",
            "CARGO_BUILD_BUILD_DIR": str(self.shared),
            "CARGO_INCREMENTAL": "1",
            "CARGO_TERM_COLOR": "never",
            "CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST": "all",
            "CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST": "all",
            "RUSTUP_TOOLCHAIN": "ohm",
            "RUSTC": str(self.rustc),
        }
        self.env.update(self.overrides)
        cargo_source = args.cargo_source.resolve()
        cargo_diff = subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=cargo_source)
        (self.root / "cargo-source.patch").write_bytes(cargo_diff)
        self.provenance = {
            "cargo_source": str(cargo_source),
            "cargo_source_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=cargo_source, text=True).strip(),
            "cargo_source_diff_sha256": hashlib.sha256(cargo_diff).hexdigest(),
            "cargo": str(self.cargo), "cargo_sha256": sha256(self.cargo),
            "cargo_build_profile": args.cargo_build_profile,
            "cargo_version": subprocess.check_output([self.cargo, "--version", "--verbose"],
                                                      env=self.env, text=True),
            "rustc": str(self.rustc), "rustc_sha256": sha256(self.rustc),
            "rustc_version": subprocess.check_output([self.rustc, "--version", "--verbose"],
                                                      env=self.env, text=True),
            "harness_sha256": sha256(Path(__file__)),
            "source": str(self.source), "source_inventory": source_inventory(self.source),
            "platform": platform.platform(), "environment": self.overrides,
            "jobs": args.jobs, "package": args.package,
            "order": ORDER, "mode_A": "disabled", "mode_B": "enabled",
        }
        save(self.root / "provenance.json", self.provenance)

    def build(self, scenario, mode, name):
        source = self.source if scenario == "ruff" else self.synthetic
        target = self.root / f"{scenario}-target-{mode}"
        command = [str(self.cargo), "-Zfine-grain-locking", "-Zohm-shared-registry-cache"]
        if mode == "B":
            command.append("-Zohm-incremental-gc")
        command += ["build", "--offline", "--message-format=json", "--jobs", str(self.args.jobs)]
        if scenario == "ruff":
            command += ["--locked", "--lib", "-p", self.args.package]
        stdout = self.logs / f"{scenario}-{name}-{mode}.stdout"
        stderr = stdout.with_suffix(".stderr")
        env = self.env | {"CARGO_TARGET_DIR": str(target)}
        with stdout.open("wb") as out, stderr.open("wb") as err:
            start = time.perf_counter_ns()
            result = subprocess.run(command, cwd=source, env=env, stdout=out, stderr=err)
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
        artifacts = [item for line in stdout.read_text().splitlines()
                     if line.startswith("{") and
                     (item := json.loads(line)).get("reason") == "compiler-artifact"]
        row = {
            "name": name, "mode": mode, "scenario": scenario, "wall_ms": elapsed,
            "command": command, "cwd": str(source), "environment": self.overrides |
            {"CARGO_TARGET_DIR": str(target)}, "returncode": result.returncode,
            "artifact_count": len(artifacts),
            "local_artifact_count": sum(item["package_id"].startswith("path+") for item in artifacts),
            "all_fresh": bool(artifacts) and all(item["fresh"] for item in artifacts),
            "nonfresh": [item["target"]["name"] for item in artifacts if not item["fresh"]],
            "stdout": str(stdout), "stderr": str(stderr),
        }
        save(stdout.with_suffix(".json"), row)
        print(f"{scenario} {name} {mode}: {elapsed:.3f} ms; "
              f"{len(artifacts)} artifacts; all fresh={row['all_fresh']}", flush=True)
        if result.returncode:
            raise RuntimeError(f"Build failed; see {stderr}\n{stderr.read_text()[-4000:]}")
        return row

    def run(self):
        synthetic_workspace(self.synthetic)
        owned = {}
        for scenario in ("ruff", "synthetic"):
            before = marker_snapshot(self.shared)
            for mode in "AB":
                for attempt in range(5):
                    if self.build(scenario, mode, f"warm{attempt}")["all_fresh"]:
                        break
                else:
                    raise RuntimeError(f"{scenario} mode {mode} did not stabilize within five builds")
                if mode == "A" and before != marker_snapshot(self.shared):
                    raise RuntimeError("Disabled tracking changed managed ownership markers")
            after = marker_snapshot(self.shared)
            owned[scenario] = sorted(after.keys() - before.keys())
            if not owned[scenario]:
                raise RuntimeError(f"{scenario} did not create managed incremental units")
        self.provenance["synthetic_inventory"] = source_inventory(self.synthetic)
        save(self.root / "provenance.json", self.provenance)
        print("Warmup complete. Starting timed fresh builds; avoid competing compilation.", flush=True)
        results = {"provenance": self.provenance, "scenarios": {}}
        for scenario in ("ruff", "synthetic"):
            before = marker_snapshot(self.shared)
            save(self.root / f"{scenario}-markers-before.json", before)
            rows = []
            for index, mode in enumerate(ORDER):
                row = self.build(scenario, mode, f"measure{index:02}")
                if not row["all_fresh"]:
                    raise RuntimeError("Measured builds must have every artifact fresh")
                rows.append(row)
            after = marker_snapshot(self.shared)
            save(self.root / f"{scenario}-markers-after.json", after)
            result = summarize(rows)
            result["marker_changes"] = marker_changes(before, after, owned[scenario])
            results["scenarios"][scenario] = result
            print(json.dumps({"scenario": scenario, "mean_difference_ms": result["mean_difference_ms"],
                              "mean_percent": result["mean_percent"],
                              "marker_changes": result["marker_changes"]}), flush=True)
        results["source_unchanged"] = source_inventory(self.source) == self.provenance["source_inventory"]
        results["synthetic_unchanged"] = source_inventory(self.synthetic) == self.provenance["synthetic_inventory"]
        if not results["source_unchanged"] or not results["synthetic_unchanged"]:
            raise RuntimeError("Source changed during the experiment")
        if sha256(self.cargo) != self.provenance["cargo_sha256"] or sha256(self.rustc) != self.provenance["rustc_sha256"]:
            raise RuntimeError("Cargo or rustc executable changed during the experiment")
        save(self.root / "result.json", results)
        print(f"Measurement complete: {self.root / 'result.json'}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cargo", type=Path, required=True,
                        help="Pinned Cargo executable, built with --features ohm-defaults")
    parser.add_argument("--cargo-source", type=Path, default=Path(__file__).resolve().parents[2],
                        help="Cargo checkout used to build the executable; record its revision and diff")
    parser.add_argument("--cargo-build-profile", choices=("release", "dev"), required=True,
                        help="Explicit provenance label; the harness does not build Cargo")
    parser.add_argument("--source", type=Path, required=True,
                        help="Fixed Ruff source snapshot with Cargo.lock; never modified")
    parser.add_argument("--package", default="ruff_python_parser")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True,
                        help=f"Empty child directory beneath {TASK_ROOT}")
    Experiment(parser.parse_args()).run()


if __name__ == "__main__":
    main()
