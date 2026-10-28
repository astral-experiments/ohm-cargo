# Two fresh 32-core uv test-build confirmations

The late Wild jobserver retry passed 1 of four registered comparisons after a source edit to uv. Each checkout ran 36 three-linker blocks of the ordinary workspace `cargo test --no-run` on Ohm 1.99.0-18. The proposed change and both controls used the distributed release Cargo and rustc. The previous Wild control was the frozen #46 head `93600ec375`.

| Edit | Compared with | Control median | Candidate median | Paired median saving | Median interval | Faster pairs | Sign p | Order p |
|---|---|---:|---:|---:|---:|---|---:|---:|
| Homebrew predicate | Shipped -18 | 7.447 s | 6.455 s | +1.161 s (+16.30%) | -1.10% to +26.09% | 23/36 | 0.1325 | 0.17135 |
| Homebrew predicate | Previous #46 | 7.841 s | 6.455 s | +1.008 s (+13.34%) | +3.86% to +23.97% | 27/36 | 0.0039332 | 0.0077358 |
| Homebrew help text | Shipped -18 | 7.006 s | 6.459 s | +0.490 s (+6.49%) | +2.15% to +19.65% | 25/36 | 0.028817 | 0.040794 |
| Homebrew help text | Previous #46 | 8.007 s | 6.459 s | +1.335 s (+15.87%) | +6.93% to +27.63% | 26/36 | 0.011331 | 0.018355 |

Positive savings mean the candidate was faster. The distribution-free median intervals cover 97.12%. The paired median uses both times for the same edit and block. Each control had to have a positive lower bound and both exact two-sided p-values below .0125 in both checkouts. All six linker orders occurred six times per checkout. [Frozen assignment](../registered-32-heldout.json) · [Exact statistics](qualification.json) · [Raw rows](samples.csv)

Both cohorts compiled all 72 expected test executables without executing them. Admission and post-run tracing checked the Cargo/rustc/Wild process counts and the outputs. The host observer recorded 0 competing build or profiler events across 216 scored invocations. The raw receipts preserve wall times, CPU time and input/output counts. [Logs and traces](full-logs.zip) · [Host and workload audit](rosters-and-quiet.json)

The result misses the registered publication criterion. The 2.24-second discovery estimate came from a different checkout and contributed zero observations to this confirmation. The later release-only experiment required all four original comparisons to pass, so it stays unrun. [Discovery](../discovery-results.json) · [Release-only entry criterion](../standalone-after-upstream-rebase/registered-standalone.json)

While these fixed binaries were running, Ohm Wild #45 closed and #46 was rebased directly onto Wild 0.11. Both the previous #46 control and its candidate in this study include the older #45. The shipped control is exactly the linker from the published -18 distribution. [Wild #45](https://github.com/astral-sh/ohm-wild/pull/45) · [Wild #46](https://github.com/astral-sh/ohm-wild/pull/46)

The replay kit includes the two measured Linux x86-64 candidate binaries, source patch, raw observations and the original measurement harness. The included audit command recomputes the result without compiling. [Download the replay kit](replay.zip)
