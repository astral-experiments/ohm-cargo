# Verify large procedural-macro reader inputs in parallel

A trained Cargo command can skip a procedural-macro reader after verifying the compiler and source inputs whose changes could alter its native output. The prior verifier read those checksums serially. This candidate places the largest checksum miss in a batch with small files and computes the other batch concurrently, using one available Cargo jobserver slot. It applies when the largest miss is at least 32 MiB and the remaining misses total at least 16 MiB. A dirty upstream dependency still takes the existing scheduling path. The observer receipt and BLAKE3 calculation use the same format in both arms.

| Whole native command | Earlier Cargo median | Candidate median | Median paired reduction | Paired median interval | Faster pairs | Holm-adjusted p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Trained build with two true span readers | 101.77 ms | 80.43 ms | **20.92%** | 8.39% to 23.59% | 14/16 | 0.02145 |
| Trained test build of a consumer of registry `ron` 0.12.0 | 112.32 ms | 92.75 ms | **16.17%** | 9.60% to 18.52% | 15/16 | 0.000311 |
| First build after a genuine one-byte change to an observed input | 444.13 ms | 427.30 ms | 1.45% | −1.54% to 21.42% | 10/16 | Negative control |

The two unchanged commands were the registered co-primary comparisons. Each used 16 fixed, balanced pairs and all 12,870 possible assignments of eight earlier-Cargo-first pairs. Their raw one-sided randomization p-values were 276/12,870 and 2/12,870. The edited command cleared the prespecified noninferiority bound of −5%. Its timing interval includes zero. No measured observations were excluded. The initial exploratory Ron launcher looked for a flat output directory and stopped at its empty build. The registered runner used Cargo’s reported executable path. [Registered plan and source patch](https://github.com/astral-sh/ohm-cargo/blob/93d70de525ef34d2b76e10a395863edd1707ef7d/benchmarks/ruff-dev-loop-20261027/observed-span-parallel-verification/sdk-prefetch-registration.json)

The process audit found zero compilers and zero linkers on every unchanged build. The candidate used exactly one checksum worker on each, and the earlier Cargo used zero. Each genuine edit ran four full rustcs, one link-only rustc and three final native linkers. Neither Cargo used a checksum worker on those edits. The two readers’ outputs changed after the edit, and all three fixture executables matched their independently built references byte for byte. The Ron test executable also matched its own empty build. Its tests were never executed. These are two scoped builds. The registry source is the same dependency that acted as the sole span observer in a separately audited default Ruff test build at commit `93526150df078af7dd8fc4226cdcc469539d2001`.

`commands.jsonl` covers 227 complete Cargo invocations. There are three independent empty references, 32 training runs, 96 native timings and 96 further process-traced replays on new stores. `successful-execs.csv` records all 1,206 returned successful executions. `checksum-workers.csv` records 40 returned checksum-worker starts. One training trace also contained an unidentified unfinished syscall with no return status. The public records retain every recorded return and the tool classes and counts from the matched audit.

The guarded SDK cannot be replaced with a version-string or mtime check. A real procedural macro observed a changed source filename inside a private copy of `libstd.rmeta` with the same size and mtime, and a fully trained warm command recompiled its reader and matched the independently empty build. The older and candidate SDK controls and a diagnostic that verifies all 39 actual BLAKE3 inputs are included. With a genuinely exhausted inherited FIFO jobserver, the candidate ran zero checksum workers. Giving it a single token ran one worker and returned that token. A one-job build ran zero. Additional controls exercised corrupt, incomplete, truncated and inherited receipts, a compiler wrapper, simultaneous dirty sources, a same-mtime symlink change, and real-check and test-build modes.

The baseline source is Cargo `b0a4df740b57589ecec3c83e30d5d326ab52a56d` plus `observer-edit-screen1.patch`. The candidate adds `observer-sdk-prefetch-screen1.patch` (SHA-256 `1ed62b210aa96a41b19ecc8788ff10e2d13a34c124a61b75614d742672add17e`). The local source-matched PGO Cargo binaries are `597a8a2d1bae8a572ff4eec7b2dd2c54dbc3c8527a61fd5a080bd3b6d4eeb419` and `025d5bf9a3fd64b72fe7f7ef4231b44c434ee340d3051fbb3f15b155504ba5cd`. Both were built with the Ohm release profile data `481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7`, incremental compilation disabled, and the same source/build paths, release configuration and Ohm defaults. Both arms use the release-PGO/BOLT compiler driver `dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f`.

Run `sha256sum -c SHA256SUMS` and `python3 -B verify.py` in this directory to validate the evidence and recalculate all three endpoints. Re-running the live commands requires a compatible Linux Rustup proxy with an `ohm` alias, the exact subject binaries, bubblewrap, strace, four reserved cores and trusted cached registry sources for the pinned Ruff lockfile. `STATE/sysroot` and `STATE/rustup` must point to the same matched SDK. The runner creates private physical stores at the new working path and binds both arms to the same logical paths inside it.

```sh
PREVIOUS_CARGO=/absolute/cargo-prior \
BENCH_REGISTRY=/absolute/cargo-home/registry \
RUFF_LOCKFILE=/absolute/ruff-at-93526150/Cargo.lock \
  python3 -B sdk-prefetch-study.py --mode score --cpus 0-3 \
    --state /absolute/STATE --work /dev/shm/ohm-sdk-prefetch-replay \
    --driver /absolute/librustc_driver.so --parent /absolute/cargo-golden \
    --candidate /absolute/cargo-with-parallel-verification
```

The Rustup frontend and all Cargo/driver digests are recorded in `subjects.json`. The study and the linked source repository require repository access.
