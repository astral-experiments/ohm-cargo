# Ruff workspace test builds on Ohm Cargo #291 and #292

On each of two ordinary unchanged `cargo test --workspace --no-run` commands, the child Cargo converted 16 of 107 full compiler invocations into 16 link-only invocations. Both Cargo versions still launched stock Wild 103 times, including once for each of the 50 inventoried Ruff test executables. Their empty builds each emitted 619 typed Cargo artifacts and launched 623 full compilers and 188 linkers. [Parent Cargo PR](https://github.com/astral-sh/ohm-cargo/pull/291) · [Child Cargo PR](https://github.com/astral-sh/ohm-cargo/pull/292)

Adding a native library earlier on the search path changed the exit of all 50 test executables to 83 on both Cargo versions. Removing it restored all 50 programs and their inventories. Both Cargos rejected malformed replacements in ordinary and forced builds. A genuine Ruff inlay-hint edit matched an independently empty build across all 213,692,248 bytes, and an invalid Rust edit failed with E0308. The checks reopened all 103 distinct retained native binaries and 103,988 per-thread trace files from 40 source and native-provider commands. The separate six-command baseline includes both cold builds and both unchanged visits for each Cargo.

Run both checks from this directory. The two subdirectories also include independent, source-bound rerun instructions and the original packet manifests.

```sh
python3 -IB unchanged/verify-extra.py --self-test
python3 -IB native-provider/verify-native.py --self-test
```
