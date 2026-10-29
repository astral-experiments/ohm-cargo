# Ordinary Ruff binary builds and the unused link recipe

A normal `cargo build -p ruff --bin ruff` on Cargo #284 generates a recipe that this build cannot reuse. Suppressing `-Zemit-rlink` produced the same Ruff executable in the controlled one-option comparison. It also changed the executable produced by an ordinary package whose re-exported procedural macro reads the compiler's arguments. The two packages ran the same Rust compiler and stock native linker. There is no elapsed-time or instruction-count result here.

## Ruff's real edit

Ruff was at `93526150df078af7dd8fc4226cdcc469539d2001`. The one-file patch reinstates the response-file `unwrap()` that upstream changed in `7d7237c6606fa621485cf3cb982f107ce0f48db3`. It retains the current `ruff_command_line::expand_args` API. Each successful CLI also formatted `x=  1` on stdin. A missing `@` response file distinguishes Ruff's exit 2 and diagnostic from the historical panic and exit 101. [Ruff's upstream change](https://github.com/astral-sh/ruff/commit/7d7237c6606fa621485cf3cb982f107ce0f48db3)

| Ordinary Cargo state | Cargo artifacts | Dirty artifacts | Physical terminal work | Ruff verdict |
| --- | ---: | ---: | --- | --- |
| Empty original | 373 | 373 | Cargo JSON only | Exit 2, formatter passed |
| Unchanged original | 373 | 0 | None | Exit 2, formatter passed |
| Edited | 373 | 1 | One full rustc, cc, collect2 and bundled Wild | Exit 101, formatter passed |
| Unchanged edit | 373 | 0 | None | Exit 101, formatter passed |
| Invalid Rust edit | 372 | 0 of the successful artifacts | One failing rustc | Cargo 101/E0308, edited ELF retained |
| Restored | 373 | 1 | One full rustc, cc, collect2 and bundled Wild | Original ELF restored byte for byte |
| Unchanged restore | 373 | 0 | None | Exit 2, formatter passed |
| Independently empty edit | 373 | 373 | Cargo JSON only | Exit 101, formatter passed |
| Invalid in the independently trained directory | 372 | 0 of the successful artifacts | One failing rustc | Cargo 101/E0308, clean edited ELF retained |

Both traced successful edits physically passed `--emit=dep-info,link`, `-Z emit-rlink`, the persistent `-Z temps-dir=…`, and 100 externs to rustc. The independently empty edited build used distinct target and build paths. Its ELF was 16 bytes larger than the warm edited ELF and passed both real program checks. The original and restored ELFs were identical at 151,043,112 bytes. The nine commands used the matched release-profile #284 Cargo, SHA-256 `8c1717fa9786e16d3bec0c3181c02c1803484ed857d262580ce88d54056504c5`, with the published -19 Linux Rust and Wild. All jobs ran as UID 1000 with real root ownership. Build outputs used a private executable tmpfs. Each durable filesystem kept a 24 GiB floor.

## Which consumption paths apply

At `8dc33c9cc641e2b641c5b8e7075652a3e9e1f70b`, `collect_relink_cache()` is enabled by the packaged defaults while `relink_only()` requires explicit opt-in. The current binary has Build mode. The integration self-dependency proof requires a test target and Test or test-Check mode. Deferred development dependencies require a Test-mode library. The restored genuine manifest encodes `unused_extern_names` as absent, which its serde declaration decodes as `None`. Cargo's worktree import also excludes `.rlink` and `.rlink-*` files. [Cargo's compiler path](https://github.com/astral-sh/ohm-cargo/blob/8dc33c9cc641e2b641c5b8e7075652a3e9e1f70b/src/compiler/mod.rs) · [Deferred dev-dependency requirements](https://github.com/astral-sh/ohm-cargo/blob/8dc33c9cc641e2b641c5b8e7075652a3e9e1f70b/src/compiler/ohm_deferred_dev_deps.rs) · [Worktree imports](https://github.com/astral-sh/ohm-cargo/blob/8dc33c9cc641e2b641c5b8e7075652a3e9e1f70b/src/ops/cargo_worktree/mod.rs)

The persisted Ruff recipe is 127,635 bytes. Its 22 object names cover 294,952 bytes. Twenty-one are hardlinks to that unit's own incremental store, covering 293,904 bytes. The remaining object is 1,048 bytes. The record is 7,400 bytes. Removing all the optional files after compilation could release 136,083 bytes of unique file payload in this state. That upper bound excludes filesystem metadata and says nothing about elapsed time. The separate `b29c83670` prototype already avoids post-compiler payload hashing and record publication when no proof or codegen consumer exists. It and #284 are siblings of `5394ce8817`. The earlier native evidence is in the separate `rc19-proofless-relink-inputs` component.

## What the compiler option changes

The six direct replays used the actual previously captured rustc operands, fixed canonical paths, empty per-replay compiler outputs and incremental history, the same CPU, and verified stock cc, collect2 and Wild execution. The treatment removed exactly `-Z` and `emit-rlink`. It kept `temps-dir` and all other literal Rust operands. The A/B/A arrangement checked reproducibility independently. The original Cargo CLI and the direct compiler replays have separate ledgers.

| Direct native program | Original | Without recipe emission | Original again |
| --- | --- | --- | --- |
| Ruff | Original full ELF, exit 2, format passed | Same full ELF and verdicts | Same full ELF and verdicts |
| Re-exported macro witness | 17 | 29, different same-size ELF | 17, exact original ELF |

The three Ruff compiler process trees each opened and created executable mappings of 23 identified procedural-macro DSOs, including `clap_derive`, `serde_derive` and `ruff_macros`. The full Cargo graph emitted 28 procedural-macro artifacts, including two versions of `thiserror_impl`. `main.rs` imports the `clap::Parser` trait without invoking an external derive, so inspecting its syntax would miss this executable-code reachability. A mapping does not establish that a particular macro entry point ran. The witness's re-exported macro actually materializes 17 or 29 in the binary. The fixture deliberately reads an internal compiler flag through the standard process argument API.

Wild still consumed 22 Ruff CGUs and seven witness CGUs under the exact same persistent directory. Across separate compiler runs, individual randomized CGU basenames, `symbols.o`, the GCC resolution file and `raw-dylibs` changed. The like-for-like A/A repeated those categories too. The treatment left no retained recipe or objects after the full link. The compiler source also suppresses its stable CGU naming when `emit_rlink` is set for incremental builds with debug info and unpacked split DWARF. This Linux experiment cannot qualify changes to those debug paths. [Compiler switch use](https://github.com/astral-sh/ohm-rust/blob/eef2f3425c1c6f7fddfb4555769a9f90fe1e0f53/compiler/rustc_interface/src/util.rs) · [Object cleanup](https://github.com/astral-sh/ohm-rust/blob/eef2f3425c1c6f7fddfb4555769a9f90fe1e0f53/compiler/rustc_codegen_ssa/src/back/link.rs)

## Existing warm versus clean disagreement

In 28 actual Cargo commands, each `default` and `-Zrelink-only=no` history started with separate empty stores. Each history then switched modes with the same working source and immediate unchanged retry. Dirty source controls and restoration followed. Both published -19 Cargo (`235f9228`) and #284 produced this table using the same published -19 compiler. No compiler wrappers or custom Rust flags were used.

| Mode transition | First switched build | Second switched build | Independent empty selected mode | After actual consumer compile |
| --- | ---: | ---: | ---: | ---: |
| Default → explicit no | 17, fresh | 17, fresh | 29 | 29 |
| Explicit no → default | 29, fresh | 29, fresh | 17 | 17 |

On #284 the short fingerprint distinguishes explicit codegen reuse, while default collection and an explicit no both report `relink_only() == false`. The earlier shipped Cargo defaults `relink_only()` to true and lacks that later fingerprint discriminator. Its authentic result establishes that this disagreement was already present in the published package. Correlating the mode with the unit fingerprint can repair reuse after a switch. A forced compile still makes the macro see the changed option. [Shipped feature defaults](https://github.com/astral-sh/ohm-cargo/blob/235f9228651b74c591e6f62cae4c9b761448dd2d/src/workspace/features.rs) · [#284 fingerprint](https://github.com/astral-sh/ohm-cargo/blob/8dc33c9cc641e2b641c5b8e7075652a3e9e1f70b/src/compiler/fingerprint/mod.rs)

The duplicate check covered 293 named branches and 237 open and closed PR heads. Their union contained 284 product tips and 13 evidence-only tips. The module bodies reduced to 109 verified Git blobs. The three tips with the modern collection-versus-reuse split (#282, #283 and #284) retained the original unconditional emission. Historical #65 reduced the number of compiler launches and #70 removed unrelated saved temporaries. Neither preserves the public compiler argument list while eliminating this unused emission. [#65](https://github.com/astral-sh/ohm-cargo/pull/65) · [#70](https://github.com/astral-sh/ohm-cargo/pull/70)

## Verification and reproduction

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py --self-test
python3 -IB reproduce.py /path/to/ohm-sdk /path/to/new-private-directory --expect historical
```

The exact packaged reproduction also passed all 14 commands against the published -19 SDK in a separate new directory. `reproducer-verdicts.json` records those executable outcomes. The reproduction runs the actual binary after every Cargo command and captures complete Cargo JSON and stderr. Use `--expect correct` for a repaired transition. The compact evidence includes ordered, typed artifact records, actual post-expansion Rust/GCC/linker argument digests, positive executable-mapping commitments, intent and floor stops, and SHA-256s of the private originals. The clean Ruff source hash and the exact applied hunk are recorded alongside them.
