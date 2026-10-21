# Reproducing the retained scheduler experiment

This package is an explicit publication subset of the accepted IR collection. Begin by verifying its files and extracting the raw evidence into a new directory:

```sh
sha256sum -c SHA256SUMS
mkdir raw
tar -xzf raw-ir-publication-subset.tar.gz -C raw
```

`publication-subset.json` maps every archive member to its original collection SHA256, size, and mode. It also inventories all omitted original members. The complete original collection manifest and its receipt are in `collection/`. Private host/process records and failed-native retention archives are intentionally not part of this subset; the original independent raw review and root acceptance were performed against the complete original collection before publication filtering.

## Inputs and production build

Use uv commit `3d82a6ad5a7eab8c68236553b7846517767c4b61` without source edits, Ohm `1.99.0-6` for workload rustc/rustdoc, and the two source trees in `README.md`. The candidate changes only `src/util/dependency_queue.rs`. `source/candidate.patch`, its source commit/bundle records, and the published exact-tree CI records bind that change.

The build procedure and complete environment are retained under `raw/controller/cohort/`, especially `frozen/build_driver_host2_scheduler_bitsets_stack181.py`, `results/provenance.json`, both `.build.json`/`.strip.json` files, `audit-pair.json`, and `root-pair-review.json`. The original stock compiler command was:

```text
<stock Rust 1.99.0>/bin/cargo build --release --locked --bin cargo \
  --features all-static,ohm-defaults -j 8 -v
```

The explicit settings were `CARGO_INCREMENTAL=0`, `CARGO_PROFILE_RELEASE_LTO=thin`, `CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1`, `CARGO_PROFILE_RELEASE_DEBUG=1`, `CARGO_PROFILE_RELEASE_OPT_LEVEL=3`, `CARGO_PROFILE_RELEASE_INCREMENTAL=false`, `CARGO_PROFILE_RELEASE_STRIP=none`, `CFG_RELEASE_CHANNEL=dev`, and `LIBZ_SYS_STATIC=1`. No profile-generate/profile-use input was used. The driver applies the two complete frozen source patches serially at one physical source path and common target path, retaining embedded Git head `5e5d271d763d7beb38b48755e22bd59e93f02b97` for both builds. Reproduce that source-import procedure if exact build provenance is required; the binary's embedded head alone is not the source-tree identity. The strip helper checks all allocated sections before accepting the measured binary.

The measured workload rustc SHA256 is `6109cff145371a50c4f62b61908d2ffbf6d259b180c8effde07baa426aab682a`; its `librustc_driver-b03bf00bec23bb9a.so` SHA256 is `a3a5d8cc86af464504170220d142c4ea1129434e2d5e741755feec6f9f35a436`. Full tool, runtime-library, CA-bundle, source/config, and binary identities are in each original result manifest and `raw/controller/assets.json`.

## Workload preparation and measurement

Use an otherwise quiet x86_64 Linux host with ordinary-user ownership and at least CPUs 0–8. The controller is pinned to CPU 8; preparation and measured Cargo commands are pinned to CPUs 0–7. The original host was `charlie-oss-2`. `raw/controller/driver.py`, its frozen reference controller, and `raw/controller/reviewer/` document the actual guards and audit rules.

Create a fresh owned workspace with one canonical Cargo executable, one unchanged uv checkout, and common Cargo home. Within each workflow, both variants use the **same** canonical executable, target, and shared-cache paths. The original root was `/tmp/ohm-hillclimb-20261021/scheduler-bitsets-stack181`; check and test use separate `targets/ir-check`/`targets/ir-test` and `shared-cache/ir-check`/`shared-cache/ir-test`. Seal all four config/tool-input identities before warming. The original absolute configs are in `raw/benchmark/`; any relocation requires a new prospective config/input seal, consistently applied to both variants. Do not reuse the original approvals or treat old host-specific setup controls as an unrestricted launcher.

