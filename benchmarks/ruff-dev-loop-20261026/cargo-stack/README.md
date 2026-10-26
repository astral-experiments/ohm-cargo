# Cumulative Cargo comparisons

Ruff is pinned to `93526150df078af7dd8fc4226cdcc469539d2001`. Start with an Ohm Cargo checkout at `461a3d1007ecc997a6d86c7d75e8b518575c8d90`. The first two changes borrow lockfile identity keys and cache decoded registry source strings. The third reuses owned registry manifests. The fourth shares the workspace lint table. [#242](https://github.com/astral-sh/ohm-cargo/pull/242), [#243](https://github.com/astral-sh/ohm-cargo/pull/243), [#244](https://github.com/astral-sh/ohm-cargo/pull/244), [#245](https://github.com/astral-sh/ohm-cargo/pull/245)

The two lockfile changes touch overlapping lines. Apply one of `two.patch`, `three.patch`, or `four.patch` to the base revision to obtain the exact combination used here. Each cumulative change is measured against a release-matched parent.

The edited default check restores an identical pre-edit target snapshot before each arm. It replays the seven-line `FORCE_COLOR` deletion from Ruff `da8ee78491f784cdead4c69e83c58bc87fd0622c` against the pinned checkout. Both arms must emit 520 identical artifact records, rebuild only the Ruff CLI binary, and launch exactly Cargo and one rustc. Callgrind counts both processes. The output lists the raw paired counts, as well as the median paired reduction and the exact two-sided randomization p-value conditional on arm-order balance.

On Linux use a Rustup Cargo proxy, Python 3, Valgrind, rsync, GNU cp, and taskset. The disposable Ruff checkout must include the historical edit’s parent. Populate Cargo’s registry once with `cargo +ohm fetch --locked`. Build both binaries with the same toolchain, dependencies, features, and profile. Keep the target outside the output directory. The script physically copies the complete Ohm toolchain to isolate it from other installations.

```sh
python3 edited.py \
  --parent "$PARENT_CARGO" --candidate "$CANDIDATE_CARGO" --toolchain "$OHM_RELEASE" \
  --ruff "$RUFF_CHECKOUT" --target "$RUFF_TARGET" --shared "$SHARED_BUILD_DIR" \
  --output "$RUNS/edited" --cpu "$CPU" --pairs 12 --seed 660327
```

The ordinary release-profile builds used `CFG_RELEASE_CHANNEL=dev CARGO_PROFILE_RELEASE_INCREMENTAL=true cargo +ohm build --release --locked --offline -p cargo --bin cargo --features ohm-defaults`. PGO builds used the same source, prebuilt Ohm 1.99.0-14 compiler, and Cargo features, with release incremental compilation disabled and `-Cprofile-use` pointing to the release training data. The profile SHA-256 is `481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7`. Both PGO arms were compiled in the same directory and their binaries were frozen for all comparisons.

`pairs.csv` identifies each fixture and build profile. The two- and three-change default edit studies used seeds 57127 and 143021. The independent four-change checkout ran this standalone script with seed 660327. The PGO edit used seed 138763. The small PGO fresh check used the [fresh benchmark](../registry-manifests/) with `--package ruff_text_size --design paired --pairs 12 --artifact-messages --seed 682101`.
