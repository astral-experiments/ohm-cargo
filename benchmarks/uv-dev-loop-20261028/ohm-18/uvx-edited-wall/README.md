# Editing the uvx diagnostic with the historical Ohm stack

Two separately warmed uv checkouts changed the diagnostic printed when uvx cannot launch uv. Each block applied the same edit to distributed Ohm -18, a matched Cargo and Wild rebuild, and the historical eight changes. All three used released rustc and target std. The standard-library patch was compiled into Cargo on the historical arm.

The historical stack missed its registered primary build criterion against both controls on both checkouts. The check and test-compilation results are descriptive under the registered test order.

| Checkout | Command | Control | Paired median saving | Median interval | Wins | Sign / order p |
|---|---|---|---:|---|---:|---:|
| Initial | `cargo check` | Matched rebuild | +2.32% | +0.20% to +6.97% (95.72%) | 21/30 | 0.0428 / 0.0499 |
| Initial | `cargo check` | Distributed -18 | -0.64% | -3.93% to +2.57% (95.72%) | 13/30 | 0.5847 / 0.7046 |
| Initial | `cargo build` | Matched rebuild | +1.86% | +0.49% to +19.40% (95.72%) | 21/30 | 0.0428 / 0.0582 |
| Initial | `cargo build` | Distributed -18 | +3.42% | -0.31% to +12.10% (95.72%) | 20/30 | 0.0987 / 0.1468 |
| Initial | `cargo test --no-run` | Matched rebuild | -2.65% | -23.12% to +0.48% (95.72%) | 11/30 | 0.2005 / 0.2746 |
| Initial | `cargo test --no-run` | Distributed -18 | -0.93% | -26.78% to +0.99% (95.72%) | 14/30 | 0.8555 / 1.0000 |
| Replica | `cargo check` | Matched rebuild | +1.60% | -2.21% to +3.31% (95.72%) | 19/30 | 0.2005 / 0.2606 |
| Replica | `cargo check` | Distributed -18 | +1.87% | +0.01% to +7.21% (95.72%) | 21/30 | 0.0428 / 0.0582 |
| Replica | `cargo build` | Matched rebuild | +2.64% | -4.27% to +8.39% (95.72%) | 18/30 | 0.3616 / 0.4765 |
| Replica | `cargo build` | Distributed -18 | +3.89% | +2.02% to +9.00% (95.72%) | 22/30 | 0.0161 / 0.0163 |
| Replica | `cargo test --no-run` | Matched rebuild | +0.42% | -4.83% to +26.63% (95.72%) | 16/30 | 0.8555 / 1.0000 |
| Replica | `cargo test --no-run` | Distributed -18 | +1.86% | -6.81% to +5.87% (95.72%) | 17/30 | 0.5847 / 0.7046 |

Shipped Ohm invoked Wild for both the uvx program and its test harness. The 1,068,096-byte harness had the same raw SHA-256 at admission and postflight on both checkouts. Comparing its transient linker inputs requires a separate capture.

Every timed test-compilation command prepared the same 72 test executables. No uv tests ran.

[540 wall times](samples.csv) · [Paired comparisons](numeric-results.json) · [Process and artifact checks](audit.json) · [Original receipts, assignments and standalone scorer](observations.zip)

To repeat the numerical and product audit from a fresh directory, run

```sh
unzip observations.zip
python3 -I -B protocol/rescore-edited-native.py . r18-uvx
```
