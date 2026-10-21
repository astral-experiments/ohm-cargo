# Instruction-count-only draft publication amendment

Decision announced at 2026-10-21 23:19:26 UTC, after the instruction-count results were known and before any paired native timing effects were inspected for the three candidates below.

The user's request explicitly permits instruction counts or reliable wall time. Repeated host activity has interrupted the planned native regression checks. This amendment changes the publication criterion: these three candidates may be published as drafts after their original instruction-count gates, correctness checks, and exact-source CI pass. Completing a native regression screen is no longer a prerequisite for these drafts.

This is a post-IR change to the publication plan. It does not mean the original full protocols completed. Native speedups, native equivalence, and absence of native regression remain unverified. An interrupted experiment is not a statistically inconclusive completed experiment.

## Scope and unchanged evidence

The amendment applies uniformly to the three active candidates, all measured independently against PR181's exact source revision:

- Parser allocations: both check and test-build instruction gates passed.
- Scheduler bitsets: the primary test-build gate and separate check instruction gate passed.
- PackageId identity comparison: the primary check instruction gate passed. Test-build instructions remained below the original 1% claim threshold, so no test-build improvement claim is permitted.

The original instruction-count configurations, source and binary identities, randomized orders, two warmup pairs, twelve measured pairs per workflow, seeds, observations, raw audits, and analysis remain unchanged. The original gates remain: at least 1% point reduction, positive 99% paired bootstrap interval, exact two-sided sign-test p <= 0.01, and positive effects in both orders. Both workflow raw audits preceded effect analysis. Compiler-child instructions and uv test execution are excluded as originally specified.

No instruction sample is added, replaced, omitted, pooled, or reclassified. The previously rejected allocator and macro candidates remain rejected; this amendment does not revive failed primary screens. Individual effects are not summed into a combined claim. The measured Cargo builds use matched all-static/Ohm-defaults settings, ThinLTO and one codegen unit, without PGO; they are not the published PGO binaries.

## Native attempts

The decision rests on operational failures, not native effect estimates. Scheduler preflight was interrupted by maintenance before any timed sample. PackageId stopped before its first preflight because maintenance was active. Parser's latest attempt stopped at a workflow boundary because a host service was active; any partial native observations remain unanalysed. Earlier transport, guard, and preservation failures remain failures.

No native effect or regression estimate is used for publication. All existing attempts and preservation records remain retained. Existing fixtures are left in place; the scheduler's five completed preservation moves are not reported as a completed six-move operation. Further relocation and native replay preparation stop. No services, security controls, occupancy guards, measurement code, or source changes are made to obtain a passing run.

Private operational logs can contain unrelated process arguments. Publication must use a sanitized operational summary and opaque original-file hashes, and must not upload those unredacted logs or an archive containing them. Raw instruction evidence and complete profiles supporting the claims remain publishable after the normal artifact review. Partial native tables may be retained as opaque private evidence but must not be presented as a completed confirmation.

## Required draft disclosure

Every affected PR and evidence README must say that the claim concerns Cargo-process instruction counts, explain the fixed paired confirmation, and identify exact source revisions and reproduction inputs. They must explicitly state that the original plan included native runtime regression checks, that host activity interrupted them, that publication criteria changed after IR results were known and before native effects were analyzed, and that wall-time effects and regressions remain unverified.

Exact-source correctness and CI remain required before creating each draft. A separate final decision must bind the accepted IR evidence, this amendment and its independent review, measured source tree, source commit, and successful CI. No PR may claim that every original preregistered gate passed.
