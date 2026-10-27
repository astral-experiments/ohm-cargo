# Rerunning the native compiler edits with the corrected Cargo

The four primary compiler measurements used one identical Cargo on every arm. This additional unscored run exercises the published historical-edit helper with the same final #233 Rust compiler and the FIFO-safe companion Cargo. It checks that the change in Cargo preserves the observed full-compiler and native link counts.

The runner uses the pinned clean Ruff worktree on H2 and the separately trained, restored candidate stores for build and test-build. It holds the native measurement lock and starts after the preceding Cargo comparisons finish. Each edit runs through `rerun-native-edit.py` with the exact binary hashes and `--trace-edit`. It checks the Ruff executable's diagnostics, zero dirty units in the immediate JSON repeat, source bytes and Git index on restoration. The changed command is traced, so it has no reported wall time.

| Edit | Mode | Expected full rustcs | Expected link-only rustcs | Expected Wild calls |
| --- | --- | ---: | ---: | ---: |
| Private linter doc correction | build | 2 | 2 | 3 |
| Private linter doc correction | test --no-run | 4 | 16 | 19 |
| Parser diagnostic | build | 3 | 6 | 8 |
| Parser diagnostic | test --no-run | 6 | 62 | 67 |

Full source and toolchain commands are available in the paired results. The separate Cargo comparison identifies the exact release-built Cargo and the writerless FIFO, regular symlink and downgrade controls. [Compiler data and reproducer](https://github.com/astral-sh/ohm-cargo/tree/2f07518331735487c84aaeadab58ce98d7c5a71b/benchmarks/ruff-dev-loop-20261027/native-qualified-results) · [Cargo subjects](https://github.com/astral-sh/ohm-cargo/tree/0b8c518679748e0e7d199bc4c6ed783326849396/benchmarks/ruff-dev-loop-20261027/observed-span-fifo-qualification)

The first prefetch comparison found two complete registry reader records in separate compiler namespaces and stopped before its first sample. This replacement waits for the independently registered second comparison. The original failure and queue remain available. The pinned Ruff patch, commands, expected full/link-only/linker counts, sources, output checks and release binaries are identical.
