# Preserve ordinary worktree snapshots after Clippy

## Recommendation

Ship the clone-gated policy for Ohm worktree users, with the explicit disable
available. The representative parser workflow below uses **12.75% less physical
storage** and **12.75% less elapsed time**. Donor-only total time is nearly flat,
but repeated donor Clippy has an observed **14.95 ms / 16.66%** median cost. This
is a small, explicit tradeoff; the evidence does not establish universal absence
of performance regressions or attribute that entire cost to the new policy.

The benchmark compares automatic isolation with explicit isolation-off using the
same new Cargo binary. It measures this policy's effect on fresh state, not every
change in the PR against the prior release or an in-place upgrade.

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
can coexist until normal cleanup. Fresh-workflow savings below exclude that
transition. Re-enabling isolation never clears a previous denial marker.

Local validation passes 32 worktree integration tests, 17 incremental-cleanup and
reuse tests, four targeted filesystem/driver unit tests, and all Cargo target
Clippy checks with warnings denied. New coverage includes automatic admission on
clone-capable storage, explicit disable/child overrides, global wrapper and logger
rejection, mismatched unwrapped rustc versions, and cleanup of legacy namespaces.

## Production validation

The production implementation is
`795cddae649feb6387fbf35c7a905d7b4977dba0`. The measured CI binary was built from
`496285f24f268208a93cecb45c642b8a82658650` with `--release --features ohm-defaults`.
The final PR source is `0428ec35f1c2fc6903220d1b5be7675e2ebeed72`.
Production paths (`src/cargo`, `src/bin`, `crates`, `Cargo.toml`, `Cargo.lock`,
`build.rs`) are identical across all three commits; intervening changes concern
tests, snapshots, CI, and the measurement harness. Compiler and Clippy are the
packaged Ohm 1.98.0-9. The measured Cargo SHA-256 is
`24e006f5db0835da3fcd3e0931ab5db07f49a4361b61eeb6a1b193e92d2a5b02`.
[All identities and original artifact manifest](results/shipping/production-archive.json).

