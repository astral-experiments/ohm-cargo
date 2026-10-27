# Released Ohm 1.99.0-16 checksums for filenames containing spaces

The packaged Linux toolchain recorded the checksum of a different filesystem entry when a path contained a space. In the direct rustc control, the program printed 17 from its actual rlib. Its dep-info instead contained the SHA-256 of the file under the literal backslash-space name used in the Make rule. The native checksum control uses an ordinary external rlib, explicitly enables rustc binary dep-info and SHA-256, and preserves both path spellings.

An independent Cargo fixture uses a four-unit workspace and the packaged `cargo +ohm build --offline -p hold_direct` with normal Ohm defaults. It supplies an ordinary external, prebuilt rlib through `--extern` and leaves both trust overrides unset. It runs the native executable after every build. The edit replaces only the rlib bytes and restores its nanosecond mtime.

| External input | Unchanged build after training | Native value after the rlib changed | Independent empty build |
| --- | --- | ---: | ---: |
| Path containing a space, literal escaped-name neighbor held the future library | Recompiled the reader and wrote a complete OBS1 | 17, all four units reported fresh | 29 |
| Path containing a space, no neighbor | Recompiled the reader with a pending OBS1 | 29 | 29 |
| Ordinary filename | All fresh with a complete OBS1 | 29 | 29 |

The result archive includes all fifteen original Cargo JSON streams, stderr, rustc depfiles, encoded Cargo records, tool invocations, native program outputs and ELF hashes. A separate six-second test placed a FIFO only at the escaped spelling. The actual rlib remained regular, and the released compiler blocked in the kernel waiting for a writer. No writer opened the FIFO.

Run `python3 verify.py` for the offline checks. The archived `input/cargo-decoy-v3.py` contains the ordinary Cargo reproduction and its seven-package source template (only four units build). Run it against an unused output directory with the release-16 SDK selected by `cargo +ohm` and `rustc +ohm`. The sibling `space-decoy.py` and `fifo-decoy.py` reproduce the direct compiler cases. The FIFO helper accepts an unused directory and `--expect blocked`. These controls use the authenticated stock package recorded in the [release-16 installation receipt](https://github.com/astral-sh/ohm-cargo/tree/db71638cbb6dda4752d51ca6373e234811dff18f/benchmarks/ruff-dev-loop-20261027/shipping-16-macro-results).
