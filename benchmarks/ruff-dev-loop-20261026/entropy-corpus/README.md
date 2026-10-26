# Held-out historical Ruff edits

The workload selection was frozen before measuring any of the listed patches. `select-corpus.py` hashes the full commit ID with the fixed seed `ohm-ruff-entropy-20261026-stage2` and takes the first two qualifying commits in hash order for each stratum. The earlier single-edit experiments and the active perflint discovery commit are excluded. The first match is for discovery and the second is held back for independent confirmation.

The search used the most recent 1,600 first-parent non-merge commits through Ruff `93526150df078af7dd8fc4226cdcc469539d2001`. A retained commit changes between 2 and 170 Rust lines in one Ruff crate, touches at most 18 files, has no lockfile or TOML changes, and has a binary patch of at most 140,000 bytes. The complete patch must apply in reverse to the pinned checkout. Fixtures, snapshots, and documentation in the original commit accompany its Rust changes. Standalone integration-test edits were rare under those criteria. Extending that stratum to the last 8,500 first-parent non-merge commits yielded one applicable patch, which is used for discovery. The other five strata each have a held-out patch.

| Stratum | Discovery | Holdout | Command in initial discovery pass |
| --- | --- | --- | --- |
| Lint rule | `c2b2eda972` | `88b8c7a504` | `cargo check` |
| Parser or AST | `0ecff87790` | `6e29838d4b` | `cargo check` |
| Formatter | `1fcdb82be0` | `b3fb43af25` | `cargo build` |
| Shared library | `103168bd42` | `83a3afc315` | `cargo test --no-run` |
| CLI, server or workspace | `f304bc0cac` | `fca5c7cf2c` | `cargo build` |
| Integration test | `2fb7c8ddd8` | | `cargo test --no-run` |

`manifest.json` identifies each full patch, its paths, its hash rank, and the SHA-256 of `git diff --no-ext-diff --no-renames --binary COMMIT^ COMMIT`. Generate the patches locally with `python3 select-corpus.py "$RUFF_CHECKOUT" "$CORPUS"`. `corpus-survey.py` applies and reverses each discovery patch in a disposable linked worktree. It records Cargo’s exit status, artifact records, dirty targets and compiler diagnostics. Set `CARGO_TARGET_DIR` to that worktree’s private target, `CARGO_BUILD_BUILD_DIR` to a separate shared build directory, and use `python3 corpus-survey.py --corpus "$CORPUS" --ruff "$DISPOSABLE_RUFF" --output "$OUTPUT"`. Both Ruff worktrees must be at the pinned revision. Each command uses Ohm with `--locked --offline`. Timings from this one-pass survey describe the workloads and do not qualify performance changes.
