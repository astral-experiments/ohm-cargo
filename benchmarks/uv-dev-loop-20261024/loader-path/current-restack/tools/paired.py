#!/usr/bin/env python3
"""Run paired build measurements and analyze them without third-party packages."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import shutil
import statistics
import subprocess
import sys
import time


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def make_plan(count, seed):
    """Randomize pair order while balancing the number of AB and BA pairs."""
    orders = [("baseline", "candidate")] * (count // 2)
    orders += [("candidate", "baseline")] * (count // 2)
    generator = random.Random(seed)
    if count % 2:
        orders.append(generator.choice((("baseline", "candidate"), ("candidate", "baseline"))))
    generator.shuffle(orders)
    return orders


def substitute(value, context):
    # Do not use str.format: arguments may legitimately contain Python/Rust braces.
    for key, replacement in context.items():
        value = value.replace("{" + key + "}", str(replacement))
    return value


def read_callgrind_summary(path, event="Ir"):
    """Read one event from a complete single-part Callgrind summary."""
    event_rows = []
    summaries = []
    with Path(path).open() as stream:
        for line in stream:
            if line.startswith("events:"):
                event_rows.append(line.partition(":")[2].split())
            elif line.startswith("summary:"):
                summaries.append(line.partition(":")[2].split())
    if len(event_rows) != 1 or len(summaries) != 1:
        raise ValueError(f"expected one events header and one summary in {path}")
    events, summary = event_rows[0], summaries[0]
    if len(set(events)) != len(events) or len(events) != len(summary):
        raise ValueError(f"ambiguous or mismatched Callgrind event columns in {path}")
    if event not in events:
        raise ValueError(f"missing Callgrind event {event!r} in {path}")
    try:
        counts = [int(value) for value in summary]
    except ValueError as error:
        raise ValueError(f"invalid Callgrind summary count in {path}") from error
    if any(value < 0 for value in counts):
        raise ValueError(f"negative Callgrind summary count in {path}")
    return counts[events.index(event)]


def run_command(command, cwd, environment, stdout_path, stderr_path):
    receipt_path = stdout_path.with_name(stdout_path.name + ".command.json")
    if receipt_path.exists():
        raise ValueError(f"raw command receipt already exists: {receipt_path}")
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        started = time.perf_counter_ns()
        process = subprocess.run(command, cwd=cwd, env=environment, stdout=stdout, stderr=stderr)
        elapsed_ns = time.perf_counter_ns() - started
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    result = {
        "returncode": process.returncode,
        "wall_ns": elapsed_ns,
        "user_seconds": after.ru_utime - before.ru_utime,
        "system_seconds": after.ru_stime - before.ru_stime,
        "minor_faults": after.ru_minflt - before.ru_minflt,
        "major_faults": after.ru_majflt - before.ru_majflt,
        "voluntary_context_switches": after.ru_nvcsw - before.ru_nvcsw,
        "involuntary_context_switches": after.ru_nivcsw - before.ru_nivcsw,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
    }
    atomic_json(receipt_path, {"schema_version": 1, "command": command, "cwd": str(cwd),
                               "environment_sha256": hashlib.sha256(json.dumps(list(environment.items()), separators=(",", ":")).encode()).hexdigest(),
                               "result": result})
    return result


def install_variant(source, destination):
    """Replace a regular file atomically, never overwrite a symlink's target."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError(f"canonical executable must be a regular file, not a symlink: {destination}")
    temporary = destination.with_name(destination.name + ".bench-tmp")
    shutil.copyfile(source, temporary)
    os.chmod(temporary, source.stat().st_mode & 0o777)
    temporary.replace(destination)


def machine_metadata():
    result = {
        "platform": platform.platform(),
        "uname": list(platform.uname()),
        "python": sys.version,
        "cpu_count": os.cpu_count(),
        "affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "load_average": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
        "uid": os.getuid() if hasattr(os, "getuid") else None,
        "effective_uid": os.geteuid() if hasattr(os, "geteuid") else None,
        "root_directory_owner_uid": Path("/").stat().st_uid,
    }
    for filename in ("/proc/cpuinfo", "/proc/meminfo", "/proc/sys/kernel/perf_event_paranoid"):
        try:
            result[filename] = Path(filename).read_text()
        except OSError:
            pass
    return result


