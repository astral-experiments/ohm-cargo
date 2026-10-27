# Two unchanged parser test executables after a real Ruff edit

Ruff commit `83a3afc315` fixes indentation when a block starts with multiple comments. An ordinary Rust caller returned different output when we reversed the patch, then recovered the original output when we restored it. We applied all three files in a private copy of pinned Ruff using the published Linux Ohm 1.99.0-16 toolchain. [Frozen edit, inputs and native witness](https://github.com/astral-sh/ohm-cargo/tree/6ed5aa30871d5a4d30f77a13c7c9cbd1b3954d15/benchmarks/ruff-dev-loop-20261027/dedent-16-discovery-plan)

| Parser package command | Full compiles after the edit | Link-only compiler invocations | Wild links | Native output |
| --- | ---: | ---: | ---: | --- |
| `cargo build -p ruff_python_parser` | 1 | 0 | 0 | The changed trivia library compiled. |
| `cargo test --no-run -p ruff_python_parser` | 1 | 2 | 2 | The parser unit-test executable and the fixtures executable were relinked. Both SHA-256 digests stayed identical. |

Both directions gave the same physical process counts. The only declared files whose bytes changed on reversal were the trivia library's `.rlib` and `.rmeta`, out of 162 build files and 266 test-build files. The third executable, the inline-test generator, stayed identical too. Each immediate repeat reached 90/90 or 148/148 fresh with zero compiler or linker launches. No Ruff test ran. This establishes the size and location of the opportunity. Skipping the two links requires a proof that changing an input archive cannot affect these outputs.

Run `python3 -B verify.py` to reconstruct the commands and per-phase results from the 521 captured files. The original and portable hashes of each file are in `originals.json`. Twelve Cargo output files have a machine-specific registry directory replaced by a stable alias.
