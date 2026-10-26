# Ruff workspace CLI edit under six Cargo changes and two compiler changes

Both arms ran `cargo +ohm check --locked --offline --message-format=json` at the root of the same Ruff workspace. The fixture reinstates the seven lines removed by Ruff commit `da8ee78491` and then replays the deletion in `crates/ruff/src/main.rs`. The worktree is pinned to `93526150df`. An initial source-archive preflight had no `.git`, so Ruff’s build script watched the whole package and rebuilt extra units. Its measurements are excluded.

| Counted processes | Control median Ir | Treatment median Ir | Median paired reduction | Geometric mean reduction, 95% block-bootstrap interval | Pairs improved | Exact two-sided p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cargo and rustc | 1,214,501,654.0 | 1,181,092,968.5 | 2.756% | 2.757% [2.720%, 2.797%] | 16/16 | 0.0078125 |
| Cargo | 1,049,055,089.5 | 1,015,380,149.5 | 3.207% | 3.210% [3.180%, 3.242%] | 16/16 | 0.0078125 |
| rustc | 165,394,092.0 | 165,703,417.0 | -0.059% | -0.111% [-0.266%, 0.048%] | 7/16 | 0.24219 |

The control compiler is built from Ohm Rust `f1a7cf9d2`. The treatment adds [the empty lint scope change](https://github.com/astral-sh/ohm-rust/pull/230) followed by [the packed edge reader](https://github.com/astral-sh/ohm-rust/pull/231). Both use the same stage-2 PGO and BOLT recipe, profile files, frontend, standard library and LLVM. Rebuilding first the control, then the treatment, then the control again on one overlay reproduced both post-BOLT driver hashes. `subjects.json` records the source, byte and recipe input hashes for both arms. [The six-change Cargo patch](https://github.com/astral-sh/ohm-cargo/blob/5b76ff636a6c9c229a4629c43c88beb4cc6f50cc/benchmarks/ruff-dev-loop-20261026/cargo-stack/six.patch) supplies the parent-to-treatment Cargo changes.

Four cross-arm freshness checks verified 520 identical units and zero dirty targets before the edit. Every scored invocation restored a physical copy of both the target and shared build directory, applied the same edit with a fixed timestamp, and executed under child-tracing Callgrind. All emitted 520 units, rebuilt only the `ruff` binary, and recorded exactly one completed Cargo and one completed rustc count. The runtime maps in the rustc profile selected the physical driver for its assigned arm. All 442 unique emitted Rust metadata files and 435 public API hashes were byte-identical across all 32 invocations. `roster.json` records the digests.

Each of eight four-invocation blocks was randomly assigned ABBA or BAAB. `pairs.csv` preserves the order and raw per-process instruction counts. `summary.json` includes the exact two-sided block sign-flip test on log ratios and 30,000 fixed-seed block-bootstrap resamples. These are instruction counts. The check runs in a warm local workspace using six Cargo jobs and the Ohm defaults.

`replay.py --help` lists the inputs for replaying the cohort. Supply an empty output and scratch directory, a clean dedicated linked worktree at the pinned Ruff commit, an offline registry, the common release sysroot, and the two Cargo and compiler driver pairs. The script temporarily changes the single CLI source file and restores its contents and timestamps in `finally`. Pin the Python process with `taskset -c` to use the same affinity for all child processes.
