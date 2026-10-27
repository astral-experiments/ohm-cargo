# First Cargo checksum migration on an unchanged Ruff workspace

Switching from the released Linux Ohm -16 Cargo to candidate Cargo `01742c822d91` rebuilt 71 workspace compiler units for check, 68 for build and 162 for test preparation. In each case the set of full rustc invocations exactly equalled the set of pre-existing ordinary checksum-bearing records that required migration. Repeating the same command immediately afterwards ran zero compilers, linkers or build scripts. This experiment records work performed. It has no elapsed-time endpoint.

| Whole-workspace command | Total units | Fresh on first upgrade | Full rustc | Wild links | Build scripts | Fresh on second upgrade |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `cargo +ohm check --workspace` | 520 | 449 | 71 | 6 | 5 | 520 |
| `cargo +ohm build --workspace` | 501 | 433 | 68 | 15 | 5 | 501 |
| `cargo +ohm test --no-run --workspace` | 619 | 457 | 162 | 110 | 5 | 619 |

Each first upgraded command ran zero link-only rustcs. All 449, 433 and 456 ordinary records using modification times retained their original bytes. In the test endpoint, one further external unit had an authenticated, complete OBS1 record with unspaced absolute inputs. It also retained its bytes. Every settled compiler record joined to a physical unit. The 71, 68 and 162 recompiled units each used an original workspace record with a checksum. The registered unspaced workspace and registry were unchanged.

## Source and control

Ruff was pinned to `93526150df078af7dd8fc4226cdcc469539d2001`. Each endpoint began with its own empty target, build directory and registry copy. It reached a fully fresh state on the official -16 Cargo before the two comparison histories were copied. The original and copies agreed in content, mode, nanosecond mtime and hardlink relationships within each state. Their regular-file inodes were independent across copies. Each arm saw the same logical paths, SDK, Cargo defaults, eight jobs and offline locked graph. Two unchanged commands on the stock control copy of each endpoint produced zero native jobs before the first treatment command. `clone-bindings.json` contains the verified initial tree digests.

The SDK archive was SHA-256 `957ca8144205008ddaee75ef35f9775b2e428271c6b044e38bbdd8196c6bbf3e`. Cargo changed from `42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568` to `d7dfa671c8ec6ca2b50c7b0e41af4c0046e19bc02f18145d97d98455af2f722c`. The release -16 rustc frontend, driver, LLVM and Wild were held fixed. An upgrade that replaces the compiler as well has a different cache transition. [Prospective plan](https://github.com/astral-sh/ohm-cargo/tree/ae916e2b71f000eadcbc99bc0596f7ed6a65236b/benchmarks/ruff-dev-loop-20261027/cargo-checksum-migration16-plan) · [Tool and protocol binding](https://github.com/astral-sh/ohm-cargo/tree/f2b9684a110624e89bff775df88a7c791d0c47ba/benchmarks/ruff-dev-loop-20261027/cargo-checksum-migration16-binding)

The original cold test build had a real speculative `integration_test` rustc exit 1. The retry with the same argv succeeded and Cargo returned 0. Its first unchanged repeat still ran one full rustc and 50 link-only rustcs with 50 Wild invocations. Its second settled at 619/619 fresh, before the state copies. Both later stock repetitions returned 619/619 fresh. All qualifying Cargo commands succeeded, and all compiler and linker children during either upgrade call returned 0.

## Products and ordinary readers

For each endpoint exactly 31 standalone workspace `.rmeta` files changed raw bytes. The retained before/after pairs were decoded with the same stock rustc. Across all 93 pairs the private crate hash changed, while the public hash and StableCrateId agreed. The raw `.rlib` changed for 4 check, 55 build and 54 test products. The packet retains the distinct whole-file digests and lengths, without assuming that every archive member is identical. A newly compiled ordinary parser caller succeeded and a separate erroneous call preserved its E0061 text, primary span and definition note. Ruff and Ty versions, the actual Ruff F821 diagnostic and the parser harness's complete 246-test listing also agreed in their respective endpoints.

All 6 workspace check ELFs and all 15 workspace build ELFs were byte-identical. The test build emitted 110 workspace ELF artifact paths including 84 test-profile and 18 other executable target records. Of the 110, 107 were byte-identical. Each of the remaining three files differed in exactly 33 bytes. Wild's `.rodata` section header had its entry-size value change from 0 to 8, plus all 32 bytes of the GNU build ID changed. Both whole-file SHA-256 digests matched after masking only the actual entry-size word and the authenticated GNU build-ID descriptor. The changed-byte range census independently found one byte in that word and the 32-byte note at file offsets [896, 928). Every byte of `.text`, `.rodata` data, debug information, other headers and padding matched in each file pair.

The three complete listings below matched byte-for-byte. The lexicographically first listed test in each pair was then executed directly as a separate product check. All six targeted runs passed. Their test-result stdout agreed after normalizing only the harness's elapsed-time field. The Ty server debug log includes run timestamps and per-run temporary paths. Its two raw stderr streams and digests are retained separately.

| Raw-different test executable | Tests listed | Executed on both copies |
| --- | ---: | --- |
| `ruff_python_stdlib-09978b48e8f13d6a` | 4 | `identifiers::tests::migration_name` |
| `ruff-8ae260e78382292d` from ruff_annotate_snippets | 10 | `insertion_with_trailing_whitespace` |
| `e2e-dd9b7f57d7ba4f6b` from ty_server | 200 | `call_hierarchy::incoming_calls_multi_file` |

## Rechecking the receipts

Run `sha256sum -c SHA256SUMS` followed by `python3 -B verify-supplement.py` in this directory. The latter also runs `verify.py` over all 19 Cargo commands, their physical process and output records, serialized-fingerprint classes and ordinary readers. The archive exposes typed native process records with original argv hashes. Checkout, cache and registry locations in the command receipts use aliases. `changed-rmeta-headers.json` contains both real metadata headers' selected hash fields. `changed-elf-guards.json` includes the per-section data and exact raw diff ranges. Each compressed `harness-*` stream contains the original bytes. `supplement-origins.json` binds the raw hashes independently of compression.

The public copy of the export helper strips registry source-directory keys generically and accepts optional comma-separated local registry aliases in `OHM_EXPORT_REGISTRY_ALIASES`. The retained command receipts and their original hashes are unchanged.
