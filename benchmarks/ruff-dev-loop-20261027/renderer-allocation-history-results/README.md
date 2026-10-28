# Incremental allocation identities in Ruff's diagnostic renderer

On pinned Ruff `93526150df078af7dd8fc4226cdcc469539d2001`, reverting the complete historical private renderer change `9c53b5de3aae4b1832eb7ee137647dda2466f888` and restoring it gave two different public hashes for the same original native producer. The allocation patch reproduced independently clean metadata byte for byte after the edit and the restoration. Each clean source variant still has a different public hash from the other. None of the three source changes in this packet establishes a whole-job or wall-time saving.

## Two CLIs on released Ohm 1.99.0-16

Each ordinary `cargo +ohm build --locked --offline --message-format=json -p ruff --bin ruff` and the analogous `ty` command used the private source and distinct CLI native target on H3. The design used the same canonical physical inputs, effective checked-in profiles, compiler and native linker throughout. Cargo, rustc frontend, rustc driver and Wild SHA-256 are in `plan.json`. This is an unscored structural experiment. The two CLIs report real F821 and invalid-assignment diagnostics.

| Command | After full historical reversal | After restoring | Immediate unchanged repeat |
| --- | ---: | ---: | ---: |
| Ruff CLI, 373 units | 13 full rustcs, 1 Wild | 13 full rustcs, 1 Wild | 373 fresh, no rustc or Wild |
| ty CLI, 350 units | 13 full rustcs, 1 Wild | 13 full rustcs, 1 Wild | 350 fresh, no rustc or Wild |

The first ty build, before applying the change, separately ran one full `ty_vendored` rustc, its build script, one link-only rustc and Wild. A conventional external binary applied three insertions through the renderer’s public API. It returned successfully on the original and restored inputs and reproduced the earlier bounds panic with status 101 on the reverted inputs. The fixture captures native output and diagnostics separately.

The unchanged original source had private SVH `af29a126fdd3dc174ca1d57b3626f211` and stable crate ID `2485515482279618459`. The genuinely cold producer public hash was `47bde095990dca77b7f422f24c4c8e5b`. Following edit and restoration, the same original source instead gave `0fe00b8e7e80b15d08068f8d07a09456`. Forcing just the compiler call against the retained incremental directory reproduced the latter. Three additional empty producer controls all reproduced the entire initial `.rmeta` (SHA-256 `6c3555869e105fada1b3cf0cc3221ba8deaab1840732a1338eb04ae35d7c5c0c`). Both independently empty reverted producers agreed with one another. Declarations, feature flags, source manifest, actual same-variant rustc command and all three physical dependency metadata hashes were accounted for.

The standalone reader in `wire.py` decodes the complete metadata objects. Original and restored have identical source-table entries, local definition and identifier spans, all 253 expansion hash/ordinal pairs and the global public component. Of 1,099 per-definition public hashes, 682 changed across 31 pairs of component hashes. The table of CTFE allocations grew from 181 to 189. Both have exactly the same set of 180 distinct serialized payloads. The eight additional entries are duplicates for `end`, `kind`, `label`, `highlight_source`, `start`, `line`, `span` and `replacement`.

## Independent compiler comparison

The source-equivalent release-profile Rust #233 control, macro source replay control and macro source replay plus two-file allocation-identity treatment used the same release-profile frontend, real Cargo, standard library and LLVM. The matched driver hashes are recorded in the designs and every normal build ran a genuine compiler. These images differ physically from the officially distributed -16 binary. The producer-only commands were ordinary `cargo +ohm build --locked --offline -p ruff_annotate_snippets --lib`. Package-only feature selection differs from the two large CLI builds, so compare histories within a row.

| Source stimulus | Native package builds and external callers | Result |
| --- | ---: | --- |
| Complete private renderer panic fix, 9c53b5de | 15 | Rust #233 and macro replay reproduced history-sensitive public hashes. Adding allocation identity matched both independently empty sources byte-for-byte and preserved the native panic/control. Both empty sources have different public hashes. |
| Complete independent four-file renderer change, 2e647533 | 15 | All three arms already matched their clean counterpart both ways. The external renderer printed ` ::: cell 1:2:8` on the original and ` --> cell 1:2:8` under reversal. Both empty sources have different public hashes. |
| Complete whitespace.rs file from the 30-file mechanical change, 88d56e5f | 10 | The 4,058 bytes before the existing final test-only module are identical. Macro replay and macro replay plus allocation identity each kept public hash `9b70651f5c476f086b553908bf2babf1`. Source-specific raw metadata changed and matched independently empty builds in both arms. |

The trivia holdout also compiled six real `cargo test --no-run -p ruff_python_trivia --lib` native harnesses on the original, edited and restored sources in both arms. Both changed tab-expansion tests in each passed when invoked outside the build command. The three historical stimulus files and ordinary downstream readers are included with each selection plan.

The allocation patch preserves the existing allocation deduplication flag across the rustc incremental codec and changes its incremental format version. The macro replay patch is identical in the last two arms. The separate previously observed Ruff parser allocation study has its own cleaner cross-direction evidence. [Allocation identity structural controls](https://github.com/astral-sh/ohm-cargo/tree/f1acce08da8a2fde7789233b8dac00d5c0dd9013/benchmarks/ruff-dev-loop-20261027/alloc-identity-structural-results)

## Recheck the evidence

Run `python3 -B verify.py` and `sha256sum -c SHA256SUMS` in this directory. `original-records.json` binds all 1,128 original files with their raw size and SHA-256. The seven `records-*.tar.gz` archives hold 607 unique portable text payloads. One private registry hostname in 168 text records was replaced by a placeholder. Both original and portable hashes are recorded. The 50 full native rlibs contain a private registry path in their codegen objects’ debug information. `retained-archive-members.json` supplies their original SHA-256, all ordered member names, byte lengths and per-member SHA-256. `native/` preserves every distinct raw ELF metadata member and separately emitted standalone Rust metadata file. The verifier extracts the native ELF section and checks that its bytes match the independent compiler emission, the ordinary readers and the physical process receipts.

Two initial setup failures are recorded under `launch/`. The first tried to nest a mount namespace and the next tried the top-level copy before resolving the metadata output in Cargo’s typed output. The first successful traced build was adopted from its completed Cargo output, then its reader was run using the real produced path. No timings were collected.
