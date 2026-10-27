# Ten Cargo drafts on fresh Ruff workspace commands

Measure the complete ten-draft Cargo, including the small incremental check scheduler, against the release-PGO control. This is an independent combined comparison. The earlier nine-Cargo result and the separate scheduler’s fresh-check cost remain separately available. [Nine-draft source patch](../cargo-stack-holdout/nine.patch), [additional scheduler patch](../frontend-scheduling/candidate.patch)

Use the ordinary Ruff workspace `cargo +ohm check`, `cargo +ohm build` and `cargo +ohm test --no-run`, all with `--offline --locked`. All targets are already built. Use the same Rust compiler, task-specific target, build directory, home, release profile data and absolute command path in both arms. Run Callgrind with child tracing. Every counted invocation must have exactly one Cargo process. Untimed JSON verification before and after each set must show 520, 501 and 619 entirely fresh artifacts respectively. Wait for the registry manifests to settle, retain raw pairs and reject a set on a lock wait, changing records, changed Ruff index or failed command.

Use 12 independently ordered pairs per command, exactly six candidate-first. Use seeds 622901, 622902 and 622903 for check, build and test compilation on CPUs 16–19. Report the median paired instruction reduction, its distribution-free 95% interval, the exact two-sided assignment test and a Holm adjustment across all three commands. Report all endpoints, including any adverse or inconclusive result. [Counting harness](../cargo-stack-holdout/fresh.py)

The first run in the broad task home completed the check and build cohorts, then failed the requirement for two consecutive stable cache-warming cycles for test compilation. It recorded zero test pairs. Retain the first 24 pairs separately and rerun the entire three-command schedule against isolated copies of the 410 settled Ruff-only records for each format, at the same private home path. Restore the broad task home afterward and verify its original file identities and contents. [Previous occurrence and validated working set](../registry-diagnostic-keys/)

The independent reconstruction from all ten exact PR tips adds 170 lines of tests to the timed source tree. The complete binary has identical executable code, relocations and data at identical addresses. Its GNU build ID and non-loaded symbol-name table differ. As an additional confirmation, compare this exact-source binary directly against the original release control in an ordinary fully fresh workspace check. Use 12 balanced pairs, seed 618023, CPUs 16–19 and the same 520-artifact and stable-cache guards. Keep this single-endpoint schedule independent of the preceding three-command family and publish its result regardless of direction.

## Fresh workspace results

| Command | Median control instructions | Median ten-draft instructions | Median paired reduction | 95% median interval | Holm-adjusted p |
| --- | ---: | ---: | ---: | ---: | ---: |
| `cargo check` | 920,973,051.5 | 824,121,071 | 10.518% | 10.505–10.521% | 0.00649 |
| `cargo build` | 1,484,809,944.5 | 1,387,708,108 | 6.543% | 6.530–6.550% | 0.00649 |
| `cargo test --no-run` | 1,115,094,040 | 1,015,584,679.5 | 8.927% | 8.915–8.937% | 0.00649 |

All 36 pairs improved. Every scored command launched just Cargo. The active Ruff index, its single Git proof, and all 410 records in each registry format stayed fixed on each endpoint. The original broad-home directories and all 1,028 v1 and 410 v2 file identities and contents were restored. In the earlier broad-home test preflight, the v1 bucket `557` was the only cache record modified during warming. It contained `libtest-mimic` 0.8.1. That endpoint recorded no pairs. Run `python3 analyze.py` to verify the published order, exact probabilities, intervals and cache checks without a toolchain. [All 36 pairs](pairs.csv), [verified artifacts and proofs](verification.json), [24 earlier pairs](earlier-pairs.csv), [preflight details](earlier-preflight.json), [cache restoration](cache-restoration.json)

## Reconstructing the source and binary

Run `python3 verify-sources.py PATH_TO_OHM_CARGO --export-patch FULL_PATCH` in a clone containing the ten draft commits. The verifier merges each exact tip against the release base in temporary Git objects and compares the result to the measured source. The difference is 104 lines in a new `#[cfg(test)]` module, 30 lines inside an existing test module, and 36 lines in the integration test suite. All ten merge cleanly. [Exact tip and tree identities](source-verification.json)

Apply each subject patch separately at the same clean source path and build `cargo +ohm build --release --locked --offline -p cargo --bin cargo --features ohm-defaults` with `CFG_RELEASE_CHANNEL=dev` and `CARGO_PROFILE_RELEASE_INCREMENTAL=false`. Both builds used `-Cprofile-use` with the same Ohm release training profile, SHA-256 `481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7`, and `-Cllvm-args=-pgo-warn-missing-function=false`. Their 25,233,870-byte `.text` sections and all relocations, runtime data, addresses and ELF headers are byte-identical. Exactly 32 build-ID bytes and 9,074 bytes in the non-loaded `.strtab` section differ. Run `python3 compare-elf.py TIMED_CARGO FULL_DRAFT_CARGO` to verify the entire two files. [Independent ELF comparison](elf-equivalence.json)

## Exact-source rerun

The full release build from the ten draft tips used **10.510% fewer instructions** than the release control on a fresh workspace check (95% median interval 10.477–10.523%, exact two-sided p = 0.002165). It improved 12/12 independently ordered pairs. All 520 artifacts were fresh, and the registry records stayed unchanged. [Independent pairs](exact-source-pairs.csv), [validation and inference](exact-source-check.json)
