#!/usr/bin/env python3
"""Verify the collected host2 pair without executing Cargo or benchmarks."""

import datetime
import hashlib
import json
from pathlib import Path
import runpy
import shlex
import sys


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
FROZEN = ROOT / "frozen"
INPUTS = json.loads((FROZEN / "manifest.json").read_text())
REFERENCE = json.loads((FROZEN / "reference-host7-provenance.json").read_text())
COMMON = (
    "source", "target", "source_commit", "source_tree", "source_bundle_sha256",
    "compiler_input_sha256", "rustc_version", "cargo_version", "cc_version", "environment",
    "command", "inherited_cargo_configuration_sha256", "inherited_native_build_environment",
    "affinity", "approximation",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rustc_settings(directory, variant):
    text = (directory / f"{variant}.stderr").read_text()
    lines = [line.strip() for line in text.splitlines()
             if "--crate-name cargo " in line and "src/bin/cargo/main.rs" in line]
    assert len(lines) == 1, (variant, len(lines))
    command = shlex.split(lines[0].removeprefix("Running `").removesuffix("`"))
    codegen = [command[i + 1] for i, part in enumerate(command[:-1]) if part == "-C"]
    cfg = [command[i + 1] for i, part in enumerate(command[:-1]) if part == "--cfg"]
    assert {"opt-level=3", "lto=thin", "codegen-units=1", "debuginfo=1"} <= set(codegen)
    assert {'feature="all-static"', 'feature="ohm-defaults"'} <= set(cfg)
    assert "profile-use" not in text and "profile-generate" not in text
    return {"codegen": [part for part in codegen
                        if not part.startswith(("metadata=", "extra-filename="))], "cfg": cfg}


provenance = json.loads((RESULTS / "provenance.json").read_text())
assert provenance["host"] == "charlie-oss-2"
assert provenance["cohort"] == INPUTS["cohort"] == "host2-current-stack"
for key in COMMON:
    assert provenance[key] == REFERENCE[key], key
assert provenance["reference_host7_provenance_sha256"] == INPUTS["reference_host7_provenance_sha256"] == sha(FROZEN / "reference-host7-provenance.json")
assert provenance["driver_sha256"] == INPUTS["driver_sha256"] == sha(FROZEN / "build_driver_host2_current_stack.py") == sha(ROOT / "build_driver_host2_current_stack.py")
assert provenance["frozen_input_manifest_sha256"] == sha(FROZEN / "manifest.json")
assert provenance["patch_sha256"] == INPUTS["patch_sha256"]
for filename, expected_hash in INPUTS["patch_sha256"].items():
    assert sha(FROZEN / filename) == expected_hash
assert provenance["expected_variant_source_trees"] == {
    name: value["tree"] for name, value in INPUTS["expected_variants"].items()
}
assert provenance["source_revision_by_variant"] == {
    name: value["source_content_ref"] for name, value in INPUTS["expected_variants"].items()
}
prior = ROOT.parent / "host2"
assert INPUTS["preceding_cohort_manifest_sha256"] == sha(prior / "frozen/manifest.json")
assert INPUTS["preceding_driver_sha256"] == sha(prior / "frozen/build_driver_host2_pr175_sbom.py")
assert provenance["preserved_artifact_sha256"]["host2-pr175-sbom-inputs.json"] == INPUTS["preceding_cohort_manifest_sha256"]
assert provenance["preserved_artifact_sha256"]["build_driver_host2_pr175_sbom.py"] == INPUTS["preceding_driver_sha256"]
assert provenance["preserved_artifact_sha256"]["provenance-host2-pr175-sbom.json"] == sha(prior / "results/provenance.json")
assert provenance["preceding_manifest_records"] == {
    f"cargo-{variant}": json.loads((prior / "results" / f"cargo-{variant}.build.json").read_text())
    for variant in ("pr175", "pr175-lazy-sbom")
}
helper = FROZEN / "strip_binaries.py"
assert sha(helper) == provenance["strip_helper_sha256"] == INPUTS["strip_helper_sha256"]
allocated_sections = runpy.run_path(str(helper))["allocated_sections"]
shared = {key: provenance[key] for key in (
    "compiler_input_sha256", "native_build_tool_sha256", "inherited_cargo_configuration_sha256",
    "execution_environment_sha256", "command", "environment",
)}
assert hashlib.sha256(json.dumps(shared, sort_keys=True).encode()).hexdigest() == provenance["common_build_inputs_sha256"]
baseline_record = json.loads((RESULTS / "cargo-stack179-current.build.json").read_text())
baseline_settings = rustc_settings(RESULTS, "stack179-current")
assert baseline_settings == rustc_settings(ROOT.parent / "results", "pr175")
variants = sys.argv[1:] or list(INPUTS["expected_variants"])
records = []
for variant in variants:
    expected = INPUTS["expected_variants"][variant]
    name = f"cargo-{variant}"
    record = json.loads((RESULTS / f"{name}.build.json").read_text())
    proof = json.loads((RESULTS / f"{name}.strip.json").read_text())
    status = json.loads((RESULTS / f"{variant}.batch-status.json").read_text())
    occupancy = json.loads((RESULTS / f"{variant}.occupancy.json").read_text())
    assert not occupancy["other_workloads"]
    assert variant in status["completed_variants"]
    binary = (RESULTS / name).read_bytes()
    assert hashlib.sha256(binary).hexdigest() == proof["stripped_sha256"]
    assert len(binary) == proof["stripped_bytes"]
    assert allocated_sections(binary) == proof["allocated_sections"]
    assert proof["source_sha256"] == proof["original_linker_output_sha256"] == record["original_linker_output_sha256"]
    assert record["observed_source_tree"] == record["expected_source_tree_from_patches"] == expected["tree"]
    assert record["patch_sha256"] == expected["patch_sha256"]
    assert record["source_content_ref"] == expected["source_content_ref"]
    assert record["embedded_source_commit"] == expected["base"]
    assert record["common_build_inputs_sha256"] == provenance["common_build_inputs_sha256"]
    assert record["version"] == baseline_record["version"]
    assert sha(RESULTS / f"{variant}.source.patch") == record["observed_diff_sha256"] == expected["canonical_diff_sha256"]
    for extension in ("stdout", "stderr"):
        assert sha(RESULTS / f"{variant}.{extension}") == record[f"{extension}_sha256"]
    assert rustc_settings(RESULTS, variant) == baseline_settings
    if variant == "stack176-current":
        assert status["state"] == "complete"
        assert set(status["completed_variants"]) == set(INPUTS["expected_variants"])
        assert status["preserved_artifacts_verified"] == len(provenance["preserved_artifact_sha256"])
        assert len(status["sealed_artifact_sha256"]) == 21
        assert status["preserved_manifest_records_verified"] == 2
        for completed in INPUTS["expected_variants"]:
            completed_name = f"cargo-{completed}"
            completed_proof = json.loads((RESULTS / f"{completed_name}.strip.json").read_text())
            assert status["sealed_artifact_sha256"][f"binaries/{completed_name}"] == completed_proof["source_sha256"]
            assert status["sealed_artifact_sha256"][f"binaries/stripped/{completed_name}"] == sha(RESULTS / completed_name)
            assert status["sealed_artifact_sha256"][f"binaries/stripped/{completed_name}.json"] == sha(RESULTS / f"{completed_name}.strip.json")
            for extension in ("stdout", "stderr", "source.patch", "occupancy.json"):
                assert status["sealed_artifact_sha256"][f"logs/{completed}.{extension}"] == sha(RESULTS / f"{completed}.{extension}")
    records.append({"variant": variant, "source_tree": expected["tree"],
                    "original_linker_output_sha256": record["original_linker_output_sha256"],
                    "stripped_sha256": proof["stripped_sha256"], "stripped_bytes": len(binary),
                    "verified_allocated_sections": len(proof["allocated_sections"]),
                    "common_build_inputs_sha256": record["common_build_inputs_sha256"],
                    "actual_rustc_settings": baseline_settings})

report = {
    "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "cohort": "host2-current-stack",
    "scope": "Collected binary, source, log, strip, compiler, and shared build-input verification; no Cargo or benchmark execution.",
    "host7_reference_fields_except_hostname": list(COMMON),
    "host7_reference_fields_match": True,
    "common_build_inputs_sha256": provenance["common_build_inputs_sha256"],
    "frozen_input_manifest_sha256": sha(FROZEN / "manifest.json"),
    "build_driver_sha256": INPUTS["driver_sha256"],
    "collector_sha256": sha(ROOT / "collect_variant.py"),
    "audit_script_sha256": sha(Path(__file__)),
    "provenance_sha256": sha(RESULTS / "provenance.json"),
    "records": records,
}
destination = RESULTS / ("audit-cohort.json" if len(variants) == 3 else f"audit-{variants[0]}.json")
with destination.open("x") as stream:
    stream.write(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
