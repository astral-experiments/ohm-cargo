# A synchronized native compiler input replacement can make a real Cargo build falsely fresh

Two real Rust compilers consumed the old object selected by a pathname. A private atomic rename then published a different object before rustc wrote the Cargo consumer’s dep-info. The compiler reopened the pathname and hashed the replacement. By that time the executed macro or decoded external token had already influenced the consumer. The following Cargo invocations could report every unit fresh while disagreeing with an independently empty target.

## Measured programs and type checks

| Input and timing | Corrected release-source pair | New no-query pair | Explicit first-capture comparison | Independent clean |
| --- | --- | --- | --- | --- |
| Proc-macro DSO, first observation | 17 → 29 → 29 | 17 → 17 fresh → 17 fresh | 17 → 17 fresh → 17 fresh | 29 |
| Standalone .rmeta, first observation | succeeds → E0308 → E0308 | succeeds → succeeds fresh → succeeds fresh | succeeds → succeeds fresh → succeeds fresh | E0308 |
| Proc-macro DSO after completed training and a genuine consumer edit | 17 → 17 fresh → 17 fresh | same | same | 29 |
| Standalone .rmeta after completed training and a genuine consumer edit | succeeds → succeeds fresh → succeeds fresh | same | same | E0308 |

In the first two rows, the old Cargo plus new compiler crossover also repaired the output on the first repeat. In the two trained rows all four pairings failed. Training consisted of one independently cold command followed by two authentic unchanged commands through a confirmed complete, all-fresh state. The subsequent source edit genuinely reran the selected Rust compiler. The build fixture’s executable also confirmed its independently changed consumer generation. The results were the same with the replacement nanosecond mtime preserved and with the normal newer mtime.

The original DSO generated a Rust token 17. A second macro signaled only after it received that token and blocked while the test replaced the original DSO. An OS maps check recorded the original dev/inode's executable mapping in rustc. The Rust source and ELF .rustc and .dynsym contents in the two DSO versions were byte-identical. Both real DSOs linked a C function, with machine code returning 17 or 29. In the rewritten complete records, the verifier independently hashed both native files and confirmed that the stored BLAKE3 matched the replacement.

A second producer created ordinary standalone Rust metadata. Its exported token moved by exactly 256 columns after toggling equal-width comment delimiters around two copies of the macro. The decoded private crate hash, public crate hash and stable crate ID remained identical, but the serialized metadata bytes changed. Another real proc macro read the foreign token’s column. It generated a u16 in the old position or i16 in the new position. In an actual cargo check, assigning the latter to a required u16 produces E0308. The retained metadata on failing commands may still describe a prior successful invocation; the proof verifier attributes successful phase outcomes only to the observed compiler/event provenance.

The package also retains the original 64 commands with a Rust-authored proc macro or a metadata-only producer with a directly changed typed expansion. These ordinary Rust-identity changes were rejected by both compilers with a colliding StableCrateId diagnostic on the initiating build. The next two commands and independent clean then agreed. Those controls show why treating a conventional crate-hash change as representative of every observable binary change would miss the two failing cases.

## Reproduction

Run python3 -IB verify.py for standalone verification of the 240 command records. The five Python experiment scripts beside this README create independent temporary workspaces from fixture and call real cargo +ohm build or cargo +ohm check offline. Pass --sdk with the desired active SDK root and --root with a new, nonexistent writable directory. They require a Linux x86_64 host, rustup, strace and cc. The trained scripts change the consumer as described above. The device and inode numbers in the recorded private fixture are local identities.

The matched release-source control used Cargo a0c7d08c and the bfa236f6 compiler source tree. The new pair used b538e174 and 337a07a7. The explicit comparator used Cargo 97c04e44 and the same new compiler. This packet has no wall measurements. The BLAKE3 proof binds the stored checksum to the covered compiler bytes. The independent SHA-256 manifest authenticates the files in this evidence packet. Native shared libraries and raw environment records are excluded.
