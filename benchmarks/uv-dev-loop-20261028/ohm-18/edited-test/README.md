# Cargo test build after an edit to uv on Ohm -18

The two checkouts used independently scheduled edits in `crates/uv/src/install_source.rs`. Each completed comparison measured the full workspace `cargo test --no-run --locked --offline -j8` with the matched Ohm -18 base and the original eight-patch stack. The two checkouts did not both clear the registered instruction thresholds.

The replica stopped in its first native baseline admission. Its normal uv executable had an unexpected raw SHA-256 before the candidate ran. A full comparison of both retained 316,713,312-byte baseline outputs found 33 changed bytes, the complete 32-byte GNU build ID and one byte in the ELF `.rodata.sh_entsize` field (0 or 8). Every other byte matched. The replica has zero scored observations. [Complete binary comparison](stock-comparison.json)

| Checkout and raw data | Paired median instruction saving | 99.22% median interval | Wins | Two-sided sign p | Balanced-order p |
|---|---:|---:|---:|---:|---:|
| [Initial](initial.zip) | 2.097% | 1.911% to 2.224% | 8/8 | 0.00781 | 0.02857 |
| [Replica](replica.zip) | Excluded before scoring | — | — | — | — |

Each scored invocation produced 72 test executables. The counter sums application instructions in Cargo, six rustc processes and five Wild processes, including their application threads. GCC, collect2, observers, pre-exec instructions and kernel work lie outside the count. Both arms used the distributed -18 rustc. The separate ordinary wall-time trials for the historical stack were inconclusive. [Elapsed-time trials](../full-toolchain-wall/) · [Paired instruction totals](pairs.csv)

Extract each linked archive into an empty directory and run `python3 -I -B replay.py`. The packets retain the per-command counts, selected edits, product checks, original schedules and scorer.
