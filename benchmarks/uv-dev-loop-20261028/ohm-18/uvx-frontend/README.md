# Compiler time after editing uvx

The proposed Cargo rule failed its large-module control. Adding a module with 4,096 reachable functions to a previously one-file binary made an ordinary edited cargo build 234 ms slower than shipped Ohm -18 (97.73% rank interval 128–577 ms) and 479 ms slower than the matched Cargo (240–729 ms). The candidate was slower in 21 of 24 paired blocks against each control. It used the previous build’s single-file dep-info to select one thread for the first edit. Once that edit had recorded the new file, the candidate selected eight threads again. This stopped promotion to a whole-uv wall-time study. [All 72 commands and standalone verifier](large-module-control.tar.gz)

The patched and pristine Cargo binaries each trained on the same 24 bitmaps and Diesel commands. Twelve structural cases finished and every compared executable matched. In the final library control, shipped Cargo succeeded but the verifier expected an archive member starting with uv- and encountered frontlib-. The failed module margin comes from its own complete cell. The archive preserves the separate error and every original observation.

Changing rustc from eight frontend threads to one saved 38–44 ms when recompiling the edited uvx binary on Ohm 1.99.0-18. The time includes the link. Each of the six comparisons used 48 balanced pairs on a 32-vCPU AMD EPYC Milan KVM guest with 16 vCPUs available to the workload. Each checkout used a different real source edit. The brackets show 97.07% paired intervals in milliseconds.

| rustc invocation | First edit, ms saved | Second edit, ms saved | Rustc instructions saved on each edit |
|---|---:|---:|---:|
| Binary during cargo build | 43.68 [39.91, 46.72] | 41.96 [36.80, 44.68] | 13.39% / 13.24% |
| Binary during cargo test --no-run | 40.61 [37.75, 45.84] | 39.72 [36.73, 46.65] | 13.37% / 13.19% |
| Binary test harness during cargo test --no-run | 42.75 [40.28, 46.15] | 38.44 [33.86, 43.45] | 18.47% / 18.94% |

Every instruction pair favored one thread. The 48 instruction pairs used a separate DynamoRIO run and count all rustc threads. The ELF and dep-info matched byte for byte at admission and postflight. Cargo can run its two test-preparation compiler roles concurrently. Ordinary whole-command speedup remains unmeasured for this candidate. [Raw observations and standalone scorer](observations.tar.gz) · [Paired results](results.csv) · [Fresh-host capture and rerun instructions](FRESH-HOST.md)

The Cargo patch extends the existing small-check rule to native Linux x86-64 debug incremental builds of ordinary workspace binaries and their test harnesses. It requires a small root and previous unit dep-info naming only that root. Three Cargo integration tests passed on the release parent. The test archive includes the original post-run log-reader error, the corrected argument check and the portable verification. [Candidate patch](candidate.patch) · [Test logs and verifier](regression-tests.zip)

The source, sample rosters, toolchain digests, effect thresholds, randomization schedule and host checks are in the observations archive. Its offline scorer and the regression verifier were re-run from a fresh directory on the original host. The instructions for gathering fresh timings have been checked against the saved compiler arguments.
