# Full uv test build after removing one integration test

**Question.** On the source used for Ohm 1.99.0-20, does applying the math-assembly guard from Rust PR #270 together with both assembly patterns from PR #275 halve the wall time of the first full uv test build after a developer removes one integration test?

This is a new comparison of the complete stack against the original source. The completed comparison of #270 against #270 plus #275 answers a different question about the incremental benefit of #275. The standalone #275 experiment stopped during warmup and contributed no edited commands.

## Subjects and edit

Use the already-built matched stage1 compilers, bare P at `7e71d3150938ff8ed82aca03416439d7e5b87ef3` and CZD source tree `f78a9c378d843ba2c2928bf26902be8d1be03c75`. Their rustc driver SHA-256 prefixes are `0a7e620394e3` and `21ff46bc296f`. The other 64 SDK files are byte-identical. Both arms use ordinary Cargo, the same standard library, LLVM and Wild and the default native input guard. These are source-matched builds without release training. The distributed binaries are covered by a separate contextual measurement.

Start at uv `c22e6b71933443e9cd299d4b6ac8de035ed4825b`, with identical ref, source paths, registry, lock, settings and jobserver. Remove the 62-line `tool_list` addition from uv PR #20770 in place. Only `crates/uv/tests/tool/tool_list.rs` changes, from Git blob `9e699be1e4508906b8f30be2a6b047ff4babd7d1` to `13a1010ef5b04a60b16ec5b16714dc777b2f40b1`. Its test count changes from 181 to 180.

## Measurement

Run `cargo test --locked --offline -j8 -p uv --no-run` once after each write. Independently prepare the original source A with each arm and verify its own archived checkpoint. Each of the 24 measured invocations restores its arm’s unedited A before making the edit. Both arms of each pair receive identical edited bytes and mtime. Report the complete foreground Cargo interval, including all compilation and linking. Record separate untimed process admissions, six native guard markers, the two version outputs and all 15 test listings. Keep previous experiments’ data separate.

There is no efficacy pilot. The 12 pairs’ first arms, in chronological order, are **CZD, CZD, CZD, P, CZD, P, CZD, P, P, P, P, CZD**. Only machine-detected foreign work can invalidate a whole pair. Reuse its original order, with at most two replacements. A correctness failure stops the study. The original disk, tmpfs and memory floors apply.

## Exactly which executable bytes can differ

While preparing A, capture all 17 complete programs after the *first ordinary unedited P repeat* and seal their role-specific allowed SHA-256 values before either the subsequent traced P repeat or any CZD warmup. Capture the separate edited B reference after the first unscored P admission, also before any CZD B command. Use the applicable finite P-derived list for every same-arm and cross-arm repeat. Listings, versions, paths, sizes, and exit codes must match their reference.

An eligible Wild executable can have `sh_entsize` 0 or 8 in its non-loaded `.rodata` **section header**, with the corresponding 32-byte GNU build ID. Independently derive the two complete SHA-256 values from that role's P bytes. Verify the actual ELF headers, recompute each Wild BLAKE3 ID, compare all remaining bytes and reconstruct both original files when an alternative is actually observed. Keep both originals. For an ineligible ELF require raw identity. Reject a third form, any other differing byte or a transfer of alternatives between roles. The earlier P→ZD comparison required exact identity within an arm and correctly failed on two different unedited `pip_install` outputs.

## Decision and timing

Report all 12 paired ratios, absolute median times, the third-to-tenth order-statistic interval and the six-per-order medians. A twofold claim requires both order medians and the third-smallest ratio to be at least 2, a two-sided exact sign-test p below .05 against 2, and a Holm-adjusted p below .05 across all twelve declared contrasts. The two rejected combined package runs and the rejected standalone P→ZD run enter at p=1. Missing studies also enter at p=1.

This prospective comparison can start only after the ordinary commands, both official release contexts and the separate stock −18 diagnostic have closed and the full resource and product checks pass. The earlier ten-way marginal result keeps its own original decision.
