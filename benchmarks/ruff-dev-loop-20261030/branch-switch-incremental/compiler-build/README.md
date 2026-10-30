# Building the matched compilers

The elapsed and instruction cohorts used optimized stage 1 compilers for x86-64 Linux. The parent and candidate source revisions, the complete Rust tree IDs, the Cargo revision, the source counts, the original bootstrap configuration digest, the CI LLVM and bootstrap executable digests, and the entire 55-file compiler comparison are in [the source ledger](../sources.json).

For each revision, the build exposed the complete source tree and its pinned Cargo submodule at the same physical source path. The two builds used the same bootstrap tools, the same LLVM build, and the same three-line `git-commit-info` stamp. Using a common stamp lets independently built standard libraries and compiler launchers compare byte for byte. The tested Git tree, recorded separately, identifies the source under test.

The configuration template is the exact configuration used, with its five installation-path prefixes replaced by `@BOOTSTRAP_ROOT@`. The directory contains the bootstrap Rust executables under `bootstrap-runtime/bin`, matching Rust LLVM under `ci-llvm`, and a `cargo-ohm` shim that runs the installed Ohm Cargo with `-Zohm-defaults=no` during bootstrap. The measured Ruff commands use ordinary `cargo +ohm`. Substitute the installation prefix in [the bootstrap configuration](bootstrap.toml.in).

```sh
python3 x.py build --ci false --config "$BOOTSTRAP_CONFIG" --build-dir "$BUILD_DIR" \
  --host x86_64-unknown-linux-gnu --target x86_64-unknown-linux-gnu \
  --jobs 4 --stage 1 compiler/rustc library
```

The compiler and library outputs came from `$BUILD_DIR/x86_64-unknown-linux-gnu/stage1`. Each complete replay SDK also contains the pinned Ohm Cargo binary, the same stock Wild and system linker helpers under `lib/rustlib/x86_64-unknown-linux-gnu/bin`, and the matching LLVM shared library. Check the two SDKs before replay. Among the Rust launcher, the driver and the 53 standard-library files, only the driver differed. Its SHA-256 is recorded for both arms.
