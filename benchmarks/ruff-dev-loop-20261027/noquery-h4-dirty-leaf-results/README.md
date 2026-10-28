# Dirty Ruff library edits with the three release Cargo images

All 5,184 real Cargo commands used the registered 24-block sequence, with independent native qualification and 12 additional fresh control invocations. Each timed command applied or restored the real historical change to ruff_text_size. Every check and build recompiled the modified package. The Rust caller reported E0599 after removing the API and compiled successfully after restoring it. Every restored native caller printed 2-6. The source bytes, dep-info, native metadata and codegen checks passed in every slot.

The three arms used one release-profile PGO+BOLT driver and fixed-input PGO Cargo builds. B is the corrected release-source Cargo. P performs an explicit capability query, and N consumes the compiler-issued first-observation record. Each timed invocation ran without tracing. The independent native run counted one extra rustc on every dirty compile with P and none with B or N.

| Command | Pair | Control median (ms) | Subject median (ms) | Paired change (95% CI) | Mean delta (ms) | Two-sided exact P | Holm P |
|---|---|---:|---:|---:|---:|---:|---:|
| check | N vs B | 149.730 | 149.837 | -0.389% (-1.426 to +0.709) | -1.012 | 0.511312 | — |
| check | N vs P | 169.503 | 149.837 | -10.844% (-11.920 to -9.797) | -19.190 | 5.8309e-06 | 2.33236e-05 |
| check | P vs B | 149.730 | 169.503 | +11.727% (+10.498 to +12.964) | +18.178 | 5.8309e-06 | 2.33236e-05 |
| build | N vs B | 200.995 | 203.354 | +0.623% (-4.690 to +7.676) | +2.913 | 0.889516 | — |
| build | N vs P | 221.458 | 203.354 | -7.121% (-11.048 to -1.973) | -13.880 | 0.00865889 | 0.0117201 |
| build | P vs B | 200.995 | 221.458 | +8.337% (+3.423 to +13.411) | +16.793 | 0.00586006 | 0.0117201 |

The registered budget for N versus B requires the upper one-sided 97.5% bounds below both +3% and +5 ms in both endpoints. The additional sensitivity condition requires reproducibly slower build under P versus B and faster build under N versus P, using the Holm correction over four comparisons.

- Check upper bounds +0.709% and +2.012 ms (passes)
- Build upper bounds +7.676% and +26.351 ms (misses)

The no-query baseline-overhead guard failed. The registered build probe sensitivity passed.

Run python3 -IB verify.py to recompute every per-slot source and output check, all three-arm assignment tests, bootstraps and uncertainty intervals from wall.csv. The compressed per-command records retain actual process statuses, SHA-256 of each command stream, true rebuilt Cargo unit and individual output, Rust API and ordered object commitments. Whole private logs and all native caller bytes remain available on H4. [Registered schedule](https://github.com/astral-sh/ohm-cargo/tree/869cb9b4d76cf2864efaa32e60f60c31b7ac0969/benchmarks/ruff-dev-loop-20261027/noquery-dirty-leaf-h4-plan) · [Independent native admissions](https://github.com/astral-sh/ohm-cargo/tree/9ea6f62e8e3a96a49f9d80a62f516afd532602ce/benchmarks/ruff-dev-loop-20261027/noquery-dirty-leaf-h4-native) · [Exact PGO source and build attribution](https://github.com/astral-sh/ohm-cargo/tree/4fa4cc2e5f3256b57e5b6e7b1c70ce0d32456061/benchmarks/ruff-dev-loop-20261027/noquery-release-pgo-native-subjects)
