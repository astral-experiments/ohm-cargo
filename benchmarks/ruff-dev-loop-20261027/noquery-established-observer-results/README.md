# A save during a warm Rust compilation can leave an incorrect executable fresh

The official Ohm 1.99.0-17 Linux binary and a separately built Cargo/rustc pair from its released sources gave the same results across twelve histories each.

Each trained history first built a real caller three times, reaching a fresh executable that printed 17. An edit to the caller added an output line and forced rustc to run. A second process replaced a two-byte input after the compiler or procedural macro had consumed 17 but before the compiler wrote its dep-info. The changed file encoded 29.

| Acquisition and Cargo history | Executable during the edit | Next two unchanged builds | Empty build after the edit |
| --- | ---: | ---: | ---: |
| Trained, tracked macro file | 17 | 17, 17 (both fresh) | 29 |
| Trained, `include_str!` | 17 | 17, 17 (both fresh) | 29 |
| Trained, invalid-UTF-8 `include_bytes!` | 17 | 17, 17 (both fresh) | 29 |
| First compilation, all three readers | 17 | 29, 29 (first recompiled) | 29 |

These results repeated both for a normal replacement and for an independent inode retaining the original nanosecond timestamp. In every trained case the old executable printed the edited caller's new line, proving the edit reached rustc. The complete record contained the BLAKE3 hash for 29 even though the executable printed 17. Each fixture also deliberately observes a source span from another crate, which activates the affected Cargo freshness path. The experiment measures no elapsed-time endpoint. [Registered design and runnable fixture](https://github.com/astral-sh/ohm-cargo/tree/17c7526dc1e5582a2728bcae6ec7ab290610c721/benchmarks/ruff-dev-loop-20261027/noquery-established-observer-plan)

The unshipped first-observation candidate also kept 17 in the two cold tracked-file cases. Its cold builtin cases recompiled to 29 on the next build. Normal and preserved timestamps gave the same decisions. The separate native proc-macro and standalone metadata controls include a warm `cargo check` success contradicted by the clean compiler's E0308. [Native DSO and metadata controls](https://github.com/astral-sh/ohm-cargo/tree/d94e602e0f3b0eb357e9a386e3fc27971727937b/benchmarks/ruff-dev-loop-20261027/synchronized-compiler-inputs)

Run `python3 -B verify.py` to check all 198 Cargo invocations, compiler execs, real program output, encoded Cargo fingerprints, raw compiler dep-info and independent re-executions of 72 final binaries. The signed-release machine and the source-built machine are separate. `official-17.json`, `released-sources.json` and `candidate.json` contain the per-command value, caller freshness, completeness and untrackable marker, respectively, in that order within each row.
