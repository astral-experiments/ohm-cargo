# Preserve ordinary worktree snapshots after Clippy

## Production policy

Normal Ohm worktree preparation now isolates the verified bundled Clippy driver
when a small clone-only probe succeeds in the actual shared snapshot storage.
The probe checks source and destination locations, removes its temporary files,
and retains no capability marker between Cargo invocations. A different final
`CARGO_TARGET_DIR` does not change the shared directory where snapshots are cloned.

`-Zohm-clippy-seed-isolation=no` or
`CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION=false` disables the policy and skips the
probe. Explicit `yes`/`true` forces isolation even without cloning and can increase
storage, as the historical ext4 measurements below demonstrate. External Cargo
subcommands inherit explicit overrides. Arbitrary wrappers, unmatched compilers,
loader injection, and combined Clippy codegen retain conservative admission.
The old `CARGO_EXPERIMENTAL_CLIPPY_SEED_ISOLATION` variable is no longer used.

Clippy artifacts and diagnostics are never imported. Recognition checks the
canonical bundled driver and compares its compiler version with the unwrapped
selected rustc, in addition to the existing compiler/loader trust checks. Local
procedural-macro trust remains explicit.

The workspace namespace advances to v3 and snapshot/remapped-path protocol to
v7 so old importers cannot accidentally copy the Clippy subdirectory. Fresh donor
state is required. Full, package, and incremental cleanup handle both the current
namespace and the same workspace/target's legacy v2 namespace; other targets remain
untouched. An upgrade does not purge old caches automatically: v2 and v3 storage
can coexist until normal cleanup. Fresh-workflow savings exclude that transition.
Re-enabling isolation never clears a previous denial marker.

Local validation passes 32 worktree integration tests, 17 incremental-cleanup and
reuse tests, four targeted filesystem/driver unit tests, and all Cargo target
Clippy checks with warnings denied. New coverage includes automatic admission on
clone-capable storage, explicit disable/child overrides, global wrapper and logger
rejection, mismatched unwrapped rustc versions, and cleanup of legacy namespaces.

## Replaying the production policy

The optional `clippy_apfs_replay` workflow-dispatch input runs the production
comparison on a dedicated macOS runner with pinned Ohm 1.98.0-9. It builds Cargo
with `ohm-defaults`, records source and binary identities, and runs eight fresh
APFS arms in off/on/on/off/on/off/off/on order. Enabled arms use automatic
admission; disabled arms set the explicit override to false.

The replay includes the first and immediate repeated Clippy commands in both
worktrees, test-command no-ops, and donor-only allocation. It requires actual
reflink imports in enabled arms, rejected imports in disabled arms, fresh no-op
commands, and matching 812/813 Ruff test totals. Macro/native-tool trust applies
only to the pinned development fixture; the CI build itself uses private storage.

Current production results and limitations are linked from
[PR #108](https://github.com/astral-sh/ohm-cargo/pull/108). The historical results
below remain tied to their original implementation.

## Original opt-in prototype measurements

The retained results below belong to the original opt-in implementation at
`fcb7f19dc2f3bda0fdaa1c7659159a5bcf5f3037`, before the production activation and
legacy-cleanup changes. They remain historical evidence, not current-head timing
measurements. Its 29 worktree and 16 incremental-cleanup/reuse tests are recorded
in [validation provenance](results/validation.json) and the original compressed
logs. No original raw receipt or result has been replaced.

The APFS parser workflow reduced final physical allocation by **12.63–12.67%**
and the additional allocation for the child by **27.88–27.94%**. It retains ordinary
incremental state and does not discard Clippy caches. The larger ext4 replay grew
allocation, motivating the production clone gate.

## Physical APFS experiment

The same optimized candidate Cargo executable ran off/on/on/off on four fresh,
dedicated APFS sparse volumes. The compiler and Clippy were the packaged
1.98.0-9 toolchain; each arm used four jobs and explicit registry/local macro
and native-tool trust. Ruff used its opt-level 1, line-table debug profile.

The workflow starts at Ruff `1edf9fe2cab23e34c383419b8c7830324c428a58`, runs
parser tests and Clippy in the donor, forks a worktree, runs the child tests,
applies the real parser fix `0ecff877901a0377ad966ffab528488ce872b50e`, and
repeats tests, Clippy, and a no-op test command. Baseline invocations run 812
passing tests; the fix adds one fixture, producing 813. Both arms agree.

| Pair | Feature off | Feature on | Physical reduction |
| --- | ---: | ---: | ---: |
| Off then on | 983.74 MiB | 859.50 MiB | 12.63% |
| On then off | 984.84 MiB | 860.04 MiB | 12.67% |

These are allocator measurements after subtracting the donor-source checkout,
including shared dependencies, both worktrees' build/incremental state, and
the child's checkout. Each enabled fork imported 851 files, with 841 reflinks.
Measurements use `ATTR_VOL_SPACEUSED` after filesystem flush and stabilization;
inode totals in the receipts are separately labeled and never substituted for
physical allocation. Toolchains and the download cache are outside the volume.

The complete build/test/Clippy/fork/edit workflow took 48.32 versus 39.77 seconds
in the first pair and 45.92 versus 45.63 seconds in the reverse pair. Unrelated
development workloads were active, so these timings do not establish a precise
speedup or a universal no-regression result. Whole-command child CPU usage fell
16.11% and 12.74%, respectively. Allocator measurements were isolated on the
dedicated volumes. One final detach returned a transient busy error after all
measurements completed; a normal retry succeeded without forcing detachment.

Raw receipts, compressed command logs, and the derived table are in
[results/apfs](results/apfs). Reproduce on macOS with:

```sh
python3 benches/clippy-seeding/run_apfs.py \
  --cargo /path/to/optimized/cargo --ruff /path/to/ruff \
  --root /private/tmp/codex-cargo-targets/ruff/isolated/clippy-seeding \
  --evidence /path/to/results --jobs 4
python3 benches/clippy-seeding/summarize.py /path/to/results
```

The runner defaults to the historical prototype activation, for use with that
older binary. Add `--production` when testing the current automatic policy.
The runner refuses to replace existing arms and preserves each sparse image.
It prefetches dependencies before timing and builds offline. The final runner
adds retries for transient detach failures; this changes only teardown.

## Earlier native Linux replay

Two earlier Ruff/ty replay pairs use the same compiler release, 16 jobs, ext4,
and a larger edit/test/Clippy/fork continuation. Both run 868 passing tests
with 34 skipped. Their warmed replay was 2.38–4.30% faster, including donor
Clippy and the fork; fork plus child continuation was 8.09–8.90% faster.
However, final unique-inode allocation increased **6.64%**, from approximately
7.417 GB to 7.910 GB. Ext4 used ordinary copies rather than reflinks, and
additional query-cache storage accounts for most of the increase.

The second pair has the same source tree as the original opt-in prototype. The first
predates a cleanup-only amendment that its workload does not exercise. An
unpaired packaged-revision-9 reference fell inside the feature-off timing
range; that observation does not prove zero disabled-mode overhead. The
original receipts and source provenance are retained in
[results/linux](results/linux).
