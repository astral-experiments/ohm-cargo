# Scheduler reachability bitsets: uv development-loop evidence

The measured patch reduces Cargo's instruction count for warm, unchanged uv builds against PR181. The primary `cargo test --no-run` workload used **1.9571% fewer Cargo instructions**; the secondary `cargo check` workload used **1.0591% fewer**. These estimates cover Cargo itself under Callgrind, with compiler children excluded and no test execution.

| Workload | Paired Cargo instruction reduction | 99% bootstrap interval | Exact two-sided sign p | Winning measured pairs |
| --- | ---: | ---: | ---: | ---: |
| `cargo test --no-run` (primary) | 1.9571% | 1.8993%–2.0941% | 0.00048828125 | 12/12 |
| `cargo check` (secondary) | 1.0591% | 1.0107%–1.1674% | 0.00048828125 | 12/12 |

Both workflows satisfy their original instruction-count gates: at least 1% estimated reduction, positive 99% interval, sign p ≤ 0.01, and positive estimates in both execution orders. Each fixed batch has 12 measured pairs and two warmup pairs; all 56 complete profiles, including warmups, are included. Both raw audits finished before effects were calculated. This package copies the accepted analyses and root reproduction; it introduces no new statistical calculation or observations.

**Native wall-time effects and regressions remain unverified.** Native preparation was interrupted by unrelated host activity before timed sampling. Publication eligibility was explicitly amended after the instruction results were known and before native effects were analyzed. The original full protocol remains unfinished. The original protocols, the dated amendment, independent policy review, and root acceptance are retained under `policy/`. There is no wall-time, equivalence, or native no-regression claim. These estimates compare this patch alone with PR181; combined gains with other patches are unmeasured.

The bounded bitset path replaces repeated hash-set unions when scheduler reachability fits its fixed memory bound. The original algorithm remains the fallback. It preserves weighted costs, duplicate/shared descendants, leaf handling, cycle behavior, overflow behavior, and queue ordering. Focused validation ran 13 tests in both checked/debug and optimized/wrapping modes, including the original implementation as a differential oracle. All eight required jobs passed in [exact-source CI run 39693579544](https://github.com/astral-sh/ohm-cargo/actions/runs/39693579544): Rustfmt, Linux/macOS Clippy, Linux/macOS Cargo tests, workspace tests, resolver tests, and schema tests. The optional APFS replay job was skipped. The exact source commit and terminal CI receipt are recorded under `source/` and `ci/`.

| Identity | Value |
| --- | --- |
| uv commit | `3d82a6ad5a7eab8c68236553b7846517767c4b61` |
| Baseline parent | `d81a093becb4321a975522624c2a383970f0d164` (PR181) |
| Baseline source tree | `c4178b67e0b3a64a12b9b58f84b97323b99d734e` |
| Candidate commit | `694d39ac73073f17008ce6e7bd53c1231ec6ceec` |
| Candidate source tree | `807c36ec5326d42ca19a921819e1b3d1e2776cb2` |
| Candidate patch SHA256 | `ef953c7ea9c1231ef1b5e1cad139a11b53e2675e89ec13470e2541d9eef05494` |
| Measured baseline binary SHA256 | `9659892de8f5b5c2b825273fcea8ee57d806da85dd600b80287407b43f055fef` |
| Measured candidate binary SHA256 | `595a79c696ddacea7613760cd62dfc57dbaa23ec554fd7bb9a1ff08bfc85cbec` |

The matched Cargo binaries used stock Rust 1.99.0, `all-static,ohm-defaults`, opt-level 3, ThinLTO, one codegen unit, and no PGO. Debug information was removed with verification that all 31 allocated ELF sections stayed unchanged. Both variants used the same physical source/target paths and common build inputs. This approximates the release feature/profile settings; it does not measure the published PGO-built release binaries or the release bootstrap compiler. Both binaries deliberately retain the same embedded Git head from the build recipe; the independently verified source trees above establish the actual source identities.

`raw-ir-publication-subset.tar.gz` contains the two complete IR result directories, every IR preflight trace/log, all original benchmark configs and runner sources, and an explicit selection of current source, build, correctness, and controller evidence. Every included file is byte-identical to the accepted collection. The original 568-file collection manifest is in `collection/`; `publication-subset.json` lists every included and omitted file with its original hash and a reason. The omitted originals remain private. The raw phase status and operational occupancy records are omitted because they contain unrelated process metadata; `validation/ir-status.sanitized.json` is a labeled projection, never a replacement for the original record. Failed native recovery logs and the large retention archive are retained privately; `native/` contains only a sanitized closure and opaque evidence identities.

For convenient inspection, `data/` duplicates the accepted tables, analyses, gates, and integrity records. Read `metrics.cargo_ir.statistics` for the reported endpoint. Original analysis files also contain instrumented elapsed/CPU fields and generic helper text; these are not native measurements. Historical gate fields named `significant_native_regression` in the IR phase likewise do not establish a native result. The dated publication amendment governs the limited claim above.

See [REPRODUCE.md](REPRODUCE.md) for the exact workload, build settings, verification commands, and limitations. All payloads are hashed in `MANIFEST.json` and `SHA256SUMS`.
