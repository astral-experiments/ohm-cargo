# Follow-on fixed validation protocol

Recorded 2026-10-21 03:39 UTC before executing the lazy-Git candidate in any timed comparison. This supplements, without modifying, protocol-upstream-175.md and protocol-native-host8.md.

Lazy Git initialization was selected from the original baseline profile and a completed correctness review. Its frozen patch is 3707975b6b134ecce3c811963ffe65a96c1c564e9000ae4255d1bdd56cb76deb, and its combined PR175 source tree is c692e3c07d295e596b9f10eb4b1c89bb498caf68. The optional exploratory screen is omitted. The first timed validation will use the frozen matched all-static/ThinLTO production-settings binaries directly, with no candidate edits or sample-count changes based on interim effects.

- Git Cargo instructions: 12 check pairs, seed 2026102121; 12 test --no-run pairs, seed 2026102122. Two untimed warmup pairs per workload.
- Git native wall/CPU time: 30 check groups, seed 2026102124; 30 test --no-run groups, seed 2026102125. Eight invocations per group and two warmup pairs.
- Path-cache Cargo instructions: 12 check pairs, seed 2026102128; 12 test --no-run pairs, seed 2026102129. Two warmup pairs. The completed normal-build two-pair PR175 diagnostic is exploratory only and is not pooled.
- Path-cache native wall/CPU time: 30 check groups, seed 2026102126; 30 test --no-run groups, seed 2026102127. Eight invocations per group and two warmup pairs.

For every candidate, cargo check is the primary workflow. The test --no-run workload is a predeclared secondary validation and regression check; a separate test-build speedup claim requires its own full acceptance gate. A joint check-and-test claim requires both workflows to pass. A failed check primary cannot be rescued by choosing a passing test result afterward.

For every candidate, baseline is PR175 alone, not another candidate. Binaries must be built at the same absolute source/target paths with identical flags and embedded Cargo commit identity, then atomically installed at one shared executable path. Workload sources, compiler, cache roots, environment, and CPU affinity remain fixed within a pair.

The acceptance rule remains at least 1% lower Cargo instructions, a positive 99% paired bootstrap lower bound, exact two-sided sign-test p <= 0.01, and positive effects in both execution orders. Native claims require their own corresponding gate; instruction-only claims must explicitly say native timing is inconclusive if it does not qualify. There must be no established native regression. Do not pool instrumentation wall time with native wall time, different build modes, different baseline revisions, different hosts, or exploratory and fixed validation batches.

All fixed batches run to their declared length. Only operational failures, input mutation, unintended compiler/test execution in a purported fresh workload, or correctness failure may invalidate a batch; retain the failed attempt and record the reason.