The [dedicated macOS replay job](https://github.com/astral-sh/ohm-cargo/actions/runs/34032543352/job/101484660340)
passed all eight arms. Four fresh 24 GiB sparse APFS volumes per mode ran in
`off1, on1, on2, off2, on3, off3, off4, on4` order (ABBA, then BAAB).
The enabled arms used normal packaged defaults with no isolation override; off
arms set `CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION=false`.

Each arm tests `ruff_python_parser`, runs Clippy twice, repeats the tests, creates
a worktree, tests it, checks out a real parser edit, tests again, runs Clippy twice,
and repeats the tests. Ruff starts at
`1edf9fe2cab23e34c383419b8c7830324c428a58` and applies its direct child
`0ecff877901a0377ad966ffab528488ce872b50e`. Builds use four jobs, optimization
level 1, line-table debug information, and LTO off. The exact profile, commands,
environment, and outputs are retained in the receipts. Explicit macro/native-tool
trust applies only to this pinned development fixture, not the CI Cargo build.

Every enabled arm imported **851 files, including 841 reflinks**; disabled arms
imported no snapshot. Actual test logs report **812 passing tests before the edit
and 813 afterward**. Both Clippy and test no-op steps have zero `Compiling` or
`Checking` lines. An independent review reproduced every summary row, median,
and paired change from the raw receipts and checked actual test/admission logs.

### Physical storage

Values are medians of four arms per mode. Physical bytes are dedicated APFS
allocator growth (`ATTR_VOL_SPACEUSED`) from the settled post-checkout baseline,
including build/shared/incremental state and the child checkout. They exclude
toolchains and downloads outside the volume and contain no pre-upgrade caches.
Each allocator reading settled after flushes. Clone-unaware inode totals are
recorded separately and are not used as physical-storage evidence.

| Stage | Off, MiB | Automatic, MiB | Change |
| --- | ---: | ---: | ---: |
| Donor only | 540.590 | 539.924 | −0.12% |
| After fresh child tests | 882.156 | 724.727 | −17.85% |
| Final donor and edited child | 984.916 | 859.350 | **−12.75%** |
| Final child marginal allocation | 444.387 | 319.395 | **−28.13%** |

All four paired final-storage changes fall between **−12.69% and −12.76%**.
Child marginal allocation subtracts each arm's donor-only allocation before
taking the median; it is not the difference between the two displayed medians.

### Elapsed time and waited-child CPU

Times sum workload commands from the first donor test through the final child
no-op, including worktree creation and the edit checkout. They exclude source
clone/fetch, volume setup/teardown, and allocator inspection. CPU sums user and
system time for waited children. These are not retired-instruction counts.

| Phase | Off wall, s | Automatic wall, s | Wall change | Off CPU, s | Automatic CPU, s | CPU change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Whole workflow | 27.044 | 23.595 | **−12.75%** | 97.918 | 83.965 | **−14.25%** |
| Donor preparation, including both Clippy runs | 17.667 | 17.700 | +0.19% | 68.497 | 68.263 | −0.34% |
| Worktree creation and child work | 9.362 | 5.927 | −36.69% | 29.336 | 15.458 | −47.31% |
| First donor Clippy | 1.287 | 1.314 | +2.11% | 3.240 | 3.298 | +1.79% |
| First child Clippy | 1.293 | 1.300 | +0.58% | 3.276 | 3.275 | −0.02% |
| Donor test no-op | 0.659 | 0.644 | −2.27% | 2.117 | 1.924 | −9.13% |
| Child test no-op | 0.637 | 0.617 | −3.18% | 1.998 | 1.912 | −4.30% |

Whole-workflow wall-time changes are favorable in all four pairs, ranging from
−7.91% to −13.87%. The first donor Clippy median rises by 27.09 ms; its ranges
are 1.277–1.335 s off and 1.310–1.446 s automatic. Its paired changes are mixed.

Repeated Clippy is short enough to deserve separate absolute numbers:

| Repeated command | Off wall, ms | Automatic wall, ms | Wall change | Off CPU, ms | Automatic CPU, ms | CPU change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Donor Clippy | 89.753 | 104.704 | **+14.951 ms / +16.66%** | 84.402 | 97.834 | **+13.432 ms / +15.91%** |
| Child Clippy | 83.538 | 84.402 | +0.863 ms / +1.03% | 79.922 | 80.593 | +0.672 ms / +0.84% |

Donor warm wall-time ranges are **82.930–109.019 ms off** and
**92.247–105.113 ms automatic**; CPU ranges are **79.078–102.492 ms off** and
**87.980–99.647 ms automatic**. In actual execution order:

| Arm | Repeated donor Clippy wall, ms | Waited-child CPU, ms |
| --- | ---: | ---: |
| off1 | 82.930 | 79.078 |
| on1 | 104.970 | 98.303 |
| on2 | 92.247 | 87.980 |
| off2 | 109.019 | 102.492 |
| on3 | 104.438 | 99.647 |
| off3 | 95.214 | 88.467 |
| off4 | 84.292 | 80.337 |
| on4 | 105.113 | 97.365 |

Three of four paired donor warm commands are slower. A separate
[untimed local attribution trace](results/shipping/warm-trace/receipt.json) shows
both driver-version probes hitting Cargo's persistent cache on repeated Clippy,
with no version-query subprocess launched. This tiny fixture is mechanism
evidence only. Filesystem capability probing remains per invocation; the trace
does not establish how much of the representative 15 ms increase it causes.

The dedicated runner had no other Rust processes at the before/after guards,
but those checks are not continuous and do not establish an idle machine.
Recorded macOS background work includes Spotlight activity, particularly in
`on1`. This can affect short timings. Four arms per mode on one parser workflow
support this scoped result; they do not establish platform-wide or workload-wide
performance equivalence. The macOS `time -l` instruction counter failed a
waited-child sanity check, so no whole-workflow instruction-count claim is made.

### Correctness and CI

A dedicated **HFS+** smoke test exercised the automatic fallback on storage without
file cloning. An ordinary fork copied 18 files with zero reflinks. A subsequent
Clippy run created no isolated namespace, marked the ordinary donor ineligible,
and prevented another snapshot import. Explicit `true` created the isolated
namespace while retaining the earlier denial marker. No probe files remained;
the volume detached normally. This is a policy/correctness check, not a performance
result. [Procedure and receipt](results/shipping/fallback/receipt.json).

The ordinary stable-toolchain CI suite excludes bundled-Clippy tests marked
nightly. A separate CI step installs pinned Ohm 1.98.0-9 on macOS and Linux and
runs five exact admission, lint-state, override, and trust tests with
`--include-ignored`. The test helper enables Ohm defaults explicitly for a
standard Cargo build; the optimized APFS measurements use packaged defaults
with no activation override in enabled arms.

All **eight standard CI checks** passed at final PR head
`0428ec35f1c2fc6903220d1b5be7675e2ebeed72` in
[run 34032859038](https://github.com/astral-sh/ohm-cargo/actions/runs/34032859038).
The full macOS suite passed 4,211 tests; all five focused bundled-Clippy tests
ran with one pass and zero ignored on **both macOS and Linux**.
[Exact job and step receipts](results/shipping/current-ci-jobs.json).

The optional `clippy_apfs_replay` workflow-dispatch input runs the eight-arm
production replay on a dedicated macOS runner. It records the source commit and
tree, builds optimized Cargo with Ohm defaults, fetches the exact Ruff revisions,
and uploads receipts and logs separately from
the private disk images. The runner accepts `--toolchain` to pin the compiler.

[Local validation and excluded-trial provenance](results/shipping/validation.json)
records the focused test counts, the help-snapshot correction, and the partial
APFS attempts rejected when unrelated Cargo processes started, and the early
workflow/fixture repairs. None of those incomplete attempts enters the summary.

### Durable data and reproduction

[The full original CI artifact](results/shipping/production-raw.zip) contains
125 files and is 372,882 bytes, SHA-256
`69908990d257aab57057a31a29fa5a20aa7406e69d777fc04f1ca776d4b8d046`.
The archive preserves all eight receipts and command logs. Its per-file hashes
are in [the archive receipt](results/shipping/production-archive.json); receipts
and root identity files are also [available without extraction](results/shipping/production-raw).

[The derived summary](results/shipping/production-summary.json) preserves every
per-arm value, median, range, and paired change.
[The independent validator](results/shipping/summarize_production.py) checks
identities, activation, test counts, no-op behavior, admission, process guards,
and settled allocation before computing those values. Extract the original
artifact into a fresh directory and pass its `apfs` directory to that script.
The measured driver is
[run_apfs.py at 496285f](https://github.com/astral-sh/ohm-cargo/blob/496285f24f268208a93cecb45c642b8a82658650/benches/clippy-seeding/run_apfs.py);
its SHA-256 is
`34832be58e65cc3799e33f424fdc6ebae45e75cadc6ad368621b82b4232b1289`.

The evidence branch also contains a stricter optional replay mode. It disables
indexing with `mdutil` only on each newly attached task-owned volume and requires
an explicit disabled status. Before measured commands, it waits at most 60 s
for three consecutive snapshots spaced 1 s apart with no external process at
20% CPU or above and a sum below 50% among recorded processes at 1% CPU or above.
The same limits apply at the post-command snapshot. Every wait and snapshot is
recorded; settling time is excluded from workload timing. This creates a brief
pause even between first and repeated Clippy. It strengthens endpoint control
but is still not continuous monitoring. Results above are from the original
run and are retained separately from any replay using these stricter controls.

## Historical evidence

The original opt-in APFS and ext4 results remain in [README.md](README.md).
They are not current production timing measurements. Historical ext4 copying
grew physical allocation by 6.64%, motivating the clone gate; the HFS+ smoke above
checks the production fallback directly. Explicit enable can still select that
tradeoff on non-cloning storage.
