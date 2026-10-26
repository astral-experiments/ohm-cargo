# Ruff’s development loop on Ohm

These experiments use the Linux x86-64 Ohm 1.99.0-14 toolchain and Ruff revision `93526150df078af7dd8fc4226cdcc469539d2001`. The production changes are confined to Ohm. Each edited workload replays the same edit in a disposable Ruff checkout. Every `cargo test` workload uses `--no-run`.

The primary devbox was a 32-vCPU AMD EPYC Milan KVM guest running Linux 6.8 and glibc 2.39. The released compiler was `f1a7cf9d2` with LLVM 23.1.1. The instruction collectors were Valgrind 3.22.0 and DynamoRIO 11.91.20741. Individual studies identify the collector and processes included in each result.

## Native workspace checks after edits

On a second 16-vCPU host, nine Cargo changes and three compiler changes reduced an ordinary full `cargo check` after a private Ruff parser edit from 12.12 s to 0.93 s. The median paired reduction was 92.22% (95% interval 92.00–92.44%, Holm-adjusted p = 0.00433). Every one of 12 pairs improved. The optimized compiler checked the parser once and allowed Cargo to reuse 34 dependents. An exported lexer edit still needed all 35 compiler invocations. Its 2.15% estimated elapsed reduction had a 95% interval of −2.68–3.80% and remained inconclusive. All 48 commands passed and all 48 verification runs had the same 520 fresh artifacts. [Timings, rosters and replay](../native-toolchain-stack/)

## Cargo changes together

The nine Cargo drafts #242–#250 used the same release-PGO control, nine-draft candidate, default Ruff workspace and ordinary command output. All 36 fresh pairs improved with Holm-adjusted p = 0.00649 for each command. The native scheduling draft is a separate comparison.

| Workspace command | Already-built artifact count | Whole-command instruction reduction | 95% median interval |
| --- | ---: | ---: | ---: |
| `cargo check` | 520 | 10.52% | 10.51–10.53% |
| `cargo build` | 501 | 6.53% | 6.52–6.55% |
| `cargo test --no-run` | 619 | 8.93% | 8.91–8.94% |

On a separately selected historical Ruff server doc edit, nine drafts saved 4.00% over the control (3.88–4.12%) and 2.44% beyond the first seven (2.41–2.52%). Each comparison improved in all 12 matched blocks and had order-conditioned Holm-adjusted p = 0.01852. Every observation included Cargo and the real compiler child. All 442 emitted metadata files and 435 API hashes matched. [Combined patch, individual counts and rerun scripts](../cargo-stack-holdout/)

The six initial Cargo changes were compiled both individually and together with the release PGO training data. These are the unqualified workspace commands with ordinary Cargo output and already-built artifacts. Callgrind counted the complete command. Separate verification runs checked the artifact roster before and after each cohort.

| Ruff command | Fresh artifacts | Median parent instructions | Median with six changes | Median paired reduction | 95% paired-median interval |
| --- | ---: | ---: | ---: | ---: | ---: |
| `cargo check` | 520 | 918.7M | 884.5M | 3.72% | 3.71–3.73% |
| `cargo build` | 501 | 1,488.0M | 1,464.7M | 1.56% | 1.55–1.57% |
| `cargo test --no-run` | 619 | 1,115.0M | 1,078.1M | 3.32% | 3.31–3.34% |

All 12 pairs improved for each command. The two-sided exact randomization p-value, conditional on arm-order balance, was 0.00216 for each. Requesting Cargo’s artifact JSON in the scored commands gave 3.40%, 1.50% and 3.14%, respectively. The two series were independently ordered. [Raw counts, patches, commands and fixtures](../cargo-stack/)

On a historical seven-line Ruff CLI source edit, the first four PGO changes used 2.28% fewer whole-command instructions for `cargo check`. Six used 2.98% fewer (95% median interval 2.88–3.05%), and seven used 3.41% fewer (3.36–3.49%). Each comparison used 12 pairs and required exactly one rebuilt Ruff binary, one Cargo process, and one rustc process. [Edited-check harness and observations](../cargo-stack/)

