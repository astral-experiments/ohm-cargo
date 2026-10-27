# Wild on a Ruff IDE unit-test edit

This version can reuse Linux linker outputs when Rust and the C driver request a fresh path. It skips 3 of 5 full links for `cargo build` but only 1 of 14 for `cargo test --no-run`, where most destination files already exist. The experiment used two independent controls, the actual bundled Wild from Ohm 1.99.0-14 and an unmodified Wild built from the same source, lockfile, image, and release profile as the candidate. Cargo used its normal GCC and Wild settings. All three arms had 501 or 619 fresh units on every post-edit repetition.

| Endpoint and control | Control median | Candidate median | Paired time reduction (95% interval) | Holm-adjusted p |
| --- | ---: | ---: | ---: | ---: |
| Build, shipped | 3.93 s | 3.24 s | 16.0% (9.7–21.6%) | 0.007 |
| Build, source-matched | 3.99 s | 3.24 s | 16.1% (9.8–21.5%) | 0.007 |
| Test build, shipped | 5.99 s | 6.12 s | −1.1% (−4.0–1.8%) | 0.570 |
| Test build, source-matched | 5.93 s | 6.12 s | −2.1% (−4.7–0.5%) | 0.470 |

Each command had 18 randomized blocks with one ordinary Cargo invocation per subject in each block. All six subject orders occurred three times. Timing excluded tracing and test execution. `receipts.tar.gz` includes all 108 primary commands, freshness checks, native process counts, and the observed hit/miss logs from the first and final qualification traces. `primary-statistics.json` is reproducible from those receipts using the registered analyzer. The separate genuine-code miss workload and the successor that can verify existing test executables have their own measurements. [Frozen plan](https://github.com/astral-sh/ohm-cargo/tree/c977719f4247463537f6b9f978a5ce24fd4cda91/benchmarks/ruff-dev-loop-20261027/wild-reuse) · [Ruff edit](https://github.com/astral-sh/ruff/commit/1797ed542380c5aa0f7832e3877b1df56ddb2e08)
