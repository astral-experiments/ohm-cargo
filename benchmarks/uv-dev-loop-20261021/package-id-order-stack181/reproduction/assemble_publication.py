"""Package an explicit, privacy-filtered subset; never run workloads or statistics."""
from pathlib import Path, PurePosixPath
import datetime
import gzip
import hashlib
import io
import json
import re
import shutil
import stat
import tarfile

WORK = Path(__file__).resolve().parents[1]
OUT = WORK / "pr-evidence/package-id-order-stack181"
CONTROLS = WORK / "package-id-order-measurement-controls-v2"
COLLECTION = CONTROLS / "collections/ir"
RAW = COLLECTION / "remote"
ANALYSIS = WORK / "cargo-audit/package-id-order-ir-independent-review/analysis-review"
SOURCE = WORK / "package-id-order-publication"
POLICY = WORK / "qualification-policy/instruction-only-publication-20261021"
ROOT_PUBLICATION = WORK / "instruction-only-source-publication-20261021/package-id-order"
AMENDMENT_REVIEW = WORK / "benchmark-harness-reviews/instruction-only-publication-amendment-review-20261021/review.json"
OPERATIONAL_KEYS = {"occupancy", "process_snapshot", "other_workloads"}
SECRETS = re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
FOREIGN_LOG_DATA = re.compile(rb"(?:AnsiballZ_|falcon-sensor|codex-linux-san|[\"']process_snapshot[\"']\s*:|[\"']other_workloads[\"']\s*:)")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def operational_paths(value, prefix=""):
    result = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = prefix + "/" + key
            if key in OPERATIONAL_KEYS:
                result.append(path)
            result.extend(operational_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(operational_paths(child, prefix + "/" + str(index)))
    return result


def privacy_check(path, data):
    assert not SECRETS.search(data), (str(path), "credential-shaped content")
    if path.suffix == ".json":
        assert not operational_paths(json.loads(data)), (str(path), "process metadata")
    if path.suffix in {".log", ".stdout", ".stderr", ".jsonl", ".csv"}:
        assert not FOREIGN_LOG_DATA.search(data), (str(path), "operational log data")


def copy(name, path):
    data = path.read_bytes()
    privacy_check(path, data)
    target = OUT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
    supplemental[name] = {"source": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


assert not OUT.exists(), "Never overwrite a prior assembly"
transfer = read(COLLECTION / "transfer-manifest.json")
acceptance = read(CONTROLS / "root-ir-acceptance.json")
assert transfer["phase"] == "ir"
assert sha(COLLECTION / "transfer-manifest.json") == acceptance["transfer_manifest_sha256"]
assert sha(COLLECTION / "receipt.json") == acceptance["collection_receipt_sha256"]
assert sha(ANALYSIS / "review.json") == acceptance["review_sha256"] == "1c8e7c91e20aa75a9dbb76a19eea722ea8100c3754fb8f0d0ab9fba4fd12f88a"
assert sha(ANALYSIS / "raw-integrity.json") == acceptance["raw_integrity_sha256"]
assert sha(CONTROLS / "root-ir-acceptance.json") == "a9526fb8354342202206931e0e861435f1798ef7191a6359bf84f7a5f3b88940"
review = read(ANALYSIS / "review.json")
assert review["policy"]["improvement_claims"] == {"check": True, "test": False}
assert review["integrity_status"] == "passed"
amendment = read(AMENDMENT_REVIEW)
root_policy = read(POLICY / "root-acceptance.json")
assert root_policy["independent_review_sha256"] == sha(AMENDMENT_REVIEW)
assert root_policy["amendment_sha256"] == amendment["amendment_sha256"] == sha(POLICY / "amendment.md")
assert root_policy["decision_sha256"] == amendment["decision_sha256"] == sha(POLICY / "decision.json")
assert amendment["cases"]["package-id-order"]["accepted_instruction_claims"] == ["check"]
publication = read(ROOT_PUBLICATION / "code-publication.json")
source = read(SOURCE / "source-commit.json")
assert publication["commit"] == source["commit"] == "bcdd1f30d229eb8c66897799e76167f658126737"
assert publication["tree"] == source["tree"] == "12f12327e7c56fb04386b7cfb4d61d5fd434bfc5"
assert publication["patch_sha256"] == sha(SOURCE / "candidate.diff")

top_controller = {
    "assets.json", "measurement-seal.json", "accepted-production-pair.json", "plans.json",
    "protocol.json", "source-freeze.json", "source-review.json", "input-approval.json",
    "host-assignment.json", "production-schema-map.json", "input-approval.schema.json",
}
selected, omitted = {}, {}
for name, digest in sorted(transfer["files"].items()):
    relative = PurePosixPath(name)
    assert not relative.is_absolute() and ".." not in relative.parts
    path = RAW / name
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode) and not path.is_symlink()
    assert sha(path) == digest
    mandatory = name.startswith(("results/ir-check/", "results/ir-test/", "metadata/ir-check-preflight/", "metadata/ir-test-preflight/", "benchmark/")) or name in {"logs/ir-check-runner.log", "logs/ir-test-runner.log"}
    include = mandatory or name.startswith(("controller/cohort/", "controller/correctness/", "controller/reviewer/", "controller/base-configs/"))
    include |= len(relative.parts) == 2 and relative.parts[0] == "controller" and (path.suffix == ".py" or path.name in top_controller)
    include |= name in {"metadata/setup.json", "delivery.json", "ownership.json"}
    reason = "Operational/history record outside explicit publication subset; original retained privately."
    if include and path.suffix == ".json":
        operations = operational_paths(read(path))
        if operations:
            assert not mandatory, (name, operations)
            include = False
            reason = "Contains occupancy/process_snapshot/other_workloads metadata; omitted in full."
    if "occupancy" in path.name.lower() and path.suffix == ".json":
        assert not mandatory
        include = False
        reason = "Operational occupancy record; omitted in full."
    record = {"sha256": digest, "bytes": info.st_size, "mode": stat.S_IMODE(info.st_mode)}
    if include:
        privacy_check(path, path.read_bytes())
        selected[name] = record
    else:
        omitted[name] = {**record, "reason": reason}
assert len(selected) + len(omitted) == len(transfer["files"]) == 578
profiles = [name for name in selected if re.fullmatch(r"results/ir-(check|test)/callgrind-(measurement|warmup)-\d+-(baseline|candidate)\.out", name)]
assert len(profiles) == 56
for workflow in ("check", "test"):
    assert sum(name.startswith("results/ir-" + workflow + "/") for name in profiles) == 28
    for suffix in ("json", "jsonl", "csv"):
        assert "results/ir-" + workflow + "/samples." + suffix in selected

OUT.mkdir(parents=True)
supplemental = {}
archive = OUT / "ir-public-subset.tar.gz"
with archive.open("xb") as raw_archive:
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw_archive, mtime=0, compresslevel=6) as compressed:
        with tarfile.open(fileobj=compressed, mode="w|") as tar:
            for name, record in selected.items():
                header = tarfile.TarInfo(name)
                header.size, header.mode, header.mtime = record["bytes"], record["mode"], 0
                with (RAW / name).open("rb") as stream:
                    tar.addfile(header, stream)
