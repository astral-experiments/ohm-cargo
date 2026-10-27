# Private Ruff doc edit on the blocked #233 head

Reversing Ruff commit `36029f1c9a48690bc014c55007cf1ca69f479264` removes the two bytes `es` from a private doc comment in `ruff_linter`. Later lines and columns keep the same values. The shipped-profile #232 parent and #233 head used the same Cargo, rustc frontend and Wild. These discovery runs used different build histories and volumes in the two arms. Only the process and content comparisons are reported here. The paired timing protocol is in `plan.json`.

| Command | Full compiles, #232 → #233 | Link-only rustcs | Wild links |
| --- | ---: | ---: | ---: |
| Workspace build | 2 → 11 | 2 → 0 | 3 → 3 |
| Workspace test --no-run | 4 → 26 | 16 → 0 | 19 → 19 |

All 15 native build products match before and after the edit in each arm. Among the 110 test outputs, 107 matched byte-for-byte on #232 and 106 on #233. Raw differences in these initial test captures have not been attributed to particular ELF sections.

Each producer archive has 256 identical codegen-object bodies in matching slots across the change and the same ordered GNU symbol-to-member index. The native rlib public hash stays fixed on #232 and changes on #233. All 42,554 saved per-definition hashes stay the same on #232, and 32,195 of them change on #233. The global hash outside the definition graph stays fixed in both.

`discovery-receipts.tgz` contains the unit rosters, compiler/linker process counts and binary digests. The producer capture script, metadata receipts, decoded definition hashes, helper-span records and archive projections are included. The binary metadata and native archives are reproducible from the source capture script. The `small.py` experiment separates derive, ordinary macro and public opaque-return effects.

A second control run used fresh arm-specific targets and shared build directories on the same disk. It reproduced all four compile and link counts. All 15 build products matched byte for byte in both arms. Of 110 test products, 108 matched on #232 and 105 on #233. Every remaining pair had identical ELF section contents except for its GNU build ID, along with an entry-size difference in the read-only data section header. The independent raw runs are in `independent-controls-20261027.tgz`, with the section audit in `repeat-elf-section-check.json`.

Run `python3 decode.py path/to/ruff_linter.rmeta rules/ruff/helpers.rs` to read the producer's metadata using the pinned wire schema.
