# Ruff notebook edit and clean build on Ohm 1.99.0-18

The Linux x86-64 release ran the same full Ruff workspace test build with a real change to the notebook range clamp on a private checkout of Ruff `93526150df078af7dd8fc4226cdcc469539d2001`. The compiler and the packaged Wild were the distributed binaries. Cargo ran as UID 1000 with a complete host UID map and root-owned filesystem and home ancestors. Its edit transition ran 52 real native links, including `ty_server` e2e. The resulting 226,518,928-byte executable was byte-identical to a separate edited build starting with an empty target and empty shared build directory. Both executables listed the same 200 cases and failed `notebook::hover_past_end_of_cell` and `notebook::inlay_hints_range_past_end_of_cell` at the expected changed assertions. Restoring the source ran 52 links, recovered the original 226,518,976-byte executable, and passed those tests.

| Workspace run | Cargo artifacts | Fresh | Full rustc | Cached link rustc | Stock Wild | e2e SHA-256 prefix | Two notebook tests |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| First and second unchanged baseline | 619 | 563 | 1 | 50 | 50 | `be6b9375` | pass |
| Real notebook edit | 619 | 559 | 12 | 43 | 52 | `d76ef359` | fail |
| Next unchanged | 619 | 563 | 1 | 50 | 50 | `d76ef359` | fail |
| Separate empty-store edited build | 619 | 0 | 623 | 0 | 188 | `d76ef359` | fail |
| Restore source | 619 | 559 | 12 | 43 | 52 | `be6b9375` | pass |
| Final unchanged | 619 | 563 | 1 | 50 | 50 | `be6b9375` | pass |

Each of the unchanged workspace commands in the table compiled `ron` and executed the same 50 named native links. The unchanged focused `-p ty_server --test e2e` command reported 300 fresh artifacts with zero rustc or linker executions. The first transition from the earlier restricted UID mapping readmitted 605 workspace artifacts. Independent H8 data records the same 50 native links and successful cache reads under the ordinary UID mapping. [Independent host controls](https://github.com/astral-sh/ohm-cargo/tree/66e712e684f763abaf250463bd4fe9918d1dcc42/benchmarks/ruff-dev-loop-20261027/rc19-native-queue-h8-environment)

One extra unchanged workspace rebuild after switching the selection back from the focused command produced a third raw e2e digest, `eb4c8725`, at the original length. Both notebook tests passed. Its raw-byte cause is unresolved. The edited-versus-clean and original-versus-restored comparisons above use separate directly observed equalities. The initial switch to the focused command succeeded, but the initial verifier rejected an ordinary failing GCC feature probe before running its two test oracles. Its process record is retained separately. The subsequent complete focused repeat supplied the 300/300 result.

Run `python3 -IB verify.py` and `sha256sum -c SHA256SUMS` in this directory. The verifier recounts the executable identities, ordered-argument digests, linked output names, and exits of 5,507 physical processes. The projection preserves digests of the raw process reports and Cargo stdout and stderr. This study measures native execution counts and validates results. It contains no wall-time estimate.