seen = set()
with tarfile.open(archive, "r:gz") as tar:
    for member in tar:
        assert member.isfile() and member.name in selected and member.name not in seen
        seen.add(member.name)
        expected = selected[member.name]
        assert member.size == expected["bytes"] and member.mode == expected["mode"]
        with tar.extractfile(member) as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == expected["sha256"]
assert seen == set(selected)
for name, digest in transfer["files"].items():
    assert sha(RAW / name) == digest

for name in ("transfer-manifest.json", "receipt.json", "transport.json"):
    copy("original-collection/" + name, COLLECTION / name)
for name in ("review.json", "raw-integrity.json", "check-reproduced-analysis.json", "test-reproduced-analysis.json"):
    copy("accepted-analysis/" + name, ANALYSIS / name)
copy("accepted-analysis/root-ir-acceptance.json", CONTROLS / "root-ir-acceptance.json")
copy("accepted-analysis/independent-raw-and-statistical-review.json", ANALYSIS.parent / "review.json")
copy("accepted-analysis/independent-review-seal.json", ANALYSIS.parent / "seal.json")
for name in ("amendment.md", "decision.json", "root-acceptance.json"):
    copy("policy/" + name, POLICY / name)
copy("policy/independent-review.json", AMENDMENT_REVIEW)
for name in ("candidate.diff", "package_id.rs", "source-commit.json", "source.bundle", "ci.yml"):
    copy("source/" + name, SOURCE / name)
copy("source/code-publication.json", ROOT_PUBLICATION / "code-publication.json")
copy("ci/dispatch.json", ROOT_PUBLICATION / "ci-dispatch.json")
copy("reproduction/ohm-valgrind-env.c", WORK / "profiling-tools/ohm-valgrind-env.c")
copy("reproduction/assemble_publication.py", Path(__file__).resolve())

