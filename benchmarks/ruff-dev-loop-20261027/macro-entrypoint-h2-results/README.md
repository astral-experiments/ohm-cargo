# Ruff index builds after a procedural-macro edit

On published Ohm 1.99.0-17, editing `ruff_macros` rebuilt both the macro and its `ruff_index` consumer. The library test executable has five tests. Its bytes stayed identical after reversing the complete `rule_namespace.rs` portion of a historical formatting commit, and after changing the error from the `RuleNamespace` derive. Changing the maximum integer emitted by `newtype_index`, which the tests use, changed the executable. [Ruff edit](https://github.com/astral-sh/ruff/commit/c0824de94a1c9bf7c0042625c8a46ed5eafe9794) · [Registered inputs and reproduction](https://github.com/astral-sh/ohm-cargo/tree/d4c6a2c698432668c65acf6c725a6dd3d25af037/benchmarks/ruff-dev-loop-20261027/macro-entrypoint-h2-sdk-mount)

| Change and reversal | `cargo build -p ruff_index --lib` | `cargo test --no-run -p ruff_index --lib` | Test executable |
| --- | --- | --- | --- |
| Historical formatting of `RuleNamespace` | 2 full compiles, 1 link | 2 full compiles, 2 links | Identical |
| Change an invalid `RuleNamespace` input’s diagnostic | 2 full compiles, 1 link | 2 full compiles, 2 links | Identical |
| Change the bound produced by the invoked `newtype_index` macro | 2 full compiles, 1 link | 2 full compiles, 2 links | Changed, then restored exactly |

Each arm started empty on Linux x86-64 with four Cargo jobs. Each edit left 50 of 52 units fresh, and each unchanged command left all 52 fresh. All three edits changed the procedural-macro shared object and both `ruff_index` library artifacts in the `build` arm. In the test arm only the shared object changed in the first two cases. The `ruff_index` test executable remained `8dee3e5bfc6d4fc6f77f72444187431b9e79ffa40221284130f229bb3a5d7cfb`.

Independent compiler consumers observed `non-empty` versus `non-blank` for the deliberately invalid derive and `4294967294` versus `4294967293` for the changed generated bound. Building through `ruff_index`’s public re-export produced the same bound as calling the macro directly. All twelve test-build commands listed the same five tests without running any test body. These observations identify an unchanged product after a real macro edit. They do not establish that Cargo can safely skip the work or how much time it would save.

Run `python3 -B verify.py` to recompute the rosters, native process counts, output digests and external checks across all 24 Cargo commands. `observations.tar.gz` includes the original setup stop and the process traces for each compiler and linker counted. `inventory.json.gz` binds the portable files to the native originals. The only substitution was the local registry cache directory name.
