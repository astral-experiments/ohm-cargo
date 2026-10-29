# Original cached-codegen PR and assembler input acquisition

Cargo PR #51 introduces the wrong answer on the active 1.98 branch. This result applies to its opt-in cached relink on an ordinary binary with a used Rust dependency. The runtime is the publicly distributed Linux Ohm 1.98.1-1 compiler and standard library. Both Cargo binaries were built from their exact original Git heads.

| Historical Cargo | Private Rust edit plus byte 17→29 | Restore Rust source with byte missing |
|---|---|---|
| Direct parent 30004d93, public hashing | prints native 29 and Rust 10 | exits 101 |
| #51 caac2566, same public hashing plus cached relink | prints native 17 and Rust 10 | exits 0, prints native 29 and Rust 6 |
| #51 caac2566, same public hashing only | prints native 29 and Rust 10 | exits 101 |
| Independently empty, all three | prints native 29 and Rust 10 | exits 101 |

The original program prints native 17 and Rust 6. Its ordinary binary reads a volatile byte emitted by global_asm! and calls a real out-of-line function in a separate library. The edit changes x ^ 5 to x ^ 9 inside that function and replaces one input byte. Every arm rebuilds the provider and picks up its new Rust value. The provider’s compiler-reported public API hash is constant within each arm. Its independently compiled archives differ across that edit. The root depfile names the Rust source and omits the assembler input.

On #51 with cached relinking, the valid edit runs the actual compiler in link-only mode on the current Rust archive and never opens the input byte. The enrolled codegen object still contains 0x11 in its .rodata.ohm_assembly_input section and has its original whole-object SHA. Independently empty and same-state forced recompilations both read the input, produce 0x1d, and emit the identical correct executable. The missing-input test starts from that corrected, fully compiled state. Cached relinking then returns success despite the absent file. Both forced and independently empty attempts record a failed compiler-owned open and return 101. Restoring the byte and compiling it matches the independently empty original executable byte for byte.

The three independent workspaces each ran ten traced cargo +ohm build --offline --bin reader commands and physically executed every successful product. The chain for a real link was GCC, collect2, the distribution’s ld.lld dispatcher, and one rust-lld. Incremental compilation was off on every enrolled rustc. The same isolated Cargo configuration argument supplied rustc’s -Zpublic-api-hash to all three arms. Only the enabled arm received Cargo’s -Zrelink-only flag. The parent separately rejected that switch at argument parsing. Its ten successful or deliberately failing ordinary commands used the supported configuration and establish the parent verdicts.

The PR’s base and head branches are named for 1.98. These exact restored Cargo sources report Cargo 1.99.0 and their respective genuine Git commits. They were built with the official -18 compiler. Execution of the fixture used the older 1.98.1-1 rustc on every arm. The 66 runtime files matched members streamed from the complete official archive, including the driver, frontend, 27 standard-library rlibs and 27 separate rmeta files. The receipts preserve every physical compiler and linker digest, executable digest, typed artifact row, and commitments to the private raw traces and command output. The port’s Git commit credits earlier PR #2. Only the direct #51 boundary was exercised here.

The implementation saved codegen objects and a serialized linker invocation, validated them in RelinkCachePaths::is_valid, and selected use_cached_relink after a dependency-only change. Its validation included no record of assembler inputs consumed while creating those objects. The original relink_only_reuses_root_codegen regression exercised scheduling using a wrapper. This fixture has a real compiler, assembler input, native linker and direct runtime caller. [Original PR](https://github.com/astral-sh/ohm-cargo/pull/51) · [Cache validation](https://github.com/astral-sh/ohm-cargo/blob/caac2566f0fbdf3984f519c2141a6d78e18b01b2/src/compiler/mod.rs#L333) · [Cached dispatch](https://github.com/astral-sh/ohm-cargo/blob/caac2566f0fbdf3984f519c2141a6d78e18b01b2/src/compiler/mod.rs#L678) · [Binary eligibility](https://github.com/astral-sh/ohm-cargo/blob/caac2566f0fbdf3984f519c2141a6d78e18b01b2/src/compiler/fingerprint/mod.rs#L637) · [Historical test](https://github.com/astral-sh/ohm-cargo/blob/caac2566f0fbdf3984f519c2141a6d78e18b01b2/tests/testsuite/freshness.rs#L4452) · [Published compiler](https://github.com/astral-sh/ohm/releases/tag/ohm-1.98.1-1)

Verify the saved results.

    sha256sum -c SHA256SUMS
    python3 -IB verify.py

To repeat each history, use the given Cargo binary as bin/cargo in a private SDK containing the verified compiler. Supply a new output path for every command.

    taskset -c 24-27 python3 -IB reproduce.py NEW_PARENT_DIR PARENT_SDK parent
    taskset -c 24-27 python3 -IB reproduce.py NEW_HEAD_DIR HEAD_SDK relink
    taskset -c 24-27 python3 -IB reproduce.py NEW_HEAD_OFF_DIR HEAD_SDK head-off

A preliminary setup check stopped before any fixture Cargo command because it counted only rlibs when checking the split standard library. The completed inventory includes all corresponding rmeta files. Each recorded fixture invocation was used as run.
