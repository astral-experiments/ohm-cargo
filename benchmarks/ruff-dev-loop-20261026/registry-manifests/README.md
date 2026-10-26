# Owned registry manifests

The base is Ohm Cargo `461a3d1007ecc997a6d86c7d75e8b518575c8d90`. The treatment is `e0c8d5d08ce852965ecb7f06e3cff97651892acb`. Both used the release profile, `--features ohm-defaults`, release incremental compilation, and no PGO. Rustc came from the x86-64 Linux Ohm 1.99.0-14 release. Ruff is pinned to `93526150df078af7dd8fc4226cdcc469539d2001`.

`pairs.csv` retains the Cargo counts for warm Ruff checks, builds, and test compilation, and the full Cargo and rustc counts for a historical edit to `ruff_cache`. The default check used DynamoRIO with child following disabled and `--message-format=json`, processing 520 fresh artifacts. The linter check used Callgrind with child tracing and 268 fresh artifacts. The edited check replayed the change to `crates/ruff_cache/src/cache_key.rs` from `47eb6ee42b046338b91a9c0131b6283a348ff12d` from an identical pre-edit target snapshot per observation. Nine out of twelve full edited checks improved.

`fresh.py` runs a two-binary Callgrind comparison in independently randomized four-run blocks. It selects the two opposite parent/candidate run orders in each block. It verifies the artifact list before and after timing, and rejects an observation if a compiler or linker runs. The output includes the raw profiles, paired counts and a two-sided exact randomization test that exchanges labels at the block level.

Use Python 3, Valgrind, `taskset`, and a Rustup Cargo proxy on Linux. Build the two binaries with `CFG_RELEASE_CHANNEL=dev CARGO_PROFILE_RELEASE_INCREMENTAL=true cargo +ohm build --locked --release -p cargo --bin cargo --features ohm-defaults`, keeping the resolved Cargo dependencies identical between builds. Prime Ruff’s registry with `cargo +ohm fetch --locked` once. Use a fresh output directory, a dedicated target directory for the Ruff checkout, a separate shared build directory, and an available CPU or affinity mask.

```sh
python3 fresh.py \
  --parent "$PARENT_CARGO" --candidate "$CANDIDATE_CARGO" \
  --toolchain "$OHM_RELEASE" --ruff "$RUFF_CHECKOUT" \
  --target "$RUFF_TARGET" --shared "$SHARED_BUILD_DIR" --output "$RUNS/linter" \
  --mode check --package ruff_linter --blocks 8 --cpu "$CPU"
```

Omit `--package` to measure the default workspace. `--mode build` runs `cargo build`. `--mode test` runs `cargo test --no-run`.

Full default commands used 520 artifacts for check, 501 for build, and 619 for test compilation. The five-arm DynamoRIO comparisons verify every artifact during each measured command. `Callgrind-default-check` records a separate 12-pair, two-arm check with Cargo JSON validation. `linter-portable` records the separate eight-block run of the public script with `--seed 712461`.

To reproduce the two-arm full check using the same artifact output, omit `--package` and add `--design paired --pairs 12 --artifact-messages`. Each timed command must return the complete expected list of fresh artifacts. The p-value conditions on the observed balance of parent-first and candidate-first pairs. For a five-arm DynamoRIO row, `first_arm` indicates the relative order of the parent and this change within the larger block.
