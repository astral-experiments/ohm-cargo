# Measurement protocol, frozen before first candidate measurements

Baseline: Cargo 5e5d271d763d7beb38b48755e22bd59e93f02b97, rustc
6d4a7ee3200c5311112d433cb9d1da4a2630a66f (published Ohm 1.99.0-6), uv
3d82a6ad5a7eab8c68236553b7846517767c4b61. No permanent uv source changes.

All Cargo variants are built with the same compiler, source directory, target
configuration and release optimization settings. Initial screening uses ordinary
optimized Cargo builds with debuginfo, not the release's PGO configuration.
A production-build validation will be attempted for any winning candidate.

Native commands use one canonical Cargo executable path, fixed compiler and
rustdoc paths, eight jobs, affinity CPUs 0-7, fixed source and cache paths. Runs
execute on the host because sandbox UID remapping disables the shared-cache
trust checks. No compiler builds or other benchmark jobs run concurrently.

Fresh-build workloads are full-workspace `cargo check --locked --offline -j8`
and `cargo test --no-run --locked --offline -j8`, with Ohm defaults enabled.
An untimed invocation immediately before each sample warms caches and refreshes
five-minute cache-GC timestamps. Two warmup pairs are recorded but excluded by
design. Every failed or slow measurement is retained; there is no outlier removal.
Verify output and one exec trace to ensure fresh-workload samples compile nothing.

Exploration screens candidates with 8 balanced, randomized instruction-count
pairs and 30 native wall-time pairs where the initial direction merits further
measurement. Callgrind `Ir` counts cover Cargo itself, excluding subprocesses;
this limitation must accompany every reported counter result. Instrumented wall
time is not a performance measure. Count results report 99% paired-bootstrap
intervals and exact two-sided sign tests, with both order groups shown.

Before opening a draft PR, freeze the selected patch and collect a separate
12-pair instruction confirmation batch and a 30-pair native confirmation batch
for its claimed workload. A counter-based claim requires at least a 1% point
reduction, 99% interval excluding zero, sign-test p <= 0.01, and improvements in
both order groups in the independent batch. A wall-time claim requires the
harness's 30-pair, 99%-interval, p <= 0.01, >=1% gate. Do not claim a wall-time
improvement from an inconclusive interval. Investigate any established wall-time
regression even if counters improve. Validate the other requested workflow for
regressions and run targeted correctness tests.

Dirty-workload fixtures must be specified before measurement and restore
matching initial state for every sample; the second variant must not consume
the first variant's warmed result. Their build commands never run uv tests.
Any changed plan or invalid batch is retained with the reason, and a fresh batch
is collected after fixing the cause.
