# Repeat the seven-command public qualification

Use x86-64 Linux, Python 3.11 or newer, GNU coreutils, Git, GCC, and Rustup. Provide a complete matched Ohm SDK with the compiler from guarded revision `6b7f424ece4bc978ead5546b73e1b31d5ccb1e70`, Cargo `2d44bd4aa68b9ba32cacb5a384ecc18fa5e7553c`, and stock Wild. The independent formal packet enumerates all 55 matched Rust files. These comparisons used optimized source-built stage1 Rust. [Ohm Rust](https://github.com/astral-experiments/ohm-rust) · [Ohm Cargo](https://github.com/astral-experiments/ohm-cargo)

Supply a Cargo home preloaded for offline resolution at the common Ruff lockfile SHA-256 `839edc8250480bb523619b8d24bd57176a6e1f57c152cca85c5adc61ea5f94eb`. The historical Ruff checkout must expose merge `7b13f01ba1569887a25670820764b24c206da8e5` and its first parent `b5dba861cc38e3f7fb4524c9ceba3e01a474ea13`. The runner reads both donors and copies them into its own new directory. Its outputs include the complete raw processes, native executables, test listings, diagnostics and benchmark timings. The timings from this seven-case validation do not form a statistical sample. [Historical Ruff change](https://github.com/astral-sh/ruff/pull/28335)

Run this block from the packet directory, after setting the four input paths and CPU set for your machine. The new study needs room for one checkout, the SDK and registry copies, an incremental target, and two saved executables. The work filesystem should have at least 8 GiB free above those requirements in this example. Use the same absolute working directory in independent cross-arm replications. A path change or a different SDK can alter a whole binary’s raw bytes. Within a local experiment compare each return against the empty reference from its own SDK, source and paths.

```sh
export GUARDED_SDK=/path/to/guarded-sdk
export RUFF_CHECKOUT=/path/to/ruff
export CARGO_OFFLINE_HOME=/path/to/prepopulated-cargo-home
export STUDY_BASE=/absolute/path/to/new-reviewer-study
export CPU_SET=0-3
mkdir -m 700 "$STUDY_BASE"
taskset -c "$CPU_SET" python3 -IB replay_one.py \
  --sdk "$GUARDED_SDK" --ruff-checkout "$RUFF_CHECKOUT" \
  --cargo-home "$CARGO_OFFLINE_HOME" --work "$STUDY_BASE/work" \
  --out "$STUDY_BASE/result" --mode controls --min-free-gib 8
python3 -IB readback.py "$STUDY_BASE/result" > "$STUDY_BASE/reread.json"
```

Run `python3 -IB verify.py` against the supplied qualification without building anything. Its original host had enough RAM for a separate private 12-GiB work filesystem, where the launcher’s minimum free setting was 1 GiB. Host process and memory guards were supervised independently.
