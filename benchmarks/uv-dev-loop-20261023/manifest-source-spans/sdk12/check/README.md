# Lazy manifest diagnostic spans: SDK12 dirty-check evidence

The candidate reduced **Cargo-parent instructions** in both fixed dirty `cargo check` blocks:

| Block | Paired geometric reduction | 99% paired bootstrap interval | Wins |
| --- | ---: | ---: | ---: |
| 1 | 0.727376% | 0.646677–0.898895% | 8/8 |
| 2 | 0.631218% | 0.458442–0.710828% | 8/8 |

Each block separately passes its original gate: all eight candidate wins and a lower 99% reduction bound greater than 0.1%. Each two-sided exact sign p is 0.0078125. The original schedules, 200,000 resamples and seeds 2026102371/2026102372 are retained. There is no pooled or familywise claim.

This measures Cargo's parent process during an ordinary dirty check. Compiler children run natively and are outside the instruction count. It establishes no whole-command wall-time speedup. The separately planned test-build endpoint is not included or qualified by these check results.

## Change and correctness

The patch defers construction of optional manifest source-span documents until a diagnostic actually requests spans. It captures the original manifest string and shares the parsed document through `OnceLock`; ordinary manifest parsing and validation still run. The public converter's existing pre-parsed Some/None behavior remains, and the pre-construction missing-dependency error obtains its original annotations from the captured source.

The exact [candidate.patch](candidate.patch) applies to baseline `fdd26156be98618e2e01a9e02703edac71b79a35`, tree `487deda53e727c16bd22ae3d7cf1c512d1005116`. The measured candidate tree is `ee6ffdb835f1012d3968f09be6946b88decd92fe`, identical to published [fa592baf](https://github.com/astral-sh/ohm-cargo/commit/fa592baf27578e348059de7fbe0eed50126d1bca). Both producer builds retained the baseline Git HEAD while changing the staged source. Publication commit metadata is separate.

The corrected candidate passed 25 supported focused tests with SDK12. Two additional tests initially failed because that SDK lacked i686 std; those failures are retained. Normal [CI](https://github.com/astral-sh/ohm-cargo/actions/runs/40018144003) passed all eight jobs but its stable toolchain ignored those two nightly-only cases. A separate [pinned nightly+i686 job](https://github.com/astral-sh/ohm-cargo/actions/runs/40021102477) checked out the exact candidate tree, linked and ran an i686 smoke binary, and executed both exact selectors with one pass and zero ignored each. Two production missing-dependency diagnostics matched baseline stdout and stderr exactly. The earlier candidate that lost annotations was corrected before any comparative block.

Both Cargo binaries use the same optimized build recipe and actual compiler argument vectors. Stripping preserved all 31 allocated ELF sections in each arm. [source-identities.json](source-identities.json) distinguishes build/test scopes and identities.

## Workload and validation

The workload is uv `3d82a6ad5a7eab8c68236553b7846517767c4b61`, using the existing controlled equal-length non-doc comment edit in `crates/uv/src/lib.rs`. Each arm was warmed independently from source and locked archive/index seeds, with separate target, shared-build and package-home banks activated at common paths. No compiled uv state was imported. The released SDK12 compiler, rustdoc and linker were common.

Native and parent-profile preflights established the same single ordinary uv-library rustc invocation, all 1,249 ordered arguments, ordered environment after omitting only dead jobserver descriptors, and exact metadata bytes across both arms. Every measured call preserved these checks. Original source bytes/mode, lockfile and active Cargo were restored, both state banks were parked, and final fresh checks launched no compiler. No tests or rustdoc ran.

Host activity was recorded without filtering observations. Scheduling can alter Cargo polling and synchronization; balanced order does not prove independent pairs. All 32 measured profiles are retained. 32/32 profiles retain the known Callgrind brk-overflow warning. Final totals, disjoint self-cost sums and stderr `Collected` counts agree in every profile; header summaries and their small differences remain explicit.

Both measured check blocks completed without excluded measured samples. Earlier source/setup failures, an excluded ENOSPC preflight on a different host, and unexecuted host proposals remain separate and supply no observations. Host relocation occurred before either comparative block and imported no compiled state. An offline-only lookup correction joined native stdout/stderr through their existing frozen preflight completion/manifest and command receipts; measured inputs, workloads, all comparisons, raw-count readers and statistical rules stayed unchanged. See [collection-validation.json](collection-validation.json).

The public sanitizer replaces only the command header and pathname definitions. Function names, compressed references, calls, positions, costs, totals and all other record bytes remain exact. Each derivative retains original profile/stderr hashes and the unchanged non-path stream hash. Private environments, host process arguments, authentication/transport logs and unrelated or failed effects are absent. Public numerical replay does not recreate private collection, environment, output, host or restoration validation.

Run `python3 reproduce.py --profiles profiles` to authenticate all 32 sanitized profiles and recompute both fixed gates. [REPRODUCE.md](REPRODUCE.md) describes building and collecting a fresh workload. The retained binary hashes identify this matched pair, not a guarantee of identical binaries on another system.
