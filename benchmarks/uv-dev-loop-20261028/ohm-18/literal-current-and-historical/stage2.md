# Ohm 1.99.0-18 stage-2 toolchains

The control and guarded toolchains were built from Ohm Rust `a4fa11bcd38280639cb94daacc125472657db6c3`, at the same source and build paths. The guarded source adds Rust PR #247. Both use the same stage-1 bootstrap compiler, ThinLTO, one codegen unit, released LLVM 23.1.1 runtime, and released LLD for the final compiler link. The two local Rust compilers omit the release’s rustc profile-guided optimization and BOLT steps. Each package includes a separately PGO-trained Cargo driver for its experimental arm. [Ohm release](https://github.com/astral-sh/ohm/releases/tag/ohm-1.99.0-18), [Rust #247](https://github.com/astral-sh/ohm-rust/pull/247), [release build](https://github.com/astral-sh/ohm/actions/runs/40741806145/job/123006030426).

The stage-2 compiler driver, a target executable and a loaded proc-macro library each contain the scalar 966-byte path comparison in the control and the guarded 1,468-byte comparison in the treatment. The small `rustc` executable loads its arm’s `librustc_driver` shared library. Each package passed Cargo check, build and test compilation. The target checked 10,609 ordered path pairs. The macro checked 10,404 pairs when executed by rustc, and again when executed by rustdoc.

Standalone rustc has one linker-default difference relevant to reproduction. Bootstrap requires `rust.lld=false` with the external LLVM SDK. Both locally rebuilt Linux target specifications select `gnu-cc`. The installed release selects `gnu-lld-cc` and a self-contained linker. In the normal Ohm Cargo workflow, all three Cargo drivers explicitly disable LLD and the self-contained linker, add the packaged Wild directory with `-B`, and request `-fuse-ld=bfd`. Direct `execve` traces on the same one-file crate verified that all three ran the same distributed Wild ELF. The separate uv protocol installs the predeclared Wild for each arm and verifies that actual child as part of admission.

To verify the archive from any directory containing it, run

```sh
unzip literal-stage2-evidence.zip -d literal-stage2-evidence
(cd literal-stage2-evidence && sha256sum -c SHA256SUMS)
```

`round18-compiler/full-toolchain/paired-stage2-verified.json` gives both driver and target-library hashes, the compiler and Cargo versions, and the target-spec differences. Its `receipts` directory contains the bootstrap commands, actual LLD command lines, package tests, comparison disassemblies, and `default-linker-{shipped,base,guard}` traces. The evidence archive’s SHA-256 is `d6ccb7345506e87efa19eed360fd86769a98299220c5a8e49c8d1e1a6192c19a`.
