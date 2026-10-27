# Whole Ruff no-op verification on the FIFO-safe Cargo stack

Ruff is pinned at `93526150df`. The previous Cargo is `d38fdd025036` (release PGO SHA-256 `dd5cab154b8d…`). The candidate is `f4c3de3aafcc` (`90efada2bf15…`). Both use the same Rust compiler `dec72d1e68fd…`, eight jobs, two explicit local trust settings, the same logical and physical target, and the same trained Ron proof on H2. These are ordinary complete Cargo commands. Native time starts when the rustup proxy is created and ends when it returns. No tests run.

| Endpoint | Control median (ms) | Candidate median (ms) | Paired time reduction | Registered interval | Faster blocks | Registered decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `cargo test --no-run` | 775.39 | 716.75 | +17.677% | -15.578% to +35.342% | 11/16 | Did not qualify at exact one-sided p=0.077001 |
| `cargo build` | 799.13 | 669.09 | +17.006% | -15.513% to +36.625% | 10/16 | Did not establish the 5% noninferiority margin |

The eligibility test was the unchanged 16-pair, eight-per-order schedule. The primary test endpoint required at least 13 favorable pairs, a positive lower paired-median bound, and an exact one-sided randomization p below .05. The build endpoint had a prespecified 5% noninferiority margin. Every measurement was retained. The four independently prepared physical anchors were byte-identical between the two Cargo arms within each command. The 64 ordinary native processes and their 64 separately traced repetitions started no compiler or linker and kept 501/619 units fresh. All 15/110 workspace ELF images and 6/102 runnable products kept their exact initial identities.

Only the test graph advertises `ron 0.12.0`, with the default and std features. Its active compiler output and translated fingerprint share a unit directory. The actual Insta compiler passed that same Ron archive via `--extern`. A separately stored older Ron from a different compiler namespace remained byte-identical in every observation. Both translated records retained a valid BLAKE3 footer, and both raw dep-info files, observed inputs and .rmeta identities stayed fixed.

The first protocol stopped before timing because it counted both physical Ron records as active. It produced zero scored samples. Its original control preparation rebuilt 501 build units and 619 test-build units in a fresh secure namespace. The candidate preparation then saw zero dirty build units and 56 dirty test-build units. Those unscored processes are retained in runner/rejected-v1-and-starting-state.json. The v2 registration, revised observation logic, exact Cargo JSON and prior rustc out directories were published before collecting any times. The four v2 anchors were sealed before scoring. [V2 registration](https://github.com/astral-sh/ohm-cargo/tree/80139edda73d9cf453fb1bbdab4e444d4111a65b/benchmarks/ruff-dev-loop-20261027/observed-span-prefetch-fifo-v2)

The registration includes an independent equal-size/backdated SDK replacement, byte-dependent real macro outputs on both edit directions, unchanged siblings, opaque wrappers, jobserver, regular symlink, and no-writer FIFO controls. The fingerprint still verifies the SDK bytes. Ruff’s single active reader uses only registry crates, so a normal Ruff workspace-source edit cannot dirty that reader’s closed dependency graph. This experiment measures the full warm no-op commands.

The optional post-score control clone stopped before it removed its active Ron proof. Its separate rustc --version calibration counted two opens of the same binary and required exactly one. All 64 primary runs and all 64 independent audited repetitions had already finished. The original failure is preserved in initial-auxiliary-recovery.json and training-limit.json.

Run `python3 -B runner/analyze.py --public .` and `python3 -B verify-witness.py .` to independently verify the sample statistics, launch rosters, physical proofs, and all anchored native outputs in this packet.
