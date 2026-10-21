# Correctness and workload integrity

The exact measured production binary c060facdbaae756453968d6eaef1c5ab71c127d15c329a8453e260ef3064c583
passed 93 preexisting build_dir tests, with four ignored and no failures, on
host4 at 2026-10-21 11:43:07–11:44:49 UTC. This is original-PR175 correctness,
not a performance comparison or validation of the later restack. The
unchanged prebuilt integration runner has SHA256
6415ee68be80518f701a6e4d0b45c1ef76bab599af203625f06b7fa4ac696182 and was compiled
from source tree c692e3c07d295e596b9f10eb4b1c89bb498caf68. The fixed case list
matches the historical 93-pass/four-ignored run exactly; the three later
loader-only additions are absent from this runner.

The isolated ordinary-user workspace recreates the runner's otherwise absent
baked paths. Its launcher preserves each test's explicit Ohm yes/no setting
and nightly channel, defaults an unset Ohm setting to no for classic-layout
snapshots, and restores dev only for inherited stable/beta/unset channels so
the supported override is honored. PATH selects published Ohm, and its lib
directory is explicitly in LD_LIBRARY_PATH. The report binds actual binary,
runner, launcher, compiler and runtime hashes before and after; execve evidence
shows the launcher invoking the frozen candidate. No source or test snapshots
were edited or rebuilt. The test attempt passed once without a rerun.

The source archive's 3,096 tracked entries were checked after the run. All
regular bytes and executable bits match. Safe tar extraction normalized
trailing slashes in 23 unrelated cargo_add/cargo_remove fixture symlink strings
without changing their destinations. The initial collection-only check
rejected those textual differences; that attempt and the explicit final
normalization report are retained. It was not a test failure or test rerun.
See [production/README.md](validation/production/README.md), the readable
[report](validation/production/report.json), and the complete logs/records in the archive.

The path cache stores deterministic strings within one CompilationFiles
instance. A metadata hash remains stable for the corresponding Unit. Directory
strings additionally depend on the shared/private namespace and trust state.
The initial shared-cache validation can populate these directory cells before
rejecting a proposed shared context. On fallback, the patch clears immutable
units, updates the trust/isolation flags and workspace namespace, and clears
every cached directory. It retains the metadata hashes because their inputs
did not change. This prevents cached paths from outliving a rejected namespace
without caching filesystem validation results.

The later external restack moves that transition into prepare_shared_context.
The original patch and correctness evidence here apply to the original source
tree; the separately reviewed port must clear directories at the new transition.

Historical normal-build correctness ran the same 97 named build_dir cases in
both retained attempts: 93 active and four ignored. The first attempt passed
91 and failed two build-to-check reuse cases. The same failures were reproduced
with baseline when the injected loader path was empty. The supported rerun
selected cargo-path-cache and explicitly set LD_LIBRARY_PATH to the published
Ohm compiler's lib directory; all 93 active cases passed. The logs and
validation/historical-correctness.json preserve those facts.

The later test harness contains three additional loader-only cases, which
were intentionally excluded from this original-case-set run:

- shared_registry_cache_preserves_explicit_empty_loader_paths
- shared_registry_cache_reuses_built_dependencies_with_an_unset_loader_path
- unset_loader_path_adds_procedural_macro_library_directories

The tested cases include canonicalized symlinked target directories, untrusted
procedural-macro closures, configured build-script overrides, ambient native
compiler/linker/host-runner wrappers, compiler search-path/version overrides,
and the normal build-directory path/layout scenarios. No expected snapshots
were changed. The first failures and both baseline reproductions remain in
historical/logs.

Those historical tests used the original normal-build implementation, not the
measured production c060facd binary. Their logs omit per-attempt executable
hashes, and the documented older ELF metadata normalization prevents a claim
that those attempts used byte-identical files. The independently built normal
PR175 diagnostic and production candidate have the same source tree, but this
does not turn earlier tests into exact-production-binary coverage.

Production instruction validation checks both variants at one canonical Cargo
path. Native execve preflights confirm no compiler, linker, build-script or test
children on the fresh check and test --no-run workloads. Every preparation,
warmup and measured invocation is retained and checked for freshness, success,
unchanged executable and unchanged recorded inputs. Each instruction workflow
contains 28 successful invocations, including four warmup invocations, with
matching raw profile hashes and counters. Independent native runs retain every
group and subrun and their own preflight traces. These workload checks exercise
Ohm defaults explicitly enabled and do not execute uv tests.

For reproducing the existing suite, select the actual intended compiler through
PATH and unset RUSTUP_TOOLCHAIN; the test support clears RUSTC and can otherwise
prepend rustup's compiler. Preserve an explicit compiler-library loader path
when using the older harness. Freeze normal binaries before building tests.
Record the test harness source/hash, actual production CLI hash and its baked
entry path before and after any replacement; restore the original entry
atomically. Do not assume that a prebuilt harness or its fixture paths relocate.

Production enables ohm-defaults. Existing classic-layout snapshots may require
the repository-supported __CARGO_OHM_DEFAULTS=no override; because the harness
normally forces a stable channel, the established launcher also restores the
binary's dev channel before selecting that override. Such a run must be labeled
with its effective flags and must not replace Ohm-enabled workload validation.
Retain any failed default-mode attempts instead of changing snapshots.

The exact-production report above closes the earlier binary-identity gap for
the original PR175 candidate. It does not strengthen or rewrite the older
attempts, and it does not cover the subsequently ported current-stack source.
