# Full Ruff test compilation after the native-link repair

With the native-link repair in rustc, Cargo #291 removed 12 full compiler invocations in each of two unchanged Ruff workspace test builds. Both ran the same 103 native links. A later copy of the release-Cargo build state showed that the absolute number of compiles can vary.

| rustc | Cargo | Full rustc | Link-only rustc | Wild | Fresh Cargo artifacts out of 619 |
| --- | --- | ---: | ---: | ---: | ---: |
| #263 | Release pin | 74 | 0 | 71 | 503 |
| #266 | Release pin | 119 | 0 | 103 | 433 |
| #266 | #291 | 107 | 0 | 103 | 470 |

The first two rows isolate the cost of correcting stale binaries. Rechecking native inputs added 45 full compiler invocations and 32 links. The final two rows isolate the Cargo change. It saved two `chacha20` compilations with different crate metadata and one each for `compact_str`, `ruff_graph`, `ruff_python_ast`, `rustix`, `tempfile`, `terminal_size`, `ty_ide`, `ty_module_resolver`, `ty_python_semantic` and `zmij`. Every configuration still linked all 50 test targets selected before the run. [Rust #263](https://github.com/astral-sh/ohm-rust/commit/960c75a231a4bed61cb9fcfac744ea37161ea23d) · [Rust #266](https://github.com/astral-sh/ohm-rust/commit/ad005f99d0b51fd62b5c237bc13b31b371a1686e) · [Release Cargo](https://github.com/astral-sh/ohm-cargo/commit/7277e6cdaba44c43294a07c0661fc8e69fd8e3e7) · [Cargo #291](https://github.com/astral-sh/ohm-cargo/commit/84af87848a5a952ba61ae6a2cc5b22da24130200)

A follow-up copied the warm #266 and release-Cargo state. The first unchanged build launched 119 full compilers and the second launched 127. The latter added `cachedir`, `assert_fs`, the `ruff` library, `insta`, `insta-cmd`, `mdtest`, `ty_test` and `ruff_mdtest`. Both copied runs still linked the same 103 outputs and produced the same 50 test executables and inventories. The follow-up required identical compiler counts before introducing a native provider, so it stopped at that point. It included only release Cargo. The full-workspace counts in the table describe the original three installs. The independent, counterbalanced results for `ruff_python_ast` are recorded separately. [Package experiment and rerun script](https://github.com/astral-sh/ohm-cargo/tree/b8a08ddff1e5c6c8205a4615d563bdf8b8e3b024/benchmarks/ruff-dev-loop-20261029/native-links-and-assembly)

## Workload

Each configuration ran the command below three times on the same four pinned Linux CPUs with the same authenticated offline registry and stock Wild. Each started with its own empty target directory, shared build directory and Cargo home. The source-built binaries occupied the same visible paths in each configuration. [Ruff revision](https://github.com/astral-sh/ruff/commit/93526150df078af7dd8fc4226cdcc469539d2001)

```sh
cargo +ohm test --workspace --no-run --locked --offline -j4 --message-format=json
```

Each cold run emitted 619 Cargo artifact records, all freshly built. Across those units we observed 623 full rustc processes, one separate rustc target query and 188 stock Wild links. The table counts executed processes on the two following runs. Neither repeat needed a target query. We did not time these builds.

All 50 test-name lists matched across all nine invocations. The `ty_server` e2e executable matched byte for byte, retained all 200 test names and passed the three selected inlay-hints and notebook cases. Three other harnesses each produced two distinct executable hashes across the runs, for the `ruff` and `ty` binaries and the `ty_python_semantic` library. Their code and read-only data sections matched. The only differing allocated payload was the GNU build ID. Every loaded segment matched after masking exactly its parsed build-ID descriptor.

## Verify the observations

```sh
sha256sum --check SHA256SUMS
python3 -IB verify.py --self-test
```

The verifier checks all nine runs, reconstructs the two comparisons by compiler unit and native output, and rejects six deliberately corrupted observations. The compressed records include compiler and linker argument digests, Cargo targets, executable and inventory hashes, and digests of the original traces. They also record where the `psm` search directory appeared in the native linker arguments. The separate native-provider trials exercise which library was selected. The full ELF files and traces remain in the original run. [Native-provider trials](https://github.com/astral-sh/ohm-cargo/tree/86086c93eb70ed3ba340a2769b550642ba90520b/benchmarks/ruff-dev-loop-20261029/release-20-ty-server-e2e)