closure_path = WORK / "cargo-audit/package-id-native-failure01/closure/closure.json"
closure = read(closure_path)
assert closure["original_native_returncode"] == 1
assert closure["no_native_effects_inspected_computed_or_claimed"] is True
assert closure["no_retention_source_approval_move_or_replay_created_or_executed"] is True
save("sanitized-native-closure.json", {
    "status": "failed-before-native-preflight; no replay",
    "reason": "The first per-workflow quiet guard rejected unrelated host activity.",
    "original_native_returncode": 1,
    "native_workflow_preflight_or_sample_paths_created": False,
    "native_effects_inspected_computed_or_claimed": False,
    "native_wall_time_and_regressions_verified": False,
    "original_native_protocol_completed": False,
    "original_fixture_and_failure_records_retained_in_place": True,
    "retention_move_or_replay_performed": False,
    "private_closure_sha256": sha(closure_path),
    "private_capture_sha256": closure["capture_sha256"],
    "private_capture_seal_sha256": closure["capture_seal_sha256"],
    "private_capture_files": 34,
    "original_launch_receipt_sha256": "2607922b6cbeff1ba2425111d7bae5195479fe4f769fc287fcd02c5faf7b5a1c",
    "original_native_status_sha256": "58ece44f0feee41ba9f5701197760efe4477b6ff96a712a693b4d5066d66da3b",
    "original_failure_stderr_sha256": "05e94b7e60640f2cf5fb35010bdd4c1dee524321f545f0aba790754b74c4ab89",
    "privacy": "No foreign process identities, arguments or snapshots are reproduced here. The original records remain private and unchanged.",
})
save("publication-subset.json", {
    "scope": "Byte-identical selected files from the accepted IR collection; no resampling, statistical regeneration or native effects.",
    "original_transfer_manifest_sha256": sha(COLLECTION / "transfer-manifest.json"),
    "original_payload_tar_sha256": sha(COLLECTION / "payload.tar"),
    "original_collection_receipt_sha256": sha(COLLECTION / "receipt.json"),
    "included": selected, "omitted": omitted,
    "all_original_files_rehashed_before_and_after": 578,
    "full_callgrind_profiles_included": 56,
    "raw_sample_tables_and_IR_preflight_logs_unchanged": True,
    "archive": {"path": archive.name, "sha256": sha(archive), "bytes": archive.stat().st_size,
                "regular_members": len(selected), "duplicate_link_or_unsafe_members": 0,
                "all_member_bytes_sizes_modes_verified": True},
    "external_private_omission": {"description": "Failed native attempt and capture; outside the IR collection and not published.",
                                  "capture_files": 34, "capture_seal_sha256": closure["capture_seal_sha256"]},
})

table = []
for row in review["completed"]:
    summary = read(ANALYSIS / (row["workflow"] + "-reproduced-analysis.json"))["metrics"]["cargo_ir"]["statistics"]
    assert summary["paired_geometric_mean_count_reduction"] == row["reduction"]
    assert summary["bootstrap_count_reduction_interval"] == row["interval_99"]
    assert summary["pairs"] == summary["wins"] == 12
    interval = row["interval_99"]
    table.append(f"| `{row['workflow'] if row['workflow'] == 'check' else 'test --no-run'}` | {100 * row['reduction']:.4f}% | {100 * interval[0]:.4f}–{100 * interval[1]:.4f}% | 12/12 | {row['sign_p']:.9f} | {'Qualified' if row['passes_gate'] else 'Below 1% claim threshold'} |")
