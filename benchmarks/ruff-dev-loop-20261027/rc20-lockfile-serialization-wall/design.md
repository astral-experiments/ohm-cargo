# Ruff lockfile serialization A/B

Frozen before examining results from the candidate.

The control is release-profile Cargo 2fe90823d. The treatment uses source 24c98100d0, whose base differs from the control only in tests. Both binaries must use the same compile-time version stamp, PGO profile, nonproduct Rust and native dependencies, and the same local runtime.

On Ruff 93526150df078af7dd8fc4226cdcc469539d2001, reverse and restore only the Cargo.toml hunk from 6dc1031889aa24a0461457409d39861e279242a9. Measure ordinary default builds of ruff_text_size, with --locked and --offline and the already qualified 553-package lockfile. Also measure its checked-in serde integration target with test --no-run if the validated offline 19-unit graph can be hydrated with the existing soft disk floors. Charge initial hydration separately. The one-unit selection is the primary workload. The integration target is a prespecified second workload.

Use two isolated writable copies of the same physical warm source and target, mounted at identical paths. Preserve the input seed. Run ordinary native commands pinned to CPUs 0–3 with the same environment. Each of 32 chronological pairs runs both arms through a real profile change and its first unchanged build. The four-pair order AB, BA, BA, AB has both edit directions in both orders. Cache warming, oracle execution and tracing are outside wall time. Retain each raw elapsed time, result, stdout and stderr. Reject a traced qualification that compiles or links a fresh artifact, a changed lockfile, an unexpected Cargo verdict, or a product/oracle disagreement.

Report median paired wall-time reduction, a 95% stratified paired-bootstrap interval, and the two-sided exact sign-test probability. Report edited, first unchanged and combined separately. Qualify a native instruction claim only from terminal, calibrated hardware or PID-bound software counts. Wall time alone requires an interval excluding zero. Report any repeatable settled regression or direction dependence before opening a draft. The maximum measured reduction for this change is in command overhead; the workload already has zero compiles and links.
