# A re-executed macro must allocate the new virtual source

A local derive reads an asset containing `91`, parses it to a TokenStream and emits that value in a real Rust constant. We change the asset to `379` and an independent function in the same crate from 7 to 8. One library retains its incremental state. A physically separate library clears only that incremental directory. The source, generated macro image, compiler options, dependency paths and asset are identical for the two edited builds.

Two variants register the asset through `proc_macro::tracked::path`, either just before or just after the parse. The third uses stable `Span::source_text()` just after the parse, with a real `include_bytes!` dependency on the asset. An independent macro reports the byte position of a token from a later included Rust file. Real native Rust callers print the new library value, that span, and the new asset value. We separately compile ordinary bridges against the two libraries and run all four caller combinations. A replay that registers an obsolete asset before learning it must recompute can affect this later observable position.

The packaged Linux 1.99.0-15 toolchain and release-matched Rust #233 both accept all twelve ordinary caller combinations and produce identical native spans and raw Rust metadata for each warm/empty comparison. On the actual shipped toolchain, the tracked-file cases print `8:#0 bytes(374523..374533):379` and the stable span case prints `8:#0 bytes(374517..374527):379`. The two configurations run separately. The equality requirement compares the two histories within each configuration.

| Compiler | Operation ordering | Warm native result | Empty native result | Ordinary compiles passed | Equal raw metadata |
| --- | --- | --- | --- | ---: | --- |
| shipping | span-after | `8:#0 bytes(374517..374527):379` | `8:#0 bytes(374517..374527):379` | 4/4 | yes |
| shipping | track-after | `8:#0 bytes(374523..374533):379` | `8:#0 bytes(374523..374533):379` | 4/4 | yes |
| shipping | track-before | `8:#0 bytes(374523..374533):379` | `8:#0 bytes(374523..374533):379` | 4/4 | yes |
| parent | span-after | `8:#0 bytes(374517..374527):379` | `8:#0 bytes(374517..374527):379` | 4/4 | yes |
| parent | track-after | `8:#0 bytes(374523..374533):379` | `8:#0 bytes(374523..374533):379` | 4/4 | yes |
| parent | track-before | `8:#0 bytes(374523..374533):379` | `8:#0 bytes(374523..374533):379` | 4/4 | yes |

Each compiler ran nine complete Cargo builds, six ordinary Rust bridge compilations and twelve ordinary consumer compilations. We did not time these correctness controls. The verifier checks the actual Cargo freshness, arguments, exit statuses, raw compiler metadata, ordinary reader diagnostics and executed output. Run `python3 -B verify-late.py` here. The stand-alone `changed-input.py` accepts a private Linux rustup descriptor, matching SDK, Cargo binary and compiler driver.

The first H3 launcher stopped before Cargo because it referenced a missing Cargo image. A nested namespace attempt stopped before the training command executed, for both compilers. We retained those attempts on H3 and used the original single namespace per command with a mutex and sequential reuse of exactly the same source path. The shipped package used its original installer and binary hashes. [Shipping toolchain authentication and cached-expansion reproduction](https://github.com/astral-sh/ohm-cargo/tree/67e2a6e170d2717320e973c4ee69792692c282fa/benchmarks/ruff-dev-loop-20261027/shipped-15-proc-macro-span)
