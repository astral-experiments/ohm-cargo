# Reproduce the eight-change native edited test-build comparison

Use x86-64 Linux, Python 3.11+, Git, GNU coreutils, `strace`, `flock`, and `taskset`. The original host had 32 AMD EPYC Milan vCPUs. The exact command, SHA-256 identities and both 24-pair schedules are in `plan.json`. Run the two cohorts sequentially on an otherwise idle host.

1. Follow `reproduce/first-five.md` from the combined evidence archive to prepare `$OHM_BENCH_WORK`, a private `$OHM_BENCH_ROOT`, the released `$OHM_TOOLCHAIN_BIN`, the pinned uv Git checkout, and the trusted offline registry. Write the canonical benchmark-root path followed by a newline into `$OHM_BENCH_WORK/bench-home.path` if `OHM_BENCH_ROOT` is unset. The work and benchmark roots must share a filesystem for hard links.
2. Follow `reproduce/repro-pgo.md` and the PGO holdout audit to create `pgo-confirmation-v2/bin/base`, `pgo-confirmation-v2/bin/guard-stack` and `pgo-confirmation-v2/audit.json` under the work root. Train each Cargo/standard-library arm independently. These are the executables picked by the two `arms` in `plan.json`. Both compile uv with the distributed rustc, SHA-256 `7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c`.
3. Build `bin/wild-baseline` from Wild `e856d81f6683cad80b9fe0ebf1a0c3c403c6fe11` using the Wild appendix. Build `wild-prefix-v2/v2-wild` from `a77381c04eb7ad9258cdd0475642815a2a1da711` with the frozen `candidate.patch` (SHA-256 `a75c1cf2d966ddd1217e33f8879070afe4a9e20ce94d01465a8df109ca69b65c`). The Wild prefix appendix gives the locked release build and artifact comparisons. Each timed command launches the actual `lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd` in its private released sysroot with its normal fork/jobserver behavior.
4. Copy this study's programs and plan into a fresh direct child of the work root. Preserve the evidence archive separately. The parent directory must contain `measure.py`, `edit_holdout.py` and `edit_toolchain.py`. The original results and private targets are write-once.

**Retained seeds.** The initial and repeat use separate `edit-toolchain-wall-test` and `edit-toolchain-wall-replica-test` fixture directories under the benchmark root. Each needs its `source/`, `seed-target/`, `bin/cargo`, private sysroot `sysroot-edit-<study>-test`, and private Cargo home `cargo-edit-<study>-test`. The active `target` slot must be absent. Their locally generated `edit-holdout-<study>/test/protocol.json` files belong under the work root. The complete seven-change guide builds these fixtures. On fresh targets it suffices to run only the two test warm phases:

```bash
W=$OHM_BENCH_WORK B=$OHM_BENCH_ROOT
for spec in toolchain-wall:618185 toolchain-wall-replica:930413; do
  s=${spec%:*}; seed=${spec#*:}
  python3 -B "$W/edit_holdout.py" warm test --study "$s" --workspace --mode wall \
    --result "$W/edit-holdout-$s" --cargo-home "$B/cargo-edit-$s-test" \
    --base "$W/path-compare/build/bin/base" --candidate "$W/path-compare/build/bin/guard-stack" \
    --pairs 8 --seed "$seed" --toolchain-plan "$W/toolchain-wall-plan.json"
done
```

To run a source rebuild from a different path, verify its source, profile and build receipts first. In a separate copy of each plan, replace only machine-specific local ELF hashes with the verified rebuilt hashes. The first seven-change warm plans use their distinct, non-PGO driver pairs. The eight-change plan uses the `pgo-confirmation-v2/audit.json` values for Cargo and recomputed hashes of the matched Wild binaries. Keep the distributed rustc/release linker hashes, command, schedules and statistics fixed. The original measured ELF identities are retained in the archived plans.

**Warm and verify.** Set `E` to the fresh eight-change study directory. The original preparation used CPUs 24–31. For a different host, choose allowed CPU IDs for `preparation_cpus` and `native_cpus` in the copied plan before warming, and set `OHM_EIGHT_MONITOR_CPU` to an allowed core outside the measured set. The sampler records and enforces its selected affinities. Use `-j8` in every run.

```bash
E="$W/eight-wall-replay"
prep=$(python3 -B -c 'import json,sys;print(",".join(map(str,json.load(open(sys.argv[1]))["preparation_cpus"])))' "$E/plan.json")
for cohort in initial replica; do
  taskset -c "$prep" python3 -B "$E/run.py" warm "$cohort"
  test -f "$E/results/$cohort/READY.json" || exit 1
done
```

The harness copies the immutable seed, applies and settles the structural body edit, and makes two checked target copies. It audits the next identical literal edit in both arms with native `strace`, a credential-free environment, matching full rustc argv and linker-output rosters, and all reported test executables. Each stage restores the original private Cargo and linker selections and archived uv source. The shared release stays untouched. The two measured arm targets persist so every subsequent pair has the same incremental compile history.

**Time the two cohorts.** Stop other local builds, tests, counters and profiling. Explicitly release the reserved host, then run:

```bash
sh "$E/timed.sh" --coordinator-released
```

The script takes the shared native measurement lock and requires two quiet five-second windows before each cohort. Its preflight checks CPU utilization, iowait, dirty/writeback memory and active foreign compilers/linkers/counters. Every timed process is a direct Cargo launch. After Cargo exits, the clock stops and any remaining native process-group cleanup is waited for off-clock. After both cohorts, the script repeats the exact native six-compiler/five-linker audit on the measured affinity for each arm. Raw nanoseconds, executable identities and source hashes are in `results/<cohort>/pairs.csv`, with per-command logs and receipts. `quiet/` contains preflight and in-window host records. `summary.md` and `results.json` are generated from the two complete, audited 24-pair cohorts.
