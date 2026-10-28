# Final Cargo checksum migration on unmodified Ruff

With the shipped Ohm -16 compiler held fixed, the final Cargo candidate rebuilt exactly the 71, 68 and 162 workspace units whose ordinary version-2 inputs contained checksums. Every unit was fresh on the next check, build and test preparation. The six commands used independently verified copies of the three settled release states from the earlier experiment. The candidate process counts matched that experiment.

| Workspace command | Fresh on first call | Full rustcs | Build scripts | Wild links | Fresh on second call |
| --- | ---: | ---: | ---: | ---: | ---: |
| `cargo +ohm check` | 449/520 | 71 | 5 | 6 | 520/520 |
| `cargo +ohm build` | 433/501 | 68 | 5 | 15 | 501/501 |
| `cargo +ohm test --no-run` | 457/619 | 162 | 5 | 110 | 619/619 |

All six commands used `--workspace --locked --offline --message-format=json` and returned 0. Every first-call compiler matched a distinct workspace unit's original checksum record. All of these records became version 4. The 449, 433 and 456 modification-time records remained byte-identical, as did the test build's authenticated, complete OBS1 record. All second calls had zero Rust compilers, linkers and build scripts. Neither first nor second call used a link-only rustc. The observed inputs had no spaces, malformed UTF-8 or Unicode replacement characters.

The new Cargo executable was SHA-256 `787ed90b5a14000ac0b1efc1d1aac5d730e0107b2e995cc0471138402759a4d5` at source `a0c7d08c898d3fdff992f2f431dec57d2486add2`. Ruff remained at `93526150df078af7dd8fc4226cdcc469539d2001`, with the original -16 frontend, driver and Wild. Each new copy retained source state, file bytes, mode, mtimes and in-tree hardlink groups. All regular inodes were independent of its release seed. This study measures the Cargo-only one-time migration on unmodified Ruff and contains no wall-time estimate. [Prospective six-command addendum](https://github.com/astral-sh/ohm-cargo/tree/d3005f36662aa98750ac4ffb33dd03b23526ac9e/benchmarks/ruff-dev-loop-20261027/cargo-checksum-migration16-v4-plan) · [Earlier release seeds and stock controls](https://github.com/astral-sh/ohm-cargo/tree/b140a121101d15efedea72738d62e022809d08f8/benchmarks/ruff-dev-loop-20261027/cargo-checksum-migration16-results)

## Products and runtime

All 6 workspace check ELFs, all 15 build ELFs and 106 of 110 test ELFs were byte-identical to their released seed. Each of the four remaining test files changed exactly 33 bytes. One byte of the `.rodata` section header changed its entry size from 0 to 8. The other 32 bytes comprise the GNU build-ID value. The complete file SHA-256 after masking just those two fields is identical in each pair. The `.text`, `.rodata` contents, debug sections and every other file byte match. All four full harness listings were byte-identical. Each pair passed the same lexicographically first listed test, executed separately from the six Cargo commands.

| Changed test harness | Identical listed tests | Independently executed on both copies |
| --- | ---: | --- |
| ruff_annotate_snippets color | 32 | `ann_eof::case` |
| ruff_python_stdlib library | 4 | `identifiers::tests::migration_name` |
| ty_python_semantic library | 499 | `diagnostic::levenshtein::tests::non_underscored_names_always_suggested_even_if_typo_underscored::_bluch_expects` |
| ty_server e2e | 200 | `call_hierarchy::incoming_calls_multi_file` |

Check, build and test each produced 31 standalone workspace metadata files whose raw bytes and private crate hash changed. All retained the public hash and StableCrateId found by the original compiler. In the respective endpoints 4, 55 and 54 whole Rust archive hashes also changed. The archive member contents were not used to qualify a native skip. Corresponding direct parser callers, the bad caller's E0061 and source spans, Ruff F821, both CLI versions and the parser harness's 246 test names agreed with the original controls. Registry metadata and non-workspace native files matched raw.

Compared directly with the previously tested Cargo candidate rather than the shipped seed, the new run still differed in 4, 55 and 54 raw archive files. The test build also had three different ELF hashes between candidates. All standalone metadata and remaining advertised product hashes matched between candidates. The paths and paired hashes are in `v3-to-v4-products.json`.

## Verification

Run `sha256sum -c SHA256SUMS` and `python3 -B verify.py` in this directory. The verifier opens all six Cargo records and the original immutable control rows, matches actual compiler PIDs and argument digests to their preexisting serialized records, checks outputs and verifies the ordinary native-reader evidence. All 32 supplemental stdout/stderr streams are gzip-compressed verbatim. The extra ELF reader was resumed after correcting a local variable in its artifact enumeration. Its first completed ELF result was reused by exact raw digest. The six Cargo commands were each executed once.
