# Two Ruff implementation edits and the inputs of downstream native jobs

Reversing the complete Ty diagnostic and formatter comment changes in Ruff launched 5 and 8 real Wild processes in a full build. All those links read at least one file with different physical contents across edit and restore. In the two test builds we found no complete proof that any full compiler or linker could be omitted. This was an unscored first-occurrence search. It produced no timing claim or product change. [Pre-exposure plan and complete source patches](https://github.com/astral-sh/ohm-cargo/tree/336adc5250b156ebd5ac46c892513770e0546be8/benchmarks/ruff-dev-loop-20261027/nonparser-whole-inputs-plan)

| Real command | Full rustc | Cached rustc link | Wild | Wild with a differing opened input, edit vs restore | Different workspace ELF outputs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ty build | 12 | 0 | 5 | 5 of 5 | 5 of 15 |
| Formatter build | 3 | 6 | 8 | 8 of 8 | 8 of 15 |
| Ty test --no-run | 25 | 0 | 19 | 16 of 19 | 16 of 110 |
| Formatter test --no-run | 6 | 30 | 35 | 27 of 35 | 25 of 110 |

Every process count and ELF difference in the table occurred in both directions. Each immediate repeat issued zero compiler or linker processes and reported all 501 build or 619 test-build units fresh. SHA-256 covered all 922 or 1,060 declared regular files. The distinct Ty diagnostic appeared twice when reversed and once originally. Formatting changed the tabs after the comment marker in both a real Ruff CLI and an independently compiled ordinary Rust caller. Three new ordinary Ty metadata readers also compiled successfully. Cargo declared 6 or 102 executable paths. No test executable ran.

The subject was Ruff 93526150df, release PGO Cargo dd5cab15 from #254 and the PGO/BOLT rustc driver dec72d1e from #233. Both commands ran from genuine independent empty target, shared and registry homes on the same x86-64 Linux machine. The stock GCC driver, collect2 and bundled Wild, both compiler files, complete source patches, launch lines and product sets are bound by SHA-256. Build and test used separate stores and immediately restored the original sources. A kernel exec distinguished full rustc from both spellings of `-Z link-only`. Successful read-only descriptor digests, process ancestry and full Cargo artifact hashes supplied physical input witnesses. Compiler outputs in each unit's own output directory were excluded from its changed-input count. Reading a changed file alone does not show which differing byte influenced a compiler or linker output.

## Six formatter test links

The six nonempty integration tests were analyze_graph, direxist_guard, resolve_files, config, Ty cli and self_environment. Cargo already ran a cached Rust link in every case, and the six ELF file hashes held. Respectively 100, 77, 79, 76, 176 and 119 ordered native input arguments matched on captured contents. GCC-expanded Wild arguments still had three different temporary names per job, for the plugin resolution file, the raw-dylibs search directory and the actual symbols.o. Actual opens included system linker scripts and runtime objects beyond those explicit argument names. The kernel data did not authenticate every GCC/specs search, earlier nonexistent library choice, full environment or the linker's visible output side effects. This excludes treating the six equal ELF results as complete input certificates.

## Two Ty test compiles

The Ty cli and self_environment targets ran the full compiler after the Ty edit. Each recorded four upstream names as unused, opened none of those changed Rust archives, and produced the same final ELF bytes. They have 13 and two Rust source prerequisites. Their ordered native-file argument bytes agreed in all 176 and 119 positions, but the full producer generated 63 and 31 different CGU object names. With the three temporary names these yield 66 and 34 distinct argv slots.

For each target the archive contains a genuine physically observed Rust object and the two names used in these Ruff links. A small GNU script explicitly selects the first filename and the specified real object section. Stock GCC and Wild linked that input twice under the same recipe. The resulting executable exits 43 and 0 for Ty cli and 40 and 0 for self_environment. Supplying the unchanged script through an earlier library path gives the same outcomes. The small startup assembly stubs the unused external Rust references. The first no-stub attempt failed to resolve these references and is recorded in the separate pre-control directory. A second machine reproduced all eight results. This is a counterexample to retaining previous object names with arbitrary native scripts. The measured Ruff links did not supply this diagnostic script.

The remaining short Wild observations are one Linux ty_wasm integration target after the Ty edit, and two Linux wasm integration targets after the formatter edit. At least one live Wild observation was absent in each matched pair. The test sources disable their whole crates outside wasm32. These fall under an independent frontend reuse experiment that still invokes Wild. [Independent cfg-disabled test plan](https://github.com/astral-sh/ohm-cargo/tree/e7e1be37cde68e35e6c1adb8c3d78726917d2916/benchmarks/ruff-dev-loop-20261027/cfg-disabled-real-link-screen-plan)

## Separate initial warm-up

Cold full test-build, first unchanged repeat and the next unchanged repeat had 0, 563 and 619 fresh units respectively. Only ron 0.12.0 ran a full compiler on that first repeat, followed by 50 cached Rust links and 50 Wild links. The ron rlib, its metadata and two test ELFs changed. The next repeat had zero such jobs or file changes. The initial-test-freshness file includes the exact fields and a trace digest for all three initial commands. Its private registry hostname is redacted, and the raw receipt commitment is retained. The registered edit sequences started after this settled.

## Verification

Run `python3 verify.py` and `sha256sum -c SHA256SUMS` from this directory. On x86-64 Linux run `python3 replay-selector.py --wild-ld /path/to/qualified-sdk/lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld` to repeat the independent native counterexample with the packaged Wild hash checked first. Native source binding and strace capture for the original whole workspace are in the run directory. These scripts expect that dedicated Linux devbox layout, fresh isolated stores and a previously installed exact SDK. The selected files include native argv, successful exec digests, matched file hashes, missing live observations, renderer outputs and the actual two Rust codegen inputs used by the selector.
