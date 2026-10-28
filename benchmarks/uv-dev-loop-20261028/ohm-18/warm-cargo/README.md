# Warm Cargo driver instructions on Ohm 1.99.0-18

Two independently prepared, profile-guided Cargo builds ran each warm workspace command in 12 randomized pairs. The first checkout used DynamoRIO and the second used Cachegrind. Cargo rebuilt zero packages. For the test-build command it reported the same 72 test executables. The distributed compiler and linker had no build work in this comparison.

| Command | PGO + DynamoRIO | PGO + Cachegrind | ThinLTO without PGO + DynamoRIO |
|---|---:|---:|---:|
| `cargo check` | 2.30% (2.28–2.31%) | 2.31% (2.30–2.32%) | 2.29% (2.28–2.29%) |
| `cargo build` | 5.58% (5.56–5.59%) | 7.76% (7.75–7.77%) | 7.05% (7.03–7.06%) |
| `cargo test --no-run` | 2.48% (2.46–2.51%) | 2.53% (2.51–2.54%) | 2.40% (2.39–2.41%) |

Values are paired median reductions in Cargo-process instructions with a 96.14% distribution-free interval. All 12 pairs improved in each cell. The two-sided sign p-value was .00049 and the assignment-conditioned p-value was .00216. The magnitudes from the two different counters are reported separately.

The source-matched control and stack were independently trained on identical non-uv PGO workloads. The stack contains the five pending Cargo patches and Rust #247 in the Cargo executable. The linker is idle for these warm commands. The raw logs record either all per-thread dynamic instruction counts or the Cachegrind instruction references. Only separate edited-command trials can measure the time to recompile uv.

Extract `raw-and-scorer.zip` and run `python3 counter-report.py` to recompute the table on Python 3.11 or newer. The driver build commands, patches and PGO training receipts are in `driver-inputs.zip`. The complete local kit also includes the exact driver binaries.
