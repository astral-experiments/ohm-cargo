# Retained attempts and changes of baseline

All entries below are separate from the accepted production confirmations.
The archive contains their complete run directories, with profile extracts
and hashes replacing only the large attribution profiles. Earlier metadata
remains unchanged; later source/build records do not retroactively strengthen
what those runs recorded.

| Earlier attempt | Observed reduction | 99% interval | Sign p | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Original normal build, 30 single native check pairs | 9.9316% | -0.6826% to 18.6518% | 0.016124802 | Inconclusive; brief harness-unit-test overlap and substantial jitter retained |
| Stripped normal build, 30 native check groups of eight calls | 0.5583% | 0.0429% to 1.0581% | 0.042773945 | Gate fails the 1% threshold and sign-test rule |
| Initial Callgrind smoke, one failed candidate invocation | No comparison | Not applicable | Not applicable | Host setenv uprobe caused SIGTRAP; retained exit -5 and partial profile |
| Normal system SSL paths, one successful check instruction pair | 1.0925% | Single-pair interval is not confirmation | 1 | Diagnostic only |
| Stripped normal build, eight exploratory check instruction pairs | 1.1225% | 1.0804% to 1.2163% | 0.0078125 | Exploratory screen, not independent confirmation |
| Original PR175 normal build, two check instruction pairs | 1.2151% | 1.1984% to 1.2319% | 0.5 | Diagnostic only |

The first native exploratory batch did not record a runner-source hash. Its
raw configuration, compiler/lockfile/binary hashes and sample tables remain
available, but it does not have the later confirmations' complete frozen
runner provenance. The brief overlapping unit tests were recorded as
exploratory-only noise; no samples were removed.

The original full baseline and path binaries were later passed through an
objcopy section-dump operation that unexpectedly normalized ELF metadata.
historical/normal-binary-manifest.json records both original linker hashes and
the changed file hashes, noting unchanged runtime .text bytes. The first
exploratory batch used the original linker outputs. Later normal-build runs
used separately hashed stripped binaries. The historical correctness logs do
not bind an exact binary hash per attempt, so they must not be described as
byte-identical executable tests. Production builds independently preserved
their linker outputs and verified all allocated sections after stripping.

The failed profiler setup is an environment failure, not a performance result.
Setting SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt and
SSL_CERT_DIR=/usr/lib/ssl/certs avoids the instrumented setenv path while using
the same normal trust store. Certificate verification and host security were
not disabled. Both variants use the same settings in later counter runs.

External PR175 removed unused dep-info work after the earlier baseline was
selected. The already running old native check batch completed unchanged;
the unstarted old test-build batch was held. That decision and the absence of
interim effect inspection are retained in
historical/external-pr175-priority-change.json. The production confirmations
then used the explicitly frozen original PR175 baseline and fresh fixed
check/test batches. Normal and production builds, hosts and baselines are not
pooled.

At 2026-10-21 11:34 UTC, an external restack changed the PR base chain and moved
the shared-cache trust transition. The original production evidence remains
bound to original PR175 and candidate tree b0dfb3fe2cfd8d310efa04a345f58886296f712a.
The ported path-cache patch requires a separate current-stack validation. No
claim about its incremental or cumulative effect follows from these old data.
