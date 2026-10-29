# Serial rustc metadata decoding after two edits to uv

The released Ohm -18 compiler decoded the dependency tables for exported generic symbols on a single thread in both profiles. The 489 decodes occupied 341 ms after a private predicate edit and 265 ms after a Homebrew help-text edit. The enclosing query took 445 ms and 369 ms, respectively. The compiler used eight threads on four physical CPUs. These measurements describe the released compiler while self-profiling. The normal elapsed-time samples are in the [full-toolchain study](../full-toolchain-wall/README.md).

The [archive](measureme-recordings.tar.zst) contains both original measureme v9 streams, collection receipts, standalone Python decoders, computed results, and the Ohm branch and PR source audit. After extracting it, follow the commands in `critical-path-scan/README.md` to decode either stream. Archive SHA-256 `c6c0979201ab31dde7783fcbb0e29c63dd0e6f04328a513015e1c7384a7ecfcb`.
