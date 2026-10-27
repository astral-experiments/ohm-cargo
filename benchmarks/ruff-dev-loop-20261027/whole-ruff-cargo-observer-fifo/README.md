# Full Ruff no-op builds with FIFO-safe observed spans

The candidate opens each observed input without blocking and checks the opened file descriptor. This is the release-built Cargo from the corrected source. Both Cargo binaries used the same external PGO training and the same compiler, canonical source and target paths, and Cargo display version.

Ruff was pinned to `93526150df078af7dd8fc4226cdcc469539d2001` and the compiler was held at #233. Each arm and endpoint started from its own empty target, shared-build and private registry state. The cold and training commands are reported separately. The 12 balanced pairs per ordinary command include the rustup proxy and stop when Cargo exits. No tests execute inside timing. [Registration and subjects](https://github.com/astral-sh/ohm-cargo/tree/ab89add1712d466e07f7eb2f373e0e2f5d852068/benchmarks/ruff-dev-loop-20261027/observed-span-fifo-qualification)

| Command | Median seconds, parent → candidate | Paired reduction (95% CI) | Faster pairs | Holm p |
| --- | ---: | ---: | ---: | ---: |
| `cargo build` | 0.644 → 0.641 | -10.5% (-36.7 to 9.3%) | 4/12 | 0.4091 |
| `cargo test --no-run` | 6.088 → 0.956 | 85.5% (83.1 to 87.5%) | 12/12 | 0.0043 |

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
