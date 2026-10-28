# H5 admission and result binding

Run from the new protocol directory on `charlie-ohm-c5-check-1025`. The coordinator separately publishes and reads back this plan, the native catalog results, and the zero-clock wall admission. Each publication has its own immutable Git commit. A SHA-256 manifest verifies the associated files' contents. The release, repository, PR heads and publication refs establish their provenance.

```sh
P=/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028
cd "$P/wall-protocol-v3"
sha256sum --quiet -c SHA256SUMS
```

## Before admission

The plan binds Cargo B at 0aa04df8 and C at 813ba8a4, the original physically built historical scheduler source, the complete merged source tree shown by PR #260, and exact-head CI for #260 and #261. The H5 loader still verifies the original native worker in `$P/protocol-v3`, the adopted excluded seed under `ruff-evaluation-v2`, both genuine first-selection outputs, both unchanged runs, the original registry digest and all first-selection output copies. It also verifies the pristine failed-slot ELF bytes and the original failure receipt. Entries from the prior wall schedule and its clocks have no role in any reader.

Collect these separate inputs under `$P/wall-launch-v3/` after their successful publication has been independently read back.

| File | Required fields |
| --- | --- |
| `binding.json` | Exactly `ref` (new v3 wall plan commit) and `sha256` (this SHA256SUMS digest) |
| `ci.json` | Fresh #260 and #261 check reports in the same schema as ci-exact-heads.json, with exact expected head, job name, status, conclusion and GitHub job URL |
| `catalog-publication.json` | `plan_ref`, `plan_manifest`, `native_reference` from catalog_scope, `catalog_protocol_ref`, `catalog_result_ref`, `independent_review="accepted"`, and exact `view_sha256`, `terminal_sha256` and `verifier_receipt_sha256` |

The native source is fixed at `5b9490236f0557fb748a7b7e527e45452002904b` and its SHA256SUMS at `d116e7b75a81b1a5b8664248ab26425cc6ed4912abf7631e8cccdb4a14c7ead7`. Its body, independent verification, source and result receipts must be retained in `$P/whole-wild-width-v1/`. Its verifier emits `wall-view.json`, `terminal.json` and `independent.json`. The wall reader checks the independent result, the literal source manifest and all 297 fresh ordinary linker occurrences. It requires all 9,568 individually successful plain/reporting width links and 299 successful default controls. Two of those controls reconstruct the old failures independently. Their supplemental recipes cannot expand the six genuine phases' accepted output sets. [Native catalog protocol](https://github.com/astral-sh/ohm-cargo/tree/5b9490236f0557fb748a7b7e527e45452002904b/benchmarks/ruff-dev-loop-20261027/rc17-composed-all-links-protocol)

The input view identifies each old successful native invocation by target, actual exec record and full argv SHA-256. Each new occurrence binds its role, package, full or link-only kind, unique occurrence number within its phase and target, literal argv, resolved positive file identities and bytes, normal output SHA-256 and real Wild image. The reader validates these against the referenced physical capture, raw argv, positive file roster and unique recipe ID. For each such recipe it checks stock width 1–16, the exit status and matching result of each plain/reporting pair, and the SHA-256 of retained ELF bytes. New raw values must be individually present in the per-target list. Admission further checks exact historical phase outputs and agreement across every byte outside the two independently inspected ELF fields. The 60 unlinked workspace outputs and 78 registry outputs use exact raw commitments. Earlier temporary file contents absent from the retired process remain unknown; complete fresh captures at identical roles supply the per-occurrence inputs.

With sufficient space for a full physical copy, a six-GiB allowance and a 32-GiB reserve, run the zero-clock admission under the native lock.

```sh
/usr/bin/python3 -IB runner.py admit "$P/wall-qa-v1/qa.json"
```

Admission exclusively creates `$P/early-scheduler-wall-admission-v3.json` on success. A failed admission leaves `early-scheduler-wall-admission-v3.failure`. Retain it. A stale plan, source or CI snapshot, failed catalog, missing occurrence, missed formerly rejected raw output or unaccounted product ends this trial.

## Separate scoring grant

Publish and read back that new admission. Write `$P/wall-launch-v3/admission-publication.json` with exactly `plan_ref`, `catalog_ref`, `admission_ref`, `plan_manifest`, `admission_sha256`, `catalog_publication_sha256`, and `ci_sha256`. The last two hash the freshly admitted catalog publication receipt and CI snapshot. Then populate `$P/wall-launch-v3/grant.json` with `go="score exact v3 24 fresh pairs"`, `native_sha256` (wall admission), `plan_manifest`, `published_plan`, `published_catalog`, `published_native` (new wall admission), `ci_sha256`, `h5_clear=true`, `other_host_measurement=false` and `ci_review="accepted"`. The reader checks the three distinct results against the distinct published native source and excludes both earlier wall commits.

```sh
/usr/bin/python3 -IB runner.py score "$P/wall-launch-v3/grant.json"
/usr/bin/python3 -IB verify_result.py "$P/early-scheduler-wall-rc17-v3" "$P/early-scheduler-wall-admission-v3.json"
```

The scorer holds the existing native lock, restores 48 independent ext4 copies at the same canonical paths, checks the physical release chain and runs only the registered ordinary Cargo command inside each clock. Keep launcher stdout, stderr and the exact terminal exit for admission, score and verification. The result root contains each slot's start, uninstrumented command stderr/stdout and clock, 110+78 first selections, the separate unchanged process roster and 110+78 follow-up outputs, and both test listings. A complete series additionally writes all full pair rows, analysis and a terminal checksum record. A failure preserves the first exception, all attempted raw observations and the first failed private state. Retain the stopped outcome separately and report no incomplete aggregate or replacement.

## Offline checks

`check_result_reader.py` reconstructs an entire generated 48-slot series and deliberately corrupts one product. It also tests that previous or unbound publication references and invalid grants fail. `check_catalog.py` covers missing/different/failed widths, changed ordinary ELF bytes, full-versus-link-only multiplicity, a missing previous counterexample, an unrelated output and exact-head CI failures. `check_source.py CARGO_REPOSITORY PUBLISHED_BUILD_QA_DIR` verifies 3,108 source paths and modes plus the exact three-file delta from both actual repository trees. `analysis.py selftest` and `check_v3_statistics.py` exercise the unchanged full exact randomization analysis, including a gain that misses the replacement threshold. The separate check_native_registration.py fixture reconstructs 297 synthetic literal captures and rejects nine altered acquisition bindings. These local test fixtures do not execute Ruff commands or contribute observations.