readme = f"""# PackageId ordering: retained Cargo instruction evidence

Returning `Equal` immediately for the same immutable interned PackageId reduces warm `cargo check` orchestration instructions on unchanged uv. Distinct pointers retain the original inner ordering; equality, hashes, complete version ordering and source precision are unchanged. The comparison is against PR181 alone, not a sum with other candidates.

| Workflow | Cargo Ir reduction | 99% paired bootstrap interval | Winning pairs | Two-sided sign p | Original IR gate |
| --- | ---: | ---: | ---: | ---: | --- |
{chr(10).join(table)}

Only `check` qualifies for an improvement claim. The test-build result is reported for completeness and is below the 1% point-estimate threshold. Each workflow used 12 fixed randomized pairs after two warmup pairs, with six observations in each order; both orders were positive. The accepted summaries use 20,000 bootstrap resamples of paired log ratios, seed 1701, and a 99% interval. Both complete raw workflows were audited before effects. No observations were added, removed, replaced, pooled or extended.

The metric is Cargo-process Callgrind `Ir`, excluding child processes. These are warm unchanged development loops, not cold builds or test execution. uv is pinned at `3d82a6ad5a7eab8c68236553b7846517767c4b61` and was not modified; `cargo test --no-run` executes no uv tests. The complete accepted 56 profiles, six sample tables, IR logs and preflight proofs are byte-identical inside `ir-public-subset.tar.gz`. `accepted-analysis/review.json` and its two reproduced summaries are the authoritative effects, bound by the root acceptance. Generic instrumented elapsed-time fields and generic native-regression booleans in old IR schemas are not native timing or regression evidence.

The original plan also required completed native regression checks. The native attempt failed at its first per-workflow quiet guard before preflight or samples because of unrelated host activity. **The publication criterion changed after IR results were known and before native effects were analyzed. Native wall time and regressions remain unverified; the original complete protocol did not pass or complete.** The explicit amendment applies uniformly to the three active IR-qualified candidates and preserves all IR gates and rejected primary screens. See `policy/` and `sanitized-native-closure.json`.

Measured source: baseline parent `d81a093becb4321a975522624c2a383970f0d164`, tree `c4178b67e0b3a64a12b9b58f84b97323b99d734e`; candidate commit `{source['commit']}`, tree `{source['tree']}`. Matched binaries are `{acceptance['variants']['baseline']}` and `{acceptance['variants']['candidate']}`. Both were built serially at identical physical source/target paths with stock Rust 1.99.0, `all-static,ohm-defaults`, ThinLTO and one codegen unit. This is a no-PGO production-settings comparison, not the published PGO build. Debug sections were removed with allocated-section invariance checks.

All 13 focused PackageId/SourceId correctness tests passed with no failures or ignores. Exact-source CI is mandatory before a draft; the initial dispatch is retained in `ci/dispatch.json`, and terminal exact-head validation must be added before publication qualification. The eight required jobs are Rustfmt, both Clippy jobs, both Cargo test jobs, Workspace tests, Resolver tests and Schema tests. The optional APFS replay is disabled.

The original collection manifest is retained, and `publication-subset.json` accounts for every one of its 578 files. Operational histories and files containing occupancy/process snapshots or other-workload records are omitted in full, never silently redacted into apparently original raw files. Their hashes remain in the inventory; all originals remain private and unchanged. The private native capture is not published. This is an explicit subset, not a complete replay of every private admission receipt.
"""
(OUT / "README.md").write_text(readme)
(OUT / "REPRODUCE.md").write_text("""# Reproduction

Verify `manifest.json`, then extract `ir-public-subset.tar.gz` into a new directory. `publication-subset.json` specifies every included member's hash, size and mode and every omitted original file. All sample JSON/JSONL/CSV files, the 56 full profiles and the accepted summaries are original bytes. The assembler verifies archive membership and all included bytes without running statistics. No retained fixture should be reused or overwritten.

To inspect the accepted arithmetic, use `accepted-analysis/{check,test}-reproduced-analysis.json` under `metrics.cargo_ir.statistics`, and compare each raw `samples.json` metric against its complete Callgrind profile. The unchanged reviewer and statistics source are in the archive under `controller/reviewer/`; the core runner is `benchmark/frozen/paired.py`. The frozen analysis CLI is:

```sh
python3 benchmark/frozen/paired.py analyze results/ir-check --confidence 0.99 --resamples 20000 --seed 1701 --minimum-pairs 12 --minimum-improvement 0.01
python3 benchmark/frozen/paired.py analyze results/ir-test --confidence 0.99 --resamples 20000 --seed 1701 --minimum-pairs 12 --minimum-improvement 0.01
```

Those commands write analysis outputs: use a new copy for independent reproduction, never overwrite the accepted archive. Only `metrics.cargo_ir` is the claimed metric. Instrumented elapsed time is not native time. The acceptance method applies linear quantiles to bootstrapped means of log ratios before exponentiation; use the retained method, not an alternative quantile transformation. The primary check gate requires a point reduction of at least 1%, a positive 99% lower bound, two-sided exact sign p <= 0.01, and both orders positive. Test requires its own full gate for a test improvement claim and did not meet the 1% threshold.

For a new machine comparison, build both source trees with the exact common inputs in `controller/cohort/production/provenance-local-package-id-order-stack181.json`, the frozen driver/manifest and both full patches. Keep Git HEAD at the shared embedded `5e5d271d763d7beb38b48755e22bd59e93f02b97` identity and apply the respective complete tree patches; use one physical source path and one target path sequentially. Compare the resulting trees to `c4178b67e0b3a64a12b9b58f84b97323b99d734e` and `12f12327e7c56fb04386b7cfb4d61d5fd434bfc5`. The incremental published patch is `source/candidate.diff`. Keep compiler, dependency lockfile, static features, ThinLTO, codegen units, release channel and stripping identical; this study did not use PGO.

Create a fresh owned fixture with unchanged uv commit `3d82a6ad5a7eab8c68236553b7846517767c4b61`, the hash-bound packaged Ohm 1.99.0-6 runtime and pinned Valgrind/debuginfo inputs. The archive's `metadata/setup.json`, base configurations, `prepare_host.py` and measurement seal record exact inputs. `reproduction/ohm-valgrind-env.c` is the common profiler-environment normalizer source. Rebuild or obtain its shared object and verify the recorded hash. Use the same explicit certificate paths and environment for both variants; retain absent loader/allocator variables as absent.

Use distinct target/shared directories for check and test, and one canonical regular Cargo executable pathname for both variants. Place the controller on CPU8 and workload subprocesses explicitly on CPUs0–7. Preserve the three fixed untimed warm commands per variant, then the strict traced zero compiler/build-script/test-execution proof and both cross-switch freshness checks before sampling. The archived IR preflight logs and reports show these checks for this cohort. Do not treat a failed preflight or occupancy guard as a measured zero.

The exact benchmark commands and environments are in `benchmark/ir-check.json` and `benchmark/ir-test.json`. They run `cargo -Zohm-defaults=yes check --locked --offline -j 8` and `cargo -Zohm-defaults=yes test --no-run --locked --offline -j 8` under Callgrind with `--trace-children=no`. After independently sealing a new local configuration and verifying preflight, the fixed runner interfaces are:

```sh
python3 benchmark/frozen/paired.py run --config benchmark/ir-check.json --output NEW_CHECK_DIRECTORY --phase confirmation --pairs 12 --warmup-pairs 2 --seed 20261021141
python3 benchmark/frozen/paired.py run --config benchmark/ir-test.json --output NEW_TEST_DIRECTORY --phase confirmation --pairs 12 --warmup-pairs 2 --seed 20261021142
```

Archive paths and input hashes refer to the original machine. A new fixture needs an explicitly recorded path/input mapping and new seals; do not silently reuse private approval receipts or remove guards to make old controllers run. The published subset deliberately omits operational process records, so the original full admission/collection reviewer requires those private inputs. Raw instruction arithmetic and source/build/workload reproduction remain available from this subset. Complete both fixed raw batches and verify integrity before effects; never pool with interrupted runs or extend a negative batch.

Native wall-time and regression verification are outstanding. The original native plan and failed-attempt hashes are retained for transparency; no native inference follows from the instruction results or from the interrupted attempt. Exact-source green CI and final root qualification must accompany any draft.
""")
save("supplemental-origins.json", {"files": supplemental, "accepted_statistics_copied_not_regenerated": True})
for path in OUT.rglob("*"):
    if path.is_file() and path.suffix != ".gz" and path.name != "source.bundle":
        privacy_check(path, path.read_bytes())
