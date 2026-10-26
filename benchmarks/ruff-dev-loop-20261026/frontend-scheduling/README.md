# Native compiler thread counts on incremental Ruff checks

The discovery runs compared eight, four, two and one frontend threads in workspace compiler processes. All arms used the same diagnostic Cargo binary and the same Ohm 1.99.0-14 compiler. Cargo selected the frontend options itself. The source edits were the parser and linter discovery commits from the frozen historical corpus. [Workload selection](../entropy-corpus/)

On the first 32-vCPU host, 6 of 36 samples reported a package-cache lock wait. The raw timings are retained for diagnosis. The second 16-vCPU host used a private package cache, distinct target and shared directories, no concurrent benchmark processes and the normal job count. Each sample restored the same two pre-edit directories, verified the dirty artifact roster and compared all artifact metadata and API digests. The three randomized blocks had no lock waits.

On the second host, one frontend thread reduced summed child user and system CPU by 17.6–19.8% on the full parser edit and elapsed time by 0.9–3.4% in the three discovery blocks. The full lint edit had mixed elapsed results. The two libraries with the largest previous Cargo dependency files (47,805 and 162,575 bytes) took 6.8 s and 4.4 s at eight threads in a separate whole-parser timing trace. Smaller units such as `ruff_server` and `ty_test` took 0.67 s and 0.31 s with eight threads, and 0.56 s and 0.22 s with one. `discovery.csv` and `unit-durations.csv` contain every observation. These discovery samples selected the treatment.

## Frozen treatment and confirmation plan

The candidate is based on Ohm Cargo `461a3d1007ecc997a6d86c7d75e8b518575c8d90`. It chooses a single frontend thread on Linux x86-64 for native, incremental, non-test debug checks of workspace units with a prior regular Cargo dep-info file of at most 16 KiB. Missing dep-info on a cold unit and larger check units use the existing default of eight. The change runs before explicit compiler flags. SHA-256 of `candidate.patch` is `c3c30d90c59210a3919a7a049003ac2214d762856e1aff738ac7c3e889dd6e84`.

The native confirmation compares release-PGO control and candidate on the unseen parser and linter edits. Run the full workspace check for both and a package check for the parser. Each workload gets eight independently randomized ABBA or BAAB blocks, 16 paired comparisons, seed 737807. Include every sample. The timed child is ordinary `cargo +ohm check --locked --offline`, with `-p ruff_python_parser` for the scoped workload. Validate dirty diagnostics, the full roster, all emitted Rust metadata and API hashes outside the timed run. Reject a cohort on an unexpected compile, lock wait, source leak or artifact mismatch. Compare the block mean of within-pair log ratios using the exact two-sided sign-flip test and a block-bootstrap 95% interval. Adjust the three native endpoint p-values together using Holm.

The secondary instruction experiment compares the same PGO programs on the scoped parser holdout with 12 balanced randomized pairs and both Cargo and rustc counted. Keep its outcome separate from native time. The acceptance rule requires a reproducible reduction on at least one predeclared whole-command endpoint, plus native guard cases and preserved outputs. CPU time and the choice of threshold are exploratory until confirmed.

The replay script accepts paths to the disposable Ruff worktree and private measurement directories. It expects a Rustup proxy on PATH and prefilled `registry-home`, `frozen-toolchain`, `rustup/toolchains/ohm`, `target`, `shared`, and `entropy-corpus` under the pool. Copy both Cargo subjects to the pool filesystem and keep the compiler and its driver fixed. All release and benchmark paths are private to the experiment.

```sh
python3 replay.py holdout --blocks 8 --seed 737807 --out "$RESULTS" \
  --pool "$POOL" --ruff "$RUFF" --parent "$PARENT" --candidate "$CANDIDATE"
```

## First release-PGO confirmation

The 16-vCPU host completed all 96 observations using the fixed Linux executable search path `/home/dev-user/.cargo/bin:/usr/local/bin:/usr/bin:/bin`. Before timing, both programs reported 520/520 fresh artifacts on the workspace and 90/90 on the scoped command. A trace of the discovery parser's 35 compiler invocations confirmed that 32 received one frontend thread and three retained eight. All samples restored both the private target and the separate build directory.

| Holdout | Median control | Median candidate | Geometric elapsed reduction | 95% block-bootstrap interval | Exact p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Workspace check after the parser edit | 13.018 s | 12.347 s | 5.34% | 2.02–8.30% | 0.03125 | 0.09375 |
| Parser package check after the same edit | 0.606 s | 0.553 s | 16.66% | 7.30–24.29% | 0.03125 | 0.09375 |

The workspace linter endpoint failed its byte-equivalence gate. Exactly one of 442 metadata files, `ruff_linter.rmeta`, varied. All API files agreed. In six extra controlled rebuilds, stock Cargo also produced different bytes for that file from identical inputs. Its elapsed observations remain in `native.csv` and are excluded from inference. The native family retained all three endpoints for Holm, using p = 1 for the disqualified endpoint. Neither eligible elapsed result cleared 0.05 after adjustment. Two setup launches using an incompatible executable search path rebuilt registry units. Those launches were discarded before this complete run.

The separate complete scoped parser check saved **2.084%** instructions, with a conservative 95% median interval of **2.038–2.177%**. All 12 pairs improved (two-sided exact p = 0.002165). Each observation saw one Cargo and one rustc, 90 artifacts and exactly one dirty parser unit. All 72 metadata files and 72 API hashes agreed.

## Frozen native replication

Repeat the two byte-equivalent parser endpoints using the same unmodified release-PGO binaries, fixed search path, inputs, checkpoints and 16-vCPU host in a separate quiet observation window. Use 16 independently ordered ABBA or BAAB blocks per endpoint, 32 pairs each, seed 619913. All 128 timed commands will be retained. Apply the same complete output and roster gates, block-level exact randomization, 50,000-draw block bootstrap, and a two-endpoint Holm adjustment. The replication tests the elapsed effects observed in the first cohort, with no change to the threshold or code. The earlier disqualified linter endpoint remains excluded.