def build_environment_metadata():
    # Only build settings: do not serialize registry credentials or the full environment.
    names = {
        "PATH", "CARGO_HOME", "RUSTUP_HOME", "RUSTUP_TOOLCHAIN", "RUSTC", "RUSTDOC",
        "RUSTFLAGS", "RUSTDOCFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_ENCODED_RUSTDOCFLAGS",
        "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTC_BOOTSTRAP", "CARGO_TARGET_DIR",
        "CARGO_BUILD_BUILD_DIR", "CARGO_BUILD_JOBS", "CARGO_INCREMENTAL", "CARGO_LOG",
        "CARGO_LOG_PROFILE", "CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST",
        "CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST", "CC", "CXX", "AR", "CFLAGS", "CXXFLAGS",
    }
    names.update(name for name in os.environ if name.startswith("CARGO_PROFILE_"))
    return {name: os.environ[name] for name in sorted(names) if name in os.environ}


def run(args):
    configuration_path = Path(args.config).resolve()
    configuration = json.loads(configuration_path.read_text())
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "logs").mkdir()
    cwd = Path(configuration["cwd"]).resolve()
    destination = Path(configuration["canonical_executable"]).absolute()
    variants = {name: Path(configuration["variants"][name]).resolve() for name in ("baseline", "candidate")}
    if any(source == destination.resolve() for source in variants.values()):
        raise ValueError("variant inputs must differ from the canonical executable")
    for source in variants.values():
        if not source.is_file() or not os.access(source, os.X_OK):
            raise ValueError(f"variant must be an executable file: {source}")
    if not isinstance(configuration["command"], list) or not configuration["command"]:
        raise ValueError("command must be a nonempty argv list; no shell is inserted")
    metric_definitions = configuration.get("metric_files", {})
    for name, definition in metric_definitions.items():
        if definition.get("format") != "callgrind" or not definition.get("path"):
            raise ValueError(f"metric {name!r} requires format='callgrind' and a path")
    if metric_definitions:
        command = configuration["command"]
        if "--trace-children=no" not in command or any(
            argument == "--trace-children"
            or (argument.startswith("--trace-children=") and argument != "--trace-children=no")
            for argument in command
        ):
            raise ValueError("Callgrind metrics must explicitly use --trace-children=no; child compiler work is outside this metric")
    hashes = {name: sha256(path) for name, path in variants.items()}
    recorded_files = {str(Path(path).resolve()): sha256(path) for path in configuration.get("record_files", [])}
    plans = {
        "warmup": make_plan(args.warmup_pairs, args.seed ^ 0x5A17),
        "measurement": make_plan(args.pairs, args.seed),
    }
    manifest = {
        "schema_version": 1,
        "started_at": utc_now(),
        "phase": args.phase,
        "configuration": configuration,
        "configuration_path": str(configuration_path),
        "configuration_sha256": sha256(configuration_path),
        "variant_sha256": hashes,
        "variant_paths": {name: str(path) for name, path in variants.items()},
        "canonical_executable": str(destination),
        "seed": args.seed,
        "pairs": args.pairs,
        "warmup_pairs": args.warmup_pairs,
        "plans": plans,
        "machine": machine_metadata(),
        "inherited_build_environment": build_environment_metadata(),
        "recorded_file_sha256": recorded_files,
        "state": "running",
    }
    atomic_json(output / "manifest.json", manifest)
    sample_fields = ["stage", "pair", "order", "position", "variant", "started_at", "returncode",
                     "wall_ns", "user_seconds", "system_seconds", "minor_faults", "major_faults",
                     "voluntary_context_switches", "involuntary_context_switches", "stdout", "stderr"]
    sample_fields.extend("metric_" + name for name in metric_definitions)
    samples = []
    try:
        with (output / "samples.jsonl").open("w") as raw, (output / "samples.csv").open("w", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=sample_fields, extrasaction="ignore")
            writer.writeheader()
            for stage, plan in plans.items():
                for pair, order in enumerate(plan):
                    for position, variant in enumerate(order):
                        label = f"{stage}-{pair:04d}-{position}-{variant}"
                        context = {
                            "cargo": destination,
                            "variant": variant,
                            "pair": pair,
                            "stage": stage,
                            "phase": args.phase,
                            "output": output,
                            "position": position,
                        }
                        environment = os.environ.copy()
                        configured_env = dict(configuration.get("env", {}))
                        configured_env.update(configuration.get("variant_env", {}).get(variant, {}))
                        for key, value in configured_env.items():
                            if value is None:
                                environment.pop(key, None)
                            else:
                                environment[key] = substitute(str(value), context)
                        environment.update({"OHM_BENCH_" + key.upper(): str(value) for key, value in context.items() if key != "cargo"})
                        install_variant(variants[variant], destination)
                        installed_hash = sha256(destination)
                        if installed_hash != hashes[variant]:
                            raise RuntimeError(f"installed executable hash mismatch: {variant}")
                        prepare = configuration.get("prepare_command")
                        prepare_result = None
                        if prepare:
                            prepare_result = run_command(
                                [substitute(value, context) for value in prepare], cwd, environment,
                                output / "logs" / (label + ".prepare.stdout"),
                                output / "logs" / (label + ".prepare.stderr"),
                            )
                            if prepare_result["returncode"]:
                                atomic_json(output / (label + ".prepare-failure.json"), prepare_result)
                                raise RuntimeError(f"prepare failed: {label}; see its logs")
                        sample = {
                            "stage": stage, "pair": pair,
                            "order": "AB" if order[0] == "baseline" else "BA",
                            "position": position, "variant": variant, "started_at": utc_now(),
                            "command": [substitute(value, context) for value in configuration["command"]],
                            "configured_environment": {key: environment.get(key) for key in configured_env},
                            "installed_sha256": installed_hash,
                            "load_average_before": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
                            "prepare": prepare_result,
                        }
                        metric_paths = {}
                        for name, definition in metric_definitions.items():
                            path = Path(substitute(definition["path"], context))
                            metric_paths[name] = path if path.is_absolute() else cwd / path
                        for path in metric_paths.values():
                            if path.exists():
                                raise RuntimeError(f"metric output already exists before sample: {path}")
                        sample.update(run_command(
                            sample["command"], cwd, environment,
                            output / "logs" / (label + ".stdout"), output / "logs" / (label + ".stderr"),
                        ))
                        sample["load_average_after"] = list(os.getloadavg()) if hasattr(os, "getloadavg") else None
                        sample["executable_unchanged"] = sha256(destination) == hashes[variant]
                        sample["metrics"] = {}
                        sample["metric_files"] = {}
                        metric_errors = {}
                        for name, path in metric_paths.items():
                            try:
                                value = read_callgrind_summary(path, metric_definitions[name].get("event", "Ir"))
                                sample["metrics"][name] = value
                                sample["metric_" + name] = value
                                sample["metric_files"][name] = {"path": str(path), "sha256": sha256(path)}
                            except (OSError, ValueError) as error:
                                metric_errors[name] = str(error)
                        if metric_errors:
                            sample["metric_errors"] = metric_errors
                        samples.append(sample)
                        raw.write(json.dumps(sample) + "\n")
                        raw.flush()
                        writer.writerow(sample)
                        csv_file.flush()
                        print(f"{label}: {sample['wall_ns'] / 1e9:.6f} s", flush=True)
                        if sample["returncode"]:
                            raise RuntimeError(f"command failed: {label}; see its logs")
                        if not sample["executable_unchanged"]:
                            raise RuntimeError(f"canonical executable changed during sample: {label}")
                        if metric_errors:
                            raise RuntimeError(f"missing or invalid metric output: {label}; see recorded metric_errors")
        manifest["state"] = "complete"
    except BaseException as error:
        manifest["state"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
        manifest["error"] = repr(error)
        raise
    finally:
        original_error_active = sys.exc_info()[0] is not None
        cleanup_error = None
        cleanup = configuration.get("cleanup_command")
        if cleanup:
            cleanup_context = {"cargo": destination, "output": output, "phase": args.phase}
            try:
                manifest["cleanup"] = run_command(
                    [substitute(value, cleanup_context) for value in cleanup], cwd, os.environ.copy(),
                    output / "logs" / "cleanup.stdout", output / "logs" / "cleanup.stderr",
                )
                if manifest["cleanup"]["returncode"]:
                    cleanup_error = "cleanup command failed; see logs/cleanup.stderr"
            except BaseException as error:
                cleanup_error = repr(error)
            if cleanup_error:
                manifest["state"] = "failed"
                manifest["cleanup_error"] = cleanup_error
        manifest["finished_at"] = utc_now()
        manifest["sample_count"] = len(samples)
        manifest["variant_sha256_after"] = {name: sha256(path) for name, path in variants.items()}
        manifest["recorded_file_sha256_after"] = {path: sha256(path) if Path(path).exists() else None for path in recorded_files}
        atomic_json(output / "manifest.json", manifest)
        atomic_json(output / "samples.json", samples)
        if cleanup_error and not original_error_active:
            raise RuntimeError(cleanup_error)


def quantile(values, probability):
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def exact_sign_test(wins, losses):
    non_ties = wins + losses
    if not non_ties:
        return 1.0
    tail = sum(math.comb(non_ties, count) for count in range(min(wins, losses) + 1))
    return min(1.0, 2 * tail / (2 ** non_ties))


def paired_statistics(pairs, confidence=0.99, resamples=20000, seed=0):
    if not pairs:
        raise ValueError("no measurement pairs")
    logs = [math.log(pair["baseline"] / pair["candidate"]) for pair in pairs]
    generator = random.Random(seed)
    bootstraps = [statistics.fmean(generator.choices(logs, k=len(logs))) for _ in range(resamples)]
    alpha = (1 - confidence) / 2
    interval = [math.exp(quantile(bootstraps, alpha)), math.exp(quantile(bootstraps, 1 - alpha))]
    ratio = math.exp(statistics.fmean(logs))
    wins = sum(pair["baseline"] > pair["candidate"] for pair in pairs)
    losses = sum(pair["baseline"] < pair["candidate"] for pair in pairs)
    return {
        "pairs": len(pairs),
        "baseline_median_seconds": statistics.median(pair["baseline"] for pair in pairs),
        "candidate_median_seconds": statistics.median(pair["candidate"] for pair in pairs),
        "baseline_mean_seconds": statistics.fmean(pair["baseline"] for pair in pairs),
        "candidate_mean_seconds": statistics.fmean(pair["candidate"] for pair in pairs),
        "paired_geometric_mean_speedup": ratio,
        "paired_median_speedup": statistics.median(math.exp(value) for value in logs),
        "paired_geometric_mean_time_reduction": 1 - 1 / ratio,
        "confidence": confidence,
        "bootstrap_speedup_interval": interval,
        "bootstrap_time_reduction_interval": [1 - 1 / interval[0], 1 - 1 / interval[1]],
        "bootstrap_resamples": resamples,
        "bootstrap_seed": seed,
        "wins": wins,
        "losses": losses,
        "ties": len(pairs) - wins - losses,
        "exact_two_sided_sign_p": exact_sign_test(wins, losses),
        "log_ratios": logs,
        "order": {
            order: {
                "pairs": len(selected),
                "geometric_mean_speedup": math.exp(statistics.fmean(math.log(pair["baseline"] / pair["candidate"]) for pair in selected)),
            }
            for order in ("AB", "BA")
            if (selected := [pair for pair in pairs if pair.get("order") == order])
        },
    }


def paired_count_statistics(pairs, confidence=0.99, resamples=20000, seed=0):
    if any(pair[variant] <= 0 for pair in pairs for variant in ("baseline", "candidate")):
        return {"pairs": len(pairs), "note": "At least one count is zero; paired ratio statistics omitted."}
    statistics_result = paired_statistics(pairs, confidence, resamples, seed)
    replacements = {"seconds": "count", "speedup": "ratio", "time_reduction": "count_reduction"}
    result = {}
    for name, value in statistics_result.items():
        for old, new in replacements.items():
            name = name.replace(old, new)
        result[name] = value
    result["order"] = {
        order: {"pairs": values["pairs"], "geometric_mean_ratio": values["geometric_mean_speedup"]}
        for order, values in statistics_result["order"].items()
    }
    return result


def analyze(args):
    directory = Path(args.directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["state"] != "complete":
        raise ValueError(f"refusing to analyze incomplete run ({manifest['state']})")
    if manifest["variant_sha256"] != manifest["variant_sha256_after"]:
        raise ValueError("variant inputs changed during the run")
    if manifest.get("recorded_file_sha256") != manifest.get("recorded_file_sha256_after"):
        raise ValueError("recorded immutable inputs changed during the run")
    samples = json.loads((directory / "samples.json").read_text())
    grouped = {}
    cpu_grouped = {}
    metric_definitions = manifest["configuration"].get("metric_files", {})
    metric_grouped = {name: {} for name in metric_definitions}
    for sample in samples:
        if sample["stage"] != "measurement":
            continue
        if sample["returncode"] or not sample["executable_unchanged"]:
            raise ValueError("unsuccessful measurement exists")
        pair = grouped.setdefault(sample["pair"], {"order": sample["order"]})
        if sample["variant"] in pair:
            raise ValueError("duplicate variant in measurement pair")
        pair[sample["variant"]] = sample["wall_ns"] / 1e9
        cpu_pair = cpu_grouped.setdefault(sample["pair"], {"order": sample["order"]})
        cpu_pair[sample["variant"]] = sample["user_seconds"] + sample["system_seconds"]
        for name, groups in metric_grouped.items():
            if name not in sample.get("metrics", {}):
                raise ValueError(f"measurement is missing metric {name!r}")
            metric_pair = groups.setdefault(sample["pair"], {"order": sample["order"]})
            metric_pair[sample["variant"]] = sample["metrics"][name]
    if len(grouped) != manifest["pairs"] or any(set(pair) != {"baseline", "candidate", "order"} for pair in grouped.values()):
        raise ValueError("missing or malformed measurement pair")
    result = paired_statistics(list(grouped.values()), args.confidence, args.resamples, args.seed)
    result["child_cpu_seconds"] = (
        paired_statistics(list(cpu_grouped.values()), args.confidence, args.resamples, args.seed)
        if all(pair[variant] > 0 for pair in cpu_grouped.values() for variant in ("baseline", "candidate"))
        else {"note": "At least one sample has zero recorded child CPU time; ratio statistics omitted."}
    )
    result["phase"] = manifest["phase"]
    result["variant_sha256"] = manifest["variant_sha256"]
    if metric_definitions:
        result["metrics"] = {
            name: {
                "format": definition["format"],
                "event": definition.get("event", "Ir"),
                "scope": "Instrumented Cargo process only; child rustc, linker, build-script, and test processes are excluded (--trace-children=no).",
                "statistics": paired_count_statistics(list(metric_grouped[name].values()), args.confidence, args.resamples, args.seed),
                "acceptance": "No acceptance decision. Instruction comparisons screen candidates; confirm native wall time and correctness independently.",
            }
            for name, definition in metric_definitions.items()
        }
    result["screen"] = {
        "minimum_pairs": args.minimum_pairs,
        "minimum_time_reduction": args.minimum_improvement,
        "alpha": 1 - args.confidence,
        "passes": (
            result["pairs"] >= args.minimum_pairs
            and result["bootstrap_speedup_interval"][0] > 1
            and result["exact_two_sided_sign_p"] <= 1 - args.confidence
            and result["paired_geometric_mean_time_reduction"] >= args.minimum_improvement
            and all(value["geometric_mean_speedup"] > 1 for value in result["order"].values())
        ),
        "note": "This screens one workload only. Require an independently run confirmation batch, correctness validation, and regression checks before a PR performance claim. Repeated candidate selection invalidates treating exploratory p-values as confirmatory evidence.",
    }
    if metric_definitions:
        result["screen"]["measurement_kind"] = "instrumented wall time"
        result["screen"]["note"] += " Callgrind elapsed times are instrumented costs, not native dev-loop timings; this screen cannot establish a native wall-time improvement."
    atomic_json(directory / "analysis.json", result)
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    runner = subparsers.add_parser("run")
    runner.add_argument("--config", required=True)
    runner.add_argument("--output", required=True, help="new directory; existing directories are rejected")
    runner.add_argument("--phase", required=True, choices=("exploratory", "confirmation"))
    runner.add_argument("--pairs", type=int, default=30)
    runner.add_argument("--warmup-pairs", type=int, default=2)
    runner.add_argument("--seed", type=int, required=True)
    runner.set_defaults(function=run)
    analyzer = subparsers.add_parser("analyze")
    analyzer.add_argument("directory")
    analyzer.add_argument("--confidence", type=float, default=0.99)
    analyzer.add_argument("--resamples", type=int, default=20000)
    analyzer.add_argument("--seed", type=int, default=1701)
    analyzer.add_argument("--minimum-pairs", type=int, default=30)
    analyzer.add_argument("--minimum-improvement", type=float, default=0.01)
    analyzer.set_defaults(function=analyze)
    arguments = parser.parse_args()
    if arguments.operation == "run" and (arguments.pairs < 1 or arguments.warmup_pairs < 0):
        parser.error("pairs must be positive and warmup-pairs nonnegative")
    if arguments.operation == "analyze" and (not 0 < arguments.confidence < 1 or arguments.resamples < 100):
        parser.error("confidence must be between 0 and 1; resamples must be at least 100")
    arguments.function(arguments)


if __name__ == "__main__":
    main()
