#!/usr/bin/env python3
"""Aggregate native repeated no-op commands into independently paired groups."""

from __future__ import annotations

from contextlib import redirect_stdout
import csv
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
CORE_DIRECTORY = SCRIPT_DIRECTORY if SCRIPT_DIRECTORY.name == "frozen" else SCRIPT_DIRECTORY / "frozen"
CORE_PATH = CORE_DIRECTORY / "paired.py"
SPEC = importlib.util.spec_from_file_location("ohm_paired_frozen_core", CORE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load frozen benchmark core: {CORE_PATH}")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)
CORE_RUN = core.run
CORE_ANALYZE = core.analyze

ADDITIVE_FIELDS = (
    "wall_ns", "user_seconds", "system_seconds", "minor_faults", "major_faults",
    "voluntary_context_switches", "involuntary_context_switches",
)
CSV_FIELDS = (
    "stage", "pair", "order", "position", "variant", "repetition", "started_at",
    "returncode", *ADDITIVE_FIELDS, "stdout", "stderr",
)


def configuration_repetitions(configuration):
    count = configuration.get("repetitions", 1)
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("repetitions must be a positive integer")
    if configuration.get("metric_files"):
        raise ValueError("paired_repeated.py currently supports native measurements only")
    if count > 1:
        if configuration.get("repeatable_workload") != "noop":
            raise ValueError("repetitions > 1 requires repeatable_workload='noop'")
        if any("dirty_fixture" in argument for argument in configuration.get("prepare_command", [])):
            raise ValueError("dirty fixtures must re-edit before every execution; grouped no-op repetition is unsuitable")
    return count


def harness_hashes():
    return {str(path): core.sha256(path) for path in (Path(__file__).resolve(), CORE_PATH)}


class GroupRecorder:
    def __init__(self, repetitions, delegate):
        self.repetitions = repetitions
        self.delegate = delegate
        self.records = []
        self.raw_stream = None
        self.csv_stream = None
        self.csv_writer = None

    def append(self, output, record):
        if self.raw_stream is None:
            self.raw_stream = (output / "subruns.jsonl").open("w")
            self.csv_stream = (output / "subruns.csv").open("w", newline="")
            self.csv_writer = csv.DictWriter(self.csv_stream, fieldnames=CSV_FIELDS, extrasaction="ignore")
            self.csv_writer.writeheader()
        self.records.append(record)
        self.raw_stream.write(json.dumps(record) + "\n")
        self.raw_stream.flush()
        self.csv_writer.writerow(record)
        self.csv_stream.flush()

    def close(self, output):
        for stream in (self.raw_stream, self.csv_stream):
            if stream is not None:
                stream.close()
        if output.is_dir():
            core.atomic_json(output / "subruns.json", self.records)

    def __call__(self, command, cwd, environment, stdout_path, stderr_path):
        # Preparation and cleanup retain exactly one execution, outside timing.
        if stdout_path.name.endswith(".prepare.stdout") or stdout_path.name == "cleanup.stdout":
            return self.delegate(command, cwd, environment, stdout_path, stderr_path)
        output = stdout_path.parent.parent
        context = {
            "stage": environment["OHM_BENCH_STAGE"],
            "pair": int(environment["OHM_BENCH_PAIR"]),
            "position": int(environment["OHM_BENCH_POSITION"]),
            "variant": environment["OHM_BENCH_VARIANT"],
            "phase": environment["OHM_BENCH_PHASE"],
        }
        first_is_baseline = (context["variant"] == "baseline") == (context["position"] == 0)
        context["order"] = "AB" if first_is_baseline else "BA"
        records = []
        for repetition in range(1, self.repetitions + 1):
            stdout = stdout_path.with_name(f"{stdout_path.stem}.rep-{repetition:03d}{stdout_path.suffix}")
            stderr = stderr_path.with_name(f"{stderr_path.stem}.rep-{repetition:03d}{stderr_path.suffix}")
            record = {
                **context, "repetition": repetition, "started_at": core.utc_now(),
                "command": command,
                "load_average_before": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
            }
            record.update(self.delegate(command, cwd, environment, stdout, stderr))
            record["load_average_after"] = list(os.getloadavg()) if hasattr(os, "getloadavg") else None
            record["compiled_packages"] = sorted(set(re.findall(
                r"^\s*(?:Checking|Compiling)\s+([^\s]+)\s+v[^\s]+",
                stderr.read_text(errors="replace"), re.MULTILINE,
            )))
            self.append(output, record)
            records.append(record)
            if self.repetitions > 1 and record["compiled_packages"]:
                raise RuntimeError(
                    f"expected a no-op workload; {context['variant']} repetition {repetition} "
                    f"rebuilt {record['compiled_packages']}; raw subrun retained"
                )
            if record["returncode"]:
                break
        # Group metrics are sums of separately timed subprocesses. Log copying,
        # Python loop overhead, preparation and installation are excluded.
        aggregate = {field: sum(record[field] for record in records) for field in ADDITIVE_FIELDS}
        aggregate.update({
            "returncode": next((record["returncode"] for record in records if record["returncode"]), 0),
            "stdout": str(stdout_path), "stderr": str(stderr_path),
            "repetitions_requested": self.repetitions,
            "repetitions_completed": len(records),
            "repetitions": records,
        })
        for destination, field in ((stdout_path, "stdout"), (stderr_path, "stderr")):
            with destination.open("wb") as stream:
                for record in records:
                    stream.write(f"--- repetition {record['repetition']} ---\n".encode())
                    stream.write(Path(record[field]).read_bytes())
                    stream.write(b"\n")
        return aggregate


def run(args):
    configuration = json.loads(Path(args.config).read_text())
    count = configuration_repetitions(configuration)
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError("output directory must be new")
    initial_hashes = harness_hashes()
    original_command = core.run_command
    recorder = GroupRecorder(count, original_command)
    core.run_command = recorder
    try:
        CORE_RUN(args)
    finally:
        original_error_active = sys.exc_info()[0] is not None
        core.run_command = original_command
        recorder.close(output)
        manifest_path = output / "manifest.json"
        changed = False
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text())
            final_hashes = harness_hashes()
            changed = initial_hashes != final_hashes
            manifest["repeated_harness_sha256"] = initial_hashes
            manifest["repeated_harness_sha256_after"] = final_hashes
            manifest["grouping"] = {
                "repetitions_per_variant": count,
                "aggregation": "sum of individually timed native subprocesses",
                "statistical_unit": "one baseline/candidate group pair",
                "prepare_executions_per_variant_group": 1 if configuration.get("prepare_command") else 0,
                "subrun_count": len(recorder.records),
                "workload": configuration.get("repeatable_workload", "single execution"),
            }
            if changed:
                manifest["state"] = "failed"
                manifest["repeated_harness_error"] = "benchmark harness changed during execution"
            core.atomic_json(manifest_path, manifest)
        if changed and not original_error_active:
            raise RuntimeError("benchmark harness changed during execution")


