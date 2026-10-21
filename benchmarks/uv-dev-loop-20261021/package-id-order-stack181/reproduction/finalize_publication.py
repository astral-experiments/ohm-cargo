"""Append exact-source terminal CI, retaining the initial artifact index privately."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import shutil

WORK = Path(__file__).resolve().parents[1]
OUT = WORK / "pr-evidence/package-id-order-stack181"
HISTORY = WORK / "pr-evidence/package-id-order-stack181-initial-assembly"
CI = WORK / "instruction-only-source-publication-20261021/package-id-order/ci-complete.json"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")


assert not HISTORY.exists()
initial_sha = sha(OUT / "manifest.json")
assert initial_sha == "cf883b34c80edc6ed1bf76bde1aca3c2eb9b2a24b6adfc52edd7cda9b26e6f74"
initial = read(OUT / "manifest.json")
for name, entry in initial["files"].items():
    path = OUT / name
    assert path.stat().st_size == entry["bytes"] and sha(path) == entry["sha256"]
ci = read(CI)
request = read(WORK / "package-id-order-publication/publication-request.json")
assert ci["status"] == "passed" and ci["conclusion"] == "success"
assert ci["source_commit"] == request["commit"] and ci["source_tree"] == request["tree"]
assert ci["parent_commit"] == request["parent"] and ci["head_branch"] == request["branch"]
assert ci["event"] == "workflow_dispatch" and ci["run_id"] == 39693613521
assert {row["name"] for row in ci["required_jobs"]} == set(request["ci"]["required_jobs"])
assert len(ci["required_jobs"]) == 8
assert all(row["status"] == "completed" and row["conclusion"] == "success" and row["run_id"] == ci["run_id"] for row in ci["required_jobs"])
assert ci["native_effects_and_regressions_unverified"] is True
assert sha(CI) == "cb8cd2cfa6343d1c5c970d39a0fcd3cbb4e6ec5e86cb620a2c57c29751dac2d8"

HISTORY.mkdir()
for name in ("README.md", "REPRODUCE.md", "assembly-audit.json"):
    shutil.copy2(OUT / name, HISTORY / name)
    assert sha(HISTORY / name) == initial["files"][name]["sha256"]
os.rename(OUT / "manifest.json", HISTORY / "manifest.json")
assert sha(HISTORY / "manifest.json") == initial_sha
shutil.copy2(CI, OUT / "ci/complete.json")
assert sha(OUT / "ci/complete.json") == sha(CI)

readme = (OUT / "README.md").read_text()
old = "Exact-source CI is mandatory before a draft; the initial dispatch is retained in `ci/dispatch.json`, and terminal exact-head validation must be added before publication qualification. The eight required jobs are Rustfmt, both Clippy jobs, both Cargo test jobs, Workspace tests, Resolver tests and Schema tests. The optional APFS replay is disabled."
new = "Exact-source [CI run 39693613521](https://github.com/astral-sh/ohm-cargo/actions/runs/39693613521) completed successfully at this candidate commit: all eight required jobs passed (Rustfmt, both Clippy jobs, both Cargo test jobs, Workspace tests, Resolver tests and Schema tests). The terminal exact-head receipt is `ci/complete.json`; the optional APFS replay was skipped as configured."
assert readme.count(old) == 1
(OUT / "README.md").write_text(readme.replace(old, new))
reproduce = (OUT / "REPRODUCE.md").read_text()
old = "Exact-source green CI and final root qualification must accompany any draft."
new = "Exact-source CI is complete and green in `ci/complete.json`; final artifact review and root qualification still precede draft publication."
assert reproduce.count(old) == 1
(OUT / "REPRODUCE.md").write_text(reproduce.replace(old, new))
shutil.copy2(Path(__file__).resolve(), OUT / "reproduction/finalize_publication.py")
save(OUT / "publication-status.json", {
    "status": "ready-for-independent-artifact-review",
    "finalized_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "source_commit": ci["source_commit"], "source_tree": ci["source_tree"],
    "CI_run_id": ci["run_id"], "CI_sha256": sha(CI), "required_CI_jobs_passed": 8,
    "local_focused_correctness_tests_passed": 13,
    "CI_focused_test_log_names_not_asserted_by_this_receipt": True,
    "authoritative_effect_review_sha256": sha(OUT / "accepted-analysis/review.json"),
    "qualified_instruction_claims": ["check"],
    "native_time_and_regressions_unverified": True,
    "original_complete_protocol_not_satisfied": True,
    "publication_criterion_amendment_sha256": sha(OUT / "policy/amendment.md"),
    "amendment_root_acceptance_sha256": sha(OUT / "policy/root-acceptance.json"),
    "initial_manifest_retained_privately_sha256": initial_sha,
    "initial_assembly_receipt_is_historical_not_a_current_CI_status": True,
    "archive_bytes_unchanged": sha(OUT / "ir-public-subset.tar.gz") == "51c04eb0860efff81baf046f6d2bace0bc9f07663315c29ef7c9e795e2923682",
    "no_new_workload_statistics_native_effects_or_external_actions": True,
})
files = {str(path.relative_to(OUT)): {"sha256": sha(path), "bytes": path.stat().st_size}
         for path in sorted(OUT.rglob("*")) if path.is_file()}
save(OUT / "manifest.json", {"files": files, "scope": "Final local publication artifact with exact-source terminal CI; SHA256SUMS additionally covers this manifest."})
with (OUT / "SHA256SUMS").open("x") as stream:
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            stream.write(sha(path) + "  " + str(path.relative_to(OUT)) + "\n")
save(HISTORY / "retention.json", {"initial_manifest_sha256": initial_sha,
                                 "initial_docs_retained_before_CI_wording_update": True,
                                 "final_manifest_sha256": sha(OUT / "manifest.json"),
                                 "final_SHA256SUMS_sha256": sha(OUT / "SHA256SUMS")})
print(json.dumps({"manifest_sha256": sha(OUT / "manifest.json"),
                  "SHA256SUMS_sha256": sha(OUT / "SHA256SUMS"),
                  "CI_sha256": sha(CI), "files_before_manifest_and_checksums": len(files),
                  "initial_manifest_retained_at": str(HISTORY / "manifest.json")}, indent=2))
