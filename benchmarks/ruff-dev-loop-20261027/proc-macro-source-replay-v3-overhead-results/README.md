# Ruff parser startup and replay overhead

The correction met the 3% overhead bound on the historical parser edit with a retained incremental session. The comparison with an empty parser incremental session did not establish the required margin. Both were required for the registered family. [Prospective schedule and unscored qualification](https://github.com/astral-sh/ohm-cargo/tree/a996fef67164d0df852e90ddd8fa1e149e9acb52/benchmarks/ruff-dev-loop-20261027/proc-macro-source-replay-v3-overhead-plan)

| Native parser command | Pairs | Median paired overhead | One-sided upper bound | Pairs below +3% |
| --- | ---: | ---: | ---: | ---: |
| Retained parser incremental state | 16 | −2.88% | +1.31% | 13 |
| Empty parser incremental state | 16 | +0.25% | +17.67% | 10 |

All 64 native compiler commands produced the matching separately emitted and archived Rust metadata, public and private identities, and count of archive members for their independently qualified arm and history. The first and final blocks’ eight additional process audits verified the real rustc image, mapped driver and the actual derive plugin. Both compilers used the same frontend, native compiler arguments, three-file historical edit, 16 direct dependency artifacts and plugin on a read-only donor. Each invocation had a separate writable compiler output and incremental state. The measured command includes Rustup dispatch, compile and archive code generation. Other workspace units and Cargo scheduling were outside the measurement.

The measured position effect was larger for an empty session. The first compiler took longer in 12 of 16 pairs, with a +10.18% paired median relative to the second. Candidate versus parent had a paired median of +12.76% in its eight candidate-first pairs and −9.24% in its eight parent-first pairs. First/second median kernel CPU time was 0.963/0.740 seconds. Across all 32 empty-session observations elapsed time and kernel CPU had a Pearson correlation of 0.874. These descriptive splits retain every pair and do not change the two registered outcomes. H3 exposed neither per-core frequency readings nor an unprivileged instructions counter. Post-run cgroup CPU counters showed zero accumulated throttling periods.

Run `python3 -B verify.py` to validate the preregistration, every observation, the separate trace receipts and the two statistical outputs. The physical timings and balanced orders are available in `heldout/observations.json`. The production compiler’s independent native correctness gates and remaining cross-history raw metadata difference are described separately. [Whole-workspace correctness](https://github.com/astral-sh/ohm-cargo/tree/ec690fbef62d4e2d5cb4e85013b65b91161e8cbd/benchmarks/ruff-dev-loop-20261027/proc-macro-source-replay-v3-h3)
