# Native Ruff test builds on rc17-checked-paths-v4

The package ran `cargo +ohm test --no-run -p ty_project` on a target directory containing a space. The full 619-unit workspace ran the same test-build command with `--workspace` in a toolchain directory containing a space. Both used the same original Ruff source, locked offline resolution, four Cargo jobs, and compiler JSON. Each started with empty private target and build directories and had three unchanged repeats. The worker lists a real test harness outside each Cargo command. It records all four package native products or all 110 workspace ELF products, including the 102 runnable workspace outputs.

| Selection | Command | Units | Dirty | Full rustc | Link-only rustc | Wild links | Native products identical to the preceding command |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| package | 0 | 303 | 303 | 304 | 0 | 50 | cold |
| package | 1 | 303 | 3 | 1 | 1 | 1 | 4 |
| package | 2 | 303 | 0 | 0 | 0 | 0 | 4 |
| package | 3 | 303 | 0 | 0 | 0 | 0 | 4 |
| workspace | 0 | 619 | 619 | 636 | 0 | 201 | cold |
| workspace | 1 | 619 | 56 | 1 | 50 | 50 | 109 |
| workspace | 2 | 619 | 0 | 0 | 0 | 0 | 110 |
| workspace | 3 | 619 | 0 | 0 | 0 | 0 | 110 |

The compiler, Cargo, frontend, native driver, standard-library view, linker identities and effective sysroot are recorded in the run archive. No test body ran and wall time was not scored. When the candidate reported zero compiles and native links, all native outputs remained byte-identical to the preceding command. [Registered RC wall-clock study](https://github.com/astral-sh/ohm-cargo/tree/10b787284743bab1bacf9474115d67c1d079f3a4/benchmarks/ruff-dev-loop-20261027/rc17-spaced-ruff-wall-plan-v2)

Run `python3 -B verify.py` to reconstruct successful rustc and linker executions from the actual execve records. The verifier joins them to Cargo units and checks native product digest records, the observed input trailer and the actual command status. The export contains 8,643 entries. One host-specific registry basename was replaced in 741 entries. Original and portable digests are recorded separately.

The complete BOLT logs for both builds are included. They report 13,384 profiled functions in the canceled source build and 13,381 in the corrected one, with 5.3% stale samples in each. Both used the same donor profiles, Rust frontend and standard library.