save("assembly-audit.json", {
    "status": "passed-local-assembly; terminal-CI-proof-still-required",
    "assembled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "archive_sha256": sha(archive), "included_original_files": len(selected),
    "omitted_original_files": len(omitted), "all_original_files_preserved": 578,
    "profiles": 56, "sample_tables": 6, "canonical_review_sha256": sha(ANALYSIS / "review.json"),
    "no_statistics_regenerated": True, "no_native_effects_read": True,
    "no_host_workload_or_GitHub_action": True,
    "no_occupancy_process_snapshot_or_other_workload_record_in_selected_JSON": True,
    "actual_native_raw_logs_and_status_not_published": True,
    "manifest_scope": "Initial assembly. Add terminal CI evidence and a new final publication manifest without relabeling this assembly receipt.",
})
files = {str(path.relative_to(OUT)): {"sha256": sha(path), "bytes": path.stat().st_size}
         for path in sorted(OUT.rglob("*")) if path.is_file()}
save("manifest.json", {"files": files, "scope": "Initial privacy-filtered evidence assembly; original controls and raw evidence unchanged."})
print(json.dumps({"output": str(OUT), "manifest_sha256": sha(OUT / "manifest.json"),
                  "archive_sha256": sha(archive), "archive_bytes": archive.stat().st_size,
                  "selected": len(selected), "omitted": len(omitted), "profiles": 56,
                  "canonical_review_sha256": sha(ANALYSIS / "review.json")}, indent=2))