def validate_groups(manifest, samples, subruns):
    count = manifest["grouping"]["repetitions_per_variant"]
    grouped = {}
    for record in subruns:
        key = (record["stage"], record["pair"], record["variant"])
        grouped.setdefault(key, []).append(record)
    sample_keys = {(sample["stage"], sample["pair"], sample["variant"]) for sample in samples}
    if len(sample_keys) != len(samples) or set(grouped) != sample_keys:
        raise ValueError("raw subruns and group samples do not match")
    for sample in samples:
        records = grouped[(sample["stage"], sample["pair"], sample["variant"])]
        if sorted(record["repetition"] for record in records) != list(range(1, count + 1)):
            raise ValueError("missing or duplicated repetition in a group")
        if any(record["returncode"] for record in records):
            raise ValueError("unsuccessful raw repetition exists")
        if count > 1 and any(record["compiled_packages"] for record in records):
            raise ValueError("a repeated workload rebuilt a package")
        if any(record["command"] != sample["command"] or record["order"] != sample["order"] for record in records):
            raise ValueError("raw repetition command or order differs from its group")
        for field in ADDITIVE_FIELDS:
            total = sum(record[field] for record in records)
            if not math.isclose(total, sample[field], rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError(f"group {field} is not the sum of its raw repetitions")
    return count


def analyze(args):
    directory = Path(args.directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("state") != "complete":
        raise ValueError("refusing to analyze an incomplete repeated run")
    if manifest["repeated_harness_sha256"] != manifest["repeated_harness_sha256_after"]:
        raise ValueError("repeated benchmark harness changed during execution")
    samples = json.loads((directory / "samples.json").read_text())
    subruns = json.loads((directory / "subruns.json").read_text())
    count = validate_groups(manifest, samples, subruns)
    # The frozen analyzer sees one summed observation per variant per group.
    # Its bootstrap, sign test, order summaries and minimum sample gate therefore
    # use group pairs, never the correlated repetitions as extra observations.
    with redirect_stdout(io.StringIO()):
        CORE_ANALYZE(args)
    result = json.loads((directory / "analysis.json").read_text())
    result["grouping"] = manifest["grouping"]
    result["grouping"]["measurement_group_pairs"] = result["pairs"]
    result["grouping"]["measurement_subruns"] = sum(record["stage"] == "measurement" for record in subruns)
    result["grouping"]["inference"] = "Bootstrap and exact paired sign test use group aggregates; individual repetitions are not independent samples."
    result["per_invocation_seconds"] = {
        name: result[name] / count for name in (
            "baseline_median_seconds", "candidate_median_seconds", "baseline_mean_seconds", "candidate_mean_seconds",
        )
    }
    result["per_invocation_seconds"]["basis"] = "Group sums divided by the fixed repetition count; medians are across group means."
    result["repetition_position_seconds"] = [
        {
            "repetition": repetition,
            **{
                variant + "_median": statistics.median(
                    record["wall_ns"] / 1e9 for record in subruns
                    if record["stage"] == "measurement" and record["variant"] == variant and record["repetition"] == repetition
                ) for variant in ("baseline", "candidate")
            },
        }
        for repetition in range(1, count + 1)
    ]
    result["screen"]["note"] += " Repetition-position summaries are descriptive only. A passing group screen does not establish a dirty-build speedup."
    core.atomic_json(directory / "analysis.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    core.run = run
    core.analyze = analyze
    core.main()
