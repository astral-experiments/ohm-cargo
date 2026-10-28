# Recompile a foreign-span reader whose binary input may have changed after use

The fixed Cargo (9a017086, PGO SHA-256 0aa04df8…) and its matched control (a0c7d08c, 50ca4774…) ran identical fresh and previously established proc-macro observer cases. A real shared library changed its native return value from 17 to 29 while retaining the same serialized Rust metadata. A separate metadata-only library moved an exported token between columns, retained all crate hashes and changed an ordinary consumer’s required u16 to an i16. A second macro delayed publication of the consumer’s dep-info until after a verified atomic replacement. Both the normal and the preserved nanosecond mtime were tested.

| Prior history and command | Matched Cargo plus release-source rustc | Fixed Cargo plus release-source rustc |
| --- | --- | --- |
| First DSO observation, build | First repeat corrects 17 to 29 | First and second repeats return 29 |
| Known DSO, build after a genuine consumer edit | Both repeats are fresh and still return 17, clean returns 29 | Both repeats recompile and return 29 |
| First standalone metadata observation, check | First repeat reports E0308 | Both repeats report E0308 |
| Known standalone metadata after a genuine consumer edit, check | Both repeats report fresh success, clean reports E0308 | Both repeats report E0308 |

The new optional-attestation compiler was also run with the fixed Cargo. All its outcomes matched the corrected release-source compiler. Every successful dirty observer reran the real compiler without either the binary-dep-info flag or the checksum-hash flag. This deliberately includes unchanged readers with a previously observed foreign token. The compiler’s ability to serialize an optional record alone was insufficient to change the result.

The 32 additional commands used eight already-wrong, physically copied targets from the original uncorrected runs. The copies were remounted at their actual original source, SDK, target and shared-build path spellings. On every copy its original Cargo first reproduced the wrong fresh 17 or the wrong fresh successful check without starting rustc. Switching only Cargo corrected all eight on the next command. The second unchanged fixed command and an independent empty fixed target agreed. Both conventional trained records and the experimental first-capture records were included. The donors’ file contents, modes, symlink targets and nanosecond mtimes were verified before and after the migration experiment.

Run python3 -IB verify.py to replay all 164 typed command records and the two independent program/error oracles. Four portable Python fixture drivers and the original migration procedure are included. The raw archive records actual compiler execs, argv digests, the Cargo disposition, per-input digests and program or diagnostic results. Private registry details, full environments and built binary blobs are excluded. These are untimed component correctness checks. The corrected compiler shipping-source Rust subtree was bfa236f6 with stage-2 PGO+BOLT driver 52d5c046…; the separate optional-compiler check used 337a07a7 and ee9448c2….
