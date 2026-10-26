# Reusing a locked package source ID

The Ohm Cargo base is `461a3d1007ecc997a6d86c7d75e8b518575c8d90`. The candidate is `f9b4bba66b74fa2be213901ff6ec12c468530b1b`. Ruff is pinned to `93526150df078af7dd8fc4226cdcc469539d2001`, using the x86-64 Linux Ohm 1.99.0-14 compiler. The ordinary release builds used `--features ohm-defaults` and release incremental compilation.

`Dependency::lock_to` already checks that the source kind and canonical URL match. The locked package holds the interned entry for those two fields and its precise value. The regression test compares the resulting pointer with the former `with_precise_from` result for equivalent Git URL spellings, revision changes, alternate registry names, and transitions among unlocked, locked and updated states. Five unit tests and 42 focused integration tests passed.

| Collector | Default Ruff command | Fresh units | Fewer instructions in | Median paired reduction |
| --- | --- | ---: | ---: | ---: |
| Callgrind | `cargo check` | 520 | 12/12 pairs | 0.3102% |
| DynamoRIO | `cargo check` | 520 | 14/15 blocks | 0.3169% |
| DynamoRIO | `cargo build` | 501 | 15/15 blocks | 0.2062% |
| DynamoRIO | `cargo test --no-run` | 619 | 14/15 blocks | 0.2593% |

The Callgrind confirmation used six parent-first and six candidate-first pairs. Its 95% interval for the median reduction was 0.3033–0.3199%, with two-sided balanced randomization p = 0.00216. The DynamoRIO comparisons were paired within rotating multi-arm blocks. `pairs.csv` records the observed instruction counts, pair order and fresh unit count. All commands used `--locked --offline --message-format=json`.

For an independent Callgrind run, use `fresh.py` with `--mode check --design paired --pairs 12 --artifact-messages` and the default workspace. Use `--mode build` or `--mode test` for the other commands. [Build and reproduction instructions](../registry-manifests/)

The PGO DynamoRIO check saved 0.293% in 10/12 pairs (95% paired-median interval 0.260–0.315%, p = 0.01515). The two reversals are retained in the CSV. A separate plain-output full PGO check with Callgrind and child tracing saved 0.341% in 12/12 pairs (95% interval 0.322–0.357%, exact p = 0.00216). The latter used a freshly rebuilt control with identical machine code and asked Cargo for the artifact roster outside the scored commands. Reproduce it with the same harness, omitting `--artifact-messages` and using seed 572163. The PGO compiler inputs and component cohorts are in the [individual PGO evidence](../component-pgo/).