Install Valgrind 3.22.0 and matching glibc debug information as recorded in `assets.json`. The original package hashes are `744e081e5cf3d5c598b499dbb7d2250ea3f2869dde4a4d7b231fe6114f347d7d` for `valgrind_1%3a3.22.0-0ubuntu3_amd64.deb` and `c4b086cef3a6bbb6a90299969b3c0bf3867f40cb8e9bbbb0edfe5ae23f2c04f0` for `libc6-dbg_2.39-0ubuntu8.9_amd64.deb`. The included `tools/ohm-valgrind-env.c` and exact measured `.so` remove instrumentation-injected loader variables before Cargo observes its compiler environment. Native preparation has those loader variables unset. Explicit `SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt` and `SSL_CERT_DIR=/usr/lib/ssl/certs` preserve the ordinary startup behavior. Compiler children are excluded from instrumentation.

Preparation runs the corresponding native Cargo command before every instrumented observation, outside measurement. The controller also performs the frozen repeated warm/fresh checks, execve audit, and cross-variant switch checks. Require no compiler/build-script/test execution in the audited fresh command and preserve all preflight outputs. Both complete preflight directories are retained in `raw/metadata/`.

The actual measured command is the following, with `<workflow arguments>` equal to `test --no-run --locked --offline -j 8` or `check --locked --offline -j 8`:

```text
/usr/bin/taskset -c 0-7 /usr/bin/env \
  LD_PRELOAD=<root>/profiling-tools/ohm-valgrind-env.so \
  OHM_BENCH_NORMALIZE_VALGRIND_ENV=1 \
  <root>/profiling-tools/valgrind/usr/bin/valgrind \
  --tool=callgrind --trace-children=no \
  --extra-debuginfo-path=<root>/profiling-tools/valgrind/usr/lib/debug \
  --callgrind-out-file=<output>/callgrind-{stage}-{pair}-{variant}.out \
  <root>/active/bin/cargo -Zohm-defaults=yes <workflow arguments>
```

Run the **test workload first**, then check. The original fixed runner commands, each under the CPU-8 controller, were:

```text
python3 -I -B raw/benchmark/frozen/paired.py run \
  --config <sealed ir-test.json> --output <new test output> \
  --phase confirmation --pairs 12 --warmup-pairs 2 --seed 20261021131
python3 -I -B raw/benchmark/frozen/paired.py run \
  --config <sealed ir-check.json> --output <new check output> \
  --phase confirmation --pairs 12 --warmup-pairs 2 --seed 20261021132
```

Retain every observation, including all four warmup observations per workflow. Do not extend, exclude, pool, or resample based on observed effects. Audit both complete workflows against their plans, JSON/JSONL/CSV records, source/input identities, return codes, and actual `Ir` totals before calculating either effect. The original accepted audit is under `validation/`, and the exact reviewer source is under `raw/controller/reviewer/`.

## Replaying the stored analysis

Copy the extracted result directories to a separate scratch location before running an analyzer, so the original evidence stays unchanged. On each copy, the retained analyzer command is:

```text
python3 -I -B raw/benchmark/frozen/paired.py analyze <scratch result directory> \
  --confidence .99 --resamples 20000 --seed 1701 --minimum-pairs 12
```

The endpoint is `metrics.cargo_ir.statistics`: paired geometric-mean count reduction, 99% bootstrap interval, exact two-sided sign test, and separate execution-order estimates. Both workflows have six AB and six BA measured pairs. The original gates require ≥1% estimated reduction, positive lower 99% bound, sign p ≤0.01, and positive estimates in both orders. The primary test result must pass; secondary improvement requires its own full gate. Stored tables and analyses are duplicated under `data/` for inspection. Instrumented elapsed time is not a native timing estimate.

The original protocol additionally planned 30 native paired groups of eight calls per group, two warmup groups, and fixed seeds `20261021133`/`20261021134`. That stage did not complete and is not reproduced or claimed here. `policy/` records the later instruction-only publication amendment, with the original protocol unchanged. `native/` preserves a sanitized account and hashes of the private recovery evidence. A new native experiment would require a new prospective plan and reliable host admission; no native timing or no-regression conclusion follows from this artifact.
