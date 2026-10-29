# Ohm -18 after an edit to uv

Neither the seven open patches nor the original eight produced a repeatable elapsed-time improvement in this full-toolchain experiment. On two separate uv checkouts we timed 576 ordinary Cargo commands after real source edits, with 24 randomized blocks per command per checkout and all 72 test executables built. The seven-patch stack had to beat both shipped Ohm 1.99.0-18 and a source-matched rebuild. The rebuilds omit the release compiler’s PGO and BOLT stages. [Raw logs, processing and both stack comparisons](full-toolchain-wall/README.md) · [Toolchain identities and execution receipts](literal-current-and-historical/stage2.md)

The table shows the seven-patch stack’s paired median saving in wall time. Positive numbers mean faster. Brackets show the 97.73% distribution-free interval on each independent edit.

| Command | Control | Predicate edit | Help-text edit |
|---|---|---:|---:|
| `cargo check` | Shipped -18 | -3.01% [-23.51, +15.97] | -15.71% [-39.81, -4.52] |
| `cargo check` | Source-matched rebuild | +2.76% [-5.63, +20.43] | -4.16% [-19.18, -0.14] |
| `cargo build` | Shipped -18 | -4.07% [-8.85, +3.73] | +2.49% [-3.41, +11.73] |
| `cargo build` | Source-matched rebuild | -2.26% [-6.50, +3.47] | -0.10% [-10.60, +4.83] |
| `cargo test --no-run` | Shipped -18 | -16.06% [-36.87, -1.40] | +5.53% [-4.49, +22.29] |
| `cargo test --no-run` | Source-matched rebuild | +5.03% [-8.89, +11.24] | +4.68% [-10.52, +16.56] |

The extra Wild jobserver retry passed one of four preregistered holdout comparisons. The two Cargo lockfile guards passed their warm Cargo instruction tests, but neither produced a repeatable elapsed-time saving across 96 edited-check pairs. [All 216 jobserver confirmation runs](confirmation32/README.md) · [Resolver timings and product verification](resolver-wall/README.md)

### Standalone Cargo lockfile guard

A nine-line guard on the released Cargo source reduced Cargo-process instructions after real uv edits in all 16 pairs. DynamoRIO measured 0.159% and Cachegrind measured 0.152%. The earlier full-command elapsed-time comparison was inconclusive. [Raw samples, controls and reproduction](standalone-lockfile-guard/README.md)

### Instruction counts

On fully warm uv commands, the five Cargo changes and the std change in the Cargo executable reduced driver instructions by about 2.3% for check, 5.6% and 7.8% for build, and 2.5% for test preparation across two counters. Cargo launched no compiler. A stock-executable replay of the same parent-only profiler launch showed that Cachegrind sets `LD_PRELOAD`, which changes Cargo check-mode reuse eligibility. DynamoRIO added three private variables. [Per-command intervals and raw counts](warm-cargo/README.md) · [Observer audit](observer-audit/README.md)

After an edit, the historical stack saved 0.4722% and 0.4728% in the measured Cargo and rustc processes in two independent eight-pair runs. This instrumented configuration set `RUSTC_WRAPPER`, which excludes two release Cargo check-mode artifact reuse paths on marker-bearing targets. The elapsed-time observations above used ordinary compiler launches. [Instrumented counts and scorer](edited-check/README.md) · [Exact source conditions and fixture receipts](observer-audit/README.md)

The allocation-free lockfile guard saved 0.157% and 0.166% of warm Cargo instructions. The hash-set guard saved 0.145% and 0.150%. Each variant used its own comparison against the same control. On real uv links, a separate exception-frame relocation change saved 0.23–0.63% of linker instructions on two executables against released and rebuilt Wild. [Lockfile evidence](lockfile-collision/README.md) · [Linker evidence](release-eh/focused-results.json)

### Executable reuse

An official Cargo regression exercises ordinary binaries and binary test harnesses whose own package library is unused. Released Cargo relinked both after the library changed. The proposed patch reused both while the binary that reads the library produced the updated result. Its warm-workspace control ran 144 commands. The edited timing assignment is independent of those checks. [Regression, warm counts and raw logs](proof-controls/README.md) · [Edited assignment](registered-proof.json)

The Ohm coordinator and all three component forks were checked for source and PR changes through the end of the full-toolchain timing run. The release was still -18. Wild #45 had closed and #46 had been rebased before these comparisons were frozen. [Release pins and draft status](ohm-source-status/at-full-stack-completion.json) · [Resolver source-overlap check](ohm-source-status/ordered-guard-source-overlap.json)

### Compiler profiles

During two edited builds, one rustc worker spent 341 ms and 265 ms decoding exported generic symbols from the same 489 dependencies. Both captures used the released compiler. [Raw profiles and decoder](compiler-profile/README.md)

### Earlier jobserver discovery

On 32 physical cores, updating a user-facing help string in uv and running `cargo test --no-run` took a median 2.24 seconds less with the scoped Wild jobserver retry. The estimate came from 18 faster pairs out of 24. On eight cores a private predicate edit produced 16 faster pairs out of 24 and an interval that crossed zero. These measurements compare the candidate with Wild #46, using the distributed -18 Cargo, compiler and target standard library. [Release manifest](https://github.com/astral-sh/ohm/blob/ohm-1.99.0-18/toolchains/1.99.0/18.json) · [Previous Wild draft](https://github.com/astral-sh/ohm-wild/pull/46)

| Available cores and edit | Control median | Candidate median | Median paired saving | 97.7% interval | Faster pairs | Exact sign p | Order-conditioned p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8, installation predicate | 6.719 s | 6.334 s | 6.99% | −3.98 to 9.52% | 16/24 | .152 | .193 |
| 32, Homebrew update message | 8.792 s | 6.467 s | 23.49% | 0.74 to 36.35% | 18/24 | .0227 | .0361 |

Every pair applied identical source bytes to both arms and used private, independently parked incremental targets. The timers include the complete workspace Cargo command through process exit. Cargo chose its ordinary job count. Cargo produced all 72 test executables in every run. The host activity check found zero competing build or profiling processes after any of the 96 runs. A short incidental metadata walk overlapped both arms of one eight-core pair. All 24 pairs enter the result. With that pair excluded, the median was 6.98% and 15 of 23 pairs improved. [Raw rows](direct-linker-discovery.csv) · [Logs and receipts](direct-linker-discovery.zip) · [Paired analysis](discovery-results.json)

The eight-core result missed the preregistered cross-size criterion. The 32-core estimate selected a narrower question for confirmation on two new checkouts of uv. Each new checkout uses 36 randomized blocks, with all six orders equally represented. It compares the candidate with both the previous linker draft and the actual distributed -18 linker. Each of those four comparisons must have a positive lower median bound and two-sided sign and assignment-conditioned p below .0125. Fresh target and registry copies are prepared separately for each checkout. The earlier 48 pairs contribute no observations to this confirmation. [Frozen 32-core assignment](registered-32-heldout.json) · [Original two-cohort assignment](default-v3.json)

The other fixed assignments cover the historical Cargo/Wild stack with shipped rustc, a small `uvx` source edit, and reuse of binaries that do not read their package library. The first four-way admission ended before any observation. Unchanged Wild reproduced the same one-byte `.rodata` section-header difference and 32-byte GNU build ID observed among the release-generated ELF files. [Four-arm assignment](registered-four-v3.json) · [Small-binary edit](registered-uvx.json) · [Release-control replays](stock-elf-replays.zip)
