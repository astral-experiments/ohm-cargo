#!/usr/bin/env python3
"""Run the four prospectively specified production instruction confirmations."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

BENCH = Path(__file__).resolve().parent
if BENCH.name == "frozen":
    BENCH = BENCH.parent
ROOT = BENCH.parents[1]
PRODUCTION = ROOT / "work/production-build/results"
CORE_PATH = BENCH / "frozen/paired.py"
spec = importlib.util.spec_from_file_location("frozen_paired", CORE_PATH)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
PROTOCOL = BENCH / "protocol-followon-candidates.md"
UV_COMMIT = "3d82a6ad5a7eab8c68236553b7846517767c4b61"
BASELINE_SHA = "63495905e7b0b11ad99fa4c2c2674e43657b9902a2e3142ef735fd83efa44cf8"
CANDIDATES = {
    "lazy-git": {
        "sha256": "b54037b8f4041b7add52dcc9ad86357e7d8a86953a35c64e3d76718b0fed7cfd",
        "tree": "c692e3c07d295e596b9f10eb4b1c89bb498caf68",
        "patch": BENCH / "patches/lazy-git-final-3707975b6b13.patch",
        "patch_sha256": "3707975b6b134ecce3c811963ffe65a96c1c564e9000ae4255d1bdd56cb76deb",
    },
    "path-cache": {
        "sha256": "c060facdbaae756453968d6eaef1c5ab71c127d15c329a8453e260ef3064c583",
        "tree": "b0dfb3fe2cfd8d310efa04a345f58886296f712a",
        "patch": ROOT / "work/patches/path-cache.patch",
        "patch_sha256": "0ad07b5922f9fdd60f772368e8621c679f1fb0163c245fdd484aee58cd599bb0",
    },
}
PLAN = [
    ("lazy-git", "check", 2026102121),
    ("lazy-git", "test", 2026102122),
    ("path-cache", "check", 2026102128),
    ("path-cache", "test", 2026102129),
]
NOT_FRESH = re.compile(r"(?m)^\s*(?:Compiling|Checking|Running)\s|^error(?:\[|:)")


def read_json(path):
    return json.loads(Path(path).read_text())


def emit(kind, **values):
    print(json.dumps({"at": core.utc_now(), "event": kind, **values}), flush=True)


def uv_identity():
    def git(*args):
        return subprocess.check_output(["git", "-C", str(ROOT / "work/uv"), *args], text=True).strip()
    identity = {"commit": git("rev-parse", "HEAD"), "tracked_status": git("status", "--porcelain=v1", "--untracked-files=no")}
    if identity != {"commit": UV_COMMIT, "tracked_status": ""}:
        raise RuntimeError(f"uv must remain pinned and unchanged: {identity}")
    return identity


def compiler_processes():
    found = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            name = (proc / "comm").read_text().strip()
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
        if (name in {"cargo", "rustc", "rustdoc", "cc", "cc1", "cc1plus", "c++", "clang", "clang++", "ld", "ld.lld", "rust-lld"}
                or name.startswith(("cargo-pr175", "callgrind", "build-script", "testsuite-"))):
            found.append({"pid": int(proc.name), "comm": name})
    return found


def require_quiet():
    processes = compiler_processes()
    if processes:
        raise RuntimeError(f"compiler/test/profiler processes already running: {processes}")


def check_fresh_log(path):
    text = Path(path).read_text(errors="replace")
    if NOT_FRESH.search(text) or "Finished " not in text:
        raise RuntimeError(f"fresh-workload output check failed: {path}")


def audit_complete(directory, expected_seed=None):
    """Check final input hashes and every retained invocation; do not infer effects."""
    directory = Path(directory)
    manifest = read_json(directory / "manifest.json")
    samples = read_json(directory / "samples.json")
    assert manifest["state"] == "complete"
    assert manifest["pairs"] == 12 and manifest["warmup_pairs"] == 2
    if expected_seed is not None:
        assert manifest["seed"] == expected_seed
    assert len(samples) == 28
    assert manifest["variant_sha256"] == manifest["variant_sha256_after"]
    assert manifest["recorded_file_sha256"] == manifest["recorded_file_sha256_after"]
    assert core.sha256(manifest["configuration_path"]) == manifest["configuration_sha256"]
    for name, expected in manifest["variant_sha256"].items():
        assert core.sha256(manifest["variant_paths"][name]) == expected
    for path, expected in manifest["recorded_file_sha256"].items():
        assert core.sha256(path) == expected, path
    profiles = 0
    for sample in samples:
        assert sample["returncode"] == 0 and sample["executable_unchanged"]
        assert sample["installed_sha256"] == manifest["variant_sha256"][sample["variant"]]
        assert sample["prepare"]["returncode"] == 0
        check_fresh_log(sample["stderr"])
        check_fresh_log(sample["prepare"]["stderr"])
        assert "--trace-children=no" in sample["command"]
        if "test" in sample["command"]:
            assert "--no-run" in sample["command"]
        for metric in sample["metric_files"].values():
            assert core.sha256(metric["path"]) == metric["sha256"], metric["path"]
            profiles += 1
    require_quiet()
    return {"completed_at": core.utc_now(), "state": "passed", "directory": str(directory),
            "invocations_verified": len(samples), "profile_hashes_verified": profiles,
            "variant_sha256": manifest["variant_sha256"], "immutable_inputs_verified": len(manifest["recorded_file_sha256"]),
            "uv": uv_identity(), "fresh_log_check": "Every measurement, warmup and preparation succeeded and contains Finished without Compiling, Checking, Running, or error lines.",
            "scope": "Input/log integrity only; Cargo-only instruction scope remains unchanged."}


def child_environment(config):
    env = os.environ.copy()
    for key, value in config["env"].items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = str(value)
    return env


def preflight(config, output):
    output.mkdir(exist_ok=False)
    before = uv_identity()
    records = []
    env = child_environment(config)
    trace_tool = shutil.which("strace")
    if not trace_tool:
        raise RuntimeError("strace is required for the native freshness preflight")
    for name in ("baseline", "candidate"):
        require_quiet()
        source = Path(config["variants"][name])
        canonical = Path(config["canonical_executable"])
        core.install_variant(source, canonical)
        assert core.sha256(canonical) == core.sha256(source)
        command = [core.substitute(x, {"cargo": canonical}) for x in config["prepare_command"]]
        warm = core.run_command(command, config["cwd"], env, output / f"{name}.warm.stdout", output / f"{name}.warm.stderr")
        if warm["returncode"]:
            raise RuntimeError(f"native preflight warm command failed: {name}")
        trace_path = output / f"{name}.execve.log"
        trace = core.run_command([trace_tool, "-f", "-e", "trace=execve", "-s", "4096", "-o", str(trace_path), "--", *command],
                                 config["cwd"], env, output / f"{name}.trace.stdout", output / f"{name}.trace.stderr")
        if trace["returncode"]:
            raise RuntimeError(f"native preflight exec trace failed: {name}")
        check_fresh_log(trace["stderr"])
        executable_paths = re.findall(r'execve\("([^"\\]*)"', trace_path.read_text())
        unexpected = [x for x in executable_paths if x != str(canonical) and Path(x).name != "taskset"]
        if not executable_paths or str(canonical) not in executable_paths or unexpected:
            raise RuntimeError(f"unexpected subprocesses in fresh native preflight: {unexpected}")
        assert core.sha256(canonical) == core.sha256(source)
        require_quiet()
        records.append({"variant": name, "binary_sha256": core.sha256(source), "warm": warm, "trace": trace,
                        "trace_path": str(trace_path), "trace_sha256": core.sha256(trace_path), "execve_paths": executable_paths,
                        "unexpected_subprocesses": unexpected})
    report = {"state": "passed", "completed_at": core.utc_now(), "uv_before": before, "uv_after": uv_identity(),
              "canonical_executable": config["canonical_executable"], "configured_environment": config["env"],
              "machine": core.machine_metadata(), "records": records}
    core.atomic_json(output / "report.json", report)
    return output / "report.json"


def derive(candidate, workflow, preflight_report):
    original_path = BENCH / f"{workflow}-build-output-pr175-production-ir.json"
    original = read_json(original_path)
    config = json.loads(json.dumps(original))
    info = CANDIDATES[candidate]
    config["variants"]["candidate"] = str(PRODUCTION / f"cargo-pr175-{candidate}")
    config["record_files"] = [p for p in config["record_files"] if "build-output-remap" not in p]
    config_path = BENCH / f"{workflow}-{candidate}-pr175-production-ir.json"
    config["record_files"].extend(map(str, [
        info["patch"], PROTOCOL, Path(__file__).resolve(), original_path,
        PRODUCTION / f"cargo-pr175-{candidate}.build.json", PRODUCTION / f"cargo-pr175-{candidate}.strip.json",
        PRODUCTION / f"pr175-{candidate}.source.patch", PRODUCTION / f"provenance-pr175-{candidate}.json",
        preflight_report, config_path,
    ]))
    for field in original:
        if field not in {"variants", "record_files"}:
            assert original[field] == config[field]
    return config_path, config


def result_gate(directory):
    analysis = read_json(directory / "analysis.json")
    stats = analysis["metrics"]["cargo_ir"]["statistics"]
    checks = {
        "fixed_12_pairs": stats["pairs"] == 12,
        "at_least_one_percent": stats["paired_geometric_mean_count_reduction"] >= 0.01,
        "positive_99_percent_lower_bound": stats["bootstrap_count_reduction_interval"][0] > 0,
        "two_sided_sign_p_at_most_0_01": stats["exact_two_sided_sign_p"] <= 0.01,
        "both_orders_positive": set(stats["order"]) == {"AB", "BA"} and all(v["geometric_mean_ratio"] > 1 for v in stats["order"].values()),
    }
    return {"passes_instruction_gate": all(checks.values()), "gate_checks": checks, "statistics": stats,
            "scope": "Cargo-only instruction gate; no native wall-time inference, no pooling."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lease-granted", action="store_true")
    args = parser.parse_args()
    if not args.lease_granted:
        print(json.dumps({"plan": PLAN, "note": "Execution requires the explicitly granted local measurement lease."}))
        return
    if Path("/").stat().st_uid == 65534:
        raise RuntimeError("Run on the authorized ordinary host; sandbox ownership remapping disables the shared cache")
    assert core.sha256(CORE_PATH) == "50d0cb2d4f595ccfa72d463fedb3ff4dadf9dfc1446c749d482d9ede8418c7cf"
    assert core.sha256(PRODUCTION / "cargo-pr175") == BASELINE_SHA
    baseline_provenance = read_json(PRODUCTION / "provenance-pr175.json")
    compare_fields = ("source", "target", "command", "compiler_input_sha256", "environment", "affinity", "cargo_version", "rustc_version", "inherited_cargo_configuration_sha256", "inherited_native_build_environment")
    for candidate, info in CANDIDATES.items():
        assert core.sha256(PRODUCTION / f"cargo-pr175-{candidate}") == info["sha256"]
        assert core.sha256(info["patch"]) == info["patch_sha256"]
        metadata = read_json(PRODUCTION / f"cargo-pr175-{candidate}.build.json")
        assert metadata["observed_source_tree"] == info["tree"]
        provenance = read_json(PRODUCTION / f"provenance-pr175-{candidate}.json")
        assert all(baseline_provenance.get(k) == provenance.get(k) for k in compare_fields)
        assert core.sha256(PRODUCTION / f"pr175-{candidate}.source.patch") == metadata["observed_diff_sha256"]
        strip = read_json(PRODUCTION / f"cargo-pr175-{candidate}.strip.json")
        assert strip["stripped_sha256"] == info["sha256"]
    for candidate, workflow, seed in PLAN:
        assert str(seed) in PROTOCOL.read_text()
        assert not (BENCH / f"{workflow}-{candidate}-pr175-production-ir.json").exists()
        assert not (BENCH / "results" / f"{workflow}-{candidate}-pr175-production-ir-confirmation").exists()
    require_quiet()
    emit("prior_test_build_integrity_audit_started")
    audit = audit_complete(BENCH / "results/test-build-output-pr175-production-ir-confirmation")
    core.atomic_json(BENCH / "results/test-build-output-pr175-production-ir-integrity.json", audit)
    emit("prior_test_build_integrity_audit_passed", invocations=audit["invocations_verified"], profiles=audit["profile_hashes_verified"])
    summaries = []
    for candidate, workflow, seed in PLAN:
        label = f"{workflow}-{candidate}-pr175-production-ir"
        preflight_dir = BENCH / "results" / f"{label}-preflight"
        config_path, config = derive(candidate, workflow, preflight_dir / "report.json")
        emit("preflight_started", candidate=candidate, workflow=workflow)
        preflight(config, preflight_dir)
        with config_path.open("x") as stream:
            json.dump(config, stream, indent=2)
            stream.write("\n")
        output = BENCH / "results" / f"{label}-confirmation"
        emit("fixed_batch_started", candidate=candidate, workflow=workflow, pairs=12, warmup_pairs=2, seed=seed,
             configuration_sha256=core.sha256(config_path), output=str(output))
        runner_log = BENCH / "results" / f"{label}-runner.log"
        with runner_log.open("x") as stream:
            subprocess.run([sys.executable, str(CORE_PATH), "run", "--config", str(config_path), "--output", str(output),
                            "--phase", "confirmation", "--pairs", "12", "--warmup-pairs", "2", "--seed", str(seed)],
                           stdout=stream, stderr=subprocess.STDOUT, check=True)
        shutil.copyfile(runner_log, output / "runner.log")
        audit = audit_complete(output, seed)
        core.atomic_json(output / "integrity.json", audit)
        with (output / "analysis-stdout.json").open("w") as stream:
            subprocess.run([sys.executable, str(CORE_PATH), "analyze", str(output), "--confidence", "0.99", "--resamples", "20000", "--seed", "1701"],
                           stdout=stream, check=True)
        gate = result_gate(output)
        core.atomic_json(output / "instruction-gate.json", gate)
        summaries.append({"candidate": candidate, "workflow": workflow, "directory": str(output), **gate})
        core.atomic_json(BENCH / "results/followon-production-ir-summary.json", summaries)
        emit("fixed_batch_complete", **summaries[-1])
    require_quiet()
    emit("all_batches_complete", batches=len(summaries), uv=uv_identity())


if __name__ == "__main__":
    main()
