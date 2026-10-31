"""Verify the two exact Cargo verdict inventories and their separate pinned Ohm gates."""
import collections
import csv
import gzip
import hashlib
import json
from pathlib import Path

base = Path(__file__).resolve().parent
receipt = json.loads((base / "receipt.json").read_text())
assert receipt["product"] == "761ea115605c34f11a1cd29afd68812c1e1359dd"
assert receipt["product_tree"] == "19c379477ec24be16c82b952dc2e892c0563e2c7"
required = {"Rustfmt", "Schema tests", "Resolver tests", "Workspace tests",
            "Clippy (depot-ubuntu-24.04-8)", "Clippy (depot-macos-15)"}
assert set(receipt["normal_jobs"]) == required
assert all(x["conclusion"] == "success" for x in receipt["normal_jobs"].values())
for platform, expected in [("Linux", (4827, 433, 15)), ("macOS", (4799, 430, 8))]:
    job = receipt["native_full_jobs"][platform]
    assert job["source"] == receipt["product"] and job["source_tree"] == receipt["product_tree"]
    assert job["conclusion"] == "success"
    path = base / (platform + "-verdicts.tsv.gz")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == job["verdict_inventory_sha256"]
    with gzip.open(path, "rt") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    assert len({(r["suite"], r["test"]) for r in rows}) == len(rows)
    counts = collections.Counter((r["suite"], r["verdict"]) for r in rows)
    assert {r["suite"] for r in rows} == set(job["harnesses"]) | set(job["actual_gates"])
    groups = job["harnesses"]
    observed = {r["test"] for r in rows if r["verdict"] == "ok"}
    assert "freshness::native_recheck_reuses_codegen_until_the_root_changes" in observed
    assert all(x in observed for x in job["hotfix_controls"])
    for suite, h in groups.items():
        assert h["result"] == "ok" and h["filtered"] == h["failed"] == 0
        assert counts[suite, "ok"] == h["passed"] and counts[suite, "ignored"] == h["ignored"]
    for group, names in job["actual_gates"].items():
        assert sorted(r["test"] for r in rows if r["suite"] == group and r["verdict"] == "ok") == sorted(names)
    assert job["actual_gates"]["profiles"] == [
        "profile_settings::ohm_default_debuginfo", "profile_settings::ohm_default_debuginfo_respects_overrides"]
    assert set(job["profile_transcript_sha256"]) == set(job["actual_gates"]["profiles"])
    actual = (sum(counts[s, "ok"] for s in groups), sum(counts[s, "ignored"] for s in groups),
              sum(len(ns) for ns in job["actual_gates"].values()))
    assert actual == expected
    print(f"{platform}: {actual[0]} standard passes, {actual[1]} declared ignores, "
          f"0 failed or filtered, {actual[2]} pinned Ohm passes")
