# Genoa caller source-path diagnosis

The same existing Rust library and unchanged dependencies produced both complete 75,800,496-byte native caller executables when compiled from the two actual reader path spellings. All three independent native compilations used the stage1 rustc, a fixed logical executable output, and the same read-only captured Ruff workspace. All three programs returned zero with empty stderr and diagnosed SIM222 on lines 2, 3 and 4.

| Actual reader path | Selected archive | Whole ELF SHA-256 | External byte comparison |
|---|---|---|---|
| Copied, 77 bytes | Current emitted archive `d9c99f3e…` | `fbdd8f9538d4d612a6c2923e709592ff7805dde0f6fcf914193ae224b89e731a` | Identical to the initially rejected executable |
| Original, 70 bytes | Same current emitted archive | `c43c42962091e5a21b45d5e13e7a7d0f813dc7b885fc7af825a53cef5ec17bd7` | Identical to the earlier ordinary qualification executable |
| Original, 70 bytes | Independently written ordinary qualification archive `757f7dd6…` | `c43c42962091e5a21b45d5e13e7a7d0f813dc7b885fc7af825a53cef5ec17bd7` | Identical to the qualification executable and the original-path current-input result |

Changing the path spelling of the reader changed one element in the full 457-element rustc argument vector. The source files themselves had the same SHA-256. The current and independent-reference commands for the original spelling had identical arguments, including both extern path spellings. They differed in the bytes made visible at the selected rlib path. Their AST archive, SDK images, environment, working directory and canonical executable path stayed equal. Both actual final linkers were GNU ld.bfd. The packaged Wild binary remained unchanged in the SDK.

An initial supplemental observer expected the direct-rustc command to invoke Wild, whereas the real caller invokes GCC and collect2. It rejected after the first real caller and its numeric checks succeeded. That original exit and its native output were kept. The two remaining commands recorded every actual process exec and identified the system GNU linker by its opened executable, including its inode and SHA-256. The first command was not rerun. Both the original clock and the three new caller results remain separate. No Cargo commands or new timing samples were taken. The Genoa study still has zero admitted pairs.

Run `sha256sum -c SHA256SUMS` and `python3 -IB verify.py`. The portable argument vectors preserve all 457 real compiler elements and all 458 requested proxy elements in order. Private directory prefixes are represented by consistent aliases, with exact SHA-256 and byte length supplied separately for every original argument. The original raw vectors, native process records, streams and complete ELF files remain in private host custody.
