# Edited uv instruction sums

The sum covers Cargo, every released-rustc invocation, and every Wild invocation, including their threads. Both arms compile uv with the released Ohm rustc and use Wild `--no-fork`. The kernel, wrappers, `cc`, `collect2` and unwrapped forked work are outside the sum. Each pair changes a private same-length literal. No tests run.

| Cargo command | Cohort | Pairs | Baseline G instructions | Candidate G instructions | Median paired reduction [rank interval] | Improved | Exact sign p | Gate |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | --- |
| `cargo check` | Initial | 8 | 4.754 | 4.728 | 0.547% [0.518%, 0.579%] | 8/8 | 0.0078125 | passed |
| `cargo check` | Independent repeat | 8 | 4.755 | 4.730 | 0.537% [0.527%, 0.569%] | 8/8 | 0.0078125 | passed |
| `cargo build` | Initial | 8 | 14.848 | 14.691 | 1.053% [0.933%, 1.074%] | 8/8 | 0.0078125 | passed |
| `cargo build` | Independent repeat | 8 | 14.886 | 14.705 | 1.108% [0.989%, 1.330%] | 8/8 | 0.0078125 | passed |
| `cargo test --no-run` | Initial | 8 | 28.313 | 28.165 | 0.523% [0.463%, 0.539%] | 8/8 | 0.0078125 | passed |
| `cargo test --no-run` | Independent repeat | 8 | 28.347 | 28.179 | 0.527% [0.466%, 0.729%] | 8/8 | 0.0078125 | passed |

The min–max rank interval has 99.22% coverage for a continuous median at eight pairs. Sign tests exclude ties. A repeatable direction requires a positive median and two-sided p < .05/3 in the initial cohort, then a positive median and p < .05 in a separate, fresh cohort. Only initially passing endpoints qualify for the repeat.

## Baseline instruction shares

Each percentage is the median of baseline role / baseline total across the eight source edits. Parentheses show the separate baseline and candidate median role counts in billions. Medians are computed independently.

| Command | Cohort | Cargo | rustc | Wild |
| --- | --- | ---: | ---: | ---: |
| `cargo check` | Initial | 18.34% (0.872 → 0.846 G) | 81.66% (3.882 → 3.882 G) | 0.00% (0.000 → 0.000 G) |
| `cargo check` | Independent repeat | 18.37% (0.874 → 0.847 G) | 81.63% (3.882 → 3.882 G) | 0.00% (0.000 → 0.000 G) |
| `cargo build` | Initial | 6.85% (1.017 → 0.937 G) | 47.30% (7.023 → 7.023 G) | 45.85% (6.808 → 6.731 G) |
| `cargo build` | Independent repeat | 6.96% (1.036 → 0.948 G) | 47.19% (7.024 → 7.024 G) | 45.84% (6.809 → 6.731 G) |
| `cargo test --no-run` | Initial | 5.77% (1.633 → 1.593 G) | 51.24% (14.506 → 14.507 G) | 42.99% (12.172 → 12.063 G) |
| `cargo test --no-run` | Independent repeat | 5.82% (1.649 → 1.607 G) | 51.18% (14.507 → 14.505 G) | 43.01% (12.177 → 12.068 G) |

## Workload admission

The live jobserver may distribute worker threads differently across matching link outputs. All observed threads contribute to each linker count. The frozen admission gate checks which compiler and linker work the command invoked.

**cargo check initial.** Verified 1 rustc invocations (uv (lib)), 0 Wild invocations (none), and 0 test executables.

**cargo check independent repeat.** Verified 1 rustc invocations (uv (lib)), 0 Wild invocations (none), and 0 test executables.

**cargo build initial.** Verified 3 rustc invocations (uv (bin), uv (lib), uvx (bin)), 2 Wild invocations (uv, uvx), and 0 test executables.

**cargo build independent repeat.** Verified 3 rustc invocations (uv (bin), uv (lib), uvx (bin)), 2 Wild invocations (uv, uvx), and 0 test executables.

**cargo test --no-run initial.** Verified 6 rustc invocations (uv (bin), uv (lib), uvx (bin), uv (test), uv (test), uvx (test)), 5 Wild invocations (uvx-141090d4fffe584e, uv-23905aefc33b1c4d, uv, uvx, uv-c84366b26c530121), and 72 test executables.

**cargo test --no-run independent repeat.** Verified 6 rustc invocations (uv (bin), uv (lib), uvx (bin), uv (test), uv (test), uvx (test)), 5 Wild invocations (uvx-141090d4fffe584e, uv-23905aefc33b1c4d, uv, uvx, uv-c84366b26c530121), and 72 test executables.

The rejected first pilot compared the structural check edit, which compiled three targets, with a later literal change, which compiled only the library. It contributes no samples. Each subsequent cohort freezes the exact compiler and linker roster from four identical-state native/count admission cells, then checks it on every held-out observation.
