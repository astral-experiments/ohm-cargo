# Reusing checksum prefetch miss counts

The base is Ohm Cargo `461a3d1007ecc997a6d86c7d75e8b518575c8d90`. The candidate is `37e0a7083fbf535fb8f5a41d4f1bb12303676dd8` on `astral-sh/ohm-cargo`. Ruff is pinned to `93526150df078af7dd8fc4226cdcc469539d2001`. All four Cargo subjects used the release PGO profile for x86-64 Linux Ohm 1.99.0-14. A separate clean rebuild reproduced the standalone control’s `.text` and `.rodata` byte for byte.

| Comparison | Default Ruff command | Fresh units | Lower instruction count | Median paired reduction | 95% median interval | Exact p |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Release base vs this change | `cargo check` | 520 | 12/12 | 1.1019% | 1.0958–1.1109% | 0.00216 |
| Six Cargo changes vs six plus this change | `cargo check` | 520 | 12/12 | 0.4755% | 0.4582–0.4804% | 0.00216 |
| Release base vs this change | `cargo build` | 501 | 12/12 | 0.6918% | 0.6818–0.6992% | 0.00216 |
| Release base vs this change | `cargo test --no-run` | 619 | 12/12 | 0.9877% | 0.9620–0.9936% | 0.00216 |

Both predeclared check comparisons used Callgrind 3.22.0 with child tracing and plain output, `--locked --offline`, six Cargo jobs and affinity 4–7 on an AMD EPYC-Milan host. Each had six base-first and six candidate-first pairs and an independently randomized schedule. Both Holm-adjusted p-values are 0.00433. We verified the identical full artifact roster with Cargo JSON before and after each scored cohort. The supplemental full build and test-compilation comparisons used separate 12-pair schedules and the same roster checks. Both Holm-adjusted p-values are 0.00433 within this second family. Only Cargo ran in every scored profile. The source change reduces path hashing directly. Binary code generation and the other six changes also affect the whole-command result, so the two reductions are reported separately.

Use the public `fresh.py` harness with `--mode check --design paired --pairs 12`, ordinary terminal output, and a distinct output and target directory for each Ruff checkout. The standalone check seed is 753841. For the supplemental comparisons, specify `--mode build` with seed 895223 or `--mode test` with seed 618731. The test mode compiles with `--no-run`. For the incremental comparison, apply `six.patch` to both source trees before applying this change to the candidate, then use seed 238659. [Harness and build instructions](../registry-manifests/) · [Release PGO recipe and training inputs](../component-pgo/) · [Six-change patch](../cargo-stack/six.patch)

A two-pair pilot is excluded. A separate incremental run was rejected when a simultaneous historical edit recompiled `ruff_linter` in its eighth block. We discarded the whole run and replayed its original 12-block schedule on another dedicated, clean Ruff worktree. The standalone cohort had completed its final roster check before the historical edit started.
