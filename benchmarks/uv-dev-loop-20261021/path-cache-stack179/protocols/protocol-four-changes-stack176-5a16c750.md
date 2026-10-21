# Cumulative validation after the external PR176 stack

Frozen 2026-10-21 11:42 UTC before matched binaries or timing for this comparison exist.

Purpose: measure the four proposed changes together, without assuming that their independent effects add. This is a bounded cumulative validation, not another source PR. It is separate from the original PR175 comparison of build-output-remap plus loader-v2 and from the incremental path-cache comparison against PR179.

The baseline is PR176 commit 5a16c750eba7f6b7bcfd7a220a377685c62b3512. The candidate is PR179 snapshot 19718e6d1637244ffbb193334f50bae3ffca1be5 (tree f4ce59f92aa17461fe3c8b68923c88539136045a) plus the reviewed path-cache port. This compares the four changes—build-output remapping, loader-path handling, lazy Git initialization and unit-path string caching—against the preceding external stack. Final baseline/candidate trees, patch and binary hashes must be sealed before measurement. Subsequent upstream moves do not silently alter these snapshots.

Build this baseline as the third member of the same matched production cohort as the incremental path-cache pair. All three must use the same physical source/target paths, chosen Git HEAD and embedded Cargo identity, compiler and flags. Follow the matched build/strip/provenance requirements in protocol-path-cache-stack179-19718e6d.md (SHA256 468bc3a8e4dc93f6c5dab3b27d48ee461d43d4be6f0f957d9a3eb14e84c324b1): stock Rust 1.99.0, all-static/ohm-defaults, opt-level 3, ThinLTO, one codegen unit, debug level 1, no incremental compilation and no PGO. Preserve linker outputs, verify every allocated ELF section after debug-only stripping, and bind immutable source/build/strip/runtime records.

Run only after the current combined validation and then the complete incremental path-cache queue, with the local measurement lease held and no competing compiler/tests. The unchanged uv and workload compiler are the same pinned inputs used by those protocols. Use one regular canonical Cargo executable path and fixed source, compiler, target and shared-cache paths, eight jobs and CPUs 0-7. Workloads are full-workspace fresh cargo check and cargo test --no-run with Ohm defaults, --locked and --offline. No uv tests run.

Fixed Cargo-only instruction batches:

- Check: 12 balanced randomized AB/BA pairs, seed 2026102171, two warmup pairs; output check-four-changes-stack176-5a16c750-production-ir-confirmation.
- Test-build: 12 balanced randomized AB/BA pairs, seed 2026102172, two warmup pairs; output test-four-changes-stack176-5a16c750-production-ir-confirmation.

Use the frozen paired.py runner. Check is primary. Each claimed workflow must independently show at least 1% geometric-mean instruction reduction, a strictly positive lower endpoint of the 99% paired bootstrap interval (20,000 resamples, seed 1701), exact two-sided sign-test p <= 0.01 and positive effects in both orders. The pair is the statistical unit. Complete both fixed batches regardless of the primary effect unless integrity/correctness fails. Inspect effects only when each batch finishes. Do not pool with any other comparison, extend sample counts, discard outliers or stop based on the observed effect.

Preflight both variants for each workflow with native execve traces and successful fresh output without compiler, linker, build-script or test children. Seed invalidated state outside measurement. Preserve every preparation, warmup, measured invocation and failure; require zero exit status and freshness throughout. Verify every recorded input hash before and after. Stop and investigate any integrity or correctness failure, retaining the attempt; a source change after timing begins requires new frozen validation.

Callgrind 3.22 uses trace-children=no, the existing environment-normalization shim and normal system certificate paths. Counts include Cargo userspace work only, excluding children and kernel work. Retain allocator/brk warnings. Instrumented elapsed time is not native time. This protocol makes no native wall-time claim and does not require an additional native batch. Old wall-time results cannot establish the cumulative effect on these snapshots.
