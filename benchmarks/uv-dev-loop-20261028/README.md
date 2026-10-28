# Ohm developer-loop performance on uv

Five stacked Cargo changes, one standard-library change and two stacked Wild changes were measured on the pinned uv workspace using Ohm 1.99.0-17. A warm command reuses its settled build artifacts. An edited command rebuilds after a change to the private installation-source predicate in an archived copy of uv. All test-construction commands use `--no-run`. [uv source](https://github.com/astral-sh/uv/tree/c22e6b71933443e9cd299d4b6ac8de035ed4825b) · [Cargo baseline](https://github.com/astral-sh/ohm-cargo/tree/a0c7d08c898d3fdff992f2f431dec57d2486add2)

The archive includes the build recipes, original logs, calibration and analysis scripts. [Reproduction steps](REPRODUCTION.md) · [Ordered samples](samples.csv) · [Reproduction archive](uv-ohm-benchmarks.zip)

## Native edited test-build time with all eight changes

The whole-command clock covers full-workspace `cargo test --no-run --locked --offline -j8`, including the released Ohm rustc and default native Wild. Each pair builds the same new private-body literal from matched targets. No tests execute.

| Cohort | Baseline median | Candidate median | Median paired reduction [97.73% rank interval] | Improved | Ties | Exact sign p | Gate |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| initial | 6.719 s | 7.232 s | -8.498% [-19.730%, 4.535%] | 9/24 | 0 | 0.307456 | inconclusive |
| replica | 7.389 s | 7.583 s | 1.654% [-13.504%, 10.399%] | 14/24 | 0 | 0.541256 | inconclusive |

**No repeatable whole-command speedup established.**

Before and after timing, native traces verified six released rustc processes and five real Wild invocations per arm. Every one of the 96 timed commands rebuilt only uv and reported the complete 72-executable test roster. The two Cargo binaries were independently self-trained. The baseline linker is the matched release-source Wild, and the candidate linker contains both Wild changes.

The elapsed-time sensitivity analysis was specified before timing and enumerates the 2,704,156 balanced arm allocations in each cohort. [Assignment-conditioned results](components/eight-wall/order-sensitivity-results.md)

The repeat waited 30 seconds for residual writeback before its two clean preflight windows. Median I/O wait on the reserved CPUs was 0.252% initially and 0.220% in the repeat. Foreign-process checks ran during preflights. The in-window host monitor recorded aggregate counters. [Host observations](components/eight-wall/host-observations.json) · [Source, process and executable audit](components/eight-wall/complete-audit.json)

## Edited test-build instructions with all eight changes

The two arms use separately trained Cargo binaries, the same released rustc, and the parent or stacked Wild. The count sums all threads of Cargo, six rustc processes and five Wild processes during each edited `cargo test --no-run --locked --offline -j8`. The registration requires both an exact sign test and an order-conditioned randomization test to pass in each independent cohort. [Protocol and raw counts](components/eight-roles/)

| Cohort | Parent → candidate (G instructions) | Paired reduction [rank interval] | Improved | Sign p | Order p | Gate |
| --- | --- | --- | --- | --- | --- | --- |
| initial | 28.197 → 27.594 | 2.133% [1.909%, 2.176%] | 8/8 | 0.0078125 | 0.0285714 | qualified |
| replica | 28.199 → 27.593 | 2.135% [1.887%, 2.159%] | 8/8 | 0.0078125 | 0.0285714 | qualified |

## Retrained profile-guided builds

Both source states were instrumented, trained and rebuilt independently with the released compiler and identical build paths. Each used the same Diesel and bitmaps workloads from the release training corpus. The timed uv checkout was excluded from training. The shipped profile covers additional release workloads. [Training and build provenance](reproduce/pgo-holdout/README.md)

| Comparison | Cargo command | Parent → candidate (M instructions) | Paired reduction [rank interval] | Wins/pairs | Exact p |
| --- | --- | --- | --- | --- | --- |
| DynamoRIO, 28-byte checkout | `check` | 797.69 → 779.27 | 2.306% [2.293%, 2.325%] | 12/12 | 0.000488281 |
| DynamoRIO, 28-byte checkout | `build` | 888.66 → 836.11 | 5.916% [5.911%, 5.938%] | 12/12 | 0.000488281 |
| DynamoRIO, 28-byte checkout | `test --no-run` | 946.89 → 923.39 | 2.489% [2.458%, 2.500%] | 12/12 | 0.000488281 |
| Cachegrind, 76-byte checkout | `check` | 809.59 → 791.11 | 2.286% [2.267%, 2.294%] | 8/8 | 0.0078125 |
| Cachegrind, 76-byte checkout | `build` | 939.14 → 854.49 | 9.018% [8.932%, 9.029%] | 8/8 | 0.0078125 |
| Cachegrind, 76-byte checkout | `test --no-run` | 959.10 → 935.69 | 2.442% [2.425%, 2.455%] | 8/8 | 0.0078125 |

| Endpoint | Registered primary and replication gate |
| --- | --- |
| `check` | Pass |
| `build` | Pass |
| `test --no-run` | Pass |

The additional default-argument comparison ran `cargo check`, `cargo build` and `cargo test --no-run`. Cargo chose its job count, the populated registry stayed offline through the environment, and the uv lockfile was checked byte-for-byte.

| Comparison | Cargo command | Parent → candidate (M instructions) | Paired reduction [rank interval] | Wins/pairs | Exact p |
| --- | --- | --- | --- | --- | --- |
| Default Cargo arguments | `check` | 798.24 → 779.79 | 2.309% [2.188%, 2.387%] | 8/8 | 0.0078125 |
| Default Cargo arguments | `build` | 889.28 → 836.52 | 5.934% [5.850%, 6.023%] | 8/8 | 0.0078125 |
| Default Cargo arguments | `test --no-run` | 947.14 → 923.70 | 2.474% [2.433%, 2.530%] | 8/8 | 0.0078125 |

## Edited uv instruction sums

The sum covers Cargo, every released-rustc invocation, and every Wild invocation, including their threads. Both arms compile uv with the released Ohm rustc and use Wild `--no-fork`. The kernel, wrappers, `cc`, `collect2` and unwrapped forked work are outside the sum. Each pair changes a private same-length literal. No tests run.

| Cargo command | Cohort | Pairs | Baseline G instructions | Candidate G instructions | Median paired reduction [rank interval] | Improved | Exact sign p | Gate |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | --- |
| `cargo check` | Initial | 8 | 4.754 | 4.728 | 0.547% [0.518%, 0.579%] | 8/8 | 0.0078125 | passed |
| `cargo check` | Independent repeat | 8 | 4.755 | 4.730 | 0.537% [0.527%, 0.569%] | 8/8 | 0.0078125 | passed |
| `cargo build` | Initial | 8 | 14.848 | 14.691 | 1.053% [0.933%, 1.074%] | 8/8 | 0.0078125 | passed |
| `cargo build` | Independent repeat | 8 | 14.886 | 14.705 | 1.108% [0.989%, 1.330%] | 8/8 | 0.0078125 | passed |
| `cargo test --no-run` | Initial | 8 | 28.313 | 28.165 | 0.523% [0.463%, 0.539%] | 8/8 | 0.0078125 | passed |
| `cargo test --no-run` | Independent repeat | 8 | 28.347 | 28.179 | 0.527% [0.466%, 0.729%] | 8/8 | 0.0078125 | passed |

The min–max rank interval has 99.22% coverage for a continuous median at eight pairs. Sign tests exclude ties. A repeatable direction requires a positive median and two-sided p < .05/3 in the initial cohort, then a positive median and p < .05 in a separate, fresh cohort. Only initially passing endpoints qualify for the repeat.

### Baseline instruction shares

Each percentage is the median of baseline role / baseline total across the eight source edits. Parentheses show the separate baseline and candidate median role counts in billions. Medians are computed independently.

| Command | Cohort | Cargo | rustc | Wild |
| --- | --- | ---: | ---: | ---: |
| `cargo check` | Initial | 18.34% (0.872 → 0.846 G) | 81.66% (3.882 → 3.882 G) | 0.00% (0.000 → 0.000 G) |
| `cargo check` | Independent repeat | 18.37% (0.874 → 0.847 G) | 81.63% (3.882 → 3.882 G) | 0.00% (0.000 → 0.000 G) |
| `cargo build` | Initial | 6.85% (1.017 → 0.937 G) | 47.30% (7.023 → 7.023 G) | 45.85% (6.808 → 6.731 G) |
| `cargo build` | Independent repeat | 6.96% (1.036 → 0.948 G) | 47.19% (7.024 → 7.024 G) | 45.84% (6.809 → 6.731 G) |
| `cargo test --no-run` | Initial | 5.77% (1.633 → 1.593 G) | 51.24% (14.506 → 14.507 G) | 42.99% (12.172 → 12.063 G) |
| `cargo test --no-run` | Independent repeat | 5.82% (1.649 → 1.607 G) | 51.18% (14.507 → 14.505 G) | 43.01% (12.177 → 12.068 G) |

### Workload admission

The live jobserver may distribute worker threads differently across matching link outputs. All observed threads contribute to each linker count. The frozen admission gate checks which compiler and linker work the command invoked.

**cargo check initial.** Verified 1 rustc invocations (uv (lib)), 0 Wild invocations (none), and 0 test executables.

**cargo check independent repeat.** Verified 1 rustc invocations (uv (lib)), 0 Wild invocations (none), and 0 test executables.

**cargo build initial.** Verified 3 rustc invocations (uv (bin), uv (lib), uvx (bin)), 2 Wild invocations (uv, uvx), and 0 test executables.

**cargo build independent repeat.** Verified 3 rustc invocations (uv (bin), uv (lib), uvx (bin)), 2 Wild invocations (uv, uvx), and 0 test executables.

**cargo test --no-run initial.** Verified 6 rustc invocations (uv (bin), uv (lib), uvx (bin), uv (test), uv (test), uvx (test)), 5 Wild invocations (uvx-141090d4fffe584e, uv-23905aefc33b1c4d, uv, uvx, uv-c84366b26c530121), and 72 test executables.

**cargo test --no-run independent repeat.** Verified 6 rustc invocations (uv (bin), uv (lib), uvx (bin), uv (test), uv (test), uvx (test)), 5 Wild invocations (uvx-141090d4fffe584e, uv-23905aefc33b1c4d, uv, uvx, uv-c84366b26c530121), and 72 test executables.

The rejected first pilot compared the structural check edit, which compiled three targets, with a later literal change, which compiled only the library. It contributes no samples. Each subsequent cohort freezes the exact compiler and linker roster from four identical-state native/count admission cells, then checks it on every held-out observation.

The supplemental randomization test was specified after the initial cohorts and before any independent repeat finished. It conditions on the registered balance of baseline-first and candidate-first pairs. [Assignment-conditioned results](components/edited-roles/order-sensitivity-results.md)

## Individual changes under profile-guided optimization

Each adjacent Cargo revision was trained and rebuilt separately using the same non-uv workload. The last row adds the path change to the fifth Cargo revision. The primary criterion used two-sided sign p < 0.05/6 on 12 DynamoRIO pairs. The independent eight-pair Cachegrind cohort used p < 0.05. Brackets give distribution-free intervals for the median paired reduction. [Frozen protocol](reproduce/pgo-steps/registration.json) · [Driver, profile and standard-library hashes](profile-build/intermediates/driver-index.tsv)

| Change | Command | 28-byte checkout | 76-byte checkout | Outcome |
| --- | --- | --- | --- | --- |
| [Borrow unit dependencies #264](https://github.com/astral-sh/ohm-cargo/pull/264) | `test --no-run` | 0.706% [0.687%, 0.745%] | 0.678% [0.658%, 0.693%] | Pass |
| [Defer unused-key warning paths #267](https://github.com/astral-sh/ohm-cargo/pull/267) | `check` | 0.245% [0.232%, 0.270%] | 0.259% [0.208%, 0.275%] | Pass |
| [Cache filtered feature dependencies #268](https://github.com/astral-sh/ohm-cargo/pull/268) | `check` | 1.321% [1.309%, 1.330%] | 1.302% [1.290%, 1.316%] | Pass |
| [Borrow unescaped depfile paths #269](https://github.com/astral-sh/ohm-cargo/pull/269) | `build` | 1.256% [1.245%, 1.267%] | 1.899% [1.893%, 1.916%] | Pass |
| [Move locked version requirements #270](https://github.com/astral-sh/ohm-cargo/pull/270) | `check` | 0.325% [0.301%, 0.327%] | 0.315% [0.302%, 0.345%] | Pass |
| [Compare path prefixes by word #247](https://github.com/astral-sh/ohm-rust/pull/247) | `build` | 2.747% [2.720%, 2.764%] | 5.427% [5.417%, 5.441%] | Pass |

The final two builds have identical Cargo source and different standard libraries. Their independently collected Cargo profiles shared 47,703 function names and control-flow hashes. Of 660,144 comparable basic-block counters, 536 differed across 169 functions. [Training-profile comparison](profile-build/intermediates/guard-vs-semver-block-profiles.json)

## Five changes together

Dynamic counts cover user-space instructions in the Cargo process and its threads. Kernel work and executed compiler and linker subprocesses are outside that count. Native elapsed time below includes the whole command from launch through exit. Each comparison uses the same binary and target paths for both arms.

| Comparison | Cargo command | Parent → candidate (M instructions) | Paired reduction [rank interval] | Wins/pairs | Exact p |
| --- | --- | --- | --- | --- | --- |
| Warm workspace | `check` | 886.30 → 864.33 | 2.476% [2.438%, 2.506%] | 12/12 | 0.000488281 |
| Warm workspace | `build` | 953.56 → 916.43 | 3.896% [3.882%, 3.903%] | 12/12 | 0.000488281 |
| Warm workspace | `test --no-run` | 1,002.83 → 977.82 | 2.488% [2.478%, 2.499%] | 12/12 | 0.000488281 |
| Edited workspace | `check` | 889.27 → 867.21 | 2.473% [2.388%, 2.567%] | 8/8 | 0.0078125 |
| Edited workspace | `build` | 1,038.65 → 998.15 | 3.901% [3.398%, 3.945%] | 8/8 | 0.0078125 |
| Edited workspace | `test --no-run` | 1,656.24 → 1,630.99 | 1.524% [1.482%, 1.607%] | 8/8 | 0.0078125 |

All 48 edited invocations rebuilt exactly `uv v0.12.0`. All 16 test builds reported the same 72 executables from 53 packages.

## Native elapsed time for the five Cargo changes

The `matched-base` and `semver` Cargo drivers run the same released Ohm rustc and Wild. Each cell gives baseline → stack median seconds, then the median paired reduction and rank interval, wins, and exact two-sided sign-test p. A speedup requires positive medians, p < 0.05/3 on the initial cohort and p < 0.05 on its independent repeat. The warm-workspace gate also requires a positive initial interval.

| Workspace | Cargo command | Initial | Independent repeat | Elapsed-time gate |
| --- | --- | --- | --- | --- |
| Warm | `check` | 0.4835 → 0.4700 s<br>-1.347% [-8.553%, 1.884%]<br>21/48 wins, p = 0.470879 | 0.4545 → 0.4753 s<br>-1.788% [-8.046%, 1.545%]<br>19/48 wins, p = 0.193413 | Inconclusive in both cohorts |
| Warm | `build` | 0.4663 → 0.4662 s<br>-1.463% [-4.224%, 1.399%]<br>20/48 wins, p = 0.312327 | 0.4918 → 0.4788 s<br>3.028% [-2.115%, 9.702%]<br>28/48 wins, p = 0.312327 | Inconclusive in both cohorts |
| Warm | `test --no-run` | 0.5264 → 0.5317 s<br>4.050% [-4.867%, 11.029%]<br>25/48 wins, p = 0.885433 | 0.5103 → 0.5017 s<br>1.310% [-1.980%, 2.628%]<br>29/48 wins, p = 0.193413 | Inconclusive in both cohorts |
| Edited | `check` | 2.9285 → 2.7638 s<br>-0.789% [-53.734%, 33.311%]<br>4/8 wins, p = 1 | 2.8172 → 2.8315 s<br>-4.492% [-21.126%, 16.083%]<br>4/8 wins, p = 1 | Inconclusive in both cohorts |
| Edited | `build` | 5.9418 → 6.0254 s<br>-7.517% [-22.110%, 12.589%]<br>3/8 wins, p = 0.726562 | 6.6701 → 7.5177 s<br>-3.479% [-60.916%, 9.730%]<br>3/8 wins, p = 0.726562 | Inconclusive in both cohorts |
| Edited | `test --no-run` | 6.1933 → 6.0201 s<br>-1.769% [-23.588%, 33.773%]<br>4/8 wins, p = 1 | 6.9012 → 7.6921 s<br>-5.433% [-41.684%, 14.626%]<br>2/8 wins, p = 0.289062 | Inconclusive in both cohorts |

A formatter invocation pinned to CPU 28 started a rustup download during the warm five-Cargo repeat. It was interrupted after 18 seconds. The original observations, overlap timestamps and host telemetry are included in the archive. An additional 48-pair repeat used a fresh balanced order after the scheduled runs and an idle preflight. The original qualification gate still applies.

| Extra warm repeat | Parent → candidate, paired reduction and interval |
| --- | --- |
| `check` | 0.4330 → 0.4299 s<br>-0.044% [-1.274%, 1.364%]<br>23/48 wins, p = 0.885433 |
| `build` | 0.4698 → 0.4619 s<br>1.715% [-0.503%, 8.385%]<br>30/48 wins, p = 0.111403 |
| `test --no-run` | 0.4852 → 0.4835 s<br>0.320% [-2.115%, 2.060%]<br>25/48 wins, p = 0.885433 |

## Native elapsed time for the combined Cargo, standard-library and Wild changes

The baseline uses the `base` Cargo driver and `wild-baseline`. The candidate uses `guard-stack`, which contains the five Cargo changes and the guarded standard-library path comparison, with `wild-undefined`. The same released Ohm rustc compiles uv in both arms. Each comparison uses a private copy of the release with a stable linker path. Sealed Cargo SHA-256 prefixes are `744843355906` → `42b0c136d6ad`. Wild prefixes are `82a927b86f92` → `435a253fcd8a`.

| Workspace | Cargo command | Initial | Independent repeat | Elapsed-time gate |
| --- | --- | --- | --- | --- |
| Edited | `check` | 3.1482 → 3.3724 s<br>5.497% [-72.471%, 18.842%]<br>5/8 wins, p = 0.726562 | 3.2273 → 3.8472 s<br>-19.236% [-41.555%, 46.245%]<br>2/8 wins, p = 0.289062 | Inconclusive in both cohorts |
| Edited | `build` | 8.7419 → 10.3676 s<br>-12.360% [-77.140%, 27.548%]<br>3/8 wins, p = 0.726562 | 7.0443 → 7.2063 s<br>-7.006% [-47.862%, 35.936%]<br>2/8 wins, p = 0.289062 | Inconclusive in both cohorts |
| Edited | `test --no-run` | 7.5382 → 8.4763 s<br>2.407% [-56.782%, 31.307%]<br>5/8 wins, p = 0.726562 | 7.3621 → 7.4126 s<br>-3.396% [-79.775%, 29.025%]<br>3/8 wins, p = 0.726562 | Inconclusive in both cohorts |

## Standard library and linker drafts

The standard-library change scans shared path prefixes a machine word at a time. Both Cargo executables were rebuilt with the released Ohm compiler, ThinLTO and one codegen unit. The original distribution's PGO profile was unavailable. The test matrix includes the public `Path` suite, an added ordering regression test, and three independent comparison oracles. [Rust #247](https://github.com/astral-sh/ohm-rust/pull/247)

| Comparison | Cargo command | Parent → candidate (M instructions) | Paired reduction [rank interval] | Wins/pairs | Exact p |
| --- | --- | --- | --- | --- | --- |
| 76-byte checkout, DynamoRIO | `build` | 981.33 → 932.76 | 4.952% [4.937%, 4.956%] | 12/12 | 0.000488281 |
| 28-byte checkout, Cachegrind | `build` | 930.84 → 907.63 | 2.497% [2.483%, 2.579%] | 8/8 | 0.0078125 |

Replaying 93,550 recorded path comparisons saved 45.64% of the instructions in the isolated workload. Long paths that differ in their second byte cost three extra instructions per comparison (+0.21%).

Wild moves undefined-symbol reporting into a cold function. Each real edited `cargo test --no-run` launched five linkers. All eight four-command blocks improved across 160 linker processes. The median reduction in Wild instructions was 1.230% [0.952%, 1.984%] (two-sided sign p = 0.0078125, order-conditioned randomization p = 0.02857). An independent Callgrind replay of the largest link saved 1.155%. All 20 serial ELF replays and 18 native parallel replays matched their respective reference outputs. [Wild #45](https://github.com/astral-sh/ohm-wild/pull/45)

## Second Wild change, on top of #45

Wild recognizes the default `.text*` and `.rela*` ELF placement rules from a validated section-name table. Both arms used the same Cargo rebuilt from unmodified release sources and the same shipped rustc. The primary workload executed 32 edited `cargo test --no-run --locked --offline -j4` commands and counted all threads in 160 Wild invocations. The balanced-order randomization p was 0.0285714. [Wild #46](https://github.com/astral-sh/ohm-wild/pull/46)

| Workload | Wild instruction reduction [rank interval] | Improved | Sign p |
| --- | --- | --- | --- |
| Edited test builds, five linkers per command | 3.873% [3.739%, 3.956%] | 8/8 | 0.0078125 |
| Independent 319 MB uv executable | 3.385% [3.380%, 3.389%] | 10/10 | 0.00195312 |
| Independent 10 MB test harness | 0.187% [0.182%, 0.196%] | 10/10 | 0.00195312 |

The complete output digest sets matched for 10/10 output and edit combinations. The parent itself produced multiple complete digests in 2 combinations. Both reserved replay inputs reproduced their reference bytes on all 40 invocations. [Output digests](components/wild-prefix/actual/artifacts.json) · [Byte comparisons](components/wild-prefix/actual/byte-differences.json)

Controls used six complete permutations of parent, first implementation and published implementation. Positive values below are additional instructions relative to #45. [Control samples](components/wild-prefix/pilot/samples.csv)

| Control | First implementation | Published implementation |
| --- | --- | --- |
| 188-member uv-client archive, partial link | +0.9003% | +0.2156% |
| Data-heavy object, custom script | +0.2585% | +0.0001% |
| Same object, default rules | -0.1202% | -0.4632% |

## Combined Cargo and standard-library driver

These direct comparisons use identically built Cargo executables with the parent or all five Cargo changes plus the standard-library change. A settled workspace invokes no linker. The two checkout lengths expose variation in the path-scanning gain.

| Comparison | Cargo command | Parent → candidate (M instructions) | Paired reduction [rank interval] | Wins/pairs | Exact p |
| --- | --- | --- | --- | --- | --- |
| 28-byte checkout, DynamoRIO | `check` | 824.31 → 803.14 | 2.566% [2.455%, 2.581%] | 8/8 | 0.0078125 |
| 28-byte checkout, DynamoRIO | `build` | 932.75 → 874.81 | 6.212% [6.193%, 6.235%] | 8/8 | 0.0078125 |
| 28-byte checkout, DynamoRIO | `test --no-run` | 984.91 → 959.07 | 2.626% [2.598%, 2.639%] | 8/8 | 0.0078125 |
| 76-byte checkout, Cachegrind | `build` | 980.41 → 892.23 | 8.991% [8.905%, 9.005%] | 8/8 | 0.0078125 |

| Workspace | Cargo command | Initial | Independent repeat | Elapsed-time gate |
| --- | --- | --- | --- | --- |
| Warm | `check` | 0.6513 → 0.6966 s<br>-6.350% [-26.027%, 5.724%]<br>19/48 wins, p = 0.193413 | 0.4612 → 0.4558 s<br>2.672% [-4.317%, 12.144%]<br>26/48 wins, p = 0.665466 | Inconclusive in both cohorts |
| Warm | `build` | 0.5626 → 0.4797 s<br>-1.419% [-6.096%, 25.918%]<br>23/48 wins, p = 0.885433 | 0.5179 → 0.5472 s<br>-1.427% [-17.644%, 3.108%]<br>22/48 wins, p = 0.665466 | Inconclusive in both cohorts |
| Warm | `test --no-run` | 0.6243 → 0.6649 s<br>-4.108% [-28.400%, 8.609%]<br>23/48 wins, p = 0.885433 | 0.5392 → 0.5466 s<br>1.870% [-10.290%, 8.525%]<br>26/48 wins, p = 0.665466 | Inconclusive in both cohorts |

## Independently built Cargo drivers

The standalone build script rebuilt the original and fifth Cargo revisions from clean source archives. A second comparison applied all five changes to the exact source of the concurrent Cargo stack through #266. These runs used Cachegrind. [Cargo #266](https://github.com/astral-sh/ohm-cargo/pull/266)

| Comparison | Cargo command | Parent → candidate (M instructions) | Paired reduction [rank interval] | Wins/pairs | Exact p |
| --- | --- | --- | --- | --- | --- |
| Clean driver builds | `check` | 839.84 → 817.90 | 2.612% [2.501%, 2.628%] | 8/8 | 0.0078125 |
| Clean driver builds | `build` | 951.72 → 914.71 | 3.889% [3.868%, 3.904%] | 8/8 | 0.0078125 |
| Clean driver builds | `test --no-run` | 1,001.15 → 976.25 | 2.484% [2.474%, 2.505%] | 8/8 | 0.0078125 |
| Concurrent stack | `check` | 837.17 → 815.16 | 2.627% [2.616%, 2.729%] | 8/8 | 0.0078125 |
| Concurrent stack | `build` | 936.71 → 898.91 | 4.034% [4.028%, 4.056%] | 8/8 | 0.0078125 |
| Concurrent stack | `test --no-run` | 999.36 → 971.02 | 2.835% [2.821%, 2.869%] | 8/8 | 0.0078125 |

The fresh-build check harness rejected an invocation that rebuilt dependencies. Its log is retained. Subsequent native and instrumented traces were fresh. The remaining check and test cohorts required the second instrumented warmup for each arm to be fresh before collecting their full eight pairs.

## Downloaded release binary

Each row compares the downloaded Ohm Cargo to a locally built driver at a fixed path. The complete packaging, compiler and profile differences enter this comparison. The matched parent/candidate rows above isolate the changes in this work.

| Comparison | Cargo command | Parent → candidate (M instructions) | Paired reduction [rank interval] | Wins/pairs | Exact p |
| --- | --- | --- | --- | --- | --- |
| Unmodified local build, Cachegrind | `check` | 767.69 → 822.64 | -7.156% [-7.177%, -7.017%] | 0/8 | 0.0078125 |
| Unmodified local build, Cachegrind | `build` | 875.78 → 930.82 | -6.286% [-6.302%, -6.267%] | 0/8 | 0.0078125 |
| Unmodified local build, Cachegrind | `test --no-run` | 919.33 → 983.31 | -6.965% [-6.976%, -6.939%] | 0/8 | 0.0078125 |
| Combined local build, Cachegrind | `check` | 767.66 → 801.77 | -4.447% [-4.454%, -4.437%] | 0/8 | 0.0078125 |
| Combined local build, Cachegrind | `build` | 875.80 → 873.07 | 0.313% [0.294%, 0.417%] | 8/8 | 0.0078125 |
| Combined local build, Cachegrind | `test --no-run` | 919.31 → 956.91 | -4.085% [-4.099%, -4.072%] | 0/8 | 0.0078125 |
| Retrained unmodified build, DynamoRIO | `check` | 850.50 → 797.69 | 6.209% [6.183%, 6.311%] | 8/8 | 0.0078125 |
| Retrained unmodified build, DynamoRIO | `build` | 959.05 → 888.66 | 7.340% [7.296%, 7.359%] | 8/8 | 0.0078125 |
| Retrained unmodified build, DynamoRIO | `test --no-run` | 1,007.28 → 946.90 | 6.007% [5.901%, 6.019%] | 8/8 | 0.0078125 |
| Retrained combined build, DynamoRIO | `check` | 850.53 → 779.31 | 8.371% [8.269%, 8.470%] | 8/8 | 0.0078125 |
| Retrained combined build, DynamoRIO | `build` | 959.01 → 836.03 | 12.826% [12.808%, 12.837%] | 8/8 | 0.0078125 |
| Retrained combined build, DynamoRIO | `test --no-run` | 1,007.31 → 923.37 | 8.333% [8.244%, 8.346%] | 8/8 | 0.0078125 |

The negative control put the identical downloaded executable in both arms and ran each default Cargo command with a populated offline registry. Its paired differences show measurement variation on this host.

| Comparison | Cargo command | Parent → candidate (M instructions) | Paired reduction [rank interval] | Wins/pairs | Exact p |
| --- | --- | --- | --- | --- | --- |
| Released binary against itself | `check` | 850.67 → 850.58 | 0.004% [-0.021%, 0.032%] | 5/8 | 0.726562 |
| Released binary against itself | `build` | 959.12 → 959.14 | -0.004% [-0.021%, 0.088%] | 3/8 | 0.726562 |
| Released binary against itself | `test --no-run` | 1,007.15 → 1,007.23 | -0.005% [-0.085%, 0.023%] | 2/8 | 0.289062 |

## Individual Cargo draft PRs

Each change is measured against its immediate parent. The initial primary uses DynamoRIO, and the independently warmed repeat uses Cachegrind. The additional release-style comparison uses Cachegrind with binaries built by the Ohm compiler using ThinLTO, one codegen unit and statically linked native libraries. The published distribution's PGO profile was unavailable for these source builds. The primary threshold is p < 0.05/6 and the repeat threshold is p < 0.05.

| Draft | Primary command | Initial reduction | Repeat | Release-style | Instruction gate |
| --- | --- | --- | --- | --- | --- |
| [#264 Borrow unit dependencies](https://github.com/astral-sh/ohm-cargo/pull/264) | `test --no-run` | 0.445% | 0.460% | 0.630% | Pass |
| [#267 Defer unused-key warning paths](https://github.com/astral-sh/ohm-cargo/pull/267) | `check` | 0.232% | 0.260% | 0.264% | Pass |
| [#268 Cache filtered feature dependencies](https://github.com/astral-sh/ohm-cargo/pull/268) | `check` | 1.575% | 1.598% | 1.593% | Pass |
| [#269 Borrow unescaped depfile paths](https://github.com/astral-sh/ohm-cargo/pull/269) | `build` | 2.238% | 1.684% | 1.512% | Pass |
| [#270 Move locked version requirements](https://github.com/astral-sh/ohm-cargo/pull/270) | `check` | 0.380% | 0.371% | 0.303% | Pass |

<details>
<summary>Arm medians, intervals and sign tests for each change</summary>

| Comparison | Cargo command | Parent → candidate (M instructions) | Paired reduction [rank interval] | Wins/pairs | Exact p |
| --- | --- | --- | --- | --- | --- |
| #264 initial | `check` | 854.23 → 851.75 | 0.297% [0.275%, 0.312%] | 12/12 | 0.000488281 |
| #264 initial | `build` | 1,004.00 → 999.36 | 0.461% [0.438%, 0.489%] | 12/12 | 0.000488281 |
| #264 initial | `test --no-run` | 1,015.69 → 1,011.31 | 0.445% [0.416%, 0.466%] | 12/12 | 0.000488281 |
| #264 repeat | `test --no-run` | 1,014.89 → 1,010.18 | 0.460% [0.379%, 0.472%] | 8/8 | 0.0078125 |
| #264 release-style | `test --no-run` | 982.62 → 976.45 | 0.630% [0.595%, 0.648%] | 8/8 | 0.0078125 |
| #267 initial | `check` | 852.34 → 850.32 | 0.232% [0.223%, 0.262%] | 12/12 | 0.000488281 |
| #267 initial | `build` | 1,000.53 → 998.60 | 0.193% [0.177%, 0.212%] | 12/12 | 0.000488281 |
| #267 initial | `test --no-run` | 1,012.34 → 1,010.02 | 0.220% [0.208%, 0.243%] | 12/12 | 0.000488281 |
| #267 repeat | `check` | 836.72 → 834.54 | 0.260% [0.245%, 0.271%] | 8/8 | 0.0078125 |
| #267 release-style | `check` | 820.55 → 818.36 | 0.264% [0.244%, 0.288%] | 8/8 | 0.0078125 |
| #268 initial | `check` | 850.10 → 836.69 | 1.575% [1.569%, 1.597%] | 12/12 | 0.000488281 |
| #268 initial | `build` | 998.55 → 987.00 | 1.153% [1.145%, 1.165%] | 12/12 | 0.000488281 |
| #268 initial | `test --no-run` | 1,010.15 → 995.51 | 1.447% [1.438%, 1.463%] | 12/12 | 0.000488281 |
| #268 repeat | `check` | 834.75 → 821.40 | 1.598% [1.569%, 1.618%] | 8/8 | 0.0078125 |
| #268 release-style | `check` | 818.39 → 805.38 | 1.593% [1.581%, 1.605%] | 8/8 | 0.0078125 |
| #269 initial | `check` | 881.61 → 881.13 | 0.046% [0.032%, 0.082%] | 11/12 | 0.00634766 |
| #269 initial | `build` | 986.88 → 964.78 | 2.238% [2.212%, 2.275%] | 12/12 | 0.000488281 |
| #269 initial | `test --no-run` | 995.32 → 994.87 | 0.037% [0.033%, 0.055%] | 12/12 | 0.000488281 |
| #269 repeat | `build` | 933.49 → 917.75 | 1.684% [1.659%, 1.787%] | 8/8 | 0.0078125 |
| #269 release-style | `build` | 913.85 → 900.06 | 1.512% [1.500%, 1.518%] | 8/8 | 0.0078125 |
| #270 initial | `check` | 822.35 → 819.21 | 0.380% [0.351%, 0.400%] | 12/12 | 0.000488281 |
| #270 initial | `build` | 919.40 → 916.32 | 0.333% [0.315%, 0.354%] | 12/12 | 0.000488281 |
| #270 initial | `test --no-run` | 980.89 → 977.87 | 0.302% [0.286%, 0.324%] | 12/12 | 0.000488281 |
| #270 repeat | `check` | 820.73 → 817.70 | 0.371% [0.346%, 0.388%] | 8/8 | 0.0078125 |
| #270 release-style | `check` | 805.30 → 802.83 | 0.303% [0.275%, 0.322%] | 8/8 | 0.0078125 |

</details>

Keeping the filtered dependencies increased peak RSS on warm `cargo check`. GNU time reported parent and candidate medians of 105.1 and 105.8 MiB. The median paired increase was 0.751% [0.341%, 0.872%] across 16 pairs (p = 0.00418091).

<details>
<summary>Package-targeted real edits for the first draft</summary>

| Comparison | Cargo command | Parent → candidate (M instructions) | Paired reduction [rank interval] | Wins/pairs | Exact p |
| --- | --- | --- | --- | --- | --- |
| `-p uv --lib` | `check` | 803.34 → 801.17 | 0.266% [0.186%, 0.327%] | 8/8 | 0.0078125 |
| `-p uv` | `build` | 878.46 → 875.92 | 0.292% [0.214%, 0.343%] | 8/8 | 0.0078125 |
| `-p uv --test it` | `test --no-run` | 882.54 → 880.14 | 0.271% [0.251%, 0.296%] | 8/8 | 0.0078125 |

</details>

## Reading the measurements

Reductions are medians of paired `1 − candidate/parent` values. Arm columns are separate medians. Positive reductions mean less work or elapsed time. The exact two-sided sign test omits ties. Distribution-free intervals use symmetric order statistics at the highest rank that retains at least 95% coverage. Actual coverage is 99.22% at 8 pairs, 96.14% at 12 pairs, 97.87% at 16 pairs, 97.07% at 48 pairs.

The warm instruction cohorts use `--locked --offline -j16` and the real-edit cohorts use `-j8`. Each edited comparison changes the same source bytes for both arms and moves each arm's copy of a common warmed target to the same visible path. All reported comparisons use fixed balanced pair counts. Missing or partial cohorts cannot pass a gate.

## Correctness and CI

The five Cargo drafts have 40 passing checks in total. The Rust draft has 3 passing checks. Wild's release workflow has 24 setup failures before source checkout because its action references do not satisfy the organization's full-SHA policy. A separate workflow checked out the exact Wild PR head and passed 0 jobs. It covers 12 selected x86-64 ELF cases, four native arm64 Mach-O cases, and two AArch64 LLVM 21 fixtures whose release and PR output bytes matched. [Wild CI validation](https://github.com/astral-sh/ohm-wild/actions/runs/40732795058) · [Recorded checks](verification/ci-snapshot.json)

Wild #46 also inherits the release workflow. Its PR checks include 24 setup failures. The native workflow checked out `93600ec37547` and passed 0 of 3 jobs. The suites cover 35 x86-64 ELF fixtures, the new ELF regression test, four native arm64 Mach-O fixtures and byte comparisons of two AArch64 LLVM 21 fixtures. [Native run](https://github.com/astral-sh/ohm-wild/actions/runs/40745398550) · [Test receipts](verification/wild-prefix/prefix-results.txt)
