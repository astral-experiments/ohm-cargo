# Native wall times with six Cargo changes

This compares the same six release-PGO Cargo changes and two frozen binaries as the [instruction-count experiment](../cargo-stack/). Ruff is at `93526150df078af7dd8fc4226cdcc469539d2001`. Each sample runs an ordinary, native `cargo +ohm check`, `cargo +ohm build`, or `cargo +ohm test --no-run`, with `--locked --offline`. The Rustup proxy, Cargo startup and process output are included in elapsed time. Before and after each cohort the harness requires matching package IDs, target names, target kinds and test flags across 520, 501 and 619 fresh records. A timed command that starts compiling invalidates the cohort.

The two cohorts used different random seeds and nonoverlapping four-CPU affinity sets on the same devbox. Each cohort has 16 ABBA/BAAB blocks per command. Within each block, the order of the three commands and each command’s arm order were randomized. The fixed plan required a positive interval and a Holm-adjusted two-sided p-value below 0.05 in **both** cohorts before claiming a wall-time improvement on a command. Every scored sample was retained. The CSV records any Cargo lock-wait notice. The instruction-count experiments are reported separately.

Run with Python 3, the Rustup `cargo` proxy, and Linux `taskset`. Use the [six-change patch and PGO recipe](../cargo-stack/) to build the two binaries. Populate Cargo's registry and use a disposable Ruff checkout, private Rustup home, distinct target directory, and separate shared build directory. Place a complete physical copy of Ohm 1.99.0-14 at `$PRIVATE_RUSTUP/toolchains/ohm`. `$RUNTIME_CARGO` must be an absolute path to a copy of the parent Cargo executable outside that toolchain. Replace **the private copy** of `toolchains/ohm/bin/cargo` with a short executable shell script that `exec`s that path and forwards `"$@"`. Keep the Cargo path, compiler and sysroot fixed when warming and scoring.

```sh
export RUSTUP_HOME="$PRIVATE_RUSTUP" RUSTUP_AUTO_INSTALL=0
export CARGO_TARGET_DIR="$RUFF_TARGET" CARGO_BUILD_BUILD_DIR="$SHARED_BUILD_DIR"
export CARGO_BUILD_JOBS=6 CARGO_TERM_COLOR=never LC_ALL=C.UTF-8
export CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST=all CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST=all
(cd "$RUFF_CHECKOUT" && cargo +ohm check --locked --offline && cargo +ohm build --locked --offline && cargo +ohm test --no-run --locked --offline)

taskset -c "$CPU_A" python3 native-fresh.py \
  --rustup "$PRIVATE_RUSTUP" --runtime-cargo "$RUNTIME_CARGO" \
  --parent "$PARENT_CARGO" --candidate "$CANDIDATE_CARGO" \
  --ruff "$RUFF_CHECKOUT" --target "$RUFF_TARGET" --shared "$SHARED_BUILD_DIR" \
  --blocks 16 --seed 796217 --output "$RUNS/native-a"
```

Repeat with `--seed 389371`, a fresh output directory, and a second available four-CPU set. `native-summary.py wall.csv` summarizes either cohort CSV or a combined CSV with one header. The statistic is the geometric mean of the block ratios. The exact sign-flip test exchanges labels at the block level. The 95% intervals resample whole blocks. A positive percentage means lower elapsed time.

## Results

All 384 timed invocations completed without a reported lock wait. The baseline and six-change Cargo produced the same fresh rosters before and after each cohort. None of the three commands passed the replication criterion for a wall-time claim.

| Seed and CPU affinity | Command | Estimated time saved | 95% block interval | Exact p | Holm-adjusted p |
| --- | --- | ---: | ---: | ---: | ---: |
| 796217, CPUs 8–11 | `check` | 2.33% | 0.48% to 4.02% | 0.0279 | 0.0836 |
| 796217, CPUs 8–11 | `build` | 1.33% | −2.70% to 5.19% | 0.5212 | 0.5212 |
| 796217, CPUs 8–11 | `test --no-run` | −3.76% | −9.75% to 1.00% | 0.2267 | 0.4533 |
| 389371, CPUs 20–23 | `check` | 2.32% | −0.41% to 5.29% | 0.1537 | 0.3653 |
| 389371, CPUs 20–23 | `build` | 4.33% | −0.25% to 9.39% | 0.1218 | 0.3653 |
| 389371, CPUs 20–23 | `test --no-run` | 0.73% | −4.32% to 5.57% | 0.7833 | 0.7833 |

An earlier warmup invoked the same Cargo binary from a different path and started rebuilding artifacts in a different Ohm namespace. It was interrupted before scoring. Both completed cohorts kept the same Cargo path used when the benchmark was primed.
