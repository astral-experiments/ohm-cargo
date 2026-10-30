# Complete rustc instructions on a real Ruff Python version edit

Both directions met the registered threshold. This study compares the rustc parent with its one-file change that reads a span’s endpoints once when hashing native metadata locations. Both directions use the actual historical change to Ruff’s Python version defaults in an ordinary four-job package build. The instrumented process is the one dirty `ruff_python_ast` compiler. Its complete dynamic guest instructions include its compiler threads. This study has no wall-time or release-binary endpoint.

| Edit direction | Median parent Ir | Median child Ir | Paired reduction | 95% interval | Favorable | Exact two-sided p |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| forward | 7,662,943,700 | 7,619,949,362 | +0.5644% | +0.5082% to +0.5937% | 12/12 | 0.00216 |
| reverse | 7,663,366,887 | 7,621,955,397 | +0.5476% | +0.4891% to +0.5799% | 12/12 | 0.00216 |

The command was `cargo +ohm build --locked --offline -p ruff_python_ast -j 4 --message-format=json`. Each phase ran on one independent Linux host. Each direction had 12 fresh installation pairs with six parent-first. The 95% percentile interval uses 20,000 resamples stratified by actual order. The exact test enumerates all 924 allowed assignments. The two directional decisions remain independent. The native compiler and its stock linker ran normally during cold, repeat and independently empty correctness phases.

A cold build ran 39 full Rust compiler processes and eight stock linkers. The production edit ran one full compiler and zero linkers. Immediate repeats ran neither. One unchanged downstream reader linked the actual Cargo library, changed runtime answers from `3.14 3.14 3.10` to `3.15 3.15 3.11`, and reproduced the independently clean executable exactly in both directions and arms. Raw Cargo libraries and metadata varied across independent builds, including within the same compiler arm. The exact files and complete native reader digests are recorded separately.

To verify the projection offline, run `python3 -IB verify-projection.py`. It reopens the local SHA-256 manifest, checks all 48 native and counter commitments, reconstructs the prospective schedule and independently recomputes both paired intervals and p-values. The raw private archive holds complete Callgrind output, kernel argv/FD evidence and native logs for every registered run. The two measured compiler images are bound by full source, SDK and compiler construction receipts. The measured optimized stage1 compiler builds did not use distribution PGO or BOLT. This 39-unit build covers one real edit to an individual Ruff crate.
