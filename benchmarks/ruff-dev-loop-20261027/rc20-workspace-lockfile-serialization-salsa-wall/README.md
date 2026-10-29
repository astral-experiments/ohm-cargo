# Whole-Cargo wall time after changing Ruff’s Salsa requirement

Across 32 balanced pairs on one Linux host, the serializer candidate completed the edit and first unchanged build 4.46 ms sooner at the paired median. The 95% interval for the relative reduction spans −1.06% to +4.50%. The primary endpoint did not establish a whole-command speedup. The separate instruction study measured the work this change removed. [Instruction counts and native evidence](../rc20-workspace-lockfile-serialization-salsa-instructions/)

| Endpoint | Parent / candidate median (ms) | Median paired reduction | 95% interval | Median time saved | Faster pairs | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Edit and first unchanged | 259.14 / 249.28 | +1.90% | [−1.06%, +4.50%] | +4.46 ms | 19/32 | 0.754 |
| Edit alone | 190.94 / 186.18 | +1.81% | [−1.08%, +4.60%] | +3.14 ms | 20/32 | 0.646 |
| First unchanged | 62.76 / 61.37 | +0.25% | [−1.59%, +3.33%] | +0.15 ms | 17/32 | 0.860 |

Reversing Ruff’s root Salsa requirement from 0.28.5 to 0.28.2 had a +2.67% paired median reduction for the two commands. Restoring it had a +0.97% reduction. The unchanged command after restoration was 0.23% slower at the median. The most adverse complete pair was restore pair 26, parent first, at 233.170 ms for the parent and 664.567 ms for the candidate. Every pair remains in the analysis. The workload was an uninstrumented `cargo +ohm build -p ruff_text_size --locked --offline` against 93526150df078af7dd8fc4226cdcc469539d2001. Both caret requirements select the same Salsa release in the byte-identical 553-package lockfile. [Historical edit](https://github.com/astral-sh/ruff/commit/c890b04e575809cbff9b43975175b43dd82c3a1a)

Each arm received 16 reverse and 16 restore transitions, with eight AB and eight BA pairs in each direction. Each edit was followed immediately by its first unchanged build in that arm’s own history. The combined endpoint sums the two measured command durations. The analysis uses exact two-sided paired sign tests with Holm correction across the three endpoints. Its percentile intervals use 20,000 resamples stratified by direction and order. Positive values indicate a faster candidate. All direction/order summaries, absolute results, tails and raw per-pair values are retained.

## Native and timer controls

The parent, Cargo 2fe90823d, genuinely compiled the one Ruff library from empty target and build directories and then returned it fresh. The new seed’s 59-entry complete filesystem inventory was copied to physically distinct A and B directories. It used stock Rust and Wild from the enrolled toolchain. Five traced builds per arm before scoring and five after scoring each reported the single library fresh, launched no compiler or linker and produced the seed’s exact rlib and rmeta. Independently compiled callers returned `17 29 12`. The seed and both final arms were then mounted read-only and their retained callers run again. The new seed’s standalone rmeta and consumer matched the previous instruction study. In its rlib the two object member names changed, their payloads matched, and the name-bearing lib.rmeta-link payload differed. All three full archives in this wall-time study remained byte-identical. [Native input and source scope](../rc20-workspace-lockfile-serialization-salsa-plan/)

Timing starts at the monotonic raw clock immediately before launching the ordinary Rustup Cargo command. It stops immediately after a blocking `waitpid(pid, 0)` returns. Standard streams go to files opened before timing. An outer watchdog covers the complete controller. The kernel trace of 28 separate calibration commands confirmed blocking wait4 with flags zero. The medians for true, 5 ms, 15 ms and 25 ms waits were 1.61, 6.82, 16.92 and 26.79 ms. The tracer and artifact checking are outside the timed intervals.

A preflight in a separate namespace inherited the privileged launcher’s home after dropping capabilities. The native tracer could not open Rustup, and zero Cargo commands or scores ran. The corrected namespace restored the ordinary user’s home and account fields. The original attempt, corrected controller, kernel waits, frozen protocol, accepted native gates and raw outputs have separate SHA-256 commitments.

## Verify and replay

Run `sha256sum -c SHA256SUMS` and `python3 -IB verify.py --self-test`. The verifier reconstructs all 128 durations from monotonic start/exit times, checks every stability marker, replays the 32-pair analysis and rejects six corrupted ledgers. The complete private raw archive has SHA-256 `77629be9b99a24ee90847f630388452781c3f5630887f2588e2d3d0ac4d8bcea`. The public projection includes every timing, raw standard-stream digest, distinct stderr text, tagged ELF/source identities, native kernel stream digests and final product facts.

For a new physical run, supply the two exact PGO Cargo images from `protocol.json`, a verified official SDK, Ruff Git objects and an offline registry already populated for the pinned workspace. On an idle Linux x86-64 host with the documented disk floors, CPUs 0–3 and 29–30, ordinary UID 1000, Rustup proxies, strace and sudo permission for private mount namespaces, run the following. Both study locations must be new. Use a compact offline registry. The replay copies the SDK and registry into its own template and does not need a download. The original acquired run used existing read-only source and registry layers and independently empty build stores. The helper reconstructs the template from the caller’s supplied inputs.

```sh
python3 -IB replay.py --study /work/salsa-wall --physical /dev/shm/salsa-wall-copy \
  --ruff /work/ruff --sdk /work/ohm-sdk --registry /work/offline-registry \
  --parent-cargo /work/cargo-parent --candidate-cargo /work/cargo-serializer
```
