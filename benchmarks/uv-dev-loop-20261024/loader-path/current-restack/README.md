# Cargo #178: exact-restack native-build → first-check replication

The exact current restack passed its fixed whole-command replication: median first-check time was **33.135 → 20.716 seconds**, a **38.0687% paired geometric reduction** with **99% CI [36.3550%, 39.9574%]**. All **12/12 pairs** improved; exact two-sided sign p = **0.00048828125**. The AB and BA subgroup speedups were 1.567152 and 1.663676. All raw command/state/output gates passed before analysis; no native sample was retried or excluded.

The experiment compares the exact restacked [baseline ff1eacd2](https://github.com/astral-sh/ohm-cargo/commit/ff1eacd2b577777ecb8a7f3e934ddac36d11928e) and [candidate 8fbefabb](https://github.com/astral-sh/ohm-cargo/commit/8fbefabb23d1b1950b9e5d224ed986ada7331192). It measures the first ordinary whole-workspace `cargo check` after `cargo test --no-run` on unchanged uv `3d82a6ad5a7eab8c68236553b7846517767c4b61`, using the pinned Ohm SDK6 compiler. No uv test executable runs.

| Input | Baseline | Candidate |
| --- | --- | --- |
| Cargo source tree | `6919395c3f4732ade7d263db1d5b64fd7562845e` | `45280a180bb4bea53c79d423c7cc71255dfe81c3` |
| Stripped Cargo SHA256 | `65a3b781f40c78150f8c4b40d5929361882acb0c05012a32d8982e47912cb7ab` | `8ae23fe7bf9fa322b28a08295fc4f8f508c7cd20085f5a6a6315d9679da3a973` |
| Stripped bytes / mode | 41,974,120 / `0755` | 41,974,312 / `0755` |
| Naturally produced native artifacts / crate compiler calls | 733 / 733 | 733 / 733 |
| Native test executables built | 92 | 92 |
| Native provenance entries | 432 | 432 |
| Producer `loader_injected` | `true` | `false` |
| Producer `compiler_search_directories` | `[""]` | `[]` |

The matched Cargo builds use stock Rust 1.99.0, `all-static,ohm-defaults`, optimization level 3, ThinLTO, one codegen unit, debug level 1, no incremental compilation and no PGO. Both were built serially at common source/target paths. Both actual `cargo -Vv` outputs are byte-identical and omit commit fields. The build record's `embedded_head` label denotes the common checkout HEAD `5e5d271d763d7beb38b48755e22bd59e93f02b97`; it does **not** establish an emitted commit identity. Complete staged-tree and artifact hashes distinguish the two variants. These are production-settings builds, not a reconstruction of the release-bootstrap/PGO toolchain.

The frozen design is one block of twelve balanced pairs, no measurement warmups, order seed `2026102126`, and one newly generated native-only seed per arm. Each command restores its own seed to the same canonical paths and verifies all contents, modes, nanosecond mtimes, symlinks and hardlink relationships before the stopwatch starts. The first native seed was candidate, then baseline. Hashing warms artifact pages; package-download bookkeeping persists while target/shared compiler state is restored.

The original statistical rule is unchanged: paired geometric time reduction at least 1%, a 99% paired-bootstrap speedup lower bound above 1, two-sided exact sign p ≤ .01, and geometric speedup above 1 in both order groups. Bootstrap uses 20,000 whole-pair resamples with seed `1701`. The original analyzer calls this shared gate `screen`; this experiment is a prespecified confirmation. No sample extension, replacement or interim effect inspection is allowed.

The task-dedicated AMD EPYC-Genoa VM reserves a prospectively fixed 210-second window before each complete pair for the three actual heavy systemd services named in the protocol. Unavailable timer deadlines wait; service-cycle changes or active services at the command boundaries invalidate the whole block. Waits, state restoration and verification are outside timing. Load averages are retained; no generic numerical CPU-occupancy threshold is claimed.

The independently accepted historical experiment remains separate: [its immutable evidence](https://github.com/astral-sh/ohm-cargo/tree/59e50d2065ee2a04772842a23eb89f0b3d362adb/benchmarks/uv-dev-loop-20261021/loader-path) compared `efc8b515` → `64343228` on an EPYC-Milan VM. Median first-check time was 36.073 → 22.219 seconds, with 38.5387% paired geometric reduction and 12/12 wins. That result predates this restack and is never pooled with it. SDK12 already contains this behavior; the present study is not a new SDK12 speedup claim.

[REPRODUCE.md](REPRODUCE.md) describes byte verification, unchanged-statistics replay, matched builds and a fresh native-only fixture. The 59 passing checks recorded here validate the collector/restoration/admission controls; they are not a new Cargo integration-suite result. Every baseline first check launched 500 recorded crate compiler commands; every candidate first check launched 174. The native baseline snapshot was fully restored at completion. This archive preserves all 24 raw command/exit/elapsed/stream records and per-sample restoration/service observations. Private system-wide readiness and transport records are omitted; their original digests and the exact selection are in `privacy-and-selection.json`. Selected member bytes are unchanged. A post-completion transfer outage required a new read-only export, not a benchmark retry.
