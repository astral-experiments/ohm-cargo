# Cargo stack on the held-out Ruff server edit

This plan predates measurements of the combined candidate. The independent historical input is the sealed CLI/workspace holdout `fca5c7cf2cd2f8338f18b9485f936b8e9f07bd0b`. It corrects a duplicated word in a doc comment on `ClientOptions` in `ruff_server`. Apply its full original patch in reverse to Ruff `93526150df078af7dd8fc4226cdcc469539d2001`. This adds a workspace check to the historical workload set. [Edit selection](../entropy-corpus/)

The three Cargo subjects are the PGO control built from `461a3d1007ecc997a6d86c7d75e8b518575c8d90`, the first seven draft changes, and those seven plus the winner of the independent Git-index proof comparison. Include the registry diagnostic-key change in the last subject only if it passes both individual full-check measurements (already built and edited CLI) with an adjusted p-value below 0.05. No scheduling or compiler changes enter this experiment. All arms use the same absolute toolchain path, compiler, data, build options, and 32-vCPU host.

Run ordinary `cargo +ohm check --locked --offline` without JSON in the measured command. Restore identical pre-edit target and shared directories. Collect complete userspace instructions from Cargo and every compiler or other child with Callgrind. Repeat all six permutations of the three arms twice, then shuffle these 12 blocks using seed 946137. Validate that the rebuilt crate roster, full artifact roster, metadata bytes, and public API hashes match. Record every observation. A changed output or an unexpected compilation disqualifies the comparison.

The primary comparison is the extra savings over seven. Also report total savings against the PGO control. Test paired differences by exchanging the two compared labels conditional on the rank of the third arm and on the balanced order counts. Apply Holm to these two tests. Report distribution-free 95% median intervals for the two reductions. No elapsed-time claim follows from instruction counts.

Separately measure ordinary fresh `cargo check`, `cargo build`, and `cargo test --no-run` against the same control, using 12 independently balanced pairs per command, seeds 946271 through 946273. Warm both cache formats before scoring. Report the per-mode artifact counts, both medians, individual intervals, and the three Holm-adjusted p-values. Native elapsed measurements, if available, will be reported separately.

## Warm workspace commands

These results use the exact nine-draft Cargo binary `3f5223265e4f51af56ecc1ef8737a2d2744b21faf6c3168a28012b9eba1ccb60`. Each invocation completed with ordinary output. A separate check before and after scoring verified the entire fresh target roster. The timed process tree contained just Cargo. The hashes and metadata of the 410 records in each private registry cache stayed fixed. The single verified Git-index record predated the first scored run and retained its inode, timestamp, size and bytes.

| Ruff command | Fresh artifacts | Median control instructions | Median with nine drafts | Median paired reduction | 95% interval |
| --- | ---: | ---: | ---: | ---: | ---: |
| `cargo check` | 520 | 920.69M | 823.86M | 10.522% | 10.512–10.526% |
| `cargo build` | 501 | 1,484.67M | 1,387.68M | 6.533% | 6.521–6.548% |
| `cargo test --no-run` | 619 | 1,114.97M | 1,015.41M | 8.927% | 8.911–8.936% |

All 12 pairs improved for each command. The two-sided exact order-balanced p-value was 0.002165 per command and the three-way Holm-adjusted value was 0.006494. [36 randomized pairs](fresh-pairs.csv), [confidence intervals and cache checks](fresh-summary.json), [combined source patch](nine.patch)

For a clean reproduction, use the [standalone fresh harness](../registry-manifests/fresh.py) to create the stable Cargo executable shim, warmed target and separate build directory. Use a private Cargo home with trusted ancestors. Run the two control/treatment binaries through `fresh.py --mode all --sequence check build test --design paired --pairs 12 --seed 946271` using the same absolute tool-search path for all invocations.
