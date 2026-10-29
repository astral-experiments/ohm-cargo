# Four Ohm toolchains on edited uv

[All raw observations and standalone scorer](observations.zip) · [All 576 elapsed times as CSV](samples.csv) · [Seven-patch comparison](paired-wall-time.png)

This archive contains the complete native timing study for Ohm 1.99.0-18 on one Linux devbox. Each of two independent uv checkouts contributed 24 blocks per Cargo command. Every block builds the same edited bytes with all four toolchains, for 576 timed invocations in total. The shorter 54-byte checkout changes the Homebrew recognition `predicate`. The longer 90-byte checkout changes the displayed Homebrew upgrade instruction (`brew-help`). The fixture restored both source files and their original modification times after measurement.

## Read or reproduce the numbers

Starting dirty-page volume had little relationship with elapsed time within a command, checkout and toolchain. The rank correlations were 0.018 for check, 0.026 for build and −0.002 for test compilation. This exploratory calculation retained all 576 commands. [Host telemetry summary](starting-host-variance.json)

`numeric-results.json` reports every contrast and the preregistered endpoint decisions. Its `median_saved_pct` is the median of paired per-edit percentages, with positive values indicating that the treatment finished sooner. The confidence interval uses order statistics for the population median. Every check, build and test contrast involves 24 paired timings in each checkout.

Unzip the archive, then run the following command in its root with Python 3.11 or later. It checks every member digest, compares the historical and amended assignments, regenerates all 144 edit hashes, parses all 576 original Cargo logs, checks all 576 external-activity and process receipts, verifies the raw compiler/linker traces, and recalculates the exact sign and conditional randomization tests. It compares the complete result object with the sealed report before printing it.

```sh
python3 -I -B rescore.py > rescored.json
```

The study compares two treatment stacks. `stack` is the historical eight with the old Wild #45 and #46 together. `current` is the seven still open at registration, including the rebased #46 on Wild 0.11. Both treatments use the same PGO Cargo and the same true stage-2 Rust compiler, rustdoc, host standard library and target standard library with Rust #247. They differ only in the installed Wild image. `shipped` uses the unmodified published toolchain. `base` uses the matched rebuilt compiler, independently trained baseline Cargo and matched bare Wild. The rebuilt compilers omit the distribution-specific rustc PGO and BOLT steps. The shipped LLVM library is shared by the installed and rebuilt toolchains. `protocol/literal-stage2-evidence.README.md` documents the bootstrap and default-linker details.

For an endpoint to qualify, that treatment must beat both controls under the initial family-adjusted gate and do so again on the independent checkout. Each contrast requires both exact tests to pass, a positive lower confidence limit and positive medians under both pair orders. `numeric-results.json` retains every failed comparison. The full schedules, gates, source identities and original three-arm projection are under `protocol/`.

## Verify the workload

The direct commands are workspace `cargo check`, `cargo build` and `cargo test --no-run`, each with `--locked --offline -j8` and an affinity of CPUs 0–15. Admissions record a full successful exec trace before and after each endpoint, with a stable visible toolchain path, separate target trees and Cargo homes. The check traces must bind the nonempty uv library metadata to the actual rustc command. The empty metadata placeholder from compiling the uv binary remains in the receipt, paired with its binary-source dependency file. Build and test compare the true program outputs at the real edited Homebrew path and a control path. Test compilation produces the exact frozen roster of 72 logical targets.

`evidence/<cohort>/<command>/timings.csv` contains the direct wall-time and resource rows. The unfiltered quiet and external-activity logs are alongside it. Directories beginning with `m` hold all 576 original Cargo transcripts and their timer receipts. `admission-*`, `post-*`, `admitted.json` and `done.json` record every traced role, selected output digest and program check. `raw-execs.tar.gz` inside each admission or postflight contains every original strace file, including empty files for threads. The underlying binaries and large uv build outputs belong to the separate portable toolchain replay kit.

The original check artifact rule rejected a legitimate zero-byte binary metadata file before recording any timed row. `excluded-zero-row/` preserves that entire attempt. `protocol/four-arm/metadata-admission-v2.json` records the scope, raw evidence and freeze of the repair. The effective runner is `protocol/four-arm/run-metadata-v2.py` with its sibling `metadata_admission.py`. The original runner, all schedules, the corrected admission and the full phase logs are included.
