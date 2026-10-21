# Cumulative four-change uv confirmation

This package compares the frozen PR176 control with all four changes together:
build-output remapping, loader-path handling, lazy Git initialization, and
per-unit path caching. It measures full-workspace fresh `cargo check` and
`cargo test --no-run` on unchanged uv. Tests are never executed.

| Input | Commit | Source tree | Stripped Cargo SHA256 |
| --- | --- | --- | --- |
| Control | `5a16c750eba7f6b7bcfd7a220a377685c62b3512` | `06123b7a4dfa10de0abf3b5ccd520e34172bc208` | `59dc8bcef32b84a7ee2e84e02fbedfbcaa526783683af8cf19166723486ac27f` |
| All four changes | `c40676e264501bc8a93095d3a273a1c300b80875` | `0a392258c801cff734d223a3f9af73d5b5a4e3c0` | `179f17531a2e9a3475c58965ad4a82248d8eb4af5ce8f1bbfe3d6be5632de86d` |

Both production binaries come from one matched host2 build cohort, with the
same compiler, settings, physical source/target paths and embedded Cargo HEAD.
The complete patches and source/build/strip audits are included. These pins
identify the measured snapshot; later PR heads are different inputs.

| Workflow | Cargo instruction reduction | 99% paired interval | Wins | Exact sign p |
| --- | ---: | ---: | ---: | ---: |
| Check | 9.356120% | 9.293975–9.508431% | 12/12 | 0.00048828125 |
| Test build | 8.207830% | 8.041995–8.345730% | 12/12 | 0.00048828125 |

Both instruction workflows pass the fixed gate: at least 1% point reduction,
strictly positive 99% lower bound, sign p <= .01 and positive effects in both
orders. The counter scope is Cargo userspace only, with child tracing disabled.
This establishes the joint effect directly; it does not assume component gains
add together.

Both native wall-time results are inconclusive and fail the fixed gate. This
package makes no wall-time claim. Their full precision and individual checks
are retained in `results/summary.json` and each `native-gate.json`.

| Workflow | Time reduction estimate | 99% paired interval | Exact sign p |
| --- | ---: | ---: | ---: |
| Check | 3.076534% | −2.445300–8.323601% | 0.85553555 |
| Test build | 1.029482% | −3.918566–5.324714% | 0.20048842 |

Both fail the interval and sign requirements. The test-build result also has
a negative point effect in one order group.

Native analyses use independent 30-pair groups of eight calls,
not 480 independent observations. Their fixed counts, seeds and gates were
declared before any native observation. The prospective host amendment moved
the run to a reserved local host after host8's occupancy guard rejected unrelated
Ruff build activity. No native observation was made on host8 for this cohort.

`RAW-MANIFEST.json` binds every raw archive member. `CONTENTS.json` records the
run inventory, and `INPUTS.json` maps measured input hashes to packaged evidence
or explicitly external runtimes. Full attribution profiles remain in the task
workspace; their exact counter lines, sample mapping, sizes and hashes are in
`callgrind-counter-extracts.jsonl`. All other run files, including warmups,
preparation logs, stdout/stderr and raw JSON/CSV, are included.

The [current incremental path evidence](https://github.com/astral-sh/ohm-cargo/tree/46e3a8185ef33ab5439c7ae5c4c01fa31d6b6f09/benchmarks/uv-dev-loop-20261021/path-cache-stack179)
uses the later PR179 control and remains a separate comparison. The
[original PR175 composition](https://github.com/astral-sh/ohm-cargo/tree/ae67763e3d0f2d881f1c40568c82278bc6ee6a89/benchmarks/uv-dev-loop-20261021/cumulative-177-178)
and [historical path evidence](https://github.com/astral-sh/ohm-cargo/tree/35a2d7792848c3c45fffdcd7d4308d8d79d98ba4/benchmarks/uv-dev-loop-20261021/path-cache)
retain their earlier native negatives, below-threshold result and correctness
attempts. None of those observations is pooled here. See `REPRODUCE.md` and
`VALIDATION.md` for reproduction and coverage limits.
