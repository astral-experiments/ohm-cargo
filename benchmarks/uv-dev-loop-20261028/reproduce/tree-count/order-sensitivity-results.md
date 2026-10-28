# Seven-change role instructions with assignment-conditioned p-values

This separate diagnostic conditions on the frozen balance of baseline-first and candidate-first pairs. It compares the absolute observed candidate wins minus losses with all assignments under the sharp no-effect null. Original sign/rank gates are reported in the main study.

| Command | Cohort | Wins minus losses | At least as extreme | Total allocations | Two-sided conditional p |
| --- | --- | ---: | ---: | ---: | ---: |
| `cargo check` | initial | 8 | 2 | 70 | 0.028571429 |
| `cargo check` | replica | 8 | 2 | 70 | 0.028571429 |
| `cargo check` | stratified | 16 | 2 | 4,900 | 0.00040816327 |
| `cargo build` | initial | 8 | 2 | 70 | 0.028571429 |
| `cargo build` | replica | 8 | 2 | 70 | 0.028571429 |
| `cargo build` | stratified | 16 | 2 | 4,900 | 0.00040816327 |
| `cargo test --no-run` | initial | 8 | 2 | 70 | 0.028571429 |
| `cargo test --no-run` | replica | 8 | 2 | 70 | 0.028571429 |
| `cargo test --no-run` | stratified | 16 | 2 | 4,900 | 0.00040816327 |
