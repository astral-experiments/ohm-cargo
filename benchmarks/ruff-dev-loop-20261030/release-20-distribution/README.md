# Ohm 1.99.0-20 Linux release qualification

The Linux release candidate passed the reported proc-macro span, external assembler, and native-library regressions. Its artifact SHA-256 is `edb64a2ee39b2f2951614f98d53ec4e4197f55149ff794c911bd81bc7f870b15`. The Cargo and rustc executables identified their commits as `2d44bd4aa` and `7e71d3150`. These results use the Linux distribution built by the release workflow. The branch-return optimization in [Ohm Rust #274](https://github.com/astral-experiments/ohm-rust/pull/274) is outside these pins. [Release run](https://github.com/astral-experiments/ohm/actions/runs/41004598527)

| Build script declaration | Stock Cargo 1.99.0 | Signed Ohm -19 | Ohm -20 Linux |
| --- | --- | --- | --- |
| Native library file | 83 / 101 | 83 / 101 | 83 / 101 |
| Native library search directory | 83 / 101 | 83 / 101 | 83 / 101 |
| Only `build.rs` | 0 / 0 | 0 / 0 | 0 / 0 |

The first value is the test program’s exit code after a valid library appears earlier on the linker's search path. The new library changes the program from 0 to 83. The second is Cargo’s exit code after a malformed library replaces it. A correct relink rejects the input with 101. Every distribution relinked for the declared file and directory. All six changed executables matched the corresponding independently clean build byte for byte. All three tools retained the old binary when the build script declared only itself. Removing the old executable or using an empty build produced 83 / 101 in every case. The fixture uses Ruff’s locked `zmij 1.0.10`. [Recorded verdicts](observations.json) · [Cargo change](https://github.com/astral-experiments/ohm-cargo/pull/294)

The Linux package also completed `cargo check`, `cargo build`, and `cargo test --no-run` with the original multibyte proc-macro span fixture under the defaults and with `-Zohm-defaults=no`. Running both programs checked the values 34 and 17. In each mode, changing a nested assembler input yielded 29 and reproduced the clean executable. A missing or malformed input failed the build. [Artifact digests](linux-artifact.json) · [Release manifest](release-manifest.json)

To replay the native-library cases, install the selected x86-64 Linux SDK as `+ohm` and cache `zmij 1.0.10` for offline use. Choose new output directories. The programs use the system assembler and GCC linker script.

```sh
python3 -IB replay-declaration.py ./changed-file file
python3 -IB replay-declaration.py ./changed-directory directory
python3 -IB replay-declaration.py ./undeclared none
```

Each invocation records seven Cargo test builds and executes the resulting programs. The `none` run checks the behavior shared by all three toolchains. [Checksummed reference reproducer](native-input-repro.py)
