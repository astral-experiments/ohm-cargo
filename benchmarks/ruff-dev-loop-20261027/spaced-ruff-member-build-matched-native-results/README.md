# Real Ruff ordinary builds before and after a typeshed edit

These 30 ordinary Cargo builds use the same Ruff checkout and two matched source-built Ohm toolchains. B uses the canceled -17 revisions and C uses the corrected -17 revisions. The SDK path is ordinary and the target directory contains one space. Every invocation ran from the actual workspace member. Cargo emitted a complete artifact stream and native process traces identify the full compilers and real Wild linker.

| Workload | B | C |
| --- | --- | --- |
| Unchanged `ty_wasm` after training, edit or restoration | 2 full rustcs and 1 Wild, 6 of 304 units dirty | 304 fresh, zero rustcs and zero Wild |
| Actual typeshed edit and its restoration, `ty_wasm` | 2 full rustcs and 1 Wild | 2 full rustcs and 1 Wild |
| Unchanged `ty_project` after training | 1 full rustc, 4 of 275 units dirty | 275 fresh, zero rustcs and zero Wild |

The source edit reverses seven lines from Ruff commit `1eab8c883aa32324a2710c1a277bf614b86cfba3` in `stdlib/functools.pyi`. An external Rust program was freshly linked for every observation. It calls the real `ty_vendored::file_system()`, checks the expected Ruff Git stamp when linked to `ty_wasm` and returns the exact expected stub bytes. The same bytes were independently recovered from the generated ZIP and an empty corrected history built with the edited source. The generated ZIP changes across the edit. The Linux `libty_wasm.so` was byte-identical across the two arms and the source edit and restoration.

All comparable artifact rosters, features, diagnostics, ZIPs and caller bytes match across arms. Each `ty_wasm` comparison matched one of five complete raw products across different histories and each `ty_project` comparison matched zero of four. The raw `.rlib` and `.rmeta` hashes are retained. Even within one toolchain and source, successive B compilations created different raw archive bytes. A separate diagnostic tests the exact object, metadata and symbol content of those archives, including the Rust link table. No clock was taken in this cohort.

Run `python3 -B verify.py` to independently recount every Cargo and native process and the 30 external callers from 6,232 retained records. Run `python3 -B derive-products.py` to reproduce the raw per-source output vectors and the cross-toolchain comparisons.

[Native protocol](https://github.com/astral-sh/ohm-cargo/tree/105d4404a56cc799c17c9d87d0264a9d2b0b807b/benchmarks/ruff-dev-loop-20261027/spaced-ruff-member-matched-native-plan) · [Unmodified -16 baseline](https://github.com/astral-sh/ohm-cargo/tree/cb4d3788af312218c3b224532df11eb7ff5341f9/benchmarks/ruff-dev-loop-20261027/spaced-ruff-member-build-stock-native-results)
