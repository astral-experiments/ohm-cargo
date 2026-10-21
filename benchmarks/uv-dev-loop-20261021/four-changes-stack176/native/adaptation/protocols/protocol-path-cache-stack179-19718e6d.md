# Path-cache validation on the restacked PR179 snapshot

Frozen 2026-10-21 11:41 UTC before matched binaries or any timing for this comparison exist.

Purpose: measure the incremental effect of the derived unit-path string cache after the externally restacked changes. The older path-cache results against original PR175 are retained separately and do not establish the effect on this stack.

The baseline is PR179 commit 19718e6d1637244ffbb193334f50bae3ffca1be5, tree f4ce59f92aa17461fe3c8b68923c88539136045a. The candidate is that exact tree plus the reviewed path-cache port. The candidate must clear cached directories at the new prepare_shared_context trust-fallback transition. Its final patch, source tree and binary hashes are pending and must be sealed before any measured invocation. Later upstream changes do not silently change this baseline snapshot.

Build both variants at the same physical source and target paths, with the same recorded Git HEAD and only working-tree patch differences, preserving the embedded Cargo identity. Use the matched production flags and stock Rust 1.99.0 compiler from the prior production validations: opt-level 3, ThinLTO, one codegen unit, debug level 1, all-static and ohm-defaults, no incremental compilation and no PGO. Preserve each original linker output and verify that debug-only stripping preserves every allocated ELF section's address, size, alignment and bytes. Record final build, strip, source and runtime provenance in an immutable input seal. Do not refer to mutable aggregate provenance files.

The unchanged uv commit remains 3d82a6ad5a7eab8c68236553b7846517767c4b61, with published Ohm 1.99.0-6 as workload compiler. Run full-workspace warm check and test --no-run, with Ohm defaults explicitly enabled, --locked --offline, eight jobs and CPUs 0-7. No uv tests execute. Preserve one regular canonical Cargo executable path, one source path and fixed target/shared-cache paths for both variants. Freshly seed or refresh any state invalidated by the new source configuration outside measurement.

Fixed instruction batches, run serially after the existing combined validation and only when the local measurement lease is available:

- Check: 12 balanced randomized AB/BA pairs, seed 2026102161, two warmup pairs; output directory check-path-cache-stack179-19718e6d-production-ir-confirmation.
- Test-build: 12 balanced randomized AB/BA pairs, seed 2026102162, two warmup pairs; output directory test-path-cache-stack179-19718e6d-production-ir-confirmation.

Use the frozen paired.py runner and its already validated analyzer. The statistical unit is one pair. Check is primary, and a separate test-build claim must independently pass the same gate: at least 1% geometric-mean count reduction, a strictly positive lower endpoint of the 99% paired bootstrap interval (20,000 resamples, seed 1701), exact two-sided sign-test p <= 0.01 and positive effects in both AB and BA orders. Run both fixed batches regardless of the primary effect unless integrity or correctness fails. Inspect effects only after each complete batch. No extension, outlier removal, pooling, optional stopping or reuse of old observations.

Before each workflow, warm both binaries through the canonical path and capture native execve traces confirming fresh outputs with no compiler, linker, build-script or test child. Require every untimed preparation, warmup and measured command to finish successfully and remain fresh. Verify all recorded input and binary hashes before and after. Stop and investigate an integrity or correctness failure; retain all raw attempts. A changed source after timing begins requires a separately frozen fresh validation.

Callgrind 3.22 uses trace-children=no, the existing loader-environment normalization shim, and the normal system SSL_CERT_FILE and SSL_CERT_DIR. Do not alter certificate verification or host security. Counts cover Cargo userspace work only, excluding child and kernel work. Retain both variants' allocator/brk warnings. Instrumented elapsed time is not native timing. This protocol makes no native wall-time claim, and the older native confirmations are not current-stack validation; any new native batch must be declared separately before it starts.
