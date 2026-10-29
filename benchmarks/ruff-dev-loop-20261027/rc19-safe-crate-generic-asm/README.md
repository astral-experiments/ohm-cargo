# Assembler file reads across an ordinary Rust library boundary

Released Ohm 1.99.0-19 on Linux x86_64 reused a terminal object's previous bytes after the assembler input changed or disappeared. The executable crate forbids unsafe Rust. Its only operation is to call two safe ordinary Rust library functions and print their values. One function is generic and instantiates inline assembly in the executable's own codegen. A private, same-signature change to the other library makes Cargo genuinely rebuild the terminal unit. There are no proc macros, wrappers, build scripts, extra Rust flags or direct native libraries in the workspace. Incremental compilation is disabled throughout the Cargo comparison.

| Ordinary Cargo build | Correct value with edited operand | Actual edited value | Actual after removing the operand |
| --- | --- | --- | --- |
| Released default | 9:29 | 9:17, repeated on an unchanged run | Successful program printing 7:17 |
| Same SDK with `-Zrelink-only=no` | 9:29 | 9:29, repeated on an unchanged run | Cargo 101 from assembly |
| Independent empty builds, both modes | 9:29 | 9:29 | Cargo 101 from assembly |

In a separately trained target, selecting `-Zrelink-only=no` on the first and second unchanged commands after poisoning ran zero compilers and left the old executable printing 9:17. A full compile of just the executable with that switch returned 9:29 and the following fresh run agreed. This difference matters when changing defaults for an existing target, including a plain binary from a binary-only package.

## Which inputs Cargo sees

The released Rust compiler built the upstream generic rlib while the assembler input did not exist. Holding that exact rlib and terminal source fixed, four full consumer compiles with `-Zbinary-dep-depinfo=yes -Zchecksum-hash-algorithm=blake3` observed 17, 29, the missing-file diagnostic and 17. All four depfiles name the rlib and include checksums. None names the file that assembly read. The ordinary retained Cargo binary's two object files have normal `.rcgu.o` names. Those object bytes, its serialized `.rlink`, and its checked cache manifest contained neither the operand filename nor the assembler directive spelling.

Rust writes dep-info before it starts this codegen. The binary-dependency option adds compiler backend and Rust crate artifact paths to the source map and explicitly tracked files. The `.rlink` serialization carries the compiled modules, crate information, metadata, and output filenames. Rust's internal LLVM assembly predicate guards ThinLTO object-cache publication. Cargo's separate link-only codegen reuse admits LTO Off or OnlyObject and has no corresponding compiler-issued assertion. [Dep-info and codegen order](https://github.com/astral-sh/ohm-rust/blob/eef2f3425c1c6f7fddfb4555769a9f90fe1e0f53/compiler/rustc_driver_impl/src/lib.rs#L301) [Binary dependency enumeration](https://github.com/astral-sh/ohm-rust/blob/eef2f3425c1c6f7fddfb4555769a9f90fe1e0f53/compiler/rustc_interface/src/passes.rs#L665) [ThinLTO guard](https://github.com/astral-sh/ohm-rust/blob/eef2f3425c1c6f7fddfb4555769a9f90fe1e0f53/compiler/rustc_codegen_llvm/src/back/lto.rs#L812) [Cargo admission](https://github.com/astral-sh/ohm-cargo/blob/2447f7f4eacb4fdf499899929f08d0de19abb4d0/src/compiler/mod.rs#L1123)

Cargo's checked manifest verifies existing generated objects. Its unused-extern proof describes Rust dependencies and its checksum marker describes path encoding. The explicit check-session work tracks Cargo planning inputs. Rust's external-driver identity and source-file query support rely on inputs already known to the compiler or driver. None of these existing interfaces certifies an assembler's positive or failed file lookups across all emitted codegen units. [Cargo #197](https://github.com/astral-sh/ohm-cargo/pull/197) [Cargo #198](https://github.com/astral-sh/ohm-cargo/pull/198) [Cargo #107](https://github.com/astral-sh/ohm-cargo/pull/107) [Rust #71](https://github.com/astral-sh/ohm-rust/pull/71) [Rust #73](https://github.com/astral-sh/ohm-rust/pull/73)

The empirical comparison used the packaged GCC/LLVM path and real executable stdout. Compiler process classifications come from ordinary Cargo verbose command lines, with build completion and typed artifact freshness checked against its JSON stream. This experiment isolates the additional Cargo shortcut by disabling rustc incremental. Ordinary incremental codegen has its own separately demonstrated stale-input behavior. A file-only edit that Cargo has no reason to notice can still leave the entire build fresh.

## Verify or reproduce

Run the following in this directory. The verifier reopens the complete projected command output, raw depfile commitments and source identities for 22 ordinary Cargo commands plus five direct compiler invocations. The native result rows record the measured program output and complete ELF SHA-256. Absolute acquisition paths have stable aliases.

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py
python3 -IB replay.py /absolute/new-workspace /absolute/official-19-sdk
python3 -IB replay-switch.py /absolute/new-switch /absolute/official-19-sdk
python3 -IB probe-direct.py /absolute/new-direct /absolute/official-19-sdk /absolute/new-workspace/default/project
```
