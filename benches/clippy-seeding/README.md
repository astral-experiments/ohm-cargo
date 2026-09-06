# Preserve ordinary worktree snapshots after Clippy

## Assessment

Worth pursuing for worktree-heavy development on filesystems with copy-on-write
cloning. Keep the prototype opt-in: the Linux replay saved time but consumed
more disk, and existing tainted donors cannot be adopted automatically.

The APFS parser workflow reduced final physical allocation by **12.63–12.67%**
and the additional allocation for the child by **27.88–27.94%**. The experiment
retains ordinary incremental state and does not discard Clippy caches.

## Implementation

Set `CARGO_EXPERIMENTAL_CLIPPY_SEED_ISOLATION=1` to put a verified bundled
Clippy invocation's private outputs and incremental state in an excluded child
namespace. Ordinary build/test/check artifacts remain eligible for worktree
seeding. Clippy artifacts and diagnostics are never imported.

Recognition requires the canonical `sysroot/bin/clippy-driver`, a matching
compiler version, no global wrapper, and the existing compiler/loader checks.
Combined Clippy/codegen and opaque wrappers retain their existing admission
rules. Local procedural-macro trust remains explicit.

The workspace namespace advances to v3 and snapshot/remapped-path protocol to
v7 so old importers cannot accidentally copy the new Clippy subdirectory. This
requires fresh donor state; the experiment does not clear old denial markers
or reclaim older namespaces. Package and incremental cleanup include the
isolated directory.

## Local correctness

Against packaged Ohm 1.98.0-9, all **29 worktree tests** and **16 incremental-GC
and reuse tests** pass. They cover genuine Clippy recognition, rejection of a
wrapper around Clippy, fresh ordinary builds after import, exclusion of lint
state, changed lint configuration, backdated source edits, donor independence,
and cleanup. See [validation provenance](results/validation.json) and the
compressed test logs in `results/`.

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

The second pair has the same source tree as this implementation. The first
predates a cleanup-only amendment that its workload does not exercise. An
unpaired packaged-revision-9 reference fell inside the feature-off timing
range; that observation does not prove zero disabled-mode overhead. The
original receipts and source provenance are retained in
[results/linux](results/linux).
