# Cumulative Cargo comparisons

Ruff is pinned to `93526150df078af7dd8fc4226cdcc469539d2001`. Start with an Ohm Cargo checkout at `461a3d1007ecc997a6d86c7d75e8b518575c8d90`. The first two changes borrow lockfile identity keys and cache decoded registry source strings. The third reuses owned registry manifests. The fourth shares the workspace lint table. [#242](https://github.com/astral-sh/ohm-cargo/pull/242), [#243](https://github.com/astral-sh/ohm-cargo/pull/243), [#244](https://github.com/astral-sh/ohm-cargo/pull/244), [#245](https://github.com/astral-sh/ohm-cargo/pull/245)

The last two changes defer omitted fields when encoding lockfile edges and reuse the interned source ID of a locked dependency. `six.patch` contains all six runtime changes. The source-ID PR additionally has a unit test that is compiled out of the measured binary. [Lockfile encoding change](https://github.com/astral-sh/ohm-cargo/pull/246), [locked source-ID change](https://github.com/astral-sh/ohm-cargo/pull/247)

The two lockfile changes touch overlapping lines. Apply one of `two.patch`, `three.patch`, `four.patch`, or `six.patch` to the base revision to obtain the exact combination used here. Each cumulative change is measured against a release-matched parent.

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

A second build of the PGO control after compiling all candidates reproduced every loaded section except the build ID. The 25,303,611-byte `.text` section was byte-identical (SHA-256 `6d434a71f88c1b33b05d51cb43e8c13e83b0e182756510e63d550d2d232ac952`), as were the read-only data, dynamic symbols, relocations and unwind tables. The full executable also contains differing linker symbol and string tables.

Six changes against the release-PGO baseline used seed 191017 for the CLI edit. The incremental comparison of six versus four changes used seed 611276 on the same frozen edit fixture. For the ordinary-output four-change warm matrix, run [the fresh harness](../registry-manifests/) with `--mode all --design paired --pairs 12 --seed 127841`. Validation runs process Cargo JSON before and after each cohort. A scored command is rejected if child tracing sees any executable other than Cargo.

## Measured results

| Ruff command and Cargo changes | Favorable pairs | Median instruction reduction | 95% median interval | Randomization p |
| --- | ---: | ---: | ---: | ---: |
| CLI edit, first two Cargo changes | 12/12 | 0.65% | 0.61–0.76% | 0.00216 |
| CLI edit, first three Cargo changes | 12/12 | 1.68% | 1.61–1.79% | 0.00216 |
| CLI edit, four PGO changes | 12/12 | 2.28% | 2.18–2.48% | 0.00216 |
| CLI edit, six PGO changes | 12/12 | 2.98% | 2.88–3.05% | 0.00216 |
| CLI edit, six PGO changes versus the four-change PGO stack | 12/12 | 0.69% | 0.61–0.87% | 0.00216 |
| CLI edit, four Cargo changes on a second checkout | 12/12 | 1.89% | 1.84–1.93% | 0.00216 |
| Fresh check of ruff_text_size, four PGO changes, Cargo JSON | 12/12 | 8.37% | 8.37–8.37% | 0.00216 |
| Fresh default check, four PGO changes, Cargo JSON | 12/12 | 2.68% | 2.65–2.69% | 0.00216 |
| Fresh default build, four PGO changes, Cargo JSON | 12/12 | 0.97% | 0.96–0.98% | 0.00216 |
| Fresh default test --no-run, four PGO changes, Cargo JSON | 12/12 | 2.46% | 2.43–2.48% | 0.00216 |
| Fresh default check, four PGO changes, ordinary Cargo output | 12/12 | 2.90% | 2.89–2.91% | 0.00216 |
| Fresh default build, four PGO changes, ordinary Cargo output | 12/12 | 1.03% | 1.02–1.04% | 0.00216 |
| Fresh default test --no-run, four PGO changes, ordinary Cargo output | 12/12 | 2.59% | 2.59–2.60% | 0.00216 |
| Fresh default check, six PGO changes, Cargo JSON | 12/12 | 3.40% | 3.37–3.43% | 0.00216 |
| Fresh default build, six PGO changes, Cargo JSON | 12/12 | 1.50% | 1.46–1.52% | 0.00216 |
| Fresh default test --no-run, six PGO changes, Cargo JSON | 12/12 | 3.14% | 3.11–3.19% | 0.00216 |
