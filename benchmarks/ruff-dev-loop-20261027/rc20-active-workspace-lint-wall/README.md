# Ordinary Cargo after changing an active Ruff workspace lint

On one Linux x86-64 host, 96 paired trials measured the first edit and first unchanged command together. The parent was Cargo 97e5acfb7 and the candidate was 70baacdb3, built with identical release PGO inputs. On both arms the real workspace lint was passed to the genuine compiler. The complete command used the selected Ruff target, the official compiler and stock Wild. [Frozen schedule and decision rules](../rc20-active-workspace-lint-wall-plan/) · [Zero-score native admission](../rc20-active-workspace-lint-wall-admission/)

| Command | Parent / candidate median (ms) | Paired time saved (ms, 95% CI) | Paired time saved (%, 95% CI) | Candidate faster | Holm p | Repeat bound |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Check | 463.78 / 258.03 | +181.15 [+164.04, +216.82] | +42.92 [+38.66, +46.31] | 28/32 | 5.79036e-05 | Established |
| Build | 485.13 / 288.94 | +176.99 [+161.12, +214.88] | +38.25 [+35.93, +42.93] | 26/32 | 0.000535053 | Established |
| Serde test build | 869.49 / 598.61 | +204.14 [+155.45, +373.09] | +26.29 [+20.56, +37.86] | 27/32 | 0.000226148 | Established |

Positive values are paired reductions. The command-specific primary requires an adjusted two-sided sign-test p below .05 and a positive lower relative confidence bound. The separate unchanged guard requires a lower paired saving bound of at least −3% and −5 ms. A guard with a wide interval can be inconclusive even when the point estimate favors the candidate. The table below separates both source directions and both individual commands.

| Command | Source direction | Phase | Parent / candidate median (ms) | Paired saving (ms, 95% CI) | Paired saving (%, 95% CI) | Faster |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Check | Both | Edit | 401.66 / 194.25 | +183.46 [+166.46, +229.57] | +49.68 [+45.05, +52.16] | 29/32 |
| Check | Both | Repeat | 62.68 / 63.26 | +0.07 [−1.67, +1.39] | +0.11 [−2.68, +2.22] | 16/32 |
| Check | Both | Combined | 463.78 / 258.03 | +181.15 [+164.04, +216.82] | +42.92 [+38.66, +46.31] | 28/32 |
| Check | Reverse | Edit | 392.58 / 196.03 | +186.46 [+164.37, +243.86] | +50.23 [+44.19, +55.42] | 15/16 |
| Check | Reverse | Repeat | 62.76 / 63.36 | −0.29 [−2.12, +0.85] | −0.45 [−3.52, +1.42] | 7/16 |
| Check | Reverse | Combined | 457.85 / 259.26 | +186.35 [+164.04, +243.15] | +42.94 [+37.52, +48.35] | 15/16 |
| Check | Restore | Edit | 438.82 / 192.91 | +183.46 [+156.62, +250.93] | +49.12 [+44.67, +55.55] | 14/16 |
| Check | Restore | Repeat | 62.17 / 62.21 | +0.92 [−8.90, +4.15] | +1.51 [−13.41, +6.38] | 9/16 |
| Check | Restore | Combined | 498.02 / 252.59 | +177.79 [+155.70, +311.55] | +42.21 [+38.66, +52.83] | 13/16 |
| Build | Both | Edit | 425.14 / 224.44 | +177.47 [+162.33, +211.57] | +44.34 [+42.40, +48.23] | 27/32 |
| Build | Both | Repeat | 61.17 / 60.36 | +0.70 [−0.13, +1.69] | +1.16 [−0.22, +2.70] | 19/32 |
| Build | Both | Combined | 485.13 / 288.94 | +176.99 [+161.12, +214.88] | +38.25 [+35.93, +42.93] | 26/32 |
| Build | Reverse | Edit | 448.92 / 244.26 | +161.14 [−27.45, +337.48] | +41.19 [−7.26, +60.23] | 11/16 |
| Build | Reverse | Repeat | 61.17 / 61.58 | −0.02 [−0.92, +1.32] | −0.03 [−1.50, +2.17] | 8/16 |
| Build | Reverse | Combined | 509.88 / 307.09 | +161.12 [−38.00, +337.10] | +35.68 [−8.65, +55.83] | 11/16 |
| Build | Restore | Edit | 413.01 / 223.97 | +185.78 [+168.17, +234.28] | +45.63 [+43.44, +50.43] | 16/16 |
| Build | Restore | Repeat | 61.11 / 59.81 | +1.48 [−0.14, +4.71] | +2.44 [−0.23, +7.55] | 11/16 |
| Build | Restore | Combined | 471.56 / 284.53 | +183.53 [+167.04, +238.12] | +39.25 [+37.40, +45.19] | 15/16 |
| Serde test build | Both | Edit | 797.61 / 525.05 | +235.17 [+165.00, +343.54] | +30.66 [+24.57, +39.44] | 28/32 |
| Serde test build | Both | Repeat | 69.96 / 70.80 | +0.55 [−1.77, +1.13] | +0.80 [−2.53, +1.60] | 17/32 |
| Serde test build | Both | Combined | 869.49 / 598.61 | +204.14 [+155.45, +373.09] | +26.29 [+20.56, +37.86] | 27/32 |
| Serde test build | Reverse | Edit | 790.26 / 522.85 | +204.07 [+144.60, +447.15] | +28.85 [+19.23, +46.05] | 14/16 |
| Serde test build | Reverse | Repeat | 69.48 / 70.80 | −0.75 [−26.68, +1.11] | −1.06 [−38.62, +1.60] | 7/16 |
| Serde test build | Reverse | Combined | 858.85 / 594.64 | +183.37 [+74.80, +445.78] | +24.63 [+8.22, +42.77] | 13/16 |
| Serde test build | Restore | Edit | 829.07 / 532.31 | +294.54 [+160.42, +419.93] | +34.89 [+23.42, +43.87] | 14/16 |
| Serde test build | Restore | Repeat | 71.31 / 70.65 | +0.91 [−1.14, +3.91] | +1.30 [−1.66, +5.24] | 10/16 |
| Serde test build | Restore | Combined | 901.10 / 602.46 | +299.91 [+159.35, +417.38] | +33.23 [+21.14, +40.69] | 14/16 |

