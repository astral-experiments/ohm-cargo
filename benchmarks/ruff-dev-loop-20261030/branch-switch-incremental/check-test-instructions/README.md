# Compiler instructions on Ruff branch returns

An ordinary Cargo return to Ruff PR #28335 compiled `ruff_python_ast` and `ruff_python_parser` on each side. Each ratio compares Rust #269 (7e71d315) with guarded checkout-aware incremental selection (6b7f424e) using the same #294 Cargo and stock Wild. The counts cover the two complete rustc processes and every compiler worker thread, including any backend codegen performed on that invocation. The measurements have no per-CGU attribution. Cargo, rustup, metadata consumers, native Wild and executable tests ran outside the instruction counter.

Each command had two balanced, independently empty installation pairs. A and B within each installation share its original training history. Each row divides the summed parent counts from the two pairs by the summed guarded counts. Both individual ratios and both integer totals remain in `four-ratios.tsv`. These eight paired observations describe compiler work on the two branch returns. Elapsed time and statistical inference are outside their scope.

| Workflow | Return A | Return B |
| --- | ---: | ---: |
| `cargo +ohm check -p ruff_python_parser` | 2.928568876× | 2.933643225× |
| `cargo +ohm test -p ruff_python_parser --lib --no-run` | 8.882492116× | 8.778725913× |

All 32 compiler argument vectors matched their normal native flanks byte for byte. The eight check returns launched zero linkers and emitted the real AST and parser metadata. A native rustc consumer accepted the expected 64- or 56-byte expression layout, and requiring the opposite layout produced E0308. Each of the eight test returns invoked one actual Wild, produced the same complete ELF as an independently empty build of that branch, listed exactly 245 tests and passed three selected tests. The standalone verifier rechecks raw stream commitments, tool identities, process counts, native outputs and the exclusion of eight startup-only fork logs. The separate raw receipt binds 3,226 files. Two earlier setup rejections and the two accepted first-pair check installations are documented in the original integrity-protected projection.

Run `python3 -IB verify.py` from this packet to verify the enclosed original projection and recalculate all four ratios. Run `python3 -IB portable/verify.py` for the two-crate counts for every return and installation.
