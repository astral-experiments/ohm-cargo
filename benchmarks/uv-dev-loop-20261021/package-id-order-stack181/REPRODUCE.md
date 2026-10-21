# Reproduction

Verify `manifest.json`, then extract `ir-public-subset.tar.gz` into a new directory. `publication-subset.json` specifies every included member's hash, size and mode and every omitted original file. All sample JSON/JSONL/CSV files, the 56 full profiles and the accepted summaries are original bytes. The assembler verifies archive membership and all included bytes without running statistics. No retained fixture should be reused or overwritten.

To inspect the accepted arithmetic, use `accepted-analysis/{check,test}-reproduced-analysis.json` under `metrics.cargo_ir.statistics`, and compare each raw `samples.json` metric against its complete Callgrind profile. The unchanged reviewer and statistics source are in the archive under `controller/reviewer/`; the core runner is `benchmark/frozen/paired.py`. The frozen analysis CLI is:

```sh
python3 benchmark/frozen/paired.py analyze results/ir-check --confidence 0.99 --resamples 20000 --seed 1701 --minimum-pairs 12 --minimum-improvement 0.01
python3 benchmark/frozen/paired.py analyze results/ir-test --confidence 0.99 --resamples 20000 --seed 1701 --minimum-pairs 12 --minimum-improvement 0.01
```

Those commands write analysis outputs: use a new copy for independent reproduction, never overwrite the accepted archive. Only `metrics.cargo_ir` is the claimed metric. Instrumented elapsed time is not native time. The acceptance method applies linear quantiles to bootstrapped means of log ratios before exponentiation; use the retained method, not an alternative quantile transformation. The primary check gate requires a point reduction of at least 1%, a positive 99% lower bound, two-sided exact sign p <= 0.01, and both orders positive. Test requires its own full gate for a test improvement claim and did not meet the 1% threshold.

For a new machine comparison, build both source trees with the exact common inputs in `controller/cohort/production/provenance-local-package-id-order-stack181.json`, the frozen driver/manifest and both full patches. Keep Git HEAD at the shared embedded `5e5d271d763d7beb38b48755e22bd59e93f02b97` identity and apply the respective complete tree patches; use one physical source path and one target path sequentially. Compare the resulting trees to `c4178b67e0b3a64a12b9b58f84b97323b99d734e` and `12f12327e7c56fb04386b7cfb4d61d5fd434bfc5`. The incremental published patch is `source/candidate.diff`. Keep compiler, dependency lockfile, static features, ThinLTO, codegen units, release channel and stripping identical; this study did not use PGO.

Create a fresh owned fixture with unchanged uv commit `3d82a6ad5a7eab8c68236553b7846517767c4b61`, the hash-bound packaged Ohm 1.99.0-6 runtime and pinned Valgrind/debuginfo inputs. The archive's `metadata/setup.json`, base configurations, `prepare_host.py` and measurement seal record exact inputs. `reproduction/ohm-valgrind-env.c` is the common profiler-environment normalizer source. Rebuild or obtain its shared object and verify the recorded hash. Use the same explicit certificate paths and environment for both variants; retain absent loader/allocator variables as absent.

Use distinct target/shared directories for check and test, and one canonical regular Cargo executable pathname for both variants. Place the controller on CPU8 and workload subprocesses explicitly on CPUs0–7. Preserve the three fixed untimed warm commands per variant, then the strict traced zero compiler/build-script/test-execution proof and both cross-switch freshness checks before sampling. The archived IR preflight logs and reports show these checks for this cohort. Do not treat a failed preflight or occupancy guard as a measured zero.

The exact benchmark commands and environments are in `benchmark/ir-check.json` and `benchmark/ir-test.json`. They run `cargo -Zohm-defaults=yes check --locked --offline -j 8` and `cargo -Zohm-defaults=yes test --no-run --locked --offline -j 8` under Callgrind with `--trace-children=no`. After independently sealing a new local configuration and verifying preflight, the fixed runner interfaces are:

```sh
python3 benchmark/frozen/paired.py run --config benchmark/ir-check.json --output NEW_CHECK_DIRECTORY --phase confirmation --pairs 12 --warmup-pairs 2 --seed 20261021141
python3 benchmark/frozen/paired.py run --config benchmark/ir-test.json --output NEW_TEST_DIRECTORY --phase confirmation --pairs 12 --warmup-pairs 2 --seed 20261021142
```

Archive paths and input hashes refer to the original machine. A new fixture needs an explicitly recorded path/input mapping and new seals; do not silently reuse private approval receipts or remove guards to make old controllers run. The published subset deliberately omits operational process records, so the original full admission/collection reviewer requires those private inputs. Raw instruction arithmetic and source/build/workload reproduction remain available from this subset. Complete both fixed raw batches and verify integrity before effects; never pool with interrupted runs or extend a negative batch.

Native wall-time and regression verification are outstanding. The original native plan and failed-attempt hashes are retained for transparency; no native inference follows from the instruction results or from the interrupted attempt. Exact-source CI is complete and green in `ci/complete.json`; final artifact review and root qualification still precede draft publication.
