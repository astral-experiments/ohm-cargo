# Incremental procedural-macro expansion with a native build input

A procedural-macro crate compiles `native.c` from a conventional Cargo build script, links the object into its host shared library, and expands a `#[derive]` into an integer constant. The executable prints that constant. The only edit is `return 17` to `return 29` in `native.c`, after the initial Cargo process has exited. The build script declares `cargo:rerun-if-changed=native.c`. This fixture has no custom wrapper, sysroot flag, compiler observer or concurrent writer.

| Cargo under released Ohm Rust 1.99.0-17 | After C edit | Following unchanged build | After a real reader edit | Independent empty target |
|---|---:|---:|---:|---:|
| Released Cargo | 17 | 17 | 17 | 29 |
| #261, PGO | 17 | 17 | 17 | 29 |
| #261, matched dev | 17 | 17 | 17 | 29 |
| Revised default, matched dev | 29 | 29 | 29 | 29 |
| Revised Cargo, explicit `-Zcache-proc-macros` | 17 | 17 | 17 | 29 |

Both full producer and reader compilers ran after the C edit in every row. Every immediately repeated command was fully fresh. All five restored and independently clean original programs printed 17. The macro DSO’s native object, `.text` and whole-file hashes changed. Its `.rustc` and `.dynsym` hashes stayed identical. In every row, outputs that printed 17 had ELF SHA-256 `77ddb54ca7f3b3c530fccf864c3fe7a8440e6e9a180a8b0eff806d3a6f4ffe91`. Outputs printing 29 had SHA-256 `d95864fcc3df2d1233befdb17c934a8d5b9fb296f106c23ee42e839cb6cc0fe4`.

In released Rust `bfa236f639034f61ec884c15bd1f4e0b75e508ac`, `provide_derive_macro_expansion` reads the macro-defining crate’s Rust hash and receives the expansion ID and Rust input tokens. The provider’s native implementation can change without changing those inputs. Cargo’s revised default removes the implicit `-Zcache-proc-macros` from both normal rustc flags and fingerprinting. Code that can establish the conditions for using the unstable switch can still enable it explicitly.

## First-use and migration controls

A separate program combines a foreign-span join with a neighboring derive. In these controls the executing Rust compiler has loaded the old DSO and observed its value before the replacement. The native input DSO has unchanged total size, `.rustc`, and `.dynsym`, with changed native `.text`. Runs cover a new timestamp and a retained nanosecond timestamp. The old and replacement source hashes, mappings, Cargo artifacts, derive-call logs, and phase compiler invocations are included.

On #261, the following full compilers recomputed the join to 29, while the cached neighboring derive still returned 17. A proposed restriction to previously identified observers recovered already-known readers. It missed the first edit that introduced an observer, and the first upgrade of a previously wrong output. With the revised default all eight tested directions and timestamp combinations gave `(29,29)` on the first fixed command; every independent empty build also gave `(29,29)`. The initial command in each synchronized race legitimately observed the pre-replacement value 17. An explicit cache disable on the prior Cargo recovered the same outputs.

## Evidence and replay

Run `python3 verify.py` with Python 3.11 or later. The verifier rereads native command traces, runtime outcomes, both ELF identities, and each tar member’s byte count and SHA-256, including the trace files with no executed children. There are 50 ordinary Cargo commands, 60 earlier observer controls and 36 final observer controls.

`ordinary-receipts.tar.gz` and `explicit-receipts.tar.gz` contain the conventional two-crate source, frozen drivers for the experiment, and all command receipts. For a source-only reproduction, copy `input/fixture` into a fresh directory, run `cargo +ohm build -p plain_reader` and execute `target/debug/plain_reader`. Replace `17` with `29` in `driver/native.c`, build and execute again, then compare with a completely empty target and build directory. The two synchronized archives contain the secondary fixture and runner. These experiments ran on Linux x86-64. Their measurements establish output correctness and compiler scheduling; no command durations are used.

The product and checked-in test are in `source-and-test.patch`. `known-observer-v1.patch` is the rejected selective experiment. The `h5-*.json` receipts bind an identically configured dev-profile binary pair built with released -17 Rust and staged for separate Ruff work.

## Repository and pinned CI checks

The CI-only commit 857652135b0e7ee03b9c715787056a60ea313183 adds the targeted test to the existing pinned Linux Ohm job. The physical 1.98.0-9 compiler on the H2 host reproduced 17 with the matched parent Cargo. The fixed Cargo produced 29 from the same source and compiler. The traces show two actual C compilations and two executions of the fixture program in each arm.

The usual, unfeatured Cargo test harness passed all 51 rustflags tests with the normal stable Rust compiler. On the feature-enabled Cargo build and released Ohm -17, the parent passed 43 of 50 and the candidate passed 44 of 51. The same seven tests failed on both source-matched harnesses. The new native regression accounts for the additional pass. `context-receipts.tar.gz` preserves the pinned outputs and complete test module comparisons, including the failures. The separate Rust explicit-option fix is outside this Cargo packet.
