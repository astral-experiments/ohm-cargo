# Ruff build and test-build timings for Ohm Rust #233

Ruff was pinned to `93526150df078af7dd8fc4226cdcc469539d2001`. The candidate is the release PGO/BOLT compiler built from `27029b4bce40f3b5497add5019c02a11c16c4c18`. All compiler arms used the same Cargo binary. Each edit and command got twelve balanced pairs of ordinary untraced invocations, six in each order. The timer covers the complete command, including its rustup proxy, and test-build stops before executing any tests.

| Edit | Command | Control | Median seconds | Paired time reduction, 95% CI | Faster pairs | Holm p |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Private linter doc correction | build | Previous #233 | 12.81 → 11.06 | 14.3% [8.6, 20.1] | 11/12 | .0087 |
| Private linter doc correction | test --no-run | Previous #233 | 12.73 → 11.64 | 11.4% [1.5, 19.8] | 10/12 | .0303 |
| Parser diagnostic | build | #232 | 21.63 → 6.01 | 72.1% [69.7, 74.3] | 12/12 | .0087 |
| Parser diagnostic | test --no-run | #232 | 33.23 → 11.69 | 65.4% [61.3, 69.3] | 12/12 | .0087 |

The four p-values use an exact two-sided test over the 924 balanced assignments. Confidence intervals use a 20,000-draw paired bootstrap on log elapsed-time ratios. The unchanged commands immediately after the doc edit were registered as a separate two-comparison family. The build repeat went from 0.862 to 0.661 seconds (21.3% paired reduction, 95% CI 7.7% to 32.7%, adjusted p=.0346). The test-build repeat went from 0.657 to 0.744 seconds (−21.4% paired reduction, 95% CI −60.4% to 3.5%, adjusted p=.2208). Both registered comparison families are shown. [Original registration](https://github.com/astral-sh/ohm-cargo/blob/804c80a25fd2bbf29d7c48bc8327eda8bbfef493/benchmarks/ruff-dev-loop-20261027/native-observed-sources/plan.json)

Run `python3 -B reproduce-timings.py` in this directory to recalculate both families from the paired command receipts. The CSVs give the 96 individual edit timings. The receipt archive also contains the ordinary unchanged timings, unit freshness and independently collected process counts. The original source, index and benchmark process identification were checked at the end of each paired series.

These timings were exported after all 48 pairs completed. The later independent clean builds, CLI controls and archived physical process records are recorded separately when their qualification finishes. [Compiler head](https://github.com/astral-sh/ohm-rust/pull/233) · [Initial process traces](https://github.com/astral-sh/ohm-cargo/blob/c9a94a7dee3bea03b27e6cd0bf3d66cad130be1d/benchmarks/ruff-dev-loop-20261027/native-observed-sources/initial-screen.json)
