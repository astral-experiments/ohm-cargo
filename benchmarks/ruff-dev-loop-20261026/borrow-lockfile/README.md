# Borrow package identities while decoding Cargo.lock

Ruff is pinned to `93526150df078af7dd8fc4226cdcc469539d2001`. The Cargo base is `461a3d1007ecc997a6d86c7d75e8b518575c8d90` from Ohm `1.99.0-14`. The treatment is `f98a9e825516553171c88a85d55bfff7b0f9b748` in `astral-sh/ohm-cargo`. The compiler and linker come from the published x86-64 Linux Ohm release. Cargo binaries were locally built in the release profile, with Ohm defaults enabled and no PGO.

`pairs.csv` records the original observations. The edited check counted Cargo and rustc together, with the same incremental target restored before every observation. Every run rebuilt `ruff_text_size` once. The fresh check counted Cargo. Its original holdout compared four binaries in randomized rotations, with the table retaining the parent and this patch. The additional two-arm replication used the reproduction script below.

## Reproduce

Use Valgrind 3.22, a Rustup Cargo proxy, Python 3, `taskset`, `cp`, and `rsync` on Linux. Build both Cargo revisions with `cargo +ohm build --locked --release -p cargo --bin cargo --features ohm-defaults`. We set `CARGO_PROFILE_RELEASE_INCREMENTAL=true` and `CFG_RELEASE_CHANNEL=dev` for each build, and saved both binaries before switching checkouts. Set `CARGO_HOME` to a private Cargo home containing Ruff’s locked dependencies. Fetch them once with `cargo +ohm fetch --locked` in the pinned Ruff checkout.

Give the script a clean, disposable Ruff checkout at that commit, a dedicated target directory for that checkout, and a separate shared Ohm build directory. The toolchain argument is the directory containing the release’s `bin/rustc` and `lib`. Use a fresh output directory for each experiment. The script builds a private Rustup toolchain called `ohm` there and changes its Cargo binary between observations. `ruff-edit.patch` contains the `size.rs` hunk from Ruff commit `438ef334d3e71ef0ac70927c799fb159d8f25267`.

```sh
python3 reproduce.py \
  --parent "$PARENT_CARGO" --candidate "$CANDIDATE_CARGO" \
  --toolchain "$OHM_RELEASE" --ruff "$RUFF_CHECKOUT" \
  --target "$RUFF_TARGET" --shared "$SHARED_BUILD_DIR" \
  --output "$RUNS/edited" --kind edited --pairs 12 --seed 3331 --cpu "$CPU"

python3 reproduce.py \
  --parent "$PARENT_CARGO" --candidate "$CANDIDATE_CARGO" \
  --toolchain "$OHM_RELEASE" --ruff "$RUFF_CHECKOUT" \
  --target "$RUFF_TARGET" --shared "$SHARED_BUILD_DIR" \
  --output "$RUNS/fresh" --kind fresh --pairs 16 --seed 7729 --cpu "$CPU"
```

Each experiment writes the raw instruction profiles and `pairs.csv`. The command is `cargo +ohm check -p ruff_text_size --locked --offline`. The edited experiment also uses `--message-format=json` to verify the dirty target. The script computes the median paired percentage reduction and a two-sided exact randomization p-value for the mean instruction difference, enumerating the possible assignments with the same number of parent-first and candidate-first pairs. Instrumented wall time is excluded from the performance estimates.
