# Four generated Cargo cache files followed their final symlink

The four writers entered the active Ohm Cargo stack in separate PRs. Each introducing commit is the PR's exact head and an ancestor of the tested parent `5394ce8817`. We compared each direct parent's complete Git blob with the introducing blob, authenticating both against their commit trees. The resolve cache file first appears in #66. The four PRs were open and non-draft on October 29, 2026.

| Generated file | Introducing PR | Original source |
| --- | --- | --- |
| Public-API fingerprint sidecar | [#53](https://github.com/astral-sh/ohm-cargo/pull/53) | [Serialize the public-API hash](https://github.com/astral-sh/ohm-cargo/blob/1aa523118aad2b32eb365589956a96587e527f92/src/compiler/fingerprint/mod.rs#L2399) |
| Workspace resolution fingerprint | [#66](https://github.com/astral-sh/ohm-cargo/pull/66) | [Write the resolution fingerprint](https://github.com/astral-sh/ohm-cargo/blob/c512a35365c5de427107d7886056516b4948d46e/src/ops/resolve_cache.rs#L48) |
| Compiler message provenance | [#75](https://github.com/astral-sh/ohm-cargo/pull/75) | [Record the compiler's cached messages](https://github.com/astral-sh/ohm-cargo/blob/e42a45efcab3cf44489a071493f6d2aeafb826d2/src/compiler/mod.rs#L1415) |
| Early integration-test check hint | [#147](https://github.com/astral-sh/ohm-cargo/pull/147) | [Write the uses-library hint](https://github.com/astral-sh/ohm-cargo/blob/8b17025201e2e8b29b199a0dc5748dae34a73dae/src/compiler/ohm_early_tests.rs#L104) |

The two regression tests added in `8dc33c9c` failed at the intended assertions on `5394ce88`. The in-process unit test wrote the public-API JSON over the unrelated file's four original bytes, `keep`. In the black-box test, the actual parent Cargo successfully checked both packages and wrote the 16-byte workspace resolution fingerprint over the sentinel. The generated cache entry remained a symlink. The other two sites were attributed from the original and parent source here.

The existing `workspace_resolve_cache_ignores_execution_only_environment` test also failed on this parent. All three Cargo commands succeeded. The final command changed `RUSTFLAGS`, reused the workspace resolution, and rechecked both crates. Its assertion expected the resolution-cache message to be absent.

The unit used a detached parent worktree with the two exact new test definitions. The integration harness was compiled from `8dc33c9c`. Its embedded Cargo path was bound read-only to the parent CLI, and the embedded test root was separately bound to a fresh directory for each case. Native process traces confirmed all four successful Cargo commands. The retained raw logs are committed by SHA-256 in `evidence.json`. Portable harness diagnostics replace the absolute target directory with `<TEST_TARGET>`.

To verify the packet offline, run `sha256sum -c SHA256SUMS` and `python3 -IB verify.py`. To repeat the immutable blob comparisons and recheck the live PR heads from an authenticated checkout, run `python3 -IB audit-origins.py CHECKOUT EMPTY_OUTPUT_DIR`. Changes to any of those PR heads will fail that live head check. To rerun the test definitions, create a private worktree at `5394ce88`, apply `test-only.patch`, then use `cargo +ohm test --locked --offline -p cargo --lib --features ohm-defaults compiler::fingerprint::early_cutoff_tests::public_api_hash_replaces_a_symlink -- --exact` and `cargo +ohm test --locked --offline -p cargo --test testsuite --features ohm-defaults workspaces::workspace_resolve_cache_replaces_a_symlink -- --exact`.
