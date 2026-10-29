# A dependency edit that requires full workspace resolution

The measured input changes one dependency requirement in Ruff’s root manifest. Ruff commit c890b04e575809cbff9b43975175b43dd82c3a1a raised Salsa from 0.28.2 to 0.28.5. At 93526150df078af7dd8fc4226cdcc469539d2001 that exact hunk reverses cleanly. Both caret requirements accept the 0.28.5 already pinned in the 553-package lockfile. The rest of that upstream commit changed two lockfiles, the fuzz manifest and Rust source. Those other changes are outside this experiment.

## Native evidence

All 20 coordinator commands built the actual `ruff_text_size` library with `cargo +ohm build -p ruff_text_size --locked --offline --message-format=json`. Each time a separate consumer compiled against the emitted library and returned `17 29 12`. Cold preparation compiled one library. The 19 subsequent builds reported one fresh library with identical complete .rlib and .rmeta bytes and ran zero compiler or linker jobs. The library’s default feature set is empty and it does not depend on Salsa. The dependency change exercises workspace resolution independently of selected compilation work.

| Cargo source | Whole workspace resolves per change | Generic resolver entries | Serializer entries | Independently locked reads |
| --- | ---: | ---: | ---: | ---: |
| Baseline 2fe90823d | 1 | 2 | 2 | 4 |
| Profile-only 97e5acfb7 | 1 | 2 | 2 | 4 |
| Serializer 24c98100d | 1 | 2 | 1 | 4 |

The same counts held reversing and restoring the real manifest hunk. On every unchanged follow-up all three saw zero whole workspace resolves, one narrower generic resolver entry, zero serializer entries and one locked read. On its first unchanged seed migration, the profile-only image refilled the workspace cache. That initial fill is separately labeled. The acquired descriptor bytes match the pinned lockfile on all reads, including shared-lock acquisition, EOF and unlock. Four x86 execution breakpoints observed actual function entry. The runtime return address distinguishes the writer’s call from the cache marker’s call; the release image enrollment includes the relevant disassembly and return addresses.

## Prospective H8 instruction study

The predetermined sequence in `protocol.json` contains eight independently paired reverse edits and eight restore edits. Each arm immediately receives its corresponding unchanged command in its own history. Each of the four endpoints has four AB and four BA orders. Only the baseline and pure serializer images enter the instruction comparison. Both share the same physical completed one-library target as the original wall study, with separate write layers. The 97e5acfb7 result above establishes that the profile-only optimization still requires the full resolver on this edit. No combined binary was timed or counted here.

The primary estimands are per-transition median paired percentage reductions in userspace instructions executed by all parent Cargo threads including libraries. The plan uses exact paired sign tests and Holm correction for the two edit directions. It reports the two unchanged follow-ups separately. Hardware access is checked before admitting the software fallback. The fallback requires genuine same-owner thread and child calibration, per-process exec validation, exact serializer and cache-publication call counts, physical products and a compiled consumer, with no replacement sample after a rejection.

## Verification

Run `sha256sum -c SHA256SUMS` and `python3 -IB verify.py`. The verifier reads all 20 native event streams, reconstructs every locked read from the acquired byte chunks, verifies actual function placement, distinguishes the cold compile from 19 no-work commands and checks balanced enrollment for the independent instruction study. The projected event streams omit private filesystem coordinates. Individual raw trace, receipt, binary and product digests are included for independent custody.

Four early setup records are retained by digest. The first stopped on incorrect filesystem ownership before Cargo started. The second could not use the configured offline registry under an alternate key. The third stopped when a Rustup worker exited before Cargo enrollment. The final native reader initially rejected a successful cold command because its decoder expected a blocking shared-lock flag. The observer actually recorded a successful nonblocking shared lock. The same untouched cold trace was re-decoded with that flag; all later commands used the corrected decoder. All 498 locked registry checksums were verified against the admitted offline index.

Upstream provenance is available in the [Ruff change](https://github.com/astral-sh/ruff/commit/c890b04e575809cbff9b43975175b43dd82c3a1a).