Two independently seeded native wall-time cohorts on different CPU sets produced 384 timed commands. Both estimated a 2.3% elapsed-time reduction for `check`, but one 95% interval included zero and neither met the multiplicity-adjusted threshold. The build and test-compile timing intervals also included zero. The reliable improvements on this host are in executed instructions. [Native elapsed times](../native-wall/)

## Individual drafts

Each row is a separate parent-versus-change measurement. Percentages from different rows apply to their own workloads. The six PGO Cargo rows use the same 520-artifact full check so their effect sizes can be compared directly. All six passed the Holm adjustment across those comparisons. [Individual Cargo measurements](../component-pgo/)

| Ohm change | Measured effect |
| --- | --- |
| [Cargo #242](https://github.com/astral-sh/ohm-cargo/pull/242) borrows package identities while reading the lockfile | 0.10% on the full PGO check, 0.98% on a plain `ruff_text_size` check |
| [Cargo #243](https://github.com/astral-sh/ohm-cargo/pull/243) reuses the last decoded registry source | 0.63% on the full PGO check, 4.46% on a plain `ruff_python_trivia` check |
| [Cargo #244](https://github.com/astral-sh/ohm-cargo/pull/244) reuses owned registry manifests | 1.19% on the full PGO check |
| [Cargo #245](https://github.com/astral-sh/ohm-cargo/pull/245) shares inherited workspace lints | 0.66% on the full PGO check, 2.44% on a plain `ruff_text_size` check |
| [Cargo #246](https://github.com/astral-sh/ohm-cargo/pull/246) skips formatting omitted lockfile fields | 0.39% on the full PGO check |
| [Cargo #247](https://github.com/astral-sh/ohm-cargo/pull/247) reuses a locked dependency’s interned source ID | 0.29% on the full PGO check, 0.34% in an independent plain full check |
| [Cargo #248](https://github.com/astral-sh/ohm-cargo/pull/248) reuses the number of uncached paths during checksum prefetch | 1.10% on a plain full check, 0.69% on a full build and 0.99% on test compilation. It saved a further 0.48% in a direct check over all six earlier changes |
| [Cargo #249](https://github.com/astral-sh/ohm-cargo/pull/249) reuses verification of an unchanged Git index | 6.26% on the full warm workspace check and 7.21% for Cargo, rustc and the build script on a historical `ty_vendored` edit. The full build saved 3.83% and test compilation saved 5.20%. A first verification cost 0.117% on the full check. [Measurements](../verified-git-index/) |
| [Cargo #250](https://github.com/astral-sh/ohm-cargo/pull/250) restores unused-key diagnostics with the cached registry manifest | 1.16% on the full warm check and 0.95% after a historical CLI edit. The warm build saved 0.74% and test compilation saved 1.05%. The new format requires one parse per manifest on its first visit. [Measurements](../registry-diagnostic-keys/) |
| [Cargo #251](https://github.com/astral-sh/ohm-cargo/pull/251) assigns one frontend thread to small incremental workspace checks | 3.20% **less elapsed time** for a workspace check after a public lexer edit. The package-only timing interval included zero. An already-fresh workspace check used 0.034% more instructions. [Native replication and fresh control](../frontend-scheduling/) |
| [Rust #230](https://github.com/astral-sh/ohm-rust/pull/230) skips empty early-lint scopes | 0.45% for a full parser package check after a source edit, 0.26% for a full AST package build |
| [Rust #231](https://github.com/astral-sh/ohm-rust/pull/231) simplifies packed dependency-edge traversal on top of #230 | Another 0.495% for a full parser package check after an edit, with independent second-host compiler reductions of 0.67% for the parser and 0.80% for the AST |
| [Rust #232](https://github.com/astral-sh/ohm-rust/pull/232) isolates private trait implementations in metadata-only dependency hashes | Whole workspace checks on two private parser edits dropped from 14.02 s to 1.38 s and 8.03 s to 1.13 s. Actual rustc invocations fell from 35 and 22 to one. An exported lexer edit retained all 35. [82 observations and safety checks](../private-trait-check/) |
| [Packaging #185](https://github.com/astral-sh/ohm/pull/185) builds Linux Wild 0.11.0 with ThinLTO | 2.10% for the full workspace build after a CLI edit, 0.96% for full workspace test compilation after a formatter-fixture edit |
| [Wild #43](https://github.com/astral-sh/ohm-wild/pull/43) handles paired debug-range relocations together | A further 0.47% and 0.51% on two independent complete Ruff test-compilation schedules over its immediate parent |
| [Packaging #186](https://github.com/astral-sh/ohm/pull/186) packages both Wild source improvements | 2.40% and 2.48% on the same two test-compilation schedules against packaging #185 |

The Rust comparisons used matched stage-2 PGO and BOLT builds. The packed-edge study includes 104 pairs across seven workloads and build configurations. Four Cargo changes plus Rust #230 saved 1.66% in a direct combined parser-check measurement. [Packed-edge replications](../packed-edges/), [combined parser check](../cargo-rustc-stack/)

The linker measurements counted Cargo, rustc, the compiler driver and Wild. Both arms rebuilt the same one artifact out of 501 for `build` or 619 for test compilation and produced byte-identical native executables. A prospective DWARF optimization regressed the full ThinLTO test and was dropped. [Wild measurements and reproduction](https://github.com/astral-sh/ohm/tree/b0ba262a45b9d45374df1cb6a8e1af7d103e0e02/benchmarks/ruff-dev-loop-20261026/wild)

Four Cargo changes and the ThinLTO Wild package together saved 2.320% across the edited CLI `cargo build` (95% interval 2.298–2.342%) and 1.505% across the edited integration `cargo test --no-run` (1.373–1.636%). All 12 pairs improved in both commands. [Whole-command build and test measurements](https://github.com/astral-sh/ohm/blob/2e894cae7d6bad85c235c1deecbb6f1d8f384b47/benchmarks/ruff-dev-loop-20261026/wild/combined.md)

The full six-Cargo, two-rustc stack saved 2.756% on the historical CLI check. All 16 pairs improved, with a 2.72–2.80% block-bootstrap interval for the geometric reduction. Cargo saved 3.21% and rustc alone was inconclusive on this tiny edit. All 442 metadata files and 435 public API hashes agreed. Both compiler drivers reproduced byte for byte on a pristine-to-stack-to-pristine build. [Combined CLI check](../integrated-check/)

The seventh Cargo change improved all 48 pairs across four full-workspace comparisons. A mixed-worktree attempt was discarded in full and repeated after source isolation. [Checksum prefetch data](../checksum-prefetch/)

Combining six Cargo changes, both compiler changes and the ThinLTO linker reduced the complete edited CLI build by 2.49% (95% interval 2.48–2.50%) and test compilation by 1.81% (1.69–1.93%). All 12 independently ordered pairs improved in each command. Both arms used the same previously built native dependencies, and the final executables were byte-identical in every comparison. An independent from-source build produced different paths in jemalloc debug information for two executables and was excluded. [Whole-command counts, raw binaries' checksums and reproduction](https://github.com/astral-sh/ohm/blob/0efa3139d4eb7be2344fd205d6e4dff7a0bc6c46/benchmarks/ruff-dev-loop-20261026/wild/integrated.md)

The two linker confirmation schedules each used every arm order twice. All 24 matched triplets favored the new packaged Wild for both comparisons. All 102 test executables matched byte-for-byte. [Whole-command comparison and independent repeat](https://github.com/astral-sh/ohm/blob/44d5fb2604340650a2bdf49d85500a2007e7d1d4/benchmarks/ruff-dev-loop-20261026/wild/range-pairs/results/README.md)

## Historical edit coverage

Eleven source patches were selected by a fixed hash rank. Six were used to profile the rebuild work and five were reserved for confirmation. Across the six real edits, ordinary workspace commands reported between one and 58 dirty artifacts. The parser edit launched 35 distinct rustc processes. [Selection rules](../entropy-corpus/), [all discovery receipts](../discovery-results/)
