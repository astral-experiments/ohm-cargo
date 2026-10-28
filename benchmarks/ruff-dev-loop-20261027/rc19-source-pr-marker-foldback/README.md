# Fold the generated-marker fixes into Cargo #101 and #103

Both source PRs were fast-forwarded together. GitHub confirmed the exact two commit IDs and confirmed that #103 now targets the updated #101 head. Their original changes had already shipped when we reproduced Cargo overwriting a user file through a symlink placed at a generated worktree marker. The release repair stays on the release pin. [Cargo #274](https://github.com/astral-sh/ohm-cargo/pull/274) · [Rust #249](https://github.com/astral-sh/ohm-rust/pull/249) · [Ohm #201](https://github.com/astral-sh/ohm/pull/201)

| Source PR | Previous hosted head | Current verified hosted head | Scope |
| --- | --- | --- | --- |
| [Cargo #101](https://github.com/astral-sh/ohm-cargo/pull/101) | `9866420326` | `62afc4ab5a` | Protect the seed, policy-deny, compiler dep-info-deny, and saved build-script-result writes. Add the marker-specific helper and test while preserving symlinked manifest edits. |
| [Cargo #103](https://github.com/astral-sh/ohm-cargo/pull/103) | `1269b29fe7` | `1a84f8f36f` | Merge the protected #101 commit, preserve the v6 marker introduced here, and protect the local procedural-macro marker. Add a test on an unchanged build. |

Both current heads are descendants of their previous hosted heads. #103 still targets #101. The only merge conflict was the seed marker version, for which the resolved line writes the original v6 bytes using the protected writer. The fifth write and its dedicated test account for the only product and test changes made above the parent integration.

## Native regression checks

The test host built each original and fixed Cargo from its verified source. The check verified all 3,075 Git file and symlink objects, including executable modes, in each historical checkout. Both arms used the same new test source for each PR. The compiler and Cargo build driver were the same Ohm 1.99.0-17 dev toolchain. The runtime subject was each historical Cargo binary just built with its production Ohm-defaults feature. A process trace proved the test executed that binary twice for each case.

| Historical Cargo | Symlinked seed and script-result markers | Symlinked local proc-macro marker | cargo-util atomic write tests |
| --- | --- | --- | --- |
| #101 hosted head | User sentinel overwritten, test failed | Introduced later | — |
| #101 fixed head | Passed | Introduced later | 3 passed |
| #103 hosted head | User sentinel overwritten, test failed | User sentinel overwritten, test failed | — |
| #103 fixed head | Passed | Passed | 3 passed |

The tests ran unignored on Linux. The utility cases cover ordinary writes, permission preservation, and user-facing symlink handling. Both updated trees also passed `cargo +ohm fmt --all -- --check` and `git diff --check`. The external release-line matrix separately exercises all five writer paths using real builds. [Independent release candidate qualification](https://github.com/astral-sh/ohm-cargo/tree/61923deedae198a997d1797a2583a2d84558055b/benchmarks/ruff-dev-loop-20261027/rc18-marker-symlink-fixed-acceptance)

Read [the four-write patch](pr101-four-writes.patch), [the fifth-write patch](pr103-fifth-write.patch), [the full #103 update](pr103-complete.patch), and [the native command receipts](native-results.json). The release line continues to pin the already-qualified #274 revision independently.

## Five-writer release regression on each historical branch

An independent fixture exercised each writer individually. It used the same physical four Cargo executables as the integration tests, and the historical marker versions v5 and v6. An explicit pass-through workspace compiler wrapper selects the untrusted-input policy branch. A real build script installs the dep-info case during execution. Each old writer replaced its external victim. Each fixed writer preserved the victim contents, inode and mode and replaced the marker itself. The four cases on #101 and five on #103 all passed this paired comparison. Rebuilding the original and fixed images reproduced both original test-binary digests on both branches. [Per-case data](all-writers.json)

Both exact hosted heads passed all eight jobs, covering the Cargo suite and Clippy on Linux and macOS, formatting, and the workspace, resolver and schema suites. GitHub superseded the first #103 run as its base branch moved and passed all eight jobs in the replacement. [#101 CI](https://github.com/astral-sh/ohm-cargo/actions/runs/40783164617) · [#103 CI](https://github.com/astral-sh/ohm-cargo/actions/runs/40783204870) · [Per-job records](hosted-checks.json)
