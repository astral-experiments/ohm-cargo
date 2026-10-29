## Upstream Rust 1.99.1 and `.incbin`

Fourteen ordinary, isolated library builds used an existing upstream Linux x86-64 compiler and Cargo. The private `+ohm` alias in this fixture points to upstream Rust 1.99.1. The installed Cargo/rustc executables, driver, LLVM and standard library are SHA-256-bound. The installed distribution manifest's versions and all three component archive hashes match the complete dated upstream manifest bundled here. The rustc source commit also matches the upstream 1.99.1 Git tag. No component was downloaded or installed for this experiment. [Upstream Rust 1.99.1](https://github.com/rust-lang/rust/tree/58cf8f9c35b355199727627d07ae34a4e2846d67)

The fixture passes its consumer's Cargo.toml to the integrated assembler via `.incbin`. The production library and caller sources stay fixed while the study removes one `test = false` line, repeats, independently builds the edited state in an empty target/store, then restores and repeats. The two series use physically independent output and build directories. Every generated executable was linked against its own retained `.rlib` and run. For each archive the native `.rodata.manifest_fixture` section in its actual object was reopened independently and compared to runtime output and the original and edited manifest bytes. Each recorded dep-info digest was revalidated against the corresponding file before projecting its contents.

| Ordinary Cargo setting | Original | After edit | Unchanged | Independent edited build | Restored |
| --- | --- | --- | --- | --- | --- |
| `CARGO_INCREMENTAL=1` | 17 | 17 | 17 | 29 | 17 |
| `CARGO_INCREMENTAL=0` | 17 | 29 | 29 | 29 | 17 |

The incremental edit launches a real compiler. Its object still contains the previous manifest bytes. The ordinary Rust dep-info names the Rust source and omits the assembler's implicit file. The matching released Ohm result is independently recorded in the separate stock packet with manifest `c88045b0bab9a4e6d67e7d8709822447470a37d529847a877c1598278cad6024`.

Run `python3 -IB verify.py --mutations`. The packet contains source, original executable/trace/archive SHA-256 commitments, normalized ordinary compiler argv and dep-info, actual program values, and the exact embedded sections. The upstream toolchain was already installed; its installed local binaries were hashed and its installer archive hashes were compared with the official distribution manifest. The archives themselves were not fetched for this check.
