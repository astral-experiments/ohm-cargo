# Aligned generated-file reads in ordinary Ruff Cargo builds

The measured command was `cargo +ohm build -p ty_vendored` on Ruff `93526150df078af7dd8fc4226cdcc469539d2001`. Both arms used independent fully warmed targets, identical source and output spellings, a trusted private registry and the same native toolchain. The candidate aligned BLAKE3 updates on the first of two real reads of 7,918,933 bytes. Both images reread the files independently for downstream freshness. An exact source-matched profile-guided control was built above the qualified 1.99.0-19 Cargo source. The previously published 1.99.0-18 compiler used here has the identical Rust compiler source tree.

The complete numerical plan is pinned at `2d40c0ba8f68ba2bfadc489db876b49f5c442de4` and native qualification at `0454e2572db9da56d5c2520ec0dfccd5dc02bb5e`. Each host ran 48 prespecified counterbalanced strata of eight adjacent ordinary commands. The decision required both hosts independently to exceed a 0.5% median saving with a 95% lower bound above 0.25%, two-sided exact sign p below .025 and at least 32 favorable strata.

| Host | Control median | Candidate median | Paired saving (95% CI) | Faster strata | Exact p |
| --- | ---: | ---: | ---: | ---: | ---: |
| Genoa | 199.246 ms | 197.855 ms | 1.09% [0.69%, 1.79%] | 42/48 | 1.00875e-07 |
| Milan | 217.329 ms | 215.867 ms | 2.73% [-2.26%, 7.03%] | 30/48 | 0.111403 |

The two-host performance gate failed. The raw command times, ordinary stderr, empty stdout, pre/post native references, signed output maps and all per-host statistics are included. The 182-unit command consumed the three generated files twice. The results measure this fully warm Linux package workflow. The genuine content/mode edits and the independent Rust caller were exercised in the separate, previously published native qualification.

Run `python3 -B verify.py` from this directory to recheck every clock, the complete per-arm post-run maps, both tests of significance and the prespecified decision. Run `sha256sum -c SHA256SUMS` to verify all exported files.
