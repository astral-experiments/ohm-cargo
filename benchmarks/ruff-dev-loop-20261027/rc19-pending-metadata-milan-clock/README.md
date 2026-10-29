# Milan timing for pending Cargo metadata dependencies

Cargo #279 reduced the median paired time for an edited Ruff workspace check plus its first unchanged repeat by **20.07%** on Milan. All 32 pairs favored the candidate on that endpoint. The edited check alone took **2.37% longer** at the paired median. Only Milan has a completed timing cohort. Genoa reached its registered disk-space floor after two qualified pairs. The protocol requires both hosts for a cross-host performance recommendation. [Cargo #279](https://github.com/astral-sh/ohm-cargo/pull/279)

| Endpoint | Median A | Median B | Median paired saving | 95% block-bootstrap interval | Faster pairs | Exact block sign-flip p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Edit plus first repeat, primary | 17.867 s | 14.187 s | 20.07% | 19.10% to 20.94% | 32/32 | 0.0078125 |
| Edit | 9.674 s | 9.806 s | −2.37% | −3.82% to −0.02% | 9/32 | 0.0703125 |
| First unchanged repeat | 8.269 s | 4.378 s | 47.01% | 46.83% to 47.13% | 32/32 | 0.0078125 |

Each pair contributes `1 − B/A`. The primary adds the edit and repeat durations within each visit before computing that ratio. The two time columns are separate medians across the 32 visits per arm. The prespecified analysis resamples eight four-pair blocks 20,000 times for the two-sided interval and enumerates all 256 sign assignments for the test on block means of log time ratios. The primary passed its Milan threshold. The edited-only point estimate did not reach the separately registered 3% slowdown threshold.

## What ran

Each visit ran `cargo +ohm check --workspace --locked --offline -j8 --message-format=json` twice on eight physical cores. The real Ruff edit reversed and reapplied `2d6ce561250a464e1fa231ef30e54d0f029f76a4` against its parent `716260bf10d7ae1d965ed9b22653e57fbc960582`. It changes 29 Cargo manifests and one CI file. Cargo.lock has the same Git blob and SHA-256 in both revisions. Each group of four pairs contains both source directions crossed with both arm orders. Terminal visit file timestamps independently confirm the assigned sequence for all 64 visits. Only the edited and first unchanged checks entered the timing analysis. [Historical Ruff change](https://github.com/astral-sh/ruff/commit/2d6ce561250a464e1fa231ef30e54d0f029f76a4)

The matched release-profile Cargo images came from `235f9228651b74c591e6f62cae4c9b761448dd2d` (A, ELF `3a94265b0d3c…`) and `b3360c5eda186845b9a2ba6e5330a97c07d4acf2` (B, ELF `51eb6c59a381…`). The candidate changes one Cargo fingerprint source file. Both arms used the same packaged 1.99.0-18 Rust compiler, standard library and stock Wild. The fresh matched A has a different ELF from the historical control `6aaa263e…`. The original cold B `46555df3…` had different linked dependencies and was excluded before measurement. The full original matched build attestation is included.

## Correctness and work

The 32 pairs contain 128 scored checks and 128 off-clock flanks. All 256 Cargo stdout streams ended in a successful build-finished message and contained exactly 510 typed artifact records. The before and after source states differ in 30 typed records when multiplicity is preserved. Matching those records without their target test and doctest flags recovers the same inventory. The two arms agreed on each source-specific inventory.

The four donor receipts identify a common archive for both arms at each source revision. Their commitments to all 597 physical output products matched across arms at that revision. Across the two source revisions, 41 product paths had different contents. Each preflight and after check confirmed 12 dirty artifacts, the expected full typed inventory and the two fresh, byte-identical selected metadata products for `ruff_python_ast` and `ruff_python_index`. Those 128 flank receipts carry these two file digests. The terminal collection carries commitments to the separate 597-file admission rather than a physical rehash of 597 products after each command.

The edited checks reported 56 dirty Cargo artifacts every time. B's first unchanged checks reported 12 every time. A reported 21 in 25 visits, 12 in four and 24 in three. The separately traced controls recorded 51 full rustc processes and one stock Wild on A's edit, followed by 12 full rustc processes on its first unchanged check. B recorded 52 full rustc processes and one Wild on the edit, followed by one full rustc on the first unchanged check. Both next settled checks ran one full rustc. A distinct one-file method-body control ran two then one full rustc on both arms. These process counts come from off-clock qualification. The scored checks retained ordinary Cargo output.

## Verification

Run `python3 -IB verify.py` in this directory. The verifier replays the exact published roster and paired analyzer and checks them against an independent implementation. It verifies all 256 receipt bindings, every ordered Cargo artifact identity and freshness verdict, all 143,872 message positions and the per-visit times against the original pair records. The companion `python3 -IB selftest.py` checks that altered clocks, order, freshness, flank hashes and source evidence are rejected. The archive inventory contains **1,234 entries** consisting of 880 regular files and 354 directories.

The compressed ledgers retain each ordered JSON line's original SHA-256, its class, the typed fields used in the registered inventory, and the original whole-stream and stderr hashes. Workspace package identifiers are rendered relative to the Ruff source root. To repeat the original-byte reconstruction, pass `python3 -IB verify.py --archive /path/to/complete.tgz` with the retained private archive whose SHA-256 is `3cc9112b7b9081e69ca753f676faa48dac7e0b5a8a02f05bcc5070dc9fee7514`. The command reopens all 880 files and compares the reconstructed ledgers and frozen protocol byte-for-byte.

