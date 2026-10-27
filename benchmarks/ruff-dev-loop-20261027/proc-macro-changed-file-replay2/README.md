# Changed tracked input on the source replay candidate

A local derive reads an asset containing `91`, parses it to a TokenStream and emits that value in a real Rust constant. We change the asset to `379` and an independent function in the same crate from 7 to 8. One library retains its incremental state. A physically separate library clears only that incremental directory. The source, generated macro image, compiler options, dependency paths and asset are identical for the two edited builds.

Two variants register the asset through `proc_macro::tracked::path`, either just before or just after the parse. The third uses stable `Span::source_text()` just after the parse, with a real `include_bytes!` dependency on the asset. An independent macro reports the byte position of a token from a later included Rust file. Real native Rust callers print the new library value, that span, and the new asset value. We separately compile ordinary bridges against the two libraries and run all four caller combinations. A replay that registers an obsolete asset before learning it must recompute can affect this later observable position.

The results below compare identical final source, compiled plug-in and asset at a single logical path on the candidate compiler. The second implementation stores the parsed sources with the macro query result. All twelve ordinary callers compiled and printed the same new value and native span as the baseline in their respective cases. The two histories now have byte-identical raw metadata in all three cases. [Released and parent controls](https://github.com/astral-sh/ohm-cargo/tree/b9c10857abec3871c69f80a1bc03296355df8bfe/benchmarks/ruff-dev-loop-20261027/proc-macro-changed-file-controls) · [Rejected eager replay](https://github.com/astral-sh/ohm-cargo/tree/75dfe062e1a83627956ca7d6573c748d15ecc4b5/benchmarks/ruff-dev-loop-20261027/proc-macro-changed-file-replay1)

| Compiler | Operation ordering | Warm native result | Empty native result | Ordinary compiles passed | Equal raw metadata |
| --- | --- | --- | --- | ---: | --- |
| replay2 | span-after | `8:#0 bytes(374517..374527):379` | `8:#0 bytes(374517..374527):379` | 4/4 | yes |
| replay2 | track-after | `8:#0 bytes(374523..374533):379` | `8:#0 bytes(374523..374533):379` | 4/4 | yes |
| replay2 | track-before | `8:#0 bytes(374523..374533):379` | `8:#0 bytes(374523..374533):379` | 4/4 | yes |

Each compiler ran nine complete Cargo builds, six ordinary Rust bridge compilations and twelve ordinary consumer compilations. We did not time these correctness controls. The verifier checks the actual Cargo freshness, arguments, exit statuses, raw compiler metadata, ordinary reader diagnostics and executed output. Run `python3 -B verify-late.py` here. The stand-alone `changed-input.py` accepts a private Linux rustup descriptor, matching SDK, Cargo binary and compiler driver.
