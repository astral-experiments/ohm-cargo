The candidate shares each workspace's immutable inherited dependency map through `Arc`, avoiding a deep clone for every member while preserving lookup and per-member processing. This is the fresh stack180 baseline versus the single inherited-dependency-map change.

| Workflow / metric | Reduction | 99% paired interval | Sign p | Full gate |
| --- | ---: | ---: | ---: | --- |
| check / Cargo Ir | 3.7403% | [3.6321, 3.7906]% | 0.00048828125 | pass |
| test / Cargo Ir | 3.1867% | [3.1706, 3.2063]% | 0.00048828125 | pass |
| check / native wall time | -0.1743% | [-3.9962, 2.7946]% | 0.2004884221 | does not pass |
| test / native wall time | 2.2575% | [-0.9040, 5.7535]% | 0.09873714671 | does not pass |

Neither native workflow passes the complete wall-time gate; no native wall-time improvement is claimed. Neither workflow establishes a significant native regression under the frozen rule.

Cargo Ir counts cover the instrumented Cargo process only, with compiler, linker and build-script children excluded. Instrumented elapsed time is not native wall time. The production pair uses all-static and ohm-defaults, ThinLTO and one codegen unit, without release PGO. The measured commands are warm, fresh `cargo check` and `cargo test --no-run`; no test program is executed. These results do not establish a cold-build speedup.

The original fixed IR observations are retained exactly. A post-integrity guard failure was followed by a metadata-only closure of the original analysis/gate tail. Its first launch stopped before staging; the retry completed remotely even though SSH returned 255. Both failed local receipts and authenticated successful remote finalization remain. The first native admission stopped before any Cargo call; exactly two remote metadata files and three local launch records were retained, after which the byte-identical original phase ran once. No measured observation was replaced, omitted, pooled or extended.

Both independent phase reviews completed all raw workflow checks before effects. IR uses 12 fixed pairs per workflow; native uses 30 pairs of eight-call sums. Each has two warmup pairs. The full gate requires at least 1% reduction, a positive 99% paired-bootstrap lower bound, exact two-sided sign p ≤ 0.01, and positive effects in both orders. All samples, profiles, logs and failures are retained.

Verify SHA256SUMS, then use REPRODUCE.md. RAW-MANIFEST.json inventories the original archives and every raw payload. The complete original Callgrind profiles are included losslessly.
