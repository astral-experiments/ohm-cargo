# Reusing unused-key diagnostics from cached registry manifests

Ohm Cargo `779889050ecdf73104225cd5e6fbd716f7e9b751` persists the set of unused TOML keys found by the original parser. On a warm read it deserializes the typed registry manifest and restores the set. The record digest covers the manifest and the keys. The new wire format uses its own cache directory, so the first visit to a registry manifest populates a new record.

| Whole Ruff command | Median parent instructions | Median with change | Paired reduction | 95% median interval |
| --- | ---: | ---: | ---: | ---: |
| Warm workspace `cargo check` | 921.27M | 910.58M | 1.159% | 1.142–1.175% |
| Workspace `cargo check` after a CLI source edit | 1,119.22M | 1,108.42M | 0.953% | 0.835–1.071% |

All 12 pairs improved on both primary commands. Each unadjusted two-sided exact randomization p-value is 0.002165. The Holm-adjusted p-value is 0.004329 for both. Intervals are distribution-free paired-median intervals. The fresh command emitted ordinary terminal output, with the 520 fresh artifacts verified separately. The edited command emitted Cargo JSON and counted the complete Cargo and rustc invocations. It replayed the seven-line CLI edit from Ruff `da8ee78491f784cdead4c69e83c58bc87fd0622c` and rebuilt exactly one of 520 units.

Both commands used Ruff `93526150df078af7dd8fc4226cdcc469539d2001`, Ohm Cargo base `461a3d1007ecc997a6d86c7d75e8b518575c8d90`, the Ohm 1.99.0-14 Linux x86-64 compiler and Cargo's release PGO data. The control executable SHA-256 is `211465de4b9e4589da2be06871acd9304dd3b94c849c1304f723484cb4f71dfc`. The exact final candidate is `081c0af7e60ece81b44723a9a608d7a71055e11f1f7031c03790345bcbf35212`. The cache-format tests also cover nested dependency warnings handled by Cargo's existing flattened maps. [Matched build recipe and training-data hash](../component-pgo/)

Both cache directories were primed before scoring. No qualified command waited for a package-cache lock. The 370 control records and 370 candidate records in the private edited checkout retained their inodes, lengths and nanosecond mtimes across the scored observations. The ordinary workspace cohort made the same check across its full cache directories. A first checkout with an incompatible tool-search path started compiling dependencies and was stopped before a successful pair. In an earlier fresh series one control check and one control build waited for a package-cache lock. In a separate initial edited series the candidate added one record for `dirs` in the first edit cycle. The complete initial series is retained in `excluded-pairs.csv` and excluded from qualification. Both pre-edit and edited states were warmed before the confirmation.

## Reproduction

Use a private Cargo home, a separate target for each checkout, a separate shared build directory and an available affinity mask. The target and shared state must be outside the output directory. `edited.py` creates the matched Rustup shim, warms the complete Ruff workspace, restores the pre-edit snapshot for each observation, traces Cargo and every child with Callgrind, and verifies the artifact roster. Pass a fresh output directory to create a new checkpoint. To replay an existing checkpoint, pass the original directory with `--state` and a new output directory.

```sh
python3 edited.py --parent "$PARENT" --candidate "$CANDIDATE" --toolchain "$OHM" \
  --ruff "$RUFF" --target "$TARGET" --shared "$SHARED" --output "$RUN" \
  --cpu "$CPUS" --pairs 12 --seed 837479
```

`fresh.py` repeats ordinary workspace commands using the already-warm runtime directory produced by the standalone fresh harness. It validates the full artifact roster, complete process roster, settled registry records and absence of lock waits. The seed is 897225 for check, 897226 for build and 897227 for test compilation. The independent plain replay in `fresh-verify.py` uses the state from the edited experiment and seed 897215. It additionally compares every emitted metadata and API file and the complete parsed Cargo metadata response. [Standalone fresh harness](../registry-manifests/fresh.py)
