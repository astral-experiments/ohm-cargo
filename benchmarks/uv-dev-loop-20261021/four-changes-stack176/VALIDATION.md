# Validation and retained limitations

The measured candidate source commit
`c40676e264501bc8a93095d3a273a1c300b80875`, tree
`0a392258c801cff734d223a3f9af73d5b5a4e3c0`, passed
[GitHub Actions run 39594716160](https://github.com/astral-sh/ohm-cargo/actions/runs/39594716160)
on its first attempt. The retained publication record binds commit, parent and
tree; the CI snapshot records the successful run at 11:53:38 UTC. This is source
CI under that workflow's settings. It is not an integration-suite execution
against the frozen production CLI.

The retained CI context also includes the intermediate PR179 and PR177 initial
terminal-cancellation failures and their successful unchanged retries. Those
failures are preserved without asserting a cause. PR179 is the incremental
path control; the cumulative control here is the earlier frozen PR176 tree.

The matched cohort compiled all three exact source variants with identical
actual rustc flags/features, compiler and common-input digest. The independent
cohort audit verifies their source trees and patches, linker/stripped hashes,
logs and all 31 allocated ELF sections. Builds use stock Rust 1.99.0, opt-level
3, ThinLTO, one codegen unit, debug level 1, no incremental compilation, and
`all-static,ohm-defaults`. There is no PGO; these binaries are distinct from the
published PGO Cargo artifact.

The exact control and candidate successfully seed and run unchanged uv with
the published Ohm workload compiler. Initial untimed seeding may rebuild
artifacts; all subsequent traced calls, cross-switch calls, warmups, preparation
and measured calls must be fresh. The trace checks permit only taskset and the
canonical Cargo executable, with no compiler, linker, build-script or test
child. The test command retains `--no-run`.

Each instruction integrity report verifies 28 invocations, 28 full profile
hashes, 76 immutable inputs and a clean pinned uv checkout. Each native report
verifies 64 groups and 512 calls, including warmups, the exact balanced plans,
all raw JSON/JSONL/CSV/nested repetitions, unchanged binaries/inputs and fresh
logs. The native package audit checks the final status rows against the exact
workflow order and each saved gate. Raw observations are retained even when a
gate does not pass.

The original native host8 staging failed before transfer or Cargo execution
because an unrelated PR165/Ruff benchmark was active. Its stderr and occupancy
snapshots are retained. The local host amendment was declared and both configs
sealed before any native Cargo call. An obsolete task-owned Python analysis
was stopped by its owner before local preflight; the termination receipt and
unchanged completed-report hash are retained. The local adapter's independent
review confirms that measurement, grouping, raw audit and statistical functions
are unchanged from the reviewed host8 driver.
Other task compiler/benchmark work was excluded during the local slot; normal
host services were left unchanged. Occupancy and load snapshots are retained.

Earlier component correctness runs and supported classic-default wrappers
remain in the linked historical packages. They are not relabeled as an exact
current-cohort integration-suite run. The exact production binaries here have
compilation/source/ELF verification and the unchanged-uv fresh-loop checks;
the candidate's broader tests are represented by its separate source CI.

Callgrind 3.22 traces Cargo only. Standard SSL certificate paths remain
explicit, with certificate verification enabled. The included shim removes
profiler-injected loader variables. Both variants retain Valgrind's brk-limit
and allocator-fallback warnings. These constrain native allocator attribution,
and profiler wall times are not native wall-time evidence. Fresh-loop results
do not establish cold builds, dirty builds or cross-machine generality.
