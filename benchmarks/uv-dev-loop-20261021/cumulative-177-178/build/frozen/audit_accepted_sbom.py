#!/usr/bin/env python3
"""Verify collected build artifacts without running Cargo or a benchmark."""

import datetime
import hashlib
import json
from pathlib import Path
import runpy
import shlex
import sys


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
FROZEN = ROOT / "frozen/accepted-sbom"
INPUTS = json.loads((FROZEN / "manifest.json").read_text())
BASELINE = json.loads((RESULTS / "provenance.json").read_text())
COMMON = (
    "host", "source", "target", "source_commit", "source_tree", "source_bundle_sha256",
    "compiler_input_sha256", "rustc_version", "cargo_version", "cc_version", "environment",
    "command", "inherited_cargo_configuration_sha256", "inherited_native_build_environment",
    "affinity", "approximation",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rustc_settings(variant):
    text = (RESULTS / f"{variant}.stderr").read_text()
    lines = [line.strip() for line in text.splitlines()
             if "--crate-name cargo " in line and "src/bin/cargo/main.rs" in line]
    assert len(lines) == 1, (variant, len(lines))
    command = shlex.split(lines[0].removeprefix("Running `").removesuffix("`"))
    codegen = [command[i + 1] for i, part in enumerate(command[:-1]) if part == "-C"]
    cfg = [command[i + 1] for i, part in enumerate(command[:-1]) if part == "--cfg"]
    assert {"opt-level=3", "lto=thin", "codegen-units=1", "debuginfo=1"} <= set(codegen)
    assert {'feature="all-static"', 'feature="ohm-defaults"'} <= set(cfg)
    assert "profile-use" not in text and "profile-generate" not in text
    return {
        "codegen": [part for part in codegen
                    if not part.startswith(("metadata=", "extra-filename="))],
        "cfg": cfg,
    }


provenance = json.loads((RESULTS / "provenance-accepted-sbom.json").read_text())
for key in COMMON:
    assert provenance[key] == BASELINE[key], key
assert provenance["driver_sha256"] == INPUTS["driver_sha256"]
assert sha(ROOT / "build_driver_accepted_sbom.py") == INPUTS["driver_sha256"]
assert sha(FROZEN / "build_driver_accepted_sbom.py") == INPUTS["driver_sha256"]
assert provenance["frozen_input_manifest_sha256"] == sha(FROZEN / "manifest.json")
assert provenance["patch_sha256"] == INPUTS["patch_sha256"]
assert provenance["expected_variant_source_trees"] == {
    name: value["tree"] for name, value in INPUTS["expected_variants"].items()
}
helper = ROOT.parent / "benchmark/strip_binaries.py"
assert sha(helper) == provenance["strip_helper_sha256"] == INPUTS["strip_helper_sha256"]
allocated_sections = runpy.run_path(str(helper))["allocated_sections"]
baseline_record = json.loads((RESULTS / "cargo-pr175.build.json").read_text())
baseline_settings = rustc_settings("pr175")
variants = sys.argv[1:] or list(INPUTS["expected_variants"])
records = []
for variant in variants:
    expected = INPUTS["expected_variants"][variant]
    name = f"cargo-{variant}"
    record = json.loads((RESULTS / f"{name}.build.json").read_text())
    proof = json.loads((RESULTS / f"{name}.strip.json").read_text())
    status = json.loads((RESULTS / f"{variant}.batch-status.json").read_text())
    assert variant in status["completed_variants"]
    binary = (RESULTS / name).read_bytes()
    assert hashlib.sha256(binary).hexdigest() == proof["stripped_sha256"]
    assert len(binary) == proof["stripped_bytes"]
    assert allocated_sections(binary) == proof["allocated_sections"]
    assert proof["source_sha256"] == proof["original_linker_output_sha256"] == record["original_linker_output_sha256"]
    assert record["observed_source_tree"] == record["expected_source_tree_from_patches"] == expected["tree"]
    assert record["patch_sha256"] == expected["patch_sha256"]
    assert record["embedded_source_commit"] == expected["base"]
    assert record["version"] == baseline_record["version"]
    assert sha(RESULTS / f"{variant}.source.patch") == record["observed_diff_sha256"] == expected["canonical_diff_sha256"]
    for extension in ("stdout", "stderr"):
        assert sha(RESULTS / f"{variant}.{extension}") == record[f"{extension}_sha256"]
    assert rustc_settings(variant) == baseline_settings
    if variant == "pr175-lazy-sbom":
        assert status["state"] == "complete"
        assert set(status["completed_variants"]) == set(INPUTS["expected_variants"])
        assert status["preserved_artifacts_verified"] == len(provenance["preserved_artifact_sha256"])
    records.append({
        "variant": variant,
        "source_tree": expected["tree"],
        "original_linker_output_sha256": record["original_linker_output_sha256"],
        "stripped_sha256": proof["stripped_sha256"],
        "stripped_bytes": len(binary),
        "verified_allocated_sections": len(proof["allocated_sections"]),
        "actual_rustc_settings": baseline_settings,
    })

report = {
    "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "scope": "Collected binary, source, log, strip, compiler, and build-setting verification; no Cargo or benchmarks run.",
    "common_input_fields": list(COMMON),
    "all_common_inputs_match": True,
    "frozen_input_manifest_sha256": sha(FROZEN / "manifest.json"),
    "build_driver_sha256": INPUTS["driver_sha256"],
    "collector_sha256": sha(ROOT / "collect_variant.py"),
    "audit_script_sha256": sha(Path(__file__)),
    "provenance_sha256": sha(RESULTS / "provenance-accepted-sbom.json"),
    "records": records,
}
destination = RESULTS / ("audit-accepted-sbom.json" if len(variants) == 2 else f"audit-{variants[0]}.json")
with destination.open("x") as stream:
    stream.write(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
