# uv warm dev-loop: cached build-output identity remap

The candidate skips string replacement when recorded and current OUT_DIR strings are exactly equal. Source tree: `1df4917fb98e449198b61c502b799793d9aabffb`; baseline is PR175 (`efc8b51502f8a8d1fe76997dc984481edde2740e`). uv is unchanged at `3d82a6ad5a7eab8c68236553b7846517767c4b61`.

| Fixed validation | Reduction | 99% paired interval | Sign p | Result |
| --- | ---: | ---: | ---: | --- |
| Warm check, Cargo instructions, 12 pairs | 3.6577% | 3.6302% to 3.6845% | 0.000488 | Pass; 12/12 wins and both orders positive |
| Warm test --no-run, Cargo instructions, 12 pairs | 3.2104% | 3.1822% to 3.2308% | 0.000488 | Pass; 12/12 wins and both orders positive |
| Warm check, native wall time, 30 groups | 2.4590% | -5.5092% to 10.1411% | 0.5847 | Inconclusive |
| Warm test --no-run, native wall time, 30 groups | 0.6548% | -2.3905% to 3.8403% | 0.0428 | Inconclusive |

Only the instruction-count improvements are claimed. Check and test-build instruction validation are separate completed, predeclared batches; each passes the same fixed gates. Native groups contain eight calls; groups, not individual calls, are the statistical units. Instrumented elapsed time is never treated as native timing. No uv tests execute.

These are matched all-static/ohm-defaults, ThinLTO, one-codegen-unit builds using stock Rust 1.99.0, with no PGO. They are not the published PGO binaries. Cargo runs under the pinned Ohm 1.99.0-6 compiler. Callgrind 3.22 counts Cargo userspace instructions only; both variants encounter its brk/allocator fallback. No native speedup is established.

The exact measured candidate passes 15 existing parser/relocation tests using the supported classic-defaults override, with 11 also passing under Ohm defaults. Four Ohm-enabled cases assume a different verbose compiler-command snapshot. The earlier stock-compiler runner mismatch and all corrected attempts are retained. Separate exec traces prove both variants' Ohm-enabled uv check and test-build commands are fresh.

See [REPRODUCE.md](REPRODUCE.md), the frozen [protocols](protocols), [runners](harness), [original configurations](configs), and [build/source/strip provenance](build). Historical metadata intentionally preserves original absolute paths. Seed new artifacts when reproducing at a new prefix. Use actual rebuilt binary hashes; historical binary identities are not downloadable artifacts.

[raw-results.tar.gz](raw-results.tar.gz) contains every raw sample/subrun table, warmup, preparation log, stdout/stderr, and correctness attempt from the listed completed runs, including the older exploratory results. Its contents are hashed in [RAW-MANIFEST.json](RAW-MANIFEST.json). Complete large Callgrind attribution profiles remain retained in the task workspace; this branch includes their counter lines and hashes in [callgrind-counter-extracts.jsonl](callgrind-counter-extracts.jsonl), as well as raw profiler stderr and scalar sample tables.

The original evidence index is a broader task-workspace inventory dated `2026-10-21T03:53:13.097592+00:00`. Its original reproduction plan is preserved in [historical/first-pr-evidence-plan.md](historical/first-pr-evidence-plan.md). Their pending fields predate the completed test-build instruction result included here. The index's path-cache and older i686 records are retained in that workspace and are not part of this build-output archive; RAW-MANIFEST lists the archive's exact contents.

Archive SHA256: `7f5de3fb65002288b8c656788d54b8da82da4ffe7a2df2de3bc9039a2e73366e`.
