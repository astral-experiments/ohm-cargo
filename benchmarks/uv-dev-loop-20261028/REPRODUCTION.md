# Reproducing the Ohm and uv measurements

The workspace is [uv at c22e6b719](https://github.com/astral-sh/uv/tree/c22e6b71933443e9cd299d4b6ac8de035ed4825b). The driver baseline is [Cargo at a0c7d08c8](https://github.com/astral-sh/ohm-cargo/tree/a0c7d08c898d3fdff992f2f431dec57d2486add2). Every uv compilation uses the Linux x86-64 Ohm 1.99.0-17 rustc. The Cargo-only cohorts use its bundled Wild 0.11.0. The linker-specific and complete-toolchain cohorts substitute matched parent and patched Wild builds. The host had 32 AMD EPYC Milan vCPUs and 98 GiB RAM.

`samples.csv` contains each measured Cargo invocation in its original order within the pair. One row records the change, cohort, workload, command, pair index, position in the pair, arm, value and unit. A test-build row means `cargo test --no-run`. The Wild serial-replay rows count a single linker invocation. In the Wild edited-command rows, the value is the sum of five linker processes in each of two commands per arm and `order` gives the full four-command block. The individual process totals are in `components/wild/edited/samples.csv`. The contents of `runs/` preserve the original Cargo measurements, including the edit logs and source hashes.

## Reproduce the Cargo results

Start with the setup instructions and release hashes in [the five-change reproduction guide](reproduce/first-five.md). It installs the shipped Ohm compiler and bundled linker, creates private registry and target directories, prepares the two uv checkout layouts, and identifies the exact matched driver revisions. The primary drivers use stable rustc 1.99.1. The release-style builds use Ohm's shipped compiler, ThinLTO, one codegen unit and static native libraries. The distribution's original merged PGO profile was unavailable in the release assets.

After setup, these commands replay PR #269's initial and independent cohorts from their archived protocols. The helper verifies the complete recorded arm order and prints the commands when `--execute` is omitted. It also supports the cumulative and edited cohorts.

```bash
python3 -B "$OHM_BENCH_WORK/replay-first-five.py" depfile-confirm --build --execute
python3 -B "$OHM_BENCH_WORK/replay-first-five.py" depfile-replica --execute
```

The runner places both measured binaries at the same executable pathname. It warms each command, runs with `--locked --offline -j16`, and rejects errors or unexpected recompilation. DynamoRIO sums the counters for all threads in the original Cargo process. Cachegrind reads `I refs` with subprocess instrumentation disabled. The counter setup and calibration are in [the DynamoRIO notes](reproduce/dynamorio/README.md).

For wall time, select `--mode wall` and use a quiet host. The runner measures process launch through exit and rejects a contended Cargo lock. `--settle-counter` adds instrumented warmups and requires both arms to be fresh before collecting instruction-count pairs. A clean-driver check trial rebuilt a dependency and was rejected. The accepted build cohort, rejected check log, and independently ordered replacement run are retained. The original pair counts and seeds are in [the measurement protocol](reproduce/protocol.txt) and the per-cohort protocol files.

## Replay actual edits

The edit harness uses separate archives of `$OHM_BENCH_WORK/uv`. It changes the private installation-source predicate with a different input string for each pair. Each arm starts from its own copy of the same warmed target. The harness moves that arm's target to the same visible path for the command, records the packages rebuilt and the test executables emitted, and restores the original source after the run. The per-cohort README preserves the original laboratory commands. The archive-relative helper uses a new result directory, with `edit-holdout-unit` or `edit-holdout-cumulative` selecting the recorded revisions and warm/measure phases.

## Interpret the samples

Compute the paired reduction as `1 - candidate / parent`, then take the median over pairs. The sign test is exact and two-sided. With 12 nonzero pairs, 12 wins give p = 0.00048828125. The third and tenth ordered reductions form a 96.14% distribution-free interval for the median. With eight pairs, eight wins give p = 0.0078125, and the endpoints of the sample form a 99.22% interval. Each draft names its primary endpoint and reports its paired replication. Cargo-process counts exclude rustc and the linker. Ordinary wall measurements include all child processes.

## Rebuild the standard library and linker

The standard-library parent is `bfa236f639034f61ec884c15bd1f4e0b75e508ac` and the PR head is `395a878a9ea634f84319d2c04653ec1e79e38f16`. Extract `components/standard-library/guard-stack-evidence.zip` and follow its README. `build/build-one.sh` builds Cargo against each std at identical paths using `-Zbuild-std`. The archive contains input manifests, driver and rlib hashes, the recorded path corpus, oracle tests and build commands. The added public ordering test and its result are under `verification/`. [Rust #247](https://github.com/astral-sh/ohm-rust/pull/247)

The Wild parent is `e856d81f6683cad80b9fe0ebf1a0c3c403c6fe11` and the PR head is `a77381c04eb7ad9258cdd0475642815a2a1da711`. Extract `components/wild/wild-undefined-evidence.zip` and follow its README for the fixed-path release builds, real link captures, jobserver-preserving instrumentation and ELF comparisons. Its expectation of five linker processes per edited `cargo test --no-run` is specific to the pinned uv revision and target configuration. [Wild #45](https://github.com/astral-sh/ohm-wild/pull/45)

For end-to-end timings, see `reproduce/toolchain-wall-reproduction.md`, the sealed schedules in `reproduce/toolchain-wall-plan.json` and the per-command readiness data under `verification/`. The baseline and candidate use separate parked copies of the same initial target and the same visible source, target, compiler and linker paths. Every measurement edits both arms with the same bytes and verifies the rebuilt crate and the test-executable roster. The archived uv source is restored after each run.

The JSON protocols record the original local paths for provenance. Set `OHM_BENCH_ROOT`, `OHM_BENCH_WORK`, `OHM_TOOLCHAIN_BIN` and the counter paths as above when running on another machine. The per-pair CSVs and Python report renderer need only the standard library. To regenerate the report from the unpacked archive, run `python3 reproduce/render_results.py --runs runs --output report.md`.
