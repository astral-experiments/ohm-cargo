# A single compile and link after selecting an edited Ruff integration test

With a previously built library, Ohm compiled and linked Ruff’s newly selected ty_server integration test twice. Checking whether the scheduler already completed that library removes the duplicate. The workspace then ran two full compilers and two real Wild links instead of three of each. The fix also removed 13 speculative compiler processes and 12 linker processes in the native empty-state comparison. [Compiler and linker traces](https://github.com/astral-sh/ohm-cargo/tree/e6f94f097c18d813c9088f829cd1fb6feebbe63a/benchmarks/ruff-dev-loop-20261027/early-tests-completion-native-results)

| Full workspace test-build workload | Paired runs | Parent median | Fixed median | Paired reduction (95% interval) | Faster pairs | Holm-adjusted p |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| First selection after the real test edit | 24 | 8.297 s | 7.138 s | 13.86% (11.12% to 16.70%) | 24/24 | 0.00000148 |
| Empty workspace build | 12 | 291.54 s | 289.85 s | 0.65% (0.08% to 1.33%) | 8/12 | 0.0758 |

The first workload reverses the complete historical Ruff change 1b9310471b. Each arm receives a private copy of a settled workspace previously built with ty_server tests excluded. Both then run the ordinary full workspace test build. Each pair produced 110 byte-identical native files across its two arms and the same 200-test e2e listing. There were 619 Cargo units and 102 reported executables. No test body ran inside any timed command. The cold workload did not meet the registered speed criterion.

A separate, prospectively registered 16-core tmpfs replication cold-trained an independent seed for each pair. The parent and fixed medians were 8.127 s and 6.911 s. All 12 favored the fix, with a paired reduction of 21.51% (95% interval 12.81% to 33.10%, exact two-sided p=0.00216). Its programs and complete Cargo diagnostics also matched. [Independent host results](https://github.com/astral-sh/ohm-cargo/tree/b2de0ba32f1a261452db67f340c480d35194bb18/benchmarks/ruff-dev-loop-20261027/early-tests-h2-replication-results)

Both primary endpoints used matched Cargo release-profile builds on the 1.99.0-16 source base with the same released Rust compiler and Wild. The ext4 study held commands, canonical directories, CPU affinity and jobs constant. It retained every scheduled pair. The statistics use the geometric mean of within-pair treatment/control time ratios, the fixed-seed paired bootstrap and exact balanced-assignment randomization, with Holm adjustment for the two endpoints. [Registered methods and report threshold](https://github.com/astral-sh/ohm-cargo/tree/1844efed56043bca3add46f9ccac806a17af829c/benchmarks/ruff-dev-loop-20261027/early-tests-completion-wall-plan-v2)

Run `python3 -B verify.py` to reconstruct the 72 process clocks and 96 untimed follow-up commands. Each pair archive contains the original command results, native-file hashes, follow-up Cargo rosters and actual harness listing. One host-specific registry directory is given a portable spelling in 96 of the 841 exported records. The inventory retains both the original and portable hashes.
