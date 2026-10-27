# Ruff mutable standard-library defaults

Reversing the historical Ruff change switched two diagnosed default arguments from B006 to B008, one using `collections.ChainMap()` and the other `weakref.WeakSet()`. Restoring the code switched both back. Each compiler saw both edit directions twice on a separate warmed workspace. [Ruff edit](https://github.com/astral-sh/ruff/commit/523d83c941cbae9b7c8a10739c839a8eeda3245d) · [Registered experiment](https://github.com/astral-sh/ohm-cargo/tree/84fb230860eb83e7335b25a2d5d6ade11a70569a/benchmarks/ruff-dev-loop-20261027/stdlib-mutable-holdout)

Each row lists actual successful process launches, in the order full rustc / link-only rustc / native Wild. Each cell gives the two repetitions in order.

| Command | Direction | #232 full / link-only / Wild | #233 full / link-only / Wild |
| --- | --- | ---: | ---: |
| `cargo build` | edit | 25 / 0 / 7, 25 / 0 / 7 | 25 / 0 / 7, 25 / 0 / 7 |
| `cargo build` | restore | 25 / 0 / 7, 25 / 0 / 7 | 25 / 0 / 7, 25 / 0 / 7 |
| `cargo test --no-run` | edit | 58 / 0 / 41, 58 / 0 / 41 | 58 / 0 / 41, 58 / 0 / 41 |
| `cargo test --no-run` | restore | 58 / 0 / 41, 58 / 0 / 41 | 58 / 0 / 41, 58 / 0 / 41 |

All 501 build units and 619 test-build units were fresh on the subsequent command after every edit and restoration. The Ruff checkout and Git index were restored. Each trace includes the native product roster, all output file SHA-256s, the physical compiler or linker process digests, and the diagnostic locations. These are process counts from traced commands. No wall-time effect was estimated. Run `python3 -B verify.py` to verify each recorded phase and repetition.

As a separate investigation, reading the 25 physical build commands showed that six downstream crates directly received the producer with rustc’s `--extern` flag. The producer itself compiled once. The remaining 18 invocations were transitive consumers. The direct six were `ruff_linter`, `ruff_python_semantic`, `ruff_workspace`, `ty_ide`, `ty_module_resolver` and `ty_python_semantic`. The compiler arguments for each process are bound by its recorded SHA-256 in `stdlib-extern-relations.json`.
