# uv warm dev-loop: cache derived unit-path strings

CompilationFiles memoizes each unit's formatted metadata hash and directory
string for one invocation. Repeated output, fingerprint, lock, dependency and
build-script paths reuse those strings. When shared-cache validation falls
back to a private workspace namespace, cached directories are cleared before
they can retain paths from the rejected namespace. Unit hashes remain valid.
This caches derived strings; filesystem trust validation still runs.

These measurements use original PR175 commit
efc8b51502f8a8d1fe76997dc984481edde2740e on pinned Cargo
5e5d271d763d7beb38b48755e22bd59e93f02b97. The measured candidate tree is
b0dfb3fe2cfd8d310efa04a345f58886296f712a, represented by source commit
0651b04ed6faff6d94aefbca8e222925e87b28cd. The later external restack moves the
trust-fallback code; these observations do not establish incremental
performance for the ported patch on that stack. A separate validation is
predeclared for that comparison. uv remains unchanged at
3d82a6ad5a7eab8c68236553b7846517767c4b61.

| Fixed production validation | Reduction | 99% paired interval | Sign p | Wins | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Warm check, Cargo instructions, 12 pairs | 1.4068% | 1.2521% to 1.4811% | 0.000488281 | 12/12 | Pass, both orders positive |
| Warm test --no-run, Cargo instructions, 12 pairs | 1.4111% | 1.3212% to 1.4551% | 0.000488281 | 12/12 | Pass, both orders positive |
| Warm check, native wall time, 30 groups | 0.3992% | -0.4240% to 1.1313% | 0.361594608 | 18/30 | Inconclusive, gate fails |
| Warm test --no-run, native wall time, 30 groups | 0.4050% | -0.3228% to 0.9667% | 0.001430906 | 24/30 | Inconclusive, gate fails |

Only the two instruction reductions are claimed. Each passes the independently
predeclared gate of at least 1% reduction, positive 99% interval, exact two-sided
sign p <= 0.01 and improvement in both execution orders. No observations were
pooled, removed or added after inspecting an effect. Native groups contain
eight calls; the group remains the statistical unit. The native test-build
sign test does not override its below-threshold estimate and interval crossing
zero. No native wall-time improvement or absence of regression is established.
These commands are fresh, full-workspace invocations: no uv tests execute,
and dirty rebuilds are outside this workload.

The measured pair uses all-static/ohm-defaults, opt-level 3, ThinLTO, one codegen
unit and stock Rust 1.99.0. There is no PGO; these are not published PGO binaries.
The workload compiler is pinned Ohm 1.99.0-6. Debug-only stripping preserves all
allocated ELF sections. Callgrind 3.22 counts Cargo userspace instructions only,
excluding child compiler, linker, build-script, test and kernel work. Both
variants report its brk/allocator fallback. Instrumented elapsed time is not
native time.

The exact measured production candidate passed 93 preexisting build-directory
tests, with four ignored and no failures, using an unchanged integration
runner and recorded binary/runtime hashes. The supported compatibility
launcher preserves tests' explicit Ohm settings and defaults classic-layout
tests appropriately; the compiler-library path is explicit. Earlier normal
build failures and binary-provenance limits remain visible. See
[VALIDATION.md](VALIDATION.md). The production pair also passed immutable-input
and fresh Ohm-enabled uv preflights for both workflows.

[HISTORY.md](HISTORY.md) retains six earlier performance/setup attempts and
explains the external PR175 baseline change, unsuccessful profiler setup,
initial timing noise and older ELF metadata normalization. No historical
observations contribute to the production gates.

Use [REPRODUCE.md](REPRODUCE.md), the frozen [runners](harness),
[protocols](protocols), [configurations](configs) and [build provenance](build).
[INPUTS.json](INPUTS.json) maps historical recorded hashes to packaged files;
executables and system runtimes must be provisioned separately. Rebuilding at
a new workspace prefix requires fresh generated artifacts and the same
canonical paths within each pair.

[raw-results.tar.gz](raw-results.tar.gz) contains every file from the ten run
directories except the disclosed large Callgrind attribution profiles, plus
correctness/build logs and execve evidence. All sample tables, native subruns,
preparations, warmups and failed attempts are included. The full profiles remain
in the task workspace; [counter extracts](callgrind-counter-extracts.jsonl)
bind every profile's hash, size and original summary lines to its raw sample.
The failed smoke profile is explicitly labeled unsuccessful.
[RAW-MANIFEST.json](RAW-MANIFEST.json) lists the archive exactly, and
[SHA256SUMS](SHA256SUMS) seals the package. Compiled correctness fixtures and
cache databases are excluded.
