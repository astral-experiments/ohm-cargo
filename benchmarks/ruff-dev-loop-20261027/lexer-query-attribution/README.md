# Which Ruff compilers recorded the moved lexer location?

Ruff's pinned source was 93526150df. The complete first reverse of 6e29838d removed three lines from lexer.rs. Both production compiler arms passed the full build and test freshness checks and their actual Rust jobs were captured. B is #232 at driver SHA-256 051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518. C is corrected #233 at dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f. Both use #254 Cargo dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1. This packet describes query evidence from the first edit and its restoration. It contains no timed comparison.

## What changed in the graphs

| Actual first-occurrence command in each arm | Full rustcs | Producer jobs | Explicit parser externs | Other downstream jobs | Recorded parser public-hash query | Changed module-child query | Downstream `Metadata` nodes directly consuming parser public hash |
|---|---:|---:|---:|---:|---:|---:|---:|
| `cargo build` | 35 | 1 | 15 | 19 | 34 | 3 | 28 |
| `cargo test --no-run` | 93 | 2 | 54 | 37 | 82 | 5 | 27 |
 
The three build jobs were the `ruff`, `ruff_server` and `ruff_wasm` libraries. The separate Ruff CLI binary had no lexer-module query. The test added the Ruff library and server unit-test harnesses. Both compiler arms recorded the same counts and names. None of the downstream jobs recorded an individual `def_span(lex)`, `def_ident_span(lex)` or any other query keyed to the specific function. Among the 28 external build and 27 external test metadata files on each arm, neither the definition-span nor definition-identifier-span table contained any encoded location owned by the parser's lexer.rs. The parser's own tables contain both verified locations.

All five test jobs in both compiler arms changed the module result while the outer `visible_parent_map` fingerprint stayed identical across edit and restoration. The recovered #233 build restorations of the Ruff and server libraries also preserved the outer map. The other four build-restoration sessions had been collected before the extra outer-reader pass. The first-edit fingerprints and primary module-query restoration values for all six build cases are available.

Independent file readback verified 256 first-edit graphs and 114 compiler metadata files, totaling 7,574,324,290 bytes across both compiler arms.

Rustc keyed the crate-wide `public_api_hash` by the producer’s stable crate ID. Its per-item key for `ruff_python_parser::lexer::lex` uses that ID and the definition’s local DefPathHash. The two halves differ under the build and test profiles because Cargo passed different `-Cmetadata` values. The parser’s own test-harness target has its own crate ID and the scanner used its own keys.

Across twelve actual build and test producer snapshots the declared children were `lex` and `Lexer`, both public with no reexports. The identifier for `lex` moved from bytes [60314,60317) to [60126,60129) and back, with unchanged source ordinal 4, syntax context, item identity and kind. `Lexer` remained at [1243,1248). The retained test metadata independently produced the external E0061 definition note at 1623:8, 1620:8 and 1623:8 while the ordinary caller's own main diagnostic stayed fixed. 

The external `module_children` provider materializes each child's identifier through `opt_item_ident`, reading the physical `def_ident_span` table directly. The graph need not contain an individual `def_ident_span(lex)` node. In the affected Ruff graphs the sole recorded direct reader of that module query was `visible_parent_map(())`. It traverses public identities, child names, reexports and doc-hidden status, and examines `child.ident.name` for underscore reexports. Its result maps definition IDs to parent IDs. The complete per-unit fingerprints appear in the immediate-reader receipts. [Module child decoding](https://github.com/astral-sh/ohm-rust/blob/27029b4bce40f3b5497add5019c02a11c16c4c18/compiler/rustc_metadata/src/rmeta/decoder.rs), [visible parent provider](https://github.com/astral-sh/ohm-rust/blob/27029b4bce40f3b5497add5019c02a11c16c4c18/compiler/rustc_metadata/src/rmeta/decoder/cstore_impl.rs).

H5 copied the finalized graph for each original process before restoration, using its actual `-Cmetadata`, executable/library selection and rustc version to derive its directory. The session timestamp had to fall within the original Cargo invocation. Each copy came from an unchanged regular FD into a separate device/inode and its physical SHA-256 was reverified after capture. Source SHA and the succeeding 501/619-unit fully fresh invocation fence each set. The query code numbering for the compiler revision that wrote each graph is used in the reported rows. #233 adds one checksum query, shifting later numbers.

