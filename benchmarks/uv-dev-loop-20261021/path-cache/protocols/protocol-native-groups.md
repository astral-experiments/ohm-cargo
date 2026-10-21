# Native grouped timing revision, frozen before grouped measurements

The first 30-pair single-invocation path-cache exploration estimated a 9.93%
wall-time reduction, but its 99% interval was -0.68% to 18.65% and its exact
two-sided sign-test p was 0.0161. It did not pass the original acceptance gate.
All samples remain in `results/check-path-cache-exploratory`; none are excluded.

Hardware counters are unavailable under both inspected hosts' current
permissions. Callgrind executes a host-inserted INT3 in libc setenv and traps;
the same native program succeeds. No host monitoring or security setting was
modified. Consequently, subsequent claims use uninstrumented wall time.

For fresh/no-op workloads, use 30 balanced, randomized pairs, two recorded
warmup pairs, and eight invocations per variant group. Install the canonical
binary once and prepare/warm once before a group. Time each invocation
separately and preserve its output and resource counters. Sum the eight times
for the group's one observation. Bootstrap, sign tests, order comparisons and
the minimum sample count operate on the 30 paired groups, not the 240 subruns.
Any failed invocation or unexpected compilation invalidates the complete batch.

Exploration selects candidates. An independently randomized confirmation batch
uses the frozen patch, binaries, configs and harness. The original wall-time
gate remains: at least 1% point improvement, 99% paired-bootstrap interval
excluding zero, exact two-sided sign p <= 0.01, and both execution-order groups
positive. Report CPU time as supporting evidence. Test the other requested
workflow for regressions. No compiler builds or benchmark jobs run concurrently.

Debug sections are stripped from all variants identically to reduce executable
copy size between groups. The preparation helper verifies every allocated ELF
section's flags, virtual address, size, alignment and bytes, and checks that its
input file is unchanged. Per-binary manifests and their hashes are frozen with
each batch. An earlier `objcopy --dump-section` inspection inadvertently
normalized source ELF metadata after the first exploratory batch; both the
original linker-output hashes and normalized hashes are retained. No accepted
claim uses the changed setup without an independent batch.

Dirty or build-to-check transitions are not repeatable no-op workloads. They
retain one timed transition per variant per pair, with the documented fixture
restored before every sample. Their state must be validated before inference.
