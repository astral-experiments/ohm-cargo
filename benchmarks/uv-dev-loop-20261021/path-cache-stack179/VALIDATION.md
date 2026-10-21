# Validation and retained limitations

The exact candidate source commit
`c40676e264501bc8a93095d3a273a1c300b80875`, with measured tree
`0a392258c801cff734d223a3f9af73d5b5a4e3c0`, passed
[GitHub Actions run 39594716160](https://github.com/astral-sh/ohm-cargo/actions/runs/39594716160)
on its first attempt. `validation/code-publication.json` binds that commit,
parent and tree; `validation/ci/restacked-pass-snapshot.json` records the
successful run at 2026-10-21 11:53:38 UTC. This is source CI under the workflow's
settings, not an integration-suite run against the frozen production CLI.

The baseline source CI passed after an unchanged retry. Its first attempt
failed the existing terminal-cancellation case; the failure excerpt and the
similar PR177 failure are retained in
`validation/ci/restacked-177-179-original-failures.json`. A later successful
retry does not erase the earlier failure or establish its cause.

The matched production cohort compiled all three frozen source variants with
identical actual rustc flags/features, compiler and common-input digest.
`build/results/audit-cohort.json` independently verifies the trees, source
patches, original and stripped ELF hashes, logs and all 31 allocated sections
for each binary. The binaries use stock Rust 1.99.0, opt-level 3, ThinLTO, one
codegen unit, debug level 1, no incremental compilation, and
`all-static,ohm-defaults`. These are production-profile builds without PGO;
they are not the published PGO Cargo binary.

The exact baseline/candidate production binaries successfully seeded and ran
unchanged uv using the published Ohm compiler. Initial untimed seeding rebuilt
workspace artifacts after the source-stack change. The subsequent native
execve traces were fresh and had no compiler, linker, build-script or test
children. Every timed invocation, warmup and preparation succeeded and was
fresh. Each workflow's integrity report verifies 28 invocations, 28 profile
hashes, 76 immutable inputs, and the unchanged pinned uv checkout. All preflight
seed logs, traces and later per-invocation logs are retained in the archive.

The earlier 93-pass/4-ignored build-dir suite used the historical original-PR175
path-cache production binary `c060facd…`, not this current-stack binary. Its
supported classic-default compatibility wrapper, explicit compiler-library
path, raw logs and per-attempt hashes remain in the immutable historical
package linked from README.md. Earlier normal-build failures and their
baseline diagnosis are also retained there. They are not relabeled as
current-stack exact-binary integration coverage.

The profiler uses Callgrind 3.22 with child tracing disabled. Its normal system
certificate paths remain explicit; certificate verification is not disabled.
The included shim removes profiler-injected loader environment variables
before Cargo/children. Both variants report Valgrind's brk limit and allocator
fallback. This limits native allocator attribution and prevents treating the
instrumented wall-time values as native performance evidence.
