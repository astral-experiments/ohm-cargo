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
