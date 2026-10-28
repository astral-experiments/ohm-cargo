# Cargo instruction counts for settled Ruff builds

This study measures the Cargo process on the next fully fresh build after a private historical Ruff edit. Cargo still emits Make-compatible `.d` files for top-level artifacts. The change reads only paths when constructing these files, avoiding a temporary checksum map, and sorts the final path list once. Full checksum parsing remains in freshness checks.

The initial stock-release linter profile attributed 29.74 million of 450.94–453.46 million Cargo instructions to output `.d` generation across two runs. Path comparisons accounted for 19.29 million and the old parser/map accounted for 9.37 million. Another 4.78 million path-hash instructions are included in that parser/map total. Open tracing found 297 successful dep-info reads across a 268-unit graph. The output pass reopened 29 distinct units to assemble 1,243 paths. A one-input diagnostic replay reproduced the sorted `.d` path bytes in all four tested implementations. The product adopted a stable sort, which keeps the first spelling of equivalent Rust paths.

Both subjects were built from the published Ohm 1.99.0-17 Cargo source, `a0c7d08c898d3fdff992f2f431dec57d2486add2`. They shared one external PGO profile, 80 Cargo-library externs, 81 binary externs and their native library inputs. The two product jobs compiled the Cargo library and binary. The PGO producer used the same `db24aef81` build stamp on both binaries, while its verified product sources were based on the published `a0c7d08c` revision. The discovery profile used the separately packaged binary. The separately installed release compiler and SDK, Ruff commit `93526150df078af7dd8fc4226cdcc469539d2001`, local cache roots, toolchain paths, CPU affinity and four-job limit matched arm to arm on each host. The package dependency lockfile validated all 523 retained registry archives for the source test fixture. The linter and full build artifact rosters contained no `ron`. The test-build roster contained the registry package `ron 0.12.0`. The release-profile comparison uses the -17 observer rules. Cargo #261 changes the complete-marker behavior, and its corresponding implementation requires a separate integration and qualification.

## Paired whole-command measurements

Positive percentages indicate a reduction from the parent. Instruction totals cover every thread of Cargo. Ordinary wall times include starting Rustup and Cargo. Every measured run had zero Rust or native compiler jobs.

| Command | Parent / change, median Cargo instructions | Median paired reduction (interval) | Lower in | Exact p |
|---|---:|---:|---:|---:|
| `cargo build --lib`, `ruff_linter` | 498,998,132.5 / 488,775,573.5 | 2.05% (2.02%, 2.08%) | 16/16 | 0.00016 (Holm) |
| `cargo build`, full workspace | 1,416,008,717.5 / 1,334,386,574.0 | 5.77% (5.75%, 5.78%) | 16/16 | 0.00016 (Holm) |
| `cargo test --no-run`, full workspace | 1,303,379,408.5 / 1,304,411,185.0 | -0.08% (-0.09%, -0.07%) | 0/16 | 1.00000 (raw, secondary) |

Both primary endpoints had to save at least 1% at the median, improve at least 13 of 16 pairs, have a positive lower median interval bound and pass the two-test Holm threshold. The instruction intervals use the fourth and thirteenth order statistics (97.87% coverage). The test-build comparison is secondary. It took 0.084% more Cargo instructions in all 16 pairs; its 97.87% median interval was 0.071–0.093% more. All three ordinary wall-time intervals include zero.

| Command | Parent / change, median ordinary time | Median paired reduction (95% bootstrap interval) | Faster in |
|---|---:|---:|---:|
| `cargo build --lib`, `ruff_linter` | 310.7 / 313.4 ms | 1.05% (-11.88%, 10.89%) | 17/32 |
| `cargo build`, full workspace | 613.5 / 582.5 ms | 4.76% (-11.26%, 11.31%) | 20/32 |
| `cargo test --no-run`, full workspace | 628.7 / 652.7 ms | 2.26% (-19.28%, 5.94%) | 17/32 |

## Native controls and reproduction

All 268 linter, 501 default-workspace and 619 test-build artifacts were fresh. The parent and change each recreated all 1, 58 and 15 external `.d` files from missing files, respectively. Their contents and update behavior matched. Across the three commands, 492, 922 and 1,060 reported product paths retained byte content, inode, size and nanosecond modification time. Both mixed wasm `.d` files repeated a byte-identical rewrite in the default workspace build. The other two commands left all their sidecars untouched.

Each endpoint ran exactly 16 balanced instruction pairs and 32 separately balanced ordinary wall pairs. Recompute the registered statistics, all 96 per-process instruction counts, 192 wall observations, process rosters and archived native outputs with `python3 -B verify.py`. Files emitted by Cargo that exposed the machine’s configured registry mirror use a portable placeholder. The original and portable SHA-256 values are recorded in each endpoint. The per-row original `record.json` and actual command-argument bytes can be reconstructed and hashed by the verifier. [Original plan](https://github.com/astral-sh/ohm-cargo/tree/156c3f26eb3a833af6bf0f58ff07d024d1410842/benchmarks/ruff-dev-loop-20261027/settled-cargo-depfile-instruction-plan)

On the second host, running the test-build qualification advanced the shared registry store from 776 to 814 entries. The original workspace stability gate stopped before either H8 endpoint collected any observations. The separately registered worker recovered both original path-and-byte hashes, activated a private physical store for each mode at the same canonical path, and required the original native anchors and all four additional arm/mode checks. The original backup was restored after each mode. H7 retained its complete original sample. [H8 amendment and intermediate failures](https://github.com/astral-sh/ohm-cargo/tree/ae510132d41f14323668c44e8a41c6160c1d8f04/benchmarks/ruff-dev-loop-20261027/settled-cargo-depfile-h8-amendment)

The native controls cover escaped spaces, lexical/symlink aliases, relative output and dependency paths, stale or missing sidecars, two non-UTF-8 path failures and real changes visible to an ordinary Rust caller (17 to 29). A true foreign-span reader covered initial capture, confirmed capture, two fresh no-ops, trailer corruption, re-training and recovery. The public `.d` bytes and native values matched in all seven states. All 406 Cargo library tests, 15 dependency-file integration cases, and both matching build-script integration cases passed. Nine encoded dependency-file unit tests also ran separately.

The first discovery Callgrind setup rebuilt Ruff and was excluded. An initial DynamoRIO run under a different certificate environment also failed. Only calibrated complete-process observations of the all-fresh graph entered profile attribution. The first synthetic dependency-file control expected every fresh sidecar modification time to be stable but demonstrated the old mixed-output rewrite. A second control independently found a warm incremental `module_children` compiler failure on the old and new Cargo as well as the shipped toolchain. The test and compiler investigations are recorded separately from the confirmed `.d` behavior.

No Ruff product source changed in the candidate. Each benchmark applied a pinned historical Ruff edit solely as a workload, then timed the fully settled next commands. The timings cover Cargo’s settled no-job process.
