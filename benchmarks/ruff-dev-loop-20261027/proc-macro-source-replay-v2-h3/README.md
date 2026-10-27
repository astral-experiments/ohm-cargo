# Procedural macro source replay, second prototype

The release-matched compiler in this packet restores a procedural macro’s virtual source files after rustc accepts a cached expansion. All 24 ordinary downstream Rust callers for parsed strings, programmatically constructed tokens and defaults-off controls reproduced the clean program and raw producer metadata. A changed on-disk asset, parsed before the macro registered its dependency, also produced the correct new value. The independent changed-file controls for the previous prototype explain the difference. [Previous prototype and inherited controls](../proc-macro-changed-file-replay1/)

This prototype still miscompiles an empty derive followed by a different macro that embeds the debug form of its server’s call-site or mixed-site span. Neither macro parses a Rust token stream from a string. Both crossed callers fail with E0460 for each of those two accessors. The root-span and defaults-off cases accept all callers. The same program’s absolute byte endpoints stay fixed across histories while its syntax context changes. The shipping compiler had both defects. [Released compiler control for virtual sources](../shipped-15-proc-macro-span/)

## Ruff

Four ordinary, full-workspace `cargo +ohm build --locked --offline --message-format=json` commands used the unchanged Ruff project at the pinned commit and a true three-file historical reverse edit. Of 501 artifacts, all 501 were fresh on the repeat. Both following build states began from inode-independent copies of that completed original state. The empty comparator removed only the parser’s own incremental directory before applying the same source edit. The actual calibrated Rust compiler arguments, all 16 direct extern digests and the separately loaded procedural macro DSO matched. Each arm’s `ruff check` returned the same expected diagnostic. All four newly built ordinary Rust consumers compiled and ran after crossing their intermediate bridges and parser outputs. Their physical metadata and archive mappings are in `ruff/readers`.

The strict raw-output criterion failed. The retained parser session wrote 1,359,343 metadata bytes and the empty one wrote 1,359,384. The private hash, public hash and stable crate ID agreed. Two additional ordinary full-workspace builds independently reproduced each respective byte stream. Extraction of the ELF member `lib.rmeta` from every `.rlib` confirmed that its `.rmeta` section contains the complete separately emitted metadata at offset zero. Whole archive hashes varied within a history. All four diagnostic replays of the actual rustc child, including the two with `-Zmeta-stats`, reproduced their full-Cargo raw hashes.

| Encoded section | Empty minus retained, bytes |
| --- | ---: |
| MIR | +49 |
| Definition records | +52 |
| Constant allocation index | −72 |
| Hygiene | +12 |
| Total | +41 |

The observed sections identify which bytes changed in aggregate. The miniature independently establishes a cache-dependent native hygiene failure. The whole-workspace mixed-library eligibility gate remained closed. This packet contains no timed performance comparisons.

## Verification

Run `python3 -B verify.py` inside this directory. Checks include the packed source and compiler provenance, paired full-Cargo rosters, independent same-history and archive comparisons, emitted caller status and native output, and the physical artifact mappings. These private task paths and fork revisions require repository access to rebuild the original environment.

The public receipts replace one host-specific Cargo registry checkout directory with a stable alias. Its basename occurred in the four Cargo JSON streams and in the two copies of the cold Rust argument list. The package records the original and portable digests of all six files and of each of the 433 affected command lines. All compiler metadata, native diagnostics and elapsed-free correctness outcomes retain their original bytes. Run `python3 -B verify-portable.py` alongside the main verifier. A holder of the original basename can supply it as the sole argument to reproduce the private content hashes.
