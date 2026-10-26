# Packed dependency-edge traversal on Ruff edits

The two compilers differ only in how the incremental query graph decodes each node's packed edges. Both contain the empty-lint-scope change from Ohm Rust #230. Both use the same release 14 Cargo and Rust sysroot.

| Compiler | Ruff command | Counted | Parent median | Candidate median | Median paired reduction | Pairs improved | Exact p |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Release PGO+BOLT | `cargo check -p ruff_python_parser` | Cargo + rustc | 1.1167B | 1.1113B | 0.495% | 16/16 | 0.00781 |
| Release PGO+BOLT | `cargo build -p ruff_python_ast` | All rustc processes | 3.8690B | 3.8428B | 0.672% | 12/12 | 0.03125 |
| Release PGO+BOLT | `cargo test --no-run -p ruff_python_parser` | All rustc processes | 3.9276B | 3.9060B | 0.548% | 12/12 | 0.03125 |
| Release PGO+BOLT, second host | `cargo check -p ruff_python_parser` | rustc | 0.8327B | 0.8268B | 0.672% | 16/16 | 0.00781 |
| Release PGO+BOLT, second host | `cargo check -p ruff_python_ast` | rustc | 2.5560B | 2.5355B | 0.803% | 16/16 | 0.00781 |
| Stage 1 | `cargo check -p ruff_python_parser` | Cargo + rustc | 1.5586B | 1.5557B | 0.171% | 15/16 | 0.00781 |
| Stage 1 | `cargo check -p ruff_python_ast` | Cargo + rustc | 5.0201B | 5.0109B | 0.173% | 16/16 | 0.00781 |

## Workloads and measurements

Ruff is pinned to `93526150df078af7dd8fc4226cdcc469539d2001`. Each workload starts from an immutable, pre-edit target and shared build-directory snapshot. Before each measured process, copy the complete snapshot into an empty directory, replace the live store, apply the same source edit, and restore the same edit timestamp. A constant rustc executable and wrapper path select the parent or candidate driver. The measurement checks Cargo's exit status, the dirty artifact list, and the paired metadata/public API hashes.

For the parser edit, replace the single occurrence of `Invalid Syntax` with `Invalid syntax` in `crates/ruff_python_parser/src/lexer.rs`. For the AST edit, replace `A comparison has a left operand` with `a comparison has a left operand` in `crates/ruff_python_ast/src/nodes.rs`. Run each command with `cargo +ohm`, `--locked --offline`, and the default Ohm incremental flags. Use physically isolated sysroots and keep the Rustup and workspace paths stable between arms.

The complete checks instrument the Cargo parent and every child with Callgrind and require exactly one Cargo and one Rust compiler process. The release build and test-build cases use native Cargo and DynamoRIO around every compilation. The test-build executes three rustc commands for the parser library, its unit-test executable, and its fixtures. Native subprocesses, including the linker, run outside the instruction counter. The second host uses a separate archive, target and shared directory, private copies of the same compiler drivers, and a DynamoRIO counter for each crate's check. The test-build command uses `--no-run`.

The 16 pairs form eight independently randomized ABBA/BAAB blocks. The 12-pair build and test cases use six such blocks. `summary.json` includes the two-sided exact sign-flip test over the block log ratios and 95% block-bootstrap intervals for the geometric mean. `pairs.csv` contains every pair. `rosters.json` records output hashes and artifact coverage. Percentages report instructions saved.

The stage-2 builds use the same fixed Rust PGO and BOLT inputs. The final matched control and candidate were rebuilt from the same pinned bootstrap checkout and read-only base, and the matrix holds the release recipe, frontend, standard library, LLVM, and Cargo fixed. A preliminary build of the same parent from an older cache differed only in ELF build ID and the compiler's own metadata section. Its samples are excluded from this data.