A serialized graph can contain green nodes inherited from earlier runs. The presence of a node alone does not establish that its provider executed during the first edit. Differing first-edit/restoration result fingerprints establish a difference in the recorded query value. Untracked reads, keys hashed from multiple values, inline MIR, macros and debuginfo require separate probes. This measurement records graph structure and fingerprints. The declaration table scan is restricted to `def_span` and `def_ident_span`. An ordinary new caller can still display the moved definition.

The earlier independent H2 study had already run five more edits and restorations. The real first lexer sessions were absent in every one of its four arm/mode inventories. H2's retrospective B-arm projection is labeled with the actual retained generation for each unit. H5 provides the genuine first-edit graph observations.

## Bounded full-compiler opportunity

On the prior independently captured H2 B-arm test, nine terminal jobs lacked any graph key beginning with the regular parser crate ID. Six had passed the parser explicitly as an extern. All nine actual Wild link argument lists contained zero rlibs that the single edited Cargo command reported changed; each final ELF was byte-identical before/edit/restore. For seven, the saved Cargo manifest lists every changed direct Rust extern as unused and none is reachable from another potentially used root in the pinned Cargo unit graph. The two wasm API harnesses lacked an unused-extern proof. All seven remaining paths have one ordinary executable-order dependency and exclusive native build-script output. All seven unused dependency subgraphs contain the psm and zstd-sys build scripts, and six contain tikv-jemalloc-sys. The real Cargo outputs record a static library and a search path for each.

Keeping Cargo’s existing rule that rejects exclusive native search paths or link directives leaves zero admissible terminal cases. A future terminal-only rule could at most replace seven of 93 full frontend jobs with ordinary link-only on this test edit and zero of 35 on build. It would have to start from a validated prior link recipe, prove the used Rust and proc-macro closure is unchanged, wait for the binary dependencies, recheck tracked files and environment after they finish, and verify that the effective ordered link directives and their origin still match the cached recipe. The native linker would still run and resolve current archives, search-order shadowing, scripts and outputs normally. An older one-pass preflight can miss an `include_bytes!` of a just rebuilt Cargo binary. The bare unused-extern proof also did not protect a changed libauditffi.a in the prior 41→83 falsifier. Neither number is a measured saving. A broader regular-library shortcut would have to rebind `CrateDep` identity, preserve prior diagnostics and prove all serialized external inputs, not merely split the module query. Here, the concrete whole-crate dependency edge remains in the metadata writer.

## Independent verification

The two C files use the matched serialized graph footer, packed edge widths, node indices, DefPathHash key and value fingerprint. The counts of all serialized nodes and edges are verified. To scan a saved build graph with #233 as writer, compile the readers and run the following in the code directory.

```sh
cc -O2 -o query-graph query-graph.c
cc -O2 -o module-parents module-parents.c
python3 read-one.py /path/to/dep-graph.bin 5f1187e22819f3d5 --writer C --binary ./query-graph --incoming-binary ./module-parents
```

The regular test parser ID is `7313ccaf87a445db`. Per-case capture manifests include each immutable file digest, selected source state and raw process trace digest. SHA256SUMS covers the public packet. Larger original graphs reside on the separate witness volume. Every missed outer-reader restoration is listed explicitly.

The first-occurrence inputs and run order were recorded before execution. [H5 compiler-only plan](https://github.com/astral-sh/ohm-cargo/tree/d8d5011852778f8babeb4e5c3cb0613c6793ca6c/benchmarks/ruff-dev-loop-20261027/pr233-three-parser-edits-plan), [H5 runner](https://github.com/astral-sh/ohm-cargo/tree/39eaf6a145d10d7e018a7247d6858a1830002adb/benchmarks/ruff-dev-loop-20261027/pr233-three-parser-runner-v2), [independent H2 cohort plan](https://github.com/astral-sh/ohm-cargo/tree/7ef4e84e3838cabd8e713fcadef6347a67f9fc00/benchmarks/ruff-dev-loop-20261027/first-occurrence-parser-plan).

Run `python3 -B verify.py` from the downloaded packet to regenerate the four reported summaries in memory and check them against every saved unit and reader record.
