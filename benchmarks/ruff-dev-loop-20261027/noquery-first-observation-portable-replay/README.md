# Replay the first foreign-span observation and a backdated external library edit

This Linux reproducer runs ordinary `cargo +ohm build` and `rustc +ohm` offline. It requires Python 3.11+, rustup proxies on PATH, `readelf`, `strace`, the selected Cargo and rustc driver, and a matching x86-64 Ohm SDK. It creates an isolated target, shared build directory and private rustup home below a new output directory. Allow 300 MiB of temporary space.

Point `SDK` at the root containing `bin/rustc` and `lib/rustlib`, `CARGO_IMAGE` at the chosen executable, and `DRIVER` at the selected `librustc_driver` image. Choose a new, nonexistent output directory on every run.

```sh
python3 -B replay-native.py \
    --sdk "$SDK" --cargo "$CARGO_IMAGE" --driver "$DRIVER" \
    --expected optional --fixture ./heldout-fixture --out ./replay-optional
```

| Expected mode | Cargo | Rust driver | Complete on first build | Additional query on first build |
| --- | --- | --- | --- | --- |
| `optional` | N | Supporting | Yes | 0 |
| `legacy` | N | Older | No | 0 |
| `probe` | Q | Supporting | Yes | 1 |
| `ignored` | A | Supporting | No | 0 |

The four supplied result files were produced by this exact script. A regular input is named `incidental.rlib`. A different archive, passed to rustc through `--extern`, actually changes the program from 17 to 29. The script changes it in place with the original length and nanosecond timestamp. In every mode, the dirty observation compiles one caller, the next unchanged command starts zero rustc compilations and the independent edited build prints 29. The private temporary SDK contains regular copies of Cargo, the frontend and the selected driver, ensuring rustc resolves its own sysroot unambiguously. The initial test with a symlinked driver stopped at the sysroot identity check before it ran Cargo. Raw Cargo JSON, the successful and failed execve calls, rustc depfiles, encoded fingerprints and program outputs remain under each new output directory.

The input binary digests and original shared-build inputs are in the [registered product contract](https://github.com/astral-sh/ohm-cargo/tree/4fa4cc2e5f3256b57e5b6e7b1c70ce0d32456061/benchmarks/ruff-dev-loop-20261027/noquery-release-pgo-native-subjects).
