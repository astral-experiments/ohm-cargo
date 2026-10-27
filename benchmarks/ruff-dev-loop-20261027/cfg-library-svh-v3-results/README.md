# Same-source crate identity in Ruff's ty_ide

The candidate compiler produced the same private crate identity for an independently built and an incrementally rebuilt copy of the same edited Ruff source. Newly compiled ordinary Rust callers could load a bridge built against either copy. Both blocks reproduced the prior compiler's private-identity mismatch and compiler error E0460 in the two crossed combinations. The cases and both block orders were registered before running V3. [Registered plan](https://github.com/astral-sh/ohm-cargo/tree/a0b1a5a9892135ced845ba085de6bb096dd4019e/benchmarks/ruff-dev-loop-20261027/cfg-library-svh-v3-plan)

Ruff 93526150df is the starting tree. Reversing complete historical commit 1797ed5423 reinstates a 78-line test inside an existing cfg(test) module in crates/ty_ide/src/docstring.rs. The prior whole-workspace run supplied the native production crate command. These observations replay that command with the original 44 sources, 29 explicit Rust extern files, Cargo package environment, compiler frontend and logical paths. Each block starts each image from independent empty incremental and output directories. A second, independent empty build supplies each comparison. [Prior Cargo workspace and source results](https://github.com/astral-sh/ohm-cargo/tree/ffeaa8dd1b9a8a5d4acd6c25bf66ff09e4e001fe/benchmarks/ruff-dev-loop-20261027/cfg-test-only-library-edit-results)

| Block and compiler | Edited private ID, warm / empty | Restored private ID / independent original | New ordinary callers accepted |
| --- | --- | --- | --- |
| 1, #233 | a7432d33 / f917b38c | 57191ced / 5f16b3d2 | 2/4 |
| 1, V3 | f917b38c / f917b38c | 5f16b3d2 / 5f16b3d2 | 4/4 |
| 2, V3 | f917b38c / f917b38c | 5f16b3d2 / 5f16b3d2 | 4/4 |
| 2, #233 | a7432d33 / f917b38c | 57191ced / 5f16b3d2 | 2/4 |

The ordinary bridge used ty_ide::Completion and compiled against the selected edited producer without reduced-identity mode. Each fresh caller compiled with an explicitly selected bridge and a search directory excluding alternative copies of ty_ide. Every same-history caller compiled. All four crossed #233 calls exited 1 with E0460. All four crossed V3 calls exited 0. These callers emitted Rust metadata only. The eight bridges also exited 0. The native producer returned 0 in all 20 captures and every image retained public ID f321b448bc54bd2819e1fe053541ce11.

## Raw bytes

SHA-256 prefixes below show the actual edited outputs, warm / independent empty. Each archive member comparison found 171/171 complete corresponding codegen object payloads equal and 0/171 member names equal. lib.rmeta, lib.rmeta-link and the archive name table differed. The archive symbol index bytes matched in all four comparisons.

| Block and compiler | .rmeta, warm / empty | .rlib, warm / empty |
| --- | --- | --- |
| 1, #233 | 1220832994fa / 45d8733b908c | 0b7bd6c45a65 / 28816056d106 |
| 1, V3 | 445f6778f91a / 3caa2bc437d8 | 21bb118d85af / 3eed22d68337 |
| 2, V3 | 445f6778f91a / 15828d8c3137 | 0c967d552924 / ff774fd0f38c |
| 2, #233 | 442fbd23df67 / 2fb64c134c95 | 5516c3533aa9 / 4cf1998afae4 |

After restoration, V3's raw .rmeta matched the independent original in block 1 and differed in block 2. The corresponding private IDs matched in both. Both #233 restored .rmeta comparisons differed, as did all four restored .rlib comparisons. Even two independently empty original compilations could produce different raw .rmeta with the same private ID. The private compatibility fix therefore coexists with observed byte variation. This holdout covers the two source/hygiene repairs together. It does not separate their individual contributions or measure elapsed time.

## Rechecking the observations

Run `sha256sum -c SHA256SUMS`, `python3 verify.py` and `python3 summarize.py` from the extracted directory. The first Python script checks the 20 recorded native exec identities, source and dependency digests, compiler credentials, and all 16 ordinary caller statuses. The second independently reads the four enclosed block-1 edited metadata source-map entries against the complete edited source. Each contains its current source checksum, length 52,874 and all 1,744 line starts. Its JSON contains complete artifact hashes for all 20 native compilers and each ordinary compile result. The runner retained per-invocation decoded source-map and archive receipts on both blocks.

The binding directory contains the input manifest, precise argv, both source versions, stage-2 driver copy receipt and release digests. The run directory contains the original host-specific replay and archive decoder. The frozen replay used the H2 Ruff checkout and dependency corpus identified in the earlier study. Each block directory retains producer stderr, physical exec traces, ordinary caller results and the complete archive comparison.
