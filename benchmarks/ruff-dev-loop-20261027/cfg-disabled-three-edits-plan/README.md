# Whole-workspace tests after three Ruff edits

`ruff_wasm` and `ty_wasm` each have a wasm32-only integration test named `api`. On x86-64 Linux, an ordinary test build creates both executables. A candidate Cargo change tries to preserve them when the linker’s effective inputs and the compiler’s prior unused-dependency reports permit it. The design requires active tests, alternate SDK files and requested linker side effects to continue to work. A previous prototype omitted a requested layout file. [Reproduction](https://github.com/astral-sh/ohm-cargo/tree/6b4517261da946716383215de280514fe451aa2b/benchmarks/ruff-dev-loop-20261027/cfg-disabled-test-layout-controls)

The frozen plan registers full `cargo test --no-run` after three independent, reversible historical changes to the parser, Python standard-library model and WebAssembly playground. The playground change touches the library implementation and its TypeScript caller. It leaves the test sources untouched. The producer's `InlayHint.text_edits` field gives an ordinary Rust caller a build-time behavioral check.

Each workload has eighteen randomized pairs. The three estimates use one familywise error correction. A separate fresh-command cohort checks the price on an unchanged tree. Physical compiler and linker launches, source restoration, independent full-link output comparisons and the expected native behavior are required before a timed result qualifies.

This plan records the workload selection, order, controls and thresholds before collecting timings. The matching candidate and runner hashes must be bound separately before measurement. [Pinned Ruff tree](https://github.com/astral-sh/ruff/tree/93526150df078af7dd8fc4226cdcc469539d2001)
