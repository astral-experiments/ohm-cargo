# An earlier native library supplied by a transitive dependency

Two Rust application binaries call a middle crate, which calls a provider crate. The provider links a static C library with `-bundle`. Its build script supplies the earlier and fallback directories through Cargo's ordinary native link-search directive. Both variants declare the fallback archive. One also declares the earlier directory.

The source-qualified release pair was Ohm Rust 7e71d315 and Cargo 2d44bd4a. The distributed comparison used the actual Linux 1.99.0-19 archive, SHA-256 `ef21d83519bc376479811a7e01fa5ac8915ac0a500c6859bc22a1e0b4913d812`. The source-qualified Cargo executable had SHA-256 `1d06626bcef3c5235676ada14f4b7107f56e98aef620f81b0e0c47381dbe0add`. It was compiled from its checked-out commit using the optimized release profile. Default mode used Wild, whose SHA-256 was `0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5` on both toolchains. The separate `-Zohm-defaults=no` arm used GNU ld, SHA-256 `e9ceb054c12207970f2726dfc07e9a66b411602748628baf27399f02a9bbb31b`. No linker wrapper was used.

## Observed programs

Each cell is the integer printed by both programs during an ordinary warm build. Their link results agreed across source-qualified defaults, disabled defaults, and signed -19 defaults.

| Earlier native path | Declared directory | Undeclared directory | Forced and independently empty |
| --- | --- | --- | --- |
| Initially absent | 17 | 17 | 17 |
| Insert archive | 29 | 17 | 29 |
| Overwrite archive in place | 41 | 17 | 41 |
| Overwrite with malformed bytes | Cargo 101 | 17 | Cargo 101 |
| Remove archive | 17 | 17 | 17 |
| Repair with valid archive | 73 | 17 | 73 |
| Remove again | 17 | 17 | 17 |

For every actual declared change both terminal executables invoked the selected native linker. Successful unchanged repeats invoked zero terminal links. A malformed declared archive also failed the immediate repeat. With the earlier directory intentionally undeclared, the first build linked both programs and each subsequent ordinary build linked neither. Each forced/empty pair produced byte-identical complete binaries for each valid input state. The in-place overwrite preserved the archive inode and the parent-directory timestamp and allowed the normal file timestamp to change.

The two source-qualified modes ran 112 ordinary Cargo commands. Signed -19 ran 56. All 24 distinct ELF files were decompressed, hashed and executed again. The independent reader reopened 13,906 split native process/thread traces. These observations cover this declared directory contract and two native executables. The protected -20 distribution was still unbuilt at collection.

## Verify

Run `python3 -IB verify.py` to check the portable projections and exact fixture bytes. Each phase in the compressed projection records the two executable hashes, checked native linker opens, real rustc names and digest bindings to original Cargo streams and traces. The README's outputs can be reproduced with the fixture source in this directory. Construct sibling `native/early` and `native/late` directories alongside the copied `source` directory. Compile a C file defining `int native_value(void) { return 17; }` and place its object in `native/late/libohm_269_transitive.a`. Then run the following in the source directory using the selected normal SDK.

```sh
cargo +ohm build --bins --locked --offline -j2 --message-format=json -p answer-consumers
./target/debug/first_probe
./target/debug/second_probe
```

Repeat with the earlier archive exporting 29, then rewrite it in place with 41, malformed bytes, remove it, add it with 73 and remove it again. New independent targets and shared build directories supply the reference for each state. The original acquisition took place at the same visible target, shared and SDK paths in private mount namespaces. `verify_raw.py RAW_STUDY NEW_PROJECTION` reopens the complete original tracer splits, Cargo streams and compressed native binaries when that separately retained private root is available.

[Cargo #294](https://github.com/astral-sh/ohm-cargo/pull/294) · [Rust #269](https://github.com/astral-sh/ohm-rust/pull/269) · [Signed -19 release](https://github.com/astral-sh/ohm/releases/tag/ohm-1.99.0-19)
