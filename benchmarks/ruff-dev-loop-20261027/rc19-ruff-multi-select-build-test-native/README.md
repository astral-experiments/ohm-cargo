# Ruff build and test-build work after changing library test selection

Ruff commit `2d6ce561250a464e1fa231ef30e54d0f029f76a4` changes the library test or doctest settings for 27 crates. It changes 30 files without changing Rust source or the lockfile. The complete historical revisions, the 47 selected workspace members and the source inventory are available alongside the matching check experiment. [Ruff change](https://github.com/astral-sh/ruff/commit/2d6ce561250a464e1fa231ef30e54d0f029f76a4) · [Source inventory](https://github.com/astral-sh/ohm-cargo/tree/d0325acfadb4c8e38ee5a669f665d58c20f13c88/benchmarks/ruff-dev-loop-20261027/rc19-ruff-multi-select-subject) · [Check observations](https://github.com/astral-sh/ohm-cargo/tree/44070d6988b93518a7196e555dc65f3078993456/benchmarks/ruff-dev-loop-20261027/rc19-ruff-multi-select-check-native)

A private Cargo-created worktree started on the committed revision. We restored all 30 parent files and then reapplied all 30 committed files, each time using their exact Git bytes. Each command checked every changed input before and after execution, with no changes to the Git administrative directory. The qualified release-PGO Cargo at `235f9228651b74c591e6f62cae4c9b761448dd2d` used the published Ohm 1.99.0-18 compiler and stock Wild. The proposed -19 Rust source differs from -18 only in the Cargo submodule. These work counts come from one Linux host. There is no candidate comparison or wall-time estimate. [Cargo source](https://github.com/astral-sh/ohm-cargo/commit/235f9228651b74c591e6f62cae4c9b761448dd2d)

| Command and input | Full rustc | Relink-only rustc | Wild |
| --- | ---: | ---: | ---: |
| Build, parent or committed edit | 47 | 4 | 9 |
| Build, unchanged | 2 | 4 | 5 |
| Test build, enable 13 parent harnesses | 132 | 8 | 98 |
| Test build, unchanged parent | 4 | 16 | 19 |
| Test build, disable the 13 harnesses again | 119 | 8 | 85 |
| Test build, unchanged committed revision | 4 | 15 | 18 |

We ran `cargo +ohm build --workspace --locked --offline -j8 --message-format=json` and then `cargo +ohm test --no-run --workspace --locked --offline -j8 --message-format=json`. Each series includes a settled pre-edit command and two unchanged commands after each edit. The test-build preparation started from the completed build state. Linux exec observation identifies the actual rustc, GCC, collect2 and Wild executables by verified file identity. Each observation includes the original argument-vector hash and output name where available. Cargo's own typed artifact records independently establish which test targets it selected.

The built Ruff CLI had the same complete executable SHA-256 in all seven measured build commands. Its off-clock probe reported F821 at line 1, column 7 for an undefined name and accepted the valid input. Every historical `ty_server` e2e executable listed the same 103 tests. The executable's own digest changed on the committed edit and returned to its previous digest on the first unchanged command. Only the inventory was exercised in the test-build study.

Run `sha256sum -c SHA256SUMS && python3 -IB verify.py --mutations` in this directory. The verifier recounts every compiler and linker execution, reconciles the native harness reader with Cargo's selected artifacts, and prints the 13 library harnesses added by the parent manifests. The packet includes the complete test-name list and SHA-256 digests of the underlying private command logs.
