# Native private impl metadata

The compiler change is stacked on the private trait cutoff for check metadata. This directory records the native stage-2 driver, two historical Ruff source changes, their compiler outputs, the cross-crate fixture transcripts and the checked-in run-make regression. [Compiler parent](https://github.com/astral-sh/ohm-rust/commit/8ce2f21e25c06e7f884ca7b5c4e7898180791ae4).

The stage-2 control and candidate used the same Linux x86-64 frontend, standard library, PGO inputs and BOLT profile. The control driver starts `051b9d3f` and the treatment starts `55e123a9`. `stage2-receipt.json` records the full file and profile hashes. `candidate.patch` is the measured production encoder change. The subsequent changes in compiler commit `8d8897ff` contain the regression test.

## Actual Ruff compiler outputs

Reverse the complete patch from `3ea20f6161` at Ruff `93526150df`. It changes a parser implementation, its error input and the corresponding snapshot. The direct replay uses the actual compiler arguments captured from a normal `cargo build -p ruff_python_parser`, including incremental codegen at the crate's usual optimization level. The parser's native archive and raw metadata change with either compiler. [Ruff change](https://github.com/astral-sh/ruff/commit/3ea20f6161cbf59cb56595dfb634ec24bfa82f0b).

| Stage-2 driver | Original public hash | Edited public hash |
| --- | --- | --- |
| Parent | `42536a41460d0de81c1c3f89f7885deb` | `a40c89b72982e68fe45cda509db9cf64` |
| Candidate | `399e8964f158224d860912f6523abe2c` | `399e8964f158224d860912f6523abe2c` |

A separate metadata-only replay of the earlier check change also produced byte-identical original and edited metadata when comparing drivers for each source. Both drivers emitted `3a532957245d813474d316be5ae8d2a3` before and after that change. `actual-rustc-outputs.json` stores the full compiler argument, archive, metadata and driver digests.

## Historical confirmation

`choose.py` ranks previous private parser implementation changes by the digest of their commit and a fixed seed. `holdout-selection.json` records the ten qualifying commits before any compiler counters. The lowest-ranked patch did not apply to the contemporary checkout. The confirmation uses its complete original parent `3bb0dac235` and child `c1eaf6ff72`, including the two test files. The 55 altered Rust lines add a parse error for a raise statement that begins with `from`. [Historical Ruff change](https://github.com/astral-sh/ruff/commit/c1eaf6ff72875a68e2585d50deaff220ea1d8ce9).

| Ordinary scoped command | Cargo units | Parent full / link-only | Candidate full / link-only | Terminal executable records |
| --- | ---: | ---: | ---: | ---: |
| `cargo build -p ruff_python_formatter` | 94 | 3 / 0 | 1 / 1 | 1 |
| `cargo test -p ruff_python_formatter --no-run` | 107 | 7 / 0 | 1 / 4 | 5 |

Only an explicit `-Z link-only` invocation with an existing `.rlink` input counts as a relink. The parent reported three or seven dirty units. The candidate reported the same counts because Cargo can report a dirty library as a unit while skipping its compiler. The whole edited command produces the new parser diagnostic on both drivers. The original returns “Expected an identifier” for `raise from exc`. Both the edited warm result and both clean runs return “Exception missing in `raise` statement with cause” at byte range 6..10. Valid formatting samples also agree.

The parent emitted different warm and clean public hashes for this 2024 revision. Its two independent clean repetitions agreed. The candidate's original, edited-warm and both edited-clean runs emitted the same public hash. All six reported clean native products were byte-identical between drivers. The warm binaries showed a variable GNU build ID and LLVM numeric suffixes in hidden static symbol names. Independent repetitions with the parent reproduced these variations. Each raw section hash remains in `historical-qualification.json.gz`. The separate randomized cohort requires every full treatment symbol spelling to have an exact parent witness, including those suffixes.

All 250 build diagnostics were identical in both arms. In one comparison of the 270 edited test warnings, the placement of a spanless default-lint note changed between two diagnostics in the same library. Its text and count, every source span, suggestion, warning and remaining rendered line agreed. The exact rule and original positions are recorded with the timing cohort.

## Cross-crate and run-make guards

`cross-crate-transcripts.json.gz` contains 132 release-driver Cargo commands. Each driver compiled 22 cases before an edit, after the edit with a warm target, and after the edit with a clean target. All 19 cases expected to build produced byte-identical edited warm and clean executables within each arm. The other three cases produced identical complete edited diagnostics. The inputs cover generic and inline MIR, native layout, const evaluation, trait object dispatch, opaque types, macro paths, private method lookup, inferred foreign-trait projections, `From` with private input, blanket `Into` and `TryFrom`, tracked callers, generic drop glue and a private method exposed under a C symbol.

For the checked-in test, the candidate compiled and relinked a downstream binary using its saved objects. The private method change moved the source, preserved the producer's public hash and changed the result from `1 1` to `1 2`. Changing the same private type's layout changed the hash and made a freshly compiled caller print `8 2`. The matched parent fails at the first hash-equality assertion. The existing CI job selects the new directory with its `tests/run-make/rdr-public-hash*` pattern. `run-make.json` records the input digests and both compiler transcripts.

The replay programs retain the exact private cache paths and prior release bootstrap layout used on the devboxes. The JSON and compressed transcripts contain complete compiler and output digests for verification. `history.py` preserves its initial unscored experiment record. Its prototype compile-action reporter also recognized object-directory path suffixes, so the durable qualification classifies each original argv with the explicit-link rule above.