The paired percentile intervals use 20,000 resamples within historical direction and arm order. Per-direction intervals retain the original eight AB and eight BA pairs. The primary sign tests use Holm correction across the three registered commands. The raw paired ledgers and statistics.json retain both order groups and the most adverse and favorable pair.

Check met both the primary and repeat criteria. Its most adverse complete relative observation was pair 30 (restore, AB), 405.29 ms on the parent and 692.42 ms on the candidate.

Build met both the primary and repeat criteria. Its most adverse complete relative observation was pair 19 (reverse, AB), 424.42 ms on the parent and 551.34 ms on the candidate.

Serde test build met both the primary and repeat criteria. Its most adverse complete relative observation was pair 10 (restore, AB), 740.11 ms on the parent and 976.00 ms on the candidate.

## Measured work and controls

The original source is Ruff 93526150df078af7dd8fc4226cdcc469539d2001. The reverse transition restores an allowance for Clippy large-stack-array diagnostics, removed in Ruff commit 3edca130e2. The restore transition reinstates that commit. Only three lines of the workspace manifest change. The 553-package 138,994-byte lockfile retains its exact SHA-256 throughout. A and B use a common release version stamp with distinct source-tree and ELF bindings. [Upstream historical change](https://github.com/astral-sh/ruff/commit/3edca130e22b2aba1d0cfe263e3f6a6679e166cc)

On the check transition the parent made one complete workspace resolution and then one cached request. The candidate made two cached requests. On the build and serde test transitions the parent made one full resolution, and the candidate made one cached request. Each unchanged command used the cache on both arms. These observations came from separate logged runs that first trained the logged environment at fixed source. The unlogged marker also changed on the parent and stayed fixed on the candidate in every scored edit. Both original logger setup stops have raw data commitments in the admission. No counts were taken during those failures.

Check and build each ran one full Ruff library compiler on every traced first edit. Serde ran the library compiler, its integration test compiler, and one stock native linker. Every Ruff compiler received the literal argument `--allow=clippy::large_stack_arrays` in the older state and omitted it in the restored state. Immediate unchanged commands were genuinely fresh. The prior-state revisit in the same native upper also rebuilt the matching selected units. Every measured transition used a new writable overlay over an independently trained single-state lower. Rebuilding the target and selected native link was part of the measured command.

For each command and each source state, two independent empty target/build-directory runs produced the reference. Both A and B were then trained separately from copies of the same physical Rust product set. Each measurement rechecked all inherited public products outside its timer and compared the resulting selected product and real caller or test harness against both independent same-state references. Valid Rust code compiled against the check metadata and the invalid caller produced E0599. The neutral metadata-only caller binary emitted an empty downstream metadata file. The real build caller printed `17 29 12`. The serde harness and its test list were byte-exact and all three genuine tests passed.

Library archives retain all raw hashes. Rust randomized CGU member-name suffixes across independent histories. The comparison also authenticated ordered complete object bytes, symbol-to-provider ordinals, archive headers, the full metadata wrapper, and the link-metadata roster. The build caller and serde ELF are checked by their entire file bytes. Raw archive identity is not claimed across independently generated names.

The post-study read-only check reopened 24 actual independent cold or final transitioned views. The coordinator received and rehashed 21 distinct complete publicly generated bodies (3,777,353 bytes), and reran strict archive parsing on each retained library. Each final consumer or harness was also run a second time on the source host with input mounts read-only. The private raw archive digests, original trial result hashes, and every traced kernel or Cargo stream digest are included in the projection. No durations were excluded.

A blocking waitpid with flags zero ended each ordinary Cargo clock; the kernel independently confirmed all 28 calibration waits. Median elapsed milliseconds for true, 5 ms, 15 ms and 25 ms samples were 1.52, 6.74, 16.71, 26.82. The acquisition used 4 pinned workload CPUs. The outer timeout, mount setup, tracing, hashing and downstream checks run outside these timings. These measurements apply to the three locked offline selections on this host.

## Verify and rerun

Run `sha256sum -c SHA256SUMS` and `python3 -IB verify.py --self-test`. The verifier reconstructs the paired effects and intervals from the original start/end clock values and exercises six adverse data changes. The public files contain stable logical package identities, full native argument digests, actual compiler flags, cache events, original SHA-256 commitments, and enough per-pair detail to reproduce all statistics.

For a new physical run, provide a read-only checkout with the pinned Ruff Git objects, the enrolled official Linux x86-64 SDK, both exact PGO Cargo images, a populated local registry, and two empty private directories. The host needs root-only private mount setup, ordinary UID 1000, Rustup proxies, strace, and CPUs 0–3 and 29–30. The study preserves at least 24 GiB on each durable volume and 16 GiB on the allocation volume. The portable setup reconstructs the input image from separately provided local sources. The original study used preexisting authenticated read-only layers. The replay has a new target history and machine-specific wall measurements.

```sh
python3 -IB replay.py --study /work/lint-wall --physical /dev/shm/lint-alloc \
  --ruff /work/ruff --sdk /work/ohm-sdk --registry /work/offline-registry \
  --parent-cargo /work/cargo-parent --candidate-cargo /work/cargo-lint
```
