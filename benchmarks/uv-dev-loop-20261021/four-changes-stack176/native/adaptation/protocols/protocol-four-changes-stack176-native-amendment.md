# Prospective native amendment: current176 versus all four changes

Declared on 2026-10-21 while the matched current-stack production cohort is
still building and before any workload measurement of that cohort. This adds
an independent native confirmation; it does not change either frozen
instruction protocol or reuse any earlier native samples.

The instruction protocols remain:

- protocol-path-cache-stack179-19718e6d.md, SHA256
  468bc3a8e4dc93f6c5dab3b27d48ee461d43d4be6f0f957d9a3eb14e84c324b1.
- protocol-four-changes-stack176-5a16c750.md, SHA256
  7e89b6ae08712cb5ec6ad36c1caf05bb1cff3ba6b7737bb6f917195dd3513f03.

Run this native comparison only if all four completed fixed instruction
batches pass their respective predeclared gates and integrity checks:
incremental path check/test and cumulative four-change check/test. A failure
does not authorize extending samples, changing the candidate, or substituting
another native baseline under this amendment. Report the unmet prerequisite.

The native control is current176 commit
5a16c750eba7f6b7bcfd7a220a377685c62b3512, tree
06123b7a4dfa10de0abf3b5ccd520e34172bc208. The candidate is the same current179
plus ported path cache used in both instruction comparisons, tree
0a392258c801cff734d223a3f9af73d5b5a4e3c0. Its incremental path patch SHA256 is
0706ae28f7cfb62774755aec611689eda86c5080846e1e37b33e5bfc60163aa9. The exact
matched host2 cohort binaries, full source/build/strip records, protocols,
runner and configurations must be sealed before native preflight execution.
Later upstream changes do not silently change these identities.

Use quiet host8 with unchanged uv, the same published Ohm compiler, the
existing fresh check and test --no-run workloads, and the established native
environment. Keep both variants at one canonical Cargo path and the exact
same source, target, Cargo home and shared-cache paths within each pair. Seed
outside timing. Verify ordinary host ownership, no competing build processes,
fresh commands, unchanged source, and execve evidence before timing. Compiler
and test processes must not execute in the traced fresh workload.

Each workflow gets 30 randomized balanced AB/BA group pairs, two warmup group
pairs, and eight sequential timed native calls per variant group. The prepare
command runs once per variant group outside timing. Use the frozen repeated
runner and retain all 512 calls per workflow, including 32 warmup calls. There
are 30 independent measured group pairs, not 480 independent observations.

Fixed seeds and result directories:

- Check: 2026102173,
  check-four-changes-stack176-5a16c750-native-confirmation.
- Test build: 2026102174,
  test-four-changes-stack176-5a16c750-native-confirmation.

Do not inspect interim effects. Analyze each workflow only when its complete
fixed batch has finished. Aggregate wall time by summing the eight executions
inside each variant group, then analyze paired log ratios. Use a 99% paired
bootstrap interval with 20,000 resamples and analysis seed 1701, an exact
two-sided paired sign test, and separate AB/BA summaries. All four native gate
conditions must hold: at least 1% point-estimate reduction, a strictly positive
99% lower bound, sign p <= .01, and positive reduction in both order groups.

Preserve every sample and failure. No outlier removal, optional stopping,
sample extension, pooling with the original PR175 composition or other
candidates, or source changes after sealing. If a run fails, preserve it and
report the failure before any separately declared recovery attempt. Do not
infer additivity or a dirty/cold-build result from this fresh-loop comparison.
Report check and test separately, including negative or below-threshold
results. A positive interval below the 1% practical threshold is a failed
full gate, not an accepted native speedup.
