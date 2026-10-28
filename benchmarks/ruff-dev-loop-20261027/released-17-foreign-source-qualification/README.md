# Foreign source-text observation on the installed Ohm -17

A source-written macro in a standalone rlib passes a token to a procedural macro that calls `Span::source_text()`. After the macro reads the token, an independent writer atomically replaces a same-width trailing comment in its source file. The rlib stays byte-identical. A new compilation can no longer authenticate the physical source against the rlib and reports no snippet.

All four controlled histories ran ordinary `cargo +ohm build --offline -p hold_direct` on Linux with the unmodified -17 package. The two first-seen observers read 17, recompiled on the next command and produced 29, then stayed fresh. The two previously trained observers read 17 during an actual local caller recompilation, then twice reused that value. Empty state produced 29 in every case. The outcomes repeated when the replacement preserved the source timestamp.

The archive includes the fixture, exact executables' hashes, command logs, physical compiler execs, native stdout, dep-info and encoded Cargo fingerprints. In the trained arms a fresh completed observer preceded a genuine local Rust source edit. Both warm and empty products were executed again before export. No timing was measured.
