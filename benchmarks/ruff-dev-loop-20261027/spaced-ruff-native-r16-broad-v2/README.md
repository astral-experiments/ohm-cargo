# Native Ruff test builds on r16-broad-v2

The package ran `cargo +ohm test --no-run -p ty_project` on a target directory containing a space. The full 619-unit workspace ran the same test-build command with `--workspace` in a toolchain directory containing a space. Both used the same original Ruff source, locked offline resolution, four Cargo jobs, and compiler JSON. Each started with empty private target and build directories and had three unchanged repeats. The worker lists a real test harness outside each Cargo command. It records all four package native products or all 110 workspace ELF products, including the 102 runnable workspace outputs.

This first corrected compiler introduced a new crate dependency. Its BOLT coverage fell from 13,399 profiled functions to 1,553. These records establish process counts and functionality only. The profile-matched replacement and the source-matched parent have separate native qualifications.

| Selection | Command | Units | Dirty | Full rustc | Link-only rustc | Wild links | Native products identical to the preceding command |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| package | 0 | 303 | 303 | 304 | 0 | 50 | cold |
| package | 1 | 303 | 3 | 1 | 1 | 1 | 4 |
| package | 2 | 303 | 0 | 0 | 0 | 0 | 4 |
| package | 3 | 303 | 0 | 0 | 0 | 0 | 4 |
| workspace | 0 | 619 | 619 | 636 | 0 | 201 | cold |
| workspace | 1 | 619 | 56 | 1 | 50 | 50 | 110 |
| workspace | 2 | 619 | 0 | 0 | 0 | 0 | 110 |
| workspace | 3 | 619 | 0 | 0 | 0 | 0 | 110 |

The compiler, Cargo, frontend, native driver, standard-library view, linker identities and effective sysroot are recorded in the run archive. No test body ran and wall time was not scored. When the candidate reported zero compiles and native links, all native outputs remained byte-identical to the preceding command. [Registered RC wall-clock study](https://github.com/astral-sh/ohm-cargo/tree/8895a739552df06a4d4914b09acfd9c4764beb89/benchmarks/ruff-dev-loop-20261027/rc17-spaced-ruff-wall-plan)

Run `python3 -B verify.py` to reconstruct successful rustc and linker executions from the actual execve records. The verifier joins them to Cargo units and checks native product digest records, the observed input trailer and the actual command status. The export contains 8,776 entries. One host-specific registry basename was replaced in 741 entries. Original and portable digests are recorded separately.
