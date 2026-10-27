# Full Ruff no-op builds with the original observed-span implementation

This historical Cargo is the common Cargo used by the earlier compiler timing cohort. A subsequent writerless FIFO control exposed a stat/open race in this version. The corrected release Cargo has its own matched full-workspace study. These timings identify only the original measured binaries.

Ruff was pinned to `93526150df078af7dd8fc4226cdcc469539d2001` and the compiler was held at #233. Each arm and endpoint started from its own empty target, shared-build and private registry state. The cold and training commands are reported separately. The 12 balanced pairs per ordinary command include the rustup proxy and stop when Cargo exits. No tests execute inside timing. [Registration and subjects](https://github.com/astral-sh/ohm-cargo/tree/804c80a25fd2bbf29d7c48bc8327eda8bbfef493/benchmarks/ruff-dev-loop-20261027/native-observed-sources)

| Command | Median seconds, parent → candidate | Paired reduction (95% CI) | Faster pairs | Holm p |
| --- | ---: | ---: | ---: | ---: |
| `cargo build` | 1.091 → 1.140 | -13.0% (-51.2 to 11.1%) | 7/12 | 0.4697 |
| `cargo test --no-run` | 6.217 → 1.218 | 83.3% (80.0 to 86.1%) | 12/12 | 0.0043 |

| Work after the unchanged-source training run | Units | Parent full / link-only / native links | Candidate full / link-only / native links |
| --- | ---: | ---: | ---: |
| build | 501 | 0 / 0 / 0 | 0 / 0 / 0 |
| test | 619 | 1 / 50 / 50 | 0 / 0 / 0 |

| True dataclass lint input | Parent full / link-only / native links | Candidate full / link-only / native links |
| --- | ---: | ---: |
| build, edit | 2 / 2 / 3 | 2 / 2 / 3 |
| build, restore | 2 / 2 / 3 | 2 / 2 / 3 |
| test, edit | 5 / 52 / 55 | 4 / 16 / 19 |
| test, restore | 5 / 52 / 55 | 4 / 16 / 19 |

Run `python3 -B verify.py` in this directory to reproduce both statistical comparisons from the 48 untraced commands and check the independent process and ELF witnesses. The verifier compares all ELF bytes outside the two registered Wild fields. The functional phase changes the Ruff dataclass matcher and then restores it. A separate proc macro reads a foreign token span and is checked against a clean compilation. Each changed output and both unchanged controls are retained in the result files.
