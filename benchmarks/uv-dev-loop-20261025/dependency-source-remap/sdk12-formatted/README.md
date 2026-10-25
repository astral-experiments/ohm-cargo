# Dependency source remapping: direct formatted-executable confirmation

This separate cohort contains 32 complete sanitized Cargo-parent Callgrind profiles for candidate tree 70dbee538c9ccaf6c5d348550ddd0aa239e4126b and executable c76a42fdaa6b91e76ab866a4a1a662ed679d2aa81b15bf91109cf5497c989995, against the unchanged R1 baseline. The original successful cohort is retained separately.

| Machine | Fewer Cargo-parent instructions | 99% interval | Wins |
| --- | ---: | ---: | ---: |
| Host 1 | 0.4435494793% | 0.2644011570% to 0.5425899588% | 8/8 |
| Host 2 | 0.5599279780% | 0.4828020438% to 0.7457072920% | 8/8 |

Both two-sided exact sign-test p values are 0.0078125. Separate 200,000-draw paired bootstraps use prospectively fixed seeds 20261025343 and 20261025344. Each lower bound must exceed 0.25%; no observations are pooled across hosts or with the earlier cohort. No new eligibility pilot was run.

Run `python3 -I -S -B reproduce.py` in this directory. The replay authenticates every numerical-core file, independently sums complete raw records and checks final, self-cost, stderr, arm/order and registered statistical summaries. All numerical functions remain the frozen implementations. Sanitization changes only command/path labels; every non-path profile byte remains exact. Original raw/gzip/stderr hashes are retained in PROFILE-MANIFEST.json.

The metric covers Cargo and all its threads. Compiler, linker, build-script and other child instructions are excluded. The real compiler/linker execute, but this is not a whole-command wall-time result. No test body executes and no test-build claim is made.

The workload is uv 3d82a6ad5a7eab8c68236553b7846517767c4b61, with the registered equal-length five-byte ordinary-comment edit and `cargo -Zohm-defaults=yes check --locked --offline -j 8`. Both arms contain R1's registry cache. This confirmation used new independent-inode copies of the already authenticated, source-built warm banks, preserving bytes/modes/mtimes and 445 committed cache slots (803,161 bytes). Both copies passed fresh native and zero-compiler checks. Original banks and prior observations remain untouched. Cache inventories are not hit counters or physical-I/O measurements.

Fresh native/profile compiler argv, entire ordered environments, diagnostics and each arm's exact output hashes were admitted before numbering. The first host's cross-arm metadata differences were exhaustively decoded as eight generated lifetime-index permutations; the second host was byte-identical. All other bytes and all 1,135 stable definition fingerprints match. Future output admission remained exact per arm.

The test-only Rustfmt change preserved the 22,642-byte production prefix, but the old strict whole-binary gate stopped. The new binary has different GNU build-ID bytes, 305 nonloaded LLVM symbol-name suffixes and the resulting section-table offset. Its code/data and program headers match the prior candidate. We retained that strict stop and ran these wholly new direct blocks instead of transferring the old result to a different binary. The formatted candidate passed all 24 focused cases; the unchanged baseline's original 23 applicable cases remain bound.

The optimization moves name/source identity out of shared manifest data, avoiding cloning that payload when remapping only a dependency's source. On x86-64 the outer Dependency grows from 8 to 32 bytes while the shared payload shrinks by 24 bytes. Peak memory is unmeasured.
