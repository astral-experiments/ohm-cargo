# Clippy worktree snapshot benchmark

Ohm isolates the bundled Clippy driver when copy-on-write cloning works in the
shared snapshot directory. This preserves ordinary build snapshots without
importing Clippy artifacts or diagnostics. Compiler and wrapper checks still
apply, and trusting local procedural macros requires an explicit opt-in.

Set `CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION=false` to disable isolation.
Forcing it to `true` bypasses the clone probe and can increase storage usage.
External Cargo subcommands inherit explicit overrides.

## Run the APFS comparison

The runner compares automatic isolation with isolation disabled. Each arm uses
a fresh APFS volume and the same pinned Ruff parser edit, then runs tests,
Clippy, a worktree fork, and repeated commands. It checks test results, clone
imports, and freshness while recording physical allocation and command timings.

```sh
python3 benches/clippy-seeding/run_apfs.py \
  --cargo /path/to/optimized/cargo --ruff /path/to/ruff \
  --root /private/tmp/codex-cargo-targets/ruff/isolated/clippy-seeding \
  --evidence /path/to/results --toolchain ohm --jobs 4 --require-quiet
python3 benches/clippy-seeding/summarize.py /path/to/results
```

The runner requires macOS, refuses to replace existing arms, and preserves each
sparse image. It fetches dependencies before timing and builds offline. The
`clippy_apfs_replay` workflow input runs four paired comparisons on a dedicated
macOS runner. Physical allocation and command timings are separate measurements;
ordinary host activity can affect timings even with `--require-quiet`.

[Historical results and their original runner](https://github.com/astral-sh/ohm-cargo/tree/benchmark-evidence-2026-10-07-cleanup/benches/clippy-seeding)
remain available in the evidence tag.
