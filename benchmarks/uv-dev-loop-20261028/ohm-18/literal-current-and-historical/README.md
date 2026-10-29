# Literal Ohm 1.99.0-18 comparison after Wild #46 rebased

The two full-toolchain cohorts have finished. [Results, all 576 observations and the corrected metadata admission](../full-toolchain-wall/README.md)

Ohm Wild closed #45 without merging it. #46 now applies directly to Wild 0.11 at `db821991bd2931dd83e59f236149340ddfc2b427`, with base `e856d81f6683cad80b9fe0ebf1a0c3c403c6fe11`. At registration, Ohm 1.99.0-18 was still the latest published release. The five Cargo PRs, Rust #247 and Wild #46 were open. `release-status.json` records the published release, its component pins and each PR head. `upstream.json` includes the two historical Wild heads. [Wild #45](https://github.com/astral-sh/ohm-wild/pull/45), [Wild #46](https://github.com/astral-sh/ohm-wild/pull/46), [Ohm 1.99.0-18](https://github.com/astral-sh/ohm/releases/tag/ohm-1.99.0-18).

The original study registered three arms before the compiler builds. Its target root and evidence directories were still absent when this amendment froze. The new plan keeps every source tag, source path, command, CPU assignment, cohort order and relative order of the three historical arms. The current arm adds 144 timed commands, for a total of 576. The original registration and runner are preserved byte for byte. This study has its own evidence directory and retains the original fixed sysroot, target and Cargo-home invocation paths.

| Arm | Rust compiler and target libraries | Cargo | Wild |
| --- | --- | --- | --- |
| Shipped | Installed -18 | Installed -18 | Installed -18 |
| Matched base | Stage2 rebuilt from -18 | Independently trained base | Matched bare 0.11 |
| Historical eight | Stage2 rebuilt with Rust #247 | Five Cargo patches, independently trained on the guarded library | Historical #45 and #46, head `93600ec375472777043c28c33a5628adfbc0eb9b` |
| Current seven | Same guarded stage2 package | Same executable as historical eight | Current #46 only, head `db821991bd2931dd83e59f236149340ddfc2b427` |

The two rebuilt compiler configurations omit rustc PGO and BOLT. Their host and target library source differs only by #247. The Cargo arms use the existing independently trained PGO binaries. The coordinator publishes Wild as a separate executable. The membership comparison changes only that linker file between the two treatments. The initialized receipts must show the same Rust compiler, rustdoc, compiler driver, target std, LLVM runtime, PGO Cargo and stage2 readiness hash. Each checkout gives every arm its own settled target and Cargo home. Eight targets are warmed, with no additional Rust compiler build. The installed-release contrast measures the actual bundled toolchains, and the matched one controls the rebuilt compiler configuration. `official-linux-job-linkage.json` records the official build’s PGO/BOLT recipe and the evidence available in its Linux job. [Release Linux job](https://github.com/astral-sh/ohm/actions/runs/40741806145/job/123006030426).

For each of two real source-edit cohorts and each of `cargo check`, `cargo build` and `cargo test --no-run`, the earlier assignment had four copies of each three-arm order. Within each group of four original occurrences, a separate random shuffle assigns current insertion ranks 0, 1, 2 and 3. All 24 possible four-arm orders therefore occur exactly once. Every arm has six appearances at every rank and each pair runs twelve times in each order. Projecting away current reproduces all 144 original triple assignments and all 144 literal tags exactly. The original random ordering of repeated triples and the independent insertion shuffles together give equal probability to each full assignment, since `(24! / (4!)^6) × (4!)^6 = 24!`.

There are twelve primary comparisons across two treatments, two controls and three commands. For a treatment to qualify on a command, both its shipped and matched comparisons must pass in both independent checkouts. The initial cutoff for both the two-sided sign test and the position-conditional randomization test is `.05 / 12`. The independent second checkout uses `.05`, a different edit and separate caches. Both order-specific medians and the distribution-free 95% lower paired-median bound must be positive. The randomization test conditions on the identity and positions of the other two arms, yielding 12 pairs of observed opposite orderings and 4,096 admissible assignments. The report separately shows the earlier three-arm test projected from the same historical measurements as a sensitivity. No rows are removed. The program, artifact and exact 72-test-executable admissions from the original plan apply to all four arms.

The future `input-lock.json` binds the current binary to the linker agent's verified `current-pr46/ready.json` before initialization. It checks the released base, current full source commit, real executable digest, exact committed Cargo.lock SHA and locked release-build command. The three older file hashes come from the prior frozen receipt. `runner.patch` is the complete diff from the immutable original runner. `synthetic-verified.json` exercises all 576 artificial rows, positive and null effects, all original projections, 4,096-assignment test support, and rejection of five malformed input receipts. These validations run without invoking Cargo.

Run this successor only after the matched stage2 packages, current Wild receipt and exclusive measurement allocation are ready. The separate 32-core studies have their own data and hardware assignments. Commands for this literal study retain the original CPU and job settings.

```sh
study=work/round18-compiler/literal-native-amended
python3 -E -s -B "$study/run.py" bind
python3 -E -s -B "$study/run.py" initialize
taskset -c 0-15 python3 -E -s -B -u "$study/run.py" warm initial
taskset -c 0-15 python3 -E -s -B -u "$study/run.py" warm replica
taskset -c 0-15 python3 -E -s -B -u "$study/run.py" time initial
taskset -c 0-15 python3 -E -s -B -u "$study/run.py" time replica
python3 -E -s -B "$study/run.py" report > "$study/report.json"
```

Both source-matched stage-2 packages are now built. Their SHA-256 identities and the exact tested Wild builds were bound before warming uv. The build receipts record the differing standalone rustc linker default and the actual packaged Wild selected through Cargo in all three toolchains. [Build and execution receipts](stage2.md) · [Binary identities](input-lock.json)

The local four-toolchain replay archive is 133,205,022 bytes with SHA-256 `ba9e6e3c7bd7d8573d8fa1a132b6e46ea1b35f4b4129b2bdeb39bd450261efb1`. A detached staging test verified every redistributed file, selected the four exact compiler, Cargo, Wild and target-library sets under new paths, and preserved all 576 registered command assignments. Its scorer requires all six completed endpoint cohorts. [Portable archive identity and detached check](portable-replay-verification.json) · [Full component map](portable-component-map.json)
